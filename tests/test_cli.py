from __future__ import annotations

import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from zip_preflight.cli import main
from zip_preflight.scanner import RULE_CODES


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous_directory = Path.cwd()
        self.addCleanup(os.chdir, previous_directory)
        os.chdir(self.root)

    def archive(self, filename="clean.zip", member="hello.txt"):
        path = self.root / filename
        with zipfile.ZipFile(path, "w") as archive:
            info = zipfile.ZipInfo(member)
            info.filename = member
            archive.writestr(info, "hello")
        return str(path)

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        return code, output.getvalue()

    def config(self, **settings):
        path = self.root / ".zip-preflight.json"
        path.write_text(json.dumps(settings), encoding="utf-8")
        return str(path)

    def test_clean_exit(self):
        code, text = self.run_cli(self.archive())
        self.assertEqual(0, code)
        self.assertIn("PASS", text)
        self.assertIn("Payloads were not inspected", text)

    def test_list_rules_needs_no_archive(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exit_status:
            main(["--list-rules"])
        self.assertEqual(0, exit_status.exception.code)
        self.assertEqual(sorted(RULE_CODES), output.getvalue().splitlines())

    def test_error_finding_exit(self):
        code, text = self.run_cli(self.archive(member="../escape"))
        self.assertEqual(1, code)
        self.assertIn("PARENT_PATH", text)

    def test_warning_policy(self):
        path = self.archive(member="folder\\file")
        self.assertEqual(1, self.run_cli(path)[0])
        code, text = self.run_cli("--fail-on", "error", path)
        self.assertEqual(0, code)
        self.assertIn("WARNING BACKSLASH_PATH", text)

    def test_invalid_zip_and_missing_input_exit(self):
        path = self.root / "broken.zip"
        path.write_text("broken", encoding="utf-8")
        for value in (str(path), str(self.root / "missing.zip")):
            with self.subTest(value=value):
                code, text = self.run_cli(value)
                self.assertEqual(2, code)
                self.assertIn("Unable to scan", text)

    def test_json_schema_and_entry_index(self):
        code, text = self.run_cli("--format", "json", self.archive(member="NUL.txt"))
        data = json.loads(text)
        self.assertEqual(1, code)
        self.assertEqual(1, data["schema_version"])
        self.assertEqual(1, data["exit_code"])
        self.assertEqual(0, data["archives"][0]["findings"][0]["entry_index"])
        self.assertTrue(data["archives"][0]["scan_complete"])
        self.assertIn("max_ratio", data["limits"])

    def test_json_error_is_reported_on_stdout(self):
        code, text = self.run_cli("--format", "json", str(self.root / "missing.zip"))
        self.assertEqual(2, code)
        self.assertIsNotNone(json.loads(text)["archives"][0]["error"])

    def test_multiple_archives_deduplicated(self):
        first = self.archive()
        second = self.archive("other.zip", "NUL")
        code, text = self.run_cli("--format", "json", first, second, first)
        self.assertEqual(1, code)
        self.assertEqual(2, len(json.loads(text)["archives"]))

    def test_quoted_glob_is_expanded(self):
        self.archive("b.zip")
        self.archive("a.zip")
        code, text = self.run_cli("--format", "json", str(self.root / "*.zip"))
        self.assertEqual(0, code)
        self.assertEqual(2, len(json.loads(text)["archives"]))
        self.assertTrue(json.loads(text)["archives"][0]["archive"].endswith("a.zip"))

    def test_literal_brackets_in_filename(self):
        path = self.archive("data[1].zip")
        code, text = self.run_cli("--format", "json", path)
        self.assertEqual(0, code)
        self.assertEqual(path, json.loads(text)["archives"][0]["archive"])

    def test_unmatched_glob_is_error(self):
        self.assertEqual(2, self.run_cli(str(self.root / "*.zip"))[0])

    def test_unreadable_takes_precedence_over_findings(self):
        self.assertEqual(2, self.run_cli(self.archive(member="NUL"), str(self.root / "missing"))[0])

    def test_terminal_control_is_escaped(self):
        _, text = self.run_cli(self.archive(member="bad\x1b[31m\nname"))
        self.assertNotIn("\x1b", text)
        self.assertIn("\\u001b", text)
        self.assertIn("\\n", text)

    def test_json_preserves_unicode_through_escapes(self):
        _, text = self.run_cli("--format", "json", self.archive(member="数据/CON.txt"))
        self.assertEqual("数据/CON.txt", json.loads(text)["archives"][0]["findings"][0]["member"])

    def test_custom_limits(self):
        self.assertEqual(1, self.run_cli("--max-member-size", "1", self.archive())[0])

    def test_default_config_and_cli_overrides(self):
        self.config(format="json", fail_on="error", max_member_size=1)
        path = self.archive(member="folder\\file")
        code, text = self.run_cli(path)
        self.assertEqual(1, code)
        self.assertEqual(1, json.loads(text)["limits"]["max_member_size"])
        code, text = self.run_cli("--max-member-size", "100", path)
        self.assertEqual(0, code)
        self.assertEqual("error", json.loads(text)["fail_on"])
        self.assertEqual(
            1, self.run_cli("--max-member-size", "100", "--fail-on", "warning", path)[0]
        )
        _, text = self.run_cli("--format", "text", path)
        self.assertTrue(text.startswith("FAIL"))

    def test_explicit_config_replaces_default_config(self):
        self.config(max_member_size=1)
        explicit = self.root / "other.json"
        explicit.write_text('{"format": "json", "max_member_size": 100}', encoding="utf-8")
        code, text = self.run_cli("--config", str(explicit), self.archive())
        self.assertEqual(0, code)
        self.assertEqual(100, json.loads(text)["limits"]["max_member_size"])

    def test_no_config_skips_invalid_default_file(self):
        (self.root / ".zip-preflight.json").write_text("not JSON", encoding="utf-8")
        self.assertEqual(0, self.run_cli("--no-config", self.archive())[0])

    def test_config_errors_are_reported_before_scanning(self):
        for value in ("missing.json", str(self.root)):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()) as errors:
                with self.assertRaises(SystemExit) as raised:
                    self.run_cli("--config", value, "missing.zip")
                self.assertEqual(2, raised.exception.code)
                self.assertIn("Invalid config", errors.getvalue())

    def test_ignore_rules_are_visible_and_cli_replaces_or_clears_them(self):
        self.config(format="json", ignore_rules=["WINDOWS_DEVICE"])
        path = self.archive(member="NUL.txt")
        code, text = self.run_cli(path)
        data = json.loads(text)
        self.assertEqual(0, code)
        self.assertEqual(["WINDOWS_DEVICE"], data["ignore_rules"])
        self.assertEqual("WINDOWS_DEVICE", data["archives"][0]["findings"][0]["code"])
        self.assertEqual(1, self.run_cli("--ignore-rule", "LONG_PATH", path)[0])
        self.assertEqual(1, self.run_cli("--no-ignore-rules", path)[0])
        code, text = self.run_cli("--format", "text", path)
        self.assertEqual(0, code)
        self.assertIn("IGNORED ERROR WINDOWS_DEVICE", text)

    def test_repeated_ignore_rule_flags(self):
        path = self.archive(member="bad\\NUL.txt")
        self.assertEqual(1, self.run_cli("--ignore-rule", "WINDOWS_DEVICE", path)[0])
        self.assertEqual(
            0,
            self.run_cli(
                "--ignore-rule", "WINDOWS_DEVICE", "--ignore-rule", "BACKSLASH_PATH", path
            )[0],
        )

    def test_ignored_rules_do_not_hide_unreadable_input(self):
        self.assertEqual(
            2, self.run_cli("--ignore-rule", "WINDOWS_DEVICE", str(self.root / "missing.zip"))[0]
        )

    def test_summary_counts_and_examples_use_complete_findings(self):
        path = self.root / "many.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("dir//", "")
            archive.writestr("dir///", "")
            archive.writestr("NUL.txt", "")
        code, text = self.run_cli("--summary", "--max-findings", "1", str(path))
        self.assertEqual(1, code)
        self.assertIn("3/3 entries checked", text)
        self.assertIn("Findings: 1 errors, 2 warnings, 0 ignored", text)
        self.assertIn("NON_CANONICAL_PATH [warning]: 2", text)
        self.assertIn("WINDOWS_DEVICE [error]: 1", text)
        self.assertIn("2 findings omitted", text)
        self.assertNotIn('ERROR WINDOWS_DEVICE "NUL.txt"', text)

    def test_max_findings_implies_summary_and_zero_hides_examples(self):
        code, text = self.run_cli("--max-findings", "0", self.archive(member="NUL.txt"))
        self.assertEqual(1, code)
        self.assertIn("WINDOWS_DEVICE [error]: 1", text)
        self.assertIn("1 findings omitted", text)
        self.assertNotIn('ERROR WINDOWS_DEVICE "NUL.txt"', text)

    def test_summary_default_shows_five_examples(self):
        path = self.root / "many.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for index in range(7):
                archive.writestr(f"{index}/NUL", "")
        code, text = self.run_cli("--summary", str(path))
        self.assertEqual(1, code)
        self.assertEqual(5, text.count("ERROR WINDOWS_DEVICE "))
        self.assertIn("WINDOWS_DEVICE [error]: 7", text)
        self.assertIn("2 findings omitted", text)

    def test_no_summary_restores_full_text_report(self):
        self.config(summary=True, max_findings=0)
        _, text = self.run_cli("--no-summary", self.archive(member="NUL.txt"))
        self.assertIn('ERROR WINDOWS_DEVICE "NUL.txt"', text)
        self.assertNotIn("findings omitted", text)
        self.assertNotIn("[error]:", text)

    def test_json_summary_preserves_all_findings_and_schema(self):
        path = self.root / "many.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("NUL.txt", "")
            archive.writestr("dir//", "")
        code, text = self.run_cli("--format", "json", "--max-findings", "0", str(path))
        data = json.loads(text)
        self.assertEqual(1, code)
        self.assertEqual(1, data["schema_version"])
        self.assertEqual(2, len(data["archives"][0]["findings"]))
        self.assertEqual(2, data["summary"]["total_findings"])
        self.assertEqual(1, data["summary"]["errors"])
        self.assertEqual(1, data["summary"]["warnings"])
        self.assertEqual(data["summary"], data["archives"][0]["summary"])
        _, text = self.run_cli("--format", "json", str(path))
        self.assertNotIn("summary", json.loads(text))

    def test_multi_archive_summary_separates_failures_and_input_errors(self):
        clean = self.archive()
        bad = self.archive("bad.zip", "NUL")
        missing = str(self.root / "missing.zip")
        code, text = self.run_cli("--summary", clean, bad, missing)
        self.assertEqual(2, code)
        self.assertIn("Summary: 3 archives; 1 passed, 1 failed, 1 unreadable", text)
        _, text = self.run_cli("--summary", "--format", "json", clean, bad, missing)
        summary = json.loads(text)["summary"]
        self.assertEqual(1, summary["passed_archives"])
        self.assertEqual(1, summary["failed_archives"])
        self.assertEqual(1, summary["unreadable_archives"])
        self.assertEqual(1, summary["incomplete_archives"])

    def test_json_summary_tracks_ignored_findings(self):
        _, text = self.run_cli(
            "--format",
            "json",
            "--summary",
            "--ignore-rule",
            "WINDOWS_DEVICE",
            self.archive(member="NUL.txt"),
        )
        data = json.loads(text)
        self.assertEqual(0, data["exit_code"])
        self.assertEqual(0, data["summary"]["errors"])
        self.assertEqual(1, data["summary"]["ignored_findings"])
        self.assertTrue(data["summary"]["by_rule"][0]["ignored"])

    def test_summary_uses_selected_warning_policy(self):
        code, text = self.run_cli(
            "--format", "json", "--summary", "--fail-on", "error", self.archive(member="dir//")
        )
        summary = json.loads(text)["summary"]
        self.assertEqual(0, code)
        self.assertEqual(1, summary["warnings"])
        self.assertEqual(1, summary["passed_archives"])
        self.assertEqual(0, summary["failed_archives"])

    def test_clean_summary_has_zero_findings(self):
        code, text = self.run_cli("--format", "json", "--summary", self.archive())
        summary = json.loads(text)["summary"]
        self.assertEqual(0, code)
        self.assertEqual(0, summary["total_findings"])
        self.assertEqual([], summary["by_rule"])
        self.assertEqual(1, summary["passed_archives"])

    def test_summary_preserves_incomplete_scan_status(self):
        path = self.root / "many.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("a", "")
            archive.writestr("b", "")
        code, text = self.run_cli("--summary", "--format", "json", "--max-entries", "1", str(path))
        data = json.loads(text)
        self.assertEqual(1, code)
        self.assertFalse(data["archives"][0]["scan_complete"])
        self.assertEqual(1, data["summary"]["incomplete_archives"])
        self.assertEqual(1, data["summary"]["checked_entries"])
        self.assertEqual(2, data["summary"]["entry_count"])

    def test_summary_escapes_terminal_controls(self):
        _, text = self.run_cli("--summary", self.archive(member="bad\x1b[31m\nname"))
        self.assertNotIn("\x1b", text)
        self.assertIn("\\u001b", text)

    def test_invalid_options_exit_two(self):
        for args in (
            (),
            ("--max-ratio", "nan", "a"),
            ("--max-ratio", "inf", "a"),
            ("--max-ratio", "0", "a"),
            ("--max-entries", "-1", "a"),
            ("--max-total-size", "oops", "a"),
            ("--max-member-size", "0", "a"),
            ("--fail-on", "never", "a"),
            ("--max-findings", "-1", "a"),
            ("--max-findings", "oops", "a"),
            ("--ignore-rule", "TYPO", "a"),
            ("--config", "a.json", "--no-config", "a"),
        ):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as raised:
                    main(args)
                self.assertEqual(2, raised.exception.code)

    def test_version_needs_no_archive(self):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as raised:
                main(["--version"])
        self.assertEqual(0, raised.exception.code)
        self.assertIn("zip-preflight 0.1.0", output.getvalue())


if __name__ == "__main__":
    unittest.main()

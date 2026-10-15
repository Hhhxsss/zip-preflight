from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from zip_preflight.cli import main


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

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

    def test_clean_exit(self):
        code, text = self.run_cli(self.archive())
        self.assertEqual(0, code)
        self.assertIn("PASS", text)
        self.assertIn("Payloads were not inspected", text)

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

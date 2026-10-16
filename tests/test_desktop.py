from __future__ import annotations

import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from zip_preflight.config import Settings
from zip_preflight.desktop import (
    RULE_HELP,
    desktop_settings,
    display_text,
    finding_details,
    save_report,
    text_report,
)
from zip_preflight.models import Finding
from zip_preflight.reporting import build_json_report
from zip_preflight.scanner import RULE_CODES, scan_archive


class DesktopReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "资料 & (版本)%1.ZIP"
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("资料/CONOUT$.txt", "hello")
            archive.writestr("dir//", "")
        self.report = scan_archive(self.path)

    def test_every_rule_has_a_readable_explanation(self):
        self.assertEqual(RULE_CODES, RULE_HELP.keys())

    def test_display_names_keep_unicode_and_expose_controls(self):
        text = display_text("资料/a\n\x1b\u202ename")
        self.assertIn("资料/a", text)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("\u202e", text)
        self.assertIn("\\u202e", text)
        self.assertIn("\\n", text)

    def test_desktop_ignores_working_directory_config(self):
        config = self.root / ".zip-preflight.json"
        config.write_text('{"ignore_rules": ["WINDOWS_DEVICE"]}', encoding="utf-8")
        previous = Path.cwd()
        try:
            os.chdir(self.root)
            self.assertEqual(Settings(), desktop_settings())
            self.assertEqual(("WINDOWS_DEVICE",), desktop_settings(str(config)).ignore_rules)
        finally:
            os.chdir(previous)

    def test_saved_json_matches_cli_schema_and_keeps_all_findings(self):
        destination = self.root / "报告.json"
        settings = Settings(summary=True, max_findings=0, ignore_rules=("NON_CANONICAL_PATH",))
        save_report(destination, self.report, settings)
        actual = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(
            build_json_report(
                [self.report],
                limits=settings.limits,
                fail_on=settings.fail_on,
                ignore_rules=settings.ignore_rules,
                summary=True,
            ),
            actual,
        )
        self.assertEqual(2, len(actual["archives"][0]["findings"]))
        self.assertEqual(1, actual["summary"]["ignored_findings"])

    def test_text_report_contains_complete_details_and_suggestions(self):
        destination = self.root / "报告.txt"
        save_report(destination, self.report, Settings(max_findings=0))
        text = destination.read_text(encoding="utf-8")
        self.assertIn("Windows 保留设备名", text)
        self.assertIn("资料/CONOUT$.txt", text)
        self.assertIn("dir//", text)
        self.assertIn("建议：", text)
        self.assertIn("未通过", text)

    def test_related_entry_and_ignore_policy_are_explained(self):
        finding = Finding("PATH_COLLISION", "error", "message", "Docs/a", "docs/b", 2)
        details = finding_details(finding, Settings(ignore_rules=("PATH_COLLISION",)))
        self.assertIn("已忽略", details)
        self.assertIn("关联文件：docs/b", details)
        self.assertIn("条目序号：3", details)

    def test_save_cannot_replace_archive_or_hardlink(self):
        before = self.path.read_bytes()
        with self.assertRaises(ValueError):
            save_report(self.path, self.report, Settings())
        alias = self.root / "alias.json"
        os.link(self.path, alias)
        with self.assertRaises(ValueError):
            save_report(alias, self.report, Settings())
        self.assertEqual(before, self.path.read_bytes())

    def test_failed_replace_keeps_existing_report_and_removes_temporary_file(self):
        destination = self.root / "report.json"
        destination.write_text("previous report", encoding="utf-8")
        before = sorted(p.name for p in self.root.iterdir())
        with patch("zip_preflight.desktop.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                save_report(destination, self.report, Settings())
        self.assertEqual("previous report", destination.read_text(encoding="utf-8"))
        self.assertEqual(before, sorted(p.name for p in self.root.iterdir()))

    def test_invalid_extension_does_not_write_a_file(self):
        destination = self.root / "report.csv"
        with self.assertRaises(ValueError):
            save_report(destination, self.report, Settings())
        self.assertFalse(destination.exists())

    def test_unreadable_zip_can_be_saved_as_an_error_report(self):
        report = scan_archive(self.root / "missing.zip")
        destination = self.root / "error.json"
        save_report(destination, report, Settings())
        self.assertEqual(2, json.loads(destination.read_text())["exit_code"])
        self.assertIn("无法读取", text_report(report, Settings()))


if __name__ == "__main__":
    unittest.main()

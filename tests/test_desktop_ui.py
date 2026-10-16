from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from zip_preflight.desktop_ui import PAGE_SIZE, ResultWindow
from zip_preflight.models import Finding, Report


class DesktopWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if (
            sys.platform == "darwin"
            and sys.version_info[:2] == (3, 12)
            and os.environ.get("GITHUB_ACTIONS") == "true"
        ):
            # This hosted runner hangs in tk.Tk() before any test starts.
            # macOS 3.14 and Windows still exercise the real window tests.
            raise unittest.SkipTest("Tk initialization hangs on the macOS Python 3.12 CI runner")
        try:
            import tkinter as tk
        except ImportError as error:
            raise unittest.SkipTest(f"Tk is unavailable: {error}") from error
        try:
            root = tk.Tk()
        except tk.TclError as error:
            raise unittest.SkipTest(f"No graphical display: {error}") from error
        root.withdraw()
        root.destroy()
        cls.tk = tk

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.path = self.folder / "资料 & (版本)%1.ZIP"
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("资料/CONOUT$.txt", "hello")
            archive.writestr("dir//", "")
        self.root = self.tk.Tk()
        self.root.withdraw()
        self.app = ResultWindow(self.root)
        self.addCleanup(lambda: None if self.app.closed else self.app.close())

    def wait(self):
        deadline = time.monotonic() + 6
        while self.app.busy and time.monotonic() < deadline:
            self.root.update()
            time.sleep(0.01)
        self.root.update()
        self.assertFalse(self.app.busy, "Desktop operation did not complete")

    def inspect(self):
        self.app.inspect(str(self.path))
        self.wait()

    def test_open_button_scans_selected_zip_and_shows_details(self):
        with patch("tkinter.filedialog.askopenfilename", return_value=str(self.path)):
            self.app.open_button.invoke()
        self.wait()
        self.assertIsNotNone(self.app.report)
        self.assertEqual(2, len(self.app.tree.get_children()))
        self.assertIn("错误 1", self.app.counts.get())
        self.assertIn("警告 1", self.app.counts.get())
        self.assertIn("Windows 保留设备名", self.app.details.get("1.0", "end"))
        self.assertIn("建议：", self.app.details.get("1.0", "end"))
        self.assertFalse(self.app.save_button.instate(["disabled"]))

    def test_clean_zip_has_a_clear_pass_result(self):
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr("hello.txt", "hello")
        self.inspect()
        self.assertEqual("通过本次检查", self.app.status.get())
        self.assertEqual((), self.app.tree.get_children())
        self.assertIn("没有发现问题", self.app.details.get("1.0", "end"))

    def test_scan_runs_in_background_and_leaves_tk_responsive(self):
        release = threading.Event()
        self.addCleanup(release.set)

        def slow_scan(path, **_kwargs):
            release.wait(3)
            return Report(archive=path, scan_complete=True)

        with patch("zip_preflight.desktop_ui.scan_archive", side_effect=slow_scan):
            self.app.inspect(str(self.path))
            heartbeat = []
            self.root.after(0, heartbeat.append, True)
            self.root.update()
            self.assertEqual([True], heartbeat)
            self.assertTrue(self.app.busy)
            self.assertTrue(self.app.save_button.instate(["disabled"]))
            release.set()
            self.wait()

    def test_save_button_exports_full_json_and_text(self):
        self.inspect()
        for suffix in ("json", "txt"):
            destination = self.folder / f"report.{suffix}"
            with (
                self.subTest(suffix=suffix),
                patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)),
            ):
                self.app.save_button.invoke()
                self.wait()
            self.assertTrue(destination.is_file())
            if suffix == "json":
                data = json.loads(destination.read_text(encoding="utf-8"))
                self.assertEqual(2, len(data["archives"][0]["findings"]))
            else:
                self.assertIn("建议：", destination.read_text(encoding="utf-8"))
            self.assertIn("报告已保存", self.app.note.get())

    def test_cancelling_save_does_not_change_the_result(self):
        self.inspect()
        before = self.app.status.get()
        with patch("tkinter.filedialog.asksaveasfilename", return_value=""):
            self.app.save_button.invoke()
        self.assertFalse(self.app.busy)
        self.assertEqual(before, self.app.status.get())

    def test_save_error_keeps_the_inspection_available_for_retry(self):
        self.inspect()
        before = self.app.status.get()
        with patch(
            "tkinter.filedialog.asksaveasfilename", return_value=str(self.folder / "report.json")
        ):
            with patch("zip_preflight.desktop_ui.save_report", side_effect=OSError("write denied")):
                self.app.save_button.invoke()
                self.wait()
        self.assertEqual(before, self.app.status.get())
        self.assertIn("报告未保存", self.app.note.get())
        self.assertFalse(self.app.save_button.instate(["disabled"]))

    def test_invalid_zip_is_explained_and_can_be_exported(self):
        self.path.write_bytes(b"not a ZIP")
        self.inspect()
        self.assertEqual("无法读取 ZIP", self.app.status.get())
        self.assertIn("BadZipFile", self.app.details.get("1.0", "end"))
        self.assertFalse(self.app.save_button.instate(["disabled"]))

    def test_pagination_preserves_every_finding_in_saved_reports(self):
        count = PAGE_SIZE + 1
        self.app.report = Report(
            archive=str(self.path),
            entry_count=count,
            checked_entries=count,
            scan_complete=True,
            findings=[
                Finding("WINDOWS_DEVICE", "error", "message", f"{index}/NUL")
                for index in range(count)
            ],
        )
        self.app._show_report()
        self.assertEqual(PAGE_SIZE, len(self.app.tree.get_children()))
        self.app.next_button.invoke()
        self.assertEqual((str(PAGE_SIZE),), self.app.tree.get_children())
        destination = self.folder / "full.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)):
            self.app.save_button.invoke()
            self.wait()
        self.assertEqual(count, len(json.loads(destination.read_text())["archives"][0]["findings"]))

    def test_save_after_scan_prompts_once_and_saves(self):
        self.app.save_after_scan = True
        destination = self.folder / "automatic.json"
        with patch("tkinter.filedialog.asksaveasfilename", return_value=str(destination)) as dialog:
            self.inspect()
            self.wait()
        self.assertEqual(1, dialog.call_count)
        self.assertTrue(destination.is_file())

    def test_bad_explicit_config_does_not_produce_a_misleading_report(self):
        self.app.config_path = str(self.folder / "missing-config.json")
        self.inspect()
        self.assertIsNone(self.app.report)
        self.assertIn("未完成", self.app.status.get())
        self.assertTrue(self.app.save_button.instate(["disabled"]))


if __name__ == "__main__":
    unittest.main()

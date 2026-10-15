from __future__ import annotations

import io
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import patch

from zip_preflight import Limits, scan_archive


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "fixture.zip"

    def archive(self, names=(), *, compression=zipfile.ZIP_STORED, payload=b"example"):
        with warnings.catch_warnings(), zipfile.ZipFile(self.path, "w", compression) as archive:
            warnings.simplefilter("ignore", UserWarning)
            for name in names:
                info = zipfile.ZipInfo(name)
                # Preserve literal backslashes even on Windows fixture builders.
                info.filename = name
                info.compress_type = compression
                archive.writestr(info, b"" if name.endswith("/") else payload)
        return self.path

    def codes(self, names, **kwargs):
        self.archive(names)
        return {finding.code for finding in scan_archive(self.path, **kwargs).findings}

    def test_clean_archive_and_sizes(self):
        self.archive(["docs/", "docs/readme.txt", "数据.csv"])
        report = scan_archive(self.path)
        self.assertEqual([], report.findings)
        self.assertTrue(report.scan_complete)
        self.assertFalse(report.fails())
        self.assertEqual(3, report.entry_count)
        self.assertEqual(14, report.declared_uncompressed_bytes)

    def test_empty_archive(self):
        self.archive()
        report = scan_archive(self.path)
        self.assertTrue(report.scan_complete)
        self.assertFalse(report.fails())

    def test_parent_traversal_on_both_platforms(self):
        for name in ("../escape", "a/../../escape", "a\\..\\escape"):
            with self.subTest(name=name):
                self.assertIn("PARENT_PATH", self.codes([name]))

    def test_absolute_and_drive_relative_paths(self):
        for name in ("/root/a", "C:/file", "C:file", "\\root\\file", "\\\\server\\share\\a"):
            with self.subTest(name=name):
                self.assertIn("ABSOLUTE_PATH", self.codes([name]))

    def test_parent_like_name_is_not_traversal(self):
        self.assertNotIn("PARENT_PATH", self.codes(["..notes", "a/.../file"]))

    def test_windows_reserved_devices_in_any_component(self):
        for name in ("CON", "nul.txt", "a/AuX.csv", "COM1.bin", "LPT9", "COM¹.txt", "LPT³"):
            with self.subTest(name=name):
                self.assertIn("WINDOWS_DEVICE", self.codes([name]))

    def test_similar_non_device_names(self):
        self.assertNotIn(
            "WINDOWS_DEVICE", self.codes(["CONSOLE", "COM10.txt", "LPT0", "auxiliary"])
        )

    def test_windows_invalid_characters_and_streams(self):
        for char in '<>:"|?*':
            with self.subTest(char=char):
                self.assertIn("WINDOWS_CHARACTER", self.codes([f"a{char}b"]))

    def test_trailing_dots_and_spaces(self):
        for name in ("file.", "dir /file", "file ", "dir./file"):
            with self.subTest(name=name):
                self.assertIn("TRAILING_DOT_SPACE", self.codes([name]))

    def test_case_collision(self):
        self.assertIn("PATH_COLLISION", self.codes(["Readme.md", "README.md"]))

    def test_unicode_normalization_collision(self):
        self.assertIn("PATH_COLLISION", self.codes(["café.txt", "cafe\u0301.txt"]))

    def test_unicode_casefold_is_conservative(self):
        self.assertIn("PATH_COLLISION", self.codes(["straße.txt", "STRASSE.txt"]))

    def test_implicit_directory_case_collision(self):
        self.assertIn("PATH_COLLISION", self.codes(["Docs/a", "docs/b"]))

    def test_implicit_directory_unicode_collision(self):
        self.assertIn("PATH_COLLISION", self.codes(["café/a", "cafe\u0301/b"]))

    def test_trimming_collision(self):
        self.assertIn("PATH_COLLISION", self.codes(["report", "report. "]))

    def test_duplicate_entry_index(self):
        self.archive(["a", "a"])
        finding = next(f for f in scan_archive(self.path).findings if f.code == "DUPLICATE_ENTRY")
        self.assertEqual(1, finding.entry_index)

    def test_file_directory_conflict_both_orders(self):
        for names in (["a", "a/b"], ["a/b", "a"], ["a", "a/"]):
            with self.subTest(names=names):
                self.assertIn("FILE_DIRECTORY_CONFLICT", self.codes(names))

    def test_case_insensitive_file_directory_conflict(self):
        self.assertIn("FILE_DIRECTORY_CONFLICT", self.codes(["A", "a/b"]))

    def test_explicit_directory_after_implicit_is_valid(self):
        self.assertEqual(set(), self.codes(["a/b", "a/"]))

    def test_canonical_alias_targets(self):
        for names in (["a/b", "a//b"], ["a/b", "a/./b"], ["a/b", "a\\b"]):
            with self.subTest(names=names):
                self.assertIn("TARGET_COLLISION", self.codes(names))

    def test_backslash_only_is_warning(self):
        self.archive(["a\\b"])
        report = scan_archive(self.path)
        self.assertTrue(report.fails())
        self.assertFalse(report.fails("error"))

    def test_controls_and_bidi(self):
        self.assertIn("CONTROL_CHARACTER", self.codes(["a\nfile"]))
        self.assertIn("CONTROL_CHARACTER", self.codes(["a\x1b[31m"]))
        self.assertIn("BIDI_CONTROL", self.codes(["photo\u202egpj.exe"]))

    def test_nul_is_not_hidden_by_zipinfo(self):
        self.archive(["beforeXafter"])
        self.path.write_bytes(self.path.read_bytes().replace(b"beforeXafter", b"before\x00after"))
        report = scan_archive(self.path)
        finding = next(f for f in report.findings if f.code == "CONTROL_CHARACTER")
        self.assertEqual("before\x00after", finding.member)

    def test_empty_name_from_metadata(self):
        info = zipfile.ZipInfo("x")
        info.orig_filename = ""
        with patch("zip_preflight.scanner.zipfile.ZipFile") as archive:
            archive.return_value.__enter__.return_value.infolist.return_value = [info]
            self.assertIn("EMPTY_PATH", {f.code for f in scan_archive(self.path).findings})

    def test_long_utf8_component(self):
        self.assertIn("LONG_COMPONENT", self.codes(["中" * 86]))

    def test_long_utf16_path(self):
        self.assertIn("LONG_PATH", self.codes([("a/" * 100) + "😀" * 30]))

    def test_symlink_and_special_files(self):
        for mode, expected in ((stat.S_IFLNK, "SYMLINK"), (stat.S_IFIFO, "SPECIAL_FILE")):
            with self.subTest(mode=mode):
                info = zipfile.ZipInfo("link")
                info.create_system = 3
                info.external_attr = (mode | 0o777) << 16
                with zipfile.ZipFile(self.path, "w") as archive:
                    archive.writestr(info, "../outside")
                self.assertIn(expected, {f.code for f in scan_archive(self.path).findings})

    def test_windows_attributes_not_interpreted_as_unix(self):
        info = zipfile.ZipInfo("regular.txt")
        info.create_system = 0
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        with zipfile.ZipFile(self.path, "w") as archive:
            archive.writestr(info, "data")
        self.assertNotIn("SYMLINK", {f.code for f in scan_archive(self.path).findings})

    def test_encrypted_metadata(self):
        self.archive(["private.txt"])
        data = bytearray(self.path.read_bytes())
        start = data.index(b"PK\x01\x02")
        data[start + 8] |= 1
        self.path.write_bytes(data)
        self.assertIn("ENCRYPTED_MEMBER", {f.code for f in scan_archive(self.path).findings})

    def test_less_portable_compression(self):
        self.archive(["a"], compression=zipfile.ZIP_BZIP2)
        self.assertIn("COMPRESSION_METHOD", {f.code for f in scan_archive(self.path).findings})

    def test_declared_size_limits_and_boundaries(self):
        self.archive(["a", "b"], payload=b"1234")
        clean = scan_archive(self.path, limits=Limits(max_member_size=4, max_total_size=8))
        self.assertEqual([], clean.findings)
        report = scan_archive(self.path, limits=Limits(max_member_size=3, max_total_size=7))
        self.assertIn("MEMBER_SIZE_LIMIT", {f.code for f in report.findings})
        self.assertIn("TOTAL_SIZE_LIMIT", {f.code for f in report.findings})

    def test_entry_limit_marks_incomplete(self):
        self.archive(["a", "b", "../unscanned"])
        report = scan_archive(self.path, limits=Limits(max_entries=2))
        self.assertEqual(3, report.entry_count)
        self.assertEqual(2, report.checked_entries)
        self.assertFalse(report.scan_complete)
        self.assertTrue(report.fails("error"))

    def test_high_compression_ratio(self):
        self.archive(["zeros"], compression=zipfile.ZIP_DEFLATED, payload=b"0" * 10000)
        report = scan_archive(self.path, limits=Limits(max_ratio=2))
        self.assertIn("COMPRESSION_RATIO", {f.code for f in report.findings})

    def test_zero_compressed_size(self):
        info = zipfile.ZipInfo("a")
        info.file_size = 100
        info.compress_size = 0
        with patch("zip_preflight.scanner.zipfile.ZipFile") as archive:
            archive.return_value.__enter__.return_value.infolist.return_value = [info]
            self.assertIn("COMPRESSION_RATIO", {f.code for f in scan_archive(self.path).findings})

    def test_no_payload_read_and_no_archive_mutation(self):
        self.archive(["../escape", "valid.txt"])
        before = self.path.read_bytes()
        with patch.object(zipfile.ZipFile, "open", side_effect=AssertionError("payload accessed")):
            report = scan_archive(self.path)
        self.assertTrue(report.scan_complete)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual(["fixture.zip"], [p.name for p in Path(self.temp.name).iterdir()])

    def test_missing_directory_and_invalid_archive(self):
        for path in (Path(self.temp.name) / "missing.zip", Path(self.temp.name)):
            with self.subTest(path=path):
                self.assertIsNotNone(scan_archive(path).error)
        self.path.write_text("not a zip", encoding="utf-8")
        self.assertIn("BadZipFile", scan_archive(self.path).error)

    def test_truncated_archive(self):
        self.archive(["a"])
        self.path.write_bytes(self.path.read_bytes()[:-15])
        self.assertIsNotNone(scan_archive(self.path).error)

    def test_deep_paths_do_not_recurse(self):
        self.archive(["a/" * 2000 + "file"])
        self.assertTrue(scan_archive(self.path).scan_complete)

    def test_stable_report(self):
        self.archive(["NUL.txt", "docs/a", "Docs/b"])
        self.assertEqual(scan_archive(self.path).to_dict(), scan_archive(self.path).to_dict())

    def test_limits_reject_invalid_values(self):
        for name in ("max_entries", "max_total_size", "max_member_size"):
            for value in (0, -1, True, 1.5):
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    Limits(**{name: value})
        for value in (0, -1, float("nan"), float("inf"), True, "2"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Limits(max_ratio=value)

    def test_fail_on_rejects_invalid_policy(self):
        self.archive()
        with self.assertRaises(ValueError):
            scan_archive(self.path).fails("never")

    def test_file_like_zip_parser_control(self):
        # Verify the fixture builder itself produces ordinary interoperable ZIP data.
        self.archive(["hello.txt"])
        with zipfile.ZipFile(io.BytesIO(self.path.read_bytes())) as archive:
            self.assertEqual(b"example", archive.read("hello.txt"))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from zip_preflight.config import Settings, load_settings


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        previous_directory = Path.cwd()
        self.addCleanup(os.chdir, previous_directory)
        os.chdir(self.root)
        self.path = self.root / ".zip-preflight.json"

    def test_defaults_match_existing_policy(self):
        settings = load_settings({})
        self.assertEqual(Settings(), settings)
        self.assertFalse(settings.summary)
        self.assertEqual(100_000, settings.limits.max_entries)

    def test_all_settings_and_overrides(self):
        self.path.write_text(
            json.dumps(
                {
                    "format": "json",
                    "fail_on": "error",
                    "max_entries": 2,
                    "max_total_size": 30,
                    "max_member_size": 20,
                    "max_ratio": 1.5,
                    "summary": True,
                    "max_findings": 0,
                    "ignore_rules": ["LONG_PATH", "LONG_PATH"],
                }
            ),
            encoding="utf-8",
        )
        settings = load_settings({"max_entries": 4, "summary": False})
        self.assertEqual(4, settings.limits.max_entries)
        self.assertEqual(30, settings.limits.max_total_size)
        self.assertEqual(20, settings.limits.max_member_size)
        self.assertEqual(1.5, settings.limits.max_ratio)
        self.assertEqual("json", settings.format)
        self.assertEqual("error", settings.fail_on)
        self.assertEqual(("LONG_PATH",), settings.ignore_rules)
        self.assertFalse(settings.summary)

    def test_utf8_bom_is_accepted(self):
        self.path.write_text('{"summary": true}', encoding="utf-8-sig")
        self.assertTrue(load_settings({}).summary)

    def test_shipped_example_is_valid(self):
        example = Path(__file__).resolve().parents[1] / "examples" / "zip-preflight.json"
        settings = load_settings({}, config_path=str(example))
        self.assertTrue(settings.summary)
        self.assertEqual(5, settings.max_findings)
        self.assertEqual((), settings.ignore_rules)

    def test_max_findings_implies_summary_unless_explicitly_disabled(self):
        self.path.write_text('{"max_findings": 0}', encoding="utf-8")
        self.assertTrue(load_settings({}).summary)
        self.assertFalse(load_settings({"summary": False}).summary)
        self.assertTrue(load_settings({"max_findings": 3}).summary)

    def test_unknown_keys_invalid_types_and_values_are_errors(self):
        cases = (
            [],
            None,
            {"max_entry": 1},
            {"format": "yaml"},
            {"format": False},
            {"fail_on": "never"},
            {"max_entries": 0},
            {"max_total_size": True},
            {"max_member_size": "5"},
            {"max_ratio": -1},
            {"max_ratio": 10**400},
            {"summary": "true"},
            {"summary": 1},
            {"max_findings": -1},
            {"max_findings": 1.5},
            {"max_findings": True},
            {"ignore_rules": "LONG_PATH"},
            {"ignore_rules": [1]},
            {"ignore_rules": ["long_path"]},
            {"ignore_rules": ["TYPO"]},
        )
        for value in cases:
            with self.subTest(value=value):
                self.path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "Invalid config"):
                    load_settings({})

    def test_invalid_json_duplicate_keys_and_nonfinite_numbers_are_errors(self):
        for text in (
            "{",
            '{"summary": true, "summary": false}',
            '{"max_ratio": NaN}',
            '{"max_ratio": Infinity}',
            '{"max_ratio": 1e999}',
        ):
            with self.subTest(text=text):
                self.path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_settings({})
        self.path.write_bytes(b"\xff\xfe")
        with self.assertRaises(ValueError):
            load_settings({})

    def test_bad_config_is_validated_before_overrides(self):
        self.path.write_text('{"max_entries": 0}', encoding="utf-8")
        with self.assertRaises(ValueError):
            load_settings({"max_entries": 10})

    def test_parent_config_is_not_discovered(self):
        self.path.write_text('{"max_entries": 1}', encoding="utf-8")
        child = self.root / "child"
        child.mkdir()
        os.chdir(child)
        self.assertEqual(Settings(), load_settings({}))


if __name__ == "__main__":
    unittest.main()

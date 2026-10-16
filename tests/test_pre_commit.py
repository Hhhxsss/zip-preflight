from __future__ import annotations

import re
import unittest
from pathlib import Path


class PreCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest = Path(__file__).resolve().parents[1] / ".pre-commit-hooks.yaml"
        # Read the actual hook filter without adding a YAML test dependency.
        pattern = next(
            line.split(":", 1)[1].strip().strip("'\"")
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("files:")
        )
        cls.file_filter = re.compile(pattern)

    def test_zip_extensions_are_selected(self):
        for name in ("release.zip", "release.ZIP", "release.Zip", "nested/archive.zIp"):
            with self.subTest(name=name):
                self.assertIsNotNone(self.file_filter.search(name))

    def test_other_extensions_are_not_selected(self):
        for name in ("release.zip.txt", "release.ZIP.md", "archive.tgz", "releasezip"):
            with self.subTest(name=name):
                self.assertIsNone(self.file_filter.search(name))


if __name__ == "__main__":
    unittest.main()

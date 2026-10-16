"""Verify an installed distribution without relying on the source-tree import path."""

from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from zip_preflight import __version__, scan_archive


def main() -> None:
    distribution = importlib.metadata.distribution("zip-preflight")
    assert distribution.version == __version__
    assert not distribution.requires, "Unexpected runtime dependency"
    assert any(str(item).endswith("py.typed") for item in distribution.files or [])
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "bundle.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("hello.txt", "hello")
        assert not scan_archive(path).fails()
        clean = subprocess.run(
            [sys.executable, "-I", "-m", "zip_preflight", "--format", "json", str(path)],
            cwd=folder,
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(clean.stdout)["exit_code"] == 0
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("../zip-preflight-outside.txt", "hello")
        unsafe = subprocess.run(
            [sys.executable, "-I", "-m", "zip_preflight", str(path)],
            cwd=folder,
            capture_output=True,
            text=True,
            check=False,
        )
        assert unsafe.returncode == 1 and "PARENT_PATH" in unsafe.stdout
        assert sorted(item.name for item in Path(folder).iterdir()) == ["bundle.zip"]
        config = Path(folder) / ".zip-preflight.json"
        config.write_text(
            json.dumps({"format": "json", "summary": True, "max_findings": 0}),
            encoding="utf-8",
        )
        configured = subprocess.run(
            [sys.executable, "-I", "-m", "zip_preflight", str(path)],
            cwd=folder,
            capture_output=True,
            text=True,
            check=False,
        )
        data = json.loads(configured.stdout)
        assert configured.returncode == 1
        assert data["summary"]["total_findings"] == 1
        assert data["summary"]["failed_archives"] == 1
        assert data["summary"]["checked_entries"] == 1
        assert len(data["archives"][0]["findings"]) == 1
        assert sorted(item.name for item in Path(folder).iterdir()) == [
            ".zip-preflight.json",
            "bundle.zip",
        ]
    print(
        f"Installed zip-preflight {__version__}: API, CLI, JSON, configuration, "
        "summaries, and metadata verified."
    )


if __name__ == "__main__":
    main()

"""Build a standalone, windowed Windows executable using a development-only tool."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if sys.platform != "win32":
        raise SystemExit("Build the Windows executable on Windows.")
    root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment["PYINSTALLER_CONFIG_DIR"] = str(root / ".local" / "windows-build" / "cache")
    environment["PYTHONUSERBASE"] = str(root / ".local" / "windows-build" / "userbase")
    environment["PYTHONNOUSERSITE"] = "1"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--windowed",
            "--name",
            "zip-preflight",
            "--paths",
            str(root / "src"),
            "--distpath",
            str(root / "dist" / "windows"),
            "--workpath",
            str(root / ".local" / "windows-build" / "work"),
            "--specpath",
            str(root / ".local" / "windows-build"),
            str(root / "tools" / "desktop_entry.py"),
        ],
        cwd=root,
        env=environment,
        check=True,
    )
    print(f"Desktop executable: {root / 'dist' / 'windows' / 'zip-preflight.exe'}")


if __name__ == "__main__":
    main()

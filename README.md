# zip-preflight

[![CI](https://github.com/Hhhxsss/zip-preflight/actions/workflows/ci.yml/badge.svg)](https://github.com/Hhhxsss/zip-preflight/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Catch ZIP filename problems before your users do.**

Check release bundles, exported datasets, and upload archives for names that fail on
Windows, overwrite each other on case-insensitive filesystems, or contain obvious
extraction hazards. Reads ZIP metadata only. Never extracts, rewrites, or uploads files.

The optional [Windows desktop app](docs/windows-desktop.md) adds a single-ZIP
right-click menu, a native result window, and complete JSON/text report exports.
Its standalone Windows build includes Python and Tk.
The v0.1.0 release predates the desktop app and does not include an EXE. To use
this feature now, install the current `main` branch for the Python GUI or build
the EXE from source; see the [desktop guide](docs/windows-desktop.md#start-the-app).
To uninstall the portable app, remove its menu through **右键菜单…** or
`zip-preflight.exe --uninstall-context-menu`, then close the app and delete the EXE.
See [menu removal and uninstall steps](docs/windows-desktop.md#remove-the-menu-and-uninstall).

[中文文档](README.zh-CN.md) · [Rule reference](docs/rules.md) · [Usage and CI](docs/usage.md) · [Research and scope](docs/research.md)

```text
$ zip-preflight release.zip
FAIL "release.zip"
  3/3 entries checked; 15 declared uncompressed bytes
  ERROR WINDOWS_DEVICE "data/CON.csv": Component uses a Windows device name, even with an extension.
  ERROR PATH_COLLISION "docs/b.txt" (related: "Docs/a.txt"): Paths alias after NFC normalization, case folding, or trailing-dot/space trimming.
```

## Install

Python **3.10+**, with **no runtime dependencies**. Works on Windows, macOS, and Linux.
Install the tagged release from GitHub (Git is required):

```console
python -m pip install "git+https://github.com/Hhhxsss/zip-preflight.git@v0.1.0"
```

Or clone and install locally:

```console
git clone https://github.com/Hhhxsss/zip-preflight.git
cd zip-preflight
python -m pip install .
```

The package is not published on PyPI. If the command is not on your `PATH`, use
`python -m zip_preflight` with the same options.

## Use

```console
zip-preflight release.zip
zip-preflight "dist/*.zip" --format json
zip-preflight dataset.zip --fail-on error
zip-preflight dataset.zip --max-total-size 21474836480 --max-ratio 2000
zip-preflight "dist/*.zip" --summary --max-findings 5
zip-preflight release.zip --config examples/zip-preflight.json
```

Quoted globs are expanded by the tool on every OS. Unmatched patterns are errors.
Warnings fail the check by default; `--fail-on error` keeps warnings visible without
failing on them. Size options use integer **bytes**; thresholds are configurable.

Save repeated options in a `.zip-preflight.json` file in the working directory;
explicit command-line options override it. Use `--no-config` to skip that file.
The [example configuration](examples/zip-preflight.json) lists supported settings.
`--summary` groups findings by rule and shows up to five examples per archive;
`--max-findings 0` shows counts only. JSON reports always retain all findings.
See [configuration and summaries](docs/usage.md#configuration-files) for details.

| Exit | Meaning |
| --- | --- |
| `0` | No findings at or above the selected threshold |
| `1` | At least one finding meets that threshold |
| `2` | Invalid CLI arguments, unreadable input, or invalid ZIP metadata |

Input errors take precedence when checking several archives. Exit `0` is a policy
result, **not a guarantee that extraction is safe**.

## What it catches

- Parent traversal, rooted/UNC paths, drive-qualified paths, controls, symlinks, and special files.
- Windows device names (`NUL.txt`, `COM¹`), invalid characters, and trailing dots/spaces.
- Exact duplicate entries, file/directory conflicts, and normalized target collisions.
- Case and Unicode collisions in both filenames and **implicit directory names**.
- Backslash paths, bidirectional controls, long names, encrypted members, and uncommon compression.
- Declared size, entry-count, and compression-ratio policy violations.

The [rule reference](docs/rules.md) lists every code, severity, default limit, and caveat.

## CI in your project

After your build has created ZIP artifacts, add:

```yaml
- name: Install zip-preflight
  run: python -m pip install "git+https://github.com/Hhhxsss/zip-preflight.git@v0.1.0"
- name: Check release archives
  run: python -m zip_preflight "dist/*.zip"
```

For a JSON report, Python API, pre-commit configuration, and platform-specific notes,
see [the usage guide](docs/usage.md).

## Scope and limits

This is a **metadata linter**, not an antivirus or a secure extractor. It does not
decompress payloads, verify CRCs, compare local headers, inspect nested archives,
or validate link targets. Declared sizes can be dishonest. Python's `zipfile`
loads the central directory into memory before entry limits can be applied; isolate
the process and impose OS-level memory/time limits when inspecting untrusted input.

NFC plus Unicode case folding and trailing-dot/space trimming is a conservative
portability model, not an exact emulator of NTFS, APFS, or any particular extractor.
Reports contain archive paths and member names; review them before sharing.

## Contribute

```console
python -m pip install -e .
python -m unittest discover -s tests -v
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for development checks and fixture guidance.
Small reproductions of real cross-platform ZIP problems are especially welcome.

## License

[MIT](LICENSE). Related projects and the primary sources behind the checks are
credited in [Research and scope](docs/research.md).

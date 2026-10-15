# Usage guide

## Install and try the examples

```console
git clone https://github.com/Hhhxsss/zip-preflight.git
cd zip-preflight
python -m pip install .
python examples/create_demo.py
python -m zip_preflight .local/demo/clean.zip
python -m zip_preflight .local/demo/problematic.zip
```

The example generator creates two small ZIP files in `.local/demo/` and does not
extract them. The clean archive exits `0`; the problematic one exits `1`.

Virtual environments are recommended. On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install .
.venv\Scripts\python -m zip_preflight .local/demo/clean.zip
$LASTEXITCODE
```

On macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python -m zip_preflight .local/demo/clean.zip
echo $?
```

Use the interpreter that installed the package. No network access is needed for
scanning after installation.

## Options

```console
zip-preflight --help
zip-preflight one.zip two.zip
zip-preflight "artifacts/**/*.zip" --format json
zip-preflight dataset.zip --fail-on error --max-total-size 21474836480
```

Literal existing filenames are used directly, even if they contain glob characters
such as brackets. Otherwise Python glob patterns are expanded in sorted order,
including `**` for recursion. Exact repeated input strings are deduplicated;
different spellings of the same physical path are not resolved. Directories are
not searched automatically. An unmatched pattern produces an input error.

The default policy fails on warnings and errors. `--fail-on error` allows warnings
but does not hide them. All limits remain active; there is no implicit per-OS mode.
Paths beginning with `-` can follow the `--` argument separator.

## JSON reports

```console
zip-preflight release.zip --format json > report.json
```

PowerShell 5 users who need UTF-8 files should use
`zip-preflight release.zip --format json | Out-File -Encoding utf8 report.json`;
the JSON content itself uses ASCII escapes for portability.

The root object contains `schema_version`, `tool`, `version`, `fail_on`, `limits`,
`exit_code`, and `archives`. Each archive contains:

```json
{
  "archive": "release.zip",
  "entry_count": 1,
  "checked_entries": 1,
  "declared_uncompressed_bytes": 5,
  "declared_compressed_bytes": 5,
  "scan_complete": true,
  "findings": [],
  "error": null
}
```

Each finding has `code`, `severity`, `message`, `member`, `related_member`, and
`entry_index`. Fields without a relevant value are `null`. Array order is stable for
the same archive and tool version. Consumers should use codes, not message text.
Filenames are JSON-escaped without losing their decoded Unicode values.

Unreadable/invalid archives are represented by `error` and cause exit `2`; other
inputs are still processed. Syntax/option errors use argparse's normal stderr
output and exit `2`, even with `--format json`. `scan_complete: true` means every
central-directory entry received these checks, not that payloads were verified.

## Python API

```python
from zip_preflight import Limits, scan_archive

report = scan_archive(
    "dataset.zip",
    limits=Limits(max_entries=50_000, max_total_size=20 * 1024**3),
)
if report.error:
    raise RuntimeError(report.error)
for finding in report.findings:
    print(finding.code, repr(finding.member), finding.message)
if report.fails("error"):
    raise SystemExit(1)
```

`scan_archive` accepts a string or `os.PathLike[str]`. Expected file/ZIP parsing
errors are returned on the report; invalid `Limits` raise `ValueError`. Use `repr`
or JSON when displaying names yourself: member names are untrusted text.

## GitHub Actions

Place the installation and check after your own build step. A minimal example for
a repository that already stores ZIP artifacts under `bundles/`:

```yaml
name: Archive portability
on: [push, pull_request]
permissions:
  contents: read
jobs:
  lint-archives:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: '3.12'
      - run: python -m pip install "git+https://github.com/Hhhxsss/zip-preflight.git@v0.1.0"
      - run: python -m zip_preflight "bundles/*.zip"
```

For stricter supply-chain control, pin third-party actions and the install URL to
reviewed commit SHAs. The project's own CI pins actions to immutable commits.

## pre-commit

```yaml
repos:
  - repo: https://github.com/Hhhxsss/zip-preflight
    rev: v0.1.0
    hooks:
      - id: zip-preflight
```

This checks staged `.zip` files only. Generated archives excluded from Git should
be checked after the build in CI instead. Optional `args: [--fail-on, error]` changes
the warning policy.

## Troubleshooting

- **Command not found:** use `python -m zip_preflight` with the interpreter used to install.
- **Unexpected Windows name failure:** reserved names apply to every path component, even with extensions.
- **A legitimate dataset triggers a size/ratio rule:** inspect it, then increase the relevant explicit limit.
- **A ZIP passes but extraction fails:** payloads, local headers, encoding extensions, and destination conditions are outside scope.
- **Very large/untrusted archive:** run in a resource-limited process; `--max-entries` cannot prevent central-directory memory allocation.

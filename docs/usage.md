# Usage guide

For Windows right-click checks and the result window, see the
[desktop guide](windows-desktop.md). The command-line interface below remains
available for batch processing and CI.

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

## Configuration files

The CLI automatically reads `.zip-preflight.json` from its **current working
directory**. It does not search parent directories or the archive's directory.
Use `--config PATH` to select a different file, or `--no-config` to disable automatic
loading. An explicit file replaces the automatic file; the files are not merged.

```json
{
  "fail_on": "error",
  "max_total_size": 21474836480,
  "ignore_rules": ["LONG_PATH"],
  "summary": true,
  "max_findings": 5
}
```

Precedence is **explicit CLI options > configuration file > built-in defaults**.
For example, `zip-preflight release.zip --fail-on warning` overrides the file's
`fail_on` while retaining its other options. Archive arguments and glob patterns
remain command-line inputs, resolved from the working directory.

| JSON key | Values / default |
| --- | --- |
| `format` | `"text"` (default) or `"json"` |
| `fail_on` | `"warning"` (default) or `"error"` |
| `max_entries` | Positive integer; default 100,000 |
| `max_total_size` | Positive integer bytes; default 10,737,418,240 |
| `max_member_size` | Positive integer bytes; default 2,147,483,648 |
| `max_ratio` | Finite positive number; default 1000 |
| `ignore_rules` | Array of exact, uppercase rule codes; default `[]` |
| `summary` | Boolean; default `false` |
| `max_findings` | Nonnegative integer; default 5 examples per archive in summary mode |

Setting `max_findings` also enables summary mode unless `summary` is explicitly
set to `false` at the same precedence level. `--no-summary` restores full text
details even when a config file enables summaries or limits examples.

Rule exceptions affect pass/fail policy only: ignored findings remain in the
report and are marked `IGNORED` in text output. Repeated `--ignore-rule CODE` options
replace the configured list; `--no-ignore-rules` clears it. Exceptions do not
disable checks or change scan limits, and unreadable inputs still exit `2`.

Files must contain a UTF-8 JSON object (a UTF-8 BOM is accepted). Unknown keys,
unknown rule codes, duplicate keys, non-finite numbers, and invalid values are
configuration errors: stderr explains the error and the command exits `2` before
scanning. An invalid file is rejected even if a CLI option would override its bad
value. JSON comments and trailing commas are not supported.

The [full example](../examples/zip-preflight.json) keeps the built-in scan limits
and enables summaries. Copy it to `.zip-preflight.json` or try it explicitly:

```console
zip-preflight release.zip --config examples/zip-preflight.json
zip-preflight release.zip --no-config
zip-preflight release.zip --ignore-rule LONG_PATH --ignore-rule LONG_COMPONENT
```

## Report summaries

```console
zip-preflight "dist/*.zip" --summary
zip-preflight release.zip --summary --max-findings 3
zip-preflight release.zip --max-findings 0
zip-preflight "dist/*.zip" --summary --format json
```

Text summaries show error/warning/ignored totals and counts grouped by rule, then
the first five findings per archive by default. `--max-findings N` changes that
example limit and implies `--summary`; zero shows only counts. The report states
how many findings were omitted. Multiple inputs also receive a combined summary,
separating archives that passed, failed policy, or could not be read.

All normal checks still run up to `max_entries`. Example limits affect only text
display: exit codes, totals, and the complete JSON `findings` arrays use all
findings produced by the scan. An incomplete scan retains `scan_complete: false`.
The example limit does not bound scanning memory or JSON report size.

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

With summary mode enabled, the root object and each archive additionally contain
`summary`. Its fields are:

| Field | Meaning |
| --- | --- |
| `archive_count` | Number of input archives represented |
| `passed_archives` | Archives passing the selected policy |
| `failed_archives` | Readable archives failing the selected policy |
| `unreadable_archives` | Inputs with an `error` |
| `incomplete_archives` | Inputs whose `scan_complete` is false, including unreadable inputs |
| `entry_count`, `checked_entries` | Total declared and checked entry counts |
| `total_findings` | All findings, including ignored ones |
| `errors`, `warnings` | Finding counts excluding configured rule exceptions |
| `ignored_findings` | Findings excluded from pass/fail policy |
| `by_rule` | Array of `{code, severity, count, ignored}`, sorted by code and severity |

When rule exceptions are active, the root also includes `ignore_rules`, listing
the effective policy exceptions. Original finding severities remain intact.
These fields are opt-in additions to schema version `1`; default JSON reports
retain their existing shape.

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

Configuration files are a CLI feature; `scan_archive` continues to use its explicit
`limits` argument. Python callers can apply rule exceptions with
`report.fails("error", ignore_rules=["LONG_PATH"])` without removing findings.

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

This checks staged ZIP files with any capitalization of the `.zip` extension,
including `.ZIP` and `.Zip`. Generated archives excluded from Git should be checked
after the build in CI instead. Optional `args: [--fail-on, error]` changes the warning
policy.

## Troubleshooting

- **Command not found:** use `python -m zip_preflight` with the interpreter used to install.
- **Unexpected Windows name failure:** reserved names apply to every path component, even with extensions.
- **A legitimate dataset triggers a size/ratio rule:** inspect it, then increase the relevant explicit limit.
- **A ZIP passes but extraction fails:** payloads, local headers, encoding extensions, and destination conditions are outside scope.
- **Very large/untrusted archive:** run in a resource-limited process; `--max-entries` cannot prevent central-directory memory allocation.

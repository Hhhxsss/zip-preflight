"""Console interface with stable JSON and exit codes for CI."""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections.abc import Sequence

from . import __version__
from .models import Limits, Report, Severity
from .scanner import scan_archive


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a positive integer") from error
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _positive_float(value: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a finite positive number") from error
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be a finite positive number")
    return number


def _parser() -> argparse.ArgumentParser:
    defaults = Limits()
    parser = argparse.ArgumentParser(
        prog="zip-preflight",
        description=(
            "Check ZIP metadata for portability and extraction hazards; never extract files."
        ),
    )
    parser.add_argument("archives", nargs="+", help="ZIP paths or quoted glob patterns")
    parser.add_argument("--version", action="version", version=f"zip-preflight {__version__}")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--fail-on", choices=("warning", "error"), default="warning")
    parser.add_argument("--max-entries", type=_positive_int, default=defaults.max_entries)
    parser.add_argument(
        "--max-total-size", type=_positive_int, default=defaults.max_total_size, metavar="BYTES"
    )
    parser.add_argument(
        "--max-member-size", type=_positive_int, default=defaults.max_member_size, metavar="BYTES"
    )
    parser.add_argument("--max-ratio", type=_positive_float, default=defaults.max_ratio)
    return parser


def _quote(value: str) -> str:
    # Escape terminal controls and non-ASCII characters in untrusted filenames.
    return json.dumps(value, ensure_ascii=True)


def _text_report(report: Report, fail_on: Severity) -> str:
    status = "ERROR" if report.error else "FAIL" if report.fails(fail_on) else "PASS"
    lines = [f"{status} {_quote(report.archive)}"]
    if report.error:
        lines.append(f"  Unable to scan: {_quote(report.error)}")
    else:
        lines.append(
            f"  {report.checked_entries}/{report.entry_count} entries checked; "
            f"{report.declared_uncompressed_bytes} declared uncompressed bytes"
        )
        for finding in report.findings:
            location = "" if finding.member is None else f" {_quote(finding.member)}"
            related = (
                ""
                if finding.related_member is None
                else f" (related: {_quote(finding.related_member)})"
            )
            lines.append(
                f"  {finding.severity.upper()} {finding.code}{location}{related}: {finding.message}"
            )
        if not report.findings:
            lines.append("  No metadata findings. Payloads were not inspected.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    limits = Limits(args.max_entries, args.max_total_size, args.max_member_size, args.max_ratio)
    paths: list[str] = []
    for pattern in args.archives:
        # Literal filenames win over glob metacharacters (e.g. dataset[1].zip).
        matches = (
            [pattern] if os.path.exists(pattern) else sorted(glob.glob(pattern, recursive=True))
        )
        paths.extend(matches or [pattern])
    paths = list(dict.fromkeys(paths))
    reports = [scan_archive(path, limits=limits) for path in paths]
    if any(report.error for report in reports):
        exit_code = 2
    elif any(report.fails(args.fail_on) for report in reports):
        exit_code = 1
    else:
        exit_code = 0
    if args.format == "json":
        print(
            json.dumps(
                {
                    "schema_version": 1,
                    "tool": "zip-preflight",
                    "version": __version__,
                    "fail_on": args.fail_on,
                    "limits": {
                        "max_entries": limits.max_entries,
                        "max_total_size": limits.max_total_size,
                        "max_member_size": limits.max_member_size,
                        "max_ratio": limits.max_ratio,
                    },
                    "exit_code": exit_code,
                    "archives": [report.to_dict() for report in reports],
                },
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
        )
    else:
        print("\n\n".join(_text_report(report, args.fail_on) for report in reports))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

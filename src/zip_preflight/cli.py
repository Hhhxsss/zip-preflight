"""Console interface with stable JSON and exit codes for CI."""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys
from collections.abc import Collection, Sequence
from dataclasses import fields

from . import __version__
from .config import Settings, load_settings
from .models import Report, Severity
from .reporting import build_json_report, report_exit_code, summarize
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


def _nonnegative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a nonnegative integer") from error
    if number < 0:
        raise argparse.ArgumentTypeError("must be a nonnegative integer")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zip-preflight",
        description=(
            "Check ZIP metadata for portability and extraction hazards; never extract files."
        ),
    )
    parser.add_argument("archives", nargs="+", help="ZIP paths or quoted glob patterns")
    parser.add_argument("--version", action="version", version=f"zip-preflight {__version__}")
    config = parser.add_mutually_exclusive_group()
    config.add_argument("--config", metavar="PATH", help="Read a JSON configuration file")
    config.add_argument(
        "--no-config", action="store_true", help="Skip the current directory's .zip-preflight.json"
    )
    parser.add_argument("--format", choices=("text", "json"), default=argparse.SUPPRESS)
    parser.add_argument("--fail-on", choices=("warning", "error"), default=argparse.SUPPRESS)
    parser.add_argument("--max-entries", type=_positive_int, default=argparse.SUPPRESS)
    parser.add_argument(
        "--max-total-size", type=_positive_int, default=argparse.SUPPRESS, metavar="BYTES"
    )
    parser.add_argument(
        "--max-member-size", type=_positive_int, default=argparse.SUPPRESS, metavar="BYTES"
    )
    parser.add_argument("--max-ratio", type=_positive_float, default=argparse.SUPPRESS)
    ignore = parser.add_mutually_exclusive_group()
    ignore.add_argument(
        "--ignore-rule",
        dest="ignore_rules",
        action="append",
        default=argparse.SUPPRESS,
        metavar="CODE",
        help="Ignore a rule for pass/fail; repeat to replace the config's list",
    )
    ignore.add_argument(
        "--no-ignore-rules",
        dest="ignore_rules",
        action="store_const",
        const=(),
        default=argparse.SUPPRESS,
        help="Clear configured rule exceptions",
    )
    parser.add_argument(
        "--summary",
        action=argparse.BooleanOptionalAction,
        default=argparse.SUPPRESS,
        help="Group findings by rule and show a few examples per archive",
    )
    parser.add_argument(
        "--max-findings",
        type=_nonnegative_int,
        default=argparse.SUPPRESS,
        metavar="N",
        help="Show at most N examples per archive (default: 5); implies --summary",
    )
    return parser


def _quote(value: str) -> str:
    # Escape terminal controls and non-ASCII characters in untrusted filenames.
    return json.dumps(value, ensure_ascii=True)


def _summary_lines(summary: dict) -> list[str]:
    lines = [
        f"  Findings: {summary['errors']} errors, {summary['warnings']} warnings, "
        f"{summary['ignored_findings']} ignored"
    ]
    for rule in summary["by_rule"]:
        ignored = " (ignored)" if rule["ignored"] else ""
        lines.append(f"    {rule['code']} [{rule['severity']}]: {rule['count']}{ignored}")
    return lines


def _text_report(
    report: Report,
    fail_on: Severity,
    *,
    ignore_rules: Collection[str] = (),
    summary: bool = False,
    max_findings: int = 5,
) -> str:
    status = (
        "ERROR"
        if report.error
        else "FAIL"
        if report.fails(fail_on, ignore_rules=ignore_rules)
        else "PASS"
    )
    lines = [f"{status} {_quote(report.archive)}"]
    if report.error:
        lines.append(f"  Unable to scan: {_quote(report.error)}")
    else:
        lines.append(
            f"  {report.checked_entries}/{report.entry_count} entries checked; "
            f"{report.declared_uncompressed_bytes} declared uncompressed bytes"
        )
        if summary:
            lines.extend(_summary_lines(summarize([report], fail_on, ignore_rules=ignore_rules)))
        visible = report.findings[:max_findings] if summary else report.findings
        for finding in visible:
            location = "" if finding.member is None else f" {_quote(finding.member)}"
            related = (
                ""
                if finding.related_member is None
                else f" (related: {_quote(finding.related_member)})"
            )
            ignored = "IGNORED " if finding.code in ignore_rules else ""
            lines.append(
                f"  {ignored}{finding.severity.upper()} {finding.code}{location}{related}: "
                f"{finding.message}"
            )
        omitted = len(report.findings) - len(visible)
        if omitted:
            lines.append(f"  {omitted} findings omitted; use --format json for all findings.")
        if not report.findings:
            lines.append("  No metadata findings. Payloads were not inspected.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    setting_names = {item.name for item in fields(Settings)}
    try:
        settings = load_settings(
            {key: value for key, value in vars(args).items() if key in setting_names},
            config_path=args.config,
            no_config=args.no_config,
        )
    except ValueError as error:
        parser.error(str(error))
    limits = settings.limits
    paths: list[str] = []
    for pattern in args.archives:
        # Literal filenames win over glob metacharacters (e.g. dataset[1].zip).
        matches = (
            [pattern] if os.path.exists(pattern) else sorted(glob.glob(pattern, recursive=True))
        )
        paths.extend(matches or [pattern])
    paths = list(dict.fromkeys(paths))
    reports = [scan_archive(path, limits=limits) for path in paths]
    exit_code = report_exit_code(reports, settings.fail_on, ignore_rules=settings.ignore_rules)
    if settings.format == "json":
        data = build_json_report(
            reports,
            limits=limits,
            fail_on=settings.fail_on,
            ignore_rules=settings.ignore_rules,
            summary=settings.summary,
        )
        print(
            json.dumps(
                data,
                indent=2,
                ensure_ascii=True,
                allow_nan=False,
            )
        )
    else:
        sections = [
            _text_report(
                report,
                settings.fail_on,
                ignore_rules=settings.ignore_rules,
                summary=settings.summary,
                max_findings=settings.max_findings,
            )
            for report in reports
        ]
        if settings.summary and len(reports) > 1:
            total = summarize(reports, settings.fail_on, ignore_rules=settings.ignore_rules)
            sections.append(
                "\n".join(
                    [
                        f"Summary: {total['archive_count']} archives; "
                        f"{total['passed_archives']} passed, {total['failed_archives']} failed, "
                        f"{total['unreadable_archives']} unreadable; "
                        f"{total['checked_entries']}/{total['entry_count']} entries checked",
                        *_summary_lines(total),
                    ]
                )
            )
        print("\n\n".join(sections))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

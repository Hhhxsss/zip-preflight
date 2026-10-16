"""Aggregate complete findings without truncating scans or JSON details."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence

from . import __version__
from .models import Limits, Report, Severity


def report_exit_code(
    reports: Sequence[Report], fail_on: Severity = "warning", *, ignore_rules: Collection[str] = ()
) -> int:
    if any(report.error for report in reports):
        return 2
    return int(any(report.fails(fail_on, ignore_rules=ignore_rules) for report in reports))


def build_json_report(
    reports: Sequence[Report],
    *,
    limits: Limits,
    fail_on: Severity = "warning",
    ignore_rules: Collection[str] = (),
    summary: bool = False,
) -> dict:
    """Use the same complete, versioned JSON envelope in the CLI and desktop app."""
    data = {
        "schema_version": 1,
        "tool": "zip-preflight",
        "version": __version__,
        "fail_on": fail_on,
        "limits": {
            "max_entries": limits.max_entries,
            "max_total_size": limits.max_total_size,
            "max_member_size": limits.max_member_size,
            "max_ratio": limits.max_ratio,
        },
        "exit_code": report_exit_code(reports, fail_on, ignore_rules=ignore_rules),
        "archives": [report.to_dict() for report in reports],
    }
    if ignore_rules:
        data["ignore_rules"] = list(ignore_rules)
    if summary:
        data["summary"] = summarize(reports, fail_on, ignore_rules=ignore_rules)
        for item, report in zip(data["archives"], reports, strict=True):
            item["summary"] = summarize([report], fail_on, ignore_rules=ignore_rules)
    return data


def summarize(
    reports: Sequence[Report], fail_on: Severity = "warning", *, ignore_rules: Collection[str] = ()
) -> dict:
    ignored = frozenset(ignore_rules)
    counts = Counter((f.code, f.severity) for report in reports for f in report.findings)
    errors = sum(
        count
        for (code, severity), count in counts.items()
        if severity == "error" and code not in ignored
    )
    warnings = sum(
        count
        for (code, severity), count in counts.items()
        if severity == "warning" and code not in ignored
    )
    return {
        "archive_count": len(reports),
        "passed_archives": sum(
            not report.fails(fail_on, ignore_rules=ignored) for report in reports
        ),
        "failed_archives": sum(
            report.error is None and report.fails(fail_on, ignore_rules=ignored)
            for report in reports
        ),
        "unreadable_archives": sum(report.error is not None for report in reports),
        "incomplete_archives": sum(not report.scan_complete for report in reports),
        "entry_count": sum(report.entry_count for report in reports),
        "checked_entries": sum(report.checked_entries for report in reports),
        "total_findings": sum(counts.values()),
        "errors": errors,
        "warnings": warnings,
        "ignored_findings": sum(count for (code, _), count in counts.items() if code in ignored),
        "by_rule": [
            {"code": code, "severity": severity, "count": count, "ignored": code in ignored}
            for (code, severity), count in sorted(counts.items())
        ],
    }

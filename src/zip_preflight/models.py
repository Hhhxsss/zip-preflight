"""Public report types; sizes are declared sizes, never decompressed measurements."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Literal

Severity = Literal["warning", "error"]


@dataclass(frozen=True)
class Limits:
    """Positive policy limits. These do not bound zipfile's metadata allocation."""

    max_entries: int = 100_000
    max_total_size: int = 10 * 1024**3
    max_member_size: int = 2 * 1024**3
    max_ratio: float = 1000.0

    def __post_init__(self) -> None:
        for name in ("max_entries", "max_total_size", "max_member_size"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        if (
            isinstance(self.max_ratio, bool)
            or not isinstance(self.max_ratio, (int, float))
            or not math.isfinite(self.max_ratio)
            or self.max_ratio <= 0
        ):
            raise ValueError("max_ratio must be a finite positive number")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    message: str
    member: str | None = None
    related_member: str | None = None
    entry_index: int | None = None


@dataclass
class Report:
    archive: str
    entry_count: int = 0
    checked_entries: int = 0
    declared_uncompressed_bytes: int = 0
    declared_compressed_bytes: int = 0
    scan_complete: bool = False
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None

    def fails(self, fail_on: Severity = "warning") -> bool:
        if fail_on not in ("warning", "error"):
            raise ValueError("fail_on must be 'warning' or 'error'")
        return bool(self.error) or any(
            finding.severity == "error" or fail_on == "warning" for finding in self.findings
        )

    def to_dict(self) -> dict:
        return asdict(self)

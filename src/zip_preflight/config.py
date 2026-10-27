"""Strict JSON configuration with CLI overrides and no optional dependencies."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from pathlib import Path

from .models import Limits, Severity
from .scanner import RULE_CODES

DEFAULT_CONFIG = ".zip-preflight.json"
_DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class Settings:
    format: str = "text"
    fail_on: Severity = "warning"
    max_entries: int = _DEFAULT_LIMITS.max_entries
    max_total_size: int = _DEFAULT_LIMITS.max_total_size
    max_member_size: int = _DEFAULT_LIMITS.max_member_size
    max_ratio: float = _DEFAULT_LIMITS.max_ratio
    ignore_rules: tuple[str, ...] = ()
    summary: bool = False
    max_findings: int = 5

    def __post_init__(self) -> None:
        if self.format not in ("text", "json"):
            raise ValueError("format must be 'text' or 'json'")
        if self.fail_on not in ("warning", "error"):
            raise ValueError("fail_on must be 'warning' or 'error'")
        if not isinstance(self.summary, bool):
            raise ValueError("summary must be a boolean")
        if (
            isinstance(self.max_findings, bool)
            or not isinstance(self.max_findings, int)
            or self.max_findings < 0
        ):
            raise ValueError("max_findings must be a nonnegative integer")
        if not isinstance(self.ignore_rules, (list, tuple)) or any(
            not isinstance(code, str) for code in self.ignore_rules
        ):
            raise ValueError("ignore_rules must be an array of rule codes")
        unknown = set(self.ignore_rules) - RULE_CODES
        if unknown:
            raise ValueError(
                f"unknown rule codes: {', '.join(ascii(code) for code in sorted(unknown))}"
            )
        object.__setattr__(self, "ignore_rules", tuple(dict.fromkeys(self.ignore_rules)))
        try:
            _ = self.limits
        except OverflowError as error:
            raise ValueError("max_ratio must be a finite positive number") from error

    @property
    def limits(self) -> Limits:
        return Limits(self.max_entries, self.max_total_size, self.max_member_size, self.max_ratio)


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key!r}")
        result[key] = value
    return result


def _invalid_constant(value: str) -> None:
    raise ValueError(f"{value} is not a valid JSON number")


def load_settings(
    overrides: dict, *, config_path: str | None = None, no_config: bool = False
) -> Settings:
    """Load only the current directory's config, then apply explicit CLI values."""
    values = {}
    if not no_config:
        path = Path(config_path) if config_path is not None else Path(DEFAULT_CONFIG)
        if config_path is not None or path.exists():
            try:
                data = json.loads(
                    path.read_text(encoding="utf-8-sig"),
                    object_pairs_hook=_unique_object,
                    parse_constant=_invalid_constant,
                )
                if not isinstance(data, dict):
                    raise ValueError("configuration must be a JSON object")
                unknown = data.keys() - {item.name for item in fields(Settings)}
                if unknown:
                    raise ValueError(
                        f"unknown settings: {', '.join(ascii(key) for key in sorted(unknown))}"
                    )
                if "max_findings" in data and "summary" not in data:
                    data["summary"] = True
                # Validate the file even when a CLI option will override a bad value.
                values = asdict(Settings(**data))
            except (OSError, ValueError, RecursionError) as error:
                raise ValueError(f"Invalid config {str(path)!r}: {error}") from error
    values.update(overrides)
    if "max_findings" in overrides and "summary" not in overrides:
        values["summary"] = True
    return Settings(**values)

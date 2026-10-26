"""Read-only ZIP metadata checks for release pipelines and shared datasets."""

from .models import Finding, Limits, Report
from .scanner import scan_archive

__version__ = "0.2.0"
__all__ = ["Finding", "Limits", "Report", "scan_archive"]

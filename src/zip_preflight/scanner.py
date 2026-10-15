"""Inspect central-directory metadata. Never open or extract a member payload."""

from __future__ import annotations

import os
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass, field

from .models import Finding, Limits, Report, Severity

_DRIVE = re.compile(r"^[A-Za-z]:")
_RESERVED = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])$", re.IGNORECASE)
_WINDOWS_INVALID = frozenset('<>:"|?*')
_BIDI = frozenset("\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069")


def _portable_key(component: str) -> str:
    return unicodedata.normalize(
        "NFC", unicodedata.normalize("NFC", component.rstrip(" .")).casefold()
    )


def _check_member(info: zipfile.ZipInfo, index: int, report: Report, limits: Limits) -> None:
    # orig_filename retains embedded NULs that ZipInfo.filename truncates.
    name = info.orig_filename

    def add(code: str, severity: Severity, message: str) -> None:
        report.findings.append(Finding(code, severity, message, name, entry_index=index))

    path = name.replace("\\", "/")
    parts = path.rstrip("/").split("/")
    if not name or not path.strip("/"):
        add("EMPTY_PATH", "error", "Entry has no relative filename.")
    if path.startswith("/") or _DRIVE.match(path):
        add("ABSOLUTE_PATH", "error", "Rooted, UNC, or drive-qualified path.")
    if ".." in parts:
        add("PARENT_PATH", "error", "Parent-directory component can escape the destination.")
    if "\\" in name:
        add("BACKSLASH_PATH", "warning", "Backslashes are treated differently by ZIP extractors.")
    if any(part in ("", ".") for part in parts):
        add("NON_CANONICAL_PATH", "warning", "Empty or current-directory path component.")
    if any(ord(char) < 32 or ord(char) == 127 for char in name):
        add("CONTROL_CHARACTER", "error", "Filename contains a control character, including NUL.")
    if any(char in _BIDI for char in name):
        add("BIDI_CONTROL", "warning", "Bidirectional control character can disguise a filename.")

    ordinary = [part for part in parts if part not in ("", ".", "..")]
    if any(any(char in _WINDOWS_INVALID for char in part) for part in ordinary):
        add("WINDOWS_CHARACTER", "error", "Component contains a Windows-reserved character.")
    if any(_RESERVED.fullmatch(part.split(".", 1)[0].rstrip(" ")) for part in ordinary):
        add(
            "WINDOWS_DEVICE",
            "error",
            "Component uses a Windows device name, even with an extension.",
        )
    if any(part.endswith((" ", ".")) for part in ordinary):
        add("TRAILING_DOT_SPACE", "error", "Windows tools may trim a trailing dot or space.")
    if any(
        len(part.encode("utf-8", errors="surrogatepass")) > 255
        or len(part.encode("utf-16-le", errors="surrogatepass")) // 2 > 255
        for part in ordinary
    ):
        add("LONG_COMPONENT", "warning", "Component exceeds 255 UTF-8 bytes or UTF-16 code units.")
    if len(path.encode("utf-16-le", errors="surrogatepass")) // 2 >= 260:
        add(
            "LONG_PATH",
            "warning",
            "Relative path already reaches the legacy Windows 260-unit limit.",
        )

    mode = (info.external_attr >> 16) & 0xFFFF if info.create_system == 3 else 0
    file_type = stat.S_IFMT(mode)
    if file_type == stat.S_IFLNK:
        add("SYMLINK", "error", "Unix metadata marks a symbolic link; target is not inspected.")
    elif file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
        add("SPECIAL_FILE", "error", "Unix metadata marks a device, socket, or FIFO.")
    if info.flag_bits & 1:
        add(
            "ENCRYPTED_MEMBER",
            "warning",
            "Encrypted member reduces interoperability; payload is not read.",
        )
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        add(
            "COMPRESSION_METHOD",
            "warning",
            "Compression method is outside Stored/Deflate compatibility.",
        )
    if info.file_size > limits.max_member_size:
        add("MEMBER_SIZE_LIMIT", "error", f"Declared size exceeds {limits.max_member_size} bytes.")
    if info.file_size and (
        info.compress_size == 0 or info.file_size / info.compress_size > limits.max_ratio
    ):
        add(
            "COMPRESSION_RATIO",
            "warning",
            f"Declared expansion ratio exceeds {limits.max_ratio:g}:1.",
        )


@dataclass
class _PathNode:
    children: dict[str, _PathNode] = field(default_factory=dict)
    spelling: str = ""
    member: str | None = None
    aliases: set[str] = field(default_factory=set)
    file_member: str | None = None
    directory_member: str | None = None
    conflict_reported: bool = False


def _check_paths(infos: list[zipfile.ZipInfo], report: Report) -> None:
    exact: dict[str, str] = {}
    # Each prefix is indexed, so implicit directory aliases also produce findings.
    # An iterative trie avoids recursion and quadratic prefix construction for deep paths.
    root = _PathNode()

    for index, info in enumerate(infos):
        name = info.orig_filename
        if name in exact:
            report.findings.append(
                Finding(
                    "DUPLICATE_ENTRY",
                    "error",
                    "Same entry name occurs more than once.",
                    name,
                    exact[name],
                    index,
                )
            )
        else:
            exact[name] = name

        parts = [part for part in name.replace("\\", "/").split("/") if part not in ("", ".")]
        if not parts or ".." in parts or "\x00" in name:
            continue
        mode = (info.external_attr >> 16) & 0xFFFF if info.create_system == 3 else 0
        is_directory = name.endswith(("/", "\\")) or stat.S_ISDIR(mode)
        node = root
        for end, component in enumerate(parts, start=1):
            key = _portable_key(component)
            if key not in node.children:
                node.children[key] = _PathNode(spelling=component, member=name)
            node = node.children[key]
            if node.spelling != component and component not in node.aliases:
                report.findings.append(
                    Finding(
                        "PATH_COLLISION",
                        "error",
                        "Paths alias after NFC normalization, case folding, "
                        "or trailing-dot/space trimming.",
                        name,
                        node.member,
                        index,
                    )
                )
                node.aliases.add(component)

            is_dir = end < len(parts) or is_directory
            opposite = node.file_member if is_dir else node.directory_member
            if opposite is not None and not node.conflict_reported:
                report.findings.append(
                    Finding(
                        "FILE_DIRECTORY_CONFLICT",
                        "error",
                        "Path is used as both a file and a directory.",
                        name,
                        opposite,
                        index,
                    )
                )
                node.conflict_reported = True
            if is_dir:
                node.directory_member = node.directory_member or name
            else:
                if node.file_member is not None and node.file_member != name:
                    report.findings.append(
                        Finding(
                            "TARGET_COLLISION",
                            "error",
                            "Multiple entries resolve to the same file target.",
                            name,
                            node.file_member,
                            index,
                        )
                    )
                node.file_member = node.file_member or name


def scan_archive(path: str | os.PathLike[str], *, limits: Limits | None = None) -> Report:
    """Read ZIP metadata and return findings, including an error for unreadable archives.

    No extraction, CRC verification, local-header comparison, or nested scanning occurs.
    An empty finding list does not establish that an archive is safe to extract.
    """
    limits = limits or Limits()
    report = Report(archive=os.fsdecode(path))
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            report.entry_count = len(infos)
            report.declared_uncompressed_bytes = sum(info.file_size for info in infos)
            report.declared_compressed_bytes = sum(info.compress_size for info in infos)
            if len(infos) > limits.max_entries:
                report.findings.append(
                    Finding(
                        "ENTRY_COUNT_LIMIT",
                        "error",
                        f"Archive has {len(infos)} entries; "
                        f"only the first {limits.max_entries} are checked.",
                    )
                )
            if report.declared_uncompressed_bytes > limits.max_total_size:
                report.findings.append(
                    Finding(
                        "TOTAL_SIZE_LIMIT",
                        "error",
                        f"Total declared size exceeds {limits.max_total_size} bytes.",
                    )
                )
            checked = infos[: limits.max_entries]
            for index, info in enumerate(checked):
                _check_member(info, index, report, limits)
            _check_paths(checked, report)
            report.checked_entries = len(checked)
            report.scan_complete = len(checked) == len(infos)
    except (
        OSError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        NotImplementedError,
    ) as error:
        report.error = f"{type(error).__name__}: {error}"
    return report

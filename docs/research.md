# Research and project scope

Research date: **2026-10-15**. This is a focused landscape review, not an exhaustive
search or a claim that the underlying checks are novel.

## Problem

ZIP bundles are commonly built on one OS and consumed on another. A bundle can
have valid ZIP metadata but contain Windows device names, names that alias after
case/Unicode normalization, or a file where another entry requires a directory.
Release authors benefit from actionable checks before distribution.

Microsoft's [file naming reference](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file)
documents reserved characters/device names, case-sensitivity assumptions, and
trailing-dot/space behavior. Its examples include superscript-digit device names;
the test suite covers these rather than matching ASCII digits alone.

Python's [zipfile documentation](https://docs.python.org/3/library/zipfile.html)
describes filename decoding, extraction considerations, compression compatibility,
and decompression pitfalls. Those constraints motivate metadata-only inspection
with explicit limits, while also requiring an honest statement that metadata
checks do not validate payloads or establish safe extraction.

## Existing tools reviewed

| Project | Documented focus | Relationship to zip-preflight |
| --- | --- | --- |
| [pmqs/zipdetails](https://github.com/pmqs/zipdetails) | Internal ZIP records, fields, structure, and diagnostic messages | Use for detailed structural investigation; this project presents a narrower portability policy and JSON/CI exit status |
| [yuk7/zipkirei](https://github.com/yuk7/zipkirei) | Repair garbled/decomposed Unicode names, separators, and OS metadata without recompression | Useful for repair workflows; this project only reports findings and never rewrites input |
| [ziptools](https://learning-python.com/ziptools/ziptools/_README.html) | Portable archive creation/extraction, links, metadata, and nonportable filename handling | Broader archive management; this project is a small read-only lint step |
| [snyk/zip-slip-vulnerability](https://github.com/snyk/zip-slip-vulnerability) | Public research and affected-library tracking for traversal during extraction | Documents a real extraction failure mode; this tool flags suspicious paths but is not a vulnerability detector for extractors |

These are complementary projects. Their presence is evidence that portability and
archive inspection are established needs, not proof of demand for this particular
CLI. No adoption, performance, or coverage advantage is claimed. The implementation
is original and uses the Python standard library; no source code from the reviewed
projects is bundled.

## Chosen first-release scope

1. Local ZIP paths, decoded central-directory metadata, no member extraction.
2. Cross-platform naming checks, including **implicit directory** collisions.
3. Explicit policy thresholds, deterministic findings, documented codes, and JSON.
4. A Python API, CLI, pre-commit hook, and CI integration with no runtime dependencies.
5. Adversarial synthetic fixtures that never require extracting suspicious entries.

The scope is intentionally small enough to verify. Auto-repair, nested archive
inspection, antivirus scanning, local-header validation, and secure extraction are
separate problems and are not promised. See [the exact coverage](rules.md).

## Evaluation approach

Test cases are generated in temporary directories. They exercise ordinary files,
path traversal, reserved names, case/NFC aliases, implicit-directory aliases,
duplicate entries, file/directory conflicts, Unix metadata, unusual compression,
encrypted flags, NUL names, invalid archives, and limit/exit-code behavior.
Tests also assert that scanning does not open member payloads or modify the input.
CI exercises supported Python versions across Windows, macOS, and Linux and checks
an installed wheel independently of the source checkout.

## Useful next contributions

- Small reproductions of extractor-specific filename behavior, with OS/tool versions.
- A configurable destination path budget instead of only relative long-path checks.
- A documented report schema extension for additional output formats.
- Optional legacy metadata encodings with a clear minimum Python-version policy.

New behavior should come with a minimal fixture, a primary reference where
available, and updated scope documentation. Avoid presenting heuristic matches as
security guarantees.

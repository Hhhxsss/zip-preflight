# Changelog

## Unreleased

- Add a native desktop result window with background checks, readable issue
  explanations, paging, copy, and complete atomic JSON/text report exports.
- Add opt-in current-user Windows ZIP cascading menus with install/remove support
  and a standalone windowed executable build.
- Share the complete JSON report envelope between the desktop app and CLI.
- Add UTF-8 JSON configuration, current-directory discovery, explicit config
  selection, CLI overrides, and visible rule exceptions.
- Add grouped text and JSON summaries with configurable text example limits;
  preserve full findings and policy results when examples are omitted.
- Keep schema version 1's default JSON shape; add optional `summary` and
  `ignore_rules` fields when those features are used.
- Detect Windows console device names `CONIN$` and `CONOUT$`, including extensions
  and nested path components.
- Include uppercase and mixed-case ZIP extensions in the pre-commit hook.
- Warn about repeated trailing path separators while accepting ordinary directory
  entries with a single trailing separator.

## 0.1.0 — 2026-10-15

- Initial metadata-only ZIP linter with a CLI and typed Python report objects.
- Cross-platform filename rules, normalized and implicit-directory collisions,
  duplicate entries, and file/directory conflicts.
- Traversal/rooted-path, Unix link/type, encryption, and compression checks.
- Configurable declared-size, ratio, and entry-count policy limits.
- Text and JSON reports, documented exit codes, and quoted glob expansion.
- English/Chinese documentation, generated demo fixtures, pre-commit hook, and CI.

This release does not extract members, validate payloads, or establish safe extraction.

# Rule reference

Rules inspect decoded **central-directory** metadata, not actual extracted files.
Findings are emitted in archive entry order, followed by path relationship findings.
`entry_index` is zero-based and identifies duplicate entries with identical names.
Archive-level rules have no member or entry index.

## Errors

| Code | Meaning | Suggested action |
| --- | --- | --- |
| `EMPTY_PATH` | Empty name or root-only path | Remove the entry or give it a relative name |
| `ABSOLUTE_PATH` | Rooted, UNC, or drive-qualified path, including `C:relative` | Build paths relative to the archive root |
| `PARENT_PATH` | A literal `..` component using either slash style | Remove parent references |
| `CONTROL_CHARACTER` | ASCII control (0–31) or DEL in a name; original NUL retained | Rename without control characters |
| `WINDOWS_CHARACTER` | `< > : " \| ? *` in a component; includes alternate data stream syntax | Rename for Windows compatibility |
| `WINDOWS_DEVICE` | `CON`, `CONIN$`, `CONOUT$`, `PRN`, `AUX`, `NUL`, `COM1`–`COM9`, `LPT1`–`LPT9`, or superscript ¹/²/³ forms, optionally with extensions | Rename the component |
| `TRAILING_DOT_SPACE` | Component ends in a dot or ASCII space | Remove the trailing characters |
| `DUPLICATE_ENTRY` | Same original entry name appears twice | Rebuild the ZIP without duplicate entries |
| `PATH_COLLISION` | A component aliases under the portability model | Use one spelling throughout the bundle |
| `TARGET_COLLISION` | Different member names resolve to the same modeled file target | Remove aliases, including `a//b`, `a/./b`, and `a\b` |
| `FILE_DIRECTORY_CONFLICT` | Same modeled path serves as a file and a directory | Rename or remove the conflicting entry |
| `SYMLINK` | Unix file type is a symbolic link | Review the bundle and extraction policy |
| `SPECIAL_FILE` | Unix file type is a FIFO, socket, block/character device, or another non-regular type | Distribute ordinary files instead |
| `MEMBER_SIZE_LIMIT` | Declared member bytes exceed the configured limit | Review contents or adjust the policy |
| `TOTAL_SIZE_LIMIT` | Sum of all declared uncompressed bytes exceeds the limit | Review contents or adjust the policy |
| `ENTRY_COUNT_LIMIT` | Too many entries | Only the first limit entries are checked; `scan_complete` is false |

## Warnings

| Code | Meaning |
| --- | --- |
| `BACKSLASH_PATH` | Backslashes can be separators or literal characters depending on extractor |
| `NON_CANONICAL_PATH` | Empty or `.` component can be interpreted differently, including repeated trailing separators such as `dir//` |
| `BIDI_CONTROL` | Bidirectional marks, embeddings, overrides, or isolates can disguise a name |
| `LONG_COMPONENT` | Component exceeds 255 UTF-8 bytes or 255 UTF-16 code units |
| `LONG_PATH` | Relative path already reaches 260 UTF-16 code units |
| `ENCRYPTED_MEMBER` | General-purpose ZIP encryption flag is set |
| `COMPRESSION_METHOD` | Method is outside Stored (0) and Deflate (8) |
| `COMPRESSION_RATIO` | Declared uncompressed/compressed ratio exceeds policy, or nonempty declared data has zero compressed bytes |

Long-path checks do **not** include the destination directory length and cannot
predict all OS/API limits. Stored/Deflate is a compatibility baseline; other methods
can be valid ZIP and still trigger a warning. High ratios are often legitimate for
repetitive datasets; this is a heuristic, not a ZIP-bomb verdict.

One trailing separator denotes a directory and does not by itself trigger
`NON_CANONICAL_PATH`. Windows device names are checked case-insensitively in every
component; see [Python's reserved-path reference](https://docs.python.org/3.14/library/os.path.html#os.path.isreserved).

## Portability model

Separators are interpreted as `/` or `\`. Each ordinary component has trailing ASCII
dots/spaces removed, is NFC-normalized, case-folded, then NFC-normalized again for
comparison. Empty and `.` components are omitted when comparing targets. Paths with
literal `..` or NUL are reported individually and excluded from relationship checks.

Implicit directories are indexed: `Docs/a` and `docs/b` conflict even though their
full paths differ. An explicit `docs/` entry alongside `docs/a` is normal. Duplicate
explicit directory entries are reported as duplicate entries. Symlinks are treated
as file targets; their payloads and targets are never read.

Unicode case folding is intentionally conservative: `straße` and `STRASSE` collide
in this model even when a particular filesystem would keep them distinct. NFC is
not macOS filesystem normalization emulation. No Unicode compatibility (NFKC) or
visual-confusable matching is performed.

## Default limits

| Option / Python field | Default | Rule |
| --- | --- | --- |
| `--max-entries` / `max_entries` | 100,000 | `ENTRY_COUNT_LIMIT` |
| `--max-total-size` / `max_total_size` | 10,737,418,240 bytes (10 GiB) | `TOTAL_SIZE_LIMIT` |
| `--max-member-size` / `max_member_size` | 2,147,483,648 bytes (2 GiB) | `MEMBER_SIZE_LIMIT` |
| `--max-ratio` / `max_ratio` | 1000 | `COMPRESSION_RATIO` |

Limits trigger only when exceeded, not when equal. Sizes and entry counts must be
positive integers. Ratios must be finite positive numbers. Totals include all
central-directory entries, including directories and entries beyond the checking
limit. The entry limit bounds rule processing, **not** metadata parsing or memory.

## Not covered

No payload decompression, CRC/content validation, local-header comparison,
overlapping-entry detection, alternate Unicode-path extra-field interpretation,
nested archives, malware detection, symlink target validation, filesystem-specific
8.3 aliases, or extraction destination inspection is performed. Legacy filename
encodings follow `zipfile` defaults (UTF-8 flag or CP437); the tool does not guess
encodings. Multipart ZIP support follows the Python standard library and is not
provided. Always use a maintained extractor and appropriate isolation.

# Security and supported scope

The latest 0.1.x release is supported for bug reports. This is an early-stage ZIP
metadata linter; it is not a security boundary, malware scanner, or secure extractor.

The scanner never calls member `open`, `read`, `extract`, or `extractall`. It does
parse ZIP metadata through Python's standard library. Use a maintained Python
release and enforce process-level resource limits for untrusted inputs. The entry
limit applies after central-directory loading and does not bound that allocation.
The CLI's own glob expansion also follows user-supplied patterns; avoid enormous
recursive patterns in automated jobs.

A passing result is not proof that extraction is safe. Payload corruption,
overlapping entries, local-header inconsistencies, nested archives, malicious
contents, alternate filename metadata, and destination-specific conditions are
outside this release's scope. See [rules and limitations](docs/rules.md).

## Report a vulnerability

Use the repository's
[private vulnerability reporting form](https://github.com/Hhhxsss/zip-preflight/security/advisories/new).
If private reporting is unavailable, open an issue requesting a private reporting
channel without including exploit details or private data.

Include a small synthetic reproducer, affected versions, impact, and environment
details. Please avoid publishing sensitive archives, personal filenames, or
credentials. No response-time or remediation SLA is promised.

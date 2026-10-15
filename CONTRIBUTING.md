# Contributing

Thanks for helping make ZIP bundles easier to share across platforms.

## Development

Use Python 3.10 or newer and a virtual environment:

```console
python -m venv .venv
```

Activate it with `.venv\Scripts\Activate.ps1` on Windows PowerShell or
`source .venv/bin/activate` on macOS/Linux, then:

```console
python -m pip install -e . build ruff
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
```

The tests use the standard library and generate fixtures in temporary directories.
They require no network, credentials, GPUs, or downloaded archives.

## Reporting problems

Open an issue with the rule code, tool/Python/OS versions, expected behavior, and
a minimal reproducer. Include the extractor and filesystem if relevant. Use
synthetic entry names when the original archive is private. Reports contain
filenames and local paths; inspect them before posting.

For a potential security issue, use [private reporting](SECURITY.md).

## Making changes

1. Open an issue before a substantial feature or a breaking policy change.
2. Work on a focused branch with a descriptive commit message.
3. Add a small regression test for new behavior or a bug fix.
4. Update the rule/usage documentation when public behavior changes.
5. Run the development checks above and describe the results in your pull request.

For filename rules, prefer a primary reference and a minimal `ZipInfo` fixture.
Preserve raw backslashes explicitly in tests: Windows ZIP writers may otherwise
normalize them before the scanner sees them. For malformed metadata, keep byte
patches narrow and document the field being changed.

Do not extract hazardous fixtures, commit large archive blobs, add real private
data, or describe heuristic checks as proof of secure extraction. Maintain Python
3.10 compatibility and the zero-runtime-dependency constraint.

## Compatibility

Finding codes and the documented JSON schema are public interfaces. Message prose
may improve without a schema change. A breaking field or semantic change requires
a schema-version change and migration notes. The 0.x releases may add rules; review
the changelog before updating a pinned CI version.

## Maintainer release checklist

- Update the version in `pyproject.toml` and `src/zip_preflight/__init__.py`.
- Update the changelog and any pinned installation examples.
- Run tests, lint, formatting, and the wheel/sdist build.
- Install the wheel in a clean environment and run `python -I tools/smoke_install.py`.
- Push the version tag only after the commit's CI succeeds.
- Attach the built wheel and sdist to the GitHub release if distributing binaries.

By contributing, you agree that your contributions use the project's MIT license.

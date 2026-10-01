---
id: 2026-10-01-identity-guard-filesystem-attribute-set-varies-with-the-python-version
title: The identity boundary guard derives its filesystem-attribute set from the running interpreter, but CI runs only Python 3.11 while the package supports 3.11 to 3.13
status: open
importance: low
importance_why: The guard's strictness differs by interpreter, so a name innocent on CI can fail on a contributor's newer Python, and a method added in a newer Python is checked nowhere CI runs.
effort: S
kind: gap
area: activity-identity, tests/identity/test_boundary.py, .github/workflows/ci.yml
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-identity-guard-filesystem-attribute-set-varies-with-the-python-version.md] Freeze the filesystem-attribute set the identity guard checks, with a test that pins its relation to pathlib"
context:
  - tests/identity/test_boundary.py
  - .github/workflows/ci.yml
  - pyproject.toml
blocked_by: []
---

## What
`_FS_ATTRIBUTES` in the identity boundary guard is "the public names `pathlib.Path`
has and `pathlib.PurePath` lacks", computed at import time from the running
interpreter, and any attribute of that name on any receiver in `src/fitdocs/identity/`
is treated as a filesystem touch. The header acknowledges it ("Python-version
dependent by construction", and the declared exclusion "growth of `pathlib.Path`
in a later Python version"). CI installs Python 3.11 only.

## Why it matters
`requires-python` is `>=3.11` and the classifiers list 3.11, 3.12 and 3.13, so
the supported range includes interpreters the guard has never run on in CI. The
set measured on this machine differs: against 3.11's 39 names, 3.12 adds
`is_junction` and `walk`; 3.13 adds `from_uri`, `is_junction`, `walk`; 3.14 adds
`copy`, `copy_into`, `from_uri`, `info`, `is_junction`, `move`, `move_into`,
`walk`; every newer interpreter drops `link_to`. Names such as `info`, `copy` or
`move` are ordinary identifiers on non-Path receivers, so a future identity edit
that is fine on CI can fail on a contributor's Python 3.14, and a new Path method
is a filesystem touch the CI guard cannot see.

## Evidence
Measured at `fc5c06d` with the local interpreters (`set(dir(pathlib.Path)) -
set(dir(pathlib.PurePath))`, public names only), 3.11 as the baseline.
- `tests/identity/test_boundary.py:183-190` the derivation; `:18-19` the declared
  exclusion; `:992-995` `test_filesystem_attributes_are_derived_from_pathlib` pins
  only a handful of names being present and a few absent.
- `.github/workflows/ci.yml:50` `run: uv python install 3.11`; `pyproject.toml:6`
  `requires-python = ">=3.11"`, `:18-20` the 3.11-3.13 classifiers, `:82`
  `python_version = "3.11"` for mypy.
- No current identity code spells `.info`, `.copy`, `.copy_into`, `.move`,
  `.move_into`, `.walk`, `.from_uri` or `.is_junction` (grep over
  `src/fitdocs/identity/`), so nothing fails today; the guard was not run on a
  newer interpreter (doing so would replace the project's `.venv`).

## How to pick it up
1. Decide between freezing the set (a literal tuple checked against the running
   interpreter's `pathlib` with "at least these" semantics, so a newer Python
   can only add names the maintainer then reviews) and adding 3.13 to the CI
   matrix for this guard.
2. Whichever is chosen, keep the exemption test for `decision.group` in
   `planning` (`group` is a `Path` method name on POSIX).
3. Done when the guard's verdict on `src/fitdocs/identity/` is the same on 3.11
   and the newest supported interpreter.

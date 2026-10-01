---
id: 2026-10-01-parse-frontmatter-raises-on-unconstructible-yaml-values
title: "contract.parse_frontmatter catches only yaml.YAMLError, so a hand-edited `date: 2026-02-30` raises ValueError out of every full-scan command"
status: open
importance: high
importance_why: One hand-edited page with an impossible date or timezone offset turns sync, regen, load and check into tracebacks until the user finds the file, and breaks the documented "never raises" contract that wiki-contract Req 1.2 makes every command rely on.
effort: S
kind: bug
area: wiki-contract, activity-identity, src/fitdocs/contract.py, src/fitdocs/docio.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl wiki-contract [queue: .kiro/queue/2026-10-01-parse-frontmatter-raises-on-unconstructible-yaml-values.md] Make contract.parse_frontmatter return None for every YAML value PyYAML cannot construct, and pin it through the scans"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/docio.py
  - src/fitdocs/identity/pages.py
  - src/fitdocs/audit.py
  - .kiro/specs/wiki-contract/requirements.md
  - tests/test_contract.py
blocked_by: []
---

## What
`parse_frontmatter` wraps `yaml.safe_load` in `except yaml.YAMLError`. PyYAML
builds YAML timestamps with `datetime.date` / `datetime.datetime`, so an
unquoted frontmatter value that matches the timestamp pattern but is not a real
date raises a plain `ValueError`, which is not a `YAMLError`. It escapes
`parse_frontmatter`, then `docio.read_frontmatter` (which catches only
`OSError` / `UnicodeDecodeError`), then every scan that calls either. The
docstrings of both functions say "Never raises"; wiki-contract Req 1.2 says an
unparseable document is "not a fitdocs document in every command" and the run
continues.

## Why it matters
`date: 2026-02-30` is an ordinary typo in an unquoted hand-edited key, in any
`workouts/*.md` page. Every command that scans `workouts/` then dies with a
traceback and exit 1, `fitdocs check` included, which is the command meant to
report problems. Nothing names the offending file in the user-facing output.
The activity-identity scan (`identity.pages.scan_pages`, run by `sync`, `drain`
and `regen`) made this a hard stop for the whole sync path, but `audit`,
`load.engine`, `plans.corpus`, `history.documents` and `performance.engine`
share the same reader and the same hole.

## Evidence
Read at `fc5c06d`.
- `src/fitdocs/contract.py:846-849`: `try: parsed = yaml.safe_load(block)`
  / `except yaml.YAMLError: return None`. Docstring claim: `:835` "Never
  raises". `src/fitdocs/docio.py:83-87` repeats the claim for `read_frontmatter`.
- Behavioral repro, `uv run python -c` calling `parse_frontmatter("---\n<line>\n---\nbody\n")`:
  - `date: 2026-02-30` -> `ValueError: day is out of range for month`
  - `date: 2026-13-01` -> `ValueError: month must be in 1..12`
  - `d: 0000-01-01` -> `ValueError: year 0 is out of range`
  - `ts: 2026-01-01 10:00:00+24:30` -> `ValueError: offset must be a timedelta strictly between -timedelta(hours=24) and timedelta(hours=24)`
  - 5000 nested `[` ... `]` -> `RecursionError` (not a ValueError either)
- End to end: a data root whose `workouts/bad.md` is `---\ndate: 2026-02-30\n---\nhand-edited\n`.
  `fitdocs check --out <root>`, `fitdocs regen --out <root>`,
  `fitdocs load --out <root> --no-prompt` and `fitdocs sync <empty-dir> --out <root> --no-prompt`
  each exit 1 with `ValueError: day is out of range for month` raised from
  `yaml/constructor.py:330` (`check`'s frames: `cli.py:544 check_command` ->
  `audit.py:607 audit` -> `contract.py:847`). `history` and `plan` were not run.
- The only pin is `tests/test_contract.py:567-569`
  (`test_parse_frontmatter_yields_none_for_unparseable_yaml`, input
  `type: [unclosed`), which raises `YAMLError`. No test feeds a
  constructible-looking-but-invalid timestamp.

## How to pick it up
1. Add the failing parametrized test first in `tests/test_contract.py`: each
   input in the repro list above must give `parse_frontmatter(...) is None`.
2. Widen the `except` in `src/fitdocs/contract.py` (`ValueError` at least, which
   covers every timestamp case; decide whether `RecursionError` belongs too).
   Keep it in `contract.py`: every reader reaches YAML only through this function.
3. Pin it through a scan, not only the leaf: a `workouts/` page with
   `date: 2026-02-30` must leave `scan_pages`, `audit.audit` and `regen`
   returning normally with the page unrecognised (add to `tests/identity/test_pages.py`
   and `tests/test_audit.py`).
4. Read the sibling item before closing: once such a page is "not a fitdocs
   document", regen can write over or beside it (see
   `2026-10-01-regen-writes-over-or-beside-an-unreadable-page`).

## Open questions
- Should `fitdocs check` also report an unparseable `workouts/*.md` as a finding
  so the user learns which file is being ignored? Req 1.2 only requires that the
  run continue; the finding is a new surface and is the maintainer's call.

---
id: 2026-10-02-merge-fixtures-have-no-byte-pin
title: The tests/fixtures/merge.py fixtures have no byte pin, so a change to their bytes is noticed only when a golden page moves
status: open
importance: low
importance_why: Fixture bytes feed the composed-page golden and many assertions; a silent shift shows up far from its cause, though the composed_run golden catches the body.
effort: S
kind: gap
area: channel-merge, tests/fixtures/merge.py, tests/fixtures/test_merge_fixtures.py, tests/fixtures/test_builder.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: add a sha256 pin per tests/fixtures/merge.py fixture (run pair, run trio, ride pair and its two variants), with a completeness guard over merge.__all__, modelled on tests/fixtures/test_builder.py::_UNMOVED_DIGESTS [queue: .kiro/queue/2026-10-02-merge-fixtures-have-no-byte-pin.md]"
context:
  - tests/fixtures/merge.py
  - tests/fixtures/test_merge_fixtures.py
  - tests/fixtures/test_builder.py
  - tests/render/test_golden_docs.py
blocked_by: []
---

## What
`tests/fixtures/builder.py`'s fixtures are pinned by digest: `test_builder.py`
holds `_UNMOVED_DIGESTS` and a completeness guard that every `*_fit_bytes`
builder joins the table. The channel-composition fixtures in
`tests/fixtures/merge.py` have neither a digest nor a guard, and the builder
guard cannot see them because it scans only `vars(builder)`.

## Why it matters
A change to a `merge.py` helper (a constant, a field order, a shared builder
call) shifts every file's bytes and so every sha256, ref and page stem derived
from them. Today that shows up as a failure in `composed_run`'s golden or in an
e2e assertion, which names the symptom and not the fixture that moved.

## Evidence
At 5c41759.
- `tests/fixtures/test_merge_fixtures.py` has a validity check
  (`:208-218`, decodes and passes the integrity check) and a determinism check
  (`:220-231`, building twice gives identical bytes); `grep -n "sha\|digest"
  tests/fixtures/test_merge_fixtures.py` finds no digest. Neither check fails
  when the bytes change consistently.
- `tests/fixtures/test_builder.py:984-1001`: `test_fixture_bytes_did_not_move`
  parametrised over `_UNMOVED_DIGESTS`, and
  `test_every_zero_argument_fit_bytes_builder_is_pinned_or_reexport_b`, whose
  enumeration is `vars(builder).items()` at `:994`.
- `tests/fixtures/merge.py:41-48` `__all__` lists `ride_pair_fit_bytes`,
  `run_pair_fit_bytes`, `run_trio_fit_bytes` (and three constants); the self-test builds the files
  at `test_merge_fixtures.py:192-204`, including two `ride_pair_fit_bytes`
  variants (`copy_power=False`, `copy_shift_h=1`).
- `tests/render/test_golden_docs.py:763` `test_composed_run_markdown_matches_committed_golden`
  is the backstop: it catches a moved body, not a moved fixture.

## How to pick it up
1. Compute the sha256 of each `_all_files()` entry in
   `tests/fixtures/test_merge_fixtures.py:192-204` and pin them in a table
   there, with a "did not move" test.
2. Add a guard that every name in `merge.__all__` ending in `_fit_bytes` is
   covered, so a new fixture cannot slip past (the way the builder guard does).
3. Done when changing one constant in `merge.py` reds the pin test by fixture
   name.

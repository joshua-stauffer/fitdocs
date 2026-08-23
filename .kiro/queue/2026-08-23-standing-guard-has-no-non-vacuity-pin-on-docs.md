---
id: 2026-08-23-standing-guard-has-no-non-vacuity-pin-on-docs
title: The standing forbidden-string guard has no coverage pin on docs/, so a walk blind to every shipped document reds nothing
status: open
importance: medium
importance_why: docs/ is where the provenance record lives — the one document this spec ships specifically to be read by outsiders. A narrowing that silently stops scanning it would report a clean tree while the most-read artifact went unchecked, and the suite would stay green.
effort: S
kind: gap
area: tests, encumbered-content-purge
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.3 (reviewer mutation, reproduced)
pinned_at: c786326
resume_command: "do: add a docs/ coverage pin to test_standing_guard_scans_tracked_content_and_path_names alongside the existing .kiro/, src/ and tests/ pins, and verify it reds when docs/ is dropped from the walk"
context:
  - tests/test_forbidden_strings.py
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

`tests/test_forbidden_strings.py::test_standing_guard_scans_tracked_content_and_path_names`
asserts its walk actually reaches known-permanent directories, so a narrowed
walk cannot report a vacuous clean. As of task 9.3 it pins three: `.kiro/`,
`src/` and `tests/`.

It does not pin `docs/`. Narrowing the guard's `git ls-files -z` invocation to
`["git","ls-files","-z","src",".kiro","tests"]` — dropping `docs/` — leaves the
**entire suite green** in supplied-source mode (2458 passed).

## Why it matters

`docs/` holds `docs/reference/history-rewrites.md`, the provenance record. That
document is the artifact this whole spec produces for an outside reader, and it
is the one most likely to be edited by a future session that has forgotten what
the guard is for.

A walk that silently stopped covering `docs/` would report a clean tree while
the most-read document went entirely unscanned — and nothing would fail. That
is precisely the vacuity the three existing pins exist to prevent; `docs/` was
just never added.

The history here is instructive. Task 9.3 *had* to touch these pins: the guard
had hard-coded `tests/purge/` as a known-permanent directory, and the
retirement deleted it. Repointing to `src/` still discriminated, which made it
look like a clean swap — but review proved it had traded away the `tests/`
class, and a third pin was added. The same review then found `docs/` was never
covered at all. The lesson generalises: **a coverage pin that still fails
somewhere is not proof it fails everywhere it should.**

## Evidence

Reproduced by the task 9.3 reviewer and again at task 9.4:

- mutation: guard's walk → `["git","ls-files","-z","src",".kiro","tests"]`
- result: `2458 passed` with `FITDOCS_FORBIDDEN_STRINGS` supplied — no failure
- the three surviving pins each red alone on their own narrowing (verified:
  dropping `src` reds the `src/` pin solely; dropping `.kiro` reds the `.kiro/`
  pin; dropping `tests` reds the `tests/` pin)

## How to pick it up

Open `tests/test_forbidden_strings.py` and find
`test_standing_guard_scans_tracked_content_and_path_names`. It carries three
assertions of the form `assert any(rel.startswith("<dir>/") for rel in scanned_relative)`.

Add a fourth for `docs/`.

Then **prove it discriminates** rather than assuming: narrow the guard's
`git ls-files -z` invocation to drop `docs`, run
`FITDOCS_FORBIDDEN_STRINGS=<source> uv run pytest`, confirm the new assertion is
the failure, and revert **from a snapshot copy** — never a `git checkout` of
uncommitted work, which deletes the work being measured.

Consider whether the four should be derived from one list rather than written
four times; a fifth top-level directory added later will have the same gap.

Done when dropping `docs` from the walk reds, and the mutation is recorded
where the other guard mutations are recorded.

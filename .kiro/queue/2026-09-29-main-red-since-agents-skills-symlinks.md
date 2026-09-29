---
id: 2026-09-29-main-red-since-agents-skills-symlinks
title: main has been red since a6f5af2 -- the notice/mark guard reports the 19 tracked .agents/skills symlinks as "not a regular file"
status: open
importance: high
importance_why: The full suite fails on main and CI has failed on every push since 2026-09-20, so a real regression landing now would be indistinguishable from this one, and the next release's gates job cannot pass.
effort: S
kind: bug
area: tests/test_forbidden_strings.py, .agents/skills, .github/workflows/ci.yml
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, controller's pre-merge full-suite run)
pinned_at: a5792f2
resume_command: "do: make tests/test_forbidden_strings.py::_notice_guard_tracked_texts account for tracked symlinks (git mode 120000) explicitly -- e.g. resolve each one, require its target to be inside the repo and itself tracked (its files are then scanned under their own names), and record anything else as unreadable -- with a pin that a symlink pointing outside the repo still reds; then run the full suite and confirm CI on main goes green"
context:
  - tests/test_forbidden_strings.py
  - .agents/skills
  - .claude/skills
  - .github/workflows/ci.yml
blocked_by: []
---

## What
Commit `a6f5af2` ("chore: expose cc-sdd skills to codex", 2026-09-20) added
19 tracked symlinks under `.agents/skills/` (git mode `120000`), each
pointing at a `.claude/skills/kiro-*` directory. The ungated guard
`test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file` walks
every tracked path and, in `_notice_guard_tracked_texts`, files anything
for which `path.is_file()` is false under "not a regular file". A symlink
to a directory is not a regular file, so all 19 land in
`unexpected_unreadable` and the test's second assertion fails.

## Why it matters
`main` is red: the full suite fails locally and CI's run has failed on every
push since the symlinks landed. The last green CI run on main is `4f0ae00`
(2026-09-19). While main is red, a genuine regression is invisible, and the
release workflow's `gates` job would fail too.

## Evidence
- `uv run pytest tests/test_forbidden_strings.py::test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`
  on `main` at `a5792f2` -> `1 failed`; the assertion message lists
  `.agents/skills/kiro-debug: not a regular file`, `.agents/skills/kiro-discovery`, ...
- `git ls-files -s .agents/skills | awk '$1=="120000"' | wc -l` -> `19`.
- `tests/test_forbidden_strings.py:1289-1290` (`if not path.is_file(): unreadable[relative] = "not a regular file"`)
  and the assertion at `:1321`.
- `gh run list --branch main --limit 4` (2026-09-29): `.github/workflows/ci.yml`
  failure on `a5792f2`, `3c0b39a`, `a6f5af2`; success on `4f0ae00`.
- The rest of the suite is green: `uv run pytest --deselect <that test>` on
  `chore/p8-spec-batch` -> `5617 passed, 7 skipped`.

## How to pick it up
1. Read `_notice_guard_tracked_texts` and the test body
   (`tests/test_forbidden_strings.py` ~:1273-1330) and `_tracked_files`;
   check whether any other tracked-file walker (the purge guard cores, the
   release artifact scan in `scripts/check_artifacts.py`) has the same
   symlink blind spot -- the distribution spec already excludes the
   `agent-log` symlink from the sdist.
2. In a worktree, teach the guard that a tracked symlink whose resolved
   target is inside the repo and tracked is accounted for (its contents are
   scanned under the target's own paths), and that any other symlink is
   still reported. Name the mutation (drop the symlink branch -> the test
   reds on the 19 links) and a positive control (a synthetic out-of-repo
   link reds).
3. Full suite green locally, then push and confirm the CI run on `main` is
   green.

## Open questions
- Should `.agents/skills` stay symlinks at all (vs a generated copy with a
  byte-parity test, which is what the original change claimed to give)?

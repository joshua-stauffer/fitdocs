---
id: 2026-10-02-base-resolvers-is-file-choice-unpinned
title: The load, sync and performance archive resolvers use is_file() and no test puts a directory at an archive path for them
status: open
importance: low
importance_why: Swapping is_file() for exists() in any of them would turn a directory at fit-archive/<sha>.fit into a read error instead of "unresolvable", and nothing would fail.
effort: S
kind: gap
area: load-history, activity-identity, src/fitdocs/load/engine.py, src/fitdocs/sync.py, src/fitdocs/performance/engine.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: add one directory-at-the-archive-path case for each of load.engine._resolve_archive, sync._resolvable_source_archive (and the page-task member check at sync.py:1912) and performance.engine._resolve_pass_archive, modelled on tests/compose/test_archive.py::TestSkips::test_a_directory_at_the_archive_path_is_skipped [queue: .kiro/queue/2026-10-02-base-resolvers-is-file-choice-unpinned.md]"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/sync.py
  - src/fitdocs/performance/engine.py
  - src/fitdocs/compose/archive.py
  - tests/compose/test_archive.py
  - tests/performance/test_engine.py
  - .kiro/queue/2026-09-12-performance-benchmarks-minor-pin-gaps.md
blocked_by: []
---

## What
Every place that resolves a listed `fit-archive/<sha>.fit` ref to a file asks
`Path.is_file()`, so a directory sitting at that path counts as "not archived".
Only `compose/archive.py`'s own check is pinned for it. The three base
resolvers, which pick the file a page's load or benchmark pass (or regen) parses
as the base, are not.

## Why it matters
Changing `is_file()` to `exists()` in one of them would pass a directory at an
archive path on to `read_bytes()`, which fails there (by reading, not run)
instead of reporting the documented "unresolvable archive". No test would
notice. The shape is rare (a directory named like an archive file) but the
three resolvers are meant to agree, and they are only pinned to agree on a
traversal ref.

## Evidence
At 5c41759.
- `src/fitdocs/load/engine.py:660` `return archive if archive.is_file() else None`
  (`_resolve_archive`, `:632`).
- `src/fitdocs/performance/engine.py:297` the same line (`_resolve_pass_archive`,
  `:272`).
- `src/fitdocs/sync.py:2376` `if archive.is_file():` (`_resolvable_source_archive`,
  `:2351`) and `:1912` `not member_archive.is_file()` (the page task's member
  resolution).
- Pinned for the compose adapter only:
  `tests/compose/test_archive.py:98`
  `TestSkips::test_a_directory_at_the_archive_path_is_skipped`.
- `grep -rn "mkdir" tests --include='*.py' | grep -i archive` finds one
  directory made at a `<sha>.fit` name under `fit-archive/` outside the
  compose adapter's test: `tests/test_audit.py:911` (the orphan scan). It calls
  no resolver. The two-resolver equivalence tests
  (`tests/performance/test_engine.py:698-726`, `:1188-1237`) cover a traversal
  ref, not a directory.
- Overlap, deliberate: `.kiro/queue/2026-09-12-performance-benchmarks-minor-pin-gaps.md`
  bullet 2 already names "is_file vs exists on a directory-shaped <sha>.fit"
  for the performance resolver only. This item is the three-resolver version;
  close that bullet when this lands.

## How to pick it up
1. Read `tests/compose/test_archive.py::TestSkips` for the model: make the
   directory with `archive_path(root, sha).mkdir(parents=True)` and assert the
   resolver returns `None` (or the per-page result is the unresolvable-archive
   failure).
2. Add the case to the load engine, performance engine and sync (the regen path
   that calls `_resolvable_source_archive`, and a page task whose existing page
   lists a directory-shaped member).
3. Mutate `is_file()` to `exists()` in each resolver and confirm exactly its
   new case reds. Done when all four mutations red.

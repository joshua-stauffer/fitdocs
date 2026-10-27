---
id: 2026-10-27-noop-regen-rewrites-every-page
title: A no-change regen rewrites every workout page byte-identically, moving every page's mtime
status: open
importance: medium
importance_why: Defeats the point of write-if-changed for sync clients, backups and editors that watch mtimes; the cost grows with archive size (the maintainer has ~2.5k pages).
effort: S
kind: gap
area: workout-docs, src/fitdocs/sync.py
created: 2026-10-27
surfaced_by: /kiro-impl compact-chart-assets (task 6.2 review)
pinned_at: 260c3ff8
resume_command: "do: route sync._write_document through docio.write_bytes_if_changed (UTF-8 bytes) so unchanged pages keep their mtime, pin it, and check the ownership contract wording"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/docio.py
  - docs/ownership-contract.md
  - .kiro/specs/workout-docs/requirements.md
  - .kiro/specs/wiki-contract/requirements.md
blocked_by: []
---

## What
compact-chart-assets made every chart asset write-if-changed
(`sync._write_assets` → `docio.write_bytes_if_changed`), but the page itself
is still written unconditionally: `_write_document` calls
`document.write_text(markdown, encoding="utf-8")` (src/fitdocs/sync.py:2609-2612).
So after a no-change `fitdocs regen`, every page's content is unchanged but
its mtime moves.

## Why it matters
- iCloud, Obsidian Sync, git status, backup tools and file watchers all treat each page as changed on every regen.
- The CHANGELOG's Unreleased entry for compact-chart-assets correctly limits its "left untouched" promise to chart files. Users may still expect the same for pages.

## Evidence
- sync.py:2609-2612. Verified in this run.
- Reported by the 6.2 reviewer subagent, not reproduced by me: running sync then regen twice on a synthetic run moved only `workouts/<run>.md`'s mtime; the hero, map and AGENTS.md files did not move.

## How to pick it up
1. Check that the page write is not part of crash healing. The write order is assets → stale removal → move → document → archive, and the identity fault-injection test (tests/test_identity_e2e.py::test_a_fault_after_each_write_step_leaves_one_page_and_the_next_run_heals) must still pass.
2. Change `_write_document` to `write_bytes_if_changed(document, markdown.encode("utf-8"))`. Mirror tests/test_chart_asset_writes.py, using aged mtimes via `os.utime`.
3. Decide whether this is a contract guarantee. If it is, it needs a CONTRACT_VERSION bump plus wiki-contract and workout-docs amendments.
</content>
</invoke>

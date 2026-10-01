---
id: 2026-10-01-stale-facts-left-by-the-activity-identity-merge
title: 'Steering and a code comment state facts the activity-identity merge made false: deleted sync function names, a DOC_VERSION "current value", a tree-walk count'
status: open
importance: low
importance_why: Each sentence is guidance a later session will trust (the roadmap is the first file read), and each now sends the reader to a function that does not exist or a value that is wrong; none changes behavior.
effort: S
kind: docs
area: activity-identity, .kiro/steering/roadmap.md, src/fitdocs/sync.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "do: under the change ritual (steering is in scope), work the checklist in .kiro/queue/2026-10-01-stale-facts-left-by-the-activity-identity-merge.md -- replace the deleted function names in roadmap.md, reword its DOC_VERSION 'current value' sentences so they cannot go stale again, and correct the tree-walk count comment in sync.py"
context:
  - .kiro/steering/roadmap.md
  - src/fitdocs/sync.py
  - src/fitdocs/contract.py
blocked_by: []
---

## What
Three stale statements, one sitting. This is a checklist (the same shape as
`2026-09-29-stale-prose-batch-phase-8`), each line a separate fix:
1. `.kiro/steering/roadmap.md:1243` names `sync._discover_documents` as the
   workout-page discovery path, and `:1646` names `find_document` (236) and
   `_process_file` (1126) as the carriers of identity and base selection.
   `_discover_documents` and `_process_file` no longer exist; the scan is
   `identity.pages.scan_pages` and the per-page work is `sync._page_task` /
   `_run_planned` / `_process_isolated`.
2. `.kiro/steering/roadmap.md:510` says of `DOC_VERSION` "**the current value is
   4**". It is 7. The Phase 8 shared-surface list at `:1639-1641` also quotes
   `DOC_VERSION` (5, `contract.py:174`) and `CONTRACT_VERSION` ("4",
   `contract.py:275`); the planning snapshot is stale the same way.
3. `src/fitdocs/sync.py:521` (in `_scan_symlinked_documents`) says "This is the
   fifth `*.md` tree-walk in `src/`; the other four all exclude the declaration
   via `is_workout_document`". There are seven `workouts/*.md` globs.

## Why it matters
The roadmap is the document every session reads first, and a "current value" in
it that is three versions out of date, or a function name that does not resolve,
costs a verification detour each time. Comment 3 gives the wrong number to the
next person adding a scan.

## Evidence
Read at `fc5c06d`.
- `grep -n "def _discover_documents\|def _process_file" src/fitdocs/sync.py` -> no hits
  (`git log -S"def _discover_documents"` shows it removed in `1615e50`).
  `def regen` is `sync.py:1050`, `def _page_task` `:1776`, `def find_document` `:293`.
- `src/fitdocs/contract.py:182` `DOC_VERSION: Final[int] = 7`; `:309`
  `CONTRACT_VERSION: Final[str] = "5"`.
- `grep -rn 'glob("\*.md")' src` -> seven code sites: `sync.py:516`,
  `audit.py:583`, `identity/pages.py:83`, `plans/corpus.py:184`,
  `load/engine.py:613`, `history/documents.py:197`, `performance/engine.py:263`
  (the comment's count was already stale before this spec: it is present at the
  root commit).
- The older specs under `.kiro/specs/*/` also mention `_process_file`; they
  describe the code of their day and are not part of this fix.

## How to pick it up
1. Edit roadmap.md lines 1243 and 1646 to the current names, and give lines
   510 and 1639-1641 wording that cannot go stale (name the symbol and say "see
   `contract.py`" instead of quoting a number, or date-stamp the number).
   Steering edits are in the change ritual's scope; this queue skill does not edit
   the roadmap itself.
2. Fix the comment at `sync.py:521`: drop the count, or state it as "one of
   several `workouts/*.md` scans" and keep the reason the scan cannot use
   `is_workout_document`.
3. Done when `grep` finds none of the deleted names in `.kiro/steering/` or
   `src/` and no steering sentence states a `DOC_VERSION` / `CONTRACT_VERSION`
   value as current.

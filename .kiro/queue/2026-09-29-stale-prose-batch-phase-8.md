---
id: 2026-09-29-stale-prose-batch-phase-8
title: Four stale or misleading prose passages found by the Phase 8 spec writers -- settings-table docstrings, a changelog test docstring, the workout-docs offline objective, and structure.md's no-re-read rule
status: open
importance: low
importance_why: No behaviour is wrong; each sentence misdescribes the code to the next reader, and two of them sit where Phase 8 implementers will read first.
effort: S
kind: docs
area: src/fitdocs/settings.py, src/fitdocs/layout.py, tests/test_changelog.py, workout-docs, .kiro/steering/structure.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, activity-identity, connectors, running-dynamics and channel-merge writers)
pinned_at: f500dc1
resume_command: "do: under the change ritual (steering and spec docs are in scope), work the checklist in .kiro/queue/2026-09-29-stale-prose-batch-phase-8.md -- reword the settings.py and layout.py settings-table docstrings to not enumerate tables (or enumerate the live *_TABLE constants), drop the Unreleased-is-empty clause from tests/test_changelog.py's docstring, make workout-docs Requirement 14's objective say which commands reach the network, and qualify structure.md's no-re-read sentence for the load/benchmark passes; tick each box"
context:
  - src/fitdocs/settings.py
  - src/fitdocs/layout.py
  - tests/test_changelog.py
  - .kiro/specs/workout-docs/requirements.md
  - .kiro/steering/structure.md
  - .kiro/queue/2026-09-16-contract-version-docstring-ledger-incomplete.md
  - .kiro/queue/2026-09-12-ownership-contract-prose-stale-and-unpinned.md
blocked_by: []
---

## What
A checklist of one-sentence fixes. Two further passages the writers reported
already have open items and were appended there instead: the
`CONTRACT_VERSION` docstring ledger
(`2026-09-16-contract-version-docstring-ledger-incomplete`) and the
ownership contract's "future ingestion feature's quarantine record"
(`2026-09-12-ownership-contract-prose-stale-and-unpinned`).

- [ ] **Settings tables.** `src/fitdocs/settings.py:3-4` says "`[tiles]`
  lives there today, `[inbox]` and `[plugins]` join it";
  `src/fitdocs/layout.py:65-66` says "`[tiles]` today, `[inbox]` and
  `[plugins]` next". Six top-level tables ship today (`tiles`, `inbox`,
  `plugins`, `load`, `history`, `plans`; `grep -rn "_TABLE\b.*=" src/fitdocs`)
  and Phase 8 adds more. Prefer wording that does not enumerate.
- [ ] **Changelog test docstring.** `tests/test_changelog.py:649-651` --
  "`[Unreleased]` itself is now empty until the next round of work." True
  today (`CHANGELOG.md:16-18`), false the moment any spec adds an Unreleased
  entry, and every Phase 8 spec's tasks do. The test asserts only that the
  newest released section has `Added`; the docstring should say only that.
- [ ] **Workout-docs objective.** `.kiro/specs/workout-docs/requirements.md:224-226`
  -- Requirement 14's objective says "the tool works fully offline". Already
  inexact since basemap tiles are fetched over HTTPS (with an opt-out,
  `src/fitdocs/tiles.py`), and more so once `fitdocs pull` ships. It is an
  objective, not a criterion; reword to name which commands may reach the
  network.
- [ ] **structure.md no-re-read rule.** `.kiro/steering/structure.md:64-66`
  -- "renderers and calculators never re-read `.fit` files directly" sits in
  the dependency-direction bullet that channel-merge task 5.3 appends
  `compose` to. The load and benchmark passes already re-parse the archived
  base (`src/fitdocs/load/engine.py:468`,
  `src/fitdocs/performance/engine.py:366`) and after channel-merge compose
  extras through `compose.archive`. True to the letter (passes are not
  calculators) but reads as "nothing below the CLI reads archives"; name the
  passes as the sanctioned readers.

## Why it matters
Each sentence is the first thing a reader of that file sees about its
subject; the structure.md one is steering, loaded into every session.

## Evidence
Line references above, read at this pin. Reported by the Phase 8 spec
writers (2026-09-29); each re-verified against the tree before filing.

## How to pick it up
1. Re-grep each cited passage (lines drift, and the structure.md bullet will
   have `compose` appended once channel-merge lands).
2. Fix the code docstrings and the test docstring in one commit; the spec
   and steering edits follow change-protocol's class rules.
3. Done when every box is ticked; no test pins any of these sentences.

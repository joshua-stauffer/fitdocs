---
id: 2026-10-19-repo-docs-drift-after-phase-12
title: docs/ still says morning-of blocks are future work, and several path lists predate wellness, recovery and the index
status: open
importance: medium
importance_why: docs/ is the published contract the site links to; two sentences contradict shipped behavior and the uninstall list understates what stays on disk.
effort: S
kind: docs
area: docs/inbox.md, docs/ownership-contract.md, docs/install.md, docs/upgrading.md, docs/wiki-integration.md, docs/configuration.md
created: 2026-10-19
surfaced_by: 0.2 site-copy update (four fact-gathering subagents plus the session cross-checking docs/ against main)
pinned_at: 90cd00b
resume_command: "do: fix the eight docs/ sentences listed under Evidence in .kiro/queue/2026-10-19-repo-docs-drift-after-phase-12.md, moving any test pin that quotes them, then run uv run pytest tests/ -k 'docs or contract or install or upgrading' and the full suite"
context:
  - docs/inbox.md
  - docs/ownership-contract.md
  - docs/install.md
  - docs/upgrading.md
  - docs/wiki-integration.md
  - docs/configuration.md
  - src/fitdocs/layout.py
  - src/fitdocs/sync.py
blocked_by: []
---

## What
Several `docs/` pages were not updated as Phase 12 (wellness, recovery,
workout-wellness) and the analytics index landed. Two sentences say shipped
features "remain future work". Several path and table lists stop short of the
current set.

## Why it matters
- The site and the packaged skills point readers to `docs/` as the
  authority, and these sentences contradict what 0.2 ships.
- The uninstall list matters more than the rest: it is how a user learns
  what stays on disk. It omits `wellness/`, `wellness-archive/`, `recovery/`
  and the external analytics-index directory.

## Evidence
All checked at 90cd00b:
1. `docs/inbox.md:86-87`: "morning-of workout blocks remain future work".
   The block shipped; see `docs/wellness.md:322-341`.
2. `docs/ownership-contract.md:142-143`: "recovery pages and morning-of
   workout blocks remain future work". Both shipped; see the contract's own
   Recovery Page and Morning-Of Region sections.
3. `docs/install.md:115-117`: "each of the five declared directories —
   `workouts/`, `fit-archive/`, `history/`, `blocks/`, and `dashboards/`".
   There are eight (`src/fitdocs/layout.py:204-213`), and a first
   `fitdocs sync` into an empty data root creates all eight `AGENTS.md`
   files (observed in a scratch data root this session).
4. `docs/upgrading.md:162-166` and `:176-188` ("What remains on disk after
   uninstalling"): the owned-path list and the bullet list omit `wellness/`,
   `wellness-archive/` and `recovery/`. Neither mentions the analytics-index
   directory outside the data root (`docs/analytics.md`, "Where the index
   lives") or the connector credentials directory (`docs/connectors.md`,
   "Credentials").
5. `docs/ownership-contract.md:864-866` lists the `fitdocs.toml` tables
   without `[wellness]` (documented at `docs/configuration.md:246`).
6. `docs/wiki-integration.md:156-157`: "`workouts/` now holds one generated
   document per drained `.fit` file". Since activity identity, several files
   of one workout share one page.
7. `docs/configuration.md:98`: tiles are fetched "only during
   `sync`/`regen`". `fitdocs pull --sync` runs the same drain and draws maps
   too (`docs/connectors.md`, Pulling, `--sync`).
8. `docs/ownership-contract.md:18-24`: the generated `AGENTS.md` files are
   placed by "each of those four commands" (sync, regen, history, plan).
   `fitdocs recovery` also calls `ensure_declarations`
   (`src/fitdocs/recovery/engine.py:177`), and `src/fitdocs/contract.py:471`
   tells users to run it "to place `recovery/AGENTS.md`".

Also: `docs/upgrading.md` (the rename paragraph, ~:117-127) never says that
training-plan overrides naming a renamed page's old stem need updating. The
rename warning itself says so (`src/fitdocs/sync.py:2008-2012`: "plan
overrides naming the old stem need updating").

## How to pick it up
1. Edit each sentence above to match current behavior.
2. Grep `tests/` for each old literal before changing it. Several docs
   sentences are pinned (e.g. `tests/test_ownership_contract.py`,
   `tests/test_install_docs.py`). Move each pin together with its sentence.
3. Done when the eight items read true and the suite is green.

The `.gitattributes` example in the contract is tracked separately, in
`2026-09-12-ownership-contract-prose-stale-and-unpinned`.

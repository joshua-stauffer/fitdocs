---
id: 2026-09-10-load-history-three-seams-split-or-accept
title: Cross-spec review says load-history bundles three seams (owned location + contract bump, the cited model, the pass) — split, or accept with reason
status: open
importance: medium
importance_why: Decides whether the ownership-contract version and the history/ owned path wait for the whole history feature; the spec has not started implementation, so deciding now is cheapest.
effort: M
kind: spec-work
area: load-history, .kiro/steering/roadmap.md
created: 2026-09-10
surfaced_by: /kiro-spec-batch cross-spec review (Phase 6)
pinned_at: 1089b92
resume_command: "do: maintainer decision — either (a) record an accepted-with-reason line under roadmap Phase 6 › Boundary Strategy keeping load-history as one spec, or (b) add a history-location spec to the roadmap owning layout/declaration/confinement/CONTRACT_VERSION and re-run /kiro-spec-tasks load-history with task group 1 removed and a dependency on it; see Open questions for the recommendation"
context:
  - .kiro/specs/load-history/design.md
  - .kiro/specs/load-history/tasks.md
  - .kiro/steering/roadmap.md
  - .kiro/specs/wiki-contract/design.md
blocked_by: []
---

## What
The Phase 6 cross-spec reviewer found that `load-history` carries three
independently reviewable seams in one spec:
1. the new owned data-root location — `layout.OWNED_PATHS`/`DECLARED_DIRS`,
   the `declaration_text` restructure, a third `AGENTS.md` golden,
   `docs/ownership-contract.md`, the confinement guard, and the
   `CONTRACT_VERSION` bump (a wiki-contract-class change);
2. the cited fitness/fatigue/form model — sources, recursion, constant guard,
   worked-example vectors (a citation-discipline change, no filesystem);
3. the pass — documents → series → weeks → coverage → criterion points →
   chart → page → command → guards.
The spec's own task graph already isolates seam 1 as task group 1, "one
atomic change" with its own red window.

## Why it matters
As one spec, the published contract version and the `history/` owned path
land only when the whole feature is ready, and the reviewer of seam 1
(ownership prose, goldens, confinement) is a different reviewer from seam 2
(citation records, numeric vectors). The roadmap fixed load-history as one
spec at discovery (Phase 6 › Constraints: "`load-history` adds one, and
every guard moves in the same change"), so changing that is a roadmap
decision, not a fix a spec pass may take unilaterally.

## Evidence
- `.kiro/specs/load-history/design.md` — ~1,600 lines, 16 components;
  `spec.json.phase_note` accepts the length.
- `.kiro/specs/load-history/tasks.md` task group 1 (tasks 1.1–1.3) — the
  "one atomic change" wording and the group's own red window.
- `.kiro/steering/roadmap.md` Phase 6 › Constraints, the data-root sentence
  quoted above, and › Boundary Strategy, which lists `layout.py` + the
  confinement guard under load-history's shared seams.
- Cross-spec review report, Phase 6 batch, 2026-09-10 (this session).

## How to pick it up
1. Read task group 1 of load-history's tasks.md and the roadmap's Boundary
   Strategy for Phase 6.
2. Decide (a) or (b) from the resume command.
3. For (a): one roadmap sentence, committed via the steering ritual. For
   (b): `/kiro-spec-init history-location`, then regenerate load-history's
   tasks in merge mode with group 1 removed and `Dependencies:
   history-location` added; effort-tags is unaffected either way.

## Open questions
The batch controller's recommendation is (a): an owned path with no producer
is a contract claim about nothing, and the intermediate state (b) creates —
`history/` declared and versioned, nothing writing to it — is the state the
ownership contract exists to rule out. Group 1 already lands first inside
the spec's task order. The maintainer may weigh reviewer specialisation
higher.

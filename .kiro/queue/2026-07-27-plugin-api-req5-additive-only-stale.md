---
id: 2026-07-27-plugin-api-req5-additive-only-stale
title: plugin-api Req 5.4-5.6 still promise additive-only changes within 0.x; the shipped docs say unstable pre-1.0
status: open
importance: medium
importance_why: The requirements are the approved contract, and they now promise a stability guarantee the shipped documentation explicitly disclaims. A plugin author reading the spec and a plugin author reading the docs get different answers about whether their calculator can break.
effort: S
kind: inconsistency
area: plugin-api, .kiro/specs/plugin-api/requirements.md
created: 2026-07-27
surfaced_by: adversarial review of impl/plugin-api-surface (queue sweep 2026-07-27)
pinned_at: c3d2201
resume_command: "do: reconcile plugin-api requirements.md Req 5 acceptance criteria 4-6 ('shall introduce contract changes only additively' within 0.x) with the unstable-pre-1.0 statement the roadmap ratified and docs/plugins.md:291-300 now carries — this is a criterion change to an approved spec, so record it as a proper amendment rather than an in-place edit [queue: .kiro/queue/2026-07-27-plugin-api-req5-additive-only-stale.md]"
context:
  - .kiro/specs/plugin-api/requirements.md
  - docs/plugins.md
  - .kiro/specs/plugin-api/design.md
  - .kiro/steering/roadmap.md
blocked_by: []
---

## What

`.kiro/specs/plugin-api/requirements.md` Req 5, acceptance criteria 4-6, still
encode the additive-only-within-0.x promise: the surface "shall introduce
contract changes only additively" during the 0.x series.

That promise was ratified away. `docs/plugins.md:291-300` now carries the
unstable-pre-1.0 wording (landed by `training-load` task 5.2, commit
`a9a914d`), and `plugin-api/design.md` was reconciled to match in the
2026-07-27 queue sweep. The requirements copy was never moved.

## Why it matters

Requirements are the approved contract; docs are its rendering. Right now they
disagree about the single question a plugin author most needs answered — can
the calculator I write today break before 1.0? The spec says no, the shipped
documentation says yes.

It also matters for how it gets fixed. Every other copy of this rule moved
under a *decision* (the roadmap ratification). Editing the requirements in
place would make the approved criteria drift silently behind a decision they
never recorded, which is the pattern `change-protocol.md` treats as
non-trivial by definition — a criterion change needs an amendment record, not
a wording tidy.

## Evidence

Identified by the adversarial reviewer of `impl/plugin-api-surface`
(2026-07-27), follow-up 2, comparing:

- `.kiro/specs/plugin-api/requirements.md` Req 5 acceptance criteria 4, 5, 6 —
  "shall introduce contract changes only additively"
- `docs/plugins.md:291-300` — the unstable-pre-1.0 statement

Provenance of the doc change, verified during that review:
`git log -S "this surface is unstable and carries no" -- docs/plugins.md`
returns exactly `a9a914d`, whose message opens "Task 5.2".

## How to pick it up

1. Read Req 5's full acceptance criteria and `docs/plugins.md:291-300` side by
   side, then `.kiro/steering/roadmap.md` for the ratification that settled it.
2. Confirm nothing else still promises additive-only —
   `grep -rn "additively\|additive-only" .kiro/ docs/ src/`.
3. Record it as an amendment to plugin-api with a revision entry, following how
   Amendments are recorded in the sibling specs (`fit-ingest` and
   `training-load` both have worked examples). Do not edit the criteria in
   place without the record.
4. `/kiro-spec-status plugin-api` clean, and `spec.json` approvals reflecting
   what actually happened — a criterion change means the requirements approval
   is in play, which is the maintainer's call, not the session's.

Related: `.kiro/queue/2026-07-27-design-md-enumeration-unguarded.md` covers the
guard gap that let the sibling enumeration drift three times.

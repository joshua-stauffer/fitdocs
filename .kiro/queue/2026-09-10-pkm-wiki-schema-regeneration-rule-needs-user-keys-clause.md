---
id: 2026-09-10-pkm-wiki-schema-regeneration-rule-needs-user-keys-clause
title: pkm wiki-schema.md's regeneration rule needs a user-owned-keys clause, and its athlete.toml line is already wrong
status: open
importance: medium
importance_why: The PKM schema is what other tools and agents in the wiki read as the rule; it will contradict fitdocs on two points once effort-tags ships, and on one point already.
effort: S
kind: docs
area: effort-tags, external ~/code/pkm/wiki-schema.md
created: 2026-09-10
surfaced_by: /kiro-spec-batch (effort-tags design, wave 1)
pinned_at: 1251a98
resume_command: "do: in ~/code/pkm/wiki-schema.md (Editing rules, near line 707) amend the regeneration sentence so user-owned frontmatter keys (effort, effort_distance_m, effort_time_s, effort_event) are named as preserved, and correct the athlete.toml line so it says fitdocs also writes it (prompt-answered benchmarks today; derived benchmarks once performance-benchmarks ships)"
context:
  - .kiro/specs/effort-tags/design.md
  - .kiro/specs/wiki-contract/design.md
  - docs/ownership-contract.md
blocked_by: []
---

## What
The reference PKM's schema (joshua-stauffer/pkm, `wiki-schema.md`) states two
things fitdocs no longer honours or will stop honouring:
1. "Everything outside a document's region markers is replaced on
   regeneration" — false once effort-tags preserves user-owned keys.
2. "`wiki/athlete.toml` and `wiki/fitdocs.toml` are user-owned: fitdocs only
   reads them" — already inaccurate: training-load's prompt path writes
   prompt-answered benchmarks into `athlete.toml`, and performance-benchmarks
   will write derived entries.

## Why it matters
Agents and tools operating on the wiki treat the schema as the contract. A
schema that says the tag is discarded invites a second tag store somewhere
else, which is exactly the duplication effort-tags exists to prevent.

## Evidence
- `~/code/pkm/wiki-schema.md:706` — the "fitdocs only reads them" sentence.
- `~/code/pkm/wiki-schema.md:708-709` — the regeneration sentence.
- effort-tags `design.md` (commit c574cfb on `chore/spec-batch-phase6`) —
  the user-owned key class and its preservation rule.

## How to pick it up
1. Fix point 2 now; it is true today.
2. Fix point 1 in the same edit but phrase it as "from fitdocs contract
   version 2", or hold it until effort-tags merges — maintainer's call.
3. This file is outside this repo: no worktree ritual applies, but note the
   edit in the shared agent log so the next fitdocs session knows the schema
   moved.

## Open questions
Whether the pkm schema should name the four keys or point at fitdocs'
`docs/ownership-contract.md` as the single source.

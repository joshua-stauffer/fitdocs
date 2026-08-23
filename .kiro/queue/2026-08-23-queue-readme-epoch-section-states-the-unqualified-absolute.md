---
id: 2026-08-23-queue-readme-epoch-section-states-the-unqualified-absolute
title: The queue README's epoch-pin convention states "permanently unresolvable" unqualified, the exact claim Req 9.3 and the provenance record were scoped away from
status: open
importance: medium
importance_why: Req 9.3 was textually amended and the provenance record rewritten precisely because the unqualified form is false — the retained fitdocs_oss still serves 7 of 8 sampled identifiers. The README now carries the falsehood the rest of the spec was corrected to avoid, and the record paraphrases it with a scope it does not have.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/queue
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge tasks 9.1 and 9.2 (two independent reviewers)
pinned_at: c786326
resume_command: "do: scope the queue README's epoch-pin convention sentences to this repository and its canonical remote, matching the amended Req 9.3 and the provenance record's section 3"
context:
  - .kiro/queue/README.md
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/requirements.md
blocked_by: []
---

## What

`.kiro/queue/README.md`'s "The epoch pin convention" section, landed at task
9.1, states the absolute twice:

- `:94` — "original pin is permanently unresolvable — never a claim that
  `c3d2201` is …"
- `:103` — "identifier is permanently unresolvable."

Task 9.2 then amended **Req 9.3** in place, and rewrote the provenance record's
sections 3, 6 and 7, specifically to scope that claim to *"the fitdocs
repository and its canonical remote"*.

## Why it matters

The unqualified claim is **measurably false**. Task 8.4's per-identifier probes
found the retained `fitdocs_oss` still serves **7 of 8** sampled pre-replacement
identifiers, and it is retained permanently under Amendment 3. Every one of
those identifiers resolves today, in a repository that still exists.

That is exactly why Req 9.3 was amended rather than read charitably —
`design.md`'s Amendment 3 states the principle: *"A requirement that has to be
read charitably to stay satisfied is a requirement that needs amending."*

Two consequences:

1. The README is a **schema document** other sessions read to learn what a pin
   means. It now teaches the claim the spec was corrected away from.
2. The provenance record's section 6 **describes** the README as documenting
   "permanently unresolvable **in this repository**" — a scope the README does
   not carry. So the record makes a checkable claim about the README that the
   README falsifies.

Both task 9.1's and task 9.2's reviewers flagged this independently.

## Evidence

```
$ grep -n "permanently unresolvable" .kiro/queue/README.md
94:original pin is permanently unresolvable — never a claim that `c3d2201` is
103:identifier is permanently unresolvable.
```

- Amended Req 9.3 carries the scope:
  `.kiro/specs/encumbered-content-purge/requirements.md`, Requirement 9,
  criterion 3 (landed `881e564`)
- The record's scoped form and its claim about the README:
  `docs/reference/history-rewrites.md` sections 3 and 6
- The 7-of-8 measurement: record section 7 (the probe table itself was
  destroyed at task 9.4, its results reproduced in the record)

## How to pick it up

Open `.kiro/queue/README.md` at the epoch-pin convention section. Add the same
scope the amended Req 9.3 uses — "in this repository and its canonical remote"
— to both sentences.

Then re-read the record's section 6 sentence describing the README and confirm
it is now true of what the README says. That sentence is the reason this is an
inconsistency rather than a wording preference.

Do not change the convention itself: `c3d2201` as the epoch value, applied
uniformly with no per-item judgement, is correct and is pinned by 190 open
items. Only the claim *about what the pin means* needs its scope.

Done when both sentences carry the scope and the record's description of them
is true.

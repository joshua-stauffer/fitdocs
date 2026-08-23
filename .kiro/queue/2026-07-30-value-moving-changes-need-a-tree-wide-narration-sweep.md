---
id: 2026-07-30-value-moving-changes-need-a-tree-wide-narration-sweep
title: Nothing enumerates the files that narrate a value-moving change, so every sweep is scoped narrower than the defect class
status: open
importance: high
importance_why: Four consecutive review rounds each found a fresh false sentence about the same change, and the one that survived all four was never reachable by any of them — every sweep was scoped to one directory while the class spans steering, specs, docstrings and the queue. Reading harder has now failed four times; the boundary, not the care, is what is wrong.
effort: M
kind: gap
area: tooling, .kiro/steering/change-protocol.md, .claude/hooks
created: 2026-07-30
surfaced_by: adversarial review of spec/fit-ingest-np-window-criterion, round 3 (queue-tier1 batch)
pinned_at: c3d2201
resume_command: "do: design a tree-wide narration sweep for value-moving changes -- enumerate every file that describes a metric's behaviour (steering, specs, src docstrings, docs/, queue) so a change that moves a number can be checked against all of them at once, and consider whether change-guard.py can enforce it mechanically [queue: .kiro/queue/2026-07-30-value-moving-changes-need-a-tree-wide-narration-sweep.md]"
context:
  - .kiro/steering/change-protocol.md
  - .claude/hooks/change-guard.py
  - .claude/hooks/queue-guard.py
  - .kiro/steering/roadmap.md
  - src/fitdocs/contract.py
blocked_by: []
---

## What

When a change moves a reported value, the repo requires the prose describing
that value to be corrected along with it. Nothing enumerates *which* prose. In
practice each session sweeps the directory it happens to be working in, and the
defect class is wider than any one directory.

Task 13.1's normalized-power change is the worked example. The class is "a
sentence asserting a direction or consequence of the complete-window change",
and instances were found in:

- `.kiro/specs/fit-ingest/tasks.md`
- `.kiro/specs/fit-ingest/design.md` (four separate sites)
- `.kiro/specs/fit-ingest/research.md`
- `.kiro/specs/fit-ingest/requirements.md`
- `.kiro/specs/fit-ingest/spec.json`
- `.kiro/steering/roadmap.md`

Every sweep run against it — by two implementers and one reviewer, across three
rounds — was scoped to `.kiro/specs/fit-ingest/`. The `roadmap.md` instance was
therefore unreachable by all of them, and was found only when a reviewer
searched outside its own review boundary on the fourth pass.

## Why it matters

The per-round defect count went 5 → 3 → 1, which looks like convergence but is
not: the survivor was never in the search space. Another round of the same kind
would not have found it.

The `roadmap.md` instance is the worst possible location for it. `CLAUDE.md`
instructs every session to load `.kiro/steering/` as project memory, so a false
sentence there is read by every future session before it does anything — and
this one sat eight lines above its own contradiction ("53 rose and 1 fell").

The decisive evidence that this is a boundary problem and not a diligence
problem: **`src/fitdocs/contract.py:158-176` has carried the correct
formulation the entire time** — *"It is not a universal change: on a
constant-power stream… old and new NP coincide"*. The right knowledge was in
the repo from the start. What was missing was any way to enumerate every place
that repeats it.

This will recur on the next value-moving change, and the queue already shows
the same shape elsewhere: guards, records and docstrings that narrate behaviour
drift from it silently because nothing ties the narration to the thing narrated.

## Evidence

From the round-3 review at `e04af78`:

```
.kiro/steering/roadmap.md:585
  "...the design-gate ruling that normalized power emit only complete rolling
   windows (task 13.1), which raises NP and with it IF, VI, TSS and bike EF."

.kiro/steering/roadmap.md:594-595   (eight lines below)
  "53 rose and 1 fell -- a hard opener... That single faller falsifies the
   unconditional direction claim tasks.md still makes"
```

The first sentence is the falsehood the closed queue item
`2026-07-30-np-direction-claim-is-conditional` is titled after. The second is a
self-invalidation created by the very change that corrected `tasks.md`, plus a
queue path that now dangles.

Round-by-round defect counts on the same class, all found by reading:
round 1 → 5 instances, round 2 → 3, round 3 → 1 (and that one only from outside
the search boundary).

## How to pick it up

1. Decide what "narrates a metric" means concretely, because that is the whole
   problem. Candidates: `.kiro/steering/**`, `.kiro/specs/*/{requirements,design,research,tasks}.md`
   and `spec.json`, `src/fitdocs/**` module and function docstrings,
   `docs/reference/**`, and open `.kiro/queue/**`.
2. The cheap version is a checklist in `.kiro/steering/change-protocol.md` under
   the value-moving change class — an enumeration a session must walk, not a
   grep it must run. Note that the mandated `-E` prose grep is documented in
   this repo as having "matched 6 claims, all 6 true, and missed all 4 false
   ones", so a keyword grep is known not to work for this class.
3. The durable version is mechanical: `.claude/hooks/change-guard.py` already
   intercepts changes and classifies them. A change touching a metric constant
   or a `CitedConstant` value could require the session to name which narrating
   files it checked, the way `queue-guard.py` requires queue entries.
4. Done looks like: a session making a value-moving change is told, before it
   finishes, every file that describes the value it moved — and a reviewer can
   check that list rather than re-deriving the search boundary.

## Open questions

- Should this bind at the *change* level (any diff touching a metric constant)
  or the *value* level (a registry mapping each `CitedConstant` to the files
  that narrate it)? The second is stronger and much more work.
- Does the same mechanism generalise beyond metrics? The identical failure —
  prose drifting from the artifact it describes — has now appeared in this
  batch on guards, citation records and test docstrings.

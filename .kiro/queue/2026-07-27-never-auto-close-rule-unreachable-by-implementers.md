---
id: 2026-07-27-never-auto-close-rule-unreachable-by-implementers
title: The never-auto-close rule lives only in kiro-queue's SKILL.md, which implementers never read — three broke it in one day
status: open
importance: medium
importance_why: Three independent implementer sessions self-closed queue items on 2026-07-27, each reversed in review. Every one was working from a queue item's own resume_command and never invoked kiro-queue, so the rule was not reachable from where they were standing. A rule that only exists where the people bound by it do not look is not a rule.
effort: S
kind: gap
area: .claude/skills/, .kiro/queue/README.md
created: 2026-07-27
surfaced_by: /kiro-queue sweep of the top ten items (2026-07-27)
pinned_at: c3d2201
resume_command: "do: put the never-auto-close rule where implementers actually read — .kiro/queue/README.md's item format section and the resume_command contract — rather than only .claude/skills/kiro-queue/SKILL.md:157 and :62, and consider whether queue-guard.py can detect a session that git mv'd an item into .kiro/queue/closed/ without the human having asked [queue: .kiro/queue/2026-07-27-never-auto-close-rule-unreachable-by-implementers.md]"
context:
  - .claude/skills/kiro-queue/SKILL.md
  - .kiro/queue/README.md
  - .claude/hooks/queue-guard.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`.claude/skills/kiro-queue/SKILL.md` states the rule twice — at `:62`
("**Never auto-close.** Closing is the human's call; this skill proposes") and
again at `:157` in the Constraints section. It appears nowhere else.

On 2026-07-27 a single queue sweep dispatched implementers against ten ranked
items. **Three of them closed their own queue item** — `git mv` into
`.kiro/queue/closed/` with `status: done`:

- `chore/protocol-purity-audit`
- `chore/amendment-1-count`
- `chore/citation-vocabulary-unify`

All three were reversed during review. None had invoked `/kiro-queue`; each was
working from an item's `resume_command`, so `SKILL.md` was never in its
context. Two of them wrote thoughtful resolution notes and *then* closed the
item — they were being conscientious, not careless.

Worth noting on the other side: two implementers in the same sweep
(`impl/devfield-declared-scale`, `impl/load-second-reader`) explicitly did NOT
close theirs and said why, one of them citing the shared agent log's warning
about the peers who had. So the rule does reach some sessions — via the log,
not via the skill.

## Why it matters

The rule exists for a reason that the sweep demonstrated twice over. In the
`amendment-1-count` case the self-close specifically removed the human's
opportunity to rule on an open question the item itself had posed (whether a
dated `amendments[0].reason` record may be edited in place). In the
`citation-vocabulary-unify` case the item was closed while still unmerged, and
its second open question — which spec owns the citation vocabulary — was
declared "unaffected" rather than answered, so closing would have buried a
genuinely open decision.

An item closed early is worse than an item left open: `/kiro-queue` reads
`.kiro/queue/` to rank work, so a premature close removes the item from every
future ranking without anyone having decided it is done.

The generalisable point: this repo already treats prose that instructs an agent
as behavior. A behavioral rule placed only in the skill that *proposes* closes,
rather than in the artifact that *receives* them, is unreachable from the path
implementers actually take.

## Evidence

Shared agent log, 2026-07-27:

```
2026-07-27T06:06:53Z  queue-sweep-0727  WARN  ... two implementers auto-closed
their own queue items (protocol-purity, amendment-1) contrary to kiro-queue's
never-auto-close rule; under review
```

Reversals confirmed in review, each verified back to `.kiro/queue/` at
`status: open`:

- `2026-07-26-protocol-purity-guards-miss-annotations.md`
- `2026-07-26-amendment-1-constant-count-ambiguous.md`
- `2026-07-26-citation-vocabulary-diverges-across-layers.md`

Rule sites, both inside the skill: `.claude/skills/kiro-queue/SKILL.md:62`,
`:157`. `grep -rn "auto-close\|never close" .kiro/ CLAUDE.md` finds nothing
outside that file.

Note `.claude/hooks/queue-guard.py` already enforces the *opposite* direction
(that surfaced work gets written to the queue). Nothing watches the closing
direction.

## How to pick it up

1. Read `.claude/skills/kiro-queue/SKILL.md:55-70` and `:140-160` for the rule
   as written, and `.kiro/queue/README.md` for what an implementer actually has
   in front of them.
2. Put the rule in `README.md` — both in the item-format section and wherever
   the `resume_command` contract is described, since that is the field that
   carries a session into an item.
3. Consider a `queue-guard.py` branch: a session that moved a file into
   `.kiro/queue/closed/` gets a nudge asking whether the human confirmed. Read
   `.kiro/steering/concurrency.md` first — advisory, never a gate on a claim.
   Note the existing hook's escape hatch pattern for trivial changes.
4. Every copy of the rule moves in the same change, per change-protocol.md's
   steering validation row.

Done looks like: an implementer that never opens `kiro-queue/SKILL.md` still
encounters the rule before it can act on an item.

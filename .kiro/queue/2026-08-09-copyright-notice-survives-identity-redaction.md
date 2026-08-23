---
id: 2026-08-09-copyright-notice-survives-identity-redaction
title: Req 11.4 — the copyright and trademark notices survive the rewrite with the name redacted, and nobody has decided whether that satisfies the requirement
status: open
importance: medium
importance_why: Req 11.4 forbids any file containing the third party's copyright or trademark notice. After redaction the notice text remains with the name replaced; whether that discharges the requirement is a judgement no task has made, and it cannot be revisited after the one-shot rewrite.
effort: S
kind: gap
area: encumbered-content-purge, Req 11.4
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (task 6.4 review, measured in a genuinely rewritten clone)
pinned_at: c3d2201
resume_command: "do: Decide whether Req 11.4 is satisfied by redacting the name inside the copyright and trademark notices, or whether the notice text itself must be removed from history, and record the decision before task 7.2 runs."
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Req 11.4 states that no file shall contain the third party's copyright notice
or trademark notice.

The replacement rules redact the *name* inside those notices but leave the
notice text standing. Measured by running the real `git filter-repo` on a
throwaway clone of the current history:

- the notice `<copyright sign> 2026 the third party. <reserved-rights
  phrase>` survives **42 times**
- the trademark mark survives **16 times**

So after the rewrite the history still carries a copyright assertion and a
trademark mark; what it no longer carries is the name of who holds them.

## Why it matters

Two readings, and the spec does not choose between them:

1. The requirement is about **identity** — the notice without an identifiable
   holder no longer attributes anything to the third party, so redacting the
   name discharges it.
2. The requirement is about the **notice** — a surviving reserved-rights
   line is still a third party's copyright notice reproduced in this
   repository, and it must go.

This is a judgement about what the requirement means, not a defect in the
rules. It needs making **before** task 7.2, because the one-shot rewrite is the
only opportunity to remove the notice text from history, and 8.3 validates
against Req 11.4 after 7.4 has destroyed the original repository.

## Evidence

Measured in a genuinely rewritten repository (real `git filter-repo` run on a
`--mirror` clone, then scanned), not predicted from the rule set:

- the notice `<copyright sign> 2026 <redacted>. <reserved-rights phrase>` —
  42 occurrences
- the trademark mark — 16 occurrences

Related, and probably the same decision: 556 sites where a redacted path
fragment in prose now reads with a space, e.g.
`docs/reference/the third party-point-system.md`, and
`!src/fitdocs/load/the third party/data/*.csv` in a historical `.gitignore`.
Cosmetic, but it is the same "the redaction landed inside a structured string"
family and is equally unrevisitable afterwards.

## How to pick it up

Read Req 11.4 as written, decide which reading governs, and record the decision
in the requirement or in `docs/reference/history-rewrites.md` so 8.3's
validation has something to check against.

If the notice text must go, the rules need an additional pattern before 7.2
runs, and the 556 prose-path sites deserve a decision at the same time.

Done when the reading is written down and, if it requires new rules, those
rules exist and are verified in a rewritten clone.

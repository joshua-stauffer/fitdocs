---
id: 2026-07-31-queue-frontmatter-values-unvalidated
title: Nothing validates queue frontmatter values, and one item carries a branch name where the schema requires a commit SHA
status: open
importance: medium
importance_why: A pinned_at that is not a SHA silently breaks /kiro-queue's own resume mechanic, and the tooling reports nothing when it happens.
effort: S
kind: gap
area: .kiro/queue/, .claude/skills/kiro-queue/, .claude/hooks/queue-commit-guard.py
created: 2026-07-31
surfaced_by: /kiro-spec-design encumbered-content-purge (inventorying the 163 pinned_at fields for the rewrite's reference-repair design)
pinned_at: ca1d876
resume_command: "do: add a validator over .kiro/queue/**/*.md frontmatter — at minimum that pinned_at resolves as a commit and that kind is one of the seven values README.md documents — then fix the two violations in .kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md [queue: .kiro/queue/2026-07-31-queue-frontmatter-values-unvalidated.md]"
context:
  - .kiro/queue/README.md
  - .kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md
  - .claude/skills/kiro-queue/SKILL.md
  - .claude/skills/kiro-queue-add/SKILL.md
  - .claude/hooks/queue-commit-guard.py
blocked_by: []
---

## What

`.kiro/queue/README.md` documents a frontmatter schema — `pinned_at` is a
"short commit SHA", `kind` is one of seven enumerated values — and nothing
checks either. The queue has a hook (`queue-commit-guard.py`) and a test
(`tests/test_queue_commit_guard.py`), but they guard *committedness*, not
field values. One item already violates the schema in two ways, and it was
found only because an unrelated spec had to enumerate every pin in the
repository.

## Why it matters

`pinned_at` is the only queue field any tooling resolves as a commit:
`.claude/skills/kiro-queue/SKILL.md:65` runs
`git log --oneline <pinned_at>..HEAD -- <context paths>` to show a picking-up
session what landed since the evidence was gathered. When the value is not a
commit that command produces nothing useful, and the session gets no signal
that the field was malformed rather than the delta being empty — it reads as
"nothing changed". The failure is silent in exactly the situation the field
exists to serve.

The `kind` violation is milder but the same shape: `/kiro-queue` ranks on
these fields, and an out-of-enum value is not a category anything sorts.

## Evidence

`.kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md`
carries both violations:

- line 12: `pinned_at: spec/fit-ingest-primary-sourcing` — a branch name, not a
  short SHA. **That branch no longer exists**, so the pin is already
  unresolvable today, independently of any history rewrite:

  ```
  $ git branch -a --list 'spec/fit-ingest*'
  (no output)
  ```

- line 8: `kind: spec` — not one of the seven values `README.md:74` permits
  (`bug` `inconsistency` `gap` `chore` `research` `docs` `spec-work`).
  `spec-work` is the legal spelling.

Scope of the field, measured at `ca1d876` (before this item itself was
written):

```
$ grep -rl 'pinned_at:' .kiro/queue/ | wc -l
     163
```

163 files carry `pinned_at` — 111 open items, 51 closed, plus the schema
example in `README.md:40`. **162 of the 163 hold a 7-character hex value**
(76 distinct); the file above is the sole exception. Every one of those 76
distinct SHAs resolves (`git cat-file -e <sha>^{commit}` → 76/76 exit 0), so
the branch-name value is the **only** pre-existing breakage in the field —
which is why a validator would be cheap to satisfy today and expensive to
retrofit after it drifts further.

No guard exists: `grep -rn pinned_at tests/ src/ .claude/hooks/` returns
nothing — the only two hits anywhere are the two skill documents that *consume*
the field.

## How to pick it up

1. Read `.kiro/queue/README.md` §Fields — it is the authoritative schema, and
   the validator should be derived from it rather than from the items.
2. Read `tests/test_queue_commit_guard.py`. It is the model: it states the one
   property its hook exists to have, and it deliberately varies the transcript
   and shared log to prove the verdict depends only on the working tree. A
   frontmatter validator wants the same treatment — and note its lesson that
   the verdict must not depend on session-scoped state.
3. Decide where the check belongs. A pytest guard over `.kiro/queue/**/*.md` is
   the cheapest and matches how the repo pins other documentation invariants;
   a `Stop` hook would catch it at write time but adds a fourth queue hook.
   Whichever, `pinned_at` resolution must degrade gracefully when `.git` is
   absent (an sdist-based run has no history), the way
   `tests/test_cli_drain_report.py` vendors its baseline rather than resolving
   a commit at test time.
4. Fix the two violations in the file above — but see the open question first.

**Done** means: a malformed `pinned_at` or an out-of-enum `kind` reds the
suite, with a named mutation showing the guard can fail (add a bad value,
observe red, revert — through `uv run pytest`, per
`.kiro/steering/change-protocol.md` § Fixture Discrimination), and the two
existing violations are resolved or explicitly exempted.

## Open questions

- **Is a branch name ever a legitimate `pinned_at`?** The item that uses one
  was pinned to work in flight on a branch rather than to a landed commit,
  which is a real situation `/kiro-queue-add` can find itself in. Either the
  schema widens to permit it (and the skill's `git log` consumer learns to
  handle it), or it stays SHA-only and `/kiro-queue-add` is told to resolve the
  branch to its tip at write time. Do not just overwrite the value without
  deciding which.
- **What should the fix be for a *closed* item?** `encumbered-content-purge`'s
  design (`.kiro/specs/encumbered-content-purge/design.md` › ReferenceRepair)
  records this specific pin as **unresolvable** under its Req 9.8 — its rule is
  to record rather than substitute a plausible commit. A validator added after
  that purge lands must not contradict that record; the honest outcome is
  probably an explicit exemption naming why, not an invented SHA.

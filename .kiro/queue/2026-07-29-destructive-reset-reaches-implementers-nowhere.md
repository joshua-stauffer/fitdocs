---
id: 2026-07-29-destructive-reset-reaches-implementers-nowhere
title: The no-destructive-reset rule lives where neither implementers nor reviewers read, and three subagents have now broken it
status: open
importance: medium
importance_why: Two independent implementer subagents ran `git checkout` over their own uncommitted work in a single batch, and both then reconstructed files from agent memory rather than from git. Reconstruction silently invalidates every discrimination claim gathered before it, which is the one artifact the whole change protocol rests on. Both artifacts survived here only because reviewers checked.
effort: S
kind: gap
area: .claude/skills/kiro-impl, .kiro/steering/change-protocol.md
created: 2026-07-29
surfaced_by: adversarial reviews of chore/plugin-api-surface-guard and chore/banister-resource-and-note-backstops (queue-top7 batch)
pinned_at: 13acd83
resume_command: "do: put the no-destructive-reset rule where implementers actually read — .claude/skills/kiro-impl/templates/implementer-prompt.md and the Fixture Discrimination gate in .kiro/steering/change-protocol.md — rather than only kiro-impl/SKILL.md's Critical Constraints, and state the consequence that makes it matter: evidence gathered before a reset was gathered against a file that no longer exists [queue: .kiro/queue/2026-07-29-destructive-reset-reaches-implementers-nowhere.md]"
context:
  - .claude/skills/kiro-impl/SKILL.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .kiro/steering/change-protocol.md
  - .kiro/queue/2026-07-27-never-auto-close-rule-unreachable-by-implementers.md
blocked_by: []
---

## What

`.claude/skills/kiro-impl/SKILL.md` lists "**No Destructive Reset**: Never use
`git checkout .`, `git reset --hard`, or similar destructive rollback inside
the implementation loop" under Critical Constraints. That text is read by the
*orchestrating* session, not by the implementer subagent — the implementer
reads `templates/implementer-prompt.md`, which does not carry the rule.

Two implementers in one batch ran `git checkout` over their own uncommitted
work, and both then rebuilt the lost file from what the agent remembered
writing.

## Why it matters

The reset itself is recoverable annoyance. The consequence that is not is
this: **every mutation result recorded before the reset was recorded against a
file that no longer exists.** The Fixture Discrimination gate's entire output
is claims of the form "mutation X reds assertion Y", and after a
reconstruct-from-memory those claims describe a file the reviewer cannot
inspect. A reconstruction that drops or duplicates a line produces a green
suite and a confident, false evidence record — the same failure shape the
stale-bytecode hazard produces, and that one earned a full section in
`change-protocol.md`.

Both artifacts here survived, but only because reviewers were explicitly told
to check integrity first. Neither implementer flagged the risk to its own
evidence; one framed the reconstruction as a *precaution* ("not `git checkout`,
to avoid re-losing the uncommitted content edits it had already once wiped").

This is the same shape as
`2026-07-27-never-auto-close-rule-unreachable-by-implementers`: a rule that
exists only where the people bound by it do not look. That item recorded three
implementers breaking one rule in a day; this is two breaking another.

## Evidence

Both from the implementers' own reports in the 2026-07-29 queue-top7 batch:

- `chore/plugin-api-surface-guard`: *"Restored design.md from an in-memory
  backup afterward (not `git checkout`, to avoid re-losing the uncommitted
  content edits it had already once wiped mid-session)."* Reviewer verified the
  committed artifact intact (`git diff main...HEAD -- .kiro/specs/plugin-api/design.md`
  = 2 intended hunks, 1035 → 1046 lines, no third hunk).
- `chore/banister-resource-and-note-backstops`: *"I ran `git checkout`
  mid-session, which reverted the test file to its pre-edit state — caught
  immediately via `git status`, and the entire test file was reconstructed and
  re-verified green before proceeding."*

The rule's current home: `.claude/skills/kiro-impl/SKILL.md` § Critical
Constraints. Absent from `templates/implementer-prompt.md` and from
`.kiro/steering/change-protocol.md`.

**Third occurrence, 2026-07-30 — and it was a REVIEWER, not an implementer**
(`fit-ingest` task 12.2, round-4 review, branch `impl/fit-ingest`). From the
reviewer's own verdict:

> Process note: an early `git checkout src/fitdocs/metrics/sources.py` reverted
> that file's uncommitted work. It was fully reconstructed and verified
> byte-identical to the baseline checksum (`d6f9badc…`) before any further
> work; all subsequent mutations used file backups, never git.

This widens the item in two ways the original framing did not cover:

1. **The audience is wrong, not just incomplete.** `templates/reviewer-prompt.md`
   and `.claude/skills/kiro-review/SKILL.md` are a second pair of documents that
   do not carry the rule, and a reviewer is *more* exposed than an implementer:
   its whole job is apply-mutation / observe / revert against a tree of
   uncommitted work it did not write, so the revert idiom is its core loop
   rather than an occasional recovery step. Fixing only the implementer template
   would leave this occurrence unaddressed.
2. **This one degraded gracefully, and that is the argument for the fix, not
   against it.** The reviewer had taken SHA-256 baselines of all five changed
   files *before* starting, so it could verify the reconstruction was
   byte-identical rather than merely believing it — and the parent session
   independently re-verified the tree afterwards (`git status` shape unchanged,
   the `POWER_ABSENT_SAMPLE_*` records present, 2228 passed). Checksum-before-you-
   mutate is the practice that turns this from an evidence-invalidating event
   into a footnote, and it is currently nowhere in either prompt.

The positive alternative in step 3 below should therefore be stated for both
roles, and should name the checksum baseline as part of it.

## How to pick it up

1. Read `.claude/skills/kiro-impl/SKILL.md`'s "No Destructive Reset" bullet and
   confirm it is absent from `templates/implementer-prompt.md`.
2. Add it to the implementer template, with the CONSEQUENCE stated, not just
   the prohibition — an implementer that knows only "don't" will still reset
   when it feels stuck. What stops it is knowing the reset invalidates the
   evidence it has already gathered and will have to re-run.
3. Give the positive alternative in the same breath: commit early on the
   branch, or use `git stash` / a scratch copy. The mutation loop's own
   apply/observe/revert cycle needs a safe revert idiom, and `change-protocol.md`
   § Fixture Discrimination does not currently name one.
4. Consider a line in `change-protocol.md` § Fixture Discrimination stating
   that any evidence gathered before a working-tree reset must be re-gathered —
   this is what makes it a gate concern rather than a hygiene preference.

## Open questions

Whether the reviewer templates should carry a standing integrity check (does
the committed artifact match what the evidence describes?) or whether that is
too expensive to run on every task and belongs only where a reset was reported.

---
id: 2026-07-26-spec-status-arguments-path-interpolation
title: kiro-spec-status interpolates all of $ARGUMENTS into a path, so it breaks on any trailing text
status: open
importance: medium
importance_why: Harmless until now, but the queue's resume directive puts trailing text after the feature name, so a queue item naming this command would silently read a nonexistent spec directory.
effort: S
kind: bug
area: .claude/skills/kiro-spec-status
created: 2026-07-26
surfaced_by: /kiro-queue resume-command work (chore/queue-resume)
pinned_at: ec4ee03
resume_command: "do: change kiro-spec-status's Step 1 to take the feature name from the first whitespace-separated token of $ARGUMENTS rather than all of it, and ignore the remainder"
context:
  - .claude/skills/kiro-spec-status/SKILL.md
  - .kiro/queue/README.md
blocked_by: []
---

## What

`kiro-spec-status` builds its file paths by interpolating the whole argument
string: `.kiro/specs/$ARGUMENTS/spec.json`. Every other spec skill takes "the
feature name from the first argument" and tolerates extra tokens. So
`/kiro-spec-status fit-ingest` works, but `/kiro-spec-status fit-ingest
anything-else` resolves to `.kiro/specs/fit-ingest anything-else/spec.json`
and reports the spec as missing.

## Why it matters

Standalone this is a latent papercut — nobody passes a second token today.
What makes it live is the resume-command directive added on
`chore/queue-resume`: `resume_command` now appends
`[queue: <path>] <intent>` after the feature name. Any queue item that names
`/kiro-spec-status <feature>` as its resume command will send that trailing
text straight into the path and get "No spec found", with the failure looking
like a missing spec rather than a parsing bug.

`.kiro/queue/README.md` currently works around this by warning authors to
check before naming a command. That warning is the right long-term advice for
arbitrary skills, but this specific skill should just parse its argument the
way every sibling does.

## Evidence

Verified at `ec4ee03`:

- `.claude/skills/kiro-spec-status/SKILL.md:20-23` — four raw interpolations:
  `.kiro/specs/$ARGUMENTS/spec.json`, `.../brief.md`, and the directory check.
- `.claude/skills/kiro-spec-status/SKILL.md:59` — the error message
  ``"No spec found for `$ARGUMENTS`"`` confirms the whole string is treated as
  the feature name.
- Contrast: `kiro-spec-requirements/SKILL.md:25`, `kiro-spec-design/SKILL.md:26`
  and `kiro-spec-tasks` all use a `{feature}` placeholder, and
  `kiro-impl/SKILL.md:64` says "Extract feature name from first argument".
  `kiro-spec-status` is the only outlier.
- Not yet reachable in the queue: `grep "^resume_command:" .kiro/queue/*.md`
  shows no item naming `/kiro-spec-status` today, so nothing is broken right
  now.

## How to pick it up

1. Read `.claude/skills/kiro-spec-status/SKILL.md:19-25` and `:59`.
2. Replace the four `$ARGUMENTS` path interpolations with the first
   whitespace-separated token, and state that any remainder is ignored — the
   same shape `kiro-impl` already documents.
3. Confirm no sibling skill has the same pattern:
   `grep -rn 'specs/\$ARGUMENTS' .claude/skills/`.
4. Exercise it: `/kiro-spec-status fit-ingest` still reports, and
   `/kiro-spec-status fit-ingest [queue: x] blah` reports on `fit-ingest`
   rather than failing.

Done means the command tolerates trailing text, and
`.kiro/queue/README.md` can list `kiro-spec-status` among the skills safe to
name in a `resume_command`.

## Open questions

Whether `kiro-spec-status` should also honor the `[queue: …]` directive
(reading the item and reporting its status alongside the spec's), or only stop
choking on it. This item covers the parsing fix; honoring the directive would
be a separate, larger change to a read-only reporting skill.

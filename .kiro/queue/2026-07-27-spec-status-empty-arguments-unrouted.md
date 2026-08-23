---
id: 2026-07-27-spec-status-empty-arguments-unrouted
title: kiro-spec-status Step 1 has no route to the documented no-argument fallback
status: open
importance: low
importance_why: Silent wrong-path read on empty input rather than the documented "list all specs" behavior; no reported occurrence yet, but the failure mode is confusing (looks like a missing-spec bug, not a routing gap).
effort: S
kind: gap
area: .claude/skills/kiro-spec-status
created: 2026-07-27
surfaced_by: /kiro-review chore/spec-status-args remediation
pinned_at: c3d2201
resume_command: "do: give kiro-spec-status/SKILL.md Step 1 an explicit branch for empty \$ARGUMENTS that routes to the List All Specs fallback (:70-74) instead of computing an empty {feature}"
context:
  - .claude/skills/kiro-spec-status/SKILL.md
blocked_by: []
---

## What

`.claude/skills/kiro-spec-status/SKILL.md` Step 1 extracts `{feature}` from
the first whitespace-separated token of `$ARGUMENTS` with no guard for the
empty-string case. When `$ARGUMENTS` is empty, `{feature}` resolves to the
empty string and Step 1 proceeds to read `.kiro/specs//spec.json` (a missing
path with a doubled slash) instead of routing to the skill's own documented
fallback. The "List All Specs" section (`:70-74`) says "Run with no argument
… Shows all specs in `.kiro/specs/` with their status", but nothing in Step 1
checks for the no-argument case and branches there — the fallback is
described but unreachable from the normal execution path.

## Why it matters

Today this produces a spec-not-found error instead of the documented list-all
behavior when the skill is invoked with no arguments — the one input shape the
skill's own docs claim to handle specially. Low urgency (no reported
occurrence, and the failure is at least visibly a "not found" message rather
than a crash), but it is the exact kind of documented-but-unwired behavior
that erodes trust in the fallback section over time.

## Evidence

Verified at `5ab0767` (branch `chore/spec-status-args`, after the Step 1
`{feature}`-parsing fix landed):

- `.claude/skills/kiro-spec-status/SKILL.md` Step 1 (first-token extraction)
  has no conditional on `$ARGUMENTS` being empty.
- `.claude/skills/kiro-spec-status/SKILL.md:70-74` ("List All Specs") documents
  the no-argument behavior but is not referenced anywhere in Step 1 or the
  Error Scenarios section.
- Confirmed pre-existing: this gap is unchanged by the `chore/spec-status-args`
  branch (which fixed first-token parsing, not argument-presence routing) — it
  exists identically on `main`.

## How to pick it up

1. Read `.claude/skills/kiro-spec-status/SKILL.md` Step 1 and the "List All
   Specs" section (`:70-74`).
2. Add an explicit empty-`$ARGUMENTS` (or wildcard) branch at the top of
   Step 1 that routes to the List All Specs behavior before attempting to
   compute `{feature}`.
3. Exercise it: `/kiro-spec-status` with no argument lists
   `.kiro/specs/` contents rather than reporting a spec-not-found error for an
   empty feature name.

## Open questions

None.

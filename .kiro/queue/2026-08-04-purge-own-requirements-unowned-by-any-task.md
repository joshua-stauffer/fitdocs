---
id: 2026-08-04-purge-own-requirements-unowned-by-any-task
title: The purge's own requirements.md carries a copyright-notice fragment and a stale claim, and no task owns the file
status: open
importance: high
importance_why: Req 11.4 forbids the notice at any commit, and Major 7 rewrites history once. A fragment still in the tree when the rewrite runs is baked into the published repository.
effort: S
kind: gap
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/requirements.md
created: 2026-08-04
surfaced_by: /kiro-impl encumbered-content-purge (task 3.8 review, rounds 1-3)
pinned_at: c3d2201
resume_command: "/kiro-impl encumbered-content-purge [queue: .kiro/queue/2026-08-04-purge-own-requirements-unowned-by-any-task.md] Redact the purge spec's own requirements.md before Major 7"
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`.kiro/specs/encumbered-content-purge/requirements.md` carries two defects, and
no task in Majors 3-8 has it in a `_Boundary:_`. Task 3.8 owns "every remaining
spec" but its reviewer classified this file among the four legitimately excluded
— its only forbidden-string hit is the token-free retained path fragment — so
the file passed the enumeration while still carrying both of these.

1. **Line 34 retains the notice's literal reserved-rights phrase.** Req 11.4
   forbids a copyright or trademark notice at any commit. The fragment does
   not name the third party, so it is not an identifying token and no matcher
   flags it — but it is a fragment of the notice the requirement exists to
   remove.
2. **Line 58 describes the prior rewrite map in the present tense** as "a
   tracked file whose sole purpose is…". Task 3.1 deleted that file at
   `a705490`. The claim is now false.

## Why it matters

Req 11.4 is unconditional over every commit, and Major 7 is a **one-shot**
history rewrite. Anything still in the tree when it runs is what the published
repository will contain, permanently. A fragment that no matcher flags is
exactly the kind that survives to the rewrite unnoticed — the guards cannot
catch it, so only a task with the file in its boundary will.

The stale claim is lower stakes but sits in an approved requirements document,
where a later session reading it will believe the map is still tracked.

## Evidence

```
$ git grep -n -Fi "<the reserved-rights phrase>" -- .kiro/specs/
.kiro/specs/encumbered-content-purge/requirements.md:34

$ git ls-files docs/reference/
docs/reference/fitdocs-ai-reference.md
docs/reference/history-rewrites.md
docs/reference/pkm-integration.md
# the rewrite map is absent; deleted at a705490 (task 3.1)
```

Enumeration at `34b4164`: `.kiro/specs/` content hits are 4, all in this spec's
own `{design,requirements,research,tasks}.md`, and all match only the
token-free `sha-rewrite-map` fragment Req 2.5 deliberately retains. That is why
the file reads clean to every probe.

## How to pick it up

1. Read `requirements.md` lines 30-60 and confirm both sites are still present
   at the current tip.
2. Decide the reserved-rights phrase's treatment against Req 11.4's own text —
   whether a fragment that names nobody is in scope. The design's kind-3
   precedent (task 3.8 in `34b4164`) replaced the full notice in `brief.md`
   with a description rather than rewording it; the same treatment applies here
   if it is in scope.
3. Past-tense the line-58 claim, naming `docs/reference/history-rewrites.md` as
   the successor record rather than repointing at the deleted path.
4. Done looks like: grepping `.kiro/specs/` for the reserved-rights phrase
   returns nothing, no present-tense claim describes the map as tracked, and the
   redaction-only invariants hold — no criterion added, revised, withdrawn or
   renumbered, no approval flag moved.

## Open questions

Whether the reserved-rights fragment is in Req 11.4's scope when it names
no party is a judgment the maintainer may want to make. Both readings are
defensible; the conservative one removes it, and removal costs nothing.

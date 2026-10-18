---
id: 2026-10-18-morning-req-12-3-says-no-file-but-pass-uses-temp-files
title: workout-wellness Req 12.3 says the morning pass creates, renames or deletes no file, but its approved atomic write does all three on a temp file
status: open
importance: low
importance_why: Spec text and the shipped ownership contract now say different things. Behaviour is correct, but the requirement is literally false.
effort: S
kind: spec-work
area: workout-wellness, .kiro/specs/workout-wellness/requirements.md, docs/ownership-contract.md
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (review of Astra decision 15)
pinned_at: a0e4b92
resume_command: "/kiro-spec-requirements workout-wellness [queue: .kiro/queue/2026-10-18-morning-req-12-3-says-no-file-but-pass-uses-temp-files.md] Amend Req 12.3 to say no workout document is created, renamed or deleted"
context:
  - .kiro/specs/workout-wellness/requirements.md
  - .kiro/specs/workout-wellness/design.md
  - .kiro/specs/workout-wellness/tasks.md
  - src/fitdocs/morning/engine.py
  - docs/ownership-contract.md
blocked_by: []
---

## What

Req 12.3 reads: "The morning-of pass shall write only existing workout pages
under `workouts/`, and shall create, rename or delete no file."

The pass actually works like this (`src/fitdocs/morning/engine.py:103-120`):
1. creates `.morning-*.tmp` beside the page;
2. moves it over the page with `os.replace`;
3. unlinks the temp file in `finally`.

That is the temp-then-replace mechanism the approved design prescribes for
Req 7.7's atomic write (`design.md`, Components). The autonomous run's Astra
decision 15 (`tasks.md` Implementation Notes) resolved the conflict by reading
"file" as "workout document". The ownership contract now promises the
narrower "never creates, renames or deletes a workout document". The
requirement text was never amended.

## Why it matters

A later reviewer reading Req 12.3 literally will flag `_atomic_write` as a
violation. Or worse, they may "fix" it by dropping atomicity. There is also a
real edge: after a SIGKILL between create and replace, a stray
`.morning-*.tmp` can be left in `workouts/`. The load pass has the same edge
(`.kiro/queue/2026-09-15-atomic-write-helper-copied-per-engine.md`).

## Evidence

- `.kiro/specs/workout-wellness/requirements.md:220`
- `src/fitdocs/morning/engine.py:103-120`: `tempfile.NamedTemporaryFile(prefix=".morning-", suffix=".tmp", dir=path.parent, delete=False)`, then `os.replace`, then `unlink(missing_ok=True)`
- `tasks.md`: the "Astra decision 15" note

## How to pick it up

1. Append an amendment to workout-wellness `requirements.md`. Reword 12.3 to
   "...shall create, rename or delete no workout document; it may use a
   temporary file beside the page to write it atomically (Req 7.7)". Record it
   in `spec.json`.
2. Check that `docs/ownership-contract.md` and the declaration goldens already
   say "workout document". If so, they need no change.
3. Optional: make `fitdocs check` report stray `.morning-*.tmp` files, or
   point to the atomic-write-helper item.

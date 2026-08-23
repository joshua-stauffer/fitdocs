---
id: 2026-07-26-profileerror-redundant-in-config-errors
title: '`ProfileError` in the engine''s `_CONFIG_ERRORS` tuple is redundant and unremovable-by-test'
status: open
importance: low
importance_why: Behaviourally null today, but it makes the tuple read as load-bearing per entry, so a future reader could delete a genuinely load-bearing sibling by the same reasoning that says this one is fine.
effort: S
kind: chore
area: training-load, src/fitdocs/load/engine.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 5.2 review, own mutation M7a)
pinned_at: c3d2201
resume_command: "do: decide whether _CONFIG_ERRORS should list ProfileError explicitly for documentation value or drop it as covered by its AthleteFileError base, and comment whichever way it goes [queue: .kiro/queue/2026-07-26-profileerror-redundant-in-config-errors.md]"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What
`src/fitdocs/load/engine.py:140` lists `ProfileError` in the `_CONFIG_ERRORS`
tuple, the set of exceptions the load pass lets propagate as configuration
failures rather than per-document errors. But `src/fitdocs/load/profile.py:92`
declares `class ProfileError(AthleteFileError)`, and `AthleteFileError` is
already in the tuple — so the entry catches nothing its base does not.

It is therefore **unremovable by test**: no assertion can distinguish the tuple
with it from the tuple without it.

## Why it matters
Low, and honestly so — there is no behavioural defect and arguably documentation
value in naming the subclass explicitly at the boundary where it matters.

The reason to record it: an entry that no test can pin invites the wrong
inference. A future reader mutating `_CONFIG_ERRORS` to check their work will
find this entry removable with the suite green, and may generalise that the
tuple is not load-bearing — when the *other* entries are. The safe outcome is a
one-line comment stating that `ProfileError` is listed for readability and is
covered by `AthleteFileError`, so the next person does not have to rediscover
the class hierarchy to know which entries matter.

## Evidence
At `18cfc07`, removing `ProfileError` from `src/fitdocs/load/engine.py:140`:

```
uv run pytest -p no:cacheprovider   # 2008 passed
```

Class hierarchy: `src/fitdocs/load/profile.py:92` — `class ProfileError(AthleteFileError)`.

Measured by a task 5.2 reviewer as mutation M7a and correctly classified as an
**equivalent mutant** rather than a coverage finding — the mutation is
behaviourally null, so a surviving mutant here is not evidence of a missing
test.

## How to pick it up
1. Read `src/fitdocs/load/engine.py:140` and the `except` site that consumes `_CONFIG_ERRORS`, plus `src/fitdocs/load/profile.py:92` for the hierarchy.
2. Decide: keep it with an explanatory comment (recommended — the explicitness is useful at a boundary), or drop it as covered by the base.
3. Done looks like: a reader can tell from the tuple alone which entries are load-bearing, without deriving the exception hierarchy.

Owned by `training-load`, which owns `engine.py`. Note it may need an open task
before its module can be edited — the same vehicle problem recorded in
[[2026-07-26-plugin-surface-list-stale-after-amendment-3]].

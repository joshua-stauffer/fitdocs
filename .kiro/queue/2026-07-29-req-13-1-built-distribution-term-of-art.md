---
id: 2026-07-29-req-13-1-built-distribution-term-of-art
title: Req 13.1 says "built distribution", which in PyPA usage excludes the sdist the guard now covers
status: open
importance: low
importance_why: The widened reading is correct and safe, but it lives only in a test docstring. The requirement still says a term of art that, read literally, never bound the sdist — so the guard that now exists is inferred rather than required, and a later reader could remove it as unrequired.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load/requirements.md
created: 2026-07-29
surfaced_by: adversarial review of the branch that added the sdist exclusion for the withdrawn methodology's tables (queue-top7 batch)
pinned_at: c3d2201
resume_command: "do: amend training-load requirements.md criterion 13.1 so its distribution clause names both artifacts `uv build` produces rather than the PyPA term of art \"built distribution\", which excludes sdists — recording it as a proper amendment to an approved spec [queue: .kiro/queue/2026-07-29-req-13-1-built-distribution-term-of-art.md]"
context:
  - .kiro/specs/training-load/requirements.md
  - tests/load/test_packaging.py
  - pyproject.toml
blocked_by: []
---

## What

`.kiro/specs/training-load/requirements.md:416` reads:

> The installed fitdocs package shall contain no withdrawn calculator
> implementation, no withdrawn-methodology lookup tables, and no
> withdrawn-methodology-derived constants, and the
> built distribution shall ship no withdrawn-methodology data files.

In PyPA terminology, "Built Distribution" is a defined term that specifically
**excludes** a source distribution — an sdist is a "Source Distribution". Read
literally, the criterion never bound the sdist at all.

## Why it matters

`0080811` added an sdist exclusion and a guard on the strength of this
criterion. That widening is correct — Requirement 13's own objective
(`requirements.md:408-411`, "removed from the shipped tool completely and
honestly, so that no ... unlicensed data file remains") and the licensing
purpose both reach the sdist, and over-excluding cannot create exposure. But
the justification currently lives in a test docstring
(`tests/load/test_packaging.py:339`, `:346-351`) and a commit message, while
the approved criterion still says the narrower term.

The risk is not that the guard is wrong; it is that a later session reading
only `requirements.md` finds a guard enforcing more than any criterion
requires, and removes it as over-reach. The whole point of Requirement 13 is
that the withdrawal is honest, which makes an inferred obligation the wrong
shape for it.

## Evidence

- `.kiro/specs/training-load/requirements.md:416` — the criterion, unamended.
- `tests/load/test_packaging.py:339` — the widened reading, recorded only here.
- PyPA glossary: "Built Distribution" vs "Source Distribution" are distinct
  defined terms; a wheel is the former, an sdist the latter.
- The reviewer flagged this explicitly as non-blocking but real, noting the
  implementer stated the reading in a durable place but "did not flag the
  glossary tension, and `requirements.md` is unamended".

## How to pick it up

1. Read `requirements.md:408-416` (Requirement 13's objective and criterion
   13.1) and `tests/load/test_packaging.py:334-360` (the guard's own statement
   of what it covers and why).
2. Amend 13.1's final clause to name both artifacts explicitly — e.g. "neither
   artifact `uv build` produces shall ship withdrawn-methodology data files" —
   so the obligation is stated rather than inferred.
3. This is a criterion change to an approved spec: record it as a proper dated
   amendment rather than an in-place edit, following the pattern training-load
   already uses for its Amendments 1–3.
4. Done looks like: the sdist guard is required by a criterion, not merely
   permitted by one, and the test docstring can cite the criterion instead of
   arguing for it.

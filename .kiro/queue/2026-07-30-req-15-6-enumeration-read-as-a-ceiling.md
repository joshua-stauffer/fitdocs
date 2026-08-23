---
id: 2026-07-30-req-15-6-enumeration-read-as-a-ceiling
title: Req 15.6's enumeration is a floor, but a session read it as a ceiling and justified a coverage gap with it
status: open
importance: low
importance_why: The conclusion it was used to justify happens to hold via a different mechanism, so nothing shipped wrong — but the misreading is the kind that licenses a real gap next time, and task 12.2 itself created a constant outside the enumeration, which disproves the reading.
effort: S
kind: docs
area: fit-ingest, .kiro/specs/fit-ingest/requirements.md
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, round-5 review follow-up)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-req-15-6-enumeration-read-as-a-ceiling.md] Make Req 15.6 say whether its enumeration is a floor or a closed set"
context:
  - .kiro/specs/fit-ingest/requirements.md
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_sources.py
blocked_by: []
---

## What

Req 15.6 reads *"shall classify each of the following"* and then enumerates
seven items. That is a **floor** — every listed value must be classified. It
does not say the set of classified constants is closed.

A task 12.2 implementer read it as a **ceiling** and used that reading to
declare a coverage gap acceptable: it argued that
`test_non_weighting_constants_carry_no_corroborators`'s hardcoded 6-tuple could
not go stale, because "`CONSTANT_SOURCES` cardinality is fixed by Req 15.6's
enumeration" and so no eighth Citation-sourced constant could exist.

Task 12.2 had, in that same change, created `POWER_ABSENT_SAMPLE_FILL` — a
constant outside the enumeration.

## Why it matters

Low, because the conclusion survived on other grounds. The reviewer verified by
mutation that an 11th registered `Citation`-sourced constant carrying a
spurious corroborator reds three separate count assertions
(`test_constant_sources_has_exactly_ten_entries`,
`..._names_are_unique`, `..._is_exactly_the_module_level_cited_constants`), so
it cannot ship silently. The declared gap is correctly declared; only the
*reason* is wrong.

It is worth recording because a wrong premise that happens to reach a right
conclusion is not self-correcting. The next session that needs to justify not
covering something has a precedent argument — "the enumeration is closed" —
that reads as spec-grounded and is not. Requirement text that can be read two
ways, where one reading licenses skipping coverage, is worth one clarifying
clause.

## Evidence

- `.kiro/specs/fit-ingest/requirements.md:431` — *"shall classify each of the
  following"*, followed by the seven-item enumeration. No closure language.
- `src/fitdocs/metrics/sources.py` — `POWER_ABSENT_SAMPLE_FILL`, a
  `CitedConstant` created by task 12.2 and deliberately outside both the
  enumeration and `CONSTANT_SOURCES`. Its existence is the counterexample.
- Task 12.2 implementer's round-4 status report, declaring
  `test_non_weighting_constants_carry_no_corroborators` UNPINNED "since
  `CONSTANT_SOURCES` cardinality is fixed by Req 15.6 and no such 8th slot
  exists to add".
- Round-5 reviewer, follow-up 5: *"a misreading … the conclusion survives via a
  different mechanism (three count assertions red loudly), so the gap is
  correctly declared; only the reason given is wrong."*

## How to pick it up

1. Read Req 15.6 in `.kiro/specs/fit-ingest/requirements.md` and decide the
   intent: is the enumeration the minimum set that must be classified, or the
   complete set of constants the registry may hold?
2. It is almost certainly a floor, so add one clause saying so — e.g. that the
   enumeration names the values that must be classified and does not bound what
   else the registry may hold.

   **This step originally cited `POWER_ABSENT_SAMPLE_FILL` as the worked
   example of a legitimate constant outside the enumeration. That record was
   deleted at `dd10f9f`** (an absent power sample no longer resamples as a
   fabricated `0.0`, so no fill value exists to cite), and with it went the only
   constant this repo had ever bound outside 15.6's seven items. The argument
   still stands on its own — an enumeration read as a ceiling would forbid any
   future 15.8 choice — but it now has **no live example**, which if anything
   makes the clarifying clause more useful, not less: the next session to add
   such a constant will be the first, and should not have to litigate whether
   15.6 permits it.
3. While there, check whether any other test or docstring rests on the closed
   reading. `grep` for "seven" and "enumerat" across `tests/metrics/` and
   `.kiro/specs/fit-ingest/`.

Done looks like: Req 15.6 states whether its list is a floor or a closed set,
so neither reading is available to a future session.

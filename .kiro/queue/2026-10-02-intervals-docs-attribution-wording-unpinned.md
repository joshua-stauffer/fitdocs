---
id: 2026-10-02-intervals-docs-attribution-wording-unpinned
title: The Garmin attribution wording in docs/connectors.md and in the CHANGELOG [Unreleased] entry is not pinned to render/attribution.py
status: open
importance: low
importance_why: Both texts are true today (the multi-source form is now documented); nothing fails if render/attribution.py's wording changes, so they can drift silently.
effort: S
kind: gap
area: intervals-connector, channel-merge, docs/connectors.md, CHANGELOG.md, src/fitdocs/render/attribution.py, tests/connectors/test_intervals_docs.py
created: 2026-10-02
surfaced_by: /kiro-impl intervals-connector (4.2 review, feature validation); updated by /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-10-02-intervals-docs-attribution-wording-unpinned.md] Pin docs/connectors.md's and the CHANGELOG's attribution wording to render/attribution.py"
context:
  - docs/connectors.md
  - CHANGELOG.md
  - src/fitdocs/render/attribution.py
  - src/fitdocs/render/views.py
  - tests/connectors/test_intervals_docs.py
  - tests/compose/test_contract_docs.py
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/channel-merge/tasks.md
blocked_by: []
---

## What
Three places state the Garmin attribution wording, and no test ties any of
them to `render/attribution.py`'s constants (`SOLE_SOURCE_PREFIX`,
`SOURCES_PREFIX`, `OTHER_DEVICES`):

1. `docs/connectors.md`, `### Garmin attribution`, the single-source form
   `Data source: Garmin <model>`.
2. The same section's multi-source paragraph, added by channel-merge: count
   the files that donate a channel alongside the base, name each distinct
   Garmin model base-first, end with `and other devices` when any counted file
   was not recorded by a Garmin, name a model recorded twice once, write no
   line when no counted file is a Garmin. Examples
   `Data sources: Garmin <model> and other devices` and
   `Data sources: Garmin <model> and Garmin <other model>`.
3. The `CHANGELOG.md` `[Unreleased]` entry: the single form, and channel-merge's
   sentence that the data-source line "also counts the files that donate
   channels: a Garmin-recorded one is named, any other adds "other devices"".

This item was opened by intervals-connector with a second gap, that the
multi-source form was undocumented. channel-merge fixed that one; what remains
is the missing pin.

## Why it matters
If someone changes the wording in `attribution.py` (a prefix, the conjunction,
the "other devices" phrase), the docs and the release note go stale and no
test fails. docs/connectors.md says the attribution line exists because of the
terms the data comes under (intervals.icu API terms, Garmin API Brand Guidelines), so a
doc that misdescribes it is worse than one that is merely out of date.

## Evidence
All at 5c41759, read or grepped in this run.
- `src/fitdocs/render/attribution.py:19-21` defines the three constants;
  `:64` builds the single form and `:66` the plural one.
- `docs/connectors.md:184` (single form) and `:191-199` (multi-source rule and
  both examples).
- `CHANGELOG.md:98` (single form) and `:113-115` (channel-merge sentence).
- `grep -rn "other devices\|Data sources" tests/connectors tests/test_changelog.py`
  prints nothing (exit 1). Outside `tests/render/` no test file contains
  "other devices", "data-source line" or "counts the files".
- The wording is pinned only where the function itself is tested:
  `tests/render/test_attribution.py` (for example `:183`) and
  `tests/render/test_provenance.py:668`. Those do not read the docs.
- `tests/connectors/test_intervals_docs.py:214-218` pins two phrases of the
  section (the FIT SDK profile route, "just `Garmin`") and `:65` its heading;
  neither names a prefix. `tests/compose/test_contract_docs.py:155-165` pins
  four phrases of the channel-merge CHANGELOG entry and not the data-source
  sentence.
- Earlier evidence from intervals-connector: the 4.2 reviewer changed the
  attribution wording (mutation O9) and the suite stayed green (reported by
  reviewer subagent, unverified in this run).

## How to pick it up
1. Read `attribution.py` and the two doc locations above.
2. In `tests/connectors/test_intervals_docs.py`, read the `### Garmin
   attribution` section by its heading and assert it quotes the prefixes and
   the "other devices" phrase built from the module's constants, and that
   each example line is one `attribution_line` actually produces for matching
   inputs.
3. In `tests/compose/test_contract_docs.py` (where the entry is already
   located by "Channel Sources"), or `tests/test_changelog.py`, assert the
   `[Unreleased]` entry quotes the `OTHER_DEVICES` phrase from the constant.
4. Done when changing each constant, one at a time, reds a docs or changelog
   test, and the existing tests stay green.

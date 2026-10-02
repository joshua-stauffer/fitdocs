---
id: 2026-10-02-position-donation-wording-spec-vs-code
title: channel-merge Req 2.4 says an extra donates position only if it records both coordinates at the base's instants; design.md and composer.py require each coordinate to be placed somewhere
status: open
importance: low
importance_why: A spec-versus-implementation wording gap that only bites an extra whose latitude and longitude are placed on disjoint samples; no current fixture has one.
effort: S
kind: inconsistency
area: channel-merge, src/fitdocs/compose/composer.py, .kiro/specs/channel-merge/requirements.md, .kiro/specs/channel-merge/design.md
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "/kiro-spec-requirements channel-merge [queue: .kiro/queue/2026-10-02-position-donation-wording-spec-vs-code.md] Settle Req 2.4's position-donation wording against design.md and compose/composer.py"
context:
  - .kiro/specs/channel-merge/requirements.md
  - .kiro/specs/channel-merge/design.md
  - src/fitdocs/compose/composer.py
  - src/fitdocs/compose/donation.py
  - tests/compose/test_composer.py
  - docs/ownership-contract.md
blocked_by: []
---

## What
Latitude and longitude are one donation unit. Req 2.4 says an extra donates
position when it "records both ... at instants of the base's samples after
alignment". The design and the code require less: each channel of the unit must
have some placed value, not that any one sample holds both. So an extra whose
latitude is placed at one base sample and whose longitude at another (and
nowhere else) donates position, and no composed sample holds a full coordinate.
This is spec wording against an implementation choice, not a code defect: it
needs a ruling on which side moves.

## Why it matters
The published contract (`docs/ownership-contract.md`) copies the looser form, so
the ruling decides whether a requirement, a design paragraph and a contract
sentence change, or the code does. Left unsettled, a future reader will "fix"
the code to the requirement or the requirement to the code and break the other.

## Evidence
At 5c41759.
- `.kiro/specs/channel-merge/requirements.md:131` (Requirement 2, criterion 4):
  "...shall take both from the one highest-ranked extra that records both at
  instants of the base's samples after alignment."
- `.kiro/specs/channel-merge/design.md:818-822` (Composer, step 2): "every
  still-open unit whose `placed_values` record **every** channel of the unit is
  donated".
- `src/fitdocs/compose/composer.py:91`: `if all(records(v) for v in values.values()):`
  with `records` (`donation.py:36`) true when any value is not `None`; each
  channel is tested separately, never per sample.
- `docs/ownership-contract.md:572-575`: "...records both latitude and
  longitude once placed on the base's timeline".
- `tests/compose/test_composer.py:329-399` (`TestPosition`) has two tests, a
  latitude-only extra skipped for one that records both, and a base with one
  coordinate; neither places the two on disjoint samples.
- The disjoint-sample consequence is from reading the code, not run.

## How to pick it up
1. Decide: strengthen the code (donate position only if some placed sample
   holds both) or loosen the requirement to match design.md. The real case is
   rare (one fixed-rate recorder drops both together), which favours rewording.
2. Edit the losing side, keep `design.md`, `requirements.md` and the
   ownership-contract sentence aligned, and add a `TestPosition` case with
   disjoint-sample coordinates that pins whichever rule is chosen.
3. If the code changes, `DOC_VERSION`/`CONTRACT_VERSION` rules in
   `change-protocol.md` apply (composed pages can change bytes).

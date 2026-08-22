---
id: 2026-08-22-readme-user-agent-example-is-unpinned
title: The README's User-Agent example is unpinned against fitdocs.tiles.USER_AGENT
status: open
importance: medium
importance_why: The README documents the exact UA fitdocs sends to OSM, whose politeness requirement is about being identifiable and contactable; nothing cross-checks it against the constant, so a UA change can leave the shipped README advertising a stale URL.
effort: S
kind: gap
area: README.md, tests/test_tiles.py, route-maps
created: 2026-08-22
surfaced_by: kiro-review of chore/repo-rename (reviewer designed mutations the implementer had not)
pinned_at: 29604fc
resume_command: "do: pin README.md's documented User-Agent example against fitdocs.tiles.USER_AGENT so the two cannot drift, and prove it with a mutation to each side"
context:
  - README.md
  - src/fitdocs/tiles.py
  - tests/test_tiles.py
blocked_by: []
---

## What

`README.md:50` documents the user agent fitdocs sends on every tile fetch:

    fitdocs/<version> (+https://github.com/joshua-stauffer/fitdocs)

Nothing checks it against `fitdocs.tiles.USER_AGENT`. Measured by mutation
during the review of `chore/repo-rename`:

- Mutating `README.md:50` back to the old repository name leaves the full
  suite green: 4176 passed / 1 skipped.
- Mutating `src/fitdocs/tiles.py`'s `USER_AGENT` reds exactly one test,
  `test_default_fetch_sends_descriptive_user_agent_and_timeout` — and no
  README-consistency test complains.

So the two can drift in either direction with the suite green.

## Why it matters

Route-maps Requirement 3.4 makes the descriptive UA load-bearing rather than
cosmetic: OSM actively blocks default library UAs, and the whole point of the
header is that a tile provider can identify and contact the project. The
README is where a reader learns what fitdocs sends on their behalf — the
privacy disclosure immediately above it is what the example exists to make
concrete. A stale example misinforms the user about what leaves their machine.

The 2026-08-22 repository rename is the concrete instance: `README.md:50` had
to move with `tiles.py`, and only a hand-maintained checklist connected them.

## How to pick it up

The version is interpolated (`version('fitdocs')`), so the README carries a
`<version>` placeholder rather than a literal — assert on the invariant part.
Either compare `USER_AGENT`'s suffix against the README line, or have the test
reconstruct the documented form by substituting the placeholder.

Prove it in **both** directions, since this is a two-sided consistency pin:
mutating the README alone must red it, and mutating `USER_AGENT` alone must
red it. Confirm the sole-failure property for each — `USER_AGENT` already has
its own pin at `tests/test_tiles.py:556`, so check the new assertion is not
merely riding on that one.

See also [[2026-08-22-readme-ownership-section-test-inspects-the-wrong-heading]],
the same class of gap over the README/`declaration.py` pair, found in the same
review.

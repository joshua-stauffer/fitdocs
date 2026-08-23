---
id: 2026-08-05-sdist-allowlist-still-a-live-single-entry-exemption
title: The sdist guard's member allowlist still lets one added entry ship the withdrawn tables undetected
status: open
importance: medium
importance_why: The same licensing exposure the guard exists to catch (an unlicensed copy of the withdrawn methodology's tables in a published sdist) ships silently if one archive-member path is added to `_SDIST_WITHDRAWN_ALLOWLIST` -- the guard's own escape hatch is also its own blind spot, and nothing in the suite reds when that hatch is used on a genuine table.
effort: S
kind: gap
area: encumbered-content-purge, tests/load/test_packaging.py
created: 2026-08-05
surfaced_by: reviewer of encumbered-content-purge task 4.1, repair round 1
pinned_at: c3d2201
resume_command: "do: add a control that proves _SDIST_WITHDRAWN_ALLOWLIST cannot be widened to exempt a genuinely present value -- e.g. assert the allowlist stays empty by default with a dedicated non-empty-is-suspicious review note, or require an allowlist entry to also appear in a small, separately-reviewed audit list checked by a second guard -- so the exemption a maintainer reaches for under guard-failure pressure cannot itself become the evasion [queue: .kiro/queue/2026-08-05-sdist-allowlist-still-a-live-single-entry-exemption.md]"
context:
  - tests/load/test_packaging.py
  - .kiro/queue/closed/2026-07-30-sdist-guard-has-no-positive-control.md
blocked_by: []
---

## What

`tests/load/test_packaging.py::test_sdist_contains_no_withdrawn_research_record`
skips any archive member whose name is in `_SDIST_WITHDRAWN_ALLOWLIST` before
the value-oracle scan runs:

```python
if not member.isfile() or member.name in _SDIST_WITHDRAWN_ALLOWLIST:
    continue
```

The allowlist is empty by default and its own comment says it is meant to stay
that way "for the stronger reason ... none of the three paths exist anywhere
in the tree to be a candidate for it." But nothing enforces that. A single
line adding one real archive-member path to the frozenset exempts that
member's content entirely -- the value-oracle scan never sees it, and the
suite reports fully green while the member ships in a published sdist.

## Why it matters

This is the exact licensing exposure `test_sdist_contains_no_withdrawn_
research_record` exists to catch, reachable through the guard's own declared
escape hatch rather than around it. A maintainer under pressure to make a
guard failure go away has "add the failing member's path to the allowlist" as
a one-line, syntactically-sanctioned move -- the guard's own failure message
even says to do exactly that for a *legitimate* member. Nothing distinguishes
that from doing it for an actual copy of the withdrawn tables.

## Evidence

Reproduced 2026-08-05, on the `encumbered-content-purge` task 4.1 repair
branch, `tests/load/test_packaging.py` at the state reviewed:

1. Extracted one of the withdrawn methodology's pre-deletion extracted-table
   blobs from history (10986 bytes, resolvable via `git cat-file -p
   a705490^:<path>` against the removed-path fragments in the out-of-
   repository forbidden-string source) to a neutral path under
   `src/fitdocs/`.
2. Added that member's `fitdocs-X.Y.Z/`-prefixed path as the sole entry of
   `_SDIST_WITHDRAWN_ALLOWLIST`.
3. `FITDOCS_FORBIDDEN_STRINGS=... uv run pytest tests/load/test_packaging.py`
   → all tests passed. The planted table shipped in the built sdist,
   unscanned, undetected.
4. Reverted both changes; confirmed the same planted file (without the
   allowlist entry) reds `test_sdist_contains_no_withdrawn_research_record`
   as expected.

## How to pick it up

1. Read `_SDIST_WITHDRAWN_ALLOWLIST` and the member-skip line in
   `test_sdist_contains_no_withdrawn_research_record` in full.
2. Decide the shape of the fix: a structural guard that reds whenever the
   allowlist is non-empty (forcing a deliberate, reviewed override to touch
   this test file directly rather than silently pass CI) is the cheapest;
   a second, independently-reviewed audit list cross-checked against the
   allowlist is stronger but adds a file.
3. Add a positive control proving the chosen mechanism actually stops a
   genuine table from being exempted -- not just that the allowlist is
   inspected, but that widening it to cover a real hit is caught.
4. Reproduce this item's evidence steps 1-3 against the fix; confirm step 3
   now fails loudly instead of passing green.

## Open questions

- Should the wheel guard's `_LOAD_MODULE_ALLOWLIST` (a different, equality-
  compared mechanism) be audited for the same class of gap, or is its
  equality-both-directions shape already immune? It was not reproduced here.

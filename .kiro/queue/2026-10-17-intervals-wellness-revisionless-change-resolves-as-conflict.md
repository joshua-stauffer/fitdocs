---
id: 2026-10-17-intervals-wellness-revisionless-change-resolves-as-conflict
title: A changed intervals.icu wellness day without `updated` is re-delivered but the series keeps the old value as a conflict
status: open
importance: low
importance_why: Unreachable on the maintainer's account (every live record carries `updated`), but the connectors docs imply the correction is picked up.
effort: S
kind: inconsistency
area: wellness-pull, wellness-store, docs/connectors.md, src/fitdocs/wellness/formats/intervals.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (wellness-pull reviewer finding 1)
pinned_at: 160b007
resume_command: "do: either document that a revision-less changed wellness day is resolved by archive order (docs/connectors.md § Wellness) or rank content-hash revisions in wellness-store's merge; add the matching test [queue: .kiro/queue/2026-10-17-intervals-wellness-revisionless-change-resolves-as-conflict.md]"
context:
  - docs/connectors.md
  - docs/wellness.md
  - src/fitdocs/wellness/formats/intervals.py
  - src/fitdocs/wellness/merge.py
  - .kiro/specs/wellness-pull/research.md
blocked_by: []
---

## What
The pull detects a changed day that has no `updated` by content hash and
re-delivers it (`docs/connectors.md:190`: "A missing `updated` uses a content
hash instead"). On intake, wellness-store's `_revision`
(`src/fitdocs/wellness/formats/intervals.py:74-83`) returns `None` for a
missing `updated`. Two revision-less records of one day are resolved "by a
deterministic archive-reference order" (`docs/wellness.md:468-470`), not by
recency, so the series can keep the old value and report `Conflicts: 1`.

## Why it matters
A user whose platform omits `updated` sees the pull deliver a correction
that never reaches the series. The docs suggest otherwise.

## Evidence
- Code read at 160b007: `_revision` returns `None` for a non-string or
  offset-less value.
- The wellness-pull reviewer's fake-transport run delivered day 2026-10-11
  without `updated`, with restingHR changed from 51 to 45. The drain
  archived it, reported `Conflicts: 1`, and the series kept 51 (reported,
  not re-run by the parent).
- wellness-pull `research.md` TBC-W3 records that every live record carries
  an offset `updated`, so it is unreachable on the maintainer's account.

## How to pick it up
1. Choose: document the limitation in `docs/connectors.md` § Wellness and
   `docs/wellness.md` § Archive and withdrawal; or have the pull stamp a
   delivery-order revision the merge can rank. That is an envelope or
   format change; weigh it against wellness-store's revision contract.
2. Pin whichever behaviour is chosen with a test.

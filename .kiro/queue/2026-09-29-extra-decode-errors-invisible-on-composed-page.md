---
id: 2026-09-29-extra-decode-errors-invisible-on-composed-page
title: On a composed page the Device and Data Quality section lists only the base file's decode errors, so a donating extra that decoded with errors reads as clean
status: open
importance: low
importance_why: Only bites when an extra has non-fatal decode errors and donates a channel; the page then states "Decode errors -- none" beside data from a file that had errors.
effort: S
kind: gap
area: channel-merge, src/fitdocs/render/sections.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, channel-merge writer)
pinned_at: f500dc1
resume_command: "/kiro-spec-requirements channel-merge [queue: .kiro/queue/2026-09-29-extra-decode-errors-invisible-on-composed-page.md] Decide whether a composed page shows each donating extra's decode errors"
context:
  - src/fitdocs/render/sections.py
  - .kiro/specs/channel-merge/requirements.md
  - .kiro/specs/channel-merge/design.md
blocked_by: [channel-merge]
---

## What
`devices_section` appends `_decode_errors(activity)`, which reads
`activity.provenance.decode_errors` only. After channel-merge, the composed
activity takes decode errors from the base and none from an extra (its
Req 1.5), and "showing an extra's ... decode errors" is an explicit
non-goal. `parse_fit` does not abort on non-fatal decode errors (they ride
on `Provenance.decode_errors`), so an extra can decode with errors and still
donate channels.

## Why it matters
The data-quality section is where a reader checks whether to trust a
channel. A donated channel from a damaged file sits under a "none" that is
true only of the base. Deliberate scope in channel-merge, recorded so the
decision can be revisited once composed pages exist.

## Evidence
- `src/fitdocs/render/sections.py:503-524` (`devices_section`) and
  `:588-594` (`_decode_errors`, reads `activity.provenance.decode_errors`).
- `src/fitdocs/ingest/__init__.py:47` -- decode errors do not abort.
- `.kiro/specs/channel-merge/requirements.md:86` (non-goal) and `:120`
  (Req 1.5, decode errors from the base); `design.md:46-49` (non-goal).

## How to pick it up
1. After channel-merge lands, read how its contributions record each extra
   (`SourceContribution`) and whether an extra's provenance survives there.
2. Decide with the maintainer: list each donating file's errors under its
   own label, or state on the page that errors are the base's only.
3. Either way the page must stop implying all its data decoded cleanly.

---
id: 2026-10-01-incoming-files-are-fully-decoded-twice-per-run
title: Every incoming file is fully decoded twice per run, once to read its identity key for planning and again for its page task
status: open
importance: medium
importance_why: Decode is a large share of per-file cost (reviewer-reported, unverified), and the extra pass scales with every new file of every sync, drain and pull --sync, with no benefit to output.
effort: M
kind: gap
area: activity-identity, fit-ingest, src/fitdocs/sync.py, src/fitdocs/ingest/
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-spec-design activity-identity [queue: .kiro/queue/2026-10-01-incoming-files-are-fully-decoded-twice-per-run.md] Amend the Performance section: decide between a key-only decode and keeping the planning parse, then specify it"
context:
  - .kiro/specs/activity-identity/design.md
  - src/fitdocs/sync.py
  - src/fitdocs/ingest/
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What
The run planner needs only each file's session key (sport, start, elapsed,
distance, device, kind) and session UUID, but obtains them from a full
`parse_fit`. The page task then reads the file again and runs `parse_fit` a
second time to render it. The design accepts this knowingly ("files not yet
archived parse twice (plan, then task)") but no key-only decode exists.

## Why it matters
A sync or inbox drain over N new files does about 2N full decodes
(`parse_fit`: message decode, developer fields, record arrays). A reviewer subagent measured the second decode at about 41% of
total sync time; that figure is unverified here (no real-sized file is in the
repo and the synthetic fixtures are too small to time meaningfully). Skipped
files (already archived) pay nothing; only new files do.

## Evidence
Read at `fc5c06d`.
- `src/fitdocs/sync.py:1409` `activity = parse_fit(data)` in the planning loop
  of `_run_planned` (builds `RunFile.key` via `session_key(activity)` at `:1414-1419`).
- `src/fitdocs/sync.py:1481-1493` `_reload` re-reads the bytes (verifying the
  hash), and `:1525` `activity = parse_fit(data)` in `_group_task`; `_NewMember`
  (`:1676`) carries the second parse into `_page_task`.
- `.kiro/specs/activity-identity/design.md:1959-1960` states the double parse as
  an accepted cost under "Performance".
- Not decoded twice, for the record: regen's per-page rebuild parses each listed
  archive file once (`sync.py:1910`).

## How to pick it up
1. Time first: decode a realistic multi-megabyte FIT file with `parse_fit` and
   compare with a decoder restricted to `file_id` + the session message, so the
   amendment is justified by a number that is in the repo, not recalled.
2. Choose the approach (Open questions), amend design.md's Performance section
   and the fit-ingest design if the key-only decoder is added to ingest, then
   task it.
3. Keep Req 3.10 / 4.8 intact: the plan must remain a function of the files and
   pages alone, so the key-only decode must produce a byte-identical
   `SessionKey` to the one `session_key(parse_fit(data))` builds (pin by
   equality over every fixture in `tests/fixtures/`).

## Open questions
- Key-only decode (new fit-ingest entry point, a second place that must agree
  with `parse_fit` on the identity fields) versus retaining the planning parse
  for the page task (memory held for a whole run's new files; a bounded cache
  is possible)?

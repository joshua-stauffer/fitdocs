---
id: 2026-09-30-devfieldspec-cannot-express-real-file-shapes
title: The fixture builder's DevFieldSpec cannot write a FIT-standard native slot or an endian-flagged base type
status: open
importance: medium
importance_why: fit-ingest 14.10 ('a developer field never fills a native channel') cannot be pinned against the likeliest real-world wrong implementation.
effort: S
kind: gap
area: running-dynamics fixtures, tests/fixtures/builder.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: extend tests/fixtures/builder.py DevFieldSpec with native_field_num and endian-flagged base types, then pin fit-ingest 14.10 and the base-type mask with them"
context:
  - tests/fixtures/builder.py
  - src/fitdocs/ingest/developer.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/running-dynamics/design.md
blocked_by: []
---

## What
`DevFieldSpec` (tests/fixtures/builder.py:~1068-1080) has no `native_field_num`, and `_description_mesg` (:~1093-1109) writes only `native_mesg_num`. The FIT-standard way a developer field shadows a native channel is `native_mesg_num` 20 (record) plus `native_field_num`, and no fixture can write it. Its `base_type` is also documented as an SDK BASE_TYPE code (4 for uint16), while real files carry the endian-flagged codes (0x84, 0x88).

## Why it matters
A filler keyed on the FIT-standard native slot, the most plausible way to wrongly honour native slots, cannot be pinned for fit-ingest 14.10 / running-dynamics 1.10. The base-type mask in `parse_field_descriptions` is exercised by one parse unit test only, never through a fixture-built file.

## Evidence
- Read at 8b07b9f: `base_type: int  # a garmin_fit_sdk BASE_TYPE code` and `native_mesg_num: int | None = None` in the DevFieldSpec class; there is no native_field_num.
- The 2.1 reviewer subagent reported (not re-run here) that dropping the base-type mask reds only `tests/ingest/test_developer.py::test_parse_field_descriptions_keeps_file_order_and_skips_unusable_ones`, and that the SDK returns 0x84 as int 132.

## How to pick it up
1. Add `native_field_num: int | None = None` to DevFieldSpec and write it in `_description_mesg`, keeping the default None so existing fixture bytes don't move (the builder's self-tests and every golden must stay byte-identical).
2. Allow a flagged base type (e.g. 0x84).
3. Add a test in tests/ingest/test_record_developer_fields.py where a developer field declares native_mesg_num 20 with a native_field_num naming heart_rate or power, and assert the native channel is untouched.
4. Add a fixture-built file with base type 0x84 that decodes correctly.
5. Done when a filler keyed on (20, native_field_num) reds the new test.

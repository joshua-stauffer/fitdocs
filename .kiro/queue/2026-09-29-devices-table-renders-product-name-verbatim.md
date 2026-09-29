---
id: 2026-09-29-devices-table-renders-product-name-verbatim
title: The devices table writes the file's own product_name text into the page verbatim, so a newline can forge a region-marker line and a pipe breaks the row
status: open
importance: medium
importance_why: Device strings are untrusted file content and connectors widens where files come from; a forged marker line leaves a page that every later regen refuses with a RegionError until someone hand-edits it.
effort: S
kind: bug
area: workout-docs, src/fitdocs/render/sections.py, src/fitdocs/ingest/summary.py, src/fitdocs/docmerge.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, intervals-connector writer)
pinned_at: f500dc1
resume_command: "do: in src/fitdocs/render/sections.py _devices_table, render the device name on one line (collapse every whitespace run to one space and strip, the rule intervals-connector's garmin_label applies to the same field) and escape the pipe character; add a render test whose device product_name holds a newline, a line shaped like a fitdocs region marker and a pipe, asserting one four-cell table row and that docmerge.extract_regions on the rendered page finds exactly the page's own regions"
context:
  - src/fitdocs/render/sections.py
  - src/fitdocs/render/format.py
  - src/fitdocs/ingest/summary.py
  - src/fitdocs/docmerge.py
  - .kiro/specs/intervals-connector/design.md
blocked_by: []
---

## What
`_devices_table` builds each row as `f"| {name} | {manufacturer} | ..."`
with `name = device.product_name or device.manufacturer or "Unknown device"`
and no escaping. `product_name` is whatever string the file recorded:
ingest's `_product_name` returns any `str` unchanged. A name containing a
newline followed by `<!-- fitdocs:begin:notes -->` puts a whole line at
column zero that `docmerge._MARKER_RE` (`^...$`, `re.MULTILINE`) accepts as
a region marker; a name containing `|` shifts the row's cells.
intervals-connector's new attribution line collapses whitespace in this same
field precisely so device text "can never span lines, form a heading or a
region marker"; the devices table on the same page does not. Pre-existing,
not introduced by Phase 8.

## Why it matters
A forged begin marker that repeats a real region id makes `extract_regions`
raise `RegionError` (duplicated id) on the next regen, so the page cannot be
regenerated until it is hand-edited; a balanced forged pair creates a region
that fitdocs then preserves as user content. `connectors` pulls files no
human looked at before they reached the inbox, so the input surface grows.

## Evidence
- `src/fitdocs/render/sections.py:527-539` -- `_devices_table`; the name at
  `:534`, the unescaped row at `:538`.
- `src/fitdocs/render/format.py:100-106` -- `cell()` returns the value
  verbatim (only `None` becomes the absence marker).
- `src/fitdocs/ingest/summary.py:372-383` -- `_product_name`: a recorded
  string `product_name`, else a string `product`, returned as is.
- `src/fitdocs/docmerge.py:63-66` -- `_MARKER_RE`, whole-line, multiline mode;
  `:99` `extract_regions` raises `RegionError` on a duplicated id.
- `.kiro/specs/intervals-connector/design.md` `garmin_label` (~:638-643) and
  `research.md` § Risks (~:364-365) -- the collapse rule and its reason.

## How to pick it up
1. Read `_devices_table` and `_manufacturer_cell`; decide whether the
   one-line rule belongs in a small shared helper in `render/format.py` that
   intervals-connector's `garmin_label` can also use (if IC has landed,
   reuse its helper rather than writing a second one).
2. Write the failing render test first (newline + marker-shaped line + pipe
   in `product_name`), then fix the table.
3. Grep the render layer for any other file-recorded string that reaches a
   table or line unescaped; list any you find in this item rather than
   widening the fix silently. Done when the test is green and no rendered
   page can contain a marker line that fitdocs did not write.

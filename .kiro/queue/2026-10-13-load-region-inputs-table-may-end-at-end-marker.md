---
id: 2026-10-13-load-region-inputs-table-may-end-at-end-marker
title: "A computed load region can end with its inputs table directly before the end marker; nobody has checked that every Markdown renderer ends the table at the marker line"
status: open
importance: low
importance_why: If a renderer folds the end-marker comment into the table, a generated page shows a stray row or a broken table; the common renderers very likely end the table at an HTML comment, but nothing in the repo shows it, and the newer morning block was built to avoid the question.
effort: S
kind: research
area: training-load, src/fitdocs/load/render.py, src/fitdocs/docmerge.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (workout-wellness spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: render a computed load region whose result has inputs_used but no notes, non-selected values or flags through markdown-it-py (a dev dependency, GFM tables enabled) and any other renderer the wiki is read in, and record whether the end-marker comment stays out of the table; if any renderer folds it in, end the region content with a blank line the way the morning block does [queue: .kiro/queue/2026-10-13-load-region-inputs-table-may-end-at-end-marker.md]"
context:
  - src/fitdocs/load/render.py
  - src/fitdocs/load/docedit.py
  - src/fitdocs/docmerge.py
  - .kiro/specs/workout-wellness/design.md
  - tests/load/test_render.py
  - pyproject.toml
blocked_by: []
---

## What

`render_computed` joins the load region's blocks with a blank line between
them, and the region is written as the begin marker, the content, then the end
marker, each on its own line, with exactly one newline between content and end
marker. When the result has `inputs_used` but no `notes`, no `non_selected`
and no `flags`, the last block is the inputs table, so the end-marker comment
`<!-- fitdocs:end:load -->` sits on the line directly after the table's last
row. GitHub-Flavored Markdown ends a table at a blank line or the start of
another block-level structure. Whether a single HTML comment line counts as
that inside a table is the unverified part: the repository has never checked
it against the renderers that display these pages (GitHub, editors, the PKM
the wiki plugs into).

## Why it matters

If a renderer treats the comment line as one more table row, the page shows a
stray row or loses the table. Because the marker is the boundary the splice and
the merge rely on, a "fix" that moves the marker would be a contract change, so
it is worth knowing before any. The morning block was specified to end with a
blank line before its end marker for exactly this reason ("a GFM table
otherwise swallows following non-blank lines", workout-wellness design), which
suggests the concern is real for some renderers.

## Evidence

Read at `86cdf14`; no renderer was run.

- `src/fitdocs/load/render.py:402-433` -- `render_computed`; the inputs table
  is built at `:419-422` and the blocks are joined with `"\n\n"` at `:433`,
  with no trailing newline.
- `src/fitdocs/load/docedit.py:237` -- the region text is
  `f"{begin}\n{content}\n{end}"`; `src/fitdocs/docmerge.py:89-96` -- the same
  layout for a freshly composed region.
- Whether the case occurs: `src/fitdocs/load/threshold/calculator.py:606-610`
  builds `notes` only from borrowings and the selected channel's notes, so a
  result with an anchored input table and no borrowing, no flags and no
  unselected value is constructible; no test or golden pins one.
- `.kiro/specs/workout-wellness/design.md:880-883` -- the morning region's
  content is "followed by one final `"\n"`, so a blank line separates the last
  table from the end marker (a GFM table otherwise swallows following
  non-blank lines)".
- `pyproject.toml:75` -- `markdown-it-py>=3.0` is a dev dependency, usable for
  the check; `tests/load/test_render.py:92-121` builds results with
  `inputs_used`.

## How to pick it up

1. Build the case: a `LoadResult` with `inputs_used` set and `notes`,
   `non_selected` and `flags` empty, rendered by `render_computed` and wrapped
   in the markers. Parse with `MarkdownIt("commonmark").enable("table")` (and
   `"gfm-like"`) and check whether the HTML comment token is a sibling of the
   table or inside it.
2. Check any other renderer the wiki is read in the same way, and read the
   GFM spec's section on tables for how a table is broken.
3. Record the result here. If every renderer ends the table, close the item
   and pin the case with a markdown-it test in `tests/load/test_render.py`. If
   any does not, end `render_computed`'s content with a blank line, after checking how
   `PRESERVED_REGIONS` and the load pass's staleness check treat the region
   content and whether the change needs a `DOC_VERSION` decision.

## Open questions

- Would a trailing blank line change the load payload round trip
  (`parse_payload`, `extract_regions` equality)? The invariant
  `extract_regions(replace_load_region(md, c))["load"] == c` is about the
  content as written, so it should hold; the picking-up session confirms.

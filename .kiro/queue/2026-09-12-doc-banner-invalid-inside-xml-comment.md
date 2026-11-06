---
id: 2026-09-12-doc-banner-invalid-inside-xml-comment
title: contract.DOC_BANNER contains " -- " and is therefore unusable as an XML/SVG comment marker
status: open
importance: high
importance_why: Any spec that stamps a provenance marker into an SVG with DOC_BANNER writes a file no XML parser accepts; load-history had to invent a private marker and the published contract does not say which marker the chart carries.
effort: S
kind: inconsistency
area: wiki-contract, load-history, src/fitdocs/contract.py, src/fitdocs/history/engine.py, docs/ownership-contract.md
created: 2026-09-12
surfaced_by: /kiro-impl load-history 5.2 (reviewer round 1)
pinned_at: 8cd0062
resume_command: "do: give fitdocs.contract an XML-safe generated marker (no `--` inside the comment) that is_generated recognises, have history/engine.py use it instead of its module-local _CHART_MARKER, and name the chart's marker in docs/ownership-contract.md's training-history subsection"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/history/engine.py
  - tests/history/test_engine.py
  - docs/ownership-contract.md
blocked_by: []
---

## What
`contract.DOC_BANNER` reads `<!-- ... -- see this directory's AGENTS.md ... -->`.
XML 1.0 §2.5 forbids `--` inside a comment, so an SVG prefixed with it fails
`xml.etree.ElementTree.fromstring` at column 104. load-history 5.2 shipped
`history/engine.py::_CHART_MARKER = "<!-- fitdocs:generated -->"` as a
module-local workaround so the foreign-file check can recognise its own chart.

## Why it matters
The next spec that writes an SVG (or any XML) and wants the foreign-file
rule will either copy the workaround or repeat the defect. The ownership
contract describes the generated marker for documents but says nothing
about what marks the chart.

## Evidence
`uv run python -c "import xml.etree.ElementTree as ET; from fitdocs import contract; ET.fromstring(contract.DOC_BANNER + '\n<svg/>')"` → ParseError, column 104.
`tests/history/test_engine.py::test_the_written_chart_is_well_formed_xml_and_recognized_as_generated` pins the workaround; reverting to DOC_BANNER reds it.

## How to pick it up
Read `contract.py`'s banner/`is_generated` block, then `engine.py:60-75`.
Add an XML-safe marker constant to the contract (one line; `is_generated`
must match it), switch the engine, keep the engine test, add a contract
test that the marker parses inside `<svg>`. Done when no module under
`src/` spells its own generated marker.

## Also (validation 2026-09-12, coverage reviewer, Req 5.8)
The same banner's prose -- "everything outside the notes/workout/load
regions is replaced" -- is reused verbatim at the top of the history page,
which has no regions at all; `history/AGENTS.md` says the opposite ("no
user-owned region of any kind"). Whatever marker the fix introduces, the
region-less document type needs region-less wording, and
`tests/history/test_page.py` should pin that the history page's banner
names no region.

## Update 2026-11-06: most of this is resolved by the banner reword
`DOC_BANNER` now holds no `--` and names no region (wiki-contract Amendment 16), and `tests/test_contract.py` pins that it parses inside an XML comment. So the defect in this item's title is gone, along with the region-less wording in "Also". What remains is smaller: `history/engine.py`, `recovery/engine.py` and `dashboards/storage.py` each spell `f"{GENERATED_PREFIX} -->"` themselves, and `docs/ownership-contract.md` does not say what marks a chart. Close it if a shared constant isn't wanted; importance should drop either way.

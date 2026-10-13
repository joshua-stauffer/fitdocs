---
id: 2026-10-13-dashboards-test-helper-has-a-literal-bom
title: tests/dashboards writes the byte-order mark as an invisible literal U+FEFF inside string literals
status: open
importance: low
importance_why: An invisible character in source is lost by an editor that strips BOMs or a formatter that normalises, and a reader cannot see what the test builds.
effort: S
kind: chore
area: dashboards, tests/dashboards/_helpers.py, tests/dashboards/test_storage.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 3.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: replace the literal U+FEFF characters in tests/dashboards/_helpers.py:67 and tests/dashboards/test_storage.py:325,333,381 with the escape \\ufeff and run tests/dashboards [queue: .kiro/queue/2026-10-13-dashboards-test-helper-has-a-literal-bom.md]"
context:
  - tests/dashboards/_helpers.py
  - tests/dashboards/test_storage.py
blocked_by:
  - dashboards
---

## What
`page_text(bom=True)` appends a byte-order mark with a literal U+FEFF character
typed into the string, and `test_storage.py` builds its BOM pages the same way.
The character is invisible in most editors and diffs.

## Why it matters
A tool that strips or normalises a leading or embedded BOM (an editor save, a
formatter) silently turns the BOM tests into tests of a page with no BOM, and
nothing fails. Req 16.5 (keep a page's line endings and any leading BOM) is the
behaviour these tests pin.

## Evidence
Scanned at 0a98d5c with Python (`'\ufeff' in line`) and grep:
- `tests/dashboards/_helpers.py:67`: `out.append("<U+FEFF>")` inside `if bom:` (line 66).
- `tests/dashboards/test_storage.py:325`: `raw = "<U+FEFF># Pace\r\nπ run\r\n".encode()`.
- `tests/dashboards/test_storage.py:333` and `:381`: the same literal in expected-text strings.

(`<U+FEFF>` stands for the invisible character itself, which is what is in the file.)

## How to pick it up
1. Replace each literal with `"\ufeff"` (or a module constant `BOM = "\ufeff"` in `_helpers.py`, imported by `test_storage.py`).
2. Run `uv run pytest tests/dashboards -q`; the suite must be unchanged.
3. Mutation check: strip the BOM from `read_page` or `replace_page` output and confirm the BOM tests go red.

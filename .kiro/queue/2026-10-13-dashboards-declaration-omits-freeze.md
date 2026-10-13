---
id: 2026-10-13-dashboards-declaration-omits-freeze
title: The dashboards AGENTS.md declaration says chart regions are rewritten after an index refresh and when `fitdocs dashboard refresh` runs, and omits `fitdocs dashboard freeze`
status: open
importance: low
importance_why: The declaration is what an agent reads before touching dashboards/; it under-lists one of the three triggers that rewrite a region, so an agent could treat a region as stable across a freeze.
effort: S
kind: inconsistency
area: wiki-contract, dashboards, src/fitdocs/declaration.py, tests/declaration_golden/dashboards.AGENTS.md
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add `fitdocs dashboard freeze` to the trigger list in src/fitdocs/declaration.py _DASHBOARDS_DIRECTIVE, regenerate the golden with `uv run python -m tests.test_declaration_goldens`, and check whether the wiki-contract amendment text needs the same words [queue: .kiro/queue/2026-10-13-dashboards-declaration-omits-freeze.md]"
context:
  - src/fitdocs/declaration.py
  - tests/declaration_golden/dashboards.AGENTS.md
  - tests/test_declaration_goldens.py
  - .kiro/specs/wiki-contract/requirements.md
  - docs/ownership-contract.md
blocked_by:
  - dashboards
---

## What
The generated `dashboards/AGENTS.md` ends its directive paragraph with "rewrites
only the bytes between those markers, after a successful index refresh and when
`fitdocs dashboard refresh` runs." A `fitdocs dashboard freeze` run also
rewrites a chart's region (it points the region at a new snapshot), and a
`refresh` or `freeze` run also deletes stale images. The sentence lists two of
the three region-writing triggers.

## Why it matters
The declaration is the short, always-present statement of what fitdocs does to
this directory. Its text is pinned as a byte golden, so the omission is
deliberate-looking and will persist until someone notices.

## Evidence
- `src/fitdocs/declaration.py:354-359`: `_DASHBOARDS_DIRECTIVE` ends "... those markers, after a successful index refresh and when `fitdocs dashboard refresh` runs. Edit the prose, frontmatter and directives freely; do not edit inside a chart region."
- `tests/declaration_golden/dashboards.AGENTS.md:6` carries the same sentence.
- `docs/ownership-contract.md:917` lists `fitdocs dashboard freeze` among the writers ("`fitdocs dashboard freeze` takes a new snapshot of the targeted ..."), and dashboards Req 11.1 (`.kiro/specs/dashboards/requirements.md:240`) has freeze "point the chart's region at the new snapshot".

## How to pick it up
1. Edit `_DASHBOARDS_DIRECTIVE` to name `fitdocs dashboard freeze` (keep the sentence short; wiki-contract Req 3.11 limits what the declaration restates, see `2026-10-13-wiki-contract-3-11-vs-dashboards-declaration-grammar-wording`).
2. Regenerate the golden with `uv run python -m tests.test_declaration_goldens` and review the diff.
3. Check whether a declaration text change needs a contract-version or CHANGELOG entry (the declaration carries the contract version identifier, `CONTRACT_VERSION` is "10"); the answer decides whether this is a trivial-class change under `.kiro/steering/change-protocol.md`.

## Open questions
Whether to list the triggers at all, or say "when a dashboard command or the pass after an index refresh runs", which cannot go stale.

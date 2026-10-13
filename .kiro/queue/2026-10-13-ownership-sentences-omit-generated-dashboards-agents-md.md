---
id: 2026-10-13-ownership-sentences-omit-generated-dashboards-agents-md
title: The ownership sentences for dashboards/ (CHANGELOG, contract head, layout, declaration) say fitdocs writes only chart regions and the files in assets/, and omit the generated dashboards/AGENTS.md it also writes
status: open
importance: low
importance_why: Each sentence is a published promise of what fitdocs writes under dashboards/; read literally it is false by one file that the same documents tell the user to expect.
effort: S
kind: docs
area: wiki-contract, dashboards, src/fitdocs/declaration.py, src/fitdocs/layout.py, src/fitdocs/contract.py, CHANGELOG.md, docs/ownership-contract.md
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 8.2 reviewer)
pinned_at: 0a98d5c
resume_command: "do: reword the dashboards ownership sentence in declaration.py, layout.py, contract.py, CHANGELOG.md and docs/ownership-contract.md to include the generated dashboards/AGENTS.md declaration, regenerate the declaration golden (uv run python -m tests.test_declaration_goldens), and run the contract and declaration tests [queue: .kiro/queue/2026-10-13-ownership-sentences-omit-generated-dashboards-agents-md.md]"
context:
  - src/fitdocs/declaration.py
  - src/fitdocs/layout.py
  - src/fitdocs/contract.py
  - CHANGELOG.md
  - docs/ownership-contract.md
  - tests/declaration_golden/dashboards.AGENTS.md
blocked_by:
  - dashboards
---

## What
fitdocs writes `dashboards/AGENTS.md` (the ownership declaration, placed by
`ensure_declarations`). The sentences that describe what fitdocs owns under
`dashboards/` list the chart regions and `dashboards/assets/` and stop there.

## Why it matters
"fitdocs writes only the chart regions inside them and the files in
`dashboards/assets/`" is the sentence the declaration itself prints into
`dashboards/AGENTS.md`, directly above a file fitdocs wrote. The confinement
guard permits the write (the directory is in `OWNED_PATHS`), so behaviour is
right; the published text is what is incomplete.

## Evidence
At 0a98d5c:
- `src/fitdocs/declaration.py:343-346`: `_DASHBOARDS_PAGES` = "The pages in `dashboards/` belong to the athlete; fitdocs writes only the chart regions inside them and the files in `dashboards/assets/`." (also in `tests/declaration_golden/dashboards.AGENTS.md`).
- `src/fitdocs/layout.py:137-139` (`DASHBOARDS_DIR` docstring) and `:158-160` (`OWNED_PATHS` docstring): "fitdocs writes only the chart regions inside them and the files under `dashboards/assets/`".
- `src/fitdocs/contract.py:403-410` (the version 10 note): "its pages belong to the athlete, while fitdocs owns their chart regions and `dashboards/assets/`" and, in the next sentence, tells the user to run `fitdocs sync` once "to place `dashboards/AGENTS.md`".
- `CHANGELOG.md:91-94`: "where only the chart regions and the chart images and snapshots under `dashboards/assets/` are fitdocs's. Action: run `fitdocs sync` or `fitdocs regen` once to place `dashboards/AGENTS.md`."
- `docs/ownership-contract.md:6-10` repeats the contract note.

## How to pick it up
1. Choose the wording once ("... and the generated `dashboards/AGENTS.md`") and apply it to the five places above.
2. The declaration text is byte-pinned: regenerate the golden with `uv run python -m tests.test_declaration_goldens` and review the diff.
3. `docs/ownership-contract.md` is generated or pinned from `contract.py` (check which direction before editing). Check whether a published-text change advances `CONTRACT_VERSION` or needs a CHANGELOG entry under `.kiro/steering/change-protocol.md`.

## Open questions
Same as `2026-10-13-dashboards-declaration-omits-freeze`: fix both in one declaration-text change so the golden is regenerated once.

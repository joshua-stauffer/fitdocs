---
id: 2026-10-13-wiki-contract-3-11-vs-dashboards-declaration-grammar-wording
title: Wiki-contract Req 3.11 says the declaration shall not restate the directive grammar, while the dashboards declaration names the opener text and the begin/end marker forms
status: open
importance: low
importance_why: A requirement and the text it governs may disagree depending on how much naming a marker counts as restating the grammar; the declaration is byte-pinned, so the reading has to be settled before anyone edits it.
effort: S
kind: research
area: wiki-contract, dashboards, src/fitdocs/declaration.py, .kiro/specs/wiki-contract/requirements.md
created: 2026-10-13
surfaced_by: /kiro-validate-impl dashboards (design dimension, UNCLEAR)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-requirements wiki-contract [queue: .kiro/queue/2026-10-13-wiki-contract-3-11-vs-dashboards-declaration-grammar-wording.md] settle what 'shall not restate the directive grammar' permits the dashboards declaration to name"
context:
  - .kiro/specs/wiki-contract/requirements.md
  - src/fitdocs/declaration.py
  - tests/declaration_golden/dashboards.AGENTS.md
  - docs/dashboards.md
blocked_by:
  - dashboards
---

## What
Req 3.11 (Amendment 5) ends: "The declaration shall not restate the directive
grammar, which the published contract and the dashboards documentation locate."
The emitted dashboards declaration says a page declares a chart in "a hidden
`<!-- fitdocs:chart ... -->` directive" and that fitdocs maintains "a region
between `<!-- fitdocs:begin:chart:<id> -->` and `<!-- fitdocs:end:chart:<id> -->`".
Naming the opener and the two marker spellings is arguably the minimum an agent
needs to avoid editing inside a region (the same requirement also demands "must
not be edited"), and arguably a restatement of the grammar.

## Why it matters
Whoever next edits the declaration (see `2026-10-13-dashboards-declaration-omits-freeze`
and `2026-10-13-ownership-sentences-omit-generated-dashboards-agents-md`) cannot
tell whether the existing marker names are compliant or are the thing to remove.
The validate-impl reviewer marked the design "UNCLEAR", not wrong.

## Evidence
- `.kiro/specs/wiki-contract/requirements.md:322`: the 3.11 sentence quoted above.
- `src/fitdocs/declaration.py:350-359` (`_DASHBOARDS_DIRECTIVE`) and `tests/declaration_golden/dashboards.AGENTS.md:6` carry the opener `<!-- fitdocs:chart ... -->` and the begin and end markers with `<id>`.
- The full directive grammar (keys, YAML body, `sql` rules) is in `docs/dashboards.md` and is not in the declaration, which supports the compliant reading.

## How to pick it up
1. Decide the reading with the maintainer: (a) naming the opener and markers is compliant, restating the grammar would be listing keys, modes or the body shape; or (b) the declaration should point at the guide and name no spelling.
2. If (a), add one clarifying clause to 3.11 ("naming the opener and the region markers is not restating the grammar"). If (b), edit `_DASHBOARDS_DIRECTIVE`, regenerate the golden (`uv run python -m tests.test_declaration_goldens`) and make sure "do not edit inside a chart region" is still actionable without the markers.
3. Record the decision in the wiki-contract design so the next amendment does not reopen it.

## Open questions
The decision above; it is the maintainer's to make, hence `/kiro-spec-requirements`.

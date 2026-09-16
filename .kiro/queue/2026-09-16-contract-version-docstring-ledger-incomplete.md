---
id: 2026-09-16-contract-version-docstring-ledger-incomplete
title: contract.CONTRACT_VERSION's docstring records only the 1 -> 2 bump; 2 -> 3 and 3 -> 4 are missing
status: open
importance: low
importance_why: The constant's docstring is the in-code ledger of why the published contract moved; two of three bumps are unrecorded, so a reader must reconstruct them from git.
effort: S
kind: docs
area: wiki-contract, src/fitdocs/contract.py
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks 1.2 (reviewer FOLLOW_UPS)
pinned_at: 68fe42e
resume_command: "do: extend the CONTRACT_VERSION docstring in src/fitdocs/contract.py with one paragraph each for 2 -> 3 (load-history: history/ and history/assets/ owned, a second document type) and 3 -> 4 (training-blocks: blocks/ owned, two further document types, a user-owned plan-source location), in the shape of the existing 1 -> 2 paragraph"
context:
  - src/fitdocs/contract.py
  - docs/ownership-contract.md
  - .kiro/specs/wiki-contract/requirements.md
blocked_by: []
---

## What
`src/fitdocs/contract.py:273` -- "Bumped ``1`` -> ``2`` (Req 6.3) because a
stated guarantee about what ..." is the only bump the docstring records. The
literal is now `"4"`. Both the load-history bump (task 1.2, 2026-09-11) and
the training-blocks bump (task 1.2, 2026-09-16) were made under the
"one string literal" rule and left the docstring alone by instruction.

## Why it matters
The published document (`docs/ownership-contract.md`) carries the "what
changed at this version" preamble; the code-side ledger should agree with it
or say nothing. Half a ledger is worse than none.

## Evidence
- `grep -n 'Bumped' src/fitdocs/contract.py` -> 273 only.
- `docs/ownership-contract.md:3-9` -- the version-4 preamble, the source of
  the two missing paragraphs.
- `.kiro/specs/wiki-contract/requirements.md` Amendments 2 and 3.

## How to pick it up
1. Read the existing paragraph and the two amendments.
2. Add two paragraphs; no test pins the docstring, so read it back once.
3. Done when the three bumps read as one ledger. Owner: wiki-contract.

---
id: 2026-07-28-reexport-test-module-prose-and-dead-param
title: The citation re-export test module has a misdescribing docstring, a dead parameter, and a half-inapplicable rationale comment
status: open
importance: low
importance_why: Three small accuracy defects in code that shipped green and reviewer-APPROVED. None affects behavior or coverage — the walk is stricter than its docstring claims, which is the safe direction. Filed because this exact species (prose asserting something the code does not do) cost fit-ingest task 8.1 three of its four review rounds, and because neither ruff nor mypy can see any of the three.
effort: S
kind: docs
area: fit-ingest, tests/load/channels/test_sources_citation_reexport.py, src/fitdocs/load/channels/sources.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 8.2 review — found by reading docstrings sentence-by-sentence, all three outside the prose-claim grep vocabulary)
pinned_at: 067a30e
resume_command: "do: Fix the three accuracy defects in tests/load/channels/test_sources_citation_reexport.py and sources.py:99 named in this item — drop 'top-level', remove or use the dead `module` parameter, and correct the unused-imports half of the alias rationale"
context:
  - tests/load/channels/test_sources_citation_reexport.py
  - src/fitdocs/load/channels/sources.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

Three unrelated accuracy defects, all in task 8.2's diff, all non-blocking and
all invisible to `ruff` and `mypy`:

1. **`_class_def_names` docstring misdescribes its own walk.** It says the
   helper finds every `.py` file under `src/fitdocs` containing a *top-level*
   `class <name>` definition. The code uses `ast.walk(tree)`, which visits every
   descendant node, so it also catches a class nested inside a function or
   another class. The code is **stricter** than documented — the safe direction,
   and correct per task 8.1's "walk the WHOLE module" lesson — but the sentence
   is wrong. Drop "top-level".

2. **Dead parameter that misdirects the reader.** `_class_def_names(module: object, class_name: str)`
   never uses `module`. Both call sites pass `sources_module`, which reads as
   though the walk were rooted at that module; the root actually derives from
   `citation_module.__file__`. Since the whole point of the helper is *which
   tree it scans*, a parameter implying the wrong root is worse than no
   parameter. Remove it, or use it and make the root explicit.

3. **Half of the alias rationale does not apply.** `src/fitdocs/load/channels/sources.py:99`
   says the explicit `as` aliases mark both names as intentional re-exports,
   *"not unused imports"*. Both names **are** used in the module body
   (`Final[Citation]`, `VerificationStatus.PRIMARY_TEXT`, six constructor
   calls), so under the plain form `ruff` reports no unused import at all —
   verified. The `no_implicit_reexport` half is the entire reason the aliases
   are load-bearing; the unused-import half is inapplicable here and dilutes a
   comment whose job is to stop someone collapsing those aliases.

## Why it matters

Low, and deliberately `docs` rather than `gap`. No coverage is missing and no
behavior is wrong.

The reason to record it rather than shrug: `.kiro/steering/change-protocol.md`
§ "Prose is not evidence" holds that a false claim is worse than none because it
tells the next editor the coverage exists. Defect 1 is that shape — a reader
trusting it would believe a nested `class VerificationStatus` slips the guard,
when it does not. Defect 3 is the same shape pointed at a comment specifically
written to prevent a dangerous edit; weakening its stated reason weakens the
warning.

Note how all three were found: by **reading every docstring sentence against the
code**, not by the mandated `verified|caught|proven|tracked|...` grep, which
returned CLEAN over the whole diff. That grep's vocabulary does not match
sentences describing what a mechanism does or why it exists. Task 8.1 hit this
three rounds running. Recorded here as a fourth data point.

## Evidence

At `067a30e`, all confirmed by the task 8.2 reviewer:

- Defect 1 — mutation C: adding `class VerificationStatus` **nested inside a
  function body** in `src/fitdocs/metrics/power.py` reddened the tree-wide count
  test (sole failure). A top-level-only walk would not have caught it.
- Defect 2 — `_class_def_names(module: object, class_name: str)`; the body never
  references `module`. Neither `ruff` nor `mypy` flags it: the file is outside
  `[tool.mypy].files`, and an unused *parameter* is not an unused import.
- Defect 3 — mutation H: collapsing the aliases to the plain form leaves
  `uv run ruff check .` clean, confirming no unused-import diagnostic exists to
  suppress. The same mutation leaves `pytest`, `ruff format --check` and
  `uv run mypy` green too, which is the separate hazard tracked at
  `2026-07-28-mypy-perimeter-membership-unguarded`.

Negative control worth preserving (mutation D): `class VerificationStatus` in a
comment and in a string literal leaves the suite green — the scan is AST-based,
not grep-based, so it produces no false positives. Any rewrite must keep that
true.

## How to pick it up

1. Open `tests/load/channels/test_sources_citation_reexport.py`.
2. Fix 1: delete "top-level" from the `_class_def_names` docstring, or say
   explicitly that it walks every descendant.
3. Fix 2: drop the unused `module` parameter and update both call sites — or, if
   the root really should come from the passed module, use it and delete the
   `citation_module.__file__` derivation. Do not leave both.
4. Fix 3: in `src/fitdocs/load/channels/sources.py:99`, cut the "not unused
   imports" clause and keep the `no_implicit_reexport` reason, which is the one
   that is true and the one that stops the dangerous edit.
5. Done looks like: every sentence in the diff matches what the code does, the
   four re-export tests still pass, and the negative control still holds — a
   `class VerificationStatus` in a comment or string must not red anything.
   Re-run mutations C and D from the evidence above to confirm neither the
   strictness nor the no-false-positive property regressed.

## Open questions

None.

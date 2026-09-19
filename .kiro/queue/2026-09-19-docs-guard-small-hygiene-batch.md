---
id: 2026-09-19-docs-guard-small-hygiene-batch
title: Small docs-guard hygiene: unpinned README compatibility link, overclaiming docstrings, over-broad prose, and a bare-path detector edge
status: open
importance: low
importance_why: None changes behaviour; each is a guard whose claim is slightly wider or narrower than what it pins.
effort: S
kind: chore
area: distribution, tests/test_docs_guarantees.py, tests/test_install_docs.py, README.md, CHANGELOG.md, src/fitdocs/cli.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: pin README's direct link to docs/compatibility.md (Req 3.7); narrow the no-built-in-calculator guard docstring to the scoped corpus; make the bare-path detector ignore blob URLs pinned to non-main refs or document that it flags them; tighten CHANGELOG/regen 'from the data root alone' wording; fix cli.py's module docstring command count; mark the 5.2 attribution phrase pin polarity-bearing"
context:
  - README.md
  - docs/compatibility.md
  - tests/test_docs_guarantees.py
  - tests/test_install_docs.py
  - CHANGELOG.md
  - src/fitdocs/cli.py
blocked_by: []
---

## What
README.md:~210 links the compatibility policy but only docs/index.md's link is pinned; the no-built-in-calculator guard docstring predates the corpus narrowing in 5.7; the bare-path detector flags any non-main blob URL; the CHANGELOG regen entry says regen works from the data root alone (it re-decodes archived .fit bytes); cli.py's docstring says nine commands and enumerates seven.

## Why it matters
Guards whose prose is wider than their assertion teach the next session the wrong invariant.

## Evidence
Validation coverage report SPOT_CHECKS 'Weak' and finding 7; Implementation Notes 5.2, 5.7; retained reviewer FOLLOW_UPS 2026-09-19.

## How to pick it up
Work through the list top to bottom; each is a one-line edit plus, where a pin is added, its mutation. Done when every named docstring states exactly what its assertion checks.

---
id: 2026-09-19-verify-artifact-test-hermeticity-and-doc-divergence
title: 6.3's verify-artifact execution test is non-hermetic, and docs/releasing.md step 6/10 differ from the workflow bodies in ways no test pins
status: open
importance: medium
importance_why: The non-hermetic test can go online on a cold cache; the doc says the manual and automated paths 'never quietly diverge' while three small divergences are unpinned.
effort: M
kind: inconsistency
area: distribution, tests/test_release_workflow.py, docs/releasing.md, .github/workflows/release.yml
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: port tests/test_release_workflow.py's verify-artifact execution test to the hermetic executor used by the 6.4 tests (fake HOME/XDG dirs, dead proxies, warm UV_CACHE_DIR, --no-cache->--offline), then either pin the shared lines between docs/releasing.md steps 6/10 and the verify-artifact/verify-published bodies or state the deliberate differences in the doc"
context:
  - tests/test_release_workflow.py
  - docs/releasing.md
  - .github/workflows/release.yml
  - tests/test_releasing_docs.py
blocked_by: []
---

## What
Divergences: step 6 installs with `--offline`, the workflow does not (no runner cache) and additionally runs `plugins` and a version-equality `test`; step 10's manual command has no retry while the workflow retries 6x30s and runs `--help`. Separately, `uv tool install --from` is not documented for the uv version in use (0.11) though it works.

## Why it matters
The releasing doc's central promise (Req 5.10) is that the two paths cannot diverge; today it is approximately true and only the job names and the three gate commands are pinned.

## Evidence
Implementation Notes 6.3, 6.4; validation coverage report DOCS_VS_AUTOMATION and finding 5 (2026-09-19).

## How to pick it up
Start from tests/test_release_workflow.py's 6.4 hermetic helpers; then decide per divergence: pin or document. Done when the verify-artifact test passes with dead proxies from a cold shell and the doc's 'same sequence' sentence is either literally true or qualified.

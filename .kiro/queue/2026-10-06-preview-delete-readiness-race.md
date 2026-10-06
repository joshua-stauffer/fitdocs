---
id: 2026-10-06-preview-delete-readiness-race
title: Wait for the retained page after deletion before testing preview failure preservation
status: open
importance: medium
importance_why: A timing-dependent baseline test blocks unrelated canonical regression gates.
effort: S
kind: bug
area: docs-site, tests/sitebuild/test_preview.py
created: 2026-10-06
surfaced_by: /kiro-impl analytics-index task 7.1 review2 and debug1
pinned_at: 53d4a24
resume_command: "do: fix the post-deletion readiness race in tests/sitebuild/test_preview.py before introducing malformed content; preserve all existing HTTP, content, failure-report and source-preservation assertions [queue: .kiro/queue/2026-10-06-preview-delete-readiness-race.md]"
context:
  - tests/sitebuild/test_preview.py
  - scripts/sitebuild/preview.py
  - scripts/sitebuild/generator.py
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What

`test_live_preview_serves_edits_adds_deletes_failures_and_fixes` waits for the
deleted route to return 404, then writes malformed content. That 404 can occur
while Zensical is still rebuilding the last valid tree. The later `/why/`
assertion can therefore observe temporary missing HTML instead of the completed
retained page. Wait boundedly for `/why/` to serve `EDITMARKERONE` after deletion
before introducing the malformed content.

## Why it matters

The canonical analytics-index review failed this unchanged test twice even
though the task-local checks passed. The same timing failure was reproduced on
the immutable revision before the CLI task. This is test synchronization;
the investigation established no CLI regression or production contract defect.

## Evidence

- `tests/sitebuild/test_preview.py:1156` waits only for the deleted route's 404;
  `:1179` expects the retained `/why/` response to be 200 after a fixed sleep.
- At `53d4a24`, a diagnostic preserving the original status assertion observed
  `DEBUG broken initial 404 html False staged True`, then
  `DEBUG recovers while broken 200 elapsed 1.0616353747900575 html True` without
  changing malformed content. The original assertion still failed.
- Adding only the bounded post-deletion retained-page wait on that baseline
  passed every original assertion: `1 passed in 19.43s`. Diagnostic edits were
  restored byte-identically. One diagnostic pass does not prove every possible
  preview race is eliminated.
- Candidate and pre-CLI baseline uninstrumented exact tests also passed once,
  confirming timing dependence. The exact command is
  `uv run --python /Users/josh/.pyenv/versions/3.11.15/bin/python3.11 --group docs pytest tests/sitebuild/test_preview.py::test_live_preview_serves_edits_adds_deletes_failures_and_fixes -q`.
- Parent inspected raw debug outputs. Full artifacts are under
  `/private/tmp/analytics-index-evidence/7.1/debug1/`: `REPORT.md`,
  `baseline-trace-1.txt`, `baseline-synchronization.txt`, `candidate-exact.txt`,
  `baseline-exact.txt`, and `restoration-and-identity.txt`.

### Distinct added-page observation (analytics-index 8.2)

At pre-steering base `9ecf5a7`, a canonical run failed at
`tests/sitebuild/test_preview.py:1154` / helper `:1023` with
`not within 20.0s: the added page`: 9,384 passed, one failed and two expected
actionlint skips. Its exact retry passed in 25.88s. Raw evidence is
`/private/tmp/analytics-index-evidence/8.2/review2/canonical-full.txt` and
the exact-retry output in that directory. The controller inspected the raw
failure and debugger report; it did not independently rerun the trace.

The debugger's current pre-steering baseline detected, built, staged and
served the added page within 4.16s, then candidate and baseline both hit the
separate later deletion/404 assertion. The original failed fixture had
already been removed, so its intermediate build/sync/HTTP state was
unavailable. The added-page timeout's internal cause remains unresolved
(MEDIUM confidence in transient preview-readiness classification); these
observations do **not** establish the deletion race as its cause or the
post-deletion wait as its fix. Diagnostic edits were restored. See
`/private/tmp/analytics-index-evidence/8.2/debug1/REPORT.md`,
`baseline-trace.txt` and `source-proof.json`.

The task was accepted only after an unchanged retry passed a fresh canonical
run: 9,385 passed, two expected skips, exit 0. Evidence:
`/private/tmp/analytics-index-evidence/8.2/review2-debug1-retry/VERDICT.md`.
The earlier failed run remains a failure. This item still owns the known
post-deletion synchronization repair; this extra observation bounds what
that repair can claim to resolve.

## How to pick it up

1. Read the live-preview test's delete/break sequence and its bounded
   `wait_for`, `served`, and `unchanged_across` helpers, then the docs-site
   preservation requirements and preview/generator code.
2. Add the retained-page readiness wait after deletion using those helpers.
   Keep the original failure-status/content/source-preservation assertions and
   child cleanup. Build a controlled timing case to discriminate the readiness
   guard rather than relying only on an intermittently green live run.
3. Run the exact live-preview test and relevant sitebuild suite through
   `uv run --group docs pytest`, plus static checks. Use the project's correct
   interpreter and warm uv cache. Do not patch analytics-index around this test.
4. If the separate added-page deadline recurs during verification, capture
   polling build start/end, staged/HTML existence, sync containing the added
   page, generator process status and HTTP status **at the timeout, before
   fixture cleanup**. Diagnose that state before proposing another fix;
   preserve the timeout and original assertions instead of attributing it
   automatically to the post-deletion race.

---
id: 2026-10-18-preview-source-write-truncation-race
title: Valid live-preview fixture writes can expose truncated source and emit a persistent diagnostic
status: open
importance: medium
importance_why: An upstream fixture race fails unrelated required CI despite successful preview recovery.
effort: S
kind: bug
area: docs-site, tests/sitebuild/test_preview.py
created: 2026-10-18
surfaced_by: /kiro-impl workout-wellness task 5.1 branch CI and delegated Astra investigation
pinned_at: cc1f6b4
resume_command: "do: reproduce the preview fixture write/read truncation overlap under a controlled schedule, then publish complete valid fixture edits without weakening malformed-input and source-preservation assertions [queue: .kiro/queue/2026-10-18-preview-source-write-truncation-race.md]"
context:
  - tests/sitebuild/test_preview.py
  - scripts/sitebuild/preview.py
  - scripts/sitebuild/content.py
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/requirements.md
  - .kiro/queue/2026-10-06-preview-delete-readiness-race.md
blocked_by: []
---

## What

The live-preview integration test publishes valid replacements with
`Path.write_text`, exposing a truncation interval to the independently polling
preview reader. A transient incomplete source can produce a validation message
that remains in cumulative test output even after the valid page is served.
This is distinct from the historical HTTP deletion-generation readiness race.

## Why it matters

The unchanged site test failed the required DOCS workflow of an unrelated
workout-wellness candidate. A passing retry satisfies that run's gate only;
it does not repair this fixture publication race.

## Evidence

At `cc1f6b4b6ce9bd126c13659c8b055d6602c2475d`, DOCS workflow
[39107794553, attempt 1](https://github.com/joshua-stauffer/fitdocs/actions/runs/39107794553/attempts/1)
ran `FITDOCS_REQUIRE_SITE_TOOLING=1 uv run --group docs pytest tests/sitebuild
tests/test_docs_workflow.py` on Linux CPython 3.11.17. Actual result:
`1 failed, 753 passed, 3 skipped in 26.68s`, exit 1. The failing assertion is
`tests/sitebuild/test_preview.py:1178`, `assert out.text() == ""`, with:

```text
why.md: no frontmatter: the file must begin with a line ---
```

The test had already received the retained page containing
`EDITMARKERONE DELETEGENERATIONREADY`, before writing deliberately invalid
`section: Nowhere`. All preceding intended versions start with `---`.
`test_preview.py:49-54` uses `path.write_text`; `content.py:241` independently
reads bytes and `:250-254` emits this message when the opening fence is absent.
`LockedOut` protects its cumulative buffer, not source publication. The
preservation hashes start after the writer returns and cannot observe the
truncation interval. Relevant site source/tests, docs workflow and lockfile
are unchanged between main `f94c503` and this feature head.

The controller inspected the actual failed GitHub log. Delegated Astra found
HIGH confidence in the exposed race and upstream ownership, MEDIUM confidence
in this precise historical interleaving: no per-read bytes/timing trace was
captured, so the failing write phase remains unknown. No controlled overlap
reproduction or fix was executed in this session. Exactly one unchanged
failed-job rerun was requested; the first failure remains a failure. Required
passing CI on the final candidate is unchanged.

All 473 root queue frontmatters and related preview bodies plus the roadmap
were checked. The related October 6 item covers HTTP readiness and unresolved
propagation timeouts; it does not own this source-validation/write mechanism.

## How to pick it up

1. Read the writer, polling preview loop, source reader and failing test above.
   Capture source size/first line and writer phase before fixture cleanup.
2. In an isolated copy, pause the writer after truncation and before writing;
   demonstrate the reader/diagnostic overlap with bounded waits and child
   cleanup. If that discriminator rejects the proposed cause, investigate
   the captured evidence before changing code.
3. If confirmed, publish valid fixture updates as complete files (for example,
   same-directory atomic replacement). Preserve real malformed-section edits
   and every existing HTTP, content, output, source-hash and cleanup assertion.
   Verify the controlled case and full site suite; do not guess a production
   debounce/retry fix, erase output or inflate timeouts to hide the race.

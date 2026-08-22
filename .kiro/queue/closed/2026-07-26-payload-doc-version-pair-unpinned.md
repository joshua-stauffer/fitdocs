---
id: 2026-07-26-payload-doc-version-pair-unpinned
title: Nothing ties LOAD_PAYLOAD_VERSION to DOC_VERSION, so a sibling can bump one alone
status: done
importance: medium
importance_why: Req 11.5's whole point is that documents needing regeneration stay detectable from frontmatter; a lone bump breaks that silently.
effort: S
kind: gap
area: training-load, src/fitdocs/load/render.py, src/fitdocs/contract.py
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-payload-doc-version-pair-unpinned.md] Pin the payload-version/doc-version pair so bumping either alone reddens"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/render.py
  - src/fitdocs/contract.py
  - tests/load/test_render.py
blocked_by: []
---

## What
Requirement 11.5: "when the result format changes, the CLI shall change the document-format version". Task 2.4 executed the one-time bump (payload v2, `DOC_VERSION` 2->3) but nothing enforces the ongoing rule. A second, smaller instance of the same weakness: `tests/load/test_engine.py:701` asserts the recorded format version reached a skip message with `assert "1" in skip_entry.detail`, which also passes for 10, 11, 12, 21.

## Why it matters
A sibling spec bumping `LOAD_PAYLOAD_VERSION` without bumping `DOC_VERSION` leaves documents that need regeneration undetectable from their frontmatter -- exactly what 11.5 forbids. Four specs are queued to extend the load payload. Partially mitigated today: `test_payload_version_is_two` reddens on the bump and forces a human to look, but nothing tells them about the pair.

## Evidence
`grep -rn 'LOAD_PAYLOAD_VERSION ==' tests/` returns only `tests/load/test_render.py:136`; it never appears alongside `contract.DOC_VERSION` in any assertion. Verified at 3121bb6.

## How to pick it up
Open `tests/load/test_render.py:136`. Replace the lone constant assertion with one recording the `(LOAD_PAYLOAD_VERSION, DOC_VERSION)` tuple, with a failure message naming the other constant and Req 11.5. While in the area, change `tests/load/test_engine.py:701` to assert the exact token (`f"version {stamp.version}"`) rather than a bare digit. Done when bumping either constant alone reddens with a message that names the other.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`daadc4c`. The pair is asserted together with a failure message naming the other constant and Req 11.5. Honestly non-sole (7 and 13 tests redden, as `DOC_VERSION` is load-bearing). The bare-digit `"1" in detail` assertion now asserts the exact token, proven by a version-21 mutation the old form would have passed.

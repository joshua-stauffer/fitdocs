---
id: 2026-10-17-apple-test-builder-devices-classify-as-other
title: The Apple test builders' WATCH and PHONE presets say manufacturer "Apple", which production classifies as OTHER
status: open
importance: low
importance_why: A test trap, not a product defect; a future test using the presets as-is silently exercises the OTHER-writer path.
effort: S
kind: chore
area: apple-health-import, tests/wellness/apple/builders.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (apple-health-import reviewer finding 3; confirmed by the parent)
pinned_at: 160b007
resume_command: "do: change the WATCH and PHONE presets in tests/wellness/apple/builders.py to manufacturer:Apple Inc. (or rename them so the OTHER classification is explicit) and re-run tests/wellness/apple [queue: .kiro/queue/2026-10-17-apple-test-builder-devices-classify-as-other.md]"
context:
  - tests/wellness/apple/builders.py
  - src/fitdocs/wellness/formats/apple/reduce.py
  - .kiro/specs/apple-health-import/research.md
blocked_by: []
---

## What
`tests/wellness/apple/builders.py:22-31` defines `WATCH` and `PHONE` with
device strings containing `manufacturer:Apple`. `writer_of`
(`src/fitdocs/wellness/formats/apple/reduce.py:165-167`) recognizes only
`("Apple Inc.", "Watch")` and `("Apple Inc.", "iPhone")`. With the presets,
production classifies both writers as OTHER, so their physiology is
excluded. Existing tests override the device (for example `_APPLE_WATCH` in
`test_import.py`), so the suite is green.

## Why it matters
The names promise an Apple Watch and an iPhone. A new test that trusts them
asserts against the wrong path, and could pass by accident: an absent value
reads the same as an excluded one.

## Evidence
Read at 160b007: the builder lines above, and `reduce.py:165-167`. The
manufacturer string itself is a [verify] item of research.md awaiting the
maintainer's real-export smoke (task 6.2*).

## How to pick it up
1. Switch the presets to `manufacturer:Apple Inc.` and run
   `uv run pytest tests/wellness/apple -q`. Expect failures only where a test
   relied on OTHER classification. Fix those tests to name an explicit OTHER
   preset.
2. If 6.2* later shows real exports say something else, revisit both.

---
id: 2026-10-05-index-rebuild-swap-untested-on-windows
title: The index rebuild's os.replace swap with a reader open is verified only on macOS; CI never runs Windows
status: open
importance: low
importance_why: Windows users with an outside DuckDB client open would hit the design's staged-rebuild fallback path, which no CI run exercises.
effort: M
kind: research
area: analytics-index, .github/workflows/ci.yml
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-index spec writer)
pinned_at: 19fc92e
resume_command: "do: after analytics-index lands, run its rebuild-swap and staged-fallback tests on a Windows runner (one-off workflow_dispatch job or a local VM) and record the result in the analytics-index research.md; queue a CI matrix entry if they fail"
context:
  - .kiro/specs/analytics-index/design.md
  - .kiro/specs/analytics-index/research.md
  - .github/workflows/ci.yml
blocked_by: [analytics-index]
---

## What
analytics-index rebuilds into a temp file and `os.replace`s it over the live
index. Discovery measured that this works on macOS with a reader open; on
Windows an open handle can make the replace fail, and the design falls back
to a staged rebuild that the next `fitdocs index` swaps in. CI runs Ubuntu
only (`.github/workflows/ci.yml:41`), so neither path is exercised on Windows.

## Why it matters
The fallback is the only thing between a Windows user and a stuck index; an
untested fallback is a claim, not a behavior.

## Evidence
- `.github/workflows/ci.yml:41` at 19fc92e: ubuntu runner only.
- Roadmap Phase 10 "A rebuild writes a temp file and os.replaces it into place. Measured on macOS with a reader open. Windows is verified in the design."

## How to pick it up
1. Find the swap and fallback tests analytics-index adds (tests/index/).
2. Run them on Windows once; record the outcome.

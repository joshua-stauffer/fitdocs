---
id: 2026-09-10-blocked-constant-record-shape-defined-twice
title: Two per-package record shapes for "constant blocked pending a citation" — consider one shape in fitdocs.citation
status: open
importance: low
importance_why: Both shapes are blocked by the same roadmap reading task; a third package would invent a third shape, but nothing is wrong today and both specs now cross-reference each other.
effort: S
kind: chore
area: performance-benchmarks, load-history, src/fitdocs/citation.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch cross-spec review (Phase 6), issue I8
pinned_at: 1089b92
resume_command: "do: once both packages have shipped, either lift performance/sources.py's PendingConstant + BLOCKED_METHODS and history/sources.py's BlockedPreset + BLOCKED_PRESETS into one blocked-constant record in src/fitdocs/citation.py, or record in citation.py's module docstring why per-package shapes are the rule (precedent: Divergence in load/channels/sources.py)"
context:
  - src/fitdocs/citation.py
  - .kiro/specs/performance-benchmarks/design.md
  - .kiro/specs/load-history/design.md
  - src/fitdocs/load/channels/sources.py
blocked_by: [performance-benchmarks, load-history]
---

## What
performance-benchmarks records the unverified 0.95 × 20-minute FTP factor as
a `PendingConstant` in `PENDING_CONSTANTS` with the method in
`BLOCKED_METHODS`; load-history records the unverified 42/7-day Performance
Management Chart constants as a `BlockedPreset` in `BLOCKED_PRESETS`. Both
are blocked by the same roadmap Direct Implementation Candidate (verify the
Allen & Coggan 2nd-edition page locators). `fitdocs.citation` holds the
shared citation shapes and has no blocked-constant shape.

## Why it matters
One governance concept in two shapes across two packages is how a third gets
invented. The cross-spec remediation added a cross-reference in each design,
which is enough for now; a shared shape is a small refactor once both exist.

## Evidence
- `.kiro/specs/performance-benchmarks/design.md` — the `PENDING_CONSTANTS` /
  `BLOCKED_METHODS` bullet in the sources component.
- `.kiro/specs/load-history/design.md` — the `BlockedPreset` /
  `BLOCKED_PRESETS` bullet in the sources component.
- `src/fitdocs/citation.py` — module docstring: shapes only.
- `src/fitdocs/load/channels/sources.py:104` — `Divergence`, the per-package
  precedent.

## How to pick it up
1. Read both sources modules once shipped and `citation.py`.
2. If the two shapes differ only in field names, lift one into `citation.py`
   and migrate both; if they differ in meaning, write the docstring sentence.
3. Both purity guards must stay green; `citation.py` is already an allowed
   import for both packages.

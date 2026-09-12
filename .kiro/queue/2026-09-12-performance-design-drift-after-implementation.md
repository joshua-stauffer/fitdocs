---
id: 2026-09-12-performance-design-drift-after-implementation
title: performance-benchmarks design.md/requirements.md drifted from the shipped implementation
status: open
importance: medium
importance_why: Multiple design/requirements claims no longer match the code that shipped, undermining the design doc as a reliable reference for the next session.
effort: S
kind: docs
area: performance-benchmarks, .kiro/specs/performance-benchmarks/design.md, requirements.md
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: amend design.md/requirements.md per the list; every claim verified against the shipped code at d4fbc6f"
context:
  - .kiro/specs/performance-benchmarks/design.md
  - .kiro/specs/performance-benchmarks/requirements.md
  - src/fitdocs/performance/engine.py
  - src/fitdocs/performance/types.py
  - src/fitdocs/load/channels/sources.py
blocked_by: []
---

## What

A consolidated list of design/requirements claims that drifted from the
shipped implementation:

- § The pass mermaid places `load_profile` before discovery; the implemented
  (and controller-expected) placement is after the loop.
- § The pass mermaid's "alt dry run or nothing accepted → nothing written"
  and the 4.3 bullet contradict Req 6.4 (sole tag removed must delete its
  entry); the engine takes Req 6.4's reading — a run that empties a
  non-empty derived subset still writes. Record this reading in the design.
- § PassEngine Service Interface lacks `summaries: tuple[QuantitySummary, ...]`.
- The "unreadable document" failure class in § PassEngine is unreachable:
  `docio.read_frontmatter` never raises (returns `None` on
  `OSError`/`UnicodeDecodeError`), so an unreadable page is filtered by
  `is_workout_document(None)` and silently not counted — same as the load
  pass. Wording should say "unreadable archive" or acknowledge the silent
  skip.
- § Allowed Dependencies says models/derive import `fitdocs (Samples)` /
  `fitdocs (Activity, Modality, Sport)`, but the code imports from
  `fitdocs.model` and never imports `Modality`.
- § Modified Files says `tests/test_confinement.py` gets "no other change",
  but a document-less writing entry point needed the per-entry-point `wrote`
  predicate generalisation — record it.
- Whether `stat()`/`exists()` on an untagged archive counts as "resolve"
  under Req 1.3 is decided only by the test's patched method set; one
  sentence in § PassEngine would make it definitional.
- Req 4.8 says the limits of agreement are "for the derivation method it
  used", while the design mandates Borszcz's 20-minute-protocol LoA carried
  on the 50–70 min TT mean — reconcile requirement text and design.
- Req 6.1 read literally ("shall never modify, replace, or delete a
  benchmark entry that carries no derivation provenance") forbids the
  prompt's own same-date replace; scope the wording to "when the derivation
  pass writes".
- The collision decline's observed/required pair (candidate value / existing
  value) is unspecified, though 4.4 renders them — decide and pin.
- The Riegel validity window's closed-interval choice (closed at both ends)
  is a fitdocs comparison choice with no recorded justification in
  `sources.py`/design.

## Why it matters

The design doc is the reference a later session reads before touching the
pass; each of these is a place where reading only the design would produce a
wrong mental model of the shipped behavior.

## Evidence

- (4.3 r2 reviewer) mermaid placement of `load_profile`.
- (4.3 reviewer) mermaid/6.4 contradiction; design prose, S.
- (4.3 r2 reviewer) missing `summaries` field in Service Interface.
- (4.2 reviewer) unreadable-document failure class unreachable; spec prose, S.
- (5.1 r2 reviewer) Allowed Dependencies wording stale vs measured imports
  (`fitdocs.model` for Samples/Activity; no `Modality`).
- (4.5 reviewer) Modified Files "no other change" claim vs the `wrote`
  predicate generalisation needed for a document-less writing entry point.
- (4.2 r2 reviewer) untagged-archive "resolve" definition decided only by
  the test's patched method set.
- (3.3 reviewer) Req 4.8 method/LoA mismatch (50–70 min TT mean vs Borszcz's
  20-minute protocol).
- (5.3 reviewer) Req 6.1 wording forbids the prompt's own same-date replace.
- (4.3 r2 reviewer) collision decline's observed/required pair unspecified.
- (3.1 r2 reviewer) Riegel validity-window inclusivity has no recorded
  justification.

## How to pick it up

1. Read `.kiro/specs/performance-benchmarks/design.md` and
   `requirements.md` alongside the current `engine.py`/`types.py`.
2. Work through the list above one bullet at a time, verifying each against
   the shipped code before editing prose.
3. Where a reading is being pinned (e.g. Req 6.4's), state it explicitly as
   the adopted reading, not as a rewrite that erases the prior ambiguity.
</content>

## Additional drift (2026-09-12, feature-level validation)

- Req 8.6 says a corroborating record carries "its own locator"; the four
  corroborators (`DRAKE_2024`, `MCGEHEE_2005`, `DUMKE_2006`, `BORSZCZ_2018`)
  ship `locator=None` because they are honestly unread -- amend the wording
  ("a locator once read") or record the exception.
- § Per-quantity gates puts `Dated` before `Sport`; `derive()` returns
  `SPORT_NOT_COVERED` for an undated swim page (the sport branch precedes any
  leaf's undated gate; the `(3.1)` ruling governs leaves only).
- § File Structure Plan's `tests/performance/` tree omits
  `test_single_writer.py` (named later in § Guards).
- § Modified Files omits `pyproject.toml` (mypy scope), `tests/load/test_settings.py`
  and `tests/test_effort_tags_e2e.py` (both disclosed cross-spec edits).

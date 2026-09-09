---
id: 2026-09-10-riegel-1981-primary-text-unread
title: Read Riegel (1981) so the endurance-exponent citation stops being secondary attestation
status: open
importance: medium
importance_why: performance-benchmarks ships the Riegel single-race path with the constant marked SECONDARY_ATTESTATION; until the primary text is read the derived threshold pace carries a weaker citation than every other constant in the package.
effort: S
kind: research
area: performance-benchmarks, src/fitdocs/performance/sources.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch (performance-benchmarks design, wave 2)
pinned_at: 1251a98
resume_command: "do: obtain and read Riegel, P. S. (1981) 'Athletic records and human endurance', American Scientist 69(3), confirm the 1.06 exponent and the distance range it was fitted over, then upgrade the entry in src/fitdocs/performance/sources.py from SECONDARY_ATTESTATION to a primary citation with the page locator, keeping Drake et al. 2024 as corroboration"
context:
  - .kiro/specs/performance-benchmarks/design.md
  - .kiro/specs/performance-benchmarks/research.md
  - .kiro/specs/performance-benchmarks/brief.md
  - .kiro/steering/roadmap.md
blocked_by: []
---

## What
Riegel's power law is the path performance-benchmarks uses to turn one tagged
race into a one-hour pace. The 1981 American Scientist article is JSTOR-only
and has not been read by anyone on this project; the 1.06 exponent is taken
from Riegel 1977 as attested by Drake et al. 2024. The spec therefore
records the constant as secondary attestation in `BLOCKED_CITATIONS` rather
than blocking the method outright.

## Why it matters
Citation discipline is a stated Phase 6 constraint: a constant either cites
to a page of a primary source or is recorded as a fitdocs choice. Leaving the
one constant that touches every running derivation on secondary attestation
is the weakest link in the provenance chain the athlete sees on the page.

## Evidence
- `.kiro/steering/roadmap.md` Phase 6 › Constraints: "Riegel's power law
  (1981 …) cites as *secondary attestation* until the JSTOR-only 1981 text is
  read".
- `.kiro/specs/performance-benchmarks/brief.md` Constraints table, Riegel row.
- `.kiro/specs/performance-benchmarks/design.md` § sources: the
  `SECONDARY_ATTESTATION` marker and the `BLOCKED_CITATIONS` table.

## How to pick it up
1. Get the article (JSTOR, or a university library copy).
2. Confirm the exponent, the fitted distance range, and whether the paper
   itself states 1.06 or only the 1977 value.
3. Edit the citation record in `sources.py` and the design's sources table
   in one change; the derived numbers do not move, only their provenance.

## Open questions
Whether a reading task without a code change still wants the worktree
ritual — it does, because `sources.py` and the spec change together.

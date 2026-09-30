---
id: 2026-09-29-stryd-balance-side-convention-unknown
title: Whether Stryd's three balance developer fields record a left-side share or a signed difference is unknown, so running-dynamics labels no side
status: open
importance: low
importance_why: The page is honest without a side label (Req 7.5); settling the convention could only add L/R labels, not fix a wrong value.
effort: S
kind: research
area: running-dynamics, .kiro/specs/running-dynamics/research.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, running-dynamics writer)
pinned_at: f500dc1
resume_command: "do: on one maintainer-local Stryd file, read the three balance developer-field descriptors (name, units, scale, offset, base type) and the rounded range and centre of their values -- a centre near 50 suggests a share, a centre near 0 with both signs a signed difference; record descriptors and shapes only (no file name, date or value) in .kiro/specs/running-dynamics/research.md § Stryd developer-field names, and open a running-dynamics amendment only if a side can be established"
context:
  - .kiro/specs/running-dynamics/research.md
  - .kiro/specs/running-dynamics/requirements.md
  - .kiro/specs/running-dynamics/design.md
blocked_by: []
---

## What
running-dynamics recognises `Leg Spring Stiffness Balance`,
`Impact Loading Rate Balance` and `Vertical Oscillation Balance` by name.
No public source consulted establishes whether each is a left-side share or
a signed left-right difference, so the page shows the recorded percentage
with no side (Req 7.5) and gates balances on their paired stride channel
instead of treating zero as a placeholder (Req 5.3).

## Why it matters
Low. The one gain is a meaningful L/R label; without it a reader cannot tell
which leg a skewed value favours.

## Evidence
- `.kiro/specs/running-dynamics/research.md` § "Stryd developer-field names"
  (~:82-102: "Whether a Stryd balance is a left-side share or a signed
  difference is not established by any public source consulted") and
  § Risks (~:264-265).
- `.kiro/specs/running-dynamics/requirements.md:182` -- Req 7.5, no side.

**Rendered consequence (2026-09-30, running-dynamics at 8b07b9f).** running-dynamics Req 5.3 keeps a recorded 0.0 balance, so the `stryd_run` golden (tests/render/golden_docs/stryd_run.md) shows Vertical oscillation balance average 48.4 % beneath its own 10th percentile, 49.0 %. A single mid-run 0.0 at fixture record 12 drives it. That is spec-conforming but physically implausible for a balance. Decide it together with the side convention, possibly as an activity-qa-flags plausibility rule.

## How to pick it up
1. Read the two research passages and Req 5.3 / 7.5.
2. Run the descriptor-and-shape read in a scratch directory outside the
   repository and the data root; print nothing identifying.
3. A share still does not say which side it measures; label a side only if a
   public statement or the descriptor itself names one. Otherwise record the
   finding and close this item.

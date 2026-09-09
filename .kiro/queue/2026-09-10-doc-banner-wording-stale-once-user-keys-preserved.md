---
id: 2026-09-10-doc-banner-wording-stale-once-user-keys-preserved
title: Reword DOC_BANNER's "everything outside the regions is replaced" once user-owned keys are preserved
status: open
importance: low
importance_why: The banner sits in every generated document, but rewording it forces a DOC_VERSION bump that rewrites the whole archive, so it must ride on the next bump taken for another reason.
effort: S
kind: docs
area: effort-tags, src/fitdocs/contract.py
created: 2026-09-10
surfaced_by: /kiro-spec-batch (effort-tags design, wave 1)
pinned_at: 1251a98
resume_command: "do: at the next DOC_VERSION bump, reword DOC_BANNER in src/fitdocs/contract.py so it no longer claims everything outside the notes/workout/load regions is replaced on regeneration (user-owned effort keys are preserved once effort-tags ships); move the banner golden tests in the same change"
context:
  - src/fitdocs/contract.py
  - .kiro/specs/effort-tags/design.md
  - docs/ownership-contract.md
blocked_by: [effort-tags]
---

## What
`DOC_BANNER` in `src/fitdocs/contract.py` tells the reader that everything
outside the notes/workout/load regions is replaced on regeneration. Once
effort-tags ships, the user-owned frontmatter keys (`effort`,
`effort_distance_m`, `effort_time_s`, `effort_event`) survive regeneration,
so the sentence becomes a simplification that is wrong for the one case the
athlete most cares about.

## Why it matters
The banner is the first line of every generated document and the one
statement of the ownership rule an athlete reads without opening the docs.
It will say the tag is discarded when the tag is in fact preserved.

## Evidence
- `src/fitdocs/contract.py:340-343` — `DOC_BANNER` text: "everything outside
  the notes/workout/load regions is replaced on regeneration".
- effort-tags `design.md` § Open Questions and `spec.json.phase_note`
  (commit c574cfb on `chore/spec-batch-phase6`) record the deferral: the
  brief forbids a `DOC_VERSION` bump unless one is forced, and any banner
  change is a byte change in every document.

## How to pick it up
1. Wait for whichever change next bumps `DOC_VERSION` for its own reason.
2. In that same change, reword `DOC_BANNER` to name what is preserved
   (regions plus user-owned keys) rather than what is replaced.
3. Regenerate the golden documents and confirm the banner tests and the
   `docs/ownership-contract.md` wording agree.

## Open questions
None — the wording itself is a small editorial call for the bump's author.

---
id: 2026-10-18-platform-grades-pre-publish-checks
title: Archive unarchived terms and settle five open facts before publishing the platform grades page
status: open
importance: medium
importance_why: The page publishes grades about named companies; three of its cited terms documents have no archive copy, and five grade-relevant facts were unresolved at writing.
effort: S
kind: docs
area: website/content/philosophy/platform-grades.md
created: 2026-10-18
surfaced_by: writing website/content/philosophy/platform-grades.md (branch m/docs_improvements)
pinned_at: c097732
resume_command: "do: Archive the three unarchived terms documents named in this item, resolve its five open facts, and update website/content/philosophy/platform-grades.md where a grade or wording changes"
context:
  - website/content/philosophy/platform-grades.md
  - docs/website.md
blocked_by: []
---

## What
`website/content/philosophy/platform-grades.md` grades 18 fitness platforms,
as of 2026-10-18, on programmatic access to your own data (Access) and on what
their terms let you do with it (Freedom). Every grade cites a primary terms
document. Two loose ends remain before it goes live:

- **Three cited documents have no Wayback Machine snapshot**, so a later edit
  to them would leave the page's quotes unverifiable.
- **Five facts that bear on a grade were open** when the page was written.

## Why it matters
- **Accuracy is the page's only authority.** It quotes named companies'
  terms; one quote that can no longer be checked undermines it.
- **It will go stale.** Four of the 18 platforms changed their API terms in
  the four months before it was written.
- **Merging is publishing.** `main` deploys `fitdocs.ai` through GitHub
  Pages (`docs/website.md`, "Maintainer runbook"), so these checks belong
  before the merge.

## Evidence
**Terms documents with no Wayback snapshot** (reported by the research
subagents on 2026-10-18; the absence was not re-checked in this run):

1. Intervals.icu API Terms and Conditions:
   `https://forum.intervals.icu/t/intervals-icu-api-terms-and-conditions/114087`
2. Stryd Terms of Use PDF:
   `https://storage.googleapis.com/stryd_static_assets/legal/stryd-terms-of-use-4-6-21.pdf`
3. Stryd Privacy Policy (not cited on the page):
   `https://www.iubenda.com/privacy-policy/137798/legal`

**Open facts.** Each is worded on the page as unconfirmed; grep the page for
the platform's `###` heading.

1. **Hammerhead account review.** The page grades Access A. The support
   article (2025-11-21) documents self-serve developer accounts, but the API
   License Agreement still says to request a key "by emailing", and whether
   SRAM reviews accounts isn't stated. If SRAM reviews them, Access becomes B
   and Hammerhead drops to 4th.
2. **Garmin's agreement and individual access.**
   - Whether the 2026-03-03 Connect Developer Program Agreement (the PDF
     linked on the page) binds US developers is unconfirmed.
   - On 2026-10-14 the Intervals.icu developer reported hearing of "an easier
     path for individuals". If Garmin announces one, Access could change from
     F.
3. **Suunto MCP fidelity.** `https://mcp.suunto.com/mcpguide`, first
   archived 2026-10-11, doesn't document whether it returns FIT files or
   streams. Full-fidelity FIT would raise Access from C.
4. **Withings dates conflict.** Withings+ applies to accounts created after
   2026-10-12, per the plans page. The new API terms are effective
   2026-10-13. The page uses both, as each source gives them; confirm that
   both dates are right.
5. **Samsung Freedom.** The page grades B. A strict reading of the SDK
   agreement's purpose limit, plus its written-agreement requirement for any
   third party such as a cloud model, could justify C, which moves Samsung
   from 6th to 9th. This is a judgement call, not a missing fact.

## How to pick it up
1. **Archive the three documents** with the Wayback Machine's Save Page Now
   (`https://web.archive.org/save/<url>`). Optionally add each snapshot link
   next to its terms link on the page.
2. **Re-check the five facts** against the live sources. Change the page
   only where a fact changed. Keep its scoring rule (A=4 through F=0; rank by
   the sum; ties by Access, then alphabetically) and re-rank if any grade
   moves.
3. **Rebuild** with `uv run --group docs python -m scripts.build_site build`
   from the repository root. It must print `built N pages`.
   - Done means: the three documents are archived, each open fact is
     resolved or still marked unconfirmed on the page, and the build is
     green.

## Open questions
- **Review cadence.** Should the page carry a re-grade date, for example a
  quarterly check of all 18 terms documents, and who owns it? That is the
  maintainer's call.

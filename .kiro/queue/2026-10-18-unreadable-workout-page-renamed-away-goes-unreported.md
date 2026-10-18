---
id: 2026-10-18-unreadable-workout-page-renamed-away-goes-unreported
title: An unreadable workout page renamed away from its computed stem is silently duplicated by regen, and `fitdocs check` does not report it
status: open
importance: medium
importance_why: The user sees two pages for one activity with no warning anywhere; the hand-edited page with their notes is the one fitdocs no longer recognises.
effort: M
kind: gap
area: activity-identity, src/fitdocs/sync.py, src/fitdocs/audit.py, src/fitdocs/identity/pages.py
created: 2026-10-18
surfaced_by: independent review of chore/q-regen-pages (queue-prerelease session)
pinned_at: 972aa0e
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-18-unreadable-workout-page-renamed-away-goes-unreported.md] Report workouts/*.md pages whose frontmatter cannot be read, in regen and/or fitdocs check"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/audit.py
  - src/fitdocs/identity/pages.py
  - .kiro/queue/closed/2026-10-01-regen-writes-over-or-beside-an-unreadable-page.md
blocked_by: []
---

## What

972aa0e made regen warn when it seeds a page beside an unreadable file at the
computed stem, and refuse to write over an unmatched file. It deliberately did
not add a general report of unreadable pages. Remaining hole, reproduced by the
reviewer: garble a synced page's frontmatter (e.g. `date: 2026-02-30`), rename
it to `workouts/my-race.md`, run `fitdocs regen` -> written
`workouts/<stem>.md`, failures (), warnings (); both files exist. `fitdocs
check` also stays silent: `src/fitdocs/audit.py` (~765) skips any page whose
frontmatter is None as "not a fitdocs workout document".

## Why it was not fixed

Reporting every unreadable page needs the page scan to return skipped paths,
which touches the `PageIndex` signature (~24 call sites), and whether `check`
should report non-fitdocs files under `workouts/` is a product choice (a plain
note placed there is legitimate). The parse_frontmatter item's own open
question ("should check report it?") is the same decision.

## Done when

A maintainer decides where unreadable `workouts/*.md` pages are reported
(regen warning, `check` finding, both), and that path is implemented with an
end-to-end test of the renamed-away case.

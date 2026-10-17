---
id: 2026-10-17-recovery-source-changes-across-gaps-and-sleep-sources
title: Recovery page omits source changes that follow a gap, and its Sleep section never names its source or changes (Req 5.5, 5.6)
status: open
importance: medium
importance_why: The page silently continues across two different measurements, which is exactly what Req 5 exists to prevent.
effort: S
kind: gap
area: recovery, src/fitdocs/recovery/view.py, src/fitdocs/recovery/page.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (recovery reviewer, NO-GO; confirmed by the parent in code and on a real-data page)
pinned_at: 160b007
resume_command: "/kiro-impl recovery [queue: .kiro/queue/2026-10-17-recovery-source-changes-across-gaps-and-sleep-sources.md] State source changes across gaps and name Sleep's sources"
context:
  - src/fitdocs/recovery/view.py
  - src/fitdocs/recovery/page.py
  - tests/recovery/test_view.py
  - .kiro/specs/recovery/requirements.md
  - .kiro/specs/recovery/design.md
blocked_by: []
---

## What
Two Req 5 gaps on the recovery page:
1. **Source changes after a gap are not stated.** In `_signal`
   (`src/fitdocs/recovery/view.py:146-149`), `previous = item.source` is
   reset to `None` on every day with no shown source. A change from source A
   to source B across a gap longer than the six-day carry is therefore never
   compared, never listed, and the "baseline is the new source's own"
   sentence never appears. `tests/recovery/test_view.py:166-185` pins this
   narrow reading (c → b after a gap is not listed). The design
   (`design.md:648-649`, "the previous window day's non-None shown source")
   reads more naturally as "the latest earlier day that had a source".
2. **The Sleep section states neither changes nor sources.**
   `page.py:308-328` renders only the chart and the table. The table does not
   name the shown source, and no `Sources shown` line or change lines are
   printed, although `SleepView.total` is a `SignalView` that already
   computes `changes` and `sources`. Other-signal panels never print their
   origins in text either (Req 5.6).

## Why it matters
Req 5.5: "When the shown source of a signal changes within the window, the
recovery page shall state each day it changed ...". Req 5.6: "name, for
each source it shows, the source's identifier and the origins". The
optional maintainer task 6.3* exists to check exactly the source switches
(Garmin export → Apple Health → intervals.icu), which are separated by gaps.

## Evidence
- Code read at 160b007: `view.py:146-149`, `page.py:288-328`.
- Recovery reviewer staged root (synthetic, `write_series`): Garmin
  export, a 10-day gap, then Apple Health, then intervals.icu. Resting HR
  stated only the Apple → intervals change. HRV (rMSSD) showed two sources
  and stated no change. A sleep-only root stated neither the change nor the
  origins.
- On the maintainer's real-data sample page, the Sleep section printed no
  source line; the HRV and resting-HR sections did. The parent confirmed
  this in the page text.

## How to pick it up
1. Get a one-line ruling recorded in the design: a change is measured
   against the latest earlier window day that had a shown source. Then
   change `view.py` to keep `previous` across `None` days, and flip
   `test_view.py:166-185`.
2. Render `changes` and `sources` for the Sleep section, the same way
   `_signal` does in `page.py`, and name the shown source in the sleep table
   heading or caption.
3. Decide whether the Other Signals panels need an origins sentence for Req
   5.6, or whether the panel title's source suffices.

---
id: 2026-10-13-forgotten-activity-delivery-older-than-listing-window-never-refetched
title: "A forgotten activity delivery older than the listing window is never listed again, contradicting connectors Req 8.7 that the next pull fetches it again"
status: open
importance: medium
importance_why: Silent data loss of one activity per occurrence, most likely right after a first full-history pull when old deliveries sit unarchived in the inbox; the docs and the requirement both promise the opposite.
effort: M
kind: bug
area: connectors, src/fitdocs/connectors/delivery.py, src/fitdocs/connectors/pull.py, src/fitdocs/connectors/ledger.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (wellness-pull spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "/kiro-spec-design connectors [queue: .kiro/queue/2026-10-13-forgotten-activity-delivery-older-than-listing-window-never-refetched.md] Make a forgotten activity delivery older than the listing window come back on the next pull, as wellness-pull does for wellness by lowering its mark"
context:
  - src/fitdocs/connectors/delivery.py
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/ledger.py
  - .kiro/specs/connectors/requirements.md
  - .kiro/specs/connectors/design.md
  - .kiro/specs/wellness-pull/design.md
  - docs/connectors.md
blocked_by: []
---

## What

When an activity delivery vanishes from the inbox before the drain archives it
(the athlete deleted or moved it), the pull's sweep "forgets" the activity's
ledger entry so that a later pull fetches it again (connectors Req 8.7). The
fetch only happens if the activity is listed, and the listing window starts at
the watermark less the instance's `lookback_days` (default 30). The watermark
never moves backward. An activity whose start is older than that window is
therefore never listed again, so it is never re-fetched, unless the athlete
happens to pass `--since` with an early enough date. The sweep forgets it
correctly; nothing then brings it back.

wellness-pull closes the same gap for wellness deliveries by lowering its own
mark when a delivery is forgotten (its design, below). The activity side has
no equivalent.

## Why it matters

The failure is silent: the entry is gone from the ledger, no report names it,
and the activity is simply missing from the wiki. The window is short (30
days by default) while a first pull lists a whole history, so every
history-era delivery that vanishes before the drain runs is affected, not just
recent ones. `docs/connectors.md` tells the athlete the opposite.

## Evidence

Read at `86cdf14` (static reading; no run).

- `src/fitdocs/connectors/delivery.py:296-300` -- in `sweep`, an entry whose
  archive copy is absent and whose pending file is absent is dropped:
  `result = result.without(entry.remote_id)`.
- `src/fitdocs/connectors/ledger.py:171-180` -- `without` copies the ledger
  with the same watermark.
- `src/fitdocs/connectors/pull.py:221-234` -- `_window_start`: `--since` if
  given, else `watermark - timedelta(days=lookback_days)`, else `None`; used at
  `:426-428`. The sweep runs first (`:380`), the listing after (`:445`).
- `src/fitdocs/connectors/ledger.py:182-193` -- `with_watermark` raises on a
  value earlier than the current one ("the watermark never moves backward",
  Req 7.2). `DEFAULT_LOOKBACK_DAYS = 30` at
  `src/fitdocs/connectors/settings.py:66`.
- `.kiro/specs/connectors/requirements.md:223` -- Req 8.7: "forget that
  activity's ledger record so that the next pull fetches it again".
- `docs/connectors.md:344-345` -- "A delivery that vanished before being
  archived is simply forgotten, and fetched again on a later pull".
- `.kiro/specs/wellness-pull/design.md:322-323` and `:355-366` (the sweep
  precedes both steps so a forgotten wellness delivery "moves the mark back";
  `Forgotten` "lowers the mark") and `:1370-1371` ("A forgotten wellness
  delivery moves the wellness mark back; the activity watermark rule is
  unchanged").
- Related, same root cause (a window anchored only on a never-decreasing
  watermark): `.kiro/queue/2026-10-02-intervals-rate-limit-resume-claim-since-backfill.md`
  and `.kiro/queue/2026-10-02-connectors-page-delivery-and-lookback-inaccuracies.md`.

## How to pick it up

1. Reproduce with the connectors test transport (`tests/connectors/`, see
   `test_sweep_forgetting_the_last_entry_rewrites_the_ledger_file` in
   `tests/connectors/test_pull.py` for the staging): pull an activity whose
   start is more than `lookback_days` older than a newer one, delete its
   pending file, pull again, and show it is never listed or fetched.
2. Pick the fix. Candidates: record the earliest start among forgotten
   entries in the ledger and have `_window_start` take the minimum of that and
   the watermark window, clearing it when the activity is final again (what
   wellness-pull does for its mark); or allow the watermark to be lowered
   under the sweep with its own guard in `Ledger`.
3. Decide with the two related items above, which share the window logic.
   Done when the reproduction in step 1 fetches the activity on the next pull
   and a mutation that drops the lowering reds a named test.

## Open questions

- Does connectors need an amendment (Req 7.2 says the watermark never moves
  backward; a second ledger key would leave it true) or a reword of Req 8.7 to
  say "within the look-back window"? The first keeps the promise.

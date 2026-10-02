---
id: 2026-10-02-connectors-page-delivery-and-lookback-inaccuracies
title: docs/connectors.md misstates three pull behaviours -- the first-pull lookback ignores --since, a vanished delivery is re-fetched in the same pull, and a changed activity whose new bytes are already archived is reported held, not delivered
status: open
importance: low
importance_why: The page is the user reference for pull; each sentence predicts a different report than the user will see, but no data is at risk.
effort: S
kind: docs
area: connectors, docs/connectors.md
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "do: correct the three passages of docs/connectors.md listed in .kiro/queue/2026-10-02-connectors-page-delivery-and-lookback-inaccuracies.md (lookback_days row, vanished-delivery sentence, different-bytes revision sentence) and run uv run pytest tests/connectors/test_docs.py tests/test_docs_guarantees.py -q"
context:
  - docs/connectors.md
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/delivery.py
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
1. **Lookback row ignores `--since`.** `docs/connectors.md:30`: "An
   instance's first pull, with no ledger yet, lists everything regardless of
   this key." `_window_start` (`src/fitdocs/connectors/pull.py:220-233`)
   returns `--since` outright when given ("wins outright", `:225`), so a first
   pull with `--since` lists from that day. Add "(unless `--since` is given)".
2. **A vanished delivery is re-fetched in the same pull.** `:197-198`: "A
   delivery that vanished before being archived is simply forgotten, and
   fetched again on a later pull". The sweep runs before listing
   (`pull.py:380` sweep, `:445` `list_activities`), and a forgotten entry
   has no final outcome, so the same pull re-lists and re-fetches it --
   design.md:400-402 says exactly that ("re-listed and re-fetched in the same
   run"). Say "fetched again by this same pull".
3. **Changed bytes already archived are held, not delivered.** `:191-193`:
   "Different bytes release the old copy ... and the new bytes are delivered
   in its place." When the new bytes are already archived (or held by
   another pending delivery), `run_pull` records `ALREADY_HELD` and reports
   `held` (`pull.py:633-643`), which still releases the old copy (the entry
   is replaced) but delivers nothing. Add that case.

## Why it matters
A user comparing a pull report with the page will see `held` where the page
promised `delivered`, and an immediate re-fetch where it promised a later
one, and conclude something is wrong.

## Evidence
Lines read at `ad985b3`. Items 2-3 first reported by the feature-validation
integration reviewer (F4), item 1 by the task 7 round-4 reviewer; all three
re-derived from the code in this session (static reading, no run).

## How to pick it up
1. Read `docs/connectors.md:20-35` and `:174-205` beside `pull.py:220-233`
   and `:600-690`.
2. Make the three edits; leave the never-delete guarantees as they are
   (`tests/connectors/test_docs.py:557` pins "Nothing you or your own tools
   put in the inbox is ever removed" on the docs pages).
3. Run the docs tests named in `resume_command`. Done when each sentence
   predicts the report the code produces.

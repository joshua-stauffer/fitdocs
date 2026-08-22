---
id: 2026-07-29-coggan-steps-5-7-untranscribed
title: COGGAN_2003's note transcribes steps 1, 2-4 and 8 only, so any prose about the intervening steps is unverifiable in-repo
status: open
importance: low
importance_why: Nothing currently depends on steps 5-7, but the gap already produced one rejected overclaim, and the record does not say the omission is deliberate.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/metrics/sources.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.2, review rounds 2-3)
pinned_at: 373405a
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-coggan-steps-5-7-untranscribed.md] Either transcribe Coggan 2003's steps 5-7 into the COGGAN_2003 record next time the text is open, or state in the note that their omission is deliberate"
context:
  - src/fitdocs/metrics/sources.py
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/stress.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`COGGAN_2003`'s note in `src/fitdocs/metrics/sources.py` records that the work's
printed page 10 lists eight computation steps, and transcribes step 1, steps 2-4
and step 8. Steps 5, 6 and 7 are not transcribed and the note does not say
whether that is deliberate.

## Why it matters

Requirement 15's whole point is that a claim about a published work rests on
that work's own text having been read. Where the record transcribes only part of
a text, prose elsewhere in the codebase can quietly assert what the untranscribed
part says, and nothing in the repo can contradict it.

This is not hypothetical: task 10.2's first remediation wrote "steps 5-8 govern
TSS and live in `fitdocs.metrics.stress`, not here" and was rejected for it —
partly because `intensity_factor` in `power.py` falsifies the "not here" half,
and partly because the content of steps 5-7 is not established anywhere a
reviewer can check. The approved wording retreated to what step 8's own
transcription entails ("steps 5-8 carry the derivation on to TSS"), which is
sound but is an inference rather than a reading.

Low importance because no constant is cited to steps 5-7 and no metric depends
on them. It is filed so the next session with the text open closes it cheaply,
rather than the next session without it guessing again.

## Evidence

At `373405a`, `src/fitdocs/metrics/sources.py`'s `COGGAN_2003` note transcribes:

- step 1 — the 30-second rolling average;
- steps 2-4 — raise to the fourth power, average, take the fourth root;
- step 8 — divide the "raw" TSS by the amount of work that could be performed in
  one hour at threshold power, and multiply by 100.

Nothing between steps 4 and 8. Confirmed independently by two reviewer subagents
across task 10.2's rounds 2 and 3.

## How to pick it up

1. This needs the primary text. Coggan (2003) is the USA Cycling chapter already
   identified by this record and by `load/channels/sources.py`'s `COGGAN_TSS`;
   it is a machine-local prerequisite exactly like the Banister scans, and a
   fresh worktree will not have it. Confirm access before starting.
2. If the text is reachable, transcribe steps 5-7 into the note in the same form
   as the existing steps, with the page locator, and re-verify the steps already
   transcribed against the page rather than against the note.
3. If it is not reachable, the honest close is a sentence in the note saying the
   omission is deliberate and which steps are unread — so a later session knows
   the gap is known rather than accidental.
4. Do not resolve this by summarizing a secondary source. Req 15.4 forbids
   establishing content that way, and the 9.x tasks were rejected repeatedly for
   the softer version of it.

## Open questions

Whether a record may transcribe a text selectively at all, or whether Req 15's
"read from the work's own text" implies the locator's full content. The existing
record has shipped through review in its partial form, so the current answer is
that selective transcription is acceptable — this item only asks that it be
declared.

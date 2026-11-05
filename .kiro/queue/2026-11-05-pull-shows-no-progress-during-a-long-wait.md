---
id: 2026-11-05-pull-shows-no-progress-during-a-long-wait
title: "`fitdocs pull` prints nothing while a connector waits out a rate limit or paces a long listing"
status: open
importance: medium
importance_why: A Garmin first pull spends minutes in 1 s pacing and may wait up to 900 s in rate-limit backoff in total with a silent terminal; a user cannot tell it from a hang and may interrupt it.
effort: S
kind: gap
area: src/fitdocs/connectors/pull.py, src/fitdocs/connectors/protocol.py, src/fitdocs/connectors/garmin.py, src/fitdocs/cli.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector 6.3
pinned_at: 25a96806
resume_command: "/kiro-spec-requirements connectors [queue: .kiro/queue/2026-11-05-pull-shows-no-progress-during-a-long-wait.md] Show progress while a pull waits or paces, without leaking a secret"
context:
  - src/fitdocs/connectors/garmin.py
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/protocol.py
  - src/fitdocs/cli.py
  - .kiro/specs/garmin-connector/design.md
  - .kiro/specs/connectors/requirements.md
blocked_by: []
---

## What
`fitdocs pull` prints its report once, at the end (`_report_pull` in
`src/fitdocs/cli.py`, called by `pull_command`). A connector's pacing and waits go
through `ConnectorSession.sleep`, a plain `Callable[[float], None]`
(`src/fitdocs/connectors/protocol.py:363`), which carries no message. The Garmin
connector sleeps one second between requests (`garmin.py:721`) and waits 30, 60,
120 and 240 seconds, to a total of 900 seconds a pull, on a 429
(`garmin.py:68-70`, `:790`). During a first pull of a long history the terminal
shows nothing for minutes.

## Why it matters
The user cannot tell a deliberate wait from a hang, and interrupting a pull
mid-run is the one thing the design's per-run cap and ledger are built to make
safe but not pleasant.

## Evidence
- `src/fitdocs/connectors/garmin.py:721` and `:790` call `session.sleep(...)`.
- `src/fitdocs/connectors/protocol.py:363`: `sleep: Callable[[float], None]`.
- `grep -n "_report_pull" src/fitdocs/cli.py`: the report prints after the
  engine returns. Unknown: whether intervals' pull has the same silence on a long
  429 wait (it shares the transport's retry waits, so it likely does).

## How to pick it up
1. Decide the seam: a progress callback on `ConnectorSession`, or a message
   carried by the sleep (a spec question; it touches the connectors contract and
   its approved requirements, so it wants an amendment).
2. Print one line per wait and a periodic count for a long listing to stderr, never
   a secret, never a signed link; mind `--json`-style output if the command has any.
3. Test with the injected `sleep` and a fake transport, no real clock.

## Open questions
Whether a quiet mode is wanted for scheduled runs (the connectors page describes
running on a schedule).

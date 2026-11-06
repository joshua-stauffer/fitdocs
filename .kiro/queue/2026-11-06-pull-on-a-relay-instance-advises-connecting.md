---
id: 2026-11-06-pull-on-a-relay-instance-advises-connecting
title: fitdocs pull on an unconnected relay instance says to connect, and connecting only leads to "does not pull"
status: open
importance: low
importance_why: Only a user who names a relay instance reaches it, a plain pull skips them, and the second message is clear; it costs one wasted connect.
effort: S
kind: bug
area: connectors, src/fitdocs/connectors/credentials.py, src/fitdocs/connectors/pull.py
created: 2026-11-06
surfaced_by: independent fact-check of draft PR 5
pinned_at: 7f58681e
resume_command: "do: make fitdocs pull report that a named relay or strava instance does not pull before it checks credentials, and pin the unconnected case with a test [queue: .kiro/queue/2026-11-06-pull-on-a-relay-instance-advises-connecting.md]"
context:
  - src/fitdocs/connectors/credentials.py
  - src/fitdocs/connectors/pull.py
  - tests/connectors/test_pull.py
blocked_by: []
---

## What
`fitdocs pull relay` checks credentials before it checks whether the instance can pull. With nothing stored, the report says to connect. With a token, the same command says the instance does not pull, so following the first message's advice cannot help.

## Why it matters
A user follows the advice, pastes a token at the relay, and only then learns the command was never going to work for that instance.

## Evidence
Run at 7f58681e over a scratch data root whose `fitdocs.toml` holds `[connectors.relay]` with `url = "http://127.0.0.1:9"`:

```
$ fitdocs pull relay --out <root>
  NotConnectedError: relay is not connected: run `fitdocs connect relay` or set FITDOCS_CONNECTOR_RELAY_TOKEN
exit 1

$ FITDOCS_CONNECTOR_RELAY_TOKEN=probe-not-a-token fitdocs pull relay --out <root>
  does not pull activities or wellness
exit 1
```

The first message comes from `src/fitdocs/connectors/credentials.py:459`. A `strava` instance was not run; it is expected to behave the same.

## How to pick it up
1. In the pull engine, find where a named instance's capabilities and credentials are checked, and check the capability first.
2. Add a test for an unconnected relay instance named on the command line: it reports that the instance does not pull, and makes no request.
3. Done when both commands above print the second message.

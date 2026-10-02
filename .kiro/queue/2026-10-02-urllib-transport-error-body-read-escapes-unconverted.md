---
id: 2026-10-02-urllib-transport-error-body-read-escapes-unconverted
title: urllib_transport lets two exception paths escape as raw stdlib errors instead of TransportError -- a failed read of an HTTP error body, and a malformed URL rejected before the try
status: open
importance: low
importance_why: Neither path carries a URL query today, so nothing secret leaks; the cost is that a data-mode call does not retry a transient error-body read, and the error reaches the pull's generic exception mapping instead of the transport's typed message.
effort: S
kind: bug
area: connectors, src/fitdocs/connectors/http.py, tests/connectors/test_http.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-urllib-transport-error-body-read-escapes-unconverted.md] Convert every exception urllib_transport can raise into TransportError, including the HTTPError body read and the target description"
context:
  - src/fitdocs/connectors/http.py
  - tests/connectors/test_http.py
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
`urllib_transport` (`src/fitdocs/connectors/http.py:142-185`) is meant to turn
every failure into a `TransportError` whose text names only scheme, host and
path. Two paths escape it:

1. **The error-body read.** In the `except urllib.error.HTTPError` arm
   (`:164-167`), `exc.read(MAX_RESPONSE_BYTES + 1)` runs inside an except
   handler. An exception raised there is not caught by the sibling `except`
   clauses (`:168-181`), so a timeout, `IncompleteRead` or `OSError` while
   reading a 4xx/5xx body escapes raw. `HttpClient`'s data-mode retry only
   retries `TransportError`, so this transient failure is not retried.
2. **The target description.** `_describe_target(request.url, ...)` (`:147`,
   defined `:127-135`) runs before the `try`. `urlsplit(...).port` raises
   `ValueError` for a non-numeric port and `urlsplit` raises it for a broken
   IPv6 literal, both unconverted.

The two larger gaps first reported here are already fixed at this pin: the
`Request` is now built inside the `try`, and `(ValueError,
http.client.HTTPException)` has its own arm (`:174-177`).

## Why it matters
Requirement 10.4 (no query string in any message) holds today because the
stdlib's messages on these paths carry no URL -- an accident of the stdlib,
not a property the code establishes. Converting both paths makes the
guarantee structural and lets data mode retry the read failure.

## Evidence
Run at `ad985b3`:

```
# urlopen patched to raise HTTPError whose body .read() raises TimeoutError
-> builtins TimeoutError read timed out          # not TransportError
urllib_transport(HttpRequest(method="GET", url="https://h:abc/p?k=SECRET"), 1.0)
-> ValueError Port could not be cast to integer value as 'abc'
urllib_transport(HttpRequest(method="GET", url="https://[::1/p?k=SECRET"), 1.0)
-> ValueError Invalid IPv6 URL
```

The read-failure path was first reported by the task 2.1 round-3 reviewer
subagent; both paths re-run in this session.

## How to pick it up
1. Read `http.py:127-185` and the transport tests in
   `tests/connectors/test_http.py`.
2. Move `_describe_target` inside the `try` (or give it its own guarded call
   that falls back to a fixed placeholder), and wrap the HTTPError arm's
   `exc.read(...)` in its own `try` mapping `TimeoutError`, `OSError` and
   `http.client.HTTPException` to `TransportError` with the same
   target-only text the sibling arms use.
3. Pin each with a fixture whose exception text *contains* the query
   (so a leak would be visible), and one data-mode test that a failed
   error-body read is retried.
4. Done when no exception other than `TransportError` can leave
   `urllib_transport` for any input URL.

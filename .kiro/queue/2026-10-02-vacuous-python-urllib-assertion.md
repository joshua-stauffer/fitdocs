---
id: 2026-10-02-vacuous-python-urllib-assertion
title: test_intervals_pull.py's "no request carries Python-urllib" assertion can never fail with a scripted transport
status: open
importance: low
importance_why: A vacuous assertion presents a guarantee as pinned when it is not. Another assertion carries the real guarantee, so nothing is unprotected today.
effort: S
kind: test-quality
area: intervals-connector, connectors, tests/connectors/test_intervals_pull.py, src/fitdocs/connectors/http.py
created: 2026-10-02
surfaced_by: /kiro-impl intervals-connector (4.1 review)
pinned_at: 9d08482
resume_command: "do: either delete or reword the vacuous Python-urllib assertion at tests/connectors/test_intervals_pull.py:212 (and the matching sentence in intervals-connector design.md Testing Strategy 'Integration' and tasks.md 4.1), or pin urllib_transport's outgoing User-Agent at the transport level in tests/connectors/test_http.py"
context:
  - tests/connectors/test_intervals_pull.py
  - src/fitdocs/connectors/http.py
  - tests/connectors/test_http.py
  - .kiro/specs/intervals-connector/design.md
blocked_by: []
---

## What
`tests/connectors/test_intervals_pull.py:212` asserts that no recorded
request header contains `Python-urllib`. urllib adds its default agent inside
`urllib.request` at send time, never in `HttpRequest.headers`, so the
scripted transport never sees it. No production mutation can make this
assertion fail. The User-Agent equality assertion on the line above is what
actually pins Req 5.6.

## Why it matters
The task text and the design's Testing Strategy both name this assertion, so
a reader takes the "no Python-urllib" guarantee to be tested at the transport
level when it is not.

## Evidence
- `tests/connectors/test_intervals_pull.py:212`: `assert not any("Python-urllib" in v for v in request.headers.values())`.
- The 4.1 reviewer reported that `grep -rn "Python-urllib" tests/ src/` finds
  only this line, and that urllib's default agent is added below
  `HttpRequest` (reviewer subagent; the controller confirmed the grep line
  only).

## How to pick it up
1. Read `src/fitdocs/connectors/http.py`'s `urllib_transport` and how it
   builds a `urllib.request.Request`.
2. Better: in `tests/connectors/test_http.py`, intercept the
   `urllib.request.Request` that `urllib_transport` builds (or patch the
   opener) and assert its `User-Agent` is fitdocs's. Show that dropping the
   override reds it.
3. Then delete the vacuous assertion, or reword it with a comment, and
   update design.md's Integration bullet.

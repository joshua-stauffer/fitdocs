---
id: 2026-11-02-strava-publish-connectors-protocol-all-lists-consent-names-but-not-relay-types
title: "connectors.protocol.__all__ lists the four consent names but not relay-server's five protocol types, and nothing pins __all__"
status: open
importance: low
importance_why: "Export list is inconsistent and unguarded."
effort: S
kind: chore
area: "src/fitdocs/connectors/protocol.py, tests/connectors"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 5.1 review"
pinned_at: 964cc419
resume_command: "do: decide the intended public surface of connectors.protocol, make __all__ match, and add a test that pins it (read .kiro/queue/2026-11-02-strava-publish-connectors-protocol-all-lists-consent-names-but-not-relay-types.md first)"
context:
  - src/fitdocs/connectors/protocol.py
  - .kiro/queue/2026-11-01-connectors-protocol-dataclass-flags-unpinned.md
blocked_by: []
---

## What
`__all__` in protocol.py lists strava-publish's four consent names but not the five types relay-server added there.

## Why it matters
Star-imports and docs generators see an inconsistent surface.

## Evidence
`src/fitdocs/connectors/protocol.py:51` `__all__ = [`; full contents not diffed against the module's definitions in this run.

## How to pick it up
List the public names defined in the module, compare with `__all__`, fix, and add a test (see the related protocol dataclass queue item).

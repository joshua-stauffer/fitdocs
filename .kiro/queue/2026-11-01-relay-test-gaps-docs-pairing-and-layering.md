---
id: 2026-11-01-relay-test-gaps-docs-pairing-and-layering
title: 'Two relay test gaps: docs sentence/heading pairing, and internal layer order'
status: open
importance: low
importance_why: Both are claimed invariants (a design "defect" line; a per-heading docs check) that nothing would fail on.
effort: M
kind: gap
area: relay/tests/test_docs_relay.py, relay/tests/test_boundary.py, relay/src/fitdocs_relay/routes.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.3 review r2; /kiro-validate-impl relay-server (G-1)
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-test-gaps-docs-pairing-and-layering.md] Pin the docs pairing and the relay layer order"
context:
  - relay/tests/test_docs_relay.py
  - relay/tests/test_boundary.py
  - relay/src/fitdocs_relay/routes.py
  - .kiro/specs/relay-server/design.md
blocked_by: []
---

## What
(1) The docs statement checker pairs each sentence with a heading, but no test checks the pairing, so searching the whole page instead stays green. (2) `routes.py` imports `app.RelayServices` under `TYPE_CHECKING`, an upward import. Design says a violation of the layer order is a defect, but `test_boundary.py` pins only third-party placement.

## Why it matters
Both guards are weaker than the text that describes them.

## Evidence
- `relay/src/fitdocs_relay/routes.py:60-61`: `if TYPE_CHECKING:` import of `RelayServices` from `fitdocs_relay.app`.
- `.kiro/specs/relay-server/design.md:353-354`: "a violation is a defect".
- `relay/tests/test_docs_relay.py` contains the checker; no test mutates its heading pairing.

## How to pick it up
1. Write a mutation test for the docs checker: a sentence moved under the wrong heading must fail.
2. Encode the layer order from design.md:340-360 as an import-graph test (include TYPE_CHECKING imports); move or invert `RelayServices` if it fails.
3. Done when both mutations are red.

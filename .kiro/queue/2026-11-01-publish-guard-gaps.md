---
id: 2026-11-01-publish-guard-gaps
title: "Several publish-core boundary and wording guards are unpinned"
status: open
importance: low
importance_why: Each gap lets a small regression through silently; none is a live defect.
effort: M
kind: gap
area: publish-core, tests/publish/test_boundary.py, tests/connectors/test_boundary.py, tests/test_contract_consumers.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: close the five publish guard gaps (a)-(e) listed in the item [queue: .kiro/queue/2026-11-01-publish-guard-gaps.md]"
context:
  - src/fitdocs/connectors/protocol.py
  - tests/connectors/test_boundary.py
  - tests/publish/test_boundary.py
  - tests/test_contract_consumers.py
  - .kiro/steering/structure.md
blocked_by: []
---

## What
(a) The `PostPublisher` docstring framing before "A target's" in
`connectors/protocol.py` is unpinned; inserting a sentence survives.
(b) No rule-level guard stops a future connector target module importing
`fitdocs.publish.*`; only per-module equality pins in
`tests/connectors/test_boundary.py` exist.
(c) No reverse scan that only `cli` (and `connectors.protocol`/`registry`)
import `fitdocs.publish` from outside the package; add to
`tests/publish/test_boundary.py`.
(d) `FORBIDDEN_LITERALS` in `tests/test_contract_consumers.py` (~:392) lacks
`PUBLISH_KEY` and the post/published region ids, so a publish module could spell
"post"/"publish" itself.
(e) Nothing pins the `.kiro/steering/structure.md` publish bullet or its
connectors-sentence clauses; mutations left 280 readers green.

## Why it matters
Each is a boundary the publish-core design relies on and a mutation passes today.

## Evidence
The files and lines above; mutation runs in the publish-core implementation
left the listed readers green.

## How to pick it up
Take (a)-(e) in turn; for each add the pin, then show a mutation fails it.

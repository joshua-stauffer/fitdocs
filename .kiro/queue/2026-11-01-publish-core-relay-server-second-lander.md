---
id: 2026-11-01-publish-core-relay-server-second-lander
title: "relay-server must reconcile with publish-core when it lands second"
status: open
importance: high
importance_why: The two branches collide on shared contract text, version numbers, pins and amendment numbers; a naive rebase leaves contradictory contract prose or a red suite.
effort: M
kind: spec-work
area: relay-server, publish-core, docs/ownership-contract.md, tests/test_ownership_contract.py, tests/test_publish_contract_docs.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: when relay-server rebases onto main after publish-core landed, apply .kiro/queue/2026-11-01-publish-core-relay-server-second-lander.md"
context:
  - docs/ownership-contract.md
  - tests/test_publish_contract_docs.py
  - tests/test_ownership_contract.py
  - tests/connectors/test_boundary.py
  - .kiro/steering/structure.md
  - tests/test_docs_guarantees.py
  - src/fitdocs/cli.py
  - .kiro/specs/wiki-contract
  - .kiro/specs/distribution
  - .kiro/specs/connectors
blocked_by: []
---

## What
The unmerged relay-server branch (worktree `../fitdocs-relay-server`, branch
`impl/relay-server`) and publish-core collide beyond renumbering. The second
lander must:

(a) Write ONE "only operations that write to or remove from the credentials
store" list in `docs/ownership-contract.md` (~931) covering `fitdocs connect`, a
credential-renewing `fitdocs pull`, a credential-renewing `fitdocs publish
--yes` and `fitdocs disconnect`; drop "never deletes it or anything in it"; and
move both sides' pins (`tests/test_publish_contract_docs.py` on publish-core,
`tests/test_ownership_contract.py` on relay), both CONTRACT_VERSION history
paragraphs and both wiki-contract criteria.

(b) Take CONTRACT_VERSION 19, CLI command count 17, connectors surface 63
(50+8+5), and the protocol entry in `tests/connectors/test_boundary.py` =
`{http, secrets, relay_codes, publish.outcomes, publish.request}`.

(c) Renumber colliding amendments: wiki-contract Amendment 14 (+ criterion
2.23/2.24), distribution Amendment 6, connectors Amendment 6.

(d) Resolve the textual conflict on the same `.kiro/steering/structure.md`
connectors line, plus pyproject urls/mypy files, `docs/index.md`,
`tests/test_docs_guarantees.py` `_REQUIRED_ENTRY_POINT_LINKS`, CHANGELOG
Unreleased, SKILL.md, and the `cli.py` module docstring count word.

## Why it matters
Both branches edit the same contract list, version numbers and pins; whoever
lands second inherits every conflict.

## Evidence
agent-log WARN by impl-publish-core, 2026-11-01; `git -C ../fitdocs-relay-server
diff main`.

## How to pick it up
1. Read the agent-log WARN and the relay-server diff against main.
2. Rebase relay-server onto main and resolve (a)-(d) above.
3. Run the full suite; every pin named in (a) must pass on the merged text.

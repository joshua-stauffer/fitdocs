---
id: 2026-11-02-strava-publish-design-text-drift-from-landed-code
title: "strava-publish design.md describes several modules and wordings differently from the landed code"
status: open
importance: low
importance_why: "Documentation drift only; the next reader of the design is misled about imports, file names and comment text."
effort: S
kind: docs
area: ".kiro/specs/strava-publish/design.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 1.2, 1.3, 3.3, 3.11 reviews and validate-impl"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-design-text-drift-from-landed-code.md] Reconcile the listed design.md statements with the landed code in the Amendment note"
context:
  - .kiro/specs/strava-publish/design.md
  - .kiro/specs/strava-publish/tasks.md
  - relay/src/fitdocs_relay/shared/relay_targets.py
  - src/fitdocs/connectors/relay_connect.py
  - relay/src/fitdocs_relay/strava/budget.py
  - relay/tests/conformance/test_connections.py
  - .kiro/queue/2026-11-01-relay-design-file-structure-plan-names.md
blocked_by: []
---

## What
A bundle of small design-text mismatches, all reported by reviewers: (a) the design file list omits `connectors/relay_connect.py`, whose `_NEXT_STEPS` gained registration-style text for the five connect codes (connect codes stay refusals in `RelayClient` token operations); (b) design lists `relay_codes` as an allowed import of `relay_targets`, but the module imports only `relay_envelope`; (c) the builders `target_route`, `connect_page_path` and `link_path` raise `EnvelopeError` on malformed parts and the design is silent; (d) the `BudgetDecision` comment says `retry_after_s` is `None` when allowed, but `StravaBudget` also returns `None` on a refusal no window can hold; (e) consent wording "under relay, the relay returns only fitdocs codes" is literally false (connect answers carry user code, poll secret, interval, expiry and connection token); the implementation says it returns nothing Strava supplied; (f) the file-plan names drift: conformance/test_target_connections.py became test_connections.py, relay/tests/strava/{test_config,test_budget,test_routes,test_cli}.py have other names, tests/connectors/test_strava.py is split, the confinement case lives in test_relay_offline.py.

## Why it matters
Low stakes, but the design is the reference a later spec cites.

## Evidence
- `.kiro/specs/strava-publish/design.md:428`: `conformance/test_target_connections.py`; `ls relay/tests/conformance` has `test_connections.py` and no `test_target_connections.py`; `ls tests/connectors` has test_strava_consent.py, test_strava_publish.py, test_strava_wire_examples.py, test_strava_docs.py, test_strava_changelog.py, test_cli_strava.py (no test_strava.py).
- `relay/src/fitdocs_relay/strava/budget.py` and `design.md` BudgetDecision comment ("# None when allowed"): confirmed the comment text exists in the design; the budget behaviour is the reviewer's claim.
- Items (a), (b), (c), (e) reported by reviewer subagents, unverified. Precedent: .kiro/queue/2026-11-01-relay-design-file-structure-plan-names.md.

## How to pick it up
1. Add a bullet per item to the design's Amendment note (2026-11-02) or fix the sentences in place.
2. Verify each against the code before writing (grep the imports of relay_targets.py; read budget.py's refusal path).

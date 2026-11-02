---
id: 2026-11-02-strava-publish-connectors-autouse-fixtures-skipped-when-args-interleave
title: "tests/connectors autouse guards silently switch off when pytest args interleave a root test file first"
status: open
importance: medium
importance_why: "The no-network guard is the suite's backstop for connector tests; it turning off silently means a test could reach the network."
effort: S
kind: bug
area: "tests/connectors/conftest.py, tests/conftest.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 5.8 review"
pinned_at: 964cc419
resume_command: "do: find why tests/connectors/conftest.py autouse fixtures are not applied for interleaved arguments and make them apply (read .kiro/queue/2026-11-02-strava-publish-connectors-autouse-fixtures-skipped-when-args-interleave.md first)"
context:
  - tests/connectors/conftest.py
  - tests/conftest.py
  - .kiro/queue/2026-11-01-connectors-cli-tests-file-order-pollution.md
blocked_by: []
---

## What
When pytest is given a `tests/connectors` file after a root `tests/` file, the autouse fixtures `_forbid_network_sockets` and `_isolated_connector_environment` do not run for the later file (reviewer saw this on pytest 9.1.1; `--setup-show` listed neither). Tests then fail with `KeyError: FITDOCS_CREDENTIALS_DIR`, and the network guard is off. A full `uv run pytest` is unaffected. Related to, but a distinct cause from, 2026-11-01-connectors-cli-tests-file-order-pollution (that one is leaked state; this is a missing fixture).

## Why it matters
A developer or CI job running selected files can run connector tests without the network guard.

## Evidence
Reproduced at HEAD 964cc419: `uv run pytest -q -p no:randomly tests/connectors/test_atomic.py tests/test_agent_skill.py tests/connectors/test_relay_offline.py` -> `11 failed, 160 passed in 0.75s` (first failures include `tests/connectors/test_relay_offline.py::test_the_targets_listing_shows_a_strava_instance_without_a_request[...]`). Autouse fixtures are defined at tests/connectors/conftest.py:96, 108, 149.

## How to pick it up
1. Re-run the repro above; add `--setup-show` to see which fixtures run per test.
2. Check how conftest is collected when a root file precedes it (rootdir/conftest ordering, `pytest_collect_file`, a plugin-level hook).
3. Done when the same command passes and the guard demonstrably runs; consider a hook that fails the session if a tests/connectors test ran without the guard.

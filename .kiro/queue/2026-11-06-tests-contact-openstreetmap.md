---
id: 2026-11-06-tests-contact-openstreetmap
title: Four tests fetch real tiles from tile.openstreetmap.org on every suite run
status: open
importance: medium
importance_why: A volunteer-run public service takes automated test traffic from every CI job, and each of these tests silently depends on the network; nothing suite-wide would notice a fifth.
effort: S
kind: bug
area: tests/load/test_settings.py, tests/load/test_feature_e2e.py, tests/index/test_boundary.py, tests/conftest.py, src/fitdocs/tiles.py
created: 2026-11-06
surfaced_by: maintainer-requested test suite audit (sampling profile, then an audit hook on socket events)
pinned_at: a6038449
resume_command: "do: Stop the four tests in .kiro/queue/2026-11-06-tests-contact-openstreetmap.md from contacting tile.openstreetmap.org by injecting the existing tile fake, then add a suite-wide guard so an in-process test cannot open an external connection"
context:
  - tests/load/test_settings.py
  - tests/load/test_feature_e2e.py
  - tests/index/test_boundary.py
  - tests/conftest.py
  - tests/connectors/conftest.py
  - tests/support/tiles.py
  - src/fitdocs/tiles.py
blocked_by: []
---

## What

A `sys.addaudithook` logger on `socket.getaddrinfo` and `socket.connect`, run
over the full root suite, recorded 72 lookups and 72 connections to
`tile.openstreetmap.org`, all from these four tests:

- `tests/load/test_settings.py::test_invalid_priority_value_in_data_root_aborts_load_pass_before_writing`
- `tests/load/test_settings.py::test_invalid_sufficiency_value_in_data_root_aborts_load_pass_before_writing`
- `tests/load/test_feature_e2e.py::test_cli_sync_printed_summary_matches_load_report_buckets`
- `tests/index/test_boundary.py::test_untouched_commands_do_not_import_duckdb` (through its module-scoped `_untouched_command_observation`)

They reach `fitdocs.tiles._default_fetch` because they run a real sync with no
injected fetch. Each run starts with an empty tile cache in its temp root.

## Why it matters

- The traffic goes to a shared public service for no test purpose. Across about
  34 `ci.yml` runs a day on three interpreters that is on the order of 7,000
  requests a day. This is an estimate from the local count: CI's own
  traffic was not observed, though nothing in the suite would block it there.
- These tests get slower or change path when the network or the service does. They
  account for about 8 s of the serial run.
- `_forbid_network_sockets` is autouse only under `tests/connectors/`. Other
  modules guard per test or not at all, so nothing suite-wide stops a new one.

## Evidence

Sampled stacks of the serial run: `tiles.py:_default_fetch` took 5.5 s under
`tests/load/test_settings.py`, 1.4 s under `tests/load/test_feature_e2e.py` and
1.3 s under `tests/index/test_boundary.py`, with `ssl.do_handshake` on the stack.
The audit-hook run found only `tile.openstreetmap.org`, with no other external
host. The hook sees the pytest process only, so subprocess traffic is out of its
view; `2026-09-19-offline-test-infrastructure-warm-cache-dependence` covers that
side.

## How to pick it up

1. Read how `tests/test_cli_sync_inbox.py` and `tests/test_inbox_e2e.py` stay
   offline with an injected tile fetch, and `FetchStub` in `tests/support/tiles.py`.
2. Give the four tests the same fake.
3. Move a socket guard up to `tests/conftest.py`, letting loopback through for the
   tests that need it (`tests/sitebuild/test_preview.py` serves locally).

Done means the audit hook logs no external host across a full run, and a test that
opens an external socket fails.

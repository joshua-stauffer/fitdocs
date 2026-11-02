---
id: 2026-11-02-strava-publish-relay-flaky-sqlite-connect-page-public-address-test
title: "Watch a possible SQLite flake in the relay connect-page public-address test"
status: open
importance: low
importance_why: "A single observation, not reproduced; recorded so a repeat is recognised rather than re-investigated."
effort: S
kind: research
area: "relay/tests/test_targets_pipeline.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 4.1 review"
pinned_at: 964cc419
resume_command: "do: if test_the_built_connect_page_names_the_configured_public_address fails in CI on SQLite, capture the failure and bisect; otherwise drop this item (read .kiro/queue/2026-11-02-strava-publish-relay-flaky-sqlite-connect-page-public-address-test.md first)"
context:
  - relay/tests/test_targets_pipeline.py
blocked_by: []
---

## What
A reviewer saw this test fail once under the SQLite backend and pass on rerun (no cause found).

## Why it matters
A flaky relay suite wastes review rounds.

## Evidence
Test exists at `relay/tests/test_targets_pipeline.py:327`. The flake itself: reported by reviewer subagent, unverified, not reproduced here.

## How to pick it up
Run it 50 times (`uv run --directory relay pytest -q relay/tests/test_targets_pipeline.py -k public_address --count 50` or a shell loop); if it never fails, close as dropped.

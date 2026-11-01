---
id: 2026-11-01-relay-workflow-guards-do-not-cover-scripts
title: 'The relay workflow word-ban scans run bodies only, and nothing guards the no-relay-image rule workflow-wide'
status: open
importance: medium
importance_why: The repository's no-publish rule for the relay can be bypassed by moving a command into a script or another workflow file.
effort: M
kind: gap
area: tests/test_relay_workflow.py, .github/workflows, relay/scripts
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 5.3, 8.7 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-workflow-guards-do-not-cover-scripts.md] Extend the publish-word ban to scripts and all workflows"
context:
  - tests/test_relay_workflow.py
  - .github/workflows/relay.yml
  - .github/workflows/release.yml
  - relay/scripts/image_smoke.sh
blocked_by: []
---

## What
(1) `_publishing_runs` bans publish/login/push/upload words in workflow `run:` bodies only; any step that delegates to a script is invisible to it (5.3 added a script-side scan for `image_smoke.sh` alone). (2) Only `relay.yml` is pinned against building or pushing a relay image for publication; the other four workflow files are unguarded, so nothing says this repository publishes no relay image.

## Why it matters
The rule is a distribution promise (the maintainer deploys elsewhere). A later change can break it without a red test.

## Evidence
- `tests/test_relay_workflow.py:117-126`: `_publishing_runs` and its use.
- `tests/test_relay_workflow.py:277-279`: the script calls it already special-cases.
- `ls .github/workflows` lists ci.yml, docs.yml, relay.yml, release.yml, specs.yml.

## How to pick it up
1. Extend the scan to every script path referenced by a `run:` step, in all workflow files.
2. Add a workflow-wide assertion that no workflow builds-and-pushes an image (docker push, build-push-action with push true, registry login).
3. Include mutation checks: add a push to a script and to release.yml; both must go red.

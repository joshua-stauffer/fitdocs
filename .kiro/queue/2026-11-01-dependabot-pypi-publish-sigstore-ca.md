---
id: 2026-11-01-dependabot-pypi-publish-sigstore-ca
title: 'Dependabot critical alert: bump pypa/gh-action-pypi-publish before the next release'
status: open
importance: high
importance_why: A release cut with the vulnerable action risks failed or unverifiable Trusted Publishing and attestations; the next release is the first that could ship relay-server.
effort: S
kind: chore
area: .github/workflows/release.yml
created: 2026-11-01
surfaced_by: /kiro-impl relay-server (observed during queue triage; unrelated to relay)
pinned_at: 774a883c
resume_command: "do: bump pypa/gh-action-pypi-publish in .github/workflows/release.yml (both uses) to the version the open Dependabot alert names as patched, update the pin-verification comments and any test that pins the version; see .kiro/queue/2026-11-01-dependabot-pypi-publish-sigstore-ca.md"
context:
  - .github/workflows/release.yml
  - tests/test_release_workflow.py
blocked_by: []
---

## What
An open Dependabot alert on main reports that the pinned `pypa/gh-action-pypi-publish` action is affected by a revocation of a CA in the chain Sigstore uses for Trusted Publishing and Digital Attestations for PyPI. The workflow pins v1.14.2 in two places.

## Why it matters
The next release publishes through this action. If the pinned version is the affected one, publishing or attestation can fail at the moment of release.

## Evidence
- `gh api repos/:owner/:repo/dependabot/alerts --jq '.[]|select(.state=="open")|.security_advisory.summary'` prints: `pypi-publish action revocation of CA in the chain that Sigstore uses in Trusted Publishing and Digital Attestations for PyPI` (run 2026-11-01).
- `.github/workflows/release.yml:233` and `:266`: `pypa/gh-action-pypi-publish@v1.14.2`; the comments at `:219-221` record how the pin was verified.

## How to pick it up
1. Read the alert's patched version from the alert page.
2. Re-pin both uses to the patched release and update the verification comments at :219-221.
3. Update any test that pins the version string (grep tests for `gh-action-pypi-publish`); done when the alert closes and the workflow tests are green.

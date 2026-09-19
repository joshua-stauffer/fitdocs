---
id: 2026-09-19-checker-text-like-suffixes-exact-case-incomplete
title: check_artifacts' text-like member set is an exact-case suffix list that omits .svg/.html/.xml/.tsv and upper-case variants
status: open
importance: medium
importance_why: A forbidden term in an .svg or .MD member would not be scanned by the encumbered-content gate.
effort: S
kind: gap
area: distribution, scripts/check_artifacts.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: make the text-like decision case-insensitive and extend the suffix set (.svg .html .xml .tsv .csv .txt .rst .toml .yaml .yml .json .md .py .cfg .ini), with a wheel+sdist twin fixture per newly covered suffix planting a synthetic needle"
context:
  - scripts/check_artifacts.py
  - tests/test_release_artifacts.py
  - release/artifact-policy.toml
blocked_by: []
---

## What
The content scan decides text-likeness by suffix; the set is exact-case and short. Charts are rendered as images/SVG in the docs pipeline, so .svg is a live gap if any is ever packaged.

## Why it matters
The gate is the security-grade boundary the design names; a suffix gap is a silent hole rather than a fail-closed one.

## Evidence
Implementation Note 2.3; scripts/check_artifacts.py text-like suffix constant.

## How to pick it up
Read the suffix constant and the twin-fixture pattern in tests/test_release_artifacts.py (every content fixture needs a wheel AND sdist twin). Done when a `.SVG` member carrying a synthetic needle reds both artifact kinds.

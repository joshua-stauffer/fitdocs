---
id: 2026-09-19-shared-git-ls-files-enumeration-helper
title: Two tests carry private copies of `.gitignore`-aware file enumeration (`git ls-files -co --exclude-standard`)
status: open
importance: low
importance_why: Any future file-set pin will copy it a third time; a stray .DS_Store false-red already cost a review round.
effort: S
kind: chore
area: tests/test_version_identity.py, tests/test_preserved_guarantees.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: extract a tests/_repo_files.py helper wrapping `git ls-files --cached --others --exclude-standard -- <paths>` and use it from tests/test_version_identity.py and tests/test_preserved_guarantees.py"
context:
  - tests/test_version_identity.py
  - tests/test_preserved_guarantees.py
blocked_by: []
---

## What
Both files shell out to git with the same flags to enumerate tracked-plus-untracked-not-ignored files.

## Why it matters
Docs pins in 5.2/5.7 style and any future golden-tree pin need the same enumeration; three copies drift.

## Evidence
Implementation Note 7.2; validation integration follow-up 4 (2026-09-19).

## How to pick it up
Pure refactor with the suite as the oracle. Done when both call sites import the helper.

---
id: 2026-09-19-design-stale-on-landed-deviations
title: distribution design.md is stale on four recorded deviations the implementation accepted
status: open
importance: medium
importance_why: Every deviation is recorded in tasks.md Implementation Notes and the policy header, but the design is what the next amendment reads first.
effort: S
kind: spec-work
area: distribution, .kiro/specs/distribution/design.md
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "/kiro-spec-design distribution [queue: .kiro/queue/2026-09-19-design-stale-on-landed-deviations.md] Amend design.md to match the landed checker modes, policy Data Shape, sdist extras and the six-table configuration statement"
context:
  - .kiro/specs/distribution/design.md
  - .kiro/specs/distribution/tasks.md
  - release/artifact-policy.toml
  - scripts/check_artifacts.py
blocked_by: []
---

## What
(1) checker modes `--no-artifacts` / `--no-version-check` and exit code 2 for hard errors are not in the design; (2) the policy Data Shape lacks `[sdist].required +PKG-INFO`, `[forbidden] +.fitdocs/*`, `[metadata] +Author-email` and has `Description` (never a header); (3) hatchling always ships `.gitignore` and `PKG-INFO` in the sdist; (4) design 3.8 says fitdocs.toml has three user-written tables today; docs/compatibility.md documents six. Also: `scripts/artifact_policy.py` (the loader) is not in the File Structure Plan, and 10.4 landed in tests/test_preserved_guarantees.py rather than by extending tests/test_determinism.py.

## Why it matters
A future amendment re-deriving tasks from the design would re-introduce the rejected shape (e.g. a `Description` header check that can never pass).

## Evidence
Implementation Notes 1.2, 1.4, 2.2, 2.4, 5.1, 7.2 in .kiro/specs/distribution/tasks.md; release/artifact-policy.toml header comment; design.md:~812 (three tables).

## How to pick it up
Read the six notes, then edit design.md's Components, Data Shape and File Structure Plan sections in one amendment commit; no code changes. Done when `grep -n 'three tables' design.md` is empty and the Data Shape matches release/artifact-policy.toml.

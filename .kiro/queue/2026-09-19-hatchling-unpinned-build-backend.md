---
id: 2026-09-19-hatchling-unpinned-build-backend
title: `build-system.requires = ["hatchling"]` is unpinned and absent from uv.lock, so cross-machine reproducibility (Req 10.5) depends on hatchling version equality
status: open
importance: medium
importance_why: Two builds of one tagged revision on different days can differ by hatchling's Generator metadata alone; the in-run reproducibility tests cannot see it.
effort: S
kind: gap
area: distribution, pyproject.toml, scripts/build_release.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: pin hatchling in [build-system].requires (exact or narrow range), record the pin in docs/releasing.md step 4 and the policy header, and add a test that build-system.requires carries a version constraint"
context:
  - pyproject.toml
  - scripts/build_release.py
  - tests/test_release_artifacts.py
  - tests/test_preserved_guarantees.py
  - docs/releasing.md
blocked_by: []
---

## What
`grep -c hatchling uv.lock` is 0 and pyproject.toml's `[build-system]` names hatchling with no constraint. `uv build` resolves whatever hatchling is current at build time; the wheel's METADATA `Generator` line and any packaging behaviour change ride along.

## Why it matters
Requirement 10.5 (same tagged revision built twice yields identical contents) is only guaranteed within one environment. A release rebuilt for verification months later may differ for reasons unrelated to fitdocs.

## Evidence
pyproject.toml `[build-system]`; 7.2 reviewer rounds 1-3 (Implementation Notes 7.2); tests/test_preserved_guarantees.py reproducibility tests build twice in ONE environment only.

## How to pick it up
Pick the hatchling version the current uv resolves (`uv build -v` shows it), pin it, rebuild, and confirm the artifact digests are unchanged. Then add the constraint test. Done when a fresh clone with an empty uv cache builds the same digests as the warm developer cache.

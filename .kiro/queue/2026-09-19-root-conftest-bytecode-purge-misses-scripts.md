---
id: 2026-09-19-root-conftest-bytecode-purge-misses-scripts
title: Root conftest.py purges stale bytecode only under src/, so mutation runs against scripts/ silently execute cached code
status: open
importance: medium
importance_why: A mutation that never took effect reports a discriminating assertion as insensitive (or vice versa); every scripts/ mutation review this spec needed a manual `rm -rf scripts/__pycache__`.
effort: S
kind: chore
area: conftest.py, scripts/
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: extend the root conftest.py bytecode purge to cover scripts/ (and tests/_*.py helper modules the checker imports); verify by mutating scripts/check_artifacts.py without touching mtime/size and confirming uv run pytest sees the change"
context:
  - conftest.py
  - scripts/check_artifacts.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What
change-protocol.md's Fixture Discrimination section says `uv run pytest` is cache-proof because the root conftest purges bytecode; that is true for src/ only. scripts/ became test-covered production code in this spec.

## Why it matters
Reviewers and implementers must remember an out-of-band `rm -rf scripts/__pycache__`; forgetting it produces false discrimination verdicts in the direction the protocol warns about.

## Evidence
Implementation Notes 2.2 and 7.2 (WARN in the agent log 2026-09-19); root conftest.py purge scope.

**Also tests/fixtures/ (2026-09-30, running-dynamics at 8b07b9f).** The same gap applies to fixture self-test mutations. The running-dynamics ground rules have those mutations target `tests/fixtures/builder.py`, but `conftest.py:38-56` purges only `_SRC.rglob("__pycache__")`, and `tests/fixtures/__pycache__/builder.cpython-311.pyc` exists. A same-size, same-second mutation of builder.py can run stale bytecode even under `uv run pytest`. This was reported by the task 1.2 reviewer subagent; the conftest lines were re-read here.

## How to pick it up
Read conftest.py's purge, add scripts/ (and consider making the purge scope a list), then run the check named in the resume command. Done when a same-second, same-size mutation to scripts/artifact_policy.py reds a test without a manual purge.

## Update 2026-10-01 (docs-site validation)
docs-site adds a large mutation-tested package under `scripts/sitebuild/` (10 modules) plus `scripts/build_site.py`, `check_site.py`, `make_hero_chart.py`; every docs-site reviewer mutated these files. The design-validation reviewer re-flagged this item: a `scripts/**/__pycache__` left by a direct `python -m scripts.*` run can make mutation evidence false. None existed at validation time (impl/docs-site ba76d03). The fix should cover `scripts/sitebuild/` too.

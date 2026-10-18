---
id: 2026-10-18-release-gates-job-3-11-only-and-unarmed
title: release.yml's gates job runs pytest on 3.11 only and without FITDOCS_FORBIDDEN_STRINGS, unlike ci.yml since accccba
status: open
importance: low
importance_why: see body
effort: S
kind: gap
area: .github/workflows/release.yml, tests/test_release_workflow.py
created: 2026-10-18
surfaced_by: queue-prerelease session (chore/q-ci-matrix implementer + review)
pinned_at: accccba
resume_command: "do: decide whether release.yml gates should mirror ci.yml (3.12/3.13 test legs; armed pytest with the add-mask step) and implement with workflow-test pins [queue: .kiro/queue/2026-10-18-release-gates-job-3-11-only-and-unarmed.md]"
context:
  - .github/workflows/release.yml
  - .github/workflows/ci.yml
  - tests/test_release_workflow.py
blocked_by: []
---

release.yml (~61-62) runs `uv run pytest` on 3.11 with the guard unarmed. The tagged commit has
already passed ci.yml on main (3 interpreters, armed), and release.yml's check_artifacts step is armed,
so this is a consistency gap, not an open hole. Low importance; decide before the next release whether
the release gate should re-prove the matrix.

---
id: 2026-09-30-check-artifacts-echoes-matched-member-names
title: scripts/check_artifacts.py writes a matched member name into the public release log
status: open
importance: medium
importance_why: The repo is public, so a release run's Actions log is public; echoing an encumbered file name defeats the no-echo rule the docs-site gate follows.
effort: S
kind: bug
area: distribution, scripts/check_artifacts.py
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (review)
pinned_at: 3014dfb
resume_command: "do: redact matched member names in scripts/check_artifacts.py findings as scripts/check_site.py does; add a needle-named-member test"
context:
  - scripts/check_artifacts.py
  - scripts/check_site.py
  - tests/test_release_artifacts.py
blocked_by: []
---

## What
check_artifacts reports findings with the matched member's name in the detail: `f"binary member {member.name!r} name matches a forbidden-string token match"` (scripts/check_artifacts.py:540-548), and names `member.name` in content details (:518-535). If the member name itself matches a forbidden token, the name is printed.

## Why it matters
The docs-site gate (scripts/check_site.py) redacts such subjects as `<root>/<redacted path #N>` and never echoes matched text; the release gate does not.

## Evidence
Found by the docs-site 2.6 reviewer (2026-09-30) comparing the two gates.

## How to pick it up
1. Mirror check_site.py's redaction: when a member's name matches, report an ordinal placeholder instead of the name.
2. Add a test in tests/test_release_artifacts.py (or check_artifacts' tests) with a needle-named member asserting the needle is absent from stdout and stderr.

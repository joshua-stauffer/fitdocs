---
id: 2026-09-18-btb-test-strength-leftovers
title: build-training-block suites: three assertions weaker than the rule they name (stage-C fixture confounded with stem order; bare `plan` span unbound; compatibility note pinned by substring; wheel scans prefix-match)
status: open
importance: low
importance_why: Each is a clause the suite claims but cannot fail on under one plausible mutation; none changes behaviour.
effort: S
kind: gap
area: build-training-block, tests/test_skill_e2e.py, tests/test_agent_skill.py, tests/test_skill_wheel.py
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: (1) tests/test_skill_e2e.py stage C -- name the stems so start-time order and stem order disagree (e.g. 07:00 page stem sorts AFTER the 18:00 one) so 'first row takes the earlier page' is pinned apart from stem order, with the design's fixture note updated; (2) tests/test_agent_skill.py -- bind single-word command spans (`plan`, `sync`, `regen`) to the registry or state they are unbound; pin the compatibility note's 'installed'/'path' wording; (3) tests/test_skill_wheel.py -- assert member names are canonical (no `./`, no backslash) before prefix-matching"
context:
  - tests/test_skill_e2e.py
  - tests/test_agent_skill.py
  - tests/test_skill_wheel.py
  - src/fitdocs/plans/corpus.py
  - .kiro/specs/build-training-block/design.md
blocked_by: []
---

## Evidence
- Stage C: `src/fitdocs/plans/corpus.py:126-133` `order_key` ends in `stem`;
  review mutation "both pages start_time 07:00" stayed green because
  `2030-01-22-run-0700` < `...-1800` agrees with the time order (3.4 round 1, m3).
- `SKILL.md:16` carries a bare `` `plan` `` span; `tests/test_agent_skill.py`
  scans only spans whose first word is `fitdocs` (validation coverage note 4.1).
- Compatibility: `tests/test_agent_skill.py` ~:304-307 asserts only `"fitdocs" in compatibility`.
- Wheel: 3.1 review probe -- synthetic `./fitdocs/skills/phantom/SKILL.md` and a
  backslash name slip past the unregistered-directory pin (unreachable via hatchling).

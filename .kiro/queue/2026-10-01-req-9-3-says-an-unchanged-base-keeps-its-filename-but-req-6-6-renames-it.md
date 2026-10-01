---
id: 2026-10-01-req-9-3-says-an-unchanged-base-keeps-its-filename-but-req-6-6-renames-it
title: Requirement 9.3 states that a page whose base does not change keeps its filename, which Requirement 6.6's settle rename contradicts
status: open
importance: low
importance_why: The shipped contract text already carries the exception, so users are not misled; the requirement the text was written from still says otherwise and will be the one re-read.
effort: S
kind: inconsistency
area: activity-identity, .kiro/specs/activity-identity/requirements.md, docs/ownership-contract.md
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-spec-requirements activity-identity [queue: .kiro/queue/2026-10-01-req-9-3-says-an-unchanged-base-keeps-its-filename-but-req-6-6-renames-it.md] Reword Req 9.3 so the contract statement carries Req 6.6's settle-rename exception"
context:
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
  - docs/ownership-contract.md
  - src/fitdocs/declaration.py
blocked_by: []
---

## What
Req 9.3 requires the ownership contract to state "that a page whose base does
not change keeps its filename". Req 6.6 requires fitdocs, after a run, to rename
each page it wrote under a collision-suffixed name to the unsuffixed name once
that name is free, with no base change involved. Read literally, a contract that
satisfies 9.3 is false of 6.6's pages.

## Why it matters
The implementation resolved it correctly, but only in prose, so the requirement
text and the acceptance test it implies disagree. A later session verifying the
contract against Req 9.3 as written would either flag the shipped sentence or
delete its exception.

## Evidence
Read at `fc5c06d`.
- `.kiro/specs/activity-identity/requirements.md:204` (6.6) and `:242` (9.3).
- `docs/ownership-contract.md:604-608`: "A page whose base does not change keeps
  its filename, including one you chose, except that a page fitdocs wrote under
  a collision-suffixed name `<name>-<8 characters>.md` is moved to `<name>.md`
  once that name is free (with a rename warning)."
- `src/fitdocs/declaration.py:232-238` (`_RENAMES`) lists the settle rename as a
  second rename trigger.
- Code path: `src/fitdocs/sync.py:1953-1966` (`stranded` / `settling` renames a
  page whose base did not change).

## How to pick it up
1. Reword Req 9.3 in `requirements.md` to say the page keeps its filename except
   under Req 6.6's settle rename, and check the design's traceability row for 9.3.
2. Check whether any test pins the exception clause in the ownership contract
   (a grep of `tests/identity/test_contract_docs.py` for `collision-suffixed`,
   `settle` and `unsuffixed` found nothing at `fc5c06d`); add a pin if none does.
3. Done when requirements, design, the ownership contract and the declaration
   fragment all state the same exception.

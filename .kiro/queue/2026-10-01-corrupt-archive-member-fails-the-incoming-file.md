---
id: 2026-10-01-corrupt-archive-member-fails-the-incoming-file
title: When an already-archived file listed by the matched page cannot be decoded, the failure is reported against the innocent incoming file and does not name the corrupt one
status: open
importance: medium
importance_why: A good file is reported failed (and retried every run) with a message that points at neither the real culprit nor its archive path, so the user cannot tell which file to restore.
effort: S
kind: bug
area: activity-identity, src/fitdocs/sync.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-corrupt-archive-member-fails-the-incoming-file.md] Report a page task's undecodable archived member by its archive path, not as the incoming file's failure"
context:
  - src/fitdocs/sync.py
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
To rank a page's files, `_page_task` decodes every archived file the page lists
(`parse_fit(member_archive.read_bytes())`). If one of them is corrupt, the
exception propagates out of the page task and `_group_task` marks every live
incoming member of that task failed with the exception's reason. The incoming
file was fine; the reason (`NotFitFileError: Source is not a FIT file: header
check failed.`) names no path.

## Why it matters
The user sees a failure on a file that is not broken, with no hint that the page
already holds a damaged archive file, and the same failure repeats on every
later run that brings a file to that page. Req 7.7 covers *unresolvable*
(missing) entries, which are kept in the list and never chosen as base; a
present-but-undecodable entry has no stated behavior.

## Evidence
Reproduced at `fc5c06d`.
- `src/fitdocs/sync.py:1910` `member_activity = parse_fit(member_archive.read_bytes())`
  in `_page_task`; `src/fitdocs/sync.py:1559-1562` `_group_task`'s
  `except Exception as exc:` sets `outcomes[member.position] = _Outcome("failed", _reason(exc))`
  for every `live` member.
- Repro: `fitdocs sync` the builder's `reexport_a_fit_bytes()` into a fresh data
  root; overwrite its `fit-archive/<sha>.fit` with `b"not a fit file at all"`;
  `fitdocs sync` a directory holding `reexport_b_fit_bytes()` (a valid
  re-export of the same session). Output: `Failed: <path>/reexport_b.fit
  NotFitFileError: Source is not a FIT file: header check failed.`, and the load
  pass then also fails the page.

## How to pick it up
1. Add the e2e test from the repro (`tests/test_identity_e2e.py` helpers).
2. In `_page_task`, decode each archived member separately: an undecodable
   listed member becomes an `unresolved` ref (kept at the front of `sources`,
   never the base, as Req 5.3 / 7.7 treat a missing one) with a warning naming
   its archive path; or fail the task with a reason that names the archive
   path. Choose, then pin which file name appears in the report.
3. Check regen's per-page rebuild (`_process_isolated`) gives the same
   attribution, since it shares `_page_task`.

## Open questions
- Is an undecodable listed file "unresolved" (page still rendered from the
  others, mirroring Req 7.7) or a hard failure of the page? The first keeps
  the incoming file archived and the page current; requirements do not say.

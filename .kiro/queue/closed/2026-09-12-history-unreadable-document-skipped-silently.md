---
id: 2026-09-12-history-unreadable-document-skipped-silently
title: Req 1.9 says an unreadable workout document is skipped AND named; the history scan drops it silently because docio cannot distinguish unreadable from non-document
status: done
importance: high
importance_why: A permission-denied or corrupt workout document vanishes from the history page and its report; the coverage statement's "skipped" figure can only ever count undated pages, so Req 3.5's "skipped as unreadable" is unreachable.
effort: M
kind: inconsistency
area: load-history, wiki-contract, src/fitdocs/history/documents.py, src/fitdocs/docio.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 3.1 (reviewer round 1, follow-up 1)
pinned_at: 8cd0062
resume_command: "do: land the finished fix on origin/chore/q-history-unreadable -- rebase onto main, resolve the CHANGELOG.md conflict, re-run the three gates, merge per change-protocol.md, then close this item and 2026-10-05-history-negative-load-uncaught-traceback"
context:
  - .kiro/specs/load-history/requirements.md
  - .kiro/specs/load-history/design.md
  - src/fitdocs/history/documents.py
  - src/fitdocs/docio.py
  - src/fitdocs/audit.py
blocked_by: []
---

## What
requirements.md Req 1.9, Req 3.5, the traceability row and the Error Handling
paragraph (design.md ~1588) say an unreadable document is skipped and named.
The DocumentScan component (~896–899) and task 3.1 say `read_frontmatter is
None` → silent skip, because `docio.read_frontmatter` collapses symlink,
OSError, decode error, no fence and bad YAML into one `None`, and naming every
`None` would report `workouts/AGENTS.md` on every run. The implementation
follows the component text. design.md ~1588–1591 additionally lists non-workout
`.md` and unparsable `load_value` as SkippedPage cases, contradicting the
component section.

## Why it matters
A workout document the athlete cannot see in the report is exactly the class
of silent data loss the ownership contract exists to prevent.

## Evidence
`tests/history/test_documents.py` — a permission-denied file at
`workouts/denied.md` is neither a page nor a skip (probe in the 3.1 round-1
review). `src/fitdocs/docio.py:89-95`; `src/fitdocs/audit.py:326-341`
distinguishes the causes.

## How to pick it up
Read docio's read path and audit's `_read_document`; decide the docio API
(a result type, or a second function). Then: documents.py names unreadable
workout files with a reason, excludes the declaration by name, and the two
design passages are reconciled. Done when a chmod-0 workout document appears
in `report.skipped` with its reason and the page's archive-wide skipped count.

## Update 2026-10-19 -- a finished fix exists and never landed

Found by the 0.2 release-readiness triage at `4f1c1f4`. Branch
`origin/chore/q-history-unreadable` (8 commits, 2026-10-18, no PR) carries
`272d70c fix(history): name unreadable workout documents in the skipped list
(Req 1.9)` and `75b15e2 fix(contract): frontmatter_block_error catches the
shared YAML load-error tuple`, plus the fix for the sibling item
`2026-10-05-history-negative-load-uncaught-traceback` (`ceeae9c`, `a3db1e6`,
`7c3e7ac`). CI is green at its tip (run 39136120605). `git cherry origin/main
origin/chore/q-history-unreadable` -> 8 `+`; none landed. The agent log holds
no record of why it stopped.

`git merge-tree --write-tree origin/main origin/chore/q-history-unreadable` at
`4f1c1f4`: code merges cleanly; the only conflict is `CHANGELOG.md`.

## Resolution

Done 2026-10-19: `chore/q-history-unreadable` landed (rebased onto main; only
CHANGELOG.md conflicted). `contract.frontmatter_block_error` distinguishes a
closed block YAML cannot read from a non-document, and the history scan names
unreadable workout documents (permission denied, not UTF-8, unparsable or
unconstructible YAML) in `report.skipped` and the page's skipped list, while
files that were never documents stay silent. Pinned by
`tests/history/test_documents.py::test_a_permission_denied_workout_document_is_skipped_and_named`,
`..._not_utf8_is_skipped_and_named`, `..._will_not_parse_is_skipped_and_named`,
`test_files_that_were_never_workout_documents_stay_silent`, and
`tests/test_contract.py::test_frontmatter_block_error_*` (all green at the
landing tip).

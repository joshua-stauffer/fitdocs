---
id: 2026-09-12-history-unreadable-document-skipped-silently
title: Req 1.9 says an unreadable workout document is skipped AND named; the history scan drops it silently because docio cannot distinguish unreadable from non-document
status: open
importance: high
importance_why: A permission-denied or corrupt workout document vanishes from the history page and its report; the coverage statement's "skipped" figure can only ever count undated pages, so Req 3.5's "skipped as unreadable" is unreachable.
effort: M
kind: inconsistency
area: load-history, wiki-contract, src/fitdocs/history/documents.py, src/fitdocs/docio.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 3.1 (reviewer round 1, follow-up 1)
pinned_at: 8cd0062
resume_command: "do: decide whether docio.read_frontmatter (or a sibling) should return a distinguishing result for unreadable vs not-a-document (audit._read_document is the precedent), then make history/documents.py name unreadable workout documents in SkippedPage per Req 1.9 and correct design.md's DocumentScan text and Error Handling paragraph to match"
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

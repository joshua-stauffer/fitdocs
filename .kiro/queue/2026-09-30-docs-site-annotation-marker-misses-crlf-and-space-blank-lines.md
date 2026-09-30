---
id: 2026-09-30-docs-site-annotation-marker-misses-crlf-and-space-blank-lines
title: The docs-site annotation marker misses CRLF pages and whitespace-only blank lines, so the block leaks into the site
status: open
importance: medium
importance_why: A leaked iA Writer authorship block publishes editorial annotations on fitdocs.ai, against docs-site 1.6 and 1.8; the fixture self-test refuses CR, so no test would show it.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/model.py, .kiro/specs/docs-site/design.md
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (task 2.1 review)
pinned_at: dd0d648
resume_command: "/kiro-spec-design docs-site [queue: .kiro/queue/2026-09-30-docs-site-annotation-marker-misses-crlf-and-space-blank-lines.md] Decide how the annotation strip treats CRLF and whitespace-only blank lines"
context:
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/requirements.md
  - scripts/sitebuild/model.py
blocked_by: []
---

## What
`model.ANNOTATION_MARKER` is `"\n\n---\nAnnotations:"`, and design § ContentLoader
prescribes `strip_annotation` as `rfind(ANNOTATION_MARKER)` keeping `text[: i + 1]`.
A page saved with CRLF line endings, or whose "blank" line before the `---` holds
spaces, does not contain that exact marker, so its annotation block is left in
place and published.

## Why it matters
The maintainer's copy is written in iA Writer. A page that arrives with CRLF,
from another editor or a git autocrlf setting, or with a trailing space on the
blank line, publishes the authorship block ("Annotations: … &Claude: … @Josh: …")
on fitdocs.ai and in llms-full.txt. Requirement 1.8 says the block never reaches
any output.

## Evidence
On branch impl/docs-site (scripts/sitebuild/content.py, task 2.1):
- `strip_annotation("a\r\n\r\n---\r\nAnnotations: x\r\n")` returns the input unchanged.
- `strip_annotation("a\n \n---\nAnnotations: x\n")` returns the input unchanged.
- `tests/sitebuild/test_fixture_site.py` refuses CR in fixture files, so no
  fixture exercises the case.

## How to pick it up
1. Check whether task 2.2 or any later stage refuses CR in page files. If CRLF
   already fails the build, only the whitespace-blank-line case remains; lower
   the importance.
2. Decide between refusing such pages with a Problem naming the file (fail
   loud) and normalising before matching, which conflicts with 1.6's
   byte-for-byte promise.
3. Amend design § ContentLoader and pin the choice with a test.

## Open questions
- If the choice changes the content contract in docs/website.md, it is the
  maintainer's call.

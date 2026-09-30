---
id: 2026-09-30-docs-site-unreadable-dirs-and-special-files-in-content
title: Specify how docs-site discovery handles unreadable directories and FIFOs or sockets in the content directory
status: open
importance: low
importance_why: Both are rare in a content folder, but today one crashes the build with a raw OSError and the other would hang the byte-copy stager.
effort: S
kind: gap
area: docs-site, .kiro/specs/docs-site/design.md
created: 2026-09-30
surfaced_by: /kiro-impl docs-site (task 2.1 review)
pinned_at: dd0d648
resume_command: "/kiro-spec-design docs-site [queue: .kiro/queue/2026-09-30-docs-site-unreadable-dirs-and-special-files-in-content.md] Specify discovery's handling of unreadable directories and special files"
context:
  - .kiro/specs/docs-site/design.md
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What
The docs-site design (§ ContentLoader, § Error Handling) does not say what
discovery does with an unreadable directory, or with an entry that is neither a
regular file nor a directory (a FIFO, socket or device). Task 2.1 settled on
this behaviour by controller ruling:
- An unreadable directory under an excluded (`_`/`.`) name, or under a reserved
  root name, is skipped, since it contributes nothing to the site.
- An unreadable **included** directory raises `OSError` out of `discover`, so
  its pages are never silently dropped.
- A FIFO or socket is carried as an `Asset`.

## Why it matters
- The raw OSError needs mapping to an exit class and a one-line problem
  (requirements 2.9, 6.5). Without that, the CLI (task 3.5) shows a traceback.
- A FIFO carried as an asset would block the byte-copy stager (task 3.2) on
  read.

## Evidence
On branch impl/docs-site, `scripts/sitebuild/content.py` `discover`:
- its `try/except OSError` around `os.scandir` re-raises unless the directory
  is inside an excluded subtree;
- its final `else` sends every entry that is not a directory or a symlink to
  `assets`.

## How to pick it up
1. Decide whether an unreadable included directory is a `Problem` (exit 1, one
   line naming it) or an exit-2 error, and whether a special file is refused as
   a `Problem`.
2. Amend design § ContentLoader and § Error Handling.
3. Change `discover` and `tests/sitebuild/test_content.py`, where
   `test_an_unreadable_included_directory_raises` pins today's behaviour.

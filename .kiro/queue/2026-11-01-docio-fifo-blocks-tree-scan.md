---
id: 2026-11-01-docio-fifo-blocks-tree-scan
title: "A FIFO named *.md in workouts/ blocks docio tree scans forever"
status: open
importance: low
importance_why: Needs a hostile or accidental FIFO in the data tree, but the symptom is a silent hang.
effort: S
kind: bug
area: src/fitdocs/docio.py, src/fitdocs/publish/pages.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: make docio.read_bytes refuse non-regular files and test a FIFO named *.md in workouts/ [queue: .kiro/queue/2026-11-01-docio-fifo-blocks-tree-scan.md]"
context:
  - src/fitdocs/docio.py
  - src/fitdocs/publish/pages.py
blocked_by: []
---

## What
Selecting all pages (`publish.pages._top_level_pages` -> `docio.read_document`
-> `read_bytes`) and other docio tree scanners block forever on a FIFO named
`*.md` in `workouts/`. `read_bytes()` has no regular-file check.

## Why it matters
A single stray special file hangs the command with no message.

## Evidence
`src/fitdocs/docio.py:155-161`. Reproduce with `mkfifo workouts/x.md` in a scratch
data root, then run a tree scan.

## How to pick it up
Check `stat.S_ISREG` before opening in `read_bytes` and raise the existing
document-read error; add a test using `os.mkfifo`.

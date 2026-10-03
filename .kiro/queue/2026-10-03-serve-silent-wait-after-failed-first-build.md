---
id: 2026-10-03-serve-silent-wait-after-failed-first-build
title: serve gives no hint that it is waiting (no server yet) after a failed first build
status: open
importance: low
importance_why: Cost a maintainer a debugging round-trip; preview-only, no data or contract impact.
effort: S
kind: gap
area: docs-site, scripts/sitebuild/preview.py
created: 2026-10-03
surfaced_by: maintainer report "unable to start the local server"
pinned_at: 6ce34fe
resume_command: "do: in scripts/sitebuild/preview.py serve(), when a build fails before the serve process has started, print one line saying nothing is served yet and the server starts after the first clean build; pin it in the preview tests"
context:
  - scripts/sitebuild/preview.py
  - scripts/build_site.py
  - .kiro/specs/docs-site/requirements.md
blocked_by: []
---

## What
When the first build under `python -m scripts.build_site serve` fails a content
check, `serve()` prints only the problem lines and keeps polling. No server
starts until a clean build, so localhost:8000 refuses connections. Nothing
says the loop is still alive and waiting for a fix, so the run looks crashed.

## Why it matters
On 2026-10-03 the maintainer saw `changelog.md: source: key is not allowed by
the content contract`, then "Unable to connect", and took it as a failure to
start. The fix would have been to edit the file and let the running loop pick
it up.

## Evidence
`scripts/sitebuild/preview.py` serve(): on `not outcome.ok` it prints
`outcome.problems` and falls through to the poll loop with `process is None`;
`start_serve` runs only after a successful build.

## How to pick it up
1. Read serve() in scripts/sitebuild/preview.py and the docs-site requirement
   7.x text it cites.
2. Add one stderr line when a build fails and `process is None` (and maybe one
   after a later failure: "still serving the last good build").
3. Pin the wording in the preview tests. Check that the docs-site spec wording
   allows the extra line, or amend the spec.

---
id: 2026-11-02-strava-publish-dockerignore-comment-omits-changelog-and-live-check
title: "relay/.dockerignore says it keeps everything else out of the context but does not list CHANGELOG.md or the live-check files"
status: open
importance: low
importance_why: "Comment/list mismatch only; the image is unaffected because the Dockerfile copies named paths."
effort: S
kind: chore
area: "relay/.dockerignore"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish task 8 review"
pinned_at: 964cc419
resume_command: "do: list CHANGELOG.md and LIVE_CHECK_STRAVA*.md in relay/.dockerignore or soften its header comment (read .kiro/queue/2026-11-02-strava-publish-dockerignore-comment-omits-changelog-and-live-check.md first)"
context:
  - relay/.dockerignore
  - relay/Dockerfile
blocked_by: []
---

## What
The header says the file keeps everything except the named copy paths out of the build context, but CHANGELOG.md, LIVE_CHECK_STRAVA.md and LIVE_CHECK_STRAVA_RECORD.md are present in relay/ and not ignored.

## Why it matters
Cosmetic; slightly larger build context.

## Evidence
`head -5 relay/.dockerignore` shows the header and only `.venv`, `.git`, `__pycache__`...; `ls relay` lists CHANGELOG.md, LIVE_CHECK_STRAVA.md, LIVE_CHECK_STRAVA_RECORD.md.

## How to pick it up
Read relay/.dockerignore fully, add the three names, and check whether a test pins the file's content.

---
id: 2026-10-01-docs-site-preview-sigterm-orphans-serve
title: "SIGTERM to `build_site serve` orphans the `zensical serve` child, which keeps holding the port"
status: open
importance: low
importance_why: "Only on a non-Ctrl-C stop (IDE stop button, kill); next preview then fails with a busy port."
effort: S
kind: bug
area: docs-site, scripts/sitebuild/preview.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-preview-sigterm-orphans-serve.md] SIGTERM to `build_site serve` orphans the `zensical serve` child, which keeps holding the "
context:
  - scripts/sitebuild/preview.py
  - tests/sitebuild/test_preview.py
  - .kiro/specs/docs-site/design.md
blocked_by: []
---

## What
`preview.serve` only catches KeyboardInterrupt, so on SIGTERM its `finally` (which terminates the serve child) does not run and `zensical serve` survives the parent.

## Why it matters
A stale `zensical serve` keeps the port; the next `build_site serve` exits 2 with `site generator: serve exited with status 1` (busy port), and the maintainer must find and kill the orphan by hand.

## Evidence
- `scripts/sitebuild/preview.py:112` `except KeyboardInterrupt:` / `:114` `finally:` -- no SIGTERM handler (pinned at ba76d03).
- Reported by the 6.1 round-3 reviewer subagent: terminating the `uv run ... build_site serve` parent left `zensical serve -f mkdocs.yml -a 127.0.0.1:61438` running. Behaviour not re-run by the controller.

## How to pick it up
1. Read `scripts/sitebuild/preview.py` `serve` and its `_terminate`.
2. Install a SIGTERM handler for the loop's lifetime that raises (e.g. `KeyboardInterrupt` or a private exception) so `finally` runs; restore the previous handler on exit.
3. Test: spawn the preview as a subprocess against the fixture site, SIGTERM it, assert the serve pid is gone (`tests/sitebuild/test_preview.py` already has pid-liveness helpers). Needs a Dies-on line.

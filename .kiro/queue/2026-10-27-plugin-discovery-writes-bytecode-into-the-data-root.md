---
id: 2026-10-27-plugin-discovery-writes-bytecode-into-the-data-root
title: Loading a local plugin from inside the data root writes __pycache__ there, before any preflight
status: open
importance: low
importance_why: Contradicts a stated guarantee ("no write to data_root ever occurs") and the CLI's "nothing written before a config error" promise, but only for users who keep plugins inside their data root.
effort: S
kind: bug
area: plugin-api, src/fitdocs/plugins.py, src/fitdocs/cli.py
created: 2026-10-27
surfaced_by: /kiro-impl compact-chart-assets (task 5.3 review)
pinned_at: 260c3ff8
resume_command: "do: make plugins._load_local_file import without writing bytecode (e.g. set sys.dont_write_bytecode around exec_module, or use a no-cache loader) and pin that discovery leaves the data root unchanged"
context:
  - src/fitdocs/plugins.py
  - src/fitdocs/cli.py
  - .kiro/specs/plugin-api/design.md
  - tests/test_cli_encoder_preflight.py
blocked_by: []
---

## What
`plugins.discover`'s docstring says "no write to ``data_root`` ever occurs"
(src/fitdocs/plugins.py:337). But `_load_local_file` imports a local plugin
with `spec.loader.exec_module(module)` (plugins.py:613) without
`sys.dont_write_bytecode` set. With `[plugins] path = "plugins"` inside the
data root, discovery writes `plugins/__pycache__/<name>.cpython-311.pyc`.
That happens before `_basemap_preflight` and before any other config check, so
a run that exits 2 still leaves a new file behind.

## Why it matters
Both claims become false for that setup: the plugin guarantee, and the CLI's
"exit 2 before any write". The `.pyc` also lands in a folder the user may
sync or keep under git.

## Evidence
- plugins.py:337 (the docstring) and :613 (`exec_module`). Verified in this run.
- Reported by the 5.3 reviewer subagent, not reproduced by me: with `plugins/p.py` in a scratch data root and no WebP encoder, `fitdocs regen` exits 2 and leaves `plugins/__pycache__/p.cpython-311.pyc`.

## How to pick it up
1. Reproduce it: a data root containing `fitdocs.toml` with `[plugins] path="plugins"` and a trivial `plugins/p.py`; run `fitdocs regen` and list the directory.
2. Suppress bytecode writes for local plugin loads only (save and restore `sys.dont_write_bytecode` around `exec_module`).
3. Add a test that snapshots the data root around discovery. Show that it reds without the fix.
</content>
</invoke>

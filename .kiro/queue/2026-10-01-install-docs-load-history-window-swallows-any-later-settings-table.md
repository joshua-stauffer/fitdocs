---
id: 2026-10-01-install-docs-load-history-window-swallows-any-later-settings-table
title: The install-docs guard's [load]/[history] window runs to the next "## " heading, so a settings table documented after [history] is read as part of it
status: open
importance: low
importance_why: Passing today; the first new settings table placed after `[history]` makes the "no unknown backticked key" test red with a message that blames the wrong section.
effort: S
kind: gap
area: distribution, tests/test_install_docs.py, docs/configuration.md
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "do: end the window in tests/test_install_docs.py _load_history_section_text at the first '### ' heading after the [history] heading (not the next '## '), and add a test that a heading placed after [history] is outside the window"
context:
  - tests/test_install_docs.py
  - docs/configuration.md
blocked_by: []
---

## What
`_load_history_section_text()` returns the text from the `### `[load]`` heading to
the next `## ` (level-2) heading. That is meant to be the two sections
documenting the load and history tables, but the end is defined by a level-2
heading, not by the end of `[history]`. Any level-3 section placed between
`[history]` and the next `##` heading is silently inside the window, and every
backticked, key-shaped token in it is checked as a `[load]`/`[history]` key.

## Why it matters
The activity-identity spec added `[identity]` to `docs/configuration.md` ahead of
`[load]`, so it stayed outside the window by placement luck. The connectors spec
plans a `[connectors]` settings table (`.kiro/specs/connectors/design.md`, the
"`[connectors]` table reader"); documented after `[history]` it would fail
`test_load_history_section_names_no_backticked_key_that_is_not_real` with an
"unknown key" message about keys that are not load or history settings, and a
future author may "fix" it by adding those keys to the real-keys table.

## Evidence
Read and demonstrated at `fc5c06d`.
- `tests/test_install_docs.py:350-367` `_load_history_section_text`
  (`start = text.index("### `[load]`")`, `next_h2 = re.search(r"^## ", ...)`).
  Consumers: `:464`, `:484`, `:503`.
- `docs/configuration.md` headings: `### [identity]` `:177`, `### [load]` `:236`,
  `### [history]` `:276`, next `## The athlete profile` `:292`.
- Demonstration (in memory, file untouched): inserting
  `### `[connectors]`: example` with a backticked `pull_interval_s` bullet before
  `## The athlete profile` puts `` `pull_interval_s` `` inside the returned window.
  `uv run pytest tests/test_install_docs.py` currently passes (44 tests).

## How to pick it up
1. Add the failing test first: construct the configuration text with an extra
   `###` section after `[history]` and assert it is outside the window (the helper
   reads the file through `_configuration_text()`, so parametrize it or split the
   slicing into a pure function of the text).
2. End the window at the first `### ` heading after the `[history]` heading, or
   at the next `## `, whichever comes first.
3. Done when the new test passes and the 44 existing tests still do.

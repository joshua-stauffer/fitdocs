---
id: 2026-10-02-plugins-table-tests-fail-under-narrow-columns
title: Two `fitdocs plugins` table tests fail whenever COLUMNS is narrow, because Rich truncates the path cell they assert on
status: open
importance: low
importance_why: Latent -- CI does not set COLUMNS so it passes there -- but a contributor with a narrow terminal or COLUMNS exported sees two unexplained failures on a clean checkout.
effort: S
kind: bug
area: plugin-api, tests/test_cli.py, src/fitdocs/cli.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors (task 5.3 review)
pinned_at: ad985b3
resume_command: "do: make tests/test_cli.py's plugins-table tests independent of the terminal width (set COLUMNS in the test's env or assert on the report data rather than the rendered cell), then confirm COLUMNS=60 uv run pytest tests/test_cli.py -q passes"
context:
  - tests/test_cli.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What
`tests/test_cli.py::test_plugins_lists_injected_distribution_plugin_with_name_and_version`
and `::test_plugins_renders_unknown_for_none_version` assert that strings such
as `plugins/local.py` appear in `result.output`. The `fitdocs plugins` table
(`src/fitdocs/cli.py:1443`, `Table(title="fitdocs plugins")`) has five
columns; under a narrow `COLUMNS` Rich truncates cells with an ellipsis, so
the asserted text is not in the output.

## Why it matters
Test results should not depend on the developer's terminal. The failure looks
like a real regression and costs a contributor time to rule out. The same
pattern (asserting on a Rich-rendered cell) recurs in other CLI tests, so the
fix is a convention worth stating.

## Evidence
Run at `ad985b3`:

```
$ COLUMNS=60 uv run pytest tests/test_cli.py -q -k "plugins_lists_injected_distribution_plugin_with_name_and_version or plugins_renders_unknown_for_none_version"
E   AssertionError: assert 'plugins/local.py' in '...│ plugins/l… │ ...'
FAILED tests/test_cli.py::test_plugins_lists_injected_distribution_plugin_with_name_and_version
FAILED tests/test_cli.py::test_plugins_renders_unknown_for_none_version
2 failed, 37 deselected
```

Reported by the connectors task 5.3 reviewer as also failing on `main`; not
re-run on `main` in this session.

## How to pick it up
1. Run the command above to reproduce.
2. Either pass `env={"COLUMNS": "200"}` to these `runner.invoke` calls (the
   smallest fix), or set it once in a `tests/conftest.py` autouse fixture so
   every CliRunner test is width-independent -- check first that no test
   relies on the 80-column default (several soft-wrap tests do; see
   `.kiro/queue/2026-09-18-config-error-output-surface-wrap-and-stderr.md`).
3. Done when the two tests pass under `COLUMNS=60` and `COLUMNS=200`.

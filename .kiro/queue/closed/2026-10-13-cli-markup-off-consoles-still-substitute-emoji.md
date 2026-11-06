---
id: 2026-10-13-cli-markup-off-consoles-still-substitute-emoji
title: Rich consoles in cli.py built with markup=False but without emoji=False turn a `:a:` in user-derived text into an emoji
status: done
importance: medium
importance_why: It also fires with no user data at all, on fitdocs' own message naming the end marker a page needs, so the printed fix is wrong; the original case needs a colon-delimited shortcode in a page path, an error message or a producer name.
effort: S
kind: bug
area: src/fitdocs/cli.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 6.2 reviewer)
pinned_at: 0a98d5c
resume_command: "do: add emoji=False to every Console(markup=False, ...) in src/fitdocs/cli.py that prints user-derived text (the index pass lines and report first), and pin one with a :a: path as test_pass.py:573 does for the dashboard pass [queue: .kiro/queue/2026-10-13-cli-markup-off-consoles-still-substitute-emoji.md]"
context:
  - src/fitdocs/cli.py
  - tests/dashboards/test_pass.py
  - .kiro/queue/2026-09-19-prompts-print-swallows-y-n-markup.md
blocked_by:
  - dashboards
---

## What
The dashboard pass already prints through `Console(markup=False, emoji=False,
highlight=False, soft_wrap=True)` (`src/fitdocs/cli.py:599, 613, 617`) and
`test_a_key_that_looks_like_an_emoji_code_prints_verbatim`
(`tests/dashboards/test_pass.py:573`) pins it. The older consoles that print
index-pass output turn off markup but leave rich's emoji substitution on, so
`:a:` becomes a emoji glyph.

## Why it matters
`Index: could not index workouts/2026-:a:.md: ...` prints the file as a
different name. The 6.2 reviewer reported "~45" such sites; the count below is
what a grep finds now.

## Evidence
At 0a98d5c, `src/fitdocs/cli.py`:
- Consoles built with `markup=False` and no `emoji=False`: lines 526 (`_index_progress`), 556 (`_run_index_pass` except branch, prints `{type(exc).__name__}: {exc}`), 626 (`_report_index_pass`, prints page paths and errors), 677 (`_report_index_command`), 1986, 2172, 2220 (the query and dashboard stderr consoles). Seven sites; 556, 626, 677 and 1986 print user-derived text (page paths, exception text, the index file path, query state and messages), while 526, 2172 and 2220 print only counts and fixed strings. The reviewer's "~45" is not reproduced and what it counted is unknown; this item's count comes from `grep -n "Console(" src/fitdocs/cli.py | grep -v "emoji=False"`, which also lists twenty default `Console()` calls (markup and emoji both on) that are a different, wider problem.
- Real rich output, same arguments as the `_report_index_pass` console:
  ```
  Console(markup=False, highlight=False, soft_wrap=True).print("Index: could not index a/:a:.md: bad")
  -> Index: could not index a/🅰.md: bad
  same with emoji=False
  -> Index: could not index a/:a:.md: bad
  ```
- The only other `Console` constructor outside `cli.py` is `src/fitdocs/load/prompts.py:291` (default console), covered by `2026-09-19-prompts-print-swallows-y-n-markup`.

## Update 2026-11-06: seen on fitdocs' own text
At 35311b53, `fitdocs load --no-prompt` over one hand-written `type: workout` page printed:

```
LoadDocError: document has no reserved 'load' region -- expected '<!-- fitdocs:begin:load -->' ... '<!-- fitdocs🔚load -->'
```

The marker fitdocs tells the reader to add has `:end:` replaced by an emoji, because `:end:` is a shortcode. No user text is involved, so any message that prints an end marker is exposed. Which console printed this line was not traced; the failure report's console is the first to check. The line numbers in Evidence above have moved (`grep -n "Console(" src/fitdocs/cli.py | grep -v "emoji=False"` lists them now).

## How to pick it up
1. Add `emoji=False` at least at the four sites that print user-derived text, and at the other three for uniformity (a small `_plain_console(stderr=False)` helper would also remove the repeated keyword list).
2. Pin one of them as `tests/dashboards/test_pass.py:573` does: a data root whose index pass prints a page error containing `:a:`, and assert the glyph is absent.
3. Leave the default-`Console()` sites alone unless the change is wanted for them too (not audited here).

## Open questions
Whether to extend the same treatment to the twenty default consoles. They were not audited here; some may print athlete-derived names.

## Update 2026-11-06: fixed on chore/pre-cut-fixes
`src/fitdocs/cli.py` now defines a `Console` subclass that defaults to `emoji=False`, so every console built there is covered, default ones included. That answers the open question: the sighting above came from a default `Console()` built in `_report_load`, printed through `_print_detail`, which this item's list did not include, and no string under `src/` means an emoji code. Not changed: `src/fitdocs/load/prompts.py:292` builds its own console (see `2026-09-19-prompts-print-swallows-y-n-markup`), and default consoles still parse markup, as the class docstring says. A scan of `cli.py` found three f-string prints on such consoles, all fixed labels, so no bracket-loss case was shown; table cells were not audited. Left open for the maintainer to close.

## Resolution
2026-11-06. `cli.py` builds every console through a subclass defaulting to `emoji=False`, on `main` at ac4bc942 and 4d2a8780. Removing the default reds five tests, and the stderr case is pinned. `fitdocs load` now prints `<!-- fitdocs:end:load -->` correctly. `load/prompts.py` is tracked by `2026-09-19-prompts-print-swallows-y-n-markup`. The maintainer approved closing.

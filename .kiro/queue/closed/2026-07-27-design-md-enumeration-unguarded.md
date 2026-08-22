---
id: 2026-07-27-design-md-enumeration-unguarded
title: plugin-api's design.md public-surface enumeration has no mechanical guard, and has now gone stale three times
status: done
importance: high
importance_why: `docs/plugins.md` is bidirectionally guarded and design.md is not, so the next export added by threshold-load forces the doc to update and lets the design go stale a fourth time. Three recurrences of one defect is a guard gap, not bad luck.
effort: S
kind: gap
area: plugin-api, tests/test_docs_guarantees.py
created: 2026-07-27
surfaced_by: adversarial review of impl/plugin-api-surface (queue sweep 2026-07-27)
pinned_at: d8888b6
resume_command: "do: add a guard on .kiro/specs/plugin-api/design.md's public-surface enumeration, mirroring tests/test_docs_guarantees.py:296 test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_list which already does this for docs/plugins.md — including the {registry} exemption pinned at :345-346, and handling the root package's 'decode errors' prose gloss (either expand it to the three names or teach the guard about it) [queue: .kiro/queue/2026-07-27-design-md-enumeration-unguarded.md]"
context:
  - .kiro/specs/plugin-api/design.md
  - tests/test_docs_guarantees.py
  - tests/test_public_api.py
  - src/fitdocs/load/__init__.py
blocked_by: []
---

## What

`.kiro/specs/plugin-api/design.md` enumerates the documented public surface for
plugin authors. Nothing checks it against the real `__all__`:

- `grep -rln "\.kiro/specs" tests/` returns only `tests/load/channels/test_sources.py`,
  which is unrelated. **No test reads `plugin-api/design.md`.**
- `docs/plugins.md` *is* guarded bidirectionally —
  `tests/test_docs_guarantees.py:296`
  (`test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_list`),
  with the `{"registry"}` exemption pinned at `:345-346`.
- `tests/test_public_api.py`'s check is an **inclusion** check, so it does not
  fail when a name is *added* to `__all__`.

The design's own sentence — "`tests/test_public_api.py` guards the list (5.5)" —
overstates what is guarded: that test guards the shipped surface, not this
enumeration.

## Why it matters

The asymmetry has a predictable consequence. When `threshold-load` adds its
first export, `docs/plugins.md` is *forced* to update by its guard, and
`design.md` silently goes stale — for the fourth time. The three prior
recurrences are why queue item
`2026-07-26-plugin-surface-list-stale-after-amendment-3` existed at all; that
item's step 2 asked for a durable fix and got one for `docs/plugins.md` only.

A plugin author reading a stale design enumeration cannot discover the
parameters `compute` requires, which is the same failure that item was opened
against.

## Evidence

Gathered by the adversarial reviewer of `impl/plugin-api-surface`
(2026-07-27), which independently reproduced the set diff and found the
enumeration currently correct — then established that nothing keeps it so:

```
$ grep -rln "\.kiro/specs" tests/
tests/load/channels/test_sources.py        # unrelated
```

Guard that exists for the sibling doc: `tests/test_docs_guarantees.py:296`,
exemption at `:345-346`. Inclusion-only guard: `tests/test_public_api.py:136-146`.

## How to pick it up

1. Read `tests/test_docs_guarantees.py:296-346` — the guard to mirror, including
   how it pins the `registry` exemption and why `registry` is excluded
   (`docs/plugins.md:277-280` and `tests/test_public_api.py:138` both make the
   same call).
2. Note the one structural difference: the `fitdocs.load` half of the design's
   enumeration is name-exact and machine-diffable, but the root-package half
   covers `FitDecodeError`/`FitIntegrityError`/`NotFitFileError` under the prose
   gloss "decode errors". Either expand the gloss to the three names or teach
   the guard about it — do not silently skip the root half.
3. Fixture discrimination per change-protocol.md: add a name to
   `fitdocs.load.__all__`, show the new guard RED, revert, GREEN.

Done looks like: adding an export to `__all__` without updating design.md fails
the suite, exactly as it already does for `docs/plugins.md`.

## Resolution

Closed 2026-07-29, merged to `main` as `5214c30` (branch
`chore/plugin-api-surface-guard`, 6 commits, `--ff-only`, validated after
rebase onto `94f72ba`: 2092 passed, ruff check + `ruff format --check` +
mypy clean). Three adversarial review rounds.

**The guard**: `tests/test_docs_guarantees.py` now carries
`test_design_doc_public_surface_list_names_actually_import` and
`test_every_fitdocs_load_export_appears_in_the_design_doc_surface_list`,
mirroring the `docs/plugins.md` pair. The `{registry}` exemption is handled
as in the original; the `"decode errors"` prose gloss was **expanded** to its
three names (`FitDecodeError`, `NotFitFileError`, `FitIntegrityError`) rather
than teaching the guard an exemption — one of the two branches this item's
own `resume_command` offered.

**Two defects found in review, both closed:**

1. The first locator was an unanchored whole-document `text.index()`. An
   Oxford-comma edit 700 lines away in the Allowed Dependencies section, plus
   deleting `LoadCalculator`, left the guard **green** while swallowing five
   exports. Fixed by anchoring the `fitdocs.load` search to begin after the
   root marker's own match.
2. The backstop was first a 700-char cap, which had ~11 names of headroom on
   a surface that took 5 new exports in one day this month, and whose failure
   message misdiagnosed legitimate growth as a marker bug. Replaced with a
   scale-free **name-density check** (>50% of segment chars inside
   backtick-quoted names). Density rises with list length, so name growth can
   never trip it.

**Verified**: independent 29/29 exhaustive load-name sweep, zero survivors; a
sliding-window density scan of the whole document (14 of 1118 windows exceed
the threshold, all inside the enumeration); and three distinct wrong-region
attack shapes, each caught.

**Honest residual, now documented rather than overstated**: the `fitdocs`
root half is guarded **forward-only** — a 19/19 root-name sweep leaves the
suite green. `design.md:816-819` now says so plainly. Tracked separately.

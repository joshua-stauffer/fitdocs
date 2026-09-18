---
id: 2026-09-12-import-guards-scope-gaps
title: Import/purity guards are scoped to import statements and miss dynamic/attribute/literal routes
status: open
importance: medium
importance_why: Several purity and single-writer guards only scan import statements, so importlib/attribute-chain/string-literal routes into the same forbidden surface pass undetected today.
effort: M
kind: gap
area: performance-benchmarks, activity-qa-flags, tests/performance/test_single_writer.py, test_reachability.py, tests/test_contract_consumers.py, tests/load/channels/test_purity.py, tests/load/threshold/test_boundary.py, tests/load/qa/test_purity.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: harden test_single_writer.py, test_reachability.py, test_contract_consumers.py, and the channels/threshold purity guards per the gaps below"
context:
  - tests/performance/test_single_writer.py
  - tests/performance/test_reachability.py
  - tests/test_contract_consumers.py
  - tests/load/channels/test_purity.py
  - tests/load/qa/test_purity.py
  - tests/load/threshold/test_boundary.py
  - src/fitdocs/performance/engine.py
blocked_by: []
---

## What

`test_single_writer.py` scans import statements only:
`importlib.import_module("fitdocs.performance")` and an unaliased
`import fitdocs.performance.types` plus the `fitdocs.performance.derive_benchmarks`
attribute chain both pass the guard today. `test_reachability.py` relies on
the sibling guards for dynamic/attribute routes rather than checking them
itself. The channels/threshold import allowlists in `test_purity.py` and
`test_boundary.py` are one-directional (real imports ⊆ allowlist), so an
unused allowlist entry is silent. `FORBIDDEN_LITERALS` in the consumer
registry (`test_contract_consumers.py`) does not include the effort key
constants — `_E = "effort_distance_m"` in `engine.py` passes the guard
today.

## Why it matters

Each of these guards exists specifically to prevent an unsanctioned route
into a forbidden surface; the gaps mean that route is currently open and
undetected by the very test written to catch it.

## Evidence

- (4.5 r2 reviewer) "test_single_writer.py: add a name-level complement
  (flag `.attr`/`.id == 'derive_benchmarks'` in a non-sanctioned module)
  plus a string-literal scan for 'fitdocs.performance' in
  import_module/__import__ calls; importlib.import_module('fitdocs.performance')
  and unaliased `import fitdocs.performance.types` + attribute chain both
  pass today (design scopes the guard to import statements)."
- (5.1 r3 reviewer) "test_reachability.py's stated scope is import
  statements only; importlib.import_module / __import__ / `import fitdocs`
  + attribute routes from channels/threshold into fitdocs.performance are
  caught only by the sibling guards -- if either sibling weakens, 10.2
  loses that coverage silently."
- (5.1 reviewer) "tests/load/channels/test_purity.py and
  tests/load/threshold/test_boundary.py import allowlists are
  one-directional (real ⊆ allowlist); an unused allowlist entry is
  silent."
- (4.5 r2 reviewer) "test_contract_consumers.py: extend FORBIDDEN_LITERALS
  with the effort key constants so 10.3's 'no second spelling of an effort
  key' is pinned at the literal level (`_E = 'effort_distance_m'` in
  engine.py passes today)."

## How to pick it up

1. Read the four guard test modules listed in `area` and the current
   `engine.py` effort key constants.
2. Add a name-level complement and string-literal scan to
   `test_single_writer.py`; add the same dynamic/attribute coverage
   directly to `test_reachability.py` rather than relying on siblings.
3. Add the reverse-direction check (unused allowlist entries fail) to
   `test_purity.py`/`test_boundary.py`; extend `FORBIDDEN_LITERALS` with
   the effort key constants in `test_contract_consumers.py`.
</content>

## Additional gap (2026-09-12, feature-level validation)

- design § Allowed Dependencies claims a structural assertion that
  `fitdocs.performance` imports nothing from `fitdocs.render`, `fitdocs.sync`
  or `fitdocs.cli`; `tests/performance/test_purity.py` covers exactly the four
  pure modules, so `src/fitdocs/performance/engine.py`'s import surface is
  unguarded. Add an engine-level import allowlist (no `render`, `sync`, `cli`,
  `load.prompts`).

## Additional gaps (2026-09-18, activity-qa-flags task 4.3 review + feature-level validation)

The same class recurs in `tests/load/qa/test_purity.py` (new,
`activity-qa-flags` task 4.3), notable because that guard's *import-boundary*
half is otherwise unusually strong — a fresh adversarial reviewer wrote 12
relative-import spellings not in the implementer's own 18 parametrized cases
and all 12 were caught, matching this item's own recommended technique. The
gaps below are specifically in the categories this item already tracks:

- **Dynamic/attribute route, confirmed by mutation**: `getattr(importlib
  .import_module("fitdocs.load"), "engine")`, an f-string import target, and
  a variable import target all pass `tests/load/qa/test_purity.py`'s
  `_boundary_violations` scanner undetected — the same limitation class this
  item's opening paragraph describes for `test_single_writer.py`. Verified
  the spelling itself parses (`ast.parse` succeeds); the evasion was
  reported by the review subagent, re-run and independently confirmed by
  the review's own second pass, not independently re-verified in this
  session.
- **Missing forbidden-module entry, not the dynamic-route class but the same
  general "guard scope narrower than requirement text" family**: `_FORBIDDEN
  _IO_OR_RANDOM_MODULES` in `tests/load/qa/test_purity.py:555-571` lists
  `pathlib`, `random`, `secrets`, `time`, and several network/LLM modules,
  but not `os` — `os.urandom(...)`, `os.environ`, `os.open(...)` all pass
  the I/O/random-source exclusion (Req 1.9) undetected. Verified directly:
  ```
  $ grep -n "_FORBIDDEN_IO_OR_RANDOM_MODULES" -A 16 tests/load/qa/test_purity.py
  _FORBIDDEN_IO_OR_RANDOM_MODULES: tuple[str, ...] = (
      "pathlib", "random", "secrets", "time", "requests", "urllib", "http",
      "socket", "ftplib", "smtplib", "httpx", "subprocess", "openai",
      "anthropic", "langchain",
  )
  ```
  No live defect: the real 8-file package imports none of `os`/`tempfile`/
  `shutil`/`io` today (checked at `d26b682`); this is a guard-strength gap
  against future drift, matching this item's own framing.

Neither gap is a live production defect — the `activity-qa-flags` package is
clean under both. Pick-up: add `os` to the forbidden-modules tuple (one
line, `S` effort); the dynamic-route gap is the same unsolved problem this
item's `How to pick it up` already describes and doesn't need a separate
plan, just wider `area` coverage when someone takes this item.

## Additional gap (2026-09-18, /kiro-validate-impl activity-qa-flags post-merge pass)

Same guard, same family, one more missing entry class — **the project's own
configuration readers**. Requirement 6.8 ("shall not read, locate, or
re-read any settings file itself") and 1.9 ("read no configuration of its
own") are pinned on the positive side —
`tests/load/threshold/test_calculator.py:1252` asserts
`call_kwargs["settings"] is computed_context.settings.flags` — but on the
negative side only by the absence of `open(...)` calls and of `pathlib`
imports. `tests/load/qa/test_purity.py` is a **denylist** (`_ALWAYS_FORBIDDEN`
at :110-126 names engine, render, docedit, registry, contract, threshold,
profile; `_LOAD_CONTRACT`; `_NAME_RESTRICTED_TARGETS` for `fitdocs.benchmarks`),
not an allowlist of permitted `fitdocs.*` targets, so a
`from fitdocs.settings import load_settings_document` or
`from fitdocs.load.settings import load_load_settings` in any qa module —
called with a `str` data root, which dodges
`test_no_function_signature_names_a_filesystem_path` — passes every purity
test. Likewise `tomllib` and `io` are absent from
`_FORBIDDEN_IO_OR_RANDOM_MODULES` (:555-571) alongside the `os` gap above.

Verified at `e16acc3`:
```
$ grep -n "fitdocs.settings\|fitdocs.load.settings\|tomllib\|\"io\"" tests/load/qa/test_purity.py
(no matches)
```
No live defect — none of the eight qa modules imports any of these
(reviewer read all eight; controller confirmed the denylist shape). Pick-up
for this piece: add `fitdocs.settings` and `fitdocs.load.settings` to
`_ALWAYS_FORBIDDEN` (note `settings.py` legitimately imports **from** qa —
`from fitdocs.load.qa.types import FlagSettings` — so the edge is inbound
only and the reverse must stay forbidden), and `os`, `io`, `tomllib` to
`_FORBIDDEN_IO_OR_RANDOM_MODULES`; the existing injected-spelling self-test
(`test_boundary_scanner_catches_every_reported_spelling`) should be extended
with one of the new names so the addition is proven live.

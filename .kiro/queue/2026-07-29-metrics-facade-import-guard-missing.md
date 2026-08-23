---
id: 2026-07-29-metrics-facade-import-guard-missing
title: The metrics facade has no import-restriction guard, leaving Req 17.3 mechanically unpinned
status: open
importance: high
importance_why: Every sibling metrics module has this guard; the one module it is missing from is the only one that reads a caller input Req 17.3 forbids reading from disk, and an env-var read of it passes all 2215 tests.
effort: S
kind: gap
area: fit-ingest, src/fitdocs/metrics/__init__.py, tests/metrics/
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest task 11 (two independent verify-gate passes)
pinned_at: c3d2201
resume_command: "do: add an import-restriction guard for src/fitdocs/metrics/__init__.py to tests/metrics/, mirroring the sibling modules' test_module_imports_from_metrics_package, so Req 17.3 gains a mechanical pin"
context:
  - src/fitdocs/metrics/__init__.py
  - .kiro/specs/fit-ingest/requirements.md
  - tests/metrics/test_stress.py
  - tests/metrics/test_sources.py
  - tests/test_determinism.py
blocked_by: []
---

## What

Every arithmetic-bearing module in `fitdocs.metrics` carries a test asserting
what it may import — `test_module_imports_from_metrics_package` in
`tests/metrics/test_power.py:136`, `test_aggregates.py:144`,
`test_zones.py:38`, `test_stress.py:96` (plus `test_stress.py:382`'s stricter
`test_module_imports_only_model_sources_and_stdlib`), and
`test_sources.py:194`'s `test_module_source_imports_only_fitdocs_citation_internally`.

`src/fitdocs/metrics/__init__.py` — the facade — has none. Nothing in
`tests/` constrains what it imports.

That is the one module where it matters most for Amendment 1. The facade is
the sole reader of the caller's weighting selection
(`src/fitdocs/metrics/__init__.py:95`, `sources.weighting_for(athlete.trimp_weighting)`),
and Req 17.3 says the library "shall accept the weighting selection as a
caller-supplied input only, and shall not read it from stored athlete profile
data or from any configuration file". Task 11 shipped that requirement
**UNPINNED and declared** for exactly this reason.

## Why it matters

Req 17.3 is currently guaranteed by nothing but the absence of code that
violates it. A future edit that reads the selection from an env var, a config
file, or a stored profile would satisfy the entire suite.

The near neighbours do not close it:

- `tests/test_determinism.py::test_write_guard_blocks_writes_but_allows_reads`
  deliberately permits reads, so a config *read* passes by design.
- The sibling guards cover `stress.py` and `sources.py`, neither of which
  reads the selection any more — task 11 moved that read into the facade.
- `tests/metrics/test_sources.py:171-178` explicitly notes that importing
  `fitdocs.metrics.sources` first runs `fitdocs.metrics.__init__`, and that
  the parent package's import behavior "is not what this test pins" —
  the gap is already known and consciously left open at that site.

## Evidence

Verified independently by two separate completion-gate passes during
`/kiro-impl fit-ingest` task 11, both executed rather than reasoned:

Adding `import os` plus an env-var fallback for the selection to
`src/fitdocs/metrics/__init__.py` leaves the **entire suite green**:

```
uv run pytest  ->  2215 passed
```

The mutation was live, not dead code — setting the env var then reddens three
facade tests:

```
FITDOCS_TRIMP_WEIGHTING=banister_female uv run pytest tests/metrics/test_facade.py
  ->  3 failed
```

So the suite cannot distinguish a facade that honours Req 17.3 from one that
violates it, until the violating path is actually exercised by configuration.

Absence of the guard, at `0ae83aa`:

```
grep -rn 'metrics/__init__\|metrics\.__init__' tests/
  ->  only tests/metrics/test_sources.py:176, a prose note disclaiming coverage
```

## How to pick it up

1. Open `tests/metrics/test_stress.py:96` (`test_module_imports_from_metrics_package`)
   and `test_stress.py:382` — they are the pattern to mirror; both walk the
   module's AST and assert on the collected import names.
2. Read the two traps recorded against those guards on this branch before
   writing a new one: a rewritten collector that admits only `fitdocs`-prefixed
   names made a sibling assertion **unreachable** while still passing, and
   dropped relative imports entirely (`node.module` is `None` when `level > 0`).
   A guard that scans zero imports passes. Assert the walk found something.
3. Add the guard for `src/fitdocs/metrics/__init__.py`. The facade legitimately
   imports its own sibling metric modules and `fitdocs.model`, so the allowed
   set is wider than `stress.py`'s — but `os`, `pathlib`, `configparser`,
   `tomllib`, and anything under `fitdocs.load` or `fitdocs.ingest` must all
   red it.
4. Prove it fails: add `import os` to the facade and confirm the new test
   reddens, then revert. A guard never shown to fail is not a guard.
5. Done when Req 17.3 can be reclassified from UNPINNED to PINNED, and the
   prose note at `tests/metrics/test_sources.py:171-178` can drop its
   "outside this task's boundary" disclaimer.

## Open questions

Whether the guard should also forbid `fitdocs.ingest` outright. The facade
must never import it (the lazy-re-export design in `src/fitdocs/__init__.py`
exists precisely to keep `garmin_fit_sdk` out of `import fitdocs.model`), but
that property is currently pinned only indirectly, by
`tests/metrics/test_sources.py:171`'s subprocess check. Folding it into the
same guard would be cheap; it is a judgment call whether one test should carry
both concerns.

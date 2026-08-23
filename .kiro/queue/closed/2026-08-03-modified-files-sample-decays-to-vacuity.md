---
id: 2026-08-03-modified-files-sample-decays-to-vacuity
title: The sweep's modified-files needle sample shrinks with every redaction task and ends near-vacuous
status: done
importance: medium
importance_why: Every remaining Major 3 task forces another entry out; the guard degrades silently and the only backstop can be satisfied by one entry.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_sweep.py
created: 2026-08-03
surfaced_by: /kiro-impl encumbered-content-purge (task 3.5 review)
pinned_at: c3d2201
resume_command: "do: re-base _MODIFIED_FILES_TABLE_SAMPLE in tests/purge/test_sweep.py onto files the purge intends to keep hitting (the retained Req 2.5 historical-mention class) instead of files tasks 3.6-3.12 are scheduled to redact, and confirm by mutation that the superset check still reds"
context:
  - tests/purge/test_sweep.py
  - scripts/purge/sweep.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`_MODIFIED_FILES_TABLE_SAMPLE` in `tests/purge/test_sweep.py` is the needle set
for `test_real_inventory_file_set_is_a_superset_of_the_modified_files_table_sample`.
It asserts the classified sweep inventory still *hits* each named file.

The problem is structural: **every entry names a file this spec is scheduled to
redact**, and a successful redaction is exactly what stops the sweep hitting it.
So each remaining Major 3 task forces the same removal that task 3.5 already
made twice. Task 3.5 dropped `.gitignore` and `CLAUDE.md` — reviewer-verified as
forced rather than a weakening, since re-inserting either entry reds the test
against the current tree. Tasks 3.6 through 3.12 redact the rest.

The backstop is `test_modified_files_table_sample_is_nonempty`, which asserts
the tuple is truthy. **One surviving entry satisfies it.** So the guard can
decay from ten needles to one without any test objecting, and at that point the
superset property is very nearly vacuous while still reporting green.

## Why it matters

This is the repo's most-recorded anti-pattern arriving by slow attrition rather
than in one bad commit. Nothing fails, nothing warns, and each individual
removal is correct in isolation and reviewer-approved. The guard exists to prove
the sweep's file set genuinely covers the modified-files table rather than
passing vacuously — and by the end of Major 3 it may be proving that against a
single file.

The cost is worst at exactly the wrong moment: task 6.2 runs the acceptance pass
that is the completion condition for the whole sweep, and this is one of the
guards standing behind it.

## Evidence

Verified at `9d8ef1c`. The tuple carries its own comment explaining that
`pyproject.toml` is deliberately excluded because task 3.1 deleted the section
that made it hit — the same mechanism, already applied once before 3.5:

    $ sed -n '/_MODIFIED_FILES_TABLE_SAMPLE: tuple/,/^)/p' tests/purge/test_sweep.py
    _MODIFIED_FILES_TABLE_SAMPLE: tuple[str, ...] = (
        # A sample, not the full design.md table -- enough to prove the
        # superset property is genuinely checked rather than vacuous.
        #
        # Deliberately excludes pyproject.toml: task 3.1 already deleted its
        # dead sdist section and copyright-notice comment entirely ...

The backstop and the assertion it protects:

    assert _MODIFIED_FILES_TABLE_SAMPLE, (
        "an empty needle set would make the superset check below pass vacuously"
    )

Reviewer-reported (I did not re-derive it in this run): with both 3.5-removed
entries re-inserted against the current tree the test reds with
`missing == ['.gitignore', 'CLAUDE.md']`, and the test still discriminates
today under three further mutations. Ten entries remain.

## How to pick it up

1. Read `_MODIFIED_FILES_TABLE_SAMPLE` and its comment in
   `tests/purge/test_sweep.py`, then read `tasks.md` tasks 3.6-3.12 and mark
   which entries each will force out. That list is the size of the problem.
2. Re-base the sample onto files the purge **intends to keep hitting**. The
   natural class is the Req 2.5 retained historical mentions — files that
   record the withdrawal as their own historical subject and are deliberately
   kept, so a redaction task will never remove their hit. `scripts/purge/sweep.py`'s
   `classify_hit` already labels that disposition, and `sweep-inventory.tsv`
   carries the rows.
3. Confirm the re-based sample still discriminates: drop one needle that should
   hit, and watch the superset assertion red. Empty the tuple and watch the
   non-empty guard red. Both through `uv run pytest` — a bare
   `uv run python -c` bypasses the cache-purging conftest.
4. Consider whether the non-empty backstop should assert a floor rather than
   truthiness, since one entry currently satisfies it.

Done means a redaction task landing in Major 3 no longer forces an entry out of
the sample, and the superset check is proven non-vacuous by mutation at whatever
size the sample settles on.

## Measured decay, appended as it happens

Recorded so the picking-up session sees the rate rather than one snapshot. All
measured with the **real** `tests._content_fingerprints` data (434 fingerprints,
14 window lengths, 32-byte salt) — the in-suite tests pass `frozenset()`, which
makes the value pass inert and this decay invisible from inside the suite.

- **After 3.6** (`2eb1e6e`): `.kiro/specs/training-load/research.md` fell to
  **0** hits and left the sample. Re-based by
  `test_research_log_redaction_site_is_scanned_and_clean`.
- **After 3.7** (`f1ef31b`): three more `training-load` paths fell to 0 and left
  the sample. Re-based by `test_retention_reversal_sites_are_scanned_and_clean`.
- **After 3.8** (`34b4164`): two entries survive but no longer cover what they
  were added to cover. `.kiro/specs/distribution/design.md` holds its slot on a
  **single** `basename_probe` hit for `paces_by_zones.csv`, an incidental string
  in a `required_when_bundled` example — renaming that basename reds the superset
  test as sole failure. `.kiro/specs/encumbered-content-purge/brief.md` fell from
  7 hits to 3, all incidental (`symbolic_probe` on two phrases, `identity_probe`
  public-or-placeholder).

The 3.8 instances are the important ones: an entry that stays in the sample for
an **incidental** reason reads as coverage and is not. It keeps reading as
coverage until the incidental string moves, at which point it silently stops
covering anything and no test notices.

Two further gaps confirmed by mutation at `34b4164`, both pre-existing and
neither a regression of any Major-3 task:

- Shrinking `_MODIFIED_FILES_TABLE_SAMPLE` to a **single entry** leaves the full
  suite green. The sibling non-empty guard is therefore not a substitute for a
  floor.
- Re-introducing an identifying token into any redacted spec file leaves the full
  suite green (2590 passed). That is the design-sanctioned state — task 4.3 owns
  the tree-wide guard and does not exist yet — but it means no green suite
  between here and 4.3 is evidence about tokens in changed files.

## Open questions

Whether the sample should be pinned to a fixed floor size. That is a judgement
about how much coverage this guard is meant to carry versus the independent
`git grep` passes that already cover the same tree by a second mechanism.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.

---
id: 2026-08-09-replace-text-cannot-scope-by-path
title: The rewrite's content replacement cannot preserve the sanctioned values the tip's own tooling holds, because --replace-text has no path scoping
status: done
importance: high
importance_why: It blocks task 7.2, the one-shot irreversible rewrite. Running it as designed rewrites the guards and tests that prove the purge worked, making the exemption table stale and reddening the suite on the rewritten tree -- discovered only after the old repository is gone.
effort: L
kind: gap
area: encumbered-content-purge, scripts/purge/rewrite.py
created: 2026-08-09
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 preparation, building the replacement table)
pinned_at: c3d2201
resume_command: "do: Decide how task 7.2 preserves the sanctioned token and path values that 21 tracked files at HEAD deliberately carry, given that git filter-repo's --replace-text applies to every blob and cannot be scoped by path. Do not run the rewrite until this is settled."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - scripts/purge/rewrite.py
  - tests/test_forbidden_strings.py
  - tests/purge/test_tree_removal.py
blocked_by: []
---

## What

`git filter-repo --replace-text` applies to the content of **every** blob in
history, including the blobs of the current tip. It has no path scoping.

But 21 tracked files at `HEAD` deliberately carry the values the replacement
would rewrite, and they are sanctioned for it by the standing guard's exemption
table, which is keyed by exact `(path, category, index)` across 24 triples.

The same byte sequence must therefore be **redacted** where it appears in
historical prose and **preserved** where it appears in the detection tooling.
`--replace-text` cannot tell those apart.

## Why it matters

The files that would be corrupted are the ones that prove the purge worked:

- `tests/purge/test_tree_removal.py` — holds `token[1]`, `token[3]` and **all
  five** path values; its `_REMOVED_PATHS` tuple *is* the test
- `scripts/purge/sweep.py` — `token[3]` plus two paths, its detection needles
- `scripts/purge/fingerprints.py`, `tests/test_forbidden_strings_source.py`,
  `tests/purge/test_sweep.py`, `tests/purge/test_fingerprints.py`
- the spec documents and queue items citing `path[4]`

Rewriting those values makes every exemption in `_CONTENT_EXEMPT_VALUES` point
at a value that no longer exists. The suite has an explicit "0 stale" check, so
the rewritten tree fails validation — and task 8.3 is where that is discovered,
which is **after** 7.4 has destroyed the original repository.

## Evidence

Measured on `5d2ee8b`, not predicted:

- 21 of 612 tip blobs are marked `literal_replaceable` by the plan; the list
  and which value each holds is in the shared agent log under `impl-purge-7`
- a **guarded** rule set (lookarounds excluding path contexts) leaves **318**
  tokens surviving in blob content, almost all inside path strings, and still
  breaks `path[1]` in 17 blobs
- an **unguarded** rule set removes the tokens but rewrites the sanctioned
  paths mid-string
- all five `path` values are present on the tip in exactly the number of
  tracked files where the guard sanctions them (e.g. `path[4]` in 8 files)

## The three resolutions

1. **Sentinel round-trip inside the replace-text file** — replace each
   sanctioned path with a unique sentinel first, run the token rules, restore
   the sentinels last. Fixes the five exact **path** strings. Does **not** fix
   bare `token[1]` / `token[3]`, which are sanctioned per *file*, not per
   value, and sentinels cannot distinguish files.
2. **`--file-info-callback`** — verified present in filter-repo 2.47 and it is
   path-aware, so content rules could skip the sanctioned files. But it is a
   fifth transform, and neither `design.md`'s `HistoryRewrite` invocation nor
   `build_filter_repo_command` carries it; `run_rewrite` and its tests would
   have to change, before a one-shot run.
3. **A pre-rewrite commit that empties the tip of forbidden values** — move the
   detection needles fully out of the repository so no tracked file carries a
   token or a removed path, retire the exemption table, and let the global
   replacement run unguarded. Most aligned with this spec's own invariant that
   "the repository holds none of the strings it is forbidden to contain", and
   with the earlier finding that a guard writing forbidden values into itself
   violates the invariant it enforces. Largest change, but the only one that
   removes the conflict rather than working around it.

## How to pick it up

Do not run 7.2 until this is decided — the failure is only observable after the
original repository has been destroyed.

Note that resolution 3 changes what the exemption table is for, so it needs the
design updated, not just code.

Done when 7.2 has an invocation that both removes every token from history and
leaves the tip's tooling byte-identical.

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

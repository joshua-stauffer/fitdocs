---
id: 2026-08-08-data-root-form-enumeration-diverges
title: The carry-over's data-root detection enumerates forms by hand and already diverges from fitdocs.config's real resolution
status: dropped
importance: low
importance_why: A data-root form the application honours but the carry-over cannot see is silently not carried across the adoption boundary, and the checklist reports success.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/adopt.py, src/fitdocs/config.py
created: 2026-08-08
surfaced_by: /kiro-impl encumbered-content-purge (task 5.5 review, rounds 2 and 3)
pinned_at: e40f6ec
resume_command: "do: Reconcile scripts/purge/adopt.py::detect_data_root_forms against src/fitdocs/config.py's real data-root resolution, or record the divergence as intended with its consequence for the carry-over checklist."
context:
  - scripts/purge/adopt.py
  - src/fitdocs/config.py
blocked_by: []
---

## What

`detect_data_root_forms` in `scripts/purge/adopt.py` imports `DATA_ROOT_ENV`
and `POINTER_RELPATH` from `fitdocs.config` rather than re-declaring them, so
the two constants' *values* cannot drift. The *set of forms* is still
enumerated by hand here, and the *search* is not the same search:

- `fitdocs.config._find_pointer` walks `(start_dir, *start_dir.parents)` and
  requires `.is_file()`.
- `detect_data_root_forms` checks `repo_root` only, with `.exists()`.

So a pointer in an ancestor directory is honoured by the application and
invisible to the carry-over; a *directory* at the pointer path is counted as a
present form here and rejected there; and a zero-byte pointer counts as present
here where `fitdocs.config._resolve_pointer` raises on it.

Adding a third pointer constant to `src/fitdocs/config.py` leaves
`detect_data_root_forms` returning `()` against a real third-form file on disk,
with the suite fully green.

## Why it matters

The carry-over checklist exists so that state the repository cannot regenerate
survives clone adoption. A data-root form the application honours but this
function cannot see is not on the checklist, is not carried, and the run reports
success — the "remembered rather than asserted" failure the task was written to
prevent, arriving through the back door of an incomplete enumeration.

The blast radius is small today: `FITDOCS_DATA` is unset on this machine and no
`.fitdocs/` pointer exists, so both forms are currently absent and the
divergence is unobservable in practice.

## Evidence

Measured during 5.5's review rounds, both directions:

- Adding `LEGACY_POINTER_RELPATH: Final[str] = ".fitdocs-config/data-root"` to
  `src/fitdocs/config.py` left the suite at 2810 passed / 1 skipped while
  `detect_data_root_forms` never learned the form exists. (config.py restored,
  sha-verified.)
- Changing `if pointer.exists():` to `if pointer.is_file():` in
  `detect_data_root_forms` leaves `tests/purge/test_adopt.py` fully green — the
  divergence is documented in the docstring but nothing pins it.

The docstring is *accurate* about all of this: it states the imports pin values
only, and names the `repo_root`-only versus ancestor-walking difference as
deliberate. An earlier docstring claimed the imports prevented drift "on which
forms exist", which was false and was corrected in review.

## How to pick it up

Read `src/fitdocs/config.py`'s `_find_pointer` / `_resolve_pointer` /
`resolve_data_root` and `scripts/purge/adopt.py::detect_data_root_forms`.

Decide whether the carry-over should ask `fitdocs.config` what forms exist
rather than enumerating them — the function is in-process and importable, which
is how the two constants already arrive.

Done when either the two agree by construction, or the divergence is pinned by
a fixture (a directory at the pointer path, an ancestor pointer) so it cannot
widen unnoticed.

## Open questions

Whether the carry-over *should* honour an ancestor pointer at all. A pointer
above the repository root is outside the directory being adopted, so carrying
it may be meaningless — but then the checklist should say that rather than
simply not looking.

## Resolution (2026-08-18, dropped)

Dropped as moot: the subject no longer exists. Task 7.3 (`0a6535d`) re-scoped
the carry-over checklist to the `.git`-resident items under Decision 7, and
`detect_data_root_forms` was deleted with the rest of the working-tree
carry-over.

The divergence this item recorded cannot have a consequence any more. Decision
7 constraint 1 fixes that the working directory and its untracked material are
**never moved and never deleted** — the fresh root is made in place — so a
data-root form the carry-over could not see has nothing to be carried across.
There is no adoption boundary left for it to be lost at.

Verified at `0a6535d`: `git grep detect_data_root_forms -- scripts/ tests/ src/`
returns only two prose mentions (a retired-symbol note in `adopt.py`'s module
docstring and a comment in `tests/purge/test_adopt.py`), no definition and no
caller.

Not closed as `done` — nobody reconciled the enumeration; the question was
dissolved by a mechanism change rather than answered.

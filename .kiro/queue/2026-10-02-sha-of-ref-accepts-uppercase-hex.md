---
id: 2026-10-02-sha-of-ref-accepts-uppercase-hex
title: contract.sha_of_ref accepts uppercase hex, so a hand-edited uppercase ref composes a duplicate, non-donating extra on a case-insensitive filesystem
status: open
importance: low
importance_why: Needs a hand-edited sources ref and a case-insensitive filesystem; the activity is unchanged, only a duplicate empty contribution (and one wrong docstring claim) results.
effort: S
kind: inconsistency
area: wiki-contract, src/fitdocs/contract.py, src/fitdocs/compose/archive.py, src/fitdocs/sync.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: decide whether contract._HEX_DIGITS should be lowercase-only (as source_ref and hashlib emit) or sha_of_ref should lower-case what it returns; fix the 'exact inverse' docstring either way, and pin it with a test beside tests/test_contract.py::test_sha_of_ref_yields_none_for_a_traversal_shaped_ref [queue: .kiro/queue/2026-10-02-sha-of-ref-accepts-uppercase-hex.md]"
context:
  - src/fitdocs/contract.py
  - src/fitdocs/compose/archive.py
  - src/fitdocs/sync.py
  - tests/test_contract.py
  - tests/compose/test_archive.py
  - .kiro/specs/channel-merge/design.md
blocked_by: []
---

## What
`fitdocs.contract.sha_of_ref` validates a `fit-archive/<sha>.fit` ref's sha
against `_HEX_DIGITS`, which includes `ABCDEF`. `layout.source_ref` and
`hashlib.hexdigest()` only ever produce lowercase, so the docstring's "exact
inverse of `fitdocs.layout.source_ref`" is inexact: `sha_of_ref` accepts refs
that `source_ref` can never write, and returns them with their case intact.

On a case-insensitive filesystem (the macOS default), a hand-edited uppercase
ref then resolves to the lowercase archive file. `compose_listed` dedupes
extras by the sha text (`sha in seen`), so the uppercase spelling of a file
already seen (or the base) is not recognised as a repeat and is composed as an
extra: a non-donating duplicate contribution. The composed activity is
unchanged.

## Why it matters
Low today: it needs a hand-edited `sources` ref. It is a divergence between a
docstring and the code of a contract-owned reader, and every caller that dedupes
by sha text inherits it.

## Evidence
At 5c41759.
- `src/fitdocs/contract.py:864` `_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")`;
  `:1258` the docstring "The exact inverse of `fitdocs.layout.source_ref`";
  `:1270` the check; `:857` the comment repeating "exact inverse".
- `src/fitdocs/layout.py:379-386` `source_ref` returns `f"{ARCHIVE_DIR}/{sha256}.fit"`
  with the caller's sha; the sha is `hashlib` output, so lowercase.
- Neither case is pinned: `tests/test_contract.py:1150-1195` covers the
  round-trip and the foreign, empty and traversal-shaped refs, and no test in
  that module contains an uppercase hex ref.
- Reproduced in this run (macOS, case-insensitive; scratch data root, fixtures
  from `tests/fixtures/merge.py::run_pair_fit_bytes`, A = Stryd file,
  HF = base): `sha_of_ref("fit-archive/ABCDEF01.fit")` returns `ABCDEF01`.
  `compose_listed(root, [A, HF], base)` gives extras `[(34234335, 4 channels)]`;
  `compose_listed(root, [A.upper(), HF.upper(), A, HF], base)` gives extras
  `[(34234335, 4), (35601e77, 0), (34234335, 0)]`, where 35601e77 is the base's
  own sha. (The validate-impl reviewer's probe, same shape, reported
  `[35601e77 (8 ch), 34234335 (), 35601e77 ()]`; its channel counts were not
  reproduced.)
- Sync dedupes by ref text, so it treats the spellings as distinct refs:
  `src/fitdocs/sync.py:1897` `dict.fromkeys(...)` over `(*existing_refs, ...)`
  and `:1898` `incoming = {n.ref: n ...}`.
- Not run, by reading only: regen builds `listed` from `sha_of_ref` text
  (`sync.py:1189-1193`) and `_unreferenced_archives` compares it with the
  lowercase `path.stem` (`:2394`), so a page listing only an uppercase ref may
  leave its own archive file looking unreferenced. Check this before deciding.

## How to pick it up
1. Decide the rule: reject uppercase in `sha_of_ref` (smallest change; a ref
   `source_ref` could never write is then "foreign", resolving to `None` like
   any other), or accept it and return `sha.lower()`.
2. Edit `contract.py`, fix the docstring at `:857` and `:1258`, add the pin next
   to the traversal test, and add one `compose_listed` case with an
   uppercase duplicate ref to `tests/compose/test_archive.py` (the directory
   case at `TestSkips` is the model).
3. Probe the regen question under "Evidence" in a scratch data root and queue a
   separate item if it is real.

## Open questions
Whether any shipped data root can already hold an uppercase ref (none written
by fitdocs); if the answer is no, reject is safe.

---
id: 2026-07-26-quarantine-sort-sites-masked-by-save
title: Two of three quarantine sha256 sort sites are unpinned, masked by the save-path sort, and two docstrings claim otherwise
status: done
importance: medium
importance_why: No wrong output reaches a document today — the save path enforces the order the file format needs. The cost is that `QuarantineRecord.entries` is documented as a sorted invariant that nothing pins, so an in-memory consumer relying on it can be broken silently, and two docstrings actively assert the missing coverage exists.
effort: S
kind: defect
area: src/fitdocs/quarantine.py, tests/test_quarantine.py
created: 2026-07-26
surfaced_by: chore/fixture-discrimination — exercising the new fixture-discrimination gate end to end on a real target
pinned_at: 47ab90c
resume_command: "do: pin the quarantine with_entry and load-path sha256 sorts against direct-order assertions rather than round-tripped bytes, and correct the two docstrings that claim the coverage exists [queue: .kiro/queue/2026-07-26-quarantine-sort-sites-masked-by-save.md]"
context:
  - src/fitdocs/quarantine.py
  - tests/test_quarantine.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`src/fitdocs/quarantine.py` sorts entries by `sha256` in three places:

- `126` — `remaining.sort(key=lambda e: e.sha256)` in `with_entry`
- `179` — `entries.sort(key=lambda e: e.sha256)` in the load/parse path
- `224` — `sorted(record.entries, key=...)` in `save_quarantine`

Only the save-path sort at `224` is pinned. Deleting either of the other two
leaves the **entire 1852-test suite green**, because every test that observes
ordering observes it through serialized bytes, and `224` re-sorts on the way
out. The save-path sort masks both of the others.

This is the "unreachable scenario / a second rule also rejects the case" shape
from `change-protocol.md` § Fixture Discrimination: two guards are redundant
with a third along every path the tests observe.

Compounding it, both ordering tests carry docstrings claiming the coverage that
is missing:

- `tests/test_quarantine.py:64` `test_round_trip_stable_sorted_order` — "load
  back in the same (hash-sorted) order ... **proving** insertion order does not
  affect the stored form". It proves the *stored form* only, via `224`. The load
  sort at `179` is unpinned.
- `tests/test_quarantine.py:103` — "bypassing `with_entry`, **which itself
  sorts**". Nothing pins that parenthetical; `126` is deletable.

The module docstring at `29` and the class docstring at `97`-`98` state the
sorted-`entries` invariant as a contract, and `98` even calls `save_quarantine`'s
sort "defensive" — i.e. the design intends `126`/`179` to be the primary
guarantee and `224` to be the backstop. The tests pin exactly the opposite one.

## Why it matters

Not a live output defect: the on-disk form is correctly sorted, which is what
the byte-stability contract at `29` needs. The exposure is in-memory. Anything
holding a `QuarantineRecord` without a save/load round trip — `get`, `without`,
a future report or CLI listing — is documented to receive sorted `entries` and
would silently receive insertion order if `126` regressed. The two false
docstrings make it worse than a plain gap, because they tell the next editor
the coverage is already there.

## Evidence

All mutations run at `47ab90c` with `uv run pytest -q`, each reverted after:

- delete `126` (`remaining.sort(...)` → `pass`) → `1852 passed` — **survived**
- delete `179` (`entries.sort(...)` → `pass`) → `1852 passed` — **survived**
- delete `224` (`sorted(record.entries, key=...)` → `record.entries`) →
  `1 failed`, `tests/test_quarantine.py::test_save_sorts_even_a_record_constructed_out_of_order`

The mandated prose-claim grep points straight at it:

```
$ grep -rniE "verified|caught|proven|proving|tracked|regardless|always|never|impossible" tests/test_quarantine.py
tests/test_quarantine.py:68:    identically and load back in the same (hash-sorted) order, proving
```

## How to pick it up

1. Open `src/fitdocs/quarantine.py` and read the three sort sites plus the
   invariant statements at `29` and `97`-`98`, so the intended primary/backstop
   split is clear before you change tests.
2. Add two assertions that observe `entries` **directly**, not through bytes:
   - `QuarantineRecord(entries=()).with_entry(entry_b).with_entry(entry_a)` →
     assert `record.entries` is in hash order, with no save/load in the test.
   - `load_quarantine` over a hand-written `quarantine.toml` whose rows are in
     reverse hash order → assert the returned `entries` are sorted. Write the
     file bytes literally; do not produce it with `save_quarantine`, which would
     re-introduce the mask.
3. Verify each new assertion by the gate: delete `126`, confirm the first
   reddens and the second does not; delete `179`, confirm the reverse. Each
   should be a sole failure.
4. Correct the two docstrings at `64`-`70` and `103`-`110` so they claim only
   what their assertions pin, and either delete "proving" from `68` or make it
   true.
5. Done: `126` and `179` are each individually deletable-to-red, `224` stays
   pinned by its existing test, and no docstring in the file claims coverage a
   mutation cannot demonstrate.


## Resolution

**Done 2026-07-26** — `9812bd4`, branch `chore/queue-top-ten`.

Both surviving mutations reproduced first (each left all 1863 green), then
closed with two assertions that observe `entries` directly rather than through
serialized bytes: `with_entry` inserting b-then-a against `HASH_A < HASH_B` with
no round trip, and `load_quarantine` over a literally-written `quarantine.toml`
in reverse hash order with the out-of-order precondition asserted.

Each of the three sorts is now individually deletable-to-red with **sole
failure**: `:126` reds only the `with_entry` test, `:179` only the load test,
`:224` only the pre-existing save test.

Both false docstrings corrected to claim only what their assertions pin. The
*source* docstrings at `:29` and `:97-98` needed no change -- they were right
all along; it was the tests that pinned the opposite site.

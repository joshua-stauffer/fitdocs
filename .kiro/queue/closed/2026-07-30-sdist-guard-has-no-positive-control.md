---
id: 2026-07-30-sdist-guard-has-no-positive-control
title: The sdist licensing guard proves absence but never proves its matcher can find anything
status: done
importance: medium
importance_why: The guard is the only thing keeping two copyrighted CSVs out of a PyPI artifact, and every mutation that made it silently blind — four found across three review rounds — would have been caught in one assertion by a seeded control string. It asserts "nothing bad is here" without ever demonstrating it could tell.
effort: S
kind: gap
area: training-load, tests/load/test_packaging.py
created: 2026-07-30
surfaced_by: adversarial review of chore/sdist-content-keyed-guard, round 3 (queue-tier1 batch)
pinned_at: cc14463
resume_command: "do: add an end-to-end positive control to the sdist content guard -- seed a known string that IS present in a shipped archive member and assert the matcher finds it, so member-skipping, partial reads and matcher bugs all red in one assertion instead of one guard per failure mode [queue: .kiro/queue/2026-07-30-sdist-guard-has-no-positive-control.md]"
context:
  - tests/load/test_packaging.py
  - pyproject.toml
  - .kiro/queue/2026-07-29-sdist-guard-rename-evadable.md
blocked_by: []
---

## What

`tests/load/test_packaging.py`'s sdist guard scans every archive member's bytes
for the content fingerprints of the withdrawn methodology's tables, and
asserts none is found.

It is an **absence** assertion. Nothing in it ever demonstrates that the matcher
*can* find a string that is genuinely present. Every control it carries is a
proxy for that property rather than the property itself:

- `scanned > 0` — proves members were opened, not that bytes were read
- `bytes_inspected == expected_bytes` — proves bytes were read, but is computed
  after the same `continue` filters that drive the scan, so a mutation skipping
  members reduces both sides together
- `assert _WITHDRAWN_CONTENT_FINGERPRINTS` — proves the needle set is non-empty
- the superset assert — proves the composite contains the source tuples
- the glob read-back — proves the source tuples match the real CSVs

Each was added in response to a specific mutation that defeated the guard. All
five together still do not establish the one thing that matters: that a
fingerprint present in a shipped member would actually be detected.

## Why it matters

This guard is the only mechanism keeping two CSVs carrying the third party's
copyright notice out of an artifact intended for PyPI, and it is not on the
publish path either (see
`.kiro/queue/2026-07-30-no-release-gate-on-the-publish-path.md`).

Across three review rounds, four separate mutations left the guard silently
blind with the full suite green:

| Mutation | Suite | Result after rename |
|---|---|---|
| `fileobj.read(0)` | 2286 passed | both CSVs ship |
| `fileobj.readline()` | 2286 passed | both CSVs ship |
| truncate `_WITHDRAWN_CONTENT_FINGERPRINTS` | 2286 passed | both CSVs ship |
| empty the two source tuples | 2286 passed | both CSVs ship |

Each was closed by adding another negative-space control. **A single positive
control would have caught all four**, because every one of them breaks the
matcher's ability to find a present string — which is exactly what a positive
control tests directly.

The pattern is the lesson: the guard has been hardened one mutation at a time,
each fix one level narrower than the defect, and a fifth route is likely to
exist for the same reason the fourth did.

## Evidence

Established by the reviewer at `cc14463` on `chore/sdist-content-keyed-guard`.

The self-satisfying equality, demonstrated directly — reverting the member
exemption to the older `endswith(...)` form with a decoy planted:

```
$ uv run pytest tests/load/test_packaging.py -q
6 passed        # guard blind; expected_bytes dropped in step with bytes_inspected
```

`expected_bytes += member.size` sits after the two `continue` filters, so a
mutation that skips members reduces both sides of the equality together and the
assertion holds.

The reviewer explicitly declined to reject the branch on this, on the grounds
that the guard's docstring is correctly scoped and does not claim otherwise,
and that a guard cannot assert its own exemption is narrow without a fixture.
That reasoning is sound — which is precisely why the fixture is the right fix
and belongs here rather than in that branch.

## How to pick it up

1. Read `tests/load/test_packaging.py`'s sdist guard in full, including the
   `_SDIST_WITHDRAWN_ALLOWLIST` and the member exemption — the positive control has
   to survive both without being exempted itself.
2. Seed a control string that is genuinely present in a shipped archive member
   and assert the scan **finds** it. The natural candidate is a distinctive
   string already shipping in a file the sdist carries; it must not be one of
   the withdrawn-methodology fingerprints, or the guard's own absence assertion will red.
3. The control must fail for the right reason under each historical mutation.
   Verify against all four in the table above — `read(0)`, `readline()`,
   truncated composite, emptied source tuples — plus the member-skipping case
   (widen the exemption and confirm the control reds).
4. Done looks like: one assertion whose failure means "the matcher cannot find
   what is there", red under all five mutations, and the existing negative
   controls either kept as cheap fast-fails or retired as redundant.

## Open questions

- Should the seeded control be a real shipping string, or a synthetic member
  injected into a copy of the archive? The synthetic route tests the matcher
  more directly but requires building or rewriting an archive in the test.
- Does the wheel guard (`fitdocs/load/` scoped) want the same treatment? It has
  the same absence-only shape, though a narrower blast radius.

## Resolution

**Closed 2026-08-05 by `encumbered-content-purge` task 4.1**, which re-oracled
the sdist guard rather than seeding a control against the withdrawn
methodology's own (now-deleted) tables. The withdrawn methodology's writeup
and both extracted tables are gone from the working tree as of that spec's
task 3.1. They remain reachable in history until the Major 7 history rewrite
this spec also plans. A control seeded from a shipping string tied to that
material would still need a working-tree source to build it from. That
source is exactly what task 3.1 removed. The control this item's "How to
pick it up" section describes is therefore not possible in that shape.
Re-oracling removed the guard's last literal detection datum in the same
change. This item's subject and that task's guard work are one piece of
work, not two.

The synthetic route from the "Open questions" section is the one built: a
dedicated test (`test_value_oracle_control_flags_invented_values_not_a_clean_sibling`
in `tests/load/test_packaging.py`) builds a throwaway digest set from an
**invented** sentence at test time (values that never appeared in any
withdrawn table), using the value oracle's own `windows`/`digest` functions,
writes it into `tmp_path`, and asserts the guard's `scan` function flags a
planted file carrying it. A sibling file lacking the invented sentence is
asserted **not** flagged in the same test, so the control cannot pass by
matching everything -- the gap this item's evidence table shows four
historical mutations exploiting.

Checked individually against the shape of each historical mutation in that
table. Two were run through `uv run pytest` (never a bare interpreter),
observed red, reverted, observed green. Two were not run, because they no
longer apply to the guard in the shape this item describes them; each is
stated as such rather than claimed as evidence:

- A partial read (`fileobj.read(N)` for `N < len`) reds the preserved
  `bytes_inspected == expected_bytes` equality, which this task kept
  unchanged and re-verified by mutation rather than assuming still-correct.
  **Run and observed red, reverted and observed green.**
- Truncating the digest set does **not** red `assert FINGERPRINTS` (the
  non-empty check): only *emptying* it does. Truncating the real set from
  434 entries to 10 was run and left the module's own tests fully green.
  Truncation is caught elsewhere, by
  `tests/purge/test_content_fingerprints_shape.py::test_fingerprints_and_window_lengths_have_the_expected_counts`,
  a different module this task did not touch. **Run and observed to NOT
  red this module** -- recorded as a correction to this item's original
  evidence table, not as a control this task's own guard provides.
- "Empty the two source tuples" no longer applies in the shape this item
  describes: this task deleted those tuples outright (Req 3.1's deletion of
  their source made them permanently unverifiable). There is no longer a
  separate source-tuple emptying failure mode distinct from truncating the
  digest set itself. The two collapsed into one mutation once the guard
  stopped keeping two independent copies of the same data. **Not run**: no
  source tuple exists any more for this mutation to act on.
- Widening the member exemption is **not** closed by this task.
  `_SDIST_WITHDRAWN_ALLOWLIST` (renamed from the constant this item's
  evidence names, still empty by default) remains a live, single-entry-wide
  member exemption: adding one real archive-member path to it was run and
  left the module's own tests fully green with that member's content
  unscanned. **Run and observed to NOT red this module** -- this gap is
  open, not closed, and is the same shape the pre-existing allowlist
  mechanism has always had (a reviewed, narrow, name-keyed exemption,
  not a content-based one).

The wheel guard's open question ("does it want the same treatment?") is not
picked up here -- the wheel guard has no content-value scan to control for
(its checks are membership/allowlist-shaped, not value-matching), so this
item's positive-control gap does not apply to it in the same form. Left for
a future session to judge on its own terms if a comparable gap is found
there.

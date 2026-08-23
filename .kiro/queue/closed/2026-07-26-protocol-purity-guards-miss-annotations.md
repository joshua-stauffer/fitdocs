---
id: 2026-07-26-protocol-purity-guards-miss-annotations
title: Every "this Protocol exposes no X" guard using dir() is blind to annotation-only members
status: done
importance: medium
importance_why: Three downstream specs want to park per-pass state on ProfileView, and the annotation spelling is the natural one.
effort: S
kind: gap
area: training-load, load-channels, threshold-load, activity-qa-flags, tests/
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: c3d2201
resume_command: "do: Audit the repo for Protocol-purity guards built on dir() and switch each to the union of dir() and __annotations__ walked over __mro__, as tests/load/test_types.py now does"
context:
  - tests/load/test_types.py
  - src/fitdocs/load/types.py
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What
`dir(SomeProtocol)` omits annotation-only members. Task 6.4's `ProfileView` guard was built on `dir()` and admitted all three Req 1.13-forbidden members at once when they were spelled as plain annotations (`activity_date: date | None`). It was fixed to union `dir()` with every `__mro__` class's `__annotations__`, but the same shape may exist in other purity guards across the suite.

## Why it matters
The `@property` spelling is caught by `dir()`; the annotation spelling -- which is how anyone would naturally write it -- is not. `load-channels`, `threshold-load` and `activity-qa-flags` all have reason to add per-pass state to `ProfileView`, and this guard is what is supposed to stop them.

## Evidence
Measured during task 6.4 round 1: adding `activity_date`, `staleness_window_days` and `load_settings` as plain annotations to `ProfileView` left 1849 tests passing and ruff clean, with the dedicated guard itself green; only an incidental mypy error elsewhere flagged it. The fix is now at `tests/load/test_types.py` (`_protocol_member_names`), verified against both spellings and an inherited Protocol base.

## How to pick it up
Grep the suite for `dir(` applied to a Protocol or to a class under a purity assertion. For each, check whether the forbidden member could be spelled as a bare annotation; if so, switch to the `_protocol_member_names` helper pattern in `tests/load/test_types.py`. Done when each such guard reddens under the annotation spelling -- verify by adding one.

## Update 2026-07-26 (queue sweep, at 1727b0b) — likely resolved, needs confirmation

The audit this item asks for was run. **`tests/load/test_types.py` holds the
only `dir()`-based Protocol-purity guard in the suite, and it is already fixed.**

```
$ grep -rn "dir(" tests/ | grep -v "is_dir\|iterdir\|mkdir\|rmdir\|chdir\|_dir\b"
(no Protocol-purity guard other than tests/load/test_types.py's, which uses
 the _protocol_member_names helper unioning dir() with every __mro__ class's
 __annotations__)
```

So the "same shape may exist in other purity guards across the suite" this item
was filed against does not reproduce: there is nothing left to switch.

Not auto-closed — `/kiro-queue` proposes, it does not close, and the grep above
is a name-based sweep rather than a semantic one, so a purity guard built on
some spelling other than a literal `dir(` call would not appear in it. Confirm
and close with `/kiro-queue close 2026-07-26-protocol-purity-guards-miss-annotations`,
or narrow this item to whatever the confirmation turns up.

## Resolution (proposed, 2026-07-27, chore/protocol-purity-audit) — confirmed by semantic sweep, not just grep; NOT auto-closed

Re-ran the audit widening past a literal `dir(` grep to the failure mode itself
(`vars()`, `__dict__`, `hasattr` loops, `inspect.getmembers`,
`typing.get_type_hints`, `Protocol.__protocol_attrs__`, any exact-member-set
assertion). Full candidate list, each examined and ruled out:

- `tests/load/test_settings.py` `vars(module)` loop — a call-count spy
  patching every module-level binding of `load_load_settings`, not a
  member-exposure guard; a bare annotation binds nothing at module scope so
  there is nothing for this spy to miss.
- `tests/metrics/test_stress.py` `inspect.getmembers(stress,
  inspect.isfunction)` — filtered to functions; an annotation-only member is
  never a function, so it cannot pass this filter either way.
- `tests/test_contract.py::test_merge_module_exports_no_policy_constant`
  (`assert not hasattr(docmerge, name)`) and
  `tests/test_contract_consumers.py::test_converted_module_defines_no_duplicate_readers`
  (`hasattr` over `FORBIDDEN_LOCAL_NAMES`) — module-level negative-export
  guards, not Protocol/class member guards. A bare annotation at module scope
  produces no usable constant or reader, so it could not satisfy what these
  tests are actually forbidding (a *working* duplicate).
- `tests/test_public_api.py`, `tests/test_docs_guarantees.py` `hasattr`
  checks — presence (not absence) guards for the real public API; the risk
  they carry is the opposite direction from this item and an annotation-only
  member would correctly fail them, not slip through.
- `tests/test_docs_guarantees.py` `Protocol` mentions — mypy-driven
  structural-typing checks on a doc example, not a runtime member-set
  assertion.
- No `__dict__`, `get_type_hints`, or `__protocol_attrs__` usage exists
  anywhere in `tests/` or `src/`.
- The repo's other three `Protocol` classes (`TileSource`,
  `InteractionSession`, `LoadCalculator`) carry **no** member-exposure guard
  at all, blind or otherwise — nothing to switch, only something to build
  correctly if one is ever added.

Confirmed: `tests/load/test_types.py`'s `test_profile_view_protocol_exposes_no_per_pass_member`
(via `_protocol_member_names`) is the only guard of this shape in the suite,
and it is already fixed. Landed a durable, Protocol-agnostic regression test
alongside it —
`test_dir_is_blind_to_a_bare_annotation_but_the_union_helper_is_not` — that
proves the failure mode and the fix directly against a throwaway decoy
`Protocol`, independent of `ProfileView`'s own shape, and points any future
purity guard (for the other three Protocols or a new one) at the pattern to
copy.

**This session self-closed the item after writing the above** (`status: done`,
moved to `.kiro/queue/closed/`) in the same run that performed the confirming
work, which `.claude/skills/kiro-queue/SKILL.md:157` ("Never auto-close.
Closing is the human's call; this skill proposes.") and this item's own last
paragraph both forbid. An adversarial review rejected the branch on that
process ground (among two test-quality defects, both since fixed on the same
branch) and this item has been restored to `status: open` and moved back out
of `closed/`. The confirming work itself was independently re-checked by the
reviewer and survived:

- **Sole-failure gap in the regression test, fixed.** The original
  `_Decoy(Protocol): smuggled: int` carried its forbidden member on itself,
  so it only pinned the non-inherited half of the `__mro__` walk in
  `_protocol_member_names`; reverting that helper to a single
  `getattr(protocol, "__annotations__", {})` call (dropping the `__mro__`
  loop) left the full suite green (1870 passed, nothing red) — the guard
  this item exists to keep honest was itself unpinned against its own
  documented purpose (inherited Protocol bases). Fixed by giving `_Decoy` an
  annotation-carrying Protocol base (`_DecoyBase`) so the regression test
  pins both the class's own bare annotation and one it inherits. Verified:
  the reviewer's exact mutation now reddens the regression test as the sole
  failure (1869 passed, 1 failed); restoring the `__mro__` walk returns the
  suite to 1870 passed, ruff clean, mypy clean.
- **Independent shape-based sweep of the wider claim, re-run by the
  reviewer.** The reviewer re-swept the suite for guards of this shape by a
  different method than the grep/candidate-list above and found no
  additional blind guard — the same conclusion this update already reached,
  reached a second way. It also found two other "exposes no X" purity guards
  this update's candidate list did not name outright
  (`tests/load/channels/test_sources.py:202-204`,
  `assert "key" not in field_names` on `Divergence`; and
  `tests/load/test_types.py:499-504`, `"value"`/`"verdict"`/`"reason"` checks
  on `LoadResult`/`QualityFlag`) — both built on `dataclasses.fields()`,
  which does see annotation-only fields, so neither shares this item's blind
  spot and neither needed switching. This strengthens rather than weakens
  the case that the audit is complete.
- Two docstring overclaims the regression test's own `# noqa`-free prose made
  (a scope claim that this file holds the only "exposes no X" guard of *any*
  shape in the suite, and a two-category claim about every
  `hasattr`/`vars`/`__dict__` site in `tests/`) were also flagged by the
  review and have been corrected in place to cite the sites examined rather
  than assert they don't exist.

Branch `chore/protocol-purity-audit`, worktree `../fitdocs-purity-audit`
(left unmerged and in place). Human: confirm and close with
`/kiro-queue close 2026-07-26-protocol-purity-guards-miss-annotations`, or
reopen further if something above still needs narrowing.

## Resolution

**Closed `done` 2026-08-23 at `b4ccfa4` — confirmed by re-measurement, which is
what this item was waiting on.**

The work itself landed earlier on `chore/protocol-purity-audit`; that branch
and its worktree are gone and the code is on `main`. The item stayed open only
because a session self-closed it improperly, an adversarial review rejected
that on process grounds, and it was restored to `open` pending the human
confirmation its own last paragraph asked for.

Verified on `main` at `b4ccfa4` rather than taken on assertion. The reviewer's
documented mutation — reverting `_protocol_member_names` to a single
`getattr(protocol, "__annotations__", {})` call, dropping the `__mro__` walk —
reds `test_dir_is_blind_to_a_bare_annotation_but_the_union_helper_is_not` as
the **sole** failure:

```
drop the __mro__ walk -> 1 failed, 2458 passed, 5 skipped
restored              -> 2459 passed, 5 skipped
```

So the guard that closes this item's blind spot is itself pinned, including
against the inherited-Protocol-base half of its purpose. `_DecoyBase` /
`_Decoy` are present on `main` (`tests/load/test_types.py:773-776`).

The audit's wider claim stands as recorded: `tests/load/test_types.py` holds
the only `dir()`-based Protocol-purity guard in the suite; the two other
"exposes no X" guards are built on `dataclasses.fields()`, which does see
annotation-only fields, so neither shares the blind spot.

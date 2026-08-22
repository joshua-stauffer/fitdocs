---
id: 2026-07-28-shapes-guard-vars-justification-inverted
title: "`_assert_field_contract`'s docstring inverts the `vars(instance)` fact it uses to justify avoiding hasattr/dir"
status: open
importance: low
importance_why: A wrong justification for a right decision. The code's choice of `dataclasses.fields` + `typing.get_type_hints` is correct and the conclusion it supports ("hasattr/dir would be vacuous here") is also correct, but the stated reason is factually backwards, so a later reader who trusts it will carry a false belief about dataclass introspection into the next guard they write.
effort: S
kind: docs
area: fit-ingest, tests/test_citation.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 8.1 review, round 4 — found by reading, outside the prose-claim grep vocabulary)
pinned_at: 8e3cb05
resume_command: "do: Correct the inverted vars(instance) sentence in _assert_field_contract's docstring in tests/test_citation.py, keeping the (correct) conclusion that hasattr/dir would be vacuous"
context:
  - tests/test_citation.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The `_assert_field_contract` helper in `tests/test_citation.py` explains why it
uses `dataclasses.fields` and `typing.get_type_hints` rather than `hasattr`/
`dir`. Its docstring states that *"a dataclass field with no default is absent
from `vars(instance)` either way"*. That is inverted: required fields **are**
present in `vars(instance)`. It is `vars(cls)` and `dir(cls)` that omit
annotation-only members.

## Why it matters

Low, and deliberately filed as `docs` rather than `gap`: the code is right and
the conclusion the sentence supports is right. `hasattr(Cls, "field")` on a
dataclass field genuinely is vacuous — it is `False` either way, which is
exactly the **vacuous introspection** anti-pattern named in
`.kiro/steering/change-protocol.md` § Fixture Discrimination.

The cost is that the *reason* is wrong, in a file whose subject is guarding
against claims that outrun their evidence. `change-protocol.md` says plainly
that a false claim is worse than none because it tells the next editor the
coverage exists; the same logic applies to a false fact used to justify a
mechanism. Someone writing the next introspection guard may reach for
`vars(instance)` expecting required fields to be missing from it, and be wrong.

## Evidence

At `8e3cb05`:

```
>>> sorted(vars(Citation(key='k', authors='A', year=1, work='W',
...                      locator=None, verification=VerificationStatus.PRIMARY_TEXT)))
['authors', 'key', 'locator', 'note', 'verification', 'work', 'year']
```

All seven fields are present, including the six with no default. The docstring
predicts they would be absent.

Noted by the round-4 reviewer, and worth recording how: it was found by
**reading the docstring sentence by sentence against the code**, not by the
mandated `verified|caught|proven|tracked|...` grep, which does not match it.
Three of task 8.1's four review rounds turned on a false sentence in this same
file, and each one slipped that grep for the same reason — the vocabulary does
not cover prose explaining *why* a mechanism exists. That pattern is recorded
in the shared agent log as a `WARN` and in the spec's Implementation Notes.

## How to pick it up

1. Open `_assert_field_contract` in `tests/test_citation.py`.
2. Correct the sentence: required fields *are* in `vars(instance)`; what is
   vacuous is `hasattr(Cls, name)` / `dir(Cls)` on the **class**, because a
   dataclass field is an annotation, not a class attribute (unless it has a
   default, in which case the default *is* a class attribute — which is the
   asymmetry that makes `hasattr` unreliable rather than merely useless).
3. Keep the conclusion and keep the implementation unchanged.
4. Done looks like: the docstring's stated reason matches observable behavior,
   verifiable by pasting the `vars(...)` call above into `uv run python`.
   No assertion changes, so the suite result is unchanged at 2108 passed.

## Open questions

None.

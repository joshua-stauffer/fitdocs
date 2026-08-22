---
id: 2026-07-26-publicsurfacepin-names-wrong-test-module
title: design.md's `PublicSurfacePin` puts the `ProfileView` member-set assertions in a file that has never held them
status: open
importance: low
importance_why: The implementation is correct and the assertions exist; only design's pointer is wrong, so the cost is a future session looking in the wrong file or adding a duplicate guard.
effort: S
kind: inconsistency
area: athlete-benchmarks, .kiro/specs/athlete-benchmarks/design.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.1 round-2 reviewer)
pinned_at: 9a22c87
resume_command: "do: correct the PublicSurfacePin component in athlete-benchmarks/design.md to name tests/load/test_types.py as the home of the ProfileView member-set assertions, keeping tests/test_public_api.py for the re-export identity pin [queue: .kiro/queue/2026-07-26-publicsurfacepin-names-wrong-test-module.md]"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - tests/test_public_api.py
  - tests/load/test_types.py
blocked_by: []
---

## What
`design.md`'s `#### PublicSurfacePin` component (~line 1124) is scoped to
`tests/test_public_api.py` and says "the `ProfileView` assertions are updated to
the extended member set". That file holds no `ProfileView` member-set
assertions and never has. The member-set guard lives in
`tests/load/test_types.py::test_profile_view_protocol_exposes_no_per_pass_member`,
which is where task 4.1 correctly extended it.

The two files hold genuinely different pins and the split is right — it is only
design's pointer that is wrong:

- `tests/test_public_api.py` — the *re-export identity* pin (`_LOAD_EXPECTED`: every published name is importable and is the same object as its definition).
- `tests/load/test_types.py` — the *protocol member set* pin, including the Req 1.13 forbidden-member half that keeps `ProfileView` a pure store view.

## Why it matters
A later session reading `PublicSurfacePin` to find or extend the member-set
guard looks in `test_public_api.py`, finds nothing, and either concludes the
guard is missing or adds a second copy in the wrong module — where it would sit
next to the strict root `__all__` pin it has nothing to do with.

## Evidence
At `9a22c87`:

```
grep -n "ProfileView" tests/test_public_api.py
```
returns only two hits, lines 152 and 208, both identity checks inside
`_LOAD_EXPECTED` and the direct-import test — no member-set assertion.

The real guard, with its `_protocol_member_names` helper, is at
`tests/load/test_types.py` (helper ~line 540, test ~line 565 pre-4.1).

## How to pick it up
1. Read `#### PublicSurfacePin` in `.kiro/specs/athlete-benchmarks/design.md` (~line 1124) and the traceability row for Req 7.6 (~line 470).
2. Reword so the component names both test modules and states which pin each owns; keep Req 7.6 traced to the re-export pin, and trace the member-set assertions to `tests/load/test_types.py`.
3. Done looks like: the component's file scope matches where the assertions actually are, and no second member-set guard is invited into `test_public_api.py`.

Adjacent, same test file, same species of "the pin is not where you would look
for it": [[2026-07-26-load-all-pinned-only-by-ruff]].

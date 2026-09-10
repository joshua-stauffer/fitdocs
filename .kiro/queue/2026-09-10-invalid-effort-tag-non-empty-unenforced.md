---
id: 2026-09-10-invalid-effort-tag-non-empty-unenforced
title: InvalidEffortTag is documented as a non-empty tuple of problems, but nothing enforces or pins it and no task schedules it
status: open
importance: medium
importance_why: An empty InvalidEffortTag is a "malformed tag" that names no offending key -- describe() returns "" -- which is precisely what Req 5.6 exists to prevent; and three docstring rounds were already lost to claiming this was covered when it is not.
effort: S
kind: gap
area: effort-tags, src/fitdocs/contract.py, .kiro/specs/effort-tags/tasks.md, .kiro/specs/effort-tags/design.md
created: 2026-09-10
surfaced_by: /kiro-impl effort-tags task 1.1 (rounds 2-4 adversarial review)
pinned_at: 91b2a98
resume_command: "do: decide whether task 1.2 pins that the effort-tag reader never emits an empty problems tuple, or whether the non-empty annotation is dropped from design.md and tasks.md"
context:
  - .kiro/specs/effort-tags/tasks.md
  - .kiro/specs/effort-tags/design.md
  - src/fitdocs/contract.py
blocked_by: []
---

## What

Three documents describe `InvalidEffortTag.problems` as non-empty, and nothing
enforces it:

- `.kiro/specs/effort-tags/design.md` §EffortVocabulary annotates the field
  `# non-empty; EFFORT_KEYS order`
- `.kiro/specs/effort-tags/tasks.md:75` calls it "the malformed tag (a
  non-empty tuple of problems)"
- the type itself has no `__post_init__` and no validation

`InvalidEffortTag(problems=())` constructs cleanly, and `describe()` returns
`""` for it — a "malformed effort tag" that names no offending key at all.

Task 1.1 (which published the type) scheduled no non-empty pin in its own
`Pins:` list, and **task 1.2's bullets schedule none either** — its only
"non-empty" (tasks.md:113) concerns the *event string* ("event a string whose
stripped form is non-empty"), not `problems`. So the invariant is currently
owned by nobody.

## Why it matters

Requirement 5.6 exists so a malformed tag is reported with the key that caused
it. An empty-problems instance satisfies the type and defeats that requirement
silently: the reporter prints an empty string and the user learns nothing.

There is a second, sharper reason. During task 1.1 a production docstring
asserted this invariant was "pinned in task 1.2". That was false — the plan
schedules no such pin — and it was the third of three consecutive docstring
formulations rejected for claiming coverage that did not exist. The final
wording in `contract.py` is now scrupulously honest ("nothing here enforces
that"), but `tasks.md`'s unqualified "a non-empty tuple" is exactly the source
a fourth author would read and re-introduce the same false claim from.

## Evidence

At `91b2a98` / branch `impl/effort-tags` commit `93c4805`:

Executed against the built module:

```
>>> from fitdocs import contract
>>> inst = contract.InvalidEffortTag(problems=())
>>> inst.describe()
''
```

`.kiro/specs/effort-tags/tasks.md:75`:

```
    the malformed tag (a non-empty tuple of problems) with its one text
    renderer that joins `key: detail` pairs with `; `
```

Task 1.2's bullets (`tasks.md:102-136`) contain no assertion that `problems` is
non-empty; `grep -niE "non-empty|empty|at least one|zero"` over that block
returns only line 113 (event string) and line 122 ("an empty string for
event"). Confirmed independently by the round-3 reviewer and by the round-4
completion gate.

The shipped docstring in `src/fitdocs/contract.py` now states the gap plainly
rather than papering over it:

> This type places no lower bound on ``problems`` itself: a hand-built
> empty instance constructs, and :meth:`describe` returns ``""`` for it.
> The reader that will produce every real instance (task 1.2) emits a
> problem for each rule it fails, so an empty one does not arise in
> practice -- but nothing here enforces that.

## How to pick it up

1. Read task 1.2's bullets in `.kiro/specs/effort-tags/tasks.md` (lines
   102-136) and design.md §EffortVocabulary. Decide which of the two fixes
   applies — they are mutually exclusive.
2. **Either** add a pin to task 1.2's detail bullets: the reader never returns
   an `InvalidEffortTag` with an empty `problems` tuple, with a named mutation
   (e.g. make the rule loop emit no problem for a failing rule and assert the
   result is still reported as malformed) — **or** drop the `# non-empty`
   annotation from design.md and the "non-empty" parenthetical from tasks.md:75
   and accept the type as unconstrained.
3. If the pin is added and the invariant is meant to hold at construction
   rather than only at the producer, a `__post_init__` on `InvalidEffortTag`
   is the alternative — but note that adds behavior to the pure policy leaf,
   which task 1.1's boundary explicitly forbade, so it needs to be assigned to
   a task that owns `contract.py` (1.2, 1.3 or 4.1).
4. Done means: no document claims an invariant that no code or test enforces,
   and if the invariant is kept, a named mutation reds it.

## Open questions

Whether "non-empty" is a real contract or an incidental description of what the
reader happens to produce. If the reader is the only producer and it is pinned
to emit at least one problem per failure, the type-level constraint may be
redundant — in which case dropping the annotation is the cheaper correct
answer, not adding a guard.

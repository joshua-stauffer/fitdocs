---
id: 2026-07-25-document-date-signature-pin
title: Pin document_date's parameter type in training-load task 4.1
status: done
importance: medium
importance_why: Cheap now (3-line spec edit); after task 4.1 lands it means resigning a reviewed reader in a module a third spec owns.
effort: S
kind: inconsistency
area: training-load, athlete-benchmarks, wiki-contract, src/fitdocs/contract.py
created: 2026-07-25
surfaced_by: /kiro-validate-design athlete-benchmarks
pinned_at: 2a01dfd
resume_command: "do: add the parameter type to document_date's pinned signature in .kiro/specs/training-load/tasks.md:228 and design.md:315,529 so it reads document_date(frontmatter: Mapping[str, object] | None) -> date | None, matching wiki-contract and athlete-benchmarks"
context:
  - .kiro/specs/training-load/tasks.md
  - .kiro/specs/training-load/design.md
  - .kiro/specs/wiki-contract/design.md
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/contract.py
blocked_by: []
---

## What

Three specs agree that `contract.document_date` is one shared reader, and the
2026-07-25 design re-validation assigned the addition to `training-load` task
4.1. But the two `training-load` files an implementer of 4.1 actually reads pin
the signature only as `document_date(frontmatter) -> date | None` — the
*parameter* type is never stated. The full form,
`document_date(frontmatter: Mapping[str, object] | None) -> date | None`,
appears only in `wiki-contract`'s and `athlete-benchmarks`' designs, neither of
which the 4.1 implementer has reason to open.

This is an under-specification, not yet a contradiction. Nothing is wrong today;
the accessor resolves nowhere in `src/` or `tests/`.

## Why it matters

`src/fitdocs/contract.py` ships both conventions, and the **non-optional one is
dominant** — four readers take `Mapping[str, object]` and one takes
`Mapping[str, object] | None`. An implementer following the majority writes the
non-optional form, which is a defensible reading of the abbreviated pin and
would pass its own review.

`contract.parse_frontmatter` returns `dict[str, object] | None`, and that is
what `load/engine.py` holds at both of its call sites. `athlete-benchmarks` task
5.2 threads exactly that optional mapping into the compute step and resolves the
date through the accessor. If 4.1 lands the non-optional form, 5.2 must either
add a None-guard at the call site — which the "one reader, no second copy"
invariant exists to avoid — or resign a reader in a module `wiki-contract` owns
after it has already been reviewed and merged.

The fix before 4.1 runs is three lines of spec text. After it runs, it is a
cross-spec signature change.

## Evidence

Read against `2a01dfd`. `src/fitdocs/contract.py` is clean at that SHA;
`src/fitdocs/load/engine.py` had uncommitted changes in the working tree
(`training-load` task 3.3 mid-implementation), so its line numbers may drift.

Abbreviated pin — the text 4.1's implementer reads:
- `.kiro/specs/training-load/tasks.md:228` — ``document_date(frontmatter) -> date | None`); whichever of the two specs lands first adds it with that exact signature and the other consumes it``
- `.kiro/specs/training-load/tasks.md:229` — assigns the addition to task 4.1 "with that exact signature", referring back to line 228's abbreviated form
- `.kiro/specs/training-load/design.md:315` and `:529` — same abbreviated form

Full pin — where the parameter type actually lives:
- `.kiro/specs/wiki-contract/design.md:84`
- `.kiro/specs/athlete-benchmarks/design.md:172` and `:1085`

Shipped convention in the target module (`src/fitdocs/contract.py`):
```
388:def is_workout_document(frontmatter: Mapping[str, object] | None) -> bool:
417:def document_uuid(frontmatter: Mapping[str, object]) -> str | None:
433:def document_version(frontmatter: Mapping[str, object]) -> int | None:
454:def source_refs(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
489:def unmanaged_keys(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
342:def parse_frontmatter(text: str) -> dict[str, object] | None:
```

Consumer side: `src/fitdocs/load/engine.py:277` and `:490` both hold
`parse_frontmatter(markdown)`'s optional result.

Not yet implemented — `grep -rn "document_date" src/ tests/` returns nothing.
`training-load` tasks 3.2, 3.3 and 4.1 are all unchecked in `tasks.md`.

## How to pick it up

1. Open `.kiro/specs/training-load/tasks.md` at line 228. Confirm the signature
   is still abbreviated and that task 4.1 is still `[ ]`. If 4.1 has landed,
   this item is moot in its current form — check what signature the real
   `contract.document_date` got and, if it is non-optional, reopen this as a
   consumer-side fix on `athlete-benchmarks` task 5.2 instead.
2. Edit the pin in three places — `tasks.md:228`, `design.md:315`, `design.md:529`
   — to `document_date(frontmatter: Mapping[str, object] | None) -> date | None`.
   Nothing else in either file changes; no requirement, task or component is
   touched, so no re-approval is needed. Record it in `training-load`'s
   `spec.json` `phase_note` the way that spec records its other amendments.
3. Cross-check the two specs that already carry the full form
   (`wiki-contract/design.md:84`, `athlete-benchmarks/design.md:172` and `:1085`)
   read character-identical afterward.

**Done** means all three specs state one identical signature, and a session
implementing `training-load` task 4.1 can write the reader correctly without
opening either sibling spec.

## Resolution (2026-07-26, commits bb5fabf + 097b021)

Done as specified, before task 4.1 ran — so the cheap version, not the
cross-spec signature change.

Step 2 named three sites; there were **four**. `tasks.md:352`, in the
Amendment 3 cross-spec-coordination section, carried another copy of the same
abbreviated pin (`document_date(frontmatter) -> date | None`) and would have
re-introduced exactly the drift this item exists to remove. All four markdown
sites now read
`document_date(frontmatter: Mapping[str, object] | None) -> date | None`:
`tasks.md:228`, `tasks.md:352`, `design.md:315`, `design.md:529`.

Step 3's cross-check passes: the form is character-identical to
`wiki-contract/design.md:84` and `athlete-benchmarks/design.md:172,1085`.
`grep -rn "document_date(frontmatter)" --include="*.md"` over
`.kiro/specs/training-load/` returns nothing, and `document_date` still
resolves nowhere in `src/` or `tests/`.

Step 3's `spec.json` note landed in `097b021` as a `phase_note` append. One
deliberate exception: the 2026-07-25 design-re-validation entry in
`amendments[]` still quotes the abbreviated form. It was left verbatim because
those entries are dated records of what was ruled at the time, and rewriting
one falsifies the log; the appended note says so explicitly and points at
`design.md`/`tasks.md` as authoritative for the signature an implementer
follows. If a later session decides the convention should instead be to
correct stale signatures in place throughout `spec.json`, that is a
convention decision worth queueing — not a defect in this fix.

No requirement, criterion, task or component changed, so no re-approval was
needed. `/kiro-spec-status training-load` is clean: phase `implementation`,
all three approvals true, 9 of 18 leaf tasks done — unchanged by this edit.

---
id: 2026-08-23-guard-re-basing-section-cites-a-test-that-no-longer-exists
title: The provenance record's Guard re-basing section cites a test that task 6.3 removed, as the sole test its recorded mutation redded
status: open
importance: medium
importance_why: This is recorded mutation evidence in a durable record — the artifact a future reader re-runs to confirm a guard still discriminates. The named test does not exist, so the evidence cannot be re-run, and task 9.4's ledger is built on re-running exactly this class of record.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.4 (final reviewer follow-up)
pinned_at: c786326
resume_command: "do: repair the Guard re-basing section's citation of test_reviewed_exemption_never_exempts_a_path_surface_hit, which task 6.3 removed with the reviewed-exemption table, so the recorded mutation evidence can be re-run"
context:
  - docs/reference/history-rewrites.md
  - tests/test_forbidden_strings.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`docs/reference/history-rewrites.md:869`, inside the
"Guard re-basing: mutation evidence (tasks 4.1-4.3)" section, names
`test_reviewed_exemption_never_exempts_a_path_surface_hit` as the sole test a
recorded mutation redded.

That test no longer exists. Task 6.3 removed the reviewed-exemption table it
belonged to.

```
$ grep -rn "test_reviewed_exemption_never_exempts_a_path_surface_hit" tests/
(no matches)
$ grep -n "test_reviewed_exemption_never_exempts_a_path_surface_hit" docs/reference/history-rewrites.md
869:...
```

## Why it matters

This section is not prose — it is the **recorded mutation evidence** that
tasks 4.1–4.3 produced, and it is the record a later task re-runs to confirm a
guard still discriminates. Task 9.4's entire per-survivor ledger works by
taking a recorded mutation from this section and re-running it on the
post-retirement tree.

A citation naming a deleted test cannot be re-run. The recorded red is
therefore unverifiable — not wrong when it was written, but no longer
checkable, which is the property the record exists to provide.

This is pre-existing (it predates Major 9 and was not introduced by any task
this run) and it is *not* a defect in the guard: the surviving guard is alive
and task 9.4 re-ran its other recorded mutations successfully. The problem is
confined to this one citation's re-runnability.

Related but distinct from the seven destroyed scratch citations tracked at
`.kiro/queue/2026-08-23-provenance-record-cites-seven-destroyed-scratch-files.md`
— that one is about deleted *evidence files*, this one about a deleted *test*.

## Evidence

- `docs/reference/history-rewrites.md:869` — the citation, in the
  tasks 4.1-4.3 mutation-evidence section
- `grep -rn test_reviewed_exemption_never_exempts_a_path_surface_hit tests/`
  returns nothing on `c786326`
- The removal: task 6.3, "Empty the tip of every forbidden value and retire the
  reviewed-exemption table" (`.kiro/specs/encumbered-content-purge/tasks.md`,
  task 6.3, `[x]`)
- `tests/test_forbidden_strings.py:1087-1090` carries the surviving comment
  about the retired exemption table

## How to pick it up

Open `docs/reference/history-rewrites.md` at the Guard re-basing section and
find the row naming the test.

Decide what the record should say. The mutation was really run and really
redded that test at the time — that history is not in question and must not be
rewritten. What is needed is a note that the named test was subsequently
removed at task 6.3 with the reviewed-exemption table, so a reader knows why
re-running is impossible rather than concluding the record is wrong.

If an equivalent surviving assertion covers the same property, name it as the
present-day re-run target alongside the historical record. Check
`tests/test_forbidden_strings.py`'s path-surface assertions before claiming one
does — and if you claim it, re-run a mutation against it and record the result,
rather than asserting the equivalence.

Hold to the record's standard, which three review rounds established this run:
every pointer opened and confirmed, every causal clause traced to a nameable
source, and no clause kept whose source cannot be named.

Done when the section's evidence is either re-runnable or explicitly marked as
historical with the reason.

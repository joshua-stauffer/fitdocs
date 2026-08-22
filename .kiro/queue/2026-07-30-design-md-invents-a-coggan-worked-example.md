---
id: 2026-07-30-design-md-invents-a-coggan-worked-example
title: design.md and task 12.3's Observable clause both name a Coggan worked example the manuscript does not contain
status: open
importance: medium
importance_why: The spec asserts a specific numeric example (210 W ÷ 280 W = 0.75) as something a cited work publishes, and it does not — verified twice against the manuscript. A spec that invents a source's contents is the exact failure Req 15 exists to prevent, and the next reader has no way to know the number was never in the text.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/design.md, .kiro/specs/fit-ingest/tasks.md
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.3 — implementer finding, independently verified by the parent session)
pinned_at: ab1038d
resume_command: "/kiro-spec-design fit-ingest [queue: .kiro/queue/2026-07-30-design-md-invents-a-coggan-worked-example.md] Remove the invented Coggan worked example from design.md and correct task 12.3's Observable clause"
context:
  - .kiro/specs/fit-ingest/design.md
  - .kiro/specs/fit-ingest/tasks.md
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_worked_examples.py
blocked_by: []
---

## What

Two places in the spec assert that Coggan (2003) publishes a worked
intensity-factor example:

- `.kiro/specs/fit-ingest/design.md:1690` — *"the Coggan IF example (210 W NP ÷
  280 W FTP = 0.75) is the pattern"*
- `.kiro/specs/fit-ingest/tasks.md:254`, task 12.3's Observable clause — *"the
  manuscript's own intensity-factor example reproduces exactly"*

The manuscript contains no such example. It publishes the eight-step
algorithm and qualitative IF/TSS **bands**, but no worked calculation deriving
a result from stated inputs.

## Why it matters

This is the failure mode the whole Amendment 1 citation layer was built to
prevent, appearing in the spec that mandates the layer.

The numbers 210 and 280 are plausible, well-formed, and wrong. Had task 12.3
followed its own Observable clause literally, it would have written a test
asserting that fitdocs reproduces "Coggan's published example" — pinning a
fabricated attribution character-for-character, with a green suite and a
whole-value backstop guarding the falsehood. That is precisely the shape a peer
warned about on this branch: *a whole-value backstop pins text, not truth*.

The task was saved by its own third clause ("where the work publishes none, the
test says so explicitly rather than inventing one"), which the implementer
correctly invoked. But the clause and the Observable contradict each other, and
only one of them is true of the source.

Left as is, the next reader of `design.md` believes the example exists, and any
future re-derivation of the NP/TSS constants starts from a false premise about
what the primary text contains.

## Evidence

**Verified twice, independently.**

The implementer fetched the manuscript `COGGAN_2003` cites and read all 22
pages via `pdftotext -layout`, reporting that neither `210` nor `280` nor a
computed `0.75` appears.

The parent session then re-fetched and re-extracted it without relying on that
report:

```
$ curl -sL -o coggan.pdf https://www.ipmultisport.com/ref_lib/Coggan_Power_Meter.pdf
$ pdftotext -layout coggan.pdf out.txt && wc -l out.txt
     965 out.txt
$ grep -nE '210|280|0\.75' out.txt
504:       <0.75           level 1 recovery rides
505:       0.75-0.85       level 2 endurance training sessions
519:<0.75 (i.e., normalized power was <75% of threshold power), but the average power
```

All three hits are qualitative bands or a restatement of what an IF below 0.75
means. `210` and `280` do not occur anywhere in the document. Reading the
surrounding section (the IF/TSS discussion following printed p. 10's eight
steps) confirms it gives typical-value tables for events and training sessions,
not a computation from inputs.

The citation record itself is accurate and is **not** implicated: `COGGAN_2003`
in `src/fitdocs/metrics/sources.py` quotes the eight steps and claims nothing
about a worked example. The invention is in the spec only.

## How to pick it up

1. Open `.kiro/specs/fit-ingest/design.md:1690` and delete the parenthetical
   worked example. The surrounding point — that a worked example is the pattern
   for a 15.1 test — is fine; only the Coggan instance is false. If an example
   of the pattern is wanted, use the Banister case, which is real and is
   already implemented as a *computed, explicitly-not-quoted* value.
2. Correct task 12.3's Observable clause at `.kiro/specs/fit-ingest/tasks.md:254`.
   It should say what the task actually requires and what shipped: that the
   works publishing no worked example are recorded as publishing none, and that
   the training-impulse test states its expected number is computed rather than
   quoted.
3. Check whether any other spec text assumes the example. `grep -n '210\|280\|0\.75'`
   across `.kiro/specs/fit-ingest/` and `docs/reference/`.
4. `tests/metrics/test_worked_examples.py` already pins `COGGAN_2003.note`
   against a future editor silently adding a fabricated example, so the code
   side needs no change — verify that test still passes after the doc edits.

Done looks like: no spec document claims Coggan (2003) publishes a worked
example, and task 12.3's Observable describes what the task actually delivers.

## Open questions

- Where did 210/280 come from? The obvious hypothesis — that it was carried in
  from `docs/reference/fitdocs-ai-reference.md`, the working document Req 15.5
  forbids citing as a source — is **eliminated**: the parent session ran
  `grep -n '210\|280 W\|= 0\.75' docs/reference/fitdocs-ai-reference.md` at
  `ab1038d` and got no hits. So the numbers did not come from the working
  reference, and their origin is genuinely unknown. The remaining candidates
  are the Allen & Coggan *book* (which this project never obtained, and which
  is exactly the work `COGGAN_2003`'s note says it deliberately does not cite)
  or plain invention during design drafting. Worth one grep of the spec's own
  history (`git log -S 210 -- .kiro/specs/fit-ingest/design.md`) when picking
  this up, since the answer changes whether this is a sourcing lapse or a
  drafting slip.

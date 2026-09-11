---
id: 2026-09-11-e2e-adjacency-assertion-whitespace-coupled
title: The effort-tags e2e warning assertion is coupled to CLI report indentation
status: open
importance: low
importance_why: A purely cosmetic reporter change reds a behavioural test, which trains sessions to weaken the assertion rather than investigate.
effort: S
kind: inconsistency
area: tests/test_effort_tags_e2e.py, src/fitdocs/cli.py
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 5.2 review
pinned_at: d1147a0
resume_command: "do: decouple the effort-tags e2e warning-pairing assertion from the CLI reporter's literal indentation"
context:
  - tests/test_effort_tags_e2e.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What

`tests/test_effort_tags_e2e.py:434` asserts
`f"  {doc_ref}\n    carries an effort tag" in regen_result.output`, hard-coding
the reporter's two-space and four-space indentation to prove the warning's
document line and detail line belong to each other.

The intent is right and was hard-won: the assertion it replaced
(`doc.name in result.output`) was an ever-present token, since every successful
regen lists the document under `Written:`. But the encoding means a cosmetic
reporter change reds a behavioural test.

## Why it matters

A test that reds for a reason unrelated to its subject teaches the next session
that the assertion is noise. The likely response is to weaken it back toward
substring presence, which is exactly the vacuous form this assertion exists to
replace. Recording the trade-off now means that session inherits the reasoning
instead of rediscovering it.

## Evidence

`tests/test_effort_tags_e2e.py:434` matches the consecutive
`console.print(f"  {warning.doc}" ...)` and
`console.print(f"    {warning.detail}" ...)` at `src/fitdocs/cli.py:749,752`.

Mitigating facts established during review: `soft_wrap=True` removes the
terminal-width wrapping hazard, and the same 2-space/4-space convention recurs
at `cli.py:519/522, 690/693, 740/743`, so it is a deliberate house convention
rather than incidental formatting. The assertion is brittle, not vacuous.

The mutation it exists to catch: `DocWarning(doc="a-document", detail=...)` in
`src/fitdocs/sync.py` -- it must red.

## How to pick it up

1. Read the assertion and the reporter together, then decide whether this is
   worth changing at all -- "brittle but correct" may beat every alternative,
   and that is a legitimate outcome to record and close.
2. If you do change it, the bar is unchanged: with
   `DocWarning(doc="a-document", ...)` applied, the test must still red. Verify
   by mutation, not by reading.
3. A structured accessor on the report object, rather than scraping rendered
   output, is the shape most likely to be both robust and non-vacuous.

Done looks like: either a decision recorded that the current form is the best
available, or an assertion that survives a reformat and still reds on the
subject-swap mutation.

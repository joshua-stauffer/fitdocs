---
id: 2026-07-28-design-coggan-cross-reference-line-stale
title: fit-ingest design.md's `COGGAN_TSS` cross-reference names a stale line number, and it propagated into code
status: open
importance: medium
importance_why: Not the staleness itself — one wrong line number is trivial. It is that the design presented a line-numbered cross-reference as authoritative, an implementer copied it into a shipped citation note instead of checking the file, and it landed pointing at a string continuation. The task's own text said to verify every locator against the text rather than the design's table, and this was the one locator that was not.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/design.md
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.1 review — reviewer checked the cross-reference the implementer had copied)
pinned_at: 8e72bfc
resume_command: "/kiro-spec-design fit-ingest [queue: .kiro/queue/2026-07-28-design-coggan-cross-reference-line-stale.md] Replace the line-numbered COGGAN_TSS cross-reference with a symbol reference"
context:
  - .kiro/specs/fit-ingest/design.md
  - src/fitdocs/load/channels/sources.py
  - .kiro/queue/2026-07-26-line-number-citations-in-tests-go-stale.md
blocked_by: []
---

## What

`design.md`'s `#### MetricsSources` section identifies the Coggan source as
"already shipping as `COGGAN_TSS` with `PRIMARY_TEXT` at
`src/fitdocs/load/channels/sources.py:137`".

That line number is wrong and has been for a while. `COGGAN_TSS` is declared at
**line 122** on `impl/fit-ingest` and **line 138** on `main`. Line 137 lands in
the middle of a multi-line string — the note continuation reading
`"earlier chapter-length manuscript was found and opened in this "`.

## Why it matters

The staleness alone is trivial. What makes it worth recording is the failure
path it produced.

Task 9.1's instructions said explicitly: *"Re-verify every locator against the
text it names rather than against the design's table."* The implementer did
exactly that for the three primary-text locators — it opened the Banister page
scans, the Morton PDF and the Coggan PDF and confirmed each. Then it took this
one cross-reference from the design without opening the file, and shipped
`sources.py:137` in a citation note pointing at a string continuation.

So the design's line-numbered reference functioned as an authority that
displaced verification, in a task whose entire subject was not doing that. A
plain symbol reference could not have failed this way.

This is also the second recorded instance of the same species — see
`2026-07-26-line-number-citations-in-tests-go-stale.md`.

## Evidence

At `8e72bfc`:

```
$ grep -n 'COGGAN_TSS' src/fitdocs/load/channels/sources.py
122:COGGAN_TSS: Final[Citation] = Citation(

$ sed -n '137p' src/fitdocs/load/channels/sources.py
    "earlier chapter-length manuscript was found and opened in this "
```

On `main` the declaration is at line 138 — so the number was wrong on both
branches, by different amounts, which is the ordinary behaviour of a line
number in prose.

`design.md`'s `#### MetricsSources` section carries the `:137` reference. The
task 9.1 reviewer found it by checking the cross-reference rather than reading
past it.

## How to pick it up

1. In `.kiro/specs/fit-ingest/design.md`, replace
   `src/fitdocs/load/channels/sources.py:137` with a symbol reference —
   `COGGAN_TSS` in `fitdocs.load.channels.sources`. The symbol is unique,
   greppable, and cannot go stale on an edit above it.
2. Grep the rest of that design for other `\.py:\d+` references and decide
   whether each earns its line number. Some do (a citation to a specific bare
   literal, e.g. `aggregates.py:103`, is genuinely about a *site*), but those
   should be understood as snapshots — consider naming the enclosing function
   as well, so a reader who finds the line moved can still locate the thing.
3. Check the same pattern in the shipped citation note in
   `src/fitdocs/metrics/sources.py`, which copied this reference. (Task 9.1's
   remediation is already correcting that instance; this item is about the
   design being the source of it.)
4. Done looks like: no line-numbered cross-reference in this design points at
   something a symbol reference could name instead, and the `COGGAN_TSS`
   reference resolves by grep on any branch.

## Open questions

Whether to make this a convention across `.kiro/specs/**` — "cite symbols, not
line numbers, unless the line *is* the subject" — which would generalise both
this item and `2026-07-26-line-number-citations-in-tests-go-stale`. That is a
steering change rather than a one-line fix, and probably wants the two items
handled together.

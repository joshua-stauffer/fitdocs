---
id: 2026-07-26-doc-anchor-links-unchecked
title: Nothing checks that intra-doc anchor links resolve, and numbered headings make them break on every insertion
status: done
importance: medium
importance_why: Two of three anchors from docs/plugins.md into the contributor guide were broken at once — one pre-existing, one created and caught inside a single batch — and both are in shipped documentation a plugin author follows.
effort: S
kind: gap
area: docs, tests/test_docs_guarantees.py
created: 2026-07-26
surfaced_by: /kiro-queue sweep — inserting a section into docs/contributing-calculators.md renumbered its headings
pinned_at: e806c57
resume_command: "do: add a test asserting every `contributing-calculators.md#...` / intra-docs anchor link resolves to a real heading slug, and decide whether the guide's headings should keep their leading numbers at all given every insertion renumbers the anchors below it [queue: .kiro/queue/2026-07-26-doc-anchor-links-unchecked.md]"
context:
  - docs/plugins.md
  - docs/contributing-calculators.md
  - tests/test_docs_guarantees.py
blocked_by: []
---

## What

`docs/contributing-calculators.md` uses numbered headings (`## 4. The result
shape…`, `## 5. Reading configuration…`). GitHub-flavoured markdown derives the
anchor slug from the full heading text, so the number is *part of the anchor*:
`## 5. Reading configuration…` → `#5-reading-configuration-…`.

Consequently **inserting any section renumbers every anchor below it**, silently
breaking every inbound link. Nothing detects this: there is no link check in the
suite, and a dead in-page anchor does not 404 — the browser simply lands at the
top of the page, so it fails quietly even when a human clicks it.

Observed at `e806c57`. Three anchors point from `docs/plugins.md` into the
guide; two were broken simultaneously:

| Anchor | Status when found |
|---|---|
| `#2-answer-the-support-question-optional` | resolved |
| `#5-reading-configuration-and-the-activitys-date-only-through-loadcontext` | **broken by inserting a new section 5** — target became section 6 |
| `#4-register-it` | **already broken before the batch** — that section has been `## 7. Register it` and is now `## 8.` |

The second one is the instructive case: the link was *added* earlier in the same
batch (by the plugin-surface work), verified to resolve by a reviewer at that
time, and broken a few commits later by an unrelated item touching the same
file. Both are now repointed, but only because the renumbering was noticed by
hand.

## Why it matters

These are shipped docs. `docs/plugins.md` is the page a third-party calculator
author reads first, and its links into the contributor guide are how they reach
the detailed contract — including the `LoadContext` section, which is exactly
what the plugin-surface item existed to make discoverable. A dead anchor
silently returns them to the top of a 470-line document.

The cost is asymmetric: writing the guard is minutes, and the failure is
invisible until someone reports a confusing docs experience. Four Phase 4 specs
will add sections to these files.

## Evidence

At `e806c57`:

```
$ grep -rn "contributing-calculators.md#" docs/
docs/plugins.md:182:  ...(contributing-calculators.md#8-register-it)
docs/plugins.md:276:  ...(contributing-calculators.md#2-answer-the-support-question-optional)
docs/plugins.md:282:  [loadcontext-section]: contributing-calculators.md#6-reading-...-loadcontext
```

The heading set they must match:

```
$ grep -n "^## " docs/contributing-calculators.md
23:## 1. Implement the contract
240:## 2. Answer the support question (optional)
274:## 3. Outcome semantics (be honest)
302:## 4. The result shape: one load, everything else is diagnostic
338:## 5. Aggregating over recorded samples (Req 9.2)
354:## 6. Reading configuration and the activity's date: only through `LoadContext`
377:## 7. Talk to the user only through the session
420:## 8. Register it
438:## 9. Test against your methodology's own published numbers
454:## 10. Bundled data and licensing
```

`git show <pre-batch>:docs/contributing-calculators.md | grep "^## "` shows nine
sections with `Register it` at 7 — confirming `#4-register-it` predates this
batch and was never correct on this branch's history.

## How to pick it up

1. Add the check to `tests/test_docs_guarantees.py`, which already extracts and
   asserts against these files, so the machinery is there. Slugify every `^#+ `
   heading in each `docs/*.md` (lowercase, strip punctuation, spaces→hyphens —
   the GFM rule), collect every `](<file>#anchor)` and reference-style
   `[label]: <file>#anchor` target, and assert each resolves.
   **Include a positive control**: assert the collected anchor set is non-empty,
   or a regex change makes the guard pass having checked nothing (this repo has
   already shipped two vacuous walking guards).
2. Then take the design decision the guard only papers over: **should the guide's
   headings keep their leading numbers?** They are what couples anchors to
   position. Dropping them (`## Register it` → `#register-it`) makes anchors
   stable under insertion forever, at the cost of the guide's step-by-step
   numbering, which is genuinely useful in a tutorial. A middle option is
   keeping the numbers in the prose but not the heading. Decide deliberately —
   with numbers retained, the test will correctly redden on every future
   insertion, which is working-as-intended but recurring toil.
3. Check the reverse direction too while there: anchors from the guide into
   `plugins.md`, and any `README.md` links into either.

Done means: a broken intra-doc anchor fails the suite, and the numbering
question is answered in writing rather than rediscovered.

## Open questions

- Should this extend to *external* links (http/https) in `docs/`? That needs
  network access in the suite, which the load layer explicitly forbids for
  itself (`test_load_layer_imports_no_network_libraries`). Almost certainly a
  separate, optional check rather than part of the default gate.


## Resolution

**Done 2026-07-26** — `a91e4ab`, branch `chore/queue-top-ten`.

`tests/test_docs_guarantees.py` now slugifies every ATX heading in `README.md`
+ `docs/**/*.md` by GitHub's rule and resolves every anchor link against it --
inline, reference-style and same-document forms.

A count-based positive control proved insufficient: it cannot distinguish "found
fewer" from "there are fewer", and a first attempt at this left the corpus walk
green when the reference-style regex was dropped -- the form carrying the
`LoadContext` link. Hence a separate unit pin on the parser against a literal
fixture. Four mutations, all red: inserting a section into the guide, dropping
the reference-style regex, a vacuous inline regex, and stripping the leading
number from the slug rule.

**Numbering question answered in writing** (in the test file, next to the
guard): the numbers stay. The ordinals carry real meaning in a step-by-step
tutorial, and the defect was never the renumbering but its silence -- a dead
in-page anchor does not 404. The accepted cost, that inserting a section reddens
this test and inbound links must move in the same change, is recorded with the
trigger for revisiting it.

The item's open question about *external* http links is NOT addressed and
remains open.

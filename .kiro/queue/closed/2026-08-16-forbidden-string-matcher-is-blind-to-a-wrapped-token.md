---
id: 2026-08-16-forbidden-string-matcher-is-blind-to-a-wrapped-token
title: The forbidden-string matcher is a flat substring test, so a line-wrapped multi-word token is invisible to the guard, the plan and invariant 1
status: done
importance: high
importance_why: 37 real occurrences of multi-word identifying tokens are wrapped across a line break, and 13 (token, blob) pairs are wrapped in EVERY occurrence the blob has — those blobs read clean to the standing guard, to the redaction plan's classification and to invariant 1's own survivor check. Major 7 rewrites history once.
effort: M
kind: gap
area: encumbered-content-purge, tests/_forbidden_strings.py, scripts/purge/plan.py
created: 2026-08-16
surfaced_by: /kiro-impl encumbered-content-purge 6.5
pinned_at: 061f9ab
resume_command: "/kiro-impl encumbered-content-purge [queue: .kiro/queue/2026-08-16-forbidden-string-matcher-is-blind-to-a-wrapped-token.md] Make the forbidden-string matcher wrap-tolerant before task 7.2"
context:
  - tests/_forbidden_strings.py
  - scripts/purge/plan.py
  - scripts/purge/replacements.py
  - tests/purge/test_replacements.py
blocked_by: []
---

## What

`tests/_forbidden_strings.matches` asks `value.lower() in text.lower()` — a
flat substring test. Markdown prose wraps, so a multi-word token split across a
line break is not found. Everything built on that matcher inherits the
blindness: the standing tip guard, `scripts/purge/plan.py`'s content
classification (task 5.2, which decides which blobs are
`literal_replaceable`), and `test_invariant_1_zero_identifying_tokens_in_surviving_blob_content`,
whose survivor check is the same flat `token.lower() in lowered`.

The replacement *rules* are not affected: `build_rules` runs every multi-word
token through `_whitespace_tolerant_pattern`, which is exactly why this went
unnoticed — redaction is wrap-tolerant while every check on it is not. The
asymmetry means the checks cannot see whether the rules did their job on a
wrapped occurrence, and the plan may not list the blob at all.

## Why it matters

Task 7.2 is a one-shot rewrite driven by the plan. A blob whose only
identifying-token occurrence is wrapped is classified as carrying nothing to
replace. Independently, a wrapped token pasted into a tracked file at the tip
passes the standing guard, so the tip is not as clean as the guard reports —
and invariant 6 (the tip no-op) would then fire instead, at the point where it
is least convenient to diagnose.

This is the same defect species that produced task 6.5's own corrected
measurement, twice: a flat count of the copyright notice reported 46
occurrences in 28 blobs across 13 paths, a whitespace-wrap-tolerant count
found 49 / 31 / 15, and a count that also tolerates a wrap onto a comment
continuation line found **60 / 42 / 17**. Note the difference in kind, though:
the notice wraps onto `#` comment lines and no multi-word identifying token
does (0 of 485 measured), so this item is about the whitespace wrap only --
the token matcher does not need comment tolerance, it needs to stop being a
flat substring test.

## Evidence

Measured at `061f9ab` over every reachable blob, values never printed:

```
$ # multi-word token rows of FITDOCS_FORBIDDEN_STRINGS, flat vs wrap-tolerant
multi-word tokens: 2
flat occurrences: 448   wrap-tolerant: 485   extra: 37
(token, blob) pairs the flat matcher sees ZERO of but the wrap-tolerant sees: 13
```

`tests/_forbidden_strings.py:156-166` is the matcher. The wrap-tolerant
counterpart already exists and is tested:
`scripts/purge/replacements.py::_whitespace_tolerant_pattern`.

## How to pick it up

1. Read `tests/_forbidden_strings.py::matches` and
   `scripts/purge/replacements.py::_whitespace_tolerant_pattern` — the second
   is the machinery to reuse, not to re-derive.
2. Decide the blast radius first: `matches` backs the standing tip guard, so
   making it wrap-tolerant may newly fail tracked files. Measure that set
   before changing it (the 13 pairs above are historical blobs, not tip blobs).
3. Fix `plan.py`'s classification and invariant 1's survivor check in the same
   change — a wrap-tolerant matcher with a flat invariant check leaves the
   asymmetry in place, pointing the other way.
4. Done looks like: the matcher finds a token wrapped across a line break, a
   test pins that with a fixture that wraps, and the flat-vs-wrap-tolerant
   counts above are re-measured and equal.

## Outcome (closed 2026-08-17, branch `impl/wrapped-token` off `89b06b8`)

`tests/_forbidden_strings.matches` is wrap-tolerant for a multi-word value and
byte-for-byte the old flat test for a single-word one. It builds its pattern
from `scripts/purge/replacements.py::_whitespace_tolerant_pattern` -- the
rules' own helper, imported lazily because `replacements -> plan ->
_forbidden_strings` is a module-scope cycle -- so the matcher and the redaction
it checks cannot drift apart. Everything downstream of `matches` inherited the
fix: the standing tip guard, `scripts/purge/plan.py`'s content classification
and `classify_path`, `scripts/purge/sweep.py` and `scripts/purge/verify.py`.
Invariants 1 and 2 got a *separately derived* wrap-tolerant oracle
(`_tokens_surviving_in`, whitespace normalisation of both operands, never the
rules' helper), so a defect in that helper cannot make the rule and its own
invariant agree -- the 6.5 trap.

**Two claims in the body above are corrected by the measurements taken during
the work, both re-measured on the delivered tree:**

1. The three headline counts reproduce exactly -- 2 multi-word tokens, 448 flat
   occurrences vs 485 wrap-tolerant (37 extra), 13 (token, blob) pairs the flat
   matcher sees zero of. So does the scope note: a comment-continuation-tolerant
   count over the same population is also 485, adding 0, so the token matcher
   needed no comment tolerance.
2. **"Those blobs read clean to the redaction plan's classification" is not
   true at this tree.** Blobs whose `forbidden_strings` pass fires: 452 flat,
   452 wrap-tolerant, 0 newly classified. Every one of the 13 wrapped-only
   (token, blob) pairs sits in a blob that some *other*, single-word value
   already flags, so no blob changes disposition and `literal_replaceable` is
   unchanged. Historical paths matching: 20 of 702 blob-paths, both ways
   (24 of 787 if tree entries are counted too; the 20 and the both-ways
   equality are what matter, and both reproduce). Tracked files at
   the tip newly matching: 0 on content, 0 on path -- the fix has no blast
   radius on the standing guard today. The plan-level consequence was latent,
   not live: it depends entirely on the single-word values continuing to
   co-occur, which nothing enforces. The mechanism defect and the tip-guard
   hole were both real.

Left open, in the queue rather than fixed here:
`.kiro/queue/2026-08-17-invariant-2-survivor-call-site-is-unpinned.md` --
invariant 2 builds its own commit-message population in-body, so unlike
invariant 1 it has no seam for a counterfactual **without changing what it
measures**, and a mutation reverting its call site to the flat check survives
the suite.

One more limit, established by mutation during review and recorded here so a
later session does not read more into the corpus invariants than they carry:
**invariant 1's real-corpus assertion is structurally unable to observe the
rules losing wrap tolerance.** Breaking `_whitespace_tolerant_pattern` leaves
it green over all 452 surviving blobs, even though 35 of them carry
newline-wrapped occurrences -- because every multi-word value contains a word
that is itself a single-word forbidden value with its own rule, so the token
never survives and the corpus never enters the region where the two behaviours
differ. The counterfactual test, not the corpus invariant, is the whole pin.

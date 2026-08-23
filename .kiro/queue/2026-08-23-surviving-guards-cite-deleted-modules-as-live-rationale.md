---
id: 2026-08-23-surviving-guards-cite-deleted-modules-as-live-rationale
title: Thirty-six lines in surviving guard modules cite deleted purge modules in the present tense, one of them as the reason a guard is trustworthy
status: open
importance: medium
importance_why: One comment tells a future maintainer that an independent oracle cross-checks the whitespace-tolerant pattern, so a defect in the helper cannot make the rule and its own invariant agree. That oracle was deleted at 9.3. The stated safety property is gone and the comment still asserts it.
effort: S
kind: inconsistency
area: tests, encumbered-content-purge
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.3 (reviewer follow-up), verified this run
pinned_at: c786326
resume_command: "do: correct the present-tense references to deleted scripts/purge and tests/purge modules in the surviving guard modules, and decide whether the whitespace-tolerant pattern still needs an independent oracle now that its cross-check is deleted"
context:
  - tests/_forbidden_strings.py
  - tests/test_forbidden_strings.py
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

Task 9.3 deleted `scripts/purge/` and `tests/purge/`. Thirty-six lines across
the surviving test modules still reference those paths in the present tense.

Measured 2026-08-23 on `c786326`:

```
$ grep -rn "scripts/purge\|tests/purge" tests/*.py | wc -l
36
```

Most are harmless provenance notes ("moved here from
`scripts/purge/replacements.py`"), which are accurate history and should stay.
**One is not.**

## Why it matters

`tests/_forbidden_strings.py:214` explains why the whitespace-tolerant pattern
can be trusted: it points at
`tests/purge/test_replacements.py::_tokens_surviving_in`, which *"derives the
same tolerance ... so that a defect in this helper cannot make the rule and its
own invariant agree."*

That is a real and valuable property — an independent derivation, so a bug in
the helper cannot silently validate itself. **The independent derivation was
deleted at task 9.3.** The comment still asserts the protection. A maintainer
reading it will believe a cross-check exists that does not.

This is worse than a stale path, because the sentence is load-bearing: it is
the stated reason a reader should trust the helper. The other 35 references
mislead about *where code came from*; this one misleads about *whether the code
is guarded*.

Neighbouring instances at `:176`, `:232-234`, `:290`, and in
`tests/test_forbidden_strings.py` at `:625` and `:647` (the latter: "`scripts/purge/sweep.py`'s
own `tracked_files` solves the identical problem the same way") are the milder
species — they cite a deleted module as a live peer.

## Evidence

- 36 matching lines, measured above
- `tests/_forbidden_strings.py:214` — the independence claim, quoted above
- `tests/purge/test_replacements.py` deleted at commit `c18ec26` (task 9.3);
  `git show c18ec26 --stat` lists it among the 32 deletions
- No surviving module derives the tolerance independently — verified this run
  while confirming the retirement broke no live import (all remaining matches
  are comments and docstrings, no `import`)

## How to pick it up

Start with `tests/_forbidden_strings.py:214`, which is the only one carrying a
safety claim. Two honest options:

1. **Restore the independence** — re-derive the tolerance in a surviving module
   so the cross-check exists again, and update the comment to point at it. This
   is the option that keeps the property the comment promises.
2. **Retract the claim** — state that the independent oracle was deleted with
   the machinery at task 9.3, and that the helper is now self-validated. This is
   a declared loss in the same shape as the ones
   `docs/reference/history-rewrites.md` section 8 already records under
   Req 12.4, and it should probably be added there too.

Then sweep the remaining 35 with `grep -rn "scripts/purge\|tests/purge" tests/*.py`
and put every surviving reference in the past tense ("was moved here from",
"the retired `sweep.py` solved this the same way"), so no reader takes a
deleted module for a live peer.

Done when no comment in a surviving module asserts a property that a deleted
module was providing.

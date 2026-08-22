---
id: 2026-07-26-design-writer-guarantee-stale
title: design.md still credits benchmarks_to_document alone with the writer/reader shape guarantee, which was disproven
status: open
importance: medium
importance_why: The design states as a property of one function a guarantee that now requires two further mechanisms; a future task trusting it would reintroduce the defect that cost task 3.2 five rounds.
effort: S
kind: inconsistency
area: athlete-benchmarks, .kiro/specs/athlete-benchmarks/design.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, rounds 2-5 review)
pinned_at: 84e5e56
resume_command: "/kiro-spec-design athlete-benchmarks [queue: .kiro/queue/2026-07-26-design-writer-guarantee-stale.md] Amend the BenchmarkStore writer/reader shape guarantee to name the canonicaliser and the re-parse"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/load/profile.py
  - src/fitdocs/benchmarks.py
blocked_by: []
---

## What
`design.md`'s `#### BenchmarkStore` → Implementation Notes → Validation says:

> benchmark serialization goes through `benchmarks_to_document`, so the writer
> cannot emit a shape the reader would reject.

That was true while the serializer's output *was* the entire written region. It
stopped being true when task 3.2 made the write path **merge** into retained raw
content rather than replace it, and the guarantee now rests on two further
mechanisms the design does not mention: `_canonicalize_benchmarks_region` (which
keys the merge base by the parser's canonical scope identity) and
`save_profile`'s re-parse of the assembled document before the atomic rename.

## Why it matters
This is the exact sentence a task 3.2 implementer reasoned from, and reasoning
from it produced a writer that emitted `[benchmarks.Run]` and `[benchmarks.run]`
side by side and wrote files `load_profile` could never read again. The
implementation docstrings were corrected to say the guarantee "is enforced
there, not by this method alone"; the design was not, so the two now disagree
and the design is the one a future task reads first.

## Evidence
At `84e5e56`, `.kiro/specs/athlete-benchmarks/design.md:874-875` still carries
the original wording verbatim:

    - Validation: benchmark serialization goes through `benchmarks_to_document`, so
      the writer cannot emit a shape the reader would reject.

The corrected statement lives only in code, at `src/fitdocs/load/profile.py`
(`save_profile`'s docstring, ~`:329-361`, and `_canonicalize_benchmarks_region`'s).

The disproof is recorded in this spec's `tasks.md` Implementation Notes ("A
parser that accepts a wider grammar than its serializer emits makes
merge-on-write unsafe by construction") and was reproduced repeatedly across
task 3.2's review rounds.

## How to pick it up
Open `.kiro/specs/athlete-benchmarks/design.md` at the `#### BenchmarkStore`
component (~line 786) and read its Implementation Notes against
`src/fitdocs/load/profile.py`'s `save_profile` and
`_canonicalize_benchmarks_region` docstrings, which are the current truth.
Amend the Validation bullet to name all three mechanisms and to state the
invariant that makes the merge safe: *the merge base must be keyed by the
parser's canonical identity at every level where the parser's resolution is
non-injective — never by the raw on-disk spelling*.

Done when: design.md and the module docstrings say the same thing, and neither
credits `benchmarks_to_document` alone.

## Open questions
Whether this is large enough to want a `phase_note` entry in `spec.json`
alongside the earlier cross-spec amendments, or is a straightforward
correction. It changes no requirement and no task, so probably the latter.

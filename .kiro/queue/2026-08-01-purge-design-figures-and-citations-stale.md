---
id: 2026-08-01-purge-design-figures-and-citations-stale
title: design.md's ContentOracle measurements and the evasion-catalogue citations do not match reality
status: open
importance: medium
importance_why: The figures read as a sanity check a later reader would trust to judge whether the irreproducible artifact is intact; both are wrong.
effort: S
kind: inconsistency
area: encumbered-content-purge
created: 2026-08-01
surfaced_by: /kiro-impl encumbered-content-purge (task 2.4 review)
pinned_at: d835b7b
resume_command: "/kiro-spec-design encumbered-content-purge [queue: .kiro/queue/2026-08-01-purge-design-figures-and-citations-stale.md] Correct the ContentOracle measured figures and the evasion-catalogue attribution"
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/queue/2026-07-27-withdrawal-evasions-one-level-up.md
blocked_by: []
---

## What
Two unrelated inaccuracies in the same spec's documents, both surfaced while
implementing task 2.4.

**Measured figures.** design.md's ContentOracle *Validation* bullet states the
fingerprint set was "measured on the real files before deletion — 400 digests
… window lengths 3 to 20", and a later data-shape section repeats "Measured at
400". The real one-shot produced **434** digests over **14** window lengths
spanning **6 to 20** (19 absent).

**Evasion attribution.** design.md and tasks.md 2.4 both describe four of the
five probes as "the catalogued evasions from the withdrawal-evasions queue
item". That queue item catalogues **three** numbered entries, and only two of
the four have a counterpart in it. The probe *set* is correct and is specified
by tasks.md 2.4 and design.md themselves — only the attribution is invented.

## Why it matters
The figures read as a sanity check. A later session verifying that the
irreproducible `tests/_content_fingerprints.py` is intact would compare
against them and conclude the artifact is wrong when it is correct — or, worse,
"correct" a correct artifact toward a wrong number. After task 3.1 the real
figures cannot be re-measured.

The attribution sends a reader to a document that cannot support the claim.
The code was corrected during 2.4 to cite the specs instead; the specs still
carry the original wording, so code and spec now disagree in the opposite
direction.

## Evidence
Verified at `d835b7b`:

    $ grep -n '400\|3 to 20' .kiro/specs/encumbered-content-purge/design.md
    720:- *Validation*: measured on the real files before deletion — 400 digests at a
    721:  96-bit floor, 6.4 KB, window lengths 3 to 20; a 538-file tree scan in 2.50 s
    1709:`FINGERPRINTS: frozenset[str]`, `WINDOW_LENGTHS: frozenset[int]`. Measured at 400

    $ uv run python -c "import tests._content_fingerprints as g; \
        print(len(g.FINGERPRINTS), len(g.WINDOW_LENGTHS), sorted(g.WINDOW_LENGTHS))"
    434 14 [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20]

The evasion count was confirmed by reading
`.kiro/queue/2026-07-27-withdrawal-evasions-one-level-up.md` in full during
task 2.4's review: exactly three numbered entries.

**Appended 2026-08-03 (task 3.4) — a third wrong figure, same file, same
class.** design.md states the 2026-07-26 rewrite left **496 commit objects**
carrying the maintainer's personal address. Measured at `9d8ef1c`:

    $ git fsck --unreachable --no-reflogs | awk '$2=="commit"{print $3}' | wc -l
    557
    # of those, carrying the personal address in BOTH author and committer headers:
    248

The real figure is **248 objects**; 496 is the *header-entry* count (248 x 2),
reported by design.md as an object count. Sites:

    $ grep -n '496' .kiro/specs/encumbered-content-purge/design.md
    281:  `git fsck --unreachable` reports hundreds of unreachable commits and **496
    1424:     assumed. Deleting a ref does not delete its objects either: 496 commit
    1731:and a hook, and `.kiro/queue/` bodies hold roughly **496** hex tokens in evidence

Lines 281 and 1424 carry the wrong claim. **Line 1731 is a different subject
entirely** (hex tokens in queue-item bodies) that coincidentally shares the
number — do not "correct" it while fixing the other two.

This figure has already cost a review round. Task 3.4's first repair quoted it
out of design.md rather than measuring, which the plan's execution rules
explicitly forbid, and the false claim shipped into the provenance record
before a reviewer caught it. `docs/reference/history-rewrites.md` now carries
the measured figure; design.md still carries the wrong one, so the two
disagree.

## How to pick it up
1. Re-measure rather than copy the numbers above:
   `uv run python -c "import tests._content_fingerprints as g; print(len(g.FINGERPRINTS), sorted(g.WINDOW_LENGTHS))"`.
   The plan's standing rule is that no criterion rests on a count, so prefer
   replacing the figures with a command that regenerates them over pinning new
   literals.
2. Amend design.md's two sites in place, as a declared correction.
3. Fix the attribution in design.md and tasks.md 2.4 to cite the specs
   themselves, matching what `scripts/purge/fingerprints.py` now says, and drop
   the claim that the queue item catalogues five.

Done means a reader can check the artifact against the spec and get the right
answer, and no document attributes more evasions to that queue item than it has.

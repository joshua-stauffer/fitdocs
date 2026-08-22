---
id: 2026-08-04-distribution-forbidden-markers-scan-for-the-placeholder
title: The distribution forbidden-markers gate now scans artifacts for the redaction placeholder, never for the real terms
status: open
importance: medium
importance_why: Implemented literally from the redacted design, the release gate would pass an artifact containing the actual encumbered terms.
effort: S
kind: inconsistency
area: distribution, .kiro/specs/distribution/design.md
created: 2026-08-04
surfaced_by: /kiro-impl encumbered-content-purge (task 3.8 review, rounds 1 and 2)
pinned_at: 34b4164
resume_command: "/kiro-spec-design distribution [queue: .kiro/queue/2026-08-04-distribution-forbidden-markers-scan-for-the-placeholder.md] Re-base the forbidden-markers gate onto an out-of-repository source"
context:
  - .kiro/specs/distribution/design.md
  - .kiro/specs/distribution/research.md
  - tests/_forbidden_strings.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`distribution` Req 6 specifies a release gate that scans a built artifact for a
list of forbidden marker strings. That list was written as literal encumbered
terms. Task 3.8 redacted it, as it was required to — the terms are exactly what
Req 11.1 forbids a tracked file to contain.

The result is a gate whose specification now instructs it to scan artifacts for
the string `"the withdrawn methodology"` and never for the terms it exists to
catch. Implemented literally from the redacted design, it would pass an artifact
containing the real ones.

This is not a defect of the redaction. It is the recursion the purge hits
everywhere: a document that must name what it forbids cannot both do its job and
satisfy Req 11.1. The purge already solved it once, for its own guards — the
out-of-repository match data behind `FITDOCS_FORBIDDEN_STRINGS`.

## Why it matters

`distribution` owns the release gate that is supposed to stop encumbered content
reaching PyPI. If it is implemented from the redacted design as written, the gate
is decorative: it checks for a placeholder that will never appear in an artifact,
and reports clean.

The failure is silent and in the safest-looking direction — a green release check
that never had the capability it claims.

## Evidence

`.kiro/specs/distribution/design.md:635` — the marker list, redacted to three
entries, none of which is an encumbered term.
`.kiro/specs/distribution/design.md:642` — the surrounding claim, restated at
`34b4164` to survive the redaction.
`.kiro/specs/distribution/research.md:230-231` — the same list in the research
record.

The purge's own answer is at `tests/_forbidden_strings.py`: `load`/`require`/
`matches`/`scan_tree` read match data at run time from the file named by
`FITDOCS_FORBIDDEN_STRINGS`, so the repository holds none of the strings it is
forbidden to contain. Req 11.8's distinguishable-absence contract is the other
half: an unset variable **skips** rather than passes, so an absent source can
never be reported as a clean scan.

## How to pick it up

1. Read `tests/_forbidden_strings.py` end to end — it is the working precedent,
   already reviewed and shipped, and it solves this exact problem.
2. Read Req 11.8 in `.kiro/specs/encumbered-content-purge/requirements.md` for
   the skip-versus-pass contract. A gate that degrades to a silent pass when its
   source is missing is worse than no gate.
3. Amend `distribution`'s design so the marker source is out-of-repository and
   named by an environment variable, and so a missing source fails or skips
   loudly rather than passing.
4. Done looks like: `distribution`'s design specifies no literal encumbered term,
   the gate's behaviour with an absent source is specified explicitly, and the
   spec states that a clean scan with no source loaded is not a pass.

## Open questions

Whether `distribution` should consume `tests/_forbidden_strings.py` directly or
declare its own reader. The purge's module lives under `tests/` and is written
for the test tree; a release gate is production tooling and may not want that
dependency direction. That is a design call for whoever picks this up.

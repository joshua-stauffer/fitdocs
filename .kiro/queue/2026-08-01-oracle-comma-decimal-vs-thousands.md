---
id: 2026-08-01-oracle-comma-decimal-vs-thousands
title: design.md calls a comma a decimal separator; the value matcher treats it as a thousands separator
status: open
importance: high
importance_why: Two mutually exclusive readings of the same character in the one matcher every guard consumes; the fingerprints generated under one reading cannot be regenerated after the purge.
effort: S
kind: inconsistency
area: encumbered-content-purge, tests/_content_oracle.py
created: 2026-08-01
surfaced_by: /kiro-impl encumbered-content-purge (task 2.1 review)
pinned_at: c3d2201
resume_command: "/kiro-spec-design encumbered-content-purge [queue: .kiro/queue/2026-08-01-oracle-comma-decimal-vs-thousands.md] Declare which reading of a comma the value matcher implements"
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - tests/_content_oracle.py
blocked_by: []
---

## What
design.md's ContentOracle Testing Strategy names "a comma decimal separator"
as a spelling that must canonicalise equal to its dotted form. The implemented
matcher treats a comma as a **thousands** separator instead. The two readings
are mutually exclusive: under the design's reading `"12,5"` is one value; under
the code's it is two tokens.

The code's reading is almost certainly the right one for this material, which
is English-language and uses grouped integers. But nothing records that the
choice was made, so the design text still says the opposite.

## Why it matters
This is the single shared value matcher; design.md forbids a second
definition, and Major 4 re-bases the sdist and documentation guards onto it.
A later reader reconciling guard behaviour against design.md will find the
document describing behaviour the code does not have. The fingerprints in
`tests/_content_fingerprints.py` were generated under the code's reading and
**cannot be regenerated** once task 3.1 deletes the material, so the code's
reading is now effectively frozen — only the document can move.

## Evidence
Verified at `d835b7b`:

    $ grep -n 'comma decimal separator' .kiro/specs/encumbered-content-purge/design.md
    1778:  differing precision, a comma decimal separator, `MM:SS` versus `H:MM:SS`)

    $ uv run python -c "from tests._content_oracle import tokens, canonical; \
        print(tokens('12,5 km')); print(canonical('1,234'))"
    ['12', '5']
    1234

`tokens('12,5 km')` splits into two tokens rather than yielding one decimal;
`canonical('1,234')` strips the comma as a group separator rather than reading
it as a decimal point.

## How to pick it up
1. Open `tests/_content_oracle.py` and read `_INTEGER`, `_DECIMAL` and
   `canonical`'s docstring — the thousands reading is explicit there.
2. Open design.md's ContentOracle section, Testing Strategy bullets, and find
   the "comma decimal separator" phrase.
3. Decide which reading the spec means. If the code's (expected), amend
   design.md in place as a declared correction — the plan's convention is to
   state corrections rather than apply them silently — and say why: the corpus
   is English-language with grouped integers, and the fingerprints are frozen
   under this reading.
4. If instead the design's reading is meant, that is a much larger problem:
   changing canonicalisation invalidates `tests/_content_fingerprints.py`,
   which is irreproducible after task 3.1. Check whether 3.1 has run before
   assuming this is still possible.

Done means design.md and the module agree, and the disagreement is recorded
as a decision rather than silently resolved.

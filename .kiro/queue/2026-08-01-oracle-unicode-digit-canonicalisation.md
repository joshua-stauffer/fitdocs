---
id: 2026-08-01-oracle-unicode-digit-canonicalisation
title: The value matcher matches Unicode decimal digits but no longer canonicalises them
status: open
importance: medium
importance_why: A silent behaviour change introduced while fixing an unrelated crash; two spellings of one value stopped canonicalising equal, undocumented and untested.
effort: S
kind: defect
area: encumbered-content-purge, tests/_content_oracle.py
created: 2026-08-01
surfaced_by: /kiro-impl encumbered-content-purge (task 2.1 review)
pinned_at: c3d2201
resume_command: "do: decide whether tests/_content_oracle.py should canonicalise Unicode decimal digits or exclude them from tokenisation, then pin the choice with a test"
context:
  - tests/_content_oracle.py
  - tests/purge/test_content_oracle.py
blocked_by: []
---

## What
`_TOKEN_RE` uses `\d`, which matches Unicode decimal digits, so non-ASCII
digit runs are tokenised. Canonicalisation of them changed during task 2.1:
the original integer branch round-tripped through `int()`, which normalises
Unicode digits to ASCII; the replacement strips textually with `lstrip("0")`,
which does not.

The rewrite itself was necessary and correct — `int()` raises above CPython's
4300-digit limit, which made `scan()` non-total and would have crashed the
history-wide unreachability proof. The Unicode change was collateral.

## Why it matters
Two spellings of one value stopped canonicalising equal, which is the property
`canonical` exists to provide. Nothing documents or tests the current
behaviour, so it can drift again unnoticed. The practical exposure is low —
the corpus is English-language — but the matcher is the single shared
definition every guard consumes, and this is exactly the class of silent
divergence its docstring is otherwise careful about.

## Evidence
Verified at `d835b7b`:

    $ uv run python -c "from tests._content_oracle import tokens, canonical; \
        t='٠١٢'; print(tokens(t)); print(repr(canonical(t)))"
    ['٠١٢']
    '٠١٢'

The old `int()` path returned `'12'` for the same input. Confirmed by review
against the pre-rewrite implementation.

## How to pick it up
1. Read `canonical`'s docstring in `tests/_content_oracle.py` — it enumerates
   three collision classes and is otherwise accurate; this case is absent.
2. Decide: either normalise Unicode digits explicitly (e.g. `unicodedata.digit`
   per character, keeping the textual strip so the 4300-digit totality fix
   survives), or add `re.ASCII` to `_TOKEN_RE` so they are never tokenised.
   Prefer whichever keeps `scan()` total — check the totality test still passes.
3. Pin the choice with a test and confirm by mutation that it discriminates.
4. **Check whether task 3.1 has run.** If the fingerprints in
   `tests/_content_fingerprints.py` were generated before a canonicalisation
   change, they no longer correspond to the matcher — and they are
   irreproducible after 3.1. If 3.1 has run, do not change canonicalisation at
   all; document the behaviour instead.

Done means the behaviour is deliberate, documented, and mutation-pinned.

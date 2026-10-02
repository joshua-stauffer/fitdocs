---
id: 2026-10-02-redactor-tie-break-overlap-and-encoding-gaps
title: The connectors Redactor leaks fragments of overlapping secrets, breaks equal-length ties by hash order, and recognises only one percent-encoding of each value
status: open
importance: low
importance_why: Every leak needs two registered secrets that overlap in the text, or a URL encoded in a form fitdocs does not build itself; no shipped output is known to hit it, but the redactor is the one place Req 10.1-10.3 rests on.
effort: S
kind: bug
area: connectors, src/fitdocs/connectors/secrets.py, tests/connectors/test_secrets.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-redactor-tie-break-overlap-and-encoding-gaps.md] Make Redactor.redact mask overlapping secrets fully and deterministically, and register the other common encodings of each value"
context:
  - src/fitdocs/connectors/secrets.py
  - tests/connectors/test_secrets.py
  - .kiro/specs/connectors/design.md
  - .kiro/specs/connectors/requirements.md
blocked_by: []
---

## What
`Redactor.redact` (`src/fitdocs/connectors/secrets.py:78-87`) replaces each
registered value in turn, longest first, with `<redacted>`. Four gaps share
that one loop and the `add` method above it (`:64-76`):

1. **Overlapping values leak a fragment.** When two registered values overlap
   without one containing the other, replacing the first destroys the second's
   match, so the second's tail stays in the output.
2. **Equal-length ties are decided by set order.** `sorted(self._values,
   key=len, reverse=True)` is stable over a `set`, whose order depends on
   `PYTHONHASHSEED`. Which of two equal-length overlapping values wins, and so
   which fragment leaks, changes from run to run.
3. **Only one encoded form is registered.** `add` registers the raw value and
   `quote(raw, safe="")`. The `quote_plus` form (`+` for a space) and the
   lowercase-hex form (`%2f`) of the same value are not redacted.
4. **A value inside the marker mangles earlier markers.** A registered value
   that is a substring of `<redacted>` (e.g. `red`) is replaced inside markers
   already written, producing `<<redacted>acted>`. Cosmetic; no secret leaks.

## Why it matters
Requirement 10 is "no secret in any output"; the redactor is the single
mechanism behind it for connector reasons, exception text and service
messages. (1) and (2) mean a token pair can partially print, and in a way a
test can only catch some runs. (3) matters once a real connector
(`intervals-connector`) builds or echoes URLs it did not build through
`quote(safe="")`.

## Evidence
Run at `ad985b3` with `uv run python` against the shipped class:

```
r.add("abcdef"); r.add("defghi"); r.redact("xxabcdefghixx")
  -> xx<redacted>ghixx                      # "ghi" of the second secret leaks
r.add("a b/c"); r.redact("q=" + quote_plus("a b/c"))   -> q=a+b%2Fc   (unredacted)
                r.redact("q=a%20b%2fc")                 -> q=a%20b%2fc (unredacted)
r.add("abc"); r.add("bcd"); r.redact("abcd")
  PYTHONHASHSEED=0,1 -> a<redacted>     PYTHONHASHSEED=2,3 -> <redacted>d
r.add("red"); r.add("TOKEN"); r.redact("TOKEN then red")
  -> <<redacted>acted> then <redacted>
```

- `secrets.py:85` the sort; `:73-75` the single encoded form.
- design.md `:788-790` states "percent-encoded form when it differs" and
  "longest first" -- the design itself specifies only the shipped behaviour,
  so (1)-(3) are design-level gaps, not implementation drift.
- First reported by the task 1.1 reviewer subagent; every line above
  re-run in this session.

## How to pick it up
1. Read `secrets.py` (87 lines) and `tests/connectors/test_secrets.py`.
2. Replace the replace-loop with a span-based pass: find every match of every
   registered value in the original text, merge overlapping/adjacent spans,
   and emit one marker per merged span. That fixes (1), (2) and (4) at once
   (matching runs against the original text, never against marker text).
3. In `add`, also register `quote_plus(raw, safe="")` and the lowercase-hex
   variant of the `quote` form when they differ.
4. Pin each case with a fixture that fails under the current code (the four
   probes above are ready-made), and run the overlap case under two
   `PYTHONHASHSEED` values or with values inserted in both orders.
5. Done when the four probes print no fragment of any registered value and
   design.md's Redactor description says "overlapping matches are masked as
   one span" and lists the registered encodings.

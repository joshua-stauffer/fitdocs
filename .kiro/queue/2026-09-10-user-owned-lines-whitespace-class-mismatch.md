---
id: 2026-09-10-user-owned-lines-whitespace-class-mismatch
title: user_owned_lines' entry-start guard admits only space and tab while design.md says "not whitespace", and its key .strip() uses the full Unicode class
status: open
importance: low
importance_why: Two sites in one function disagree with the design and with each other about what counts as whitespace; unreachable from yaml.safe_load today, so it is a latent inconsistency rather than a live defect.
effort: S
kind: inconsistency
area: effort-tags, src/fitdocs/contract.py, .kiro/specs/effort-tags/design.md
created: 2026-09-10
surfaced_by: /kiro-impl effort-tags task 1.3 (rounds 1 and 3 adversarial review)
pinned_at: 25366bd
resume_command: "do: reconcile user_owned_lines' entry-start whitespace class with design.md -- either widen the guard to line[0].isspace() or narrow design.md to 'space or tab', and align the key-extraction .strip() with whichever is chosen"
context:
  - src/fitdocs/contract.py
  - .kiro/specs/effort-tags/design.md
  - tests/test_user_owned_lines.py
blocked_by: []
---

## What

`design.md` §UserKeyCarry defines a frontmatter entry start as a column-zero
line "whose first character is not whitespace, `#` or `-`". The implementation
in `src/fitdocs/contract.py` tests `line[0] not in (" ", "\t", "#", "-")` — only
two of Python's whitespace characters.

The **same function** then extracts the key with
`line.split(":", 1)[0].strip()`, and `str.strip()` uses Python's **full Unicode
whitespace class**. So one line admits only space and tab, and the next line
removes U+2028, U+00A0, form feed and the rest.

The consequence is that a line beginning with an exotic Unicode whitespace
character is treated as an **entry start** (the guard does not recognise it as
whitespace) whose key then **strips down to a user-owned spelling** (the strip
does) — so it is carried, when the design says a whitespace-led line is a
continuation.

## Why it matters

Not reachable from a real document today: `yaml.safe_load` is the only feed
(`contract.py`, `parse_frontmatter`), and a document whose frontmatter line
begins with U+2028 does not survive it in this shape. So this is a latent
inconsistency, not a live bug — which is why task 1.3 was told to leave it
alone rather than widen the predicate.

It matters because the two sites disagree with each other, not merely with the
doc. Whoever changes either one without reading the other will produce a real
defect, and the disagreement is exactly the kind that reads as intentional.

## Evidence

At `25366bd`, on branch `impl/effort-tags` (commit `2a52bf2`):

```
>>> from fitdocs.contract import user_owned_lines
>>> user_owned_lines(["---", " effort: race", "---", ""])
(' effort: race',)
```

The line is treated as an entry start, its key strips to `effort`, and it is
carried — although U+2028 is whitespace and the design says a whitespace-led
line continues the previous entry.

Two independent reviewers reached this from opposite directions:
- Round 1 found it by reading the predicate against `design.md:554`.
- Round 3 found the `.strip()` half while proving that mutating `.strip()` to
  `.rstrip()` is an equivalent mutant — it is equivalent *only* because the
  guard has already excluded space and tab from `line[0]`, so the two differ
  exclusively on this same exotic-whitespace input.

## How to pick it up

1. Read `design.md` §UserKeyCarry's entry-start predicate and the
   implementation in `src/fitdocs/contract.py` side by side.
2. Decide which is authoritative. Widening the guard to `line[0].isspace()` is
   the smaller code change and makes the two sites agree; narrowing `design.md`
   to "space or tab" is the smaller doc change but leaves the `.strip()`
   asymmetry in place and should then be commented.
3. Whichever you choose, **change both sites in the same commit** — the guard
   and the key extraction — or the disagreement simply moves.
4. If the guard is widened, add a fixture in `tests/test_user_owned_lines.py`
   with a U+2028-led continuation, and name the mutation (revert the guard to
   the two-character tuple) that reds it. Note that `.strip()` → `.rstrip()`
   stops being an equivalent mutant once the classes agree.
5. Done means: no reader of either site can conclude the two use the same
   whitespace class when they do not.

## Open questions

Whether the design intended full-Unicode whitespace at all, or wrote "not
whitespace" as shorthand for the YAML-practical case. `yaml.safe_load`'s own
indentation handling is the natural tiebreaker and nobody has checked it.

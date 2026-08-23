---
id: 2026-08-17-invariant-2-survivor-call-site-is-unpinned
title: Invariant 2's survivor call site takes no fixture, so which oracle it calls is unpinned
status: done
importance: medium
importance_why: Invariant 2 is now wrap-tolerant, but a mutation reverting its call site to the flat substring test leaves the whole suite green (measured) -- the corpus has zero survivors either way, and unlike invariant 1 the test has no injectable population, so nothing would notice the strengthening being undone before the one-shot rewrite.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_replacements.py
created: 2026-08-17
surfaced_by: "/kiro-impl encumbered-content-purge [queue: 2026-08-16-forbidden-string-matcher-is-blind-to-a-wrapped-token]"
pinned_at: c3d2201
resume_command: "do: give tests/purge/test_replacements.py::test_invariant_2_zero_identifying_tokens_in_commit_messages an injectable commit-message population (as invariant 1 has via _applied_content) and add the counterfactual that reds when its survivor check is reverted to a flat substring test"
context:
  - tests/purge/test_replacements.py
  - tests/_forbidden_strings.py
blocked_by: []
---

## What

Invariants 1 and 2 both moved from a flat `token.lower() in text.lower()`
survivor check to the wrap-tolerant `_tokens_surviving_in` oracle. Invariant 1
takes its population as a parameter (`_applied_content`), so it could be pinned
counterfactually -- `test_invariant_1_catches_a_token_wrapped_in_a_would_be_surviving_blob`
hands it a blob whose redacted text carries a wrapped token and requires it to
fail. Invariant 2 builds its population inside itself, by shelling out to `git
rev-list --all` and `git log`, so there is no seam to hand it a message
carrying a wrapped survivor. Its call site is therefore unpinned: the oracle it
calls is only observable through a corpus that has zero survivors either way.

**Corrected 2026-08-17, during review of this change.** "No seam" is too
strong: the module-scope `_applied_commit_messages` fixture that invariants
3/4/5 already use *is* a seam. The accurate statement is that there is no seam
**without changing what invariant 2 measures** -- it runs
`scan_commit_messages_for_rules` over real history, where that fixture carries
`apply_rules` output, and swapping them would silently substitute a different
subject. Step 2 below already concedes this; the sentence above did not.

## Why it matters

The invariants are the acceptance gate for the one-shot rewrite. A silently
reverted invariant 2 would not fail anything until the day a commit message
genuinely carries a wrapped token that the rules missed -- which is the day it
most needs to fire, and it would be reading history that had already been
rewritten.

## Evidence

Measured in the worktree for the wrapped-token change, with
`FITDOCS_FORBIDDEN_STRINGS` exported:

```
mutation m10: invariant 2's `hit = _tokens_surviving_in(message, tokens)`
              replaced by the flat `token.lower() in message.lower()`
result:       4 passed, 1199 deselected  -- SURVIVES

mutation m11: the same revert applied to invariant 1's call site
result:       1 failed, 4 passed -- test_invariant_1_catches_a_token_wrapped_
              in_a_would_be_surviving_blob reds as the sole failure
```

The asymmetry is exactly the injectable-population one: invariant 1's
signature is `(_applied_content: dict[str, tuple[str, str]])`, invariant 2's is
`(_built_rules: tuple[ReplacementRule, ...])` with the messages fetched
in-body.

## How to pick it up

1. Read `tests/purge/test_replacements.py`, the pair
   `test_invariant_1_zero_identifying_tokens_in_surviving_blob_content` /
   `test_invariant_1_catches_a_token_wrapped_in_a_would_be_surviving_blob`, and
   `_tokens_surviving_in` above them.
2. There is already a module-scope fixture with the right shape:
   `_applied_commit_messages` (`commit_id -> (original, redacted)`), used by
   invariants 3, 4 and 5. Invariant 2 predates it and re-fetches the messages
   itself; taking that fixture instead is most of the work. Check first that
   the two populations really agree -- invariant 2 applies
   `scan_commit_messages_for_rules`, the fixture applies `apply_rules`, and a
   change that quietly swaps one for the other is a behaviour change, not a
   refactor.
3. Done looks like: mutation m10 above reds as a sole failure, with a
   counterfactual built the same way invariant 1's is -- `load_tokens`
   monkeypatched to one synthetic multi-word token, so the fixture cannot
   raise for the wrong reason (the first draft of invariant 1's counterfactual
   did exactly that: it used a real multi-word token whose first word is
   itself a single-word token, so the flat check raised too and the mutation
   survived).

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.

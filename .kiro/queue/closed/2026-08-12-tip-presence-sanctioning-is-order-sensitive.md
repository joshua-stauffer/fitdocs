---
id: 2026-08-12-tip-presence-sanctioning-is-order-sensitive
title: Deleting an email-shaped fixture from the tip silently converts it into a derived identity-leak address
status: done
importance: medium
importance_why: Task 7.2 is a one-shot rewrite with no rollback, and this turns an ordinary tidy-up commit between 7.1 and 7.2 into a silent change to the redaction denylist. Harmless under the prescribed order, invisible if the order slips.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/replacements.py
created: 2026-08-12
surfaced_by: /kiro-impl encumbered-content-purge (task 6.4 remediation, the unsatisfiable-guard fix)
pinned_at: c3d2201
resume_command: "do: Decide whether identity_leak_addresses should treat a candidate that is absent from the tip but was present at an earlier reachable commit differently from one that was never at the tip, or whether task 7.1's quiescence gate should additionally freeze the tip against which 7.2's rules are generated. Read scripts/purge/replacements.py's identity_leak_addresses docstring first, then tasks.md 7.1 and 7.2."
context:
  - scripts/purge/replacements.py
  - tests/purge/test_replacements.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

The task 6.4 remediation replaced `_reachable_identity_leak_candidates`'s
`tests/` path-prefix scope with **tip-absence**: a candidate address present
in `git ls-tree -r HEAD` is sanctioned, one absent from it is a leak. That is
a strictly better rule than the prefix scope it replaced, and together with a
guard that halts on a confirmed address at the tip it makes the identity
denylist tip-disjoint by construction. It is also **order-sensitive in a way
nothing currently asserts**: the sanction is a property of the tip *at the
moment `build_rules` runs*, not of the address.

So an ordinary commit that deletes an email-shaped string from a tracked file
— a fixture retired, a documentation example reworded, a queue record tidied
— moves that address from "sanctioned" to "leak" without anyone editing the
generator. The next `build_rules` run emits a `--replace-text` rule for it,
and task 7.2 rewrites every historical blob that ever held it.

## Why it matters

Task 7.2 is the one artifact in this spec that cannot be corrected after it
runs. Between task 7.1 (which freezes the tip) and 7.2 (which generates the
rules from it) the rule set is a pure function of the tip, so the prescribed
order is safe. Nothing enforces that order, and nothing reports the
difference: the denylist would grow from three addresses to four with the
suite still green, because every acceptance assertion that could catch it is
the count assertion in
`test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold` — which
would simply be updated by whoever noticed it was red, that being the
obvious-looking fix.

The live instance is this branch's own incident record
(`.kiro/queue/2026-08-09-shared-object-database-pruned-during-6-4-remediation.md`),
which carries an email-shaped **role placeholder** — not an address at all,
just angle-bracket prose that happens to match the generic email shape. It is
sanctioned today only because it is at the tip. De-shaping it, which is
otherwise exactly the right hygiene and is what
`.kiro/steering/change-protocol.md`'s posture on identity values would
suggest, would make a redaction rule get generated for a string that is not an
identity.

## Evidence

Measured at `eeab771` with `FITDOCS_FORBIDDEN_STRINGS` exported, addresses
named by the 8-hex SHA-256 tag `_masked_address` produces:

- `_reachable_identity_leak_candidates` returns **7** candidates. **5** are
  present at the tip and therefore sanctioned; **2** are absent and are real
  leaks. The third real leak is the token-corroborated address, which is not
  a candidate at all — it comes from `_token_domain_addresses`, which is why
  the denylist is 3 rather than 2. `identity_leak_addresses` returns exactly
  those 3, identically
  in this working repository, in a `git clone --mirror` and in a
  `git clone --no-local` (pinned by
  `test_identity_denylist_is_identical_in_a_clone`).
- One of the 5 sanctioned candidates, tag `[1b019c94]`, occurs at exactly one
  reachable path: the 2026-08-09 incident record named above. It is a role
  placeholder in prose, not an address.
- `tests/purge/test_replacements.py::test_identity_leak_addresses_partitions_candidates_by_tip_presence`
  demonstrates the mechanism directly on a synthetic repository: two
  addresses, identical in every respect except tip-presence, land on opposite
  sides of the partition.

## How to pick it up

1. Read `identity_leak_addresses`'s docstring in
   `scripts/purge/replacements.py` — it states the rule and why tip-absence
   beats the path prefix it replaced. Do not undo that; the question here is
   only about *when* the tip is read.
2. Read tasks.md 7.1 and 7.2 and check whether 7.1's observable can carry the
   tip SHA that 7.2's rule generation must be pinned to, the way it already
   carries the abandonment record.
3. Decide between: (a) 7.1 records the tip SHA and 7.2 asserts `HEAD` still
   equals it before generating rules; (b) `build_rules` takes the tip
   revision explicitly rather than defaulting to `HEAD`; (c) accept the
   order-sensitivity and record it as a stated property rather than a gap.
4. Whichever is chosen, leave the incident record's placeholder alone until it
   lands, or de-shape it in the same change — not before.

## Open questions

- Is a *count* of derived addresses worth asserting in the 7.2 pre-flight, or
  does that just relocate the same "update the number" failure mode?

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

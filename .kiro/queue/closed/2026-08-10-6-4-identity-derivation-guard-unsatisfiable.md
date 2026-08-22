---
id: 2026-08-10-6-4-identity-derivation-guard-unsatisfiable
title: Task 6.4's identity-leak derivation guard cannot be satisfied by any fresh clone, so the branch cannot merge and Major 7 cannot start
status: done
importance: high
importance_why: It is the single blocker between the current tree and the one-shot rewrite. The generator itself is verified correct against four separate real git filter-repo rewrites; one guard on its inputs raises unconditionally, and nine acceptance tests error because of it.
effort: S
kind: bug
area: encumbered-content-purge, scripts/purge/replacements.py
created: 2026-08-10
surfaced_by: /kiro-impl encumbered-content-purge (task 6.4, round-4 review remediation)
pinned_at: 03f139d
resume_command: "do: Redesign identity_leak_addresses's consistency guard so the reachability-independent blob-text scan is the primary source and the orphan-commit source is additive, raising only when the union is empty or when the orphan source names an address the reachable scan missed. Then merge impl/replacement-rules, re-run task 7.1, and regenerate the rules against the tip 7.1 freezes."
context:
  - scripts/purge/replacements.py
  - tests/purge/test_replacements.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## Where the work lives

**Branch `impl/replacement-rules`, worktree `/Users/josh/code/fitdocs-replacement-rules`, four commits ahead of `main` (`03f139d`) and NOT merged**, because its suite is red:

    9e50a9f  the replacement-rule generator, as a tested module (task 6.4)
    62aead8  identity_email_rule is now a denylist, not an allowlist
    8088547  identity-leak derivation no longer silently degrades under --no-local
    eeab771  reopen task 6.4, its guard is unsatisfiable

`main` itself is green (2878 passed, 1 skipped) and unaffected.

## What

`identity_leak_addresses` derives the three real identity-leak addresses from
three sources and raises `ValueError` when the reachability-independent
blob-text scan names an address that neither the token-domain match nor the
orphan-commit source can corroborate.

`_orphaned_commit_identity_addresses` reads commit identities present in the
local object database but unreachable from any ref. **A fresh clone carries no
unreachable objects at all**, so that source returns nothing there — and since
2026-08-09 it returns nothing in this working repository either (see the
incident below). The guard therefore raises unconditionally, and the nine
acceptance tests that depend on the module-scoped rule-set fixture error.

## Why the guard exists, and why it is still the right instinct

It was added because the derivation *silently degraded* to 1 of 3 addresses in
a `git clone --no-local` — exactly the clone `design.md` step 3 and task 7.2
prescribe — leaving the constructed `<user>@<machine>.local` identity
permanently in `.kiro/specs/encumbered-content-purge/research.md`, a path the
rewrite does not remove. Nothing failed: the pattern stayed valid, and the
invariant-3 test asserted only that the derived set was non-empty, so 1 >= 1
passed while the leak scan searched only for what it had managed to derive.

So the guard must stay in spirit. What is wrong is its polarity: it treats the
*reachability-dependent* source as the authority.

## The fix

Make the reachable blob-text scan **primary** — it is reachability-independent
and therefore works in any clone — and the orphan-commit source **additive**.
Raise when the union is empty, or when the orphan source names something the
reachable scan missed (the real inconsistency), never when the orphan source is
simply unavailable.

**Check this first**: the reachable scan currently returns **6** candidates
where only **3** are real addresses. Confirm what the other three are before
promoting it to primary — the fixture-eating defect fixed in `62aead8` was
exactly this shape, and the corpus holds 36 distinct email-shaped strings of
which 33 are synthetic fixtures.

## The incident that made this visible

On 2026-08-09 a subagent ran `git reflog expire --expire=now --all` and
`git gc --prune=now` against what it believed was an isolated `cp -R` copy. **A
linked worktree's `.git` is a pointer file, not an object store**, so both
commands executed against the real shared `/Users/josh/code/fitdocs_oss/.git`.

Lost: every reflog in both trees, and all 572 previously-unreachable commit
objects. Not lost: anything reachable — `fsck --full` clean, `main` intact at
484 commits, every branch tip and tracked file present, no committed work gone.

Impact on the purge is close to neutral: task 7.2's clone drops unreachable
objects by construction, which task 7.1's own text states. The real losses are
the reflog safety net and the corroborating evidence this guard depends on.

Open question for the maintainer: whether to attempt a filesystem restore of
the pruned object database before Major 7. The fix above removes the need for
it, so this is optional rather than blocking.

## The other thing that happened, recorded because the lesson is general

The same subagent wrote the maintainer's real mailbox, real machine identity
and real hostname **in plaintext** into its own incident record, under an
"Evidence" heading, and committed it. Caught before any merge; the commit was
amended (`8088547`) and all four files in it scan clean, so nothing reached
`main`. The pre-amend object still exists unreachable and was deliberately not
pruned — another `gc` is what caused the incident above, those values already
exist throughout reachable history, and 7.2's clone drops unreachable objects.

**A document explaining which identity leak you found is exactly the shape that
leaks it again.** Name such values by role, never by value — in queue items,
incident records, commit messages and review reports alike.

## Done when

`identity_leak_addresses` returns the three real addresses in this working
repository, in a `--mirror` clone and in a `--no-local` clone, raises on a
genuinely inconsistent derivation, the branch's suite is green, and the branch
has merged.

## Resolution

**Done 2026-08-13**, merged to `main` fast-forward at `9144828` (5 commits);
worktree removed, branch deleted, quiescence restored.

Verified on merged `main`, not on the branch:
`test_identity_denylist_is_identical_in_a_clone[mirror]`,
`[no-local]`, `test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold`
and `test_identity_leak_addresses_survives_a_genuinely_pruned_repository` all
pass; full suite `3650 passed / 1 skipped` with `FITDOCS_FORBIDDEN_STRINGS`
exported and `3619 / 32` without, both under `-W error`.

The fix went further than this item proposed, in three ways the item could not
have known:

1. **The `tests/` path-prefix scope was retired, not kept.** The "check this
   first" instruction was the load-bearing part of this item: measured, the
   reachable scan returned 6 candidates of which only 2 were real, and **three
   of the false ones were the module's own docstring quoting its own test
   fixtures at a non-`tests/` path** — the prefix scope defeated by the file it
   was written into. Candidates are now partitioned by **tip-absence**, which
   is reachability-independent and needs no path allowlist.
2. **The orphan-commit source contributes nothing.** Making the tip guard cover
   it proved its union term dead (guard 1 forces
   `orphan ⊆ token_domain ∪ candidates` up to case, guard 2 forces
   `orphan ∩ tip = ∅`), so it was removed. It remains load-bearing in the two
   guards: an orphan-only address now **raises** rather than being silently
   added — the loud-not-silent posture this item's defect existed to establish.
3. **The identity rule is anchored**, closing a mangling defect invariant 4
   forbids (`<addr>.example` → `a redacted email address.example`) and an
   under-redaction that would have left a real identity in published history.
   The anchors are pinned by a 700-cell adjacency table whose expectations are
   derived from `_EMAIL_SHAPE` as an oracle. Five review rounds each found a
   real defect on an axis nobody had enumerated; a proposed anchor that passed
   the entire suite disagreed with the oracle 48–60 times, and the mutation
   that survived the whole suite before the table existed now reds 220 cells.

Two claims in the body above are stale and were corrected during the work: the
constructed machine identity is **not** "permanently in `research.md`" — it is
absent from the tip on both `main` and the branch and survives only in history,
which is what the rewrite reaches; and the reachable scan's 6 candidates were
2 real, not 3 (the third real address comes from the token-domain source, which
is not a candidate at all).

Follow-ups this left open:
`.kiro/queue/2026-08-12-tip-presence-sanctioning-is-order-sensitive.md`,
`.kiro/queue/2026-08-13-build-rules-clone-instruction-contradicts-the-module.md`
(high — `tasks.md` 7.2 still forbids the `--no-local` clone the derivation is
now proven independent of) and
`.kiro/queue/2026-08-13-invariant-1-and-2-diagnostics-print-raw-tokens.md`.

The maintainer also decided, on 2026-08-12, **not** to attempt a filesystem
restore of the pruned object database — the open question this item raised.
The fix removed the need for it.

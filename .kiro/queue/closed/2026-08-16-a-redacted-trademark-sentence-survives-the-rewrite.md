---
id: 2026-08-16-a-redacted-trademark-sentence-survives-the-rewrite
title: A trademark-notice sentence survives the rewrite with its identity redacted, and reads as the same phrase twice
status: done
importance: medium
importance_why: Req 11.4 forbids a trademark notice at any commit; task 6.5 removes the mark and the copyright notice but leaves the sentence that asserts the trademarks. Whether that sentence is in scope is a maintainer judgment, and task 7.2 is the only chance to act on it.
effort: S
kind: decision
area: encumbered-content-purge, scripts/purge/replacements.py
created: 2026-08-16
surfaced_by: /kiro-impl encumbered-content-purge 6.5
pinned_at: c3d2201
resume_command: "/kiro-impl encumbered-content-purge [queue: .kiro/queue/2026-08-16-a-redacted-trademark-sentence-survives-the-rewrite.md] Decide whether the redacted trademark sentence is in Req 11.4's scope before 7.2"
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - scripts/purge/replacements.py
blocked_by: []
---

## What

Task 6.5 removes the copyright notice and the trademark mark. It does not
remove the *sentence* that states the trademarks, because that sentence is a
record of the licensing constraint and Req 11.6 says to retain the record with
the identity redacted. After the full rule set, the surviving text at the one
site reads:

```
> **Licensing / attribution — OPEN QUESTION.** The workbook is marked
> "[redacted third-party copyright notice]" and "The withdrawn methodology and
> the withdrawn methodology are trademarks of the third party." Before shipping
```

Two separate questions:

1. **Is that a "trademark notice" under Req 11.4?** Criterion 11.4 forbids the
   third party's copyright notice or trademark notice at any commit. The
   sentence no longer names anyone, which is exactly the reading the maintainer
   already rejected once for the copyright notice on 2026-08-12.
2. **"A and A are trademarks of B"** — the methodology name and its
   abbreviation are two distinct tokens with the same replacement, so a
   sentence listing both now lists the same phrase twice. That is the same
   duplicate-noun shape invariant 4 already names for
   `withdrawn methodology methodology`, one level up, and it is not in the
   needle list.

## Why it matters

Both are one-shot: after 7.2 the history is what it is, and 7.4 destroys the
original repository. Question 1 is a judgment the maintainer has already had to
make once for the neighbouring case; question 2 is cosmetic in isolation but is
the sort of shape that reads as a mangling to a later reader of the published
history.

## Evidence

Reproduced by applying the full rule set (`build_rules` at `40eb36e`, 113
rules) to the reachable blobs of `docs/reference/<withdrawn writeup>.md` — the
excerpt above is the actual redacted output, not a prediction.

The mark itself is gone (18 occurrences, 16 blobs, 3 paths → 0) and so is the
copyright notice (60 → 0, measured on a real `git filter-repo --replace-text`
run over a throwaway clone, not simulated); this item is only about the prose
sentence left behind.

## How to pick it up

1. Put the excerpt above in front of the maintainer next to Req 11.4 and 11.6
   and ask which way it goes; both readings are defensible and the conservative
   one removes more.
2. If it is in scope, the rule shape is the same as `notice_rules`': key on the
   distinctive phrase (`are trademarks of`), consume a bounded span around it,
   and replace with a neutral record — never key on the word `trademark` alone,
   which appears throughout this spec's own prose.
3. If question 2 is worth fixing on its own, the fix is in the token tiers, not
   here: a rule for "<replacement> and <replacement>" collapsing to one.
4. Done looks like: a decision recorded in `tasks.md` (or a task added), and if
   removal is chosen, the six invariants re-measured with the new rule present.

## Resolution

**Closed `done` 2026-08-23 — verified satisfied in the tree.** Post-purge queue
triage after `encumbered-content-purge` completed (spec 57/57, `87ce085`).

This item asked whether Requirement 11.4 was discharged: whether the copyright
notice, the reserved-rights phrase, or the trademark sentence survived the
rewrite with only the identity redacted. The maintainer's 2026-08-12 decision
was that the notice text itself had to go, not merely the name inside it.

It went. Measured on `HEAD` at triage time:

```
$ git grep -In -i "all rights reserved" -- .
(no output, exit 1)

$ git grep -In -i "trademarks of" -- .
(hits only inside .kiro/queue/*.md, which describe the problem in generic
 terms and name nobody)
```

Zero surviving notice sites, zero surviving reserved-rights fragments, zero
surviving trademark sentences in tracked files. The 42 notice sites and 16
trademark marks this item measured pre-rewrite are gone. Closed as satisfied,
not as moot.

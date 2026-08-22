---
id: 2026-08-19-two-inherited-imprecisions-in-the-classification-section
title: Two inherited imprecisions in the provenance record's classification section — a numeral the table does not support, and a self-contradicting parenthetical
status: open
importance: medium
importance_why: The first is a count the table itself refutes, in the document whose entire job is stating what was and was not verified; both predate the 2026-08-19 rounds and so were never in any round's declared scope.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference/history-rewrites.md
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.8 classification, final review FOLLOW_UPS 1 and 2)
pinned_at: 831aa5c
resume_command: "do: correct the 'three of the five observed-mutation rows' numeral and row 7.3's misplaced parenthetical in the classification section, both inherited from earlier rounds"
context:
  - docs/reference/history-rewrites.md
  - tests/purge/test_verify.py
blocked_by: []
---

## What

Two imprecisions in the classification section of `docs/reference/history-
rewrites.md`. Neither was introduced by the 2026-08-19 remediation rounds —
both predate them and so fell outside every round's declared scope — and
neither is a false PINNED/UNPINNED label. Recorded rather than fixed
opportunistically.

**1. A numeral the table itself does not support (medium).** The paragraph
beginning "Task 6.1 ran three of the five observed-mutation rows fresh" names
"1.2 and 9.5, both UNPINNED, plus the same mutation pinning 6.1 and 6.2". The
table supports only **two** of the five as run fresh at task 6.1: rows 1.2 and
9.5 say "re-confirmed this task" / "Re-run this task", while rows 1.5, 3.6 and
11.13 cite prior commits (`bfe0ddf`, `221d60a`, `e40f6ec`). Rows 6.1 and 6.2
are explicitly excluded from "the five" because they are PINNED, so they
cannot be the third member.

This matters more than an ordinary typo because it is a count, in the
document whose stated job is recording exactly which criteria were verified
and how — and this spec's own execution rules open with "No task rests on a
count."

**2. A self-contradicting parenthetical in row 7.3 (low).** The row reads:
"...which is 10 of the 14 in the module; the other four assert a pass or a
raise and are unaffected (`..._fails_on_a_disallowed_commit_id`, ... ten
names ...) plus `test_deliberately_incomplete_fixture_repository_fails_the_
rows_it_should`". The parenthetical enumerates the **reddened** tests, not the
four unaffected ones, so read strictly the sentence contradicts itself.

Every number in it is correct — 14 `test_check_reflog_and_unreachable_gone_*`
tests exist, exactly 10 assert a failing row, the other 4 assert a pass or a
raise, and 10 + `test_deliberately_incomplete...` = the claimed 11 reds. Only
the parenthetical's placement is wrong.

## Evidence

Both measured by the final reviewer at `831aa5c` plus the uncommitted
classification work:

- rows 1.2 and 9.5 carry "this task" language; 1.5, 3.6 and 11.13 cite prior
  commits — so the "three" has no third member.
- `grep -n "def test_check_reflog_and_unreachable_gone" tests/purge/test_verify.py`
  → 14 hits; the 10 named in the parenthetical are the FAIL-asserting ones.

## How to pick it up

For (1): re-read the five observed-mutation rows, count what task 6.1 actually
re-ran, and state that number — or drop the numeral and name the rows, which
is what the rest of the section does and what "no task rests on a count"
implies.

For (2): move the ten-name list to the clause it enumerates, or relabel it.
Do not renumber anything; every figure in the sentence is already correct.

Do not re-open any row's PINNED/UNPINNED label while fixing these — the
labels were verified by exact set equality against `requirements.md`'s 81
criteria (33 PINNED / 1 PRESERVED-ONLY / 47 UNPINNED) across three
independent review rounds.

---
id: 2026-07-30-committed-test-cites-a-gitignored-scan-path
title: A committed test names a gitignored local directory as the evidence for its claims about a published work
status: open
importance: low
importance_why: The citation resolves only in the maintainer's own checkout, so any other clone reading the test finds a pointer it cannot follow — and the page-scan claims are exactly the ones a reader would most want to check.
effort: S
kind: docs
area: fit-ingest, tests/metrics/test_worked_examples.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.3, review follow-up)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-committed-test-cites-a-gitignored-scan-path.md] Cite the Banister pages by number rather than by gitignored screenshot filename"
context:
  - tests/metrics/test_worked_examples.py
  - src/fitdocs/metrics/sources.py
  - .gitignore
blocked_by: []
---

## What

`tests/metrics/test_worked_examples.py` cites its primary evidence as a
screenshot inside
`bannister_physiological_testing_of_the_high_performance_athlete/`, a directory
excluded by `.gitignore`. The file is committed; the evidence it names is not,
and cannot be — the scans are copyrighted material that the data-root contract
keeps out of this repo.

A reader in any other checkout follows the pointer and finds nothing.

## Why it matters

Low, because the claims themselves are correct and independently re-verifiable
from the citation records — `BANISTER_1991` in `src/fitdocs/metrics/sources.py`
carries authors, year, work and a page locator, which is what a reader actually
needs to obtain the pages.

It matters slightly because these are the highest-value claims in the file to
audit. The test asserts what a published figure caption prints and that the
caption contradicts the chapter's own equation — the kind of statement a
sceptical reader will want to check first, and the kind this branch has
repeatedly found to be wrong. Pointing that reader at an unresolvable path is
the least helpful place for a dead reference.

There is also a small ratchet risk: a filename is a fact that can go stale
silently. The task 12.3 review found the cited screenshot was the **wrong**
one — it named the file holding pp. 410-411 as the source for a pp. 408-409
claim. Nothing in the suite could have caught that, because nothing in the
suite can see the directory.

## Evidence

At `ab1038d` plus the uncommitted task 12.3 work:

- `tests/metrics/test_worked_examples.py` — module docstring citing
  `bannister_physiological_testing_of_the_high_performance_athlete/Screenshot
  2026-07-27 at 22.42.32.png` as the read of "pp. 408-409".
- `.gitignore:41` excludes that directory.
- The reviewer opened the scans and established the filename was wrong: that
  screenshot is pp. 410-411; pp. 408-409 are in
  `Screenshot 2026-07-27 at 22.42.24.png`. The filename is being corrected as
  part of the task-12.3 remediation, but the underlying "cite a local,
  unshareable path" pattern is not.

## How to pick it up

1. Open `tests/metrics/test_worked_examples.py` and find every reference to the
   scan directory.
2. Replace each with the citable form: the work, the page, and the figure —
   e.g. "Banister (1991), p. 409, Fig. 9.5" — which resolves for anyone holding
   the book and matches how `BANISTER_1991`'s own `locator` is written.
3. If a pointer to the local scans is genuinely useful for the maintainer, put
   it somewhere that is honest about being machine-local rather than inside a
   committed test — `docs/reference/banister-trimp-primary-sources.md` already
   plays that role and is the natural home.
4. Check the same pattern elsewhere: `grep -rn 'bannister_physiological' tests/ src/ docs/`.

Done looks like: every evidence citation in a committed file resolves for a
reader who has the cited work, without needing this machine's filesystem.

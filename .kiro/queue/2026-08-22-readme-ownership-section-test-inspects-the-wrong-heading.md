---
id: 2026-08-22-readme-ownership-section-test-inspects-the-wrong-heading
title: The README ownership-section test inspects the wrong heading, and the canonical contract link is unpinned as a result
status: open
importance: medium
importance_why: The `## Ownership` section the test names is never actually checked; the only reason any README contract link is pinned at all is a substring accident, so the two links can silently diverge and one can go stale unnoticed.
effort: S
kind: bug
area: tests/test_ownership_contract.py, wiki-contract
created: 2026-08-22
surfaced_by: kiro-review of chore/repo-rename (reviewer designed mutations the implementer had not)
pinned_at: 29604fc
resume_command: "do: fix tests/test_ownership_contract.py's section lookup so it matches the `## Ownership` heading rather than the `### Ownership of the locations the inbox uses` subsection, then pin both README contract links independently"
context:
  - tests/test_ownership_contract.py
  - README.md
  - src/fitdocs/declaration.py
blocked_by: []
---

## What

`tests/test_ownership_contract.py:176` locates the section under test with
`readme.index("## Ownership")`. That substring matches **`### Ownership of the
locations the inbox uses`** at `README.md:241` before it reaches the real
`## Ownership` heading at `README.md:252` — `###` contains `##`. So the
computed `ownership_section` is the *Inbox* subsection, and the section the
test is named for is never inspected.

Measured during the review of `chore/repo-rename`, by mutation rather than by
reading:

- Mutating `README.md:245` (the contract link **inside the Inbox
  subsection**) to the old repository name reds
  `test_ownership_contract.py:180`. That is the only reason that line is
  pinned — an accident of which heading the index landed on.
- Mutating `README.md:257` (the contract link in the **real `## Ownership`
  section**, the canonical published one) leaves the full suite green:
  4176 passed / 1 skipped.
- `grep -n "## Ownership" README.md` → `241:### Ownership of the locations
  the inbox uses`, `252:## Ownership`.

The `assert CONTRACT_DOCUMENTATION_URL in readme` check is satisfied by line
245 alone, so it cannot distinguish the two links either.

## Why it matters

`README.md:257` is the canonical link to the published ownership contract —
the one the "Ownership" section exists to give. It is unpinned. The two README
contract links and `declaration.CONTRACT_DOCUMENTATION_URL` can drift apart
with the suite green, which is exactly how a shipped README ends up
advertising a dead contract URL. The 2026-08-22 repository rename had to move
both links; nothing mechanical would have caught missing one.

Note this is a *pin* defect, not a wrong assertion: the production values are
correct today. Per `change-protocol.md`, an assertion that cannot fail is
worse than a missing one, because it tells the next session the coverage
exists.

## How to pick it up

Anchor the section lookup on a line-start match (`re.search(r"^## Ownership$",
readme, re.M)`) or slice between headings, and assert the walk found something
non-trivial before comparing — the *vacuous walk* positive-control rule.

Then pin both links independently, and prove each with its own mutation:
changing line 245 alone must red one assertion, changing line 257 alone must
red a different one. A single `in readme` check over the whole file cannot
discriminate them and is not sufficient.

See also [[2026-08-22-readme-user-agent-example-is-unpinned]], which is the
same class of gap over the other README/source pair.

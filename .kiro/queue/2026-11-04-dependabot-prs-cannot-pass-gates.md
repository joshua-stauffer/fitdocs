---
id: 2026-11-04-dependabot-prs-cannot-pass-gates
title: Every Dependabot PR fails the gates job because the Dependabot secrets store is empty
status: open
importance: low
importance_why: It fails closed, so nothing unsafe lands, but a red check on a security bump reads as a real failure and blocks the normal merge path.
effort: S
kind: gap
area: distribution, .github/workflows/ci.yml, .kiro/steering/change-protocol.md
created: 2026-11-04
surfaced_by: diagnosing Dependabot PR #3's red gates job
pinned_at: 61c2ece1
resume_command: "do: decide how Dependabot pull requests get through the encumbered-content gate, then apply and document that choice (read .kiro/queue/2026-11-04-dependabot-prs-cannot-pass-gates.md first)"
context:
  - .github/workflows/ci.yml
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What
GitHub gives Dependabot-triggered workflow runs the Dependabot secrets store, not
the Actions store. `FITDOCS_FORBIDDEN_STRINGS_CONTENT` is only in the Actions
store, so the `gates` job in `ci.yml` stops at its write step on every Dependabot
pull request, before any test runs. The comment in `ci.yml` names forks as the
no-secret case and does not mention Dependabot.

## Why it matters
Nothing unsafe can land this way, because the gate fails closed as designed. But
every Dependabot pull request shows a red `gates` check that says nothing about
its change, and its fix cannot merge by the normal path. On PR #3 this was first
misread as a test failure. Each case also needs a hand-made replacement branch.

## Evidence
- `gh run view 41260585169 --log-failed` (PR #3, a bump of
  `pypa/gh-action-pypi-publish`): `##[error]gate_not_run:
  FITDOCS_FORBIDDEN_STRINGS_CONTENT secret is not set; the encumbered-content gate
  cannot run`. Its 3.12 and 3.13 jobs passed.
- `gh api repos/:owner/:repo/dependabot/secrets --jq '.secrets[].name'` prints
  nothing; `gh api repos/:owner/:repo/actions/secrets --jq '.secrets[].name'`
  prints `FITDOCS_FORBIDDEN_STRINGS_CONTENT`.
- `.github/workflows/ci.yml:25-26` says "a fork PR stops `gates` at the write step";
  `:82-85` is the check that exits.

## How to pick it up
1. Read the header comment and the write step in `ci.yml`, and take the maintainer's
   answer to the open question below.
2. Apply that choice and correct the `ci.yml:25-26` comment so it names Dependabot.
3. Done means the next Dependabot pull request either passes `gates` for real, or
   the documented path says plainly why it cannot and what to do instead.

## Open questions
Which path should Dependabot pull requests take? This is the maintainer's call,
because the first option changes who can read the match data:
- Add the same secret to the Dependabot store with `gh secret set
  FITDOCS_FORBIDDEN_STRINGS_CONTENT --app dependabot`. The gate then runs for real,
  and Dependabot-triggered runs can read the match data.
- Keep the store empty and land each bump from a maintainer branch, as was done for
  PR #3, and write that path down in `change-protocol.md`.

Skipping the gate for Dependabot is not an option: the repository is public and the
gate exists to stop encumbered content reaching it.

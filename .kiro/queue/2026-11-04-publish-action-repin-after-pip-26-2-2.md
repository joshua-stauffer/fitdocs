---
id: 2026-11-04-publish-action-repin-after-pip-26-2-2
title: Re-pin the publish action once a release after v1.14.3 ships pip 26.2.2
status: open
importance: medium
importance_why: The pinned action image reportedly still carries the revoked CA's root in its pip bundle, and nothing will announce the fix because the repo has no dependabot.yml.
effort: S
kind: chore
area: distribution, .github/workflows/release.yml
created: 2026-11-04
surfaced_by: review of chore/pypi-publish-1.14.3
pinned_at: 61c2ece1
resume_command: "do: run `gh api repos/pypa/gh-action-pypi-publish/releases/latest --jq .tag_name`; if it is newer than v1.14.3 and carries pip >= 26.2.2, re-pin both publish steps in .github/workflows/release.yml and update the pin comment (read .kiro/queue/2026-11-04-publish-action-repin-after-pip-26-2-2.md first)"
context:
  - .github/workflows/release.yml
  - docs/releasing.md
  - tests/test_release_workflow.py
blocked_by: []
---

## What
`pypa/gh-action-pypi-publish` v1.14.3 resolves the repository's Dependabot alert
GHSA-5xjx-3w67-w9x9 and is the latest release. A later upstream change bumps the
action's image to pip 26.2.2, which is merged but not released. When it ships,
this repository should move to it.

## Why it matters
The revoked root reportedly remains in the bundle of the pip inside the image.
The publish path reportedly does not use pip, so this is residual risk rather
than a known fault. The risk of waiting is that nobody hears about the release:
no alert covers it, and with no `.github/dependabot.yml` no version-update pull
request will open either.

## Evidence
Checked on 2026-11-04:
- `gh api repos/pypa/gh-action-pypi-publish/compare/v1.14.3...unstable/v1` is
  ahead by 2 commits: "bump to pip 26.2.2" and "Merge pull request #431 from
  esoteric-ephemera/pip-26.2.2".
- `gh api repos/pypa/gh-action-pypi-publish/releases/latest --jq .tag_name`
  prints `v1.14.3`.
- `.github/dependabot.yml` does not exist.

Reported by a reviewer subagent, not re-checked by the session that wrote this
item:
- the published v1.14.3 image holds pip 26.2, whose vendored bundle still has all
  four emSign roots;
- the Python security notice (discuss.python.org/t/109576) asks for pip >= 26.2.2;
- none of `twine-upload.sh`, `oidc-exchange.py`, `attestations.py`, `print-hash.py`
  and `print-pkg-names.py` in the action references pip.

## How to pick it up
1. Run the command in `resume_command`. If the latest release is still v1.14.3,
   stop; there is nothing to do yet.
2. Read the new release's notes and confirm it carries pip >= 26.2.2. Confirm that
   every `with:` input of the two publish steps in `release.yml` is still declared
   in that tag's `action.yml`.
3. Change both `uses:` lines, and re-run the two `gh api` commands the comment above
   the first publish step names, so the comment states what they print. The SHA
   there is the annotated tag object's, not the commit's.
4. Run `uv run pytest tests/test_release_workflow.py tests/test_specs_workflow.py -q`,
   then land it from a normal branch, since a Dependabot-triggered run cannot pass
   `gates`. Done means both uses name the new tag and branch CI is green.

## Open questions
Should the repository add a `.github/dependabot.yml` for GitHub Actions version
updates, so that releases like this one are announced? Each pull request it opens
would hit `2026-11-04-dependabot-prs-cannot-pass-gates`, so decide the two together.

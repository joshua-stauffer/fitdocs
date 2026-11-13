---
id: 2026-11-13-strava-brand-phrase-dropped-from-site
title: The website no longer says "Compatible with Strava", but strava-publish Requirement 16.4–16.5 and two test files still require it
status: open
importance: medium
importance_why: A spec requirement now contradicts the published site, and the next session to touch the Strava docs will reintroduce the phrase or ask again.
effort: S
kind: inconsistency
area: strava-publish, website/content, docs/connectors.md, CHANGELOG.md, tests/connectors
created: 2026-11-13
surfaced_by: maintainer review of PR #5 (site copy for the new connectors)
pinned_at: 29fe6bdd
resume_command: "do: ask the maintainer whether the 2026-11-13 decision to drop \"Compatible with Strava\" covers docs/connectors.md and CHANGELOG.md too, then amend strava-publish Requirement 16.4–16.5 to match and update or delete the pins in tests/connectors/test_strava_docs.py and tests/connectors/test_strava_changelog.py [queue: .kiro/queue/2026-11-13-strava-brand-phrase-dropped-from-site.md]"
context:
  - .kiro/specs/strava-publish/requirements.md
  - docs/connectors.md
  - docs/relay.md
  - CHANGELOG.md
  - tests/connectors/test_strava_docs.py
  - tests/connectors/test_strava_changelog.py
  - website/content/guides/connectors.md
blocked_by: []
---

## What
On 2026-11-13 the maintainer removed "Compatible with Strava" from the website (PR #5): "this language is ridiculous, and i won't accept it". The site now describes the `strava` connector in plain sentences.

These still require the phrase:

- `.kiro/specs/strava-publish/requirements.md`, Requirement 16.4: the brand phrase is "Compatible with Strava" in documentation.
- Requirement 16.5: the changelog and documentation describe the feature "only as compatible with Strava".
- `docs/relay.md:681-683` lists it as one of the operator's obligations.
- `tests/connectors/test_strava_docs.py:190`, through `_ALLOWED_BRAND`, pins it for `docs/connectors.md`.
- `tests/connectors/test_strava_changelog.py:28,106` pins it for `CHANGELOG.md`.

## Why it matters
The spec and the site disagree. A session that follows the spec puts the phrase back on the site, and one that follows the site removes it from `docs/` and turns the two test files red.

## Evidence
- `grep -rn "Compatible with Strava" website/content` printed nothing after PR #5's edit.
- `grep -rln "Compatible with Strava" tests .kiro/specs docs CHANGELOG.md` lists the files above.

## How to pick it up
1. Ask the maintainer whether the decision covers `docs/connectors.md` and `CHANGELOG.md`, or only the website.
2. Amend Requirement 16.4–16.5 to the answer. Record it as an amendment in the spec.
3. If `docs/` and the changelog drop the phrase too, delete the doc-binding pins, following the maintainer's 2026-11-03 rule that only code is under test. Edit `docs/relay.md`'s operator list to match.

Done when the spec, `docs/`, the changelog, the tests and the site agree.

## Open questions
Whether the hosted relay's Strava application needs the phrase anywhere else. That is the operator's call.

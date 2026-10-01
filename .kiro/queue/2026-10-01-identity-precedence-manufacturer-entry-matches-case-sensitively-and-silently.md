---
id: 2026-10-01-identity-precedence-manufacturer-entry-matches-case-sensitively-and-silently
title: A configured `original:Garmin` is accepted but matches no file, silently ranking Garmin files with every other original, below phone copies
status: open
importance: medium
importance_why: 'A one-letter case typo in [identity] precedence is accepted silently and renders pages from the wrong base file -- wrong output reaching documents with no error or warning.'
effort: S
kind: gap
area: activity-identity, src/fitdocs/identity/settings.py, src/fitdocs/identity/roles.py, docs/configuration.md
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-spec-requirements activity-identity [queue: .kiro/queue/2026-10-01-identity-precedence-manufacturer-entry-matches-case-sensitively-and-silently.md] Decide how an original:<manufacturer> entry that no file can match (wrong case, unknown name) is validated or reported"
context:
  - .kiro/specs/activity-identity/requirements.md
  - src/fitdocs/identity/settings.py
  - src/fitdocs/identity/roles.py
  - docs/configuration.md
blocked_by: []
---

## What
`[identity] precedence` accepts `original:<manufacturer>` for any non-empty name
other than `development` (Req 2.7). A file's manufacturer is the name the FIT
profile gives it, lowercase (`garmin`), and the match is exact. So
`original:Garmin` validates, matches no file, and the Garmin file falls to the
position of the bare `original` entry.

## Why it matters
With the list `["original:Garmin", "phone_copy"]` the Garmin original ranks
below the phone copy, and the page's base, its filename and its rendered data
come from the phone copy: the opposite of what the entry says. Nothing reports
it, because an entry that matches no file is not an error.

## Evidence
Reproduced at `fc5c06d` (`uv run python`): `load_identity_settings({"identity":
{"precedence": [text, "phone_copy"]}}, Path("fitdocs.toml"))`, then
`rank_key` over a Garmin original (`manufacturer="garmin"`) and a phone copy.
- `"original:Garmin"` -> accepted; positions Garmin `2`, phone copy `1`; best (base) is the phone copy.
- `"original:garmin"` -> accepted; positions Garmin `0`, phone copy `1`; best is the Garmin file.
- `src/fitdocs/identity/settings.py:89-111` `_entry` checks non-empty and not
  `development` only; `src/fitdocs/identity/roles.py:108-113` `_position` compares
  `PrecedenceEntry(ORIGINAL, member.manufacturer)` for equality.
- `docs/configuration.md:~198` says an `original:<manufacturer>` entry matches a
  file whose manufacturer is "exactly `<manufacturer>`" (documented, but
  nothing helps a user who capitalizes it).

## How to pick it up
1. Decide the behavior (Open questions), amend Req 2.6/2.7 if it changes the
   validation, then implement in `settings.py` / `roles.py` and the
   configuration doc.
2. Pin with the repro above in `tests/identity/test_settings.py` and the
   ranking in `tests/identity/test_roles.py`.

## Open questions
- Case-fold the manufacturer on both sides (then `Garmin` works), reject names
  that are not in the FIT profile's manufacturer vocabulary (a typo like
  `garmn` is then an error too), or warn at run time when a configured
  `original:<m>` entry matched no file of the run? The first fixes this
  slip; the others also catch misspellings but need the vocabulary or a run-time
  path to a warning.

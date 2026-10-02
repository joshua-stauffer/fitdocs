---
id: 2026-09-30-repo-wide-no-stryd-address-guard
title: No test enforces that the public repo names no Stryd web or service address
status: open
importance: medium
importance_why: A Stryd URL added anywhere reaches the public repo unnoticed (Stryd ToS decision); two specs require the rule and only a manual grep checks it.
effort: S
kind: gap
area: running-dynamics, channel-merge, tests/
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: add one repo-wide guard test over `git ls-files` asserting no tracked text file contains a Stryd web or service address"
context:
  - .kiro/specs/running-dynamics/requirements.md
  - .kiro/specs/running-dynamics/tasks.md
  - .kiro/specs/channel-merge/requirements.md
  - .kiro/steering/roadmap.md
  - tests/test_forbidden_strings.py
blocked_by: []
---

## What
running-dynamics Req 10.5 and channel-merge Req 9.3 both forbid a Stryd web or service address in the repository, and steering's Phase 8 section says the public repo documents no Stryd endpoint. Nothing enforces it; running-dynamics 10.5 was closed as a review grep. A guard drafted during running-dynamics 6.1 (tests/test_no_stryd_endpoint.py) was dropped in review, not landed.

## Why it matters
A contributor or agent can paste a Stryd endpoint into docs, specs, steering or code and the suite stays green. The repo is public and the Stryd ToS rule is the reason no Stryd connector ships.

## Evidence
- `grep -rniE "https?://[^ )]*stryd"` over every file running-dynamics changed printed nothing at 8b07b9f (review grep, recorded in running-dynamics tasks.md Implementation Notes, 6.1).
- channel-merge requirement: `.kiro/specs/channel-merge/requirements.md:223`.
- The reviewer's findings on the dropped draft, reported by the 6.1 reviewer subagent and not re-run here:
  - A scan limited by `_SCANNED_DIRS` and a suffix allow-list missed `.kiro/steering`, CONTRIBUTING.md, CLAUDE.md, scripts/, .github/ and `docs/*.html`.
  - Dropping `docs`, dropping `tests`, or removing `re.IGNORECASE` each left the suite green, because the non-vacuity pins were membership-only and every sample was lowercase.
  - `https?://[^ )]*stryd` spans newlines, so a `<https://example.com/x>` line followed by a line starting "Stryd pods ..." false-positived.
  - The samples joined into Stryd's real public host.

- 2026-10-02 (channel-merge 6.1, partial): `tests/compose/test_boundary.py::TestNoServiceAddress` now scans every `git ls-files` text file (floor 1300) with `https?://[^\s)]*stryd` case-insensitively; planting an address in src/, docs/ or .kiro/ reds it. Still missing against this item: the generic `[a-z0-9-]+\.stryd\.[a-z]{2,}` host pattern, per-scope non-vacuity (one file under each of src/ tests/ docs/ .kiro/steering/ .kiro/specs/ scripts/ .github/), `>`/`]`/quote delimiters in the URL class, and the newline negative sample. Extend that test rather than adding a second guard; see also 2026-10-02-no-service-address-guard-git-blind-spots.

## How to pick it up
1. Read `tests/test_forbidden_strings.py` for the repo's pattern of walking `git ls-files` (it deliberately ignores untracked files).
2. Write one guard:
   - Scan every tracked UTF-8 file, skipping binaries.
   - Use a URL pattern that cannot cross whitespace or delimiters (e.g. `https?://[^\s)>\]"'`]*stryd`), plus a generic `[a-z0-9-]+\.stryd\.[a-z]{2,}` host pattern with no named prefixes, matched case-insensitively.
   - Assert non-vacuity with a file-count floor plus at least one file under src/, tests/, docs/, .kiro/steering/, .kiro/specs/, scripts/ and .github/.
3. Build the positive samples from pieces: one capitalised, and one with a made-up subdomain and an uncommon TLD. None may join into a real Stryd host.
4. Add a negative sample: a non-Stryd URL line followed by a line starting with the word Stryd.
5. Done when planting a URL in each scope reds the guard, and dropping any scope, the case-insensitivity or the generic host alternative also reds it.

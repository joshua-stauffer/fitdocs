---
id: 2026-10-18-fit-sdk-license-terms-unreviewed
title: Review Garmin's FIT Protocol License against fitdocs' MIT release and public copy
status: open
importance: medium
importance_why: The one runtime dependency every document passes through carries a proprietary licence nobody has checked against the MIT release; cheap now, awkward after wider distribution.
effort: S
kind: research
area: pyproject.toml, src/fitdocs/ingest/decode.py, src/fitdocs/ingest/sets.py, website/content
created: 2026-10-18
surfaced_by: research for website/content/philosophy.md (fitness platform API lockdowns)
pinned_at: 0f6b965
resume_command: "do: Read the FIT Protocol License (garmin/fit-python-sdk LICENSE.txt) against fitdocs' MIT release and website copy; record a verdict in docs/reference/ and fix any 'open source FIT' wording"
context:
  - pyproject.toml
  - .kiro/steering/tech.md
  - src/fitdocs/ingest/decode.py
  - src/fitdocs/ingest/sets.py
  - website/content/
blocked_by: []
---

## What
fitdocs is MIT-licensed and depends at runtime on `garmin-fit-sdk`, which is
not under an open-source licence: it ships under Garmin's own FIT Protocol
License Agreement. Nobody has read that licence against how fitdocs is
built, distributed and described. The research found no evidence that
fitdocs vendors any SDK code, so this is a confirm-and-record task, not a
known defect. The phrases that need a reading are "internal business
purposes" (§1), "or any features or functionality of the Licensed
Technology" (§2c), and "any derivatives thereof … or that others have the
right to modify it" (§2d).

## Why it matters
- **A wrong claim on the public site:** the website philosophy page in
  progress argues for data ownership and open formats. The natural slip is
  to call FIT "open source", which it is not; "royalty-free, publicly
  documented, Garmin-licensed" is accurate.
- **The EU Data Act angle:** the Commission's Data Act FAQ v1.4
  (2026-01-22) says "Formats subject to licensing constraints are not
  considered 'commonly used'". That makes FIT's licence status relevant to
  any portability argument the site makes.
- **Cost grows with distribution:** if a clause did bite, finding out after
  a wider PyPI release is costlier than finding out now.

## Evidence
- **Licence text, fetched in this run:**
  - URL: `https://raw.githubusercontent.com/garmin/fit-python-sdk/main/LICENSE.txt`,
    338 lines, footer line 339 "Last updated: October 12, 2022".
  - §1 (lines 22–32): "non-exclusive, royalty-free, non-transferable,
    non-sublicensable, limited license to use the Licensed Technology for
    Licensee's internal business purposes, including to use the FIT
    protocol in any software created by Licensee".
  - §2c (lines 47–50): may not "distribute, publish, transfer or otherwise
    make available the Licensed Technology, or any features or
    functionality of the Licensed Technology, to any third party".
  - §2d (lines 52–57): may not "distribute the Licensed Technology or any
    derivatives thereof so that any part of it becomes subject to any
    license that requires that the Licensed Technology … be disclosed or
    distributed in source code form, or that others have the right to
    modify it".
  - §2f (lines 61–62): "benchmarking or a competitive analysis **of the
    Licensed Technology**". This clause is about benchmarking the SDK
    itself, not fitdocs' training benchmarks. A research note quoted it
    truncated; do not repeat the truncated form.
- **The installed wheel does not carry the licence:**
  `.venv/lib/python3.11/site-packages/garmin_fit_sdk-21.208.0.dist-info/METADATA`
  has no `License:` field, and the dist-info contains no licence file. Its
  only pointer is `Project-URL: Homepage, https://github.com/garmin/fit-python-sdk`.
- **fitdocs' side (`pinned_at` 0f6b965):**
  - `pyproject.toml:7` `license = "MIT"`; `:26` `"garmin-fit-sdk>=21.208.0"`.
  - Imports only, at `src/fitdocs/ingest/decode.py:30`
    (`from garmin_fit_sdk import Decoder, Stream`) and
    `src/fitdocs/ingest/sets.py:42` (`from garmin_fit_sdk import Profile`).
- **No vendored code was found.** At 0f6b965,
  `grep -rln -iE "copyright.*garmin|garmin international|FIT Protocol License" src/ tests/ scripts/`
  matched nothing (exit 1).
- **The sdist and wheel include only fitdocs' own files.**
  `[tool.hatch.build.targets.sdist] only-include` lists `pyproject.toml`,
  `README.md`, `LICENSE`, `CHANGELOG.md` and `src/fitdocs`; the wheel
  packages `src/fitdocs`.
- **Unverified in this run:** whether any README or website copy already
  calls FIT "open source". A grep of `README.md`, `website/content` and
  `docs` for "open source" near "FIT" found nothing, but
  `website/content/philosophy.md` is an untracked draft on a branch and
  was not on `main` at the time of the grep.

## How to pick it up
1. Read the full licence, especially §§1–3 and the termination section,
   from the URL above. Do not rely on the excerpts here.
2. Answer three questions in writing:
   - **Redistribution:** does declaring `garmin-fit-sdk` as a PyPI
     dependency (never vendoring it) count as "distribute" or "make
     available" under §2c?
   - **Derivative:** is fitdocs a "derivative" under §2d, given that it
     imports `Decoder`, `Stream` and `Profile`?
   - **Purpose:** does "internal business purposes" constrain an
     individual's non-commercial use of an MIT tool?
   Note where the answer needs counsel instead of a reading.
3. Record the verdict briefly, e.g. under `docs/reference/` or in the
   README's licence section. Grep `website/content/` and `README.md` for
   any "open source"/"open format" claim about FIT and correct it. Done
   means: the verdict is written down with the licence's "last updated"
   date, any wrong public wording is fixed, and the vendoring guard is
   noted as an invariant (no Garmin SDK files in `src/` or the sdist).

## Open questions
- Whether to state the dependency's licence to users, for example a line
  in README "Licence" saying the FIT SDK is licensed separately by
  Garmin. That is the maintainer's call.
- Whether to keep a decoder-independence escape hatch, such as tracking
  an independent decoder like `fitdecode`. That only matters if the
  reading in step 2 comes out adverse.

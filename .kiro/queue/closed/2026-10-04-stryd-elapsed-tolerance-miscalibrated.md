---
id: 2026-10-04-stryd-elapsed-tolerance-miscalibrated
title: ELAPSED_TOLERANCE_S (10 s) rejects 34 of 90 real Stryd↔HealthFit pairs; each becomes a duplicate page that check cannot see
status: done
importance: high
importance_why: Wrong output reaches the wiki (a duplicate page per rejected Stryd file, no channel donation), and fitdocs check is blind to it because it uses the same rule.
effort: M
kind: bug
area: activity-identity, src/fitdocs/identity/matching.py, docs/ownership-contract.md
created: 2026-10-04
surfaced_by: /kiro-validate-impl (real-data Stryd merge report)
pinned_at: 5bad3dc
resume_command: "/kiro-spec-requirements activity-identity [queue: .kiro/queue/2026-10-04-stryd-elapsed-tolerance-miscalibrated.md] Recalibrate Req 3.3 strict evidence on the full Stryd↔HealthFit population"
context:
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
  - src/fitdocs/identity/matching.py
  - src/fitdocs/identity/planning.py
  - docs/ownership-contract.md
  - .kiro/specs/channel-merge/design.md
blocked_by: []
---

## What
Strict evidence (Req 3.3, `matching.py:37` and `:137-142`) requires
`|Δelapsed| ≤ 10 s`. The value came from a sample whose largest delta was 9 s
(`TOLERANCE_SOURCES["ELAPSED_TOLERANCE_S"]`, design.md:902). The real
population is wider. Across the maintainer's 90 Stryd originals that have a
HealthFit page, every pair agrees on sport and on start to within 1 s. Even so,
34 of the 90 fail strict evidence on elapsed time alone. The Stryd file is
always the shorter one. Device evidence cannot apply, because the two files
come from different writers. Shifted evidence cannot apply either, because the
start delta is 0 h. Each of the 34 is therefore planned `Fresh` and gets a
duplicate page.

The documented distance calibration is also wrong. design.md:903,
`TOLERANCE_SOURCES` and `docs/ownership-contract.md:525` say "Stryd↔HealthFit
equal to 0.01 m". Measured deltas reach 1.23 m among matching pairs, and one
pair is 91.3 m apart.

## Why it matters
- Every rejected Stryd original produces a second page for a run that already
  has one. Its running-dynamics channels are never donated to the HealthFit
  page, which defeats channel-merge's purpose for Stryd.
- `duplicate_sets` (`planning.py:285`) links pages by the same
  `pair_evidence`. So `fitdocs check` reports none of these duplicates (Req 8.3
  does not catch them). The athlete has no in-tool way to find them.
- The cost grows with every Stryd run ingested after this.
- Req 3.11 (documentation states the measured source) is currently false.

## Evidence
Measurement, 2026-10-04, read-only, at 5bad3dc. A scratch script ran
fitdocs' own functions:
1. `fitdocs.ingest.parse_fit` on each Stryd original, then `session_key`.
2. `identity.pages.page_record` on the HealthFit page the staging manifest
   matched by start and sport. The page's recorded `source_*` keys are at
   doc_version 9.
3. `pair_evidence` on the two keys.

Output (aggregate only; no personal files enter the repo):
- 90 pairs, of which 56 match (all `strict`). The Stryd-only run is excluded.
- Misses: 34. None has `|Δstart| > 1 s`. One has `Δdistance > 5 m`.
- Δelapsed for the misses, HealthFit minus Stryd, in s: 10.03, 10.05, 10.26,
  10.29, 10.69, 10.76, 10.76, 10.90, 11.02, 11.12, 11.14, 11.45, 11.70,
  12.98, 14.38, 14.87, 15.15, 16.04, 16.23, 16.94, 18.20, 18.20, 20.11,
  20.35, 20.76, 23.80, 24.80, 28.63, 37.05, 38.32, 45.33, 72.02, 210.53,
  1685.20.
- Δelapsed for the matches runs from 1.12 to 9.999 s. That range is
  continuous with the misses, so the 10 s line cuts a single distribution and
  does not separate two populations.
- Δdistance overall: 89 of 90 pairs are ≤ 1.23 m. One pair is 91.32 m, with
  Δelapsed 28.6 s.
- Stryd writes elapsed as whole seconds.
- **Root cause, confirmed 2026-10-04.** The two writers end the session at
  different moments. The method was a garmin_fit_sdk dump of the session,
  event, lap and record messages of both files in each pair, over all 90
  pairs.
  - Stryd ends its session at the final timer `stop_all`. In 89 of 90 files,
    Stryd elapsed equals start → last timer stop to within 1 s.
  - HealthFit ends its session at the later `session stop_all` event, which
    is when the workout was ended on the watch. It writes one trailing record
    and a zero-length `timer start` at that instant.
  - So Δelapsed is how long the athlete stayed paused before pressing End,
    plus about 1 s. Δelapsed minus HealthFit's (session stop − last timer
    stop) falls within 0.1–2.0 s for 83 of 89 pairs; one HealthFit file has no
    session event.
  - The 1,685 s pair was paused 28 min before End. Stryd's last record and
    HealthFit's last timer stop share one second, and their distances agree to
    0.01 m.
  - The 210 s pair (a 3.7 h run with 13 pauses) agrees on every one of its 13
    pause starts to within 1 s. It then sat 3.5 min paused before End.
  - Elapsed time therefore measures athlete behaviour after the run, not
    session identity.
- **The 91 m pair is a different mechanism: Stryd cut the tail short.** The
  run ended without a pause. The Stryd file's last record is mid-stride at
  3.46 m/s and has no closing timer stop. HealthFit continues for 28 s more,
  and 28 s × ~3.4 m/s ≈ 91 m. The starts and both pause boundaries agree to
  within 1–2 s.
- **Start discriminates sessions.** Across all 2,561 pages of the real wiki
  that record a start, exactly one same-sport pair starts within 60 s of
  another, and it is a true duplicate (Δstart 0 s, device evidence).
- The suite stays green: `TZ=UTC uv run pytest -q` gave 8674 passed and
  8 skipped. No synthetic fixture can find a miscalibrated constant.

## How to pick it up
1. Re-measure the population. Write a scratch script outside the repo that
   follows the three steps above. Use `raw/stryd/manifest.json` in the data
   root (`tech.md` data-root contract), never copy files into this repo, and
   record the full Δelapsed and Δdistance distributions in `research.md`.
   Also re-measure Garmin↔HealthFit on the 2026-09-12 adoption set, so the
   new rule is not calibrated on Stryd alone.
2. (Done 2026-10-04; see Evidence.) Elapsed time is not an identity key.
   Each writer chooses differently when to end the session, and a file can
   lose its tail. The maintainer is provisionally OK with "same sport +
   start ≤ 1 s + distance agreement" and no elapsed term. The open point is the
   distance tolerance, which has to admit a truncated tail.
3. Amend Req 3.3 and 3.11 and design.md's tolerance table, then
   `TOLERANCE_SOURCES` and the ownership-contract table (pinned by
   `tests/identity/test_contract_docs.py`). Re-run the match-rule mutation
   suite (design.md "Revalidation Triggers"). Done means all 90 real pairs
   match. It also means the design's counter-examples still fail: two 10 k runs
   17 min apart, and the shifted-tier pairs.
4. Repair the data that already exists. For each duplicate page, decide
   whether it is merged by appending to `sources` and re-syncing (the
   garmin-adoption technique), or whether regeneration settles it once the
   rule changes (Req 6.7 stranded-page settle).

## Open questions
- Which rule should replace it? With `|Δstart| ≤ 1 s` and the same sport
  already required, elapsed time barely discriminates. Options:
  - (a) Strict on start plus distance, with elapsed only as an outer sanity
    bound, or not used at all. 89 of 90 pairs fall within 1.23 m, but the
    91 m pair would still miss.
  - (b) A relative elapsed bound. This still has to admit the 1685 s case.
  - (c) A source-pair-specific tier for an original plus a phone copy with an
    identical start.
  This is a maintainer decision on an approved requirement.
- Should `fitdocs check` report same-sport pages whose starts agree to within
  1 s but that fail every tier, as a "near-duplicate" finding? That would make
  the next miscalibration visible.

## Resolution
Done 2026-10-04 by activity-identity Amendment 1 (task 8.1): strict evidence is the same sport, starts within 1 s and distances within max(5 m, 20 % of the longer); elapsed is compared only when a distance is missing. CONTRACT_VERSION 7 -> 8. All 90 real pairs match. The open question about a "near-duplicate" check finding was not pursued: same-start pairs that fail every tier did not occur in the real data root.

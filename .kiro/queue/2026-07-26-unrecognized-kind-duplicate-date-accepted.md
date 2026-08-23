---
id: 2026-07-26-unrecognized-kind-duplicate-date-accepted
title: The benchmark parser rejects a duplicate measurement date for a recognized quantity but silently accepts it for an unrecognized one
status: open
importance: low
importance_why: Forward-compat data can carry a duplicate the parser would reject the moment that quantity becomes recognized, turning a working file into an unreadable one on upgrade.
effort: S
kind: inconsistency
area: athlete-benchmarks, src/fitdocs/benchmarks.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, round-3 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-unrecognized-kind-duplicate-date-accepted.md] Decide whether Req 2.7's duplicate rule reaches unrecognized quantities, and align parser and docs"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - src/fitdocs/benchmarks.py
  - tests/test_benchmarks.py
blocked_by: []
---

## What
Req 2.7 rejects two entries sharing discipline, quantity and measurement date.
`parse_benchmarks` enforces that via a `seen` set — but only *after* it has
`continue`d past any quantity name that is not a `BenchmarkKind`
(`src/fitdocs/benchmarks.py:337-342`, the Req 1.10 forward-compatibility skip).
So the same duplicate is rejected under `ftp_watts` and accepted under
`future_kind_w`.

## Why it matters
It is a latent upgrade hazard rather than a present defect. A file that
accumulates forward-compat entries under a quantity name this version does not
recognise can carry a duplicate date indefinitely; the version that *adds* that
quantity to `BenchmarkKind` starts rejecting the file outright, and the user's
profile becomes unreadable on upgrade with no action on their part.

The cost today is genuinely low — nothing writes unrecognized quantities, so
such content only arrives by hand-editing or from a newer fitdocs.

## Evidence
Executed by the round-3 reviewer subagent of task 3.2, not re-reproduced in the
session filing this item: an `athlete.toml` carrying two
`[[benchmarks.run.future_kind]]` entries both dated `2024-01-01` passes
`load_profile`, survives `save_profile`, and reloads cleanly — both entries
persist. The same shape under a recognized quantity raises
`BenchmarkError: benchmarks.run.<kind> has more than one entry measured on
2024-01-01`.

Code, at `84e5e56`: `src/fitdocs/benchmarks.py:337-342` — the
`except ValueError: continue` for an unrecognized `BenchmarkKind` runs before
the `key = (discipline, kind, measured_on)` / `if key in seen` check at
`:367-373`.

## How to pick it up
Read `parse_benchmarks` in `src/fitdocs/benchmarks.py`, specifically the
interaction between the Req 1.10 skip (`:337-342`) and the Req 2.7 duplicate
check (`:367-373`), then read both requirements in
`.kiro/specs/athlete-benchmarks/requirements.md`.

This is a decision before it is a fix. Either:
- **1.10 wins** — unrecognized content is not this version's business, and the
  asymmetry is correct. Then document it where 2.7 is stated, so the upgrade
  hazard is a known accepted risk rather than a surprise.
- **2.7 wins** — the duplicate rule is structural and should apply by key path
  regardless of whether the quantity is recognised. Then move the `seen` check
  before the skip, keyed on the raw quantity name.

Done when: the parser and the requirement text agree, and whichever way it goes
there is a test pinning the chosen behavior for an unrecognized quantity.

## Open questions
Which way to rule. Leaning 1.10, because rejecting on data this version cannot
interpret is the more surprising outcome — but that leaves the upgrade hazard,
which argues for at least a documented note in the schema-version guard.

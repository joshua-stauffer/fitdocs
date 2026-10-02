---
id: 2026-10-02-page-and-passes-can-compose-different-file-sets
title: A listed file archived after its page was rendered is composed by the load and benchmark passes but not by the page body, until fitdocs regen
status: open
importance: low
importance_why: Needs a ref that was unresolvable at render time and archived later; the result is a page whose Channel Sources section and a load score disagree about the file set. Unclear whether it is a defect.
effort: S
kind: research
area: channel-merge, src/fitdocs/compose/archive.py, src/fitdocs/sync.py, src/fitdocs/load/engine.py, src/fitdocs/performance/engine.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "/kiro-spec-design channel-merge [queue: .kiro/queue/2026-10-02-page-and-passes-can-compose-different-file-sets.md] Decide whether the load and benchmark passes should compose only the files the page body composed, or the listed files that resolve now"
context:
  - .kiro/specs/channel-merge/requirements.md
  - .kiro/specs/channel-merge/design.md
  - src/fitdocs/compose/archive.py
  - src/fitdocs/sync.py
  - src/fitdocs/load/engine.py
  - src/fitdocs/performance/engine.py
  - docs/ownership-contract.md
blocked_by: []
---

## What
UNCLEAR whether this is a design gap or the specified behaviour. A page's
`sources` can list a ref whose archive file is missing when the page is rendered
(the page task marks it unresolved, renders without it, and keeps the ref in
`sources`). If that file is archived later, the page body is unchanged until
`fitdocs regen`, but the training-load and benchmark-derivation passes call
`compose_listed`, which resolves each listed ref at call time, and so compose the
now-present file. The load score can then rest on channels the page does not
show.

## Why it matters
The channel-merge goal is that load is scored from the same activity the page
shows (Req 6 objective). In this window it is not. The cost is small and
self-heals on `regen`, but a reader of the page and its load region would see
two different file sets.

## Evidence
At 5c41759, by reading the code; the end-to-end sequence was not run.
- `src/fitdocs/sync.py:1894-1913`: a listed ref that does not resolve to an
  archived file is `unresolved` and is not parsed or composed; the page is
  rendered from the resolved members only (`_render_activity`, `:2211`).
- `src/fitdocs/compose/archive.py:20-39` `compose_listed` calls `sha_of_ref`
  and `path.is_file()` per ref when it runs and composes every file that is
  there.
- Callers: `src/fitdocs/load/engine.py:476`
  (`compose_listed(data_root, _listed_refs(markdown), base)`) and
  `src/fitdocs/performance/engine.py:373`.
- Requirement text: `.kiro/specs/channel-merge/requirements.md:186` (6.1,
  "the activity composed of the page's listed archived files") and `:188` (6.3,
  "compose from the listed files that resolve, as regeneration does").
  Read literally, 6.1 and 6.3 describe what the passes do; neither addresses a
  file that appears after the page was written.
- The scenario was reported by the validate-impl integration report (reviewer
  subagent), unverified in this run.

## How to pick it up
1. Decide the intent: the passes composing "the listed archived files that exist
   now" may be exactly what 6.1 and 6.3 mean, with `regen` as the remedy; if so,
   say it in `docs/ownership-contract.md` and close this item.
2. Otherwise choose the fix: the passes read the page's own Channel Sources
   section for the file set, or `check` reports a page whose listed files now
   resolve and its render lists fewer.
3. Reproduce first: sync a pair, move one archive file out, `regen`, move it
   back, then compare the page's Channel Sources with the load pass's composed
   channels.

## Open questions
Whether a late-appearing archive file is a case the athlete can actually
produce (a restored backup, a cloud-sync file arriving after the page).

---
id: 2026-10-13-apple-health-import-strictness-on-real-exports
title: "Apple Health import: four strictness choices made without a real export (whole-import failure on an excluded writer's odd unit, unrepaired character references, a shorter later export replacing a longer one, third-party apps excluded)"
status: open
importance: low
importance_why: Each choice is documented and fails safe (the import is refused or the older data stays in the archive), and only the optional maintainer smoke on a real export would show whether any of them bites.
effort: M
kind: research
area: apple-health-import, wellness-store
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (apple-health-import spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: after apple-health-import has landed, run its maintainer smoke (task 6.2*) on a real export, record which of the four choices in .kiro/queue/2026-10-13-apple-health-import-strictness-on-real-exports.md fire, and amend apple-health-import for the ones that do [queue: .kiro/queue/2026-10-13-apple-health-import-strictness-on-real-exports.md]"
context:
  - .kiro/specs/apple-health-import/design.md
  - .kiro/specs/apple-health-import/research.md
  - .kiro/specs/apple-health-import/requirements.md
  - .kiro/specs/apple-health-import/tasks.md
  - .kiro/specs/wellness-store/design.md
blocked_by: [apple-health-import]
---

## What

apple-health-import was specified with no real export to read, so four
decisions lean on assumptions. None is wrong as written; each could be too
strict or too coarse once a real export is imported.

- **(a) Unit validation runs before writer classification.** `DayReducer.add`
  validates every record's unit against its type's unit table as it streams;
  writers are classified only afterwards, in `snapshots()`. A record from a
  writer the policy would exclude anyway (another app writing heart-rate
  variability, say) that states an odd unit still fails the whole import, so
  an irrelevant app can block the athlete's own watch data.
- **(b) Escaped invalid character references and invalid UTF-8 are not
  repaired.** The defect filter removes raw control bytes, but a character
  reference to a control character such as `&#11;`, and invalid UTF-8, make
  expat reject the document; the import fails with a line number and is
  quarantined.
- **(c) A later export with a shorter history replaces an earlier one
  entirely.** Latest-entry supersession keeps one extract per source, so an
  export taken after, for example, moving to a new phone without a Health
  sync drops every day it no longer holds. An alternative is a per-day rule:
  the newest export wins on the days it holds and an older export fills the
  days it lacks.
- **(d) Third-party apps' Health values are excluded** (only the Apple Watch
  and the iPhone, plus body weight from every writer). Those values could
  become their own wellness sources later.

## Why it matters

(a) and (b) turn an export fitdocs could mostly read into a refused import
that is retried only with `--retry-quarantined` after a fix, and a multi-
minute failing parse is the cost of finding out. (c) silently narrows the
series to the newest export's coverage; the design documents it but the
alternative preserves data. (d) leaves a nightly signal (for example a sleep
app's HRV) in the export unread.

## Evidence

Read at `86cdf14` (design text; no code yet).

- (a) `.kiro/specs/apple-health-import/design.md:535-538` -- `add` validates;
  `snapshots()` classifies; `:547-552` -- validation covers "a quantity
  record's unit outside the type's unit table"; `:941` and `:1136-1139`
  (decision 15) -- the failure is whole-import, named, quarantined. The unit
  table is per type, not per writer (`:887-899`).
- (b) `.kiro/specs/apple-health-import/research.md:313-315` -- "Not handled:
  a character reference to a control character (`&#11;`) and invalid UTF-8;
  they fail the import with a line number and become a follow-up if seen";
  `research.md:54-57` -- expat rejects `&#11;` ("reference to invalid
  character number"); `design.md:1133-1135` decision 14 lists the three
  repairs that are made.
- (c) `.kiro/specs/apple-health-import/research.md:341-343` -- "A later export
  with a shorter history ... supersedes a longer one -- documented"; Req 6.1
  and 6.6 (`requirements.md:162` and `:167`) state it; the per-day
  alternative is not in the design.
- (d) `.kiro/specs/apple-health-import/design.md:44` -- Non-Goal "Importing
  other apps' values written into Apple Health, except weight"; `:1116-1118`
  (decision 6) -- "Other apps' values reach fitdocs through their own
  sources".
- `.kiro/specs/apple-health-import/tasks.md:550` -- the optional smoke task
  6.2*, the only step planned against a real export.

## How to pick it up

1. Run the smoke (6.2*) on the maintainer's real export first; the import
   report names a quarantine reason for (a) and (b) if either fires. Counts
   only; no data enters the repository.
2. For (a), move unit validation after classification (validate only records
   of a writer class the policy allows) or tally unreadable units from
   excluded writers as a note instead of a failure. For (b), add the two
   repairs to the defect filter only if the smoke shows them.
3. For (c), decide with the maintainer whether the per-day rule is worth a
   second supersession mode in wellness-store (`LATEST_ENTRY` keeps the
   winner only; the merge would need a day-level rule). For (d), a new source
   is a new format spec, not an amendment.

## Open questions

- (c) is a data-policy choice: is silently narrower coverage worse than the
  complexity of a day-level merge? Only the maintainer can say, and only
  after seeing an export that shrank.

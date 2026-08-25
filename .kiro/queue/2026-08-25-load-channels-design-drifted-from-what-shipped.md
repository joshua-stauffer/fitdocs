---
id: 2026-08-25-load-channels-design-drifted-from-what-shipped
title: load-channels' design.md no longer describes what shipped — four measured instances, including two undeclared dependency edges
status: open
importance: medium
importance_why: The design is the contract three sibling specs read; two of the four instances are undeclared dependency edges, and one makes a claim in the design measurably false.
effort: S
kind: docs
area: load-channels, .kiro/specs/load-channels/design.md
created: 2026-08-25
surfaced_by: /kiro-validate-impl load-channels (design-alignment and boundary audit; F1/F2/F3/F5 verified by the parent session)
pinned_at: 8645f44
resume_command: "do: reconcile .kiro/specs/load-channels/design.md with what shipped -- the two undeclared dependency edges (grade.py -> metrics.sources, sources.py -> fitdocs.citation), the Modified Files plan's now-false 'one test module' claim, and the Directory Structure comment that omits the provenance records"
context:
  - .kiro/specs/load-channels/design.md
  - src/fitdocs/load/channels/grade.py
  - src/fitdocs/load/channels/sources.py
  - tests/load/test_packaging.py
blocked_by: []
---

## What

The `load-channels` implementation is complete and its boundary audit passed —
no spillover, no downstream workarounds, no undeclared shared ownership. But
`design.md` describes the feature in four places that the shipped code
contradicts. Two are **undeclared dependency edges**, which matter because the
design's `### Allowed Dependencies` section is the contract three sibling specs
(`threshold-load`, `activity-qa-flags`, `training-load`) read to know what this
layer may reach.

None changes behaviour. All four are documentation drift.

### F1 — `grade.py` has an undeclared edge to `fitdocs.metrics.sources`

`src/fitdocs/load/channels/grade.py:83,113`:
```python
from fitdocs.metrics import sources as metrics_sources
ALTITUDE_SMOOTHING_WINDOW: Final[int] = metrics_sources.ALTITUDE_SMOOTHING_WINDOW.value
```
`design.md:868` declares this constant as a literal `= 10`, and `design.md:853`
lists GradeAdjustment's outbound dependencies as `ProvenanceRecord`,
`fitdocs.model.Samples` only. Critically, `design.md:99-105` scopes the
`fitdocs.metrics.sources` edge **explicitly to task 2.1, `weighting.py`**.
Task 2.2 introduced a second such edge and did not amend the design — even
though task 2.1 had set the precedent by amending it for exactly this reason
two commits earlier. The value resolves to `10`, so nothing computes
differently.

### F2 — `sources.py` re-exports types the design says it defines

`design.md:470` states, of ProvenanceRecord: *"**Dependencies**: none
outbound."* `design.md:476-497` gives `class VerificationStatus(StrEnum)` and
`class Citation` as `sources.py`'s own State Management.

Shipped `src/fitdocs/load/channels/sources.py:90-91`:
```python
from fitdocs.citation import Citation as Citation
from fitdocs.citation import VerificationStatus as VerificationStatus
```
`fitdocs.citation` appears nowhere in `design.md:92-118`'s Allowed
Dependencies. The move was fit-ingest's Amendment 1 task 8.2 and **pre-dates
this branch's base**; load-channels' design was simply never reconciled. This
one appears untracked anywhere — it is not covered by
`2026-07-28-reexport-test-module-prose-and-dead-param` (that item is about the
test module's docstring and a dead parameter) nor by
`2026-07-29-verificationstatus-lacks-two-needed-terms`.

### F3 — the Modified Files plan is incomplete, and one claim in it is now false

`design.md:285-287` names `tests/test_public_api.py` as *"the one test module a
task modifies rather than owns outright"*; `design.md:293` adds
`tests/load/test_settings.py`. Shipped, there is a **third**:
`tests/load/test_packaging.py`, a `training-load`-owned module with 8 lines
added to `_LOAD_MODULE_ALLOWLIST`. So the "one test module" claim reads false.

Also outside the plan: `tests/load/channels/test_shipped_metrics_untouched.py`
(task 5.4, new) and `tests/load/channels/test_sources_citation_reexport.py`
(pre-dates this branch).

### F5 — an internal inconsistency about the package surface

`design.md:257-259` (Directory Structure) says `__init__.py` re-exports *"the
vocabulary, the three compute entry points, and the HR model seam"*.
`design.md:1233-1235` (ChannelSurface) says the same **plus the provenance
records**. Shipped matches the latter — `Citation`, `VerificationStatus`,
`Divergence`, `CITATIONS`, `DIVERGENCES`, `BLOCKED_CITATIONS` are all in
`__all__`. The Directory Structure comment is the stale half.

Separately, `design.md:1176` says the settings reader *"adds one defaulted
field and one projection helper"*; shipped adds three private helpers
(`_setting_sufficiency`, `_setting_min_duration_s`, `_setting_coverage`), all
inside the single reader path — so the shape is as intended, the count is not.

## Why it matters

`### Allowed Dependencies` is not decoration: it is what a sibling spec reads
to decide whether a reach is sanctioned. Two edges now exist that it does not
list, and one of them (F1) was added by a task that had a worked precedent for
amending the design and did not follow it. The next session to add an edge has
no reason to think the section is authoritative.

F3's false claim is the sharper cost. A reader checking "which test modules
does this feature modify rather than own?" gets a specific, confident, wrong
answer — and `tests/load/test_packaging.py` belongs to another spec.

## Evidence

Verified by the parent session at `8645f44`:

```
$ sed -n '83p;113p' src/fitdocs/load/channels/grade.py
from fitdocs.metrics import sources as metrics_sources
ALTITUDE_SMOOTHING_WINDOW: Final[int] = metrics_sources.ALTITUDE_SMOOTHING_WINDOW.value

$ sed -n '88,92p' src/fitdocs/load/channels/sources.py
from fitdocs.citation import Citation as Citation
from fitdocs.citation import VerificationStatus as VerificationStatus

$ sed -n '470p' .kiro/specs/load-channels/design.md
**Dependencies**: none outbound. Inbound: `grade.py`, `power.py`,

$ sed -n '99,105p' .kiro/specs/load-channels/design.md
- `fitdocs.metrics.sources.weighting_for` (task 2.1, `weighting.py`): ...
```

F3 and F5 were measured by the validation audit against the shipped
`__all__` and the actual test-module set; the parent reproduced F1 and F2
directly.

## How to pick it up

1. Read `design.md:92-118` (Allowed Dependencies), `:253-294` (File Structure
   Plan), `:466-500` (ProvenanceRecord), `:853-870` (GradeAdjustment),
   `:1233-1235` (ChannelSurface).
2. Add the two edges to Allowed Dependencies with the same care task 2.1's
   amendment used — say what forces each and what it is *not* (F1's is a
   read-only constant lookup, not a second source of arithmetic).
3. Correct the Modified Files plan to name all three modified-not-owned test
   modules, and add the two unplanned test modules.
4. Fix the Directory Structure comment and the "one projection helper" count.
5. Spec edits are non-trivial per the change protocol — worktree, branch,
   merge-back — and the validation for `.kiro/specs/**` is
   `/kiro-spec-status load-channels` clean with `spec.json` approvals
   reflecting what actually happened. **A design edit after implementation may
   need re-approval**; check the phase before editing.

**Done** looks like: every dependency the shipped code has is listed in
Allowed Dependencies, and no claim in the File Structure Plan or the
Directory Structure comment is false.

## Open questions

- Does amending an approved `design.md` post-implementation require the
  phase's re-approval, or is a reconciliation edit that only records what
  shipped exempt? The spec's own history has both shapes — task 2.1 amended
  the design mid-implementation and Req 8.2/9.3 were amended in place with a
  declared correction. Worth settling once, since this item is the third
  design-reconciliation request on this spec.

---
id: 2026-10-19-changelog-omits-running-dynamics-plugin-api-additions
title: CHANGELOG [Unreleased] omits the plugin-API additions running-dynamics and the local-tz fix made (DeveloperChannel, Samples fields, record_developer_fields, local_offset)
status: open
importance: high
importance_why: Governed plugin-API additions will ship in 0.2 with no changelog entry unless fixed before the release cut; after the cut the record is wrong for good.
effort: S
kind: docs
area: CHANGELOG.md, docs/plugins.md, running-dynamics, fit-ingest
created: 2026-10-19
surfaced_by: 0.2 site-copy update (pages/contract fact-gathering subagent; DeveloperChannel verified by the session)
pinned_at: 90cd00b
resume_command: "do: before cutting 0.2, add a 'Plugin API (additive; no action needed)' CHANGELOG [Unreleased] entry for DeveloperChannel, the Samples running-dynamics fields, Activity.record_developer_fields and Activity.local_offset, after confirming each is part of the documented public surface in docs/plugins.md"
context:
  - CHANGELOG.md
  - docs/plugins.md
  - docs/compatibility.md
  - src/fitdocs/__init__.py
  - src/fitdocs/model.py
blocked_by: []
---

## What
The CHANGELOG convention requires an entry for any change to a governed
contract, and the plugin API is one. The `[Unreleased]` section names
`FileIdentity`, `Activity.file_identity`, `Provenance.undocumented_messages`
and `FileIdentity.file_type`. It does not name these, which also became
reachable from the package root or the model since v0.1.0:

- `DeveloperChannel`
- the twelve running-dynamics fields on `Samples`
- `Activity.record_developer_fields`
- `Activity.local_offset`

## Why it matters
A plugin author reading the 0.2 changelog doesn't learn about these names.
`docs/compatibility.md` promises additive changes are recorded. The 0.2 cut
turns `[Unreleased]` into the permanent 0.2.0 record.

## Evidence
- `src/fitdocs/__init__.py:50`, `:72` and `:93` export `DeveloperChannel`.
  `git show v0.1.0:src/fitdocs/__init__.py | grep -c DeveloperChannel`
  prints `0`.
- `docs/plugins.md:255` lists `DeveloperChannel` in the root public surface.
- `grep -n 'DeveloperChannel\|record_developer_fields\|local_offset' CHANGELOG.md`
  prints nothing at 90cd00b.
- Added by commit 1baef62 (running-dynamics 1.1: "twelve running-dynamics
  channels, DeveloperChannel and Activity.record_developer_fields on the
  model").
- `local_offset` was added by the local-tz fix merged at b741fba
  (fit-ingest Amendment 8).
- The `Samples` field names (`src/fitdocs/model.py:143-154`) and
  `Activity.local_offset` (`model.py:348-365`) were reported by a subagent
  and not re-read here.

## How to pick it up
1. Read `docs/plugins.md`, "public surface", to decide which of the four are
   documented public API. `local_offset` and `record_developer_fields` may
   be model fields that are not promised.
2. Add one additive Plugin API entry under `### Added`, in the style of the
   `FileIdentity` entry.
3. `tests/test_changelog*.py` may pin entries; run them.
4. Done when the entry is in `[Unreleased]` before the 0.2 version bump.

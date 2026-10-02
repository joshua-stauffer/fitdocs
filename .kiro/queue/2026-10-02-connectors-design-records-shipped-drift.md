---
id: 2026-10-02-connectors-design-records-shipped-drift
title: connectors design.md still describes eight things the shipped code does differently, including a self-contradiction about `pull --sync` with no connectors
status: open
importance: low
importance_why: No behaviour is wrong; the design is what intervals-connector and the next reviewer read as the contract, and each drift is a sentence they would otherwise "fix" the code back to.
effort: S
kind: inconsistency
area: connectors, .kiro/specs/connectors/design.md, .kiro/specs/connectors/tasks.md, docs/connectors.md
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-spec-design connectors [queue: .kiro/queue/2026-10-02-connectors-design-records-shipped-drift.md] Record the shipped drifts in one design-sync amendment"
context:
  - .kiro/specs/connectors/design.md
  - .kiro/specs/connectors/tasks.md
  - src/fitdocs/cli.py
  - docs/connectors.md
blocked_by: []
---

## What
Each line is a place where `.kiro/specs/connectors/design.md` and the shipped
code at this pin disagree; the code is the accepted behaviour (reviewed and
approved per task).

- [ ] **`_report_connect` does not exist.** design.md:311 lists it among
  `cli.py`'s functions; `connect_command` prints its outcome inline
  (`src/fitdocs/cli.py:921-960`).
- [ ] **`--dry-run` help text.** design.md:1442 still has `help="List and
  report what would be fetched; fetch and write nothing."`, which Req 6.9
  contradicts (a login instance's renewed token is persisted under a dry
  run). The shipped help was corrected (`cli.py:362-366`); the design's
  signature block was not.
- [ ] **Identity wiring.** design.md:1496-1512 says `_run_drain_passes` takes
  a required `precedence` keyword, with the `[identity]` load "staying ahead
  of the helper in `sync_command`". Shipped: the helper takes no
  `precedence` and loads `[identity]` and the hold record itself
  (`cli.py:482-512`), so `pull --sync` reads both twice (once in its own
  preflight). Kept deliberately (task 5.3 declared deviation): moving the
  load out reorders `sync`'s configuration errors.
- [ ] **`connect`'s unexpected-exception mapping.** The `connect` flow
  (design.md:1478-1487) names only `Connected` and `ConnectFailed`; the CLI
  also maps any other exception from `run_connect` -- including a
  `CredentialStoreError` from `store.save` -- to one
  `<ExceptionType>: <redacted message>` line and exit 1
  (`cli.py:911-919`), as the pull already does (design.md:1316).
- [ ] **No-connectors `pull --sync` self-contradiction.** design.md:1469-1473
  says `pull --sync --no-prompt` with no `[connectors]` table "produces
  exactly what `sync --no-prompt` does" *and* prints "No connectors are
  configured" -- which `sync` never prints (`cli.py:1117-1123`).
  `docs/connectors.md:146-148` repeats both halves. Say "drains exactly as
  `sync --no-prompt` does, after one extra line". The packaged skill makes
  the same claim ("With no connectors configured, this is exactly `fitdocs
  sync --no-prompt`", `src/fitdocs/skills/fitdocs-workouts/SKILL.md:31-32`),
  pinned verbatim by `tests/test_agent_skill.py:684-686`; for an agent the
  drain behaviour is what matters, so leaving the skill as is is defensible
  -- decide explicitly.
- [ ] **Overwrite wording omits `--sync`.** design.md:1672-1676 specifies the
  contract's `pull` bullet as "... never touches documents, the archive, the
  settings file or any source folder" -- false for `pull --sync`, whose
  drain writes documents and the archive. The published contract was
  corrected in task 8.1 (`docs/ownership-contract.md:742`, "Run as
  `fitdocs pull --sync`, it then drains the inbox ..."); the design was not.
  Add the `--sync` case.
- [ ] **File Structure Plan.** `tests/connectors/test_e2e.py` exists but is
  absent from the plan (`grep -n test_e2e .kiro/specs/connectors/design.md`
  returns nothing; plan at design.md:260-305).
- [ ] **tasks.md 1.2 pin wording.** `tasks.md:155` "each next step names the
  instance" -- design's next-step table (design.md:1361-1368) has `{name}`
  only in `rejected` and `challenge`. Reword the pin to "each next step that
  tells the athlete to re-run `connect` names the instance".

## Why it matters
intervals-connector's tasks cite this design for the CLI, the drain helper
and the error mapping; a sentence that disagrees with the code invites an
implementer to "restore" the design's version.

## Evidence
Every line reference above read at `ad985b3`. The drift list was compiled by
the feature-validation coverage reviewer and the task 5.1/5.3/7/8.1 reviewers;
each item was re-checked against the files in this session.

## How to pick it up
1. Open design.md at each cited line and the cited code side by side.
2. Write one dated "design sync" amendment note at the top of design.md (the
   repo's precedent is an in-place correction plus a `phase_note` in
   `spec.json`), then edit each passage to describe the shipped behaviour;
   apply the `docs/connectors.md:146-148` rewording in the same change.
3. No code changes. Done when every box is ticked and
   `uv run pytest tests/connectors -q` is still green (some docs tests read
   `docs/connectors.md`).

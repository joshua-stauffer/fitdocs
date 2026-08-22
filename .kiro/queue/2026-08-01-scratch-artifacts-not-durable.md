---
id: 2026-08-01-scratch-artifacts-not-durable
title: The purge's irreproducible scratch artifacts live under $TMPDIR and can vanish with no record
status: open
importance: high
importance_why: M0 and the match data cannot be regenerated after the rewrite; OS cleanup of /var/folders would strand tasks 5.5, 7.4 and 8.3 with no honest recovery.
effort: S
kind: risk
area: encumbered-content-purge, scripts/purge
created: 2026-08-01
surfaced_by: /kiro-impl encumbered-content-purge (tasks 1 and 2.3 review)
pinned_at: d835b7b
resume_command: "do: relocate the encumbered-content-purge scratch artifacts from $TMPDIR to a durable path outside the repository, and update the agent-log NOTE recording their location"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What
Every out-of-repository artifact this spec depends on lives under
`$TMPDIR/fitdocs-purge` (resolving to `/var/folders/...` on this machine),
because design.md specifies `$TMPDIR` for scratch. That directory is
per-user, per-boot-scoped and subject to OS periodic cleanup.

`tasks.md` names no location at all — it says only "a scratch path outside the
repository" — so nothing tracked records where these files are. The only
durable record is two lines in the shared agent log.

## Why it matters
Several of these artifacts are **consumed after the material they describe has
ceased to exist**:

- `M0.tsv` is taken against base commit `85b3985` and is read by task 8.3 to
  prove no golden document moved — after the rewrite has destroyed that commit.
- `forbidden-strings.tsv` was enumerated from material task 3.1 deletes; six
  later tasks consume it, and after 3.1 a missing entry cannot be re-derived
  from the tree, nor from history after Major 7.
- `evasion-acceptance.json` records the one-shot acceptance that can never be
  re-run.

Task 5.5's carry-over checklist and task 7.4's destruction gate both assume
these survive. If the directory is cleaned between sessions, the honest
outcome is to stop — and the dangerous outcome is a session regenerating a
plausible replacement from a post-deletion tree, which yields a file that
silently matches nothing.

## Evidence
Verified at `d835b7b`:

    $ ls $TMPDIR/fitdocs-purge/
    M0.tsv  M0.tsv.meta.json  evasion-acceptance.json
    forbidden-strings.tsv  forbidden-strings.tsv.meta.json
    training-load-spec-status-baseline.json

    $ grep -n 'scratch path outside the repository' \
        .kiro/specs/encumbered-content-purge/tasks.md
    (names no location)

design.md specifies `$TMPDIR` for scratch artifacts in its history-rewrite
section. Locating the directory during review required a filesystem-wide
search after the obvious paths came back empty.

## How to pick it up
1. `cat "$(git rev-parse --git-common-dir)/agent-log" | grep -i 'SCRATCH ARTIFACT'`
   — that NOTE records the current absolute path and the per-category counts.
2. Confirm the directory still exists and the six files are present. **If any
   are missing, stop and report** — do not regenerate from a post-deletion
   tree.
3. Move them somewhere durable outside the repository (e.g. `~/fitdocs-purge-scratch/`),
   update every consumer that hardcodes the path, and append a new agent-log
   NOTE recording the new location. Do not put the path in a tracked file —
   naming the scratch root in the published repository is itself a leak.
4. Consider whether design.md's `$TMPDIR` instruction should be amended, since
   it is what put them at risk.

Done means the artifacts sit somewhere that survives a reboot, and the log
records where.

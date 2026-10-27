---
id: 2026-10-27-killed-run-leaves-orphan-asset-temp-file
title: A run killed mid-write leaves a hidden .<name>.<hex>.tmp in workouts/assets/ that nothing ever removes
status: open
importance: low
importance_why: Rare (needs SIGTERM/SIGKILL/power loss inside one asset write) and harmless (the contract says it is safe to delete), but it accumulates and lives in the user's wiki.
effort: S
kind: gap
area: compact-chart-assets, src/fitdocs/docio.py, src/fitdocs/sync.py, docs/ownership-contract.md
created: 2026-10-27
surfaced_by: /kiro-impl compact-chart-assets (tasks 5.2 and 6.1 reviews)
pinned_at: 260c3ff8
resume_command: "do: decide whether sync should sweep stale '.<asset>.<hex>.tmp' files in workouts/assets/ on the next run; if so implement and update the ownership-contract sentence that says one can be left behind"
context:
  - src/fitdocs/docio.py
  - src/fitdocs/sync.py
  - docs/ownership-contract.md
  - .kiro/queue/2026-09-15-atomic-write-helper-copied-per-engine.md
blocked_by: []
---

## What
`docio.write_bytes_if_changed` writes to
`path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")`, then calls
`os.replace`. It removes the temp file only on a raised `BaseException`
(src/fitdocs/docio.py:183-195). src/fitdocs installs no signal handler, so a
SIGTERM, SIGKILL or power loss between `os.open` and `os.replace` leaves the
temp file behind. Stale-asset removal (`sync._remove_stale_assets`) deletes
only names the previous page linked, so it never sweeps these. The ownership
contract (docs/ownership-contract.md § What Regeneration Replaces and
Preserves) now says such a file can be left behind and is safe to delete.

## Why it matters
Leftover files collect in the user's `workouts/assets/` over time. The same
pattern exists in other writers (see the linked atomic-write item), so one
sweep policy could cover all of them.

## Evidence
docio.py:183-195 and the contract passage, both verified in this run. The
5.2 and 6.1 reviewers checked that nothing in src reads or lists these files:
every directory listing under `workouts/` is `glob("*.md")`.

## How to pick it up
1. Choose a policy: leave the files (as documented), or sweep `.*.tmp` files older than this run in `workouts/assets/` at the start of sync/regen.
2. If sweeping, add it to `_write_outputs`'s preconditions, test it with a planted temp file, and reword the contract sentence (task 6.1 pinned it in tests/test_asset_write_contract_docs.py).
</content>
</invoke>
<invoke name="Bash">
<parameter name="command">cd /Users/josh/code/fitdocs-compact-assets/.kiro/queue && for f in 2026-10-27-*; do echo "$f: $(grep -m1 '^id:' $f)"; done; tail -5 2026-07-28-mypy-perimeter-membership-unguarded.md
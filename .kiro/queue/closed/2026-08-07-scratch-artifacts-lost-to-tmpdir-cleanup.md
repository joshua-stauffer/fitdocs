---
id: 2026-08-07-scratch-artifacts-lost-to-tmpdir-cleanup
title: All ten out-of-repository purge artifacts were deleted by the OS temp cleaner, and several cannot be regenerated
status: done
importance: high
importance_why: The forbidden-string source is recovered and verified, but the pre-change manifest and three other artifacts are still missing and are consumed by Majors 6, 7 and 8; all remain reconstructable only while main holds the pre-deletion state.
effort: M
kind: bug
area: encumbered-content-purge, .kiro/steering/change-protocol.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (wrap-up validation after task 5.4)
pinned_at: 7d49c84
resume_command: "do: Decide how to restore or replace the lost out-of-repository purge artifacts before any further encumbered-content-purge work. Do NOT regenerate the forbidden-string source or the M0 manifest from the current tree -- both were captured before task 3.1's deletions and a regenerated copy would silently be a different artifact."
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
  - scripts/purge/build_sweep_inventory.py
  - tests/_forbidden_strings.py
blocked_by: []
---

## What

The purge's scratch root held ten artifacts that live deliberately outside the
repository, because they carry the material, the addresses and the tokens by
construction. The directory still exists and is now empty. The macOS temp
cleaner removed its contents; the directory's own timestamp is the day of the
cleanup.

Lost:

- the pre-change manifest and its metadata
- the forbidden-string source and its metadata
- the evasion-acceptance record
- the extracted rewrite-map rows and their metadata
- the sweep inventory and its metadata
- the spec-status baseline

## Why it matters

Two of these are **irreproducible in principle**, not merely inconvenient.

The **forbidden-string source** is the match data every token check consumes.
Its contents are recorded nowhere else, by design — that is the whole point of
keeping it out of the repository. Without it the standing guard from task 4.3
cannot run, and the verification runner from 5.4 refuses to start, which is the
posture 5.4 deliberately chose over skipping.

The **pre-change manifest** was captured in task 1, *before* task 3.1 deleted
the encumbered material. It is what tasks 3.11 and 8.3 compare golden-document
blob identifiers against to prove nothing rendered moved. A copy regenerated
from today's tree would be a manifest of the post-deletion state wearing the
name of the pre-deletion one — it would compare clean against itself and prove
nothing, which is worse than its absence.

The remaining artifacts are consumed after the adoption boundary by tasks 8.1
through 8.4, and the sweep inventory is the only one with a documented
byte-identical regeneration path.

## Evidence

The scratch root is empty; a directory listing shows only `.` and `..`. Running
the suite with the variable pointing at the now-missing source produces 21
failures, all of the form "names a path that does not exist" — the guard
failing loudly rather than skipping, which is task 4.3's intended behaviour and
is how the loss was noticed. With the variable unset the suite is green at 2757
passed, 21 skipped, so no committed work depends on the artifacts being present.

The earlier handoff recorded the stop condition explicitly: the artifacts were
verified present at that release, and a resuming session was told that if any
were gone it should stop rather than regenerate them from a post-deletion tree.

## How to pick it up

Do not regenerate anything first. Establish what still exists elsewhere: the
maintainer may hold the forbidden-string source outside this machine's temp
directory, and the material it derives from is on `main` and on the remote
until Major 6 lands, so the source is reconstructable *from those* in a way it
would not be after the rewrite. Check whether the pre-change manifest can be
rebuilt from `main`'s tip, which still carries the pre-deletion state — that is
a genuine reconstruction rather than a rename, but it needs verifying rather
than assuming.

Then fix the durability: an artifact whose loss blocks a one-shot irreversible
operation should not live somewhere an OS cleaner can reach.

Done when every artifact Majors 6 to 8 consume either exists again with its
provenance established, or has been explicitly written off with the consequence
recorded.

## Progress, 2026-08-07

**The forbidden-string source is recovered and verified.** The maintainer
supplied the token values; the removed paths were derived mechanically from the
branch diff and from the removed-path tuple the tree-removal test holds
literally, rather than from memory.

It now lives at `~/.fitdocs-purge/forbidden-strings.tsv`, outside both the
repository and the temp directory that was cleaned. Export
`FITDOCS_FORBIDDEN_STRINGS` to that path.

The reconstruction is verified, not assumed. The standing guard's exemption
table is keyed by `(path, category, index)` across 24 triples in 13 files, so
both the values *and their order* are constrained. Reconciling a live scan
against that table gives **24 live, 24 table, 0 stale, 0 uncovered** — the same
measurement task 5.4's reviewer made against the original. Two earlier
candidates were rejected by this check: one had four surplus path entries and
transposed two tokens; the next was two values short, which a green suite hid
because a stale exemption still passes. The full suite is back to 2777 passed,
1 skipped, with the liveness test executing rather than skipping.

Order matters and is recorded in the file's own header, because a reordered
source silently re-points every exemption.

## Still missing

The pre-change manifest and its metadata, the evasion-acceptance record, the
extracted rewrite-map rows and their metadata, the sweep inventory and its
metadata, and the spec-status baseline.

All are reconstructable, and the tools survive: `manifest.py`,
`rewrite_map.py`, `build_sweep_inventory.py` and `fingerprints.py` are all
present. The digest set `tests/_content_fingerprints.py` — the one the notes
say can never be regenerated once the material is deleted — is in-repo and
safe.

## Open questions

Whether a reconstructed forbidden-string source is acceptable evidence for the
one-shot acceptance run, or whether the evasion acceptance needs re-running
against it. The evasion record was itself an acceptance artifact and is also
gone; the digest set it was built from survives, so re-running is possible.

Whether the pre-change manifest rebuilt from `main`'s tip is genuinely the
artifact task 1 captured. The discriminating check is that it must *contain the
deleted paths* — a manifest that does not is a post-deletion manifest wearing
the wrong name, and would compare clean against itself while proving nothing.

## Resolution, 2026-08-09

**All five remaining artifacts are reconstructed, none of them from today's
tree.** Every one is derived from a pre-deletion commit still in history —
`85b3985` (the commit before Major 1, which is M0's base) and `660337f` (task
3.2's own commit). That derivation is possible only until the rewrite destroys
those commits.

They now live in `~/.fitdocs-purge/`, outside the temp root that was cleaned,
alongside the forbidden-string source recovered on 2026-08-07. Full provenance,
including the exact commands and the checks below, is at
`~/.fitdocs-purge/RECONSTRUCTION.md`.

Each artifact was verified rather than assumed:

- **Pre-change manifest** (`manifest-M0.tsv`, 549 rows). The discriminating
  check this item demanded: M0 carries **7 of 9** forbidden values, a control
  manifest at `HEAD` carries **0 of 9**. It contains the deleted paths, so it
  is the pre-deletion artifact and not a post-deletion one wearing the name.
- **Spec-status baseline**. Computed against `training-load`'s spec files as of
  `85b3985`, not today's. 14 requirements, 69 criteria, 24/24 tasks, six
  approvals true. It matches the same capture against today's tree, which is
  precisely what 6.2 asserts — and non-vacuously, since the artifact is from
  the pre-purge state and the comparison is against the post-purge state.
- **Sweep inventory** (`sweep-inventory-at-3.2.tsv`). Rebuilt inside a
  throwaway `git clone --no-local` at `660337f`, since the builder scans a live
  tree. **322 hits across 77 distinct files**, with
  `reproduction_pending_redaction: 6`. `docs/reference/history-rewrites.md:175`
  independently records 322 hits across 77 tracked files — both numbers match,
  from a source committed long before this reconstruction. A separate
  current-tree inventory (`sweep-inventory.tsv`, 145 hits, no reproduction
  disposition) is what 5.5's checklist asserts present; it is not a substitute
  for the 3.2 artifact.
- **Extracted prior-map rows** (174 rows). 187 lines = 13 header + 174 data;
  the `#` header, where the personal address lives, is correctly not extracted
  — zero email-shaped values in the output. The rows do carry 3 `token`
  values and 0 `path` values, because commit subjects mention the tokens; that
  is correct for an artifact that lives outside the repository by construction.
- **Evasion-acceptance record**. Re-run rather than recovered, which settles
  this item's open question in the affirmative. All four removed paths were
  still retrievable from `85b3985`; they were extracted outside the repository,
  the acceptance was re-run against the **real** material, and the material was
  then deleted. All 8 rows pass, negative control included.

**The open question about the reconstructed forbidden-string source is also
settled.** Recomputing `collect_fingerprints` over the recovered material with
the in-repo `SALT` reproduces the surviving digest set exactly — 434 of 434
fingerprints equal, window lengths equal, `SOURCE_COUNT` 3 = 3. The material
recovered from history is the same material task 2.4 fingerprinted.

Suite at `c79d9e2` with the source exported: **2873 passed, 1 skipped**, the
skip being the complementary liveness case that proves the checks ran live.

**Durability fixed**, which was the second half of this item: nothing the purge
depends on lives in `$TMPDIR` any more.

Two traps worth carrying forward, both recorded in `RECONSTRUCTION.md`:

1. `uv run --project <clone>` does **not** change cwd, so `python -m
   scripts.purge...` still resolves from the primary repo and re-scans the
   primary tree. It produced 145 hits identical to the current-tree run and
   read as a clean reproduction of a different commit. You must `cd` into the
   clone.
2. `purge fingerprints` mints a fresh random `SALT` per run, so a regenerated
   data module necessarily differs from the in-repo one. Never point
   `--data-module-out` at `tests/_content_fingerprints.py`; the in-repo module
   is authoritative and irreplaceable.

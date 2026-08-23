# History rewrites — provenance record for the encumbered-content-purge, part one of two

**2026-08-03.** This is the durable record of what `encumbered-content-purge`
removed from the fitdocs repository, why, and what removing it cost the
repository's own ability to check itself. Once this spec's history rewrite
lands, this document is what a later session has to go on for anything the
rewrite touched. *(In-place correction, task 9.2: this sentence originally
promised a forthcoming commit map alongside this document. Decision 6,
Amendment 1, 2026-08-17, retired the mechanism that would have produced
one; §3 states, once, that no such map exists or ever will, by
construction. The promise is cancelled here rather than left standing. §2's
own forthcoming-map promise, a separate clause, carries its own note where
it stood.)* Once that rewrite completes,
nothing below can be checked against the files it describes, because those
files will no longer exist reachable from any ref. Before that rewrite
completes, the writeup, both tables, and the deleted rewrite map remain
checkable against the blobs still reachable in this repository's history;
§4 states exactly which checks that covers. Part one, below, is written
before that rewrite runs. Part
two is appended in the post-rewrite commit, once the rewrite's own record,
the remaining stated positions, and the remote measurement exist. The counts
below were measured on 2026-08-01, not on the tip.

## 1. What was removed, when, why, and by which spec

On 2026-08-01, task 3.1 deleted the writeup, both extracted tables, and the
map recording the 2026-07-26 email rewrite (§2) from the working tree. The
methodology they described was evaluated inside `training-load` and
withdrawn from it on 2026-07-25, recorded there as Amendment 2. The
withdrawal's stated reason was that the methodology's redistribution terms
required the author's permission. That permission was never obtained. The
writeup, both tables, and their packaging entries were retained afterward as
a research record. This purge reverses that retention, per Requirement 4.
Retention was reversed because publishing the repository would publish the
material. The methodology's operative content also survives in symbolic
form inside a `training-load` planning document. No table-value scan
reaches that document. Redacting those sites, and erasing the third party's
identity elsewhere in the tree and in history, is separate work inside this
spec, under Requirements 1.2, 1.4, 1.6 and 11. That work was not complete
when this document was first committed; see the classified inventory below.

## 2. The 2026-07-26 email rewrite

On 2026-07-26, a separate history rewrite corrected every commit's author
and committer address across this repository's history, replacing personal
addresses with a non-personal one. That rewrite left backup refs under
`refs/original/`, pointing at the pre-rewrite tips. Leaving those refs
behind is the rewrite tool's default behavior. Those refs preserved the only
surviving copies of two implementation branches, `impl/athlete-benchmarks`
and `impl/training-load`. Neither branch's tip was an ancestor of `main`'s
tip at the time of that rewrite, measured directly against the pre-rewrite
commit identifiers the deleted map's own header recorded. Both branches'
commits later landed on `main` by rebase, under different commit
identifiers carrying the same subjects. Those backup refs were deleted
during this spec's design phase, before Major 3 began. Task 7.1 asserts
their absence again rather than relying on that prior deletion, per
Requirement 7.2. Deleting a ref does not delete the commit objects it
pointed at, and objects from both branches remained unreachable in this
repository's object database until 2026-08-09, when an unrelated accident
pruned every unreachable object in it — recorded in
`.kiro/queue/2026-08-09-shared-object-database-pruned-during-6-4-remediation.md`.
They are gone now, by that accident rather than by design. Neither the ref deletion nor task 7.1's
assertion would have removed them; the `--no-local` clone made in task 8.2
does, because that kind of clone copies only reachable objects — so the
purge's own outcome is unchanged either way, and this paragraph records the
distinction only because the reasoning above depends on which mechanism did
it. *(In-place correction, task 9.2: this sentence originally named "task
7.2" for that clone. The retired plan's task 7.2 was the one-shot in-place
history rewrite, which made its own clone; Amendment 1 replaced it before it
ran, and under the regenerated plan the reachable-only clone is made inside
task 8.2, the actual swap. Named by the
current task number so a later reader can locate the step that ran.)* That
earlier rewrite also produced a row-per-commit map from
pre-rewrite to post-rewrite commit identifiers, tracked in the working tree
until task 3.1 deleted it. This document replaces that map as the durable
record of the 2026-07-26 rewrite, per Requirement 5.4. The map's prose
header stated the maintainer's personal address in order to explain the
rewrite. This document does not restate it. The map's data rows, without
that header, are preserved outside the repository, as scratch evidence only.
*(In-place correction, task 9.2: the sentence originally here promised these
rows would join a forthcoming commit map covering both rewrites. Decision 6
(Amendment 1, 2026-08-17) means no such map can exist for the second
rewrite, so there is nothing for these rows to join; they remain scratch
evidence, cited but never a tracked file. See §3.)* The map
file no longer exists in the working tree, per Requirement 9.7.

## 3. The history replacement

On 2026-08-22, task 8.2 replaced this repository's history with a fresh,
parentless root commit, `c3d22016e3ca55fefa8b1da25a2e4f51d892e91e`. That
commit's tree, `bb5bab6d80c4fc275360600b8b1fb67c067d2061`, is identical to
the certified pre-replacement tip's tree — the tip was
`310f930b381892cd07acbf77f3179e369524c121`, certified clean by every guard
and oracle this spec built, at task 8.1. The mechanism carried forward no
existing commit: the fresh commit was forged directly from the certified
tree, a fresh `.git` was populated by a reachable-only clone of that single
commit, and the old `.git` — carrying every pre-replacement commit,
including the old root `32aed726eba17aaa517e56ab9e4717e7518c86c9` — was
moved out, whole, to an archive outside the working tree, never deleted
(Decision 7; the grounds for the mechanism itself are recorded in
`.kiro/specs/encumbered-content-purge/brief.md`'s amendment decision).

Two further rulings, taken after Decision 6 and before certification,
changed what the remote step does. Task 8.4 re-pointed `origin` at
`git@github.com:joshua-stauffer/fitdocs.git`, a repository the maintainer
supplied and that was measured that day as already existing and empty,
standing beside the still-live `fitdocs_oss` — so there was nothing to
recreate (Amendment 2, 2026-08-22). Amendment 2 calls this a
**rename**, `fitdocs_oss` → `fitdocs`, and that word is kept here for
continuity with the plan's naming, but it is inexact and stays inexact
throughout this record: nothing was renamed. Two repositories existed
side by side before the push, and both still do; "rename" describes which
URL the project now publishes under, not an operation performed on any
repository. `fitdocs_oss`, the repository `origin` no longer points at, was
**retained** rather than deleted (Amendment 3, same date). §7 records the
retention ruling and what it costs.

No pre-replacement commit is an ancestor of the fresh root, and nothing
maps a pre-replacement commit identifier to a post-replacement one, because
the fresh root was forged from a tree rather than derived commit-by-commit
from what came before (Decision 6, Amendment 1, 2026-08-17). Stated once:
every pre-replacement commit identifier is thereafter permanently
unresolvable in the fitdocs repository and its canonical remote, there
being no mapping by construction. That statement is scoped deliberately —
it is not a claim that no copy of the pre-replacement history exists
anywhere. The retained `fitdocs_oss` resolves those same identifiers
indefinitely, to anyone with access; §7 records that position rather than
letting this section's statement stand unqualified beside it.

## 4. What is no longer verifiable

Once task 3.1 deleted the material, and once the history replacement runs
(Major 8), several
things this repository could previously check become permanently
unverifiable from inside it. *(In-place correction, task 9.2: this sentence
and the one below originally said "Major 7" — the retired plan's rewrite
major. Under the regenerated plan Major 7 builds the machinery and Major 8
runs it; the property described here belongs to the completed replacement,
Major 8's event, not Major 7's.)* The guards' detection data — the value
matcher's digest set and window lengths — was generated from the real files
described in §1. That data can never again be checked against those files
once the replacement completes, because they will not exist reachable from any
ref. The evasion-acceptance run recorded below, from task 2.4, is the last
time this check is recorded against the real files. The check itself
remains possible today, run directly against the pre-deletion blobs still
reachable in this repository's history, until the history replacement makes
them unreachable. The purge's own probe sets, the certification and
identifier evidence gathered for the replacement (Major 8, task 8.1) —
`~/.fitdocs-purge/certification-8-1.txt` and
`~/.fitdocs-purge/identifiers-8-1.json` — and the retired in-place-rewrite
mechanism's own spec files — `~/.fitdocs-purge/plan-paths.tsv`
and `~/.fitdocs-purge/plan-content.tsv`, task 5.2's redaction plan output in
the `PathMatch`/content-match shape that module defines, and
`~/.fitdocs-purge/rules.json`, the retired task 7.2's `--replace-text` rule
set — are scratch artifacts kept outside this repository. *(In-place
correction, task 9.2: an earlier draft of this
sentence read the spec files as hypothetical — files the retired mechanism
"would have needed" — and struck them from the enumeration on that ground.
They are not hypothetical: Decision 6 (Amendment 1, 2026-08-17) retired the
mechanism before it *ran*, but the plan and rule files were already written
and still exist at the paths above, verified this task. No mailmap was ever
written for either mechanism — that half of the earlier draft's correction
was accurate and stands. A second draft of this sentence attributed an
evasion-acceptance artifact to Major 8 and pointed it at §7; that was also
wrong and is corrected here rather than repeated: the evasion-acceptance run
is task 2.4's, part of Major 2, dated 2026-08-01 — see the section below,
not §7. §7 names only the two task 8.4 identifier-probe artifacts,
`remote-8-4.txt` and `identifier-probes-8-4.tsv`; Major 8's certification
evidence is named directly above, not in §7.)* They
are destroyed with the material rather than retained (task 9.4, unrun as of
this commit). The out-of-repository
forbidden-string match-data file is not among them. It is retained
indefinitely. Its retention is what makes the opt-in detection §5 describes
possible at all.

## 5. What detection was given up

This section states losses that land when Major 4 merges, not the detection
posture at this commit. Once task 4.3's standing guard is built, an
ordinary `uv run pytest` run will no longer detect an identifying token by
default. It will skip instead. Detection will run only when the maintainer
supplies the out-of-repository match-data file, through a dedicated
environment variable. Once Major 4 merges, the contributor-documentation
banned-word loop and the two CLI-output token checks are retired entirely,
not re-based. Their subject is a calculator that no longer exists in any
form. The registry that would have listed it is provably empty on a fresh
import -- before any plugin discovery has run. For the contributor-doc
retirement that closes the gap: the standing guard (task 4.3) scans the same
corpus, the guide's tracked file content, and re-introducing either retired
needle there is caught. The CLI-output retirement is narrower and this is
stated rather than argued away: `fitdocs plugins` renders `discover()`'s
report, which reads installed distributions' entry points and, when a data
root resolves, local plugin files -- channels independent of what is
registered at import, and untouched by the fresh-import measurement above.
No guard in this repository scans rendered CLI output. An installed
third-party distribution's entry point can put any string, including an
identifying token, into that listing, and that surface -- a process's
captured stdout, never a tracked file, a tracked path name, or a built-
artifact member -- is outside every one of the standing guard's four scanned
surfaces. This is the loss the CLI-output retirement accepts. Once Major 4
merges, the guard that catches the withdrawn
calculator's class symbol, module path, and package name is retired in
favor of the standing token guard. The standing guard matches literal
strings only. The same code, reintroduced under a neutral name, will then
pass every guard this spec builds or retains, undetected. That gap already
exists for renamed re-introduction in general. This erasure widens it. A
separate initialism, whose expansion contains the third party's surname,
survives this purge. It is not one of the three identifying tokens
`requirements.md`'s Naming convention defines. No task in this spec's
Major 3 or Major 4 targets it for removal. This is a stated, deliberate
gap.

## 6. Stated positions (part two adds the remainder)

*(In-place correction, task 9.2: this section's opening paragraph originally
promised the remainder would be appended "once a commit map exists to state
positions against," naming "the one unresolvable pin" — the retired
per-pin scheme Decision 3 planned. Decision 6 (Amendment 1, 2026-08-17)
means no commit map ever exists, and Amendment 1 also replaced the per-pin
scheme with the uniform epoch convention every open pin now carries
identically. The remainder below states that convention's actual shape
rather than the retired one.)*

Two pieces of untracked state carry an identifying token across this purge,
per Requirement 11.13; their position was stated when this document was
first committed and is unchanged by the replacement:

The gitignored source workbooks at the repository root have filenames that
carry a token. Their position is accepted, recorded. Requirement 1.7
requires they stay on disk and out of the repository. The ignore rule that
excludes them carries no token of its own. They are never published.
Renaming a file the repository is forbidden to contain would buy nothing.

The shared agent log, kept under the repository's common git directory, is
never tracked or shipped. Its content carries tokens across several
historical entries. Its position is accepted, with a named hazard. It is
the append-only, multi-session record every session must read first and
coordinate through. Rewriting it would falsify what earlier sessions
actually recorded. The root symlink to this log is an sdist member that
extracts dangling today. Its content is therefore not currently archived by
a build. A future packaging change that follows symlinks could turn that
into a leak. This hazard is flagged here to the `distribution` spec.

**The pin convention (task 9.1, 2026-08-23) and its README documentation.**
Every open queue item's `pinned_at:` field was set to `c3d2201`, the
replacement root's short commit id, applied uniformly with no per-item
judgement (`scripts/purge/pins.py`; per Req 9.4 and 9.8, Amendment 1 — a
single documented convention, not a mapping). `.kiro/queue/README.md` §"The
epoch pin convention" documents it: a pin equal to `c3d2201` records that
the item's evidence predates the replacement and that its original pin is
permanently unresolvable in this repository, never a claim that `c3d2201`
is that original pin's post-replacement counterpart. Measured this task:
`c3d2201` resolves (`git cat-file -e c3d2201`) and `git log --oneline
c3d2201..HEAD` resolves against it — the property `/kiro-queue` depends on.
190 open items carry this pin; 188 were repaired to it and 2 were already
current, having been created after the replacement.

**Closed items' declared staleness (Req 9.5).** The 69 items under
`.kiro/queue/closed/` were left untouched rather than repaired. Their
`pinned_at:` fields record what was true when each item's evidence was
gathered, and closed items are outside `/kiro-queue`'s ranking scope, so
repairing them would falsify the record for no consumer that reads it. A
closed item's `pinned_at:` may therefore still name a pre-replacement
commit identifier, and that identifier is permanently unresolvable in this
repository. Measured at task 9.1: all 69 were checked against the replaced
repository and none resolves. The queue schema documentation's example pin
(`.kiro/queue/README.md`'s item-format block) carries the convention value,
`c3d2201`, rather than an invented or stale example.

**The tracked fixture filename (Req 9.6).** `tests/fixtures/report_baseline_faa6d09.py`
and the `_PRE_TASK_CLI_COMMIT = "faa6d09"` constant in
`tests/test_cli_drain_report.py` name a pre-replacement commit abbreviation
in a tracked filename and a tracked identifier. Both are retained, as
historical fact rather than a live pointer: the fixture records what
`src/fitdocs/cli.py::_report` looked like at that commit, immediately
before the inbox spec's task that added `_report_drain` changed it, and
renaming the file would not make the identifier it names resolvable. The
design's retired plan would have
had this fixture point to a forthcoming commit map; that pointer is
**cancelled**, because no map exists or ever will (§3). In its place,
`tests/test_cli_drain_report.py` now carries a one-line comment recording
that `faa6d09` is a pre-replacement identifier, permanently unresolvable in
this repository, retained as historical fact rather than a resolvable
pointer — the same position this paragraph states. The comment carries no
assertion, so nothing in the suite enforces that the two stay in agreement;
either could be edited without the other reddening.

**The unrepaired SHA-shaped token count (Req 9.5, 9.1).** Task 9.1 found 268
SHA-shaped prose tokens across 138 of the 190 open queue items that its
mechanical pin repair does not touch, because they sit inside prose,
evidence sections and resume commands that record what was true at a
moment — rewriting them would falsify the record rather than repair it.
Re-measured this task, via `scripts/purge/pins.py::count_other_identifier_tokens`
run over `.kiro/queue/*.md` minus `README.md`: the same figures, 268 tokens
across 138 files. This count is a shape, not a budget, per `tasks.md`'s
execution rules — it is expected to change as queue items close or are
written, and a later reader should re-run the same measurement rather than
trust this figure across time.

**The `.git` archive (Decision 7).** The pre-replacement `.git` directory
was moved, whole, to a location outside the working tree, described here by
role and never by its literal on-disk path — an expanded home-directory path
(`/Users/<name>/...`) is adjacent to the identity this record must not
carry, and unlike the tilde-form artifact locators this record uses
elsewhere (`~/.fitdocs-purge/...`, which names no user), the archive's actual
path is never given in either form, because naming it buys a reader nothing
the role description does not already say. It is retained, never published, and
its eventual deletion is a maintainer act outside this spec (`design.md`
Out of Boundary). It is not scratch: task 9.4's scratch-directory
destruction does not reach it.

**The carried untracked states (Req 11.13).** The two positions stated
above — the gitignored source workbooks and the shared agent log — are
unchanged by the replacement. Decision 7 guarantees the working directory
and its untracked material are never moved and never deleted by the swap,
and both were confirmed present, unmoved, after task 8.2's swap ran.

## 7. The remote

Task 8.4 re-pointed `origin` from `git@github.com:joshua-stauffer/fitdocs_oss.git`
to `git@github.com:joshua-stauffer/fitdocs.git` on 2026-08-22 and pushed the
single replacement commit. **Neither a deletion-and-recreation nor a
deletion occurred, and nothing was renamed.** Decision 6 originally planned
deletion and recreation; two later rulings each removed one half before task
8.4 ran. Amendment 2 (2026-08-22) found there was nothing to recreate: the
maintainer supplied `git@github.com:joshua-stauffer/fitdocs.git`, and it was
measured that day as already existing and empty, standing beside the
still-live `fitdocs_oss`. Amendment 2 calls re-pointing `origin` at that
pre-existing destination a **rename**, `fitdocs_oss` → `fitdocs`; the word is
kept here for continuity with the plan's naming, but `design.md`'s Amendment
3 makes it inexact and that caution travels with it here: two repositories
existed side by side before the push and both still do, so no rename
operation was performed on any repository — "rename" names which URL the
project now publishes under, nothing more. Amendment 3
(2026-08-22, after
Amendment 2, before task 8.1 certified anything) settled that `fitdocs_oss`,
the repository `origin` no longer points at, would be
**retained** rather than deleted, which made deletion moot. So: the
reconciliation action task 8.1 through 8.4 actually **required** was
re-pointing `origin` at the pre-existing, empty `fitdocs` and pushing to it,
measured rather than assumed (Req 8.1); deletion and
recreation were never required once those two rulings landed, and this
record does not name them as steps that ran.

**Retention's grounds and what it costs.** The only ground this record has
for the retention itself is the maintainer's ruling (Amendment 3): `design.md`
and `brief.md` state that `fitdocs_oss` is retained, not deleted, and
`fitdocs` becomes the canonical repository, without giving a further reason
the retention was chosen — this section states that plainly rather than
implying a rationale that is not on record. That retention keeps `fitdocs_oss` serving the removed
material, in full, at every pre-replacement commit, indefinitely — this is
what Amendment 3 narrowed Requirement 8's subject to exclude, not what it
achieves. Requirement 8's amended preamble states the exemption in full:
**"the remote" in Requirement 8's criteria means the canonical repository
only**, because after task 8.4 re-points `origin`, `fitdocs_oss` is no
repository's remote at all and the criteria never reach it. What that
exemption excludes is stated with it, not left implied: Requirement 8's
objective — removal holding "on GitHub and not only on my machine" — is met
for the canonical repository and **not** for GitHub as a whole, and the
honest completion claim is **"Requirement 8 is satisfied with respect to the
canonical repository"**, never a bare "the remote no longer serves it."

**Measured positions, dated 2026-08-22, task 8.4 (`~/.fitdocs-purge/remote-8-4.txt`,
`~/.fitdocs-purge/identifier-probes-8-4.tsv`).** Before the push: `fitdocs_oss`
was private, not a fork, 0 forks, 0 open PRs, 0 open issues. `fitdocs` (the
push destination) was private, not a fork, 0 forks, 0 open PRs, 0 open
issues, and carried 0 refs. After the push: a fresh clone taken from
`fitdocs` carries exactly one commit, root `c3d22016e3ca55fefa8b1da25a2e4f51d892e91e`,
tree `bb5bab6d80c4fc275360600b8b1fb67c067d2061` — identical to the certified
tip's tree. Every local ref matches the remote's at the same commit id in
both directions, and no ref exists on the remote that is not local.

Per-identifier probes, both repositories, both from `remote-8-4.txt` and the
full table at `~/.fitdocs-purge/identifier-probes-8-4.tsv`: a liveness
control confirmed the probe method live (the new root returned HTTP 200 on
`fitdocs` before any negative result was trusted). Against the **canonical**
repository, `fitdocs`: 0 of 19 pre-replacement identifiers served — the 7
sampled pre-replacement commits, including the old root
`32aed726eba17aaa517e56ab9e4717e7518c86c9` and the old tip
`310f930b381892cd07acbf77f3179e369524c121`, each returned HTTP 422
(unrecognised object id), and the 12 sampled blobs each returned HTTP 404.
Against the **retained** repository, `fitdocs_oss`: 7 of 8 sampled
identifiers were still served, HTTP 200 — expected and accepted under
Amendment 3, recorded here as measured fact rather than a reconciliation
failure. The eighth, the certified tip `310f930b381892cd07acbf77f3179e369524c121`,
returned 422 against `fitdocs_oss` for an unrelated reason stated in the
same evidence file: that commit was never pushed there, because
`fitdocs_oss`'s `origin/main` had already fallen behind local `main` before
this spec's history replacement ran.

**Stated plainly, so a later auditor does not have to infer it**: the
retained repository still serves the removed material, in full, and
Requirement 8 is satisfied with respect to the canonical repository — the
honest form of the completion claim, checkable against the probe table
above. Both repositories were measured private after the push (Req 8.7):
neither has been made public by this purge.

**The standing duty (Req 8.8), recorded as an obligation, not a
measurement.** `fitdocs_oss` must remain private for as long as it exists.
This is not discharged by the dated observation above that it *was* private
at the time of measurement — a future maintainer reading this record must
find the obligation, not only evidence that it once held. The reason: it
holds the removed material in full, and its privacy is the only thing
keeping that material unpublished; §3's "permanently unresolvable" statement
holds only inside the fitdocs repository and its canonical remote precisely
because `fitdocs_oss` is not covered by it. Any fork of `fitdocs_oss` would
be a second permanent copy of the removed material, held in another
account. GitHub's own documentation
(<https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks>,
fetched 2026-08-22 per `design.md`'s Amendment 3, which quotes it) states
that a private repository's forks are private and cannot be made public
independently of it, and that a private repository's forks are deleted when
the repository itself is deleted — a table row this document does not
restate verbatim. GitHub places the residual duty on the account holder:
"You are responsible for ensuring that people who have lost access to a
repository delete any confidential information or intellectual property."
Requirement 8 covers no fork case; this paragraph, not a criterion, is where
that duty is recorded.

## 8. Retirement of the replacement machinery

**What was removed.** On 2026-08-23, task 9.3 deleted `scripts/` in its
entirety — sixteen tracked files, measured this task by `git rm -r scripts/`:
the fourteen one-shot modules this task's own deletion list names
(`design.md` `#### MachineryRetirement` counts them as fourteen, without
naming them, and the enumerated deletion list in the tasks phase is itself
the Req 12.1 position): `scripts/purge/__init__.py`, `adopt.py`,
`build_sweep_inventory.py`, `fingerprints.py`, `manifest.py`, `pins.py`,
`plan.py`, `preflight.py`, `replace.py`, `replacements.py`,
`rewrite_map.py`, `rewrite.py`, `sweep.py`, `verify.py`), the CLI entry point
`scripts/purge/__main__.py`, and the parent package's own
`scripts/__init__.py`, whose docstring's subject was the sdist/wheel
packaging claim that `scripts/purge/` is excluded from both build targets
(now moot, since `scripts/` no longer exists to exclude); the module also
held a bare `from __future__ import annotations` import, nothing else.
Every one of those sixteen files had planning, executing, or verifying this
spec's history operation as its only purpose (Req 12.1): each module either
built or ran a step of the retired in-place rewrite or the fresh-root
replacement, was pure infrastructure (the two `__init__.py` files, the CLI
dispatcher) with no purpose independent of the modules it hosted, or was a
one-shot generator whose output is a retained guard's data and whose own
generating logic is irreproducible after task 3.1 deleted the source
material it read (`scripts/purge/fingerprints.py`, `design.md`'s Component →
file map: "generator; retired"), which is the authority its deletion rests on.

The same task deleted `tests/purge/` less three relocations — fifteen
further tracked files, measured by `git rm -r tests/purge/`:
`tests/purge/__init__.py` and fourteen test modules (`test_adopt.py`,
`test_cli.py`, `test_fingerprints.py`, `test_manifest.py`, `test_pins.py`,
`test_plan.py`, `test_preflight.py`, `test_replace_rehearsal.py`,
`test_replacements.py`, `test_rewrite_gate.py`,
`test_rewrite_map_extraction.py`, `test_sweep.py`, `test_tree_removal.py`,
`test_verify.py`). Each pinned a module or a step deleted alongside it in
this same change, so each had verifying the history operation as its only
purpose (Req 12.1).

`tests/purge/test_content_oracle.py`, `tests/purge/test_content_fingerprints_shape.py`
— `design.md` `#### MachineryRetirement` Phase R1's two named relocations —
and `tests/purge/test_provenance_record.py`, a third relocation this task
identified beyond the two `design.md` names, moved to `tests/test_content_oracle.py`,
`tests/test_content_fingerprints_shape.py` and `tests/test_provenance_record.py`
by `git mv` in this same task. The first two move because their subjects,
`tests/_content_oracle.py` and `tests/_content_fingerprints.py`, are
retained guards (Req 12.2) with no remaining tie to the deleted machinery.
The third moves for the same reason under a different name: its subject is
this document's own required-heading-and-body skeleton, and this document's
survival is commanded, not merely convenient — Req 12.3 ("the retirement
shall retain the provenance record ... and shall remove no record
Requirement 4 or Requirement 9 requires") and Req 9.1 (the repository shall
contain it). `tests/purge/test_provenance_record.py` was not in `design.md`'s
named relocation pair and is not named in `tasks.md`'s deletion list either;
it was never in either list's field of view. Deleting it alongside
`tests/purge/` — as an earlier version of this task did — would have removed
the repository's only automated pin over a document Req 12.3 requires kept,
which Req 12.1's "every deleted module has planning, executing or verifying
the history operation as its only purpose" does not license, because
verifying a permanently-retained deliverable is not verifying the history
operation. All three relocated modules were re-run after the move with a
recorded single-line mutation to their subject — `tests/_content_oracle.py`'s
`tokens()` body replaced with `return []`, `tests/_content_fingerprints.py`'s
`ENTROPY_FLOOR_BITS` changed from `96.0` to `50.0`, and
`docs/reference/history-rewrites.md` itself truncated to 0 bytes — observed
red, then reverted and confirmed green, so the move did not silence any of
the three. The extended `_REQUIRED_HEADINGS` tuple in the relocated
`tests/test_provenance_record.py` (§1 through §8, now including this
section) is task 9.3's own mechanical pin over its own Observable ("section
8 is populated"); deleting only this section's heading, leaving the
document otherwise intact, was also re-run and observed red, then reverted
and confirmed green.

`tests/test_forbidden_strings_source.py` — the source-liveness test module —
is also deleted by this task. Its deletion is not authorized by any
delegation in `tasks.md`'s execution rules (there is none); the source is
`design.md`, which states "the enumerated deletion list in the tasks phase
**is** the 12.1 position", and, for this module specifically, task 7.2's own
body: "The source-liveness module sits outside the Component → file map's
lists; it is claimed here and deleted at 9.3 under the deletion list the
design delegates to this plan" — task 7.2 re-scoped the module's era signal
and claimed its eventual deletion at the same time. Its subject was
verifying, via `git log --all -S<value>`, that this repository's own history
still carried each `token`-category match-data value before the
replacement, and that no such value could be found in history after the
replacement (the module's own docstring, before deletion, stated this as the
"liveness check for task 2.3's real, assembled source"). That subject cannot
exist after the replacement: the replacement produced a repository carrying
exactly one commit, and every commit since descends from that root, so
`git log --all -S<value>` has, by construction, no pre-replacement tree to
search, and the module's own pre-replacement/post-replacement
posture distinction — the entire reason it existed — has nothing left to
distinguish. The loss this retirement declares (Req 12.4) is stated in full
below, not left to be inferred from the deletion.

Two modules' *contents* — not the modules themselves — moved into surviving
guards before this task ran, at task 7.2 (`design.md`
`#### MachineryRetirement` Phase R0): the `_whitespace_tolerant_pattern`
helper and the notice/mark tip guard — its word-tuple constants, its
wrap-tolerant separator pattern, and its independent survivor counter —
moved out of `scripts/purge/replacements.py` and
`tests/purge/test_replacements.py` into `tests/_forbidden_strings.py` and
`tests/test_forbidden_strings.py` before `replacements.py` and
`test_replacements.py` were deleted here. Both source modules — the
retiring rules module and its test module — are themselves counted in this
task's own deletion count above: task 7.2 moved only these two named pieces
out of them, and everything each module still held afterward (the
six-invariant rule generator and its adjacency oracles, among the rest) was
this task's to delete, not to re-home.

**What each surviving guard still detects (Req 12.2).** `tests/_forbidden_strings.py`
paired with `tests/test_forbidden_strings.py` scans every tracked file's
working-tree content and path name for a supplied match-data value (token or
removed-path fragment), detecting a returning identifying token or a
returning removed-path fragment, opt-in through `FITDOCS_FORBIDDEN_STRINGS` —
gated on the maintainer supplying the match-data source, and skipped, named,
when it is not. The notice/mark tip guard re-homed into the same modules at
task 7.2 is a separate, **ungated** test: measured directly
(`uv run pytest tests/test_forbidden_strings.py::test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`
with `FITDOCS_FORBIDDEN_STRINGS` unset), it passes rather than skips,
detecting a returning copyright-notice/trademark phrase anywhere in the
tracked tree regardless of whether the maintainer has supplied anything —
ungatedness is one of the three properties `design.md`'s Phase R0 named as
having to survive the move intact, and this is that survival, measured
fresh on the post-retirement tree. `tests/_content_oracle.py`
paired with the relocated `tests/test_content_oracle.py` still tokenises,
canonicalises, windows, salted-digests, and scans arbitrary text for a
reproduced numeric value, independent of any purge module. `tests/_content_fingerprints.py`
paired with the relocated `tests/test_content_fingerprints_shape.py` still
pins that the one-shot-generated fingerprint and window-length data has not
been truncated or emptied. `tests/load/test_packaging.py` still runs the
value oracle over two real surfaces — every shipped `.py` source under
`src/fitdocs`, and the content of every regular member of the built sdist —
detecting a reproduced numeric table shipped in a package artifact. The
**wheel** is guarded differently, and this record states the difference rather
than implying a scan that does not run: `test_wheel_contains_no_stray_data_or_module_under_load`
inspects member *names* and asserts the `fitdocs/load/` module allowlist by
equality, detecting a reintroduced methodology module under any name. It runs
no oracle content scan over wheel members, and that module's own docstring
records the wheel content scan as retired. `tests/test_docs_guarantees.py` still
pins two shipped-documentation guarantee sentences against the concatenated
markdown corpus, independent of the purge — this module's own docstring
identifies them as the *inbox* spec's Req 6.6 (no configuration ever
deletes an inbox file) and Req 8.2 (fitdocs performs no watching or
scheduling of any kind); the bare numbers belong to that spec, not to
`encumbered-content-purge`, whose own Req 6.6 and Req 8.2 are unrelated
(quiescence and the fresh-clone criterion, respectively), and are qualified
here to keep this durable record from resolving to the wrong requirements.
This task re-ran the two Req 12.2 relocated modules' own recorded
single-line mutation against their subject module after the move —
`tests/_content_oracle.py`'s
`tokens()` mutation above, and `tests/_content_fingerprints.py`'s
`ENTROPY_FLOOR_BITS` mutation above — observed red, then reverted and
confirmed green. Re-running every other surviving guard's own recorded
mutation on the post-retirement tree, per guard, is task 9.4's job (`tasks.md`,
"Prove every surviving guard still fails, then destroy the scratch") and has
not run as of this commit.

**Verification capability given up (Req 12.4), stated rather than left
implicit.** This retirement removes the fitdocs repository's own ability to:

- Scan the full reachable history — every blob and path across every ref
  (`scripts/purge/plan.py::enumerate_blob_ids`, walking
  `git rev-list --objects --all`, and `scripts/purge/replacements.py`'s own
  `(blob_id, path)` enumeration over the same command) and every commit
  message (`scripts/purge/verify.py`, via `git log --all --format=%B`) — for
  a returning token, value, or removed path. No surviving module reads
  unreachable or historical blob or commit-message content; every surviving
  guard is scoped to the current tracked working tree.
- Halt a purge run when the working tree or the object database is not
  quiescent (`scripts/purge/preflight.py`'s quiescence gate). No surviving
  module checks for a peer branch, a peer worktree, or an in-progress git
  operation before anything runs, because nothing in the surviving guard set
  performs a destructive operation that quiescence exists to protect.
- Build or compare a tree manifest, or compare the repository's state against
  a captured spec-status baseline, across a rewrite or replacement
  (`scripts/purge/manifest.py`). The tree-identity check that superseded it
  (`scripts/purge/verify.py::check_tree_identity`) is itself deleted with the
  rest of `verify.py`; no surviving module re-derives or re-checks that
  identity after this task lands.
- Probe a remote's identifier surface — whether a given commit or blob id
  still resolves against a named repository over the network
  (`scripts/purge/verify.py::probe_identifier`, `compare_refs`, and the
  retention-probe callers in `scripts/purge/verify.py`). Requirement 8's
  "standing duty" (§7 above) that `fitdocs_oss` remain private is now an
  obligation this document records, not a capability this repository can
  re-check by running anything.
- Repair a stale SHA-shaped prose pin to the replacement's epoch value, or
  verify that a repair was applied correctly and completely
  (`scripts/purge/pins.py`). A future stale pin — one written or missed after
  this retirement — has no remaining tool to find or fix it mechanically.
- Generate a `--replace-text` rule set from the six identity-erasure
  invariants and their adjacency oracles (`scripts/purge/replacements.py::build_rules`
  and the invariant-checking functions `tests/purge/test_replacements.py`
  pinned). The rules a rule set of that shape would need to guard against
  cannot be regenerated or re-validated against those invariants; only the
  narrower notice/mark tip guard re-homed at task 7.2 (see above) survives
  from that module.
- Confirm, from inside this repository, that a specific match-data value was
  ever actually present in this repository's history before the replacement,
  or that it is genuinely absent from history after the replacement —
  `tests/test_forbidden_strings_source.py`'s subject, deleted above. What the
  surviving guards check instead is narrower: that the *supplied* match-data
  source is non-empty at all (`tests/_forbidden_strings.py`'s
  `ForbiddenStrings.__post_init__`, which rejects an empty `values` tuple with
  no notion of category), and that the *current tracked tree* is clean of
  it. Neither surviving check says anything about this repository's history,
  reachable or not.
- Confirm the supplied match-data source still holds a non-empty `token`
  category *and* a non-empty `path` category separately, each above a
  recorded count floor — `tests/test_forbidden_strings_source.py`'s own
  `test_forbidden_string_source_is_live_when_supplied`, built on that
  module's private `_categorized_entries`, was the only check that *asserted*
  the source's `<category><TAB><value>` structure.
  `tests/_forbidden_strings.py`'s
  loader (`_parse`, used by every surviving guard) discards the category
  prefix on read and never reconstructs it, so no surviving module can tell
  a source that has silently lost every `path`-category entry, while keeping
  enough `token`-category entries to stay non-empty overall, from one that
  has not.

Each of these was a capability built for an operation — the in-place rewrite
or the fresh-root replacement — that can no longer recur: the replacement
already ran (§3 above), and Decision 7 forbids repeating it in place.
Retaining tooling to re-verify an operation that cannot happen again would be
exactly the false confidence Requirement 12 exists to prevent.

**Type-checking perimeter.** `pyproject.toml`'s `[tool.mypy].files` list drops
`"scripts"` and `"tests/purge"` in this same change and gains
`"tests/test_content_oracle.py"`, `"tests/test_content_fingerprints_shape.py"`
and `"tests/test_provenance_record.py"` at their new paths, so all three
relocated modules stay in the checked perimeter; `"tests/test_forbidden_strings_source.py"`
is removed with the module it named. Every other entry in that list is
unchanged. Measured this task: the checked perimeter drops from 115 files
to 82 immediately after the deletion, then rises to 83 once
`"tests/test_provenance_record.py"` is added back for the relocation.

## Evasion-acceptance results (task 2.4)

On 2026-08-01, before task 3.1 deleted the material, the purge ran a
one-shot acceptance pass testing the value matcher against the real files.
The run generated a non-empty digest set of 434 fingerprints and a
non-empty set of 14 window lengths. It recorded nine catalogued probes.
All nine passed. Three planted-source probes and one negative control
confirmed the matcher flags a planted match and does not flag a clean
control file. A verbatim re-add, a renamed and reformatted re-add, a table
pasted as language literals into an allowlisted module, and a copy under a
different file extension were each flagged. A single-constant paste,
reusing the value `test_packaging.py`'s own docstring names as its
positive-detection evidence, was correctly reported not flagged. That
value's roughly 19.9 bits of entropy cannot clear the matcher's 96-bit
floor. No window exists to fingerprint it under any salt.

## Classified sweep inventory (task 3.2)

On 2026-08-01, after the material's removal, the purge swept every tracked
file — the universe was `git ls-files`, not only `docs/reference/` —
through six passes: a combined token-and-path-name matcher over the
identifying-token and removed-path literals from task 2.3, the value
matcher, a stale-pointer search (the independent `git grep -lF` re-run of
those same path literals), a symbolic-reproduction probe set, a
personal-identifier probe set, and a bare-basename probe set. That sweep
recorded 322 hits across 77 tracked files, per Requirements 1.3 and 2.3.
The value matcher found nothing in the swept tree. That is a true
negative, not a pass that never ran. The same fingerprint set, run against
the pre-deletion blobs still reachable in this repository's history, flags
all three of the removed source files. One tracked file's content, a
binary golden fixture, could not be read as UTF-8 by either of the two
content-reading passes. Both passes independently reported it. The
inventory therefore carries two unreadable entries for that single path.
That file's path-name surface was still scanned. Every hit was classified
by disposition, as measured on 2026-08-01, before the redaction tasks later
in this spec's Major 3 ran:

| Disposition | Count |
|---|---:|
| identity pending erasure | 129 |
| stale pointer | 76 |
| the sweep tooling's own self-reference | 38 |
| guard | 22 |
| judged not a reproduction | 18 |
| retained historical subject (Requirement 2.5) | 18 |
| public or placeholder identity | 13 |
| reproduction pending redaction | 6 |
| ignore-rule stale pointer | 2 |

This count is a shape, not a budget. It is expected to fall toward zero as
the remaining tasks in this spec's Major 3 redact, rename, or retire what
it still finds. The inventory is reproducible on demand from the tracked
tree, given the out-of-repository match-data file the sweep also requires.
Unlike the evasion-acceptance run above, it is not a one-shot artifact.

## Guard re-basing: mutation evidence (tasks 4.1-4.3)

Each of the three re-based or newly-built guards recorded its own mutation
evidence in the commit that landed it, per Requirement 3.5. Task 6.1 located
all three and confirmed each mutation was run through `uv run pytest` rather
than a bare interpreter. One line per commit, summarising what the commit
message already states in full, with bullet counts counted directly against
each commit's `MUTATION EVIDENCE` block by this task (not carried over from
a prior round):

- **`221d60a` — the sdist guard re-based onto the value oracle.** Eight
  mutation bullets against `tests/load/test_packaging.py` (eleven if the
  compound `FINGERPRINTS`/`WINDOW_LENGTHS` bullet — run once in the source
  scan and again in the sdist scan — is unpacked into its four sub-cases),
  each run through `uv run pytest`, observed red, reverted, observed green;
  the commit message states each as a sole failure except the wheel-allowlist
  emptying, which is named as reddening every real module by design (a
  preserved control, not a vacuous one). "Nine" appears in this commit's own
  text only as the count of *covered requirement sections* ("six of nine
  requirements are pinned"), a different quantity from the mutation count —
  an earlier round of this record transplanted that numeral onto the mutation
  bullets, which this correction undoes.
- **`f1dad15` — the documentation guard re-based onto a synthetic corpus.**
  Nine mutations against `tests/test_docs_guarantees.py`, each run through
  `uv run pytest`, observed red, reverted. Seven are named sole failures. The
  eighth (the pairing condition inverted) is explicitly reported as reddening
  two tests rather than one, with the reason stated (both steering documents
  already record a withdrawal) rather than mis-claimed as sole. The ninth is
  the real-tree escape the commit runs and records as **not** caught (a
  plain-language description naming no one) — it reddens nothing by design,
  which is why Req 11.9 carries a stated loss for this guard rather than a
  ninth sole failure.
- **`7f447da` — the standing forbidden-string guard stood up.** Six mutation
  groups against `tests/test_forbidden_strings.py`, each run through
  `uv run pytest`, observed red, reverted. Five of the six are named sole
  failures, including the third (sdist members filtered to a single
  extension), which needed a second anchor of a different extension precisely
  because the first anchor could not detect that filter alone — a
  discrimination gap found and closed in the same commit, not a surviving
  cascade. The sixth bullet is the end-to-end check (a tracked file whose
  NAME carries a token, with the exempted set widened from the other module,
  still caught); the commit reports it caught rather than naming it a sole
  failure in those words.

No guard record was missing or ambiguous. `221d60a` states, at every site,
whether a named mutation reddens only the assertion it pins or is a preserved
control that reddens many by design (the wheel-allowlist emptying, named as
such rather than mis-claimed as sole). `7f447da` states it at four of its six
sites: "The path-only exemption keying: red." and the end-to-end
token-in-filename bullet's "still caught" leave the blast radius
unquantified. Both are in fact sole failures -- the surface-gate removal was
re-run for this record and reddened only
`test_reviewed_exemption_never_exempts_a_path_surface_hit` -- so the records
understate their own evidence rather than overstating it. `f1dad15`'s ninth item goes further than either: it is
not a mutation that reddens anything, sole or cascading, but a recorded
escape the commit states plainly rather than disguises — the same posture
Req 11.9's stated loss depends on. All three
state their commit-message act discharges Req 3.5 itself ("Req 3.5 is a
commit-message act and is UNPINNED; this message is the act" — `7f447da`),
which task 6.1 accepts: Req 3.5 asks the purge to *record* the mutation, not
to make the act of recording itself independently testable.

## Classification of all 82 requirement criteria (tasks 6.1, 7.8)

Task 6.1's own text in `tasks.md` records that incremental review does not
terminate at this spec's size — the failure mode task 5.4 hit
five times over, closing each round with "the bounded remainder" and each
being wrong, per `tasks.md`'s Implementation Notes. This section is the mechanical,
exhaustive sweep task 6.1 ran instead: every criterion in `requirements.md`,
enumerated from that document directly, in its own numbering, and assigned
one of three labels, plus the one declared exception below that splits a
single criterion across two of them.

**Corrected in place 2026-08-18 (task 7.8), then corrected again 2026-08-19
(task 7.8 remediation) because the first correction's own account of
Amendment 1's scope was itself false.** The 2026-08-18 text said Amendment 1
"rewrote three criteria inside requirements this section already covered
(9.3, 9.4, 9.8) plus one more (10.3)". Running
`git diff 40eb36e 19bd786 -- .kiro/specs/encumbered-content-purge/requirements.md`
shows that enumeration was false: Amendment 1's regeneration substituted
"replacement"/"replaced" for "rewrite"/"rewritten" across most of
Requirements 6 through 10 — a vocabulary change carrying no change in what
evidence a row needs — but it also reworded the *obligation itself*, not
only its vocabulary, in **six** criteria, not four: 8.1 (the purge now
establishes what the remote serves "after the chosen reconciliation action",
not only "after a forced update"), 8.4 (reconciles "by whatever further
means the measurement shows to be sufficient" rather than naming deletion
and recreation as a ceiling), 9.3 (a complete pre-to-post commit map → a
single stated permanent-unresolvability position), 9.4 (a commit-for-commit
mapping → one documented convention applied uniformly), 9.8 (a per-pin
unresolvable-fallback rule → a uniform substitution ban covering pins,
documents and the provenance record alike), and 10.3 (a
differ-only-in-enumerated-files comparison → tree identity).

Four further criteria changed by the vocabulary substitution alone and are
listed separately here because their rows needed correcting anyway, for
quoting the superseded wording or citing a retired anchor — not because the
obligation moved: 9.2 ("this rewrite" → "the history replacement"), 9.6
("pre-rewrite commit" → "pre-replacement commit"), 10.1 ("the rewritten
tree" → "the replacement root's tree") and 10.5 ("treat the rewrite as
incomplete" → "treat the replacement as incomplete"). The distinction is
drawn deliberately, and the decisive pair is checkable in the diff: 9.6's
change is character-for-character the substitution also applied to Req 7.3
("reference no pre-rewrite commit" → "reference no pre-replacement
commit"), and 7.3 is in neither list because nothing in its row needed
correcting. Neither list is a count of every criterion Amendment 1 touched;
the substitution reached most of Requirements 6 through 10, and the diff,
not this paragraph, is the authority on its extent.

This remediation round re-verifies all ten of those rows against the current
tree, not only the four the 2026-08-18 correction named, and corrects two
further rows (7.1, 7.2) that were separately false against the current tree
rather than against Amendment 1's text. 9.3 named `docs/reference/commit-map.tsv` as a
forthcoming Major 8 artifact, but Decision 6 and the Amendment 1 rewrite of
Req 9.3 mean no commit map can exist by construction — nothing produces one,
and the mechanism that once compared against one
(`check_commit_map_complete`) was deleted from `scripts/purge/verify.py` at
task 7.4, re-confirmed this round by
`grep -rn "commit-map\|commit_map\|CommitMap" scripts/ tests/`, which finds
only prose describing the retirement, no live code path. 8.4's row cited
"tasks.md's own naming-convention note" for the fact that the retired plan's
8.1-8.5 were replaced before any ran; that fact is stated in tasks.md's
**execution rules** ("Amendment 1 (2026-08-17) regenerated Majors 7–8 in
place. The retired plan's tasks 7.2–7.4 and 8.1–8.5 ... were replaced before
any of them ran"), not in the naming-convention note, which is a vocabulary
list naming no task number — the current plan's task 8.4 (titled "Push the
renamed remote, then measure what both remotes serve" — that title's "renamed"
is Amendment 2's word for re-pointing `origin` at a pre-existing empty
destination, not a claim that any repository was renamed; see §3 and §7 —
retitled twice on 2026-08-22: by Amendment 2, when recreating a destination
turned out to be unnecessary because one already existed, and by Amendment 3,
when the old repository was retained rather than deleted so that both
remotes remain to be measured) is the one task tagged
`_Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_` and covers this criterion.
*(Amendment 3 added criterion 8.8, a recording duty tagged on task 9.2 rather
than 8.4, so 8.4 no longer covers all of Req 8 on its own.)*

This round corrects ten rows against the current tree — 7.1, 7.2, 8.4, 9.6,
9.8, 10.1, 10.3, 10.5, plus 5.1 and 8.6's vocabulary only — the same scoped
discipline `## Scope of the 2026-08-08 prose-correction sweep` below already
establishes: **zero residual false claims is not claimed.** Of the criteria
the corrected preamble above names, this round re-ran
fresh mutation evidence only for 9.8 (the new guard-clause mutation) and
re-confirmed 9.3's citation by re-running its `grep`; 9.4, 8.1 and 8.3's
existing rows were read and found still accurate against the current tree
but their mutations were not re-run this round. This round did not touch
9.2, whose row already used "both rewrites" loosely but was not found
false. A later reviewer applying the same mutation-based scrutiny to a row
neither this round nor the 2026-08-08 sweep re-ran may still find one.

**PINNED** — a named test dies on a named single-line production mutation,
run through `uv run pytest` in this task or in the task that landed the
assertion. **PRESERVED-ONLY** — a pre-existing regression test covers the
criterion, confirmed by watching it go red on a real mutation rather than
inferred. **UNPINNED** — stated explicitly, with the mutation this task or a
prior task ran to establish that nothing in the suite catches a violation.
An UNPINNED criterion is not a gap in this purge's testing discipline; most
of the criteria concerning the history rewrite's completion — design.md's
"Major 2 — the gated pipeline" — describe a state ("when the history rewrite
is complete...") that is true only after `tasks.md`'s Major 7 and Major 8
run, which this task's own boundary forbids doing. (`tasks.md`'s own Major 2,
"Detection: the oracles...", is a different section under the same number and
is mostly PINNED; this paragraph names the design.md section deliberately to
avoid conflating the two.)

Two things this table does not claim. It does not claim every UNPINNED
criterion is false today — most are simply not yet true, because the event
they describe (the one-shot rewrite, the remote reconciliation) has not
happened. And a PINNED or PRESERVED-ONLY label pins the *mechanism* a named
test exercises, not the truth of every clause of a compound requirement
sentence; where a requirement's scope exceeds what any test reaches (for
example, the at-any-commit half of Req 11.1 and 11.2, unreachable before
Major 7), the label reflects the working-tree-today subset a standing test
can actually reach, and that limit is named in the row.

| Req | Label | Test / mutation |
|---|---|---|
| 1.1 | PINNED | `tests/purge/test_tree_removal.py::test_removed_paths_are_absent_from_git_ls_files`, with its own positive control (`test_removed_paths_actually_existed_before_the_deletion`) proving the needle set is real |
| 1.2 | UNPINNED | No tree-wide guard catches an arbitrary new reproduction outside `src/`+the built artifact. Named sites carry a narrow pin instead — re-confirmed this task: planting one sentence naming the third party into `.kiro/specs/training-load/research.md` reds three tests, not one: `tests/purge/test_sweep.py::test_research_log_redaction_site_is_scanned_and_clean` plus `tests/test_forbidden_strings.py::test_standing_guard_scans_tracked_content_and_path_names` and `::test_standing_guard_scans_sdist_members_content_and_names`. With `FITDOCS_FORBIDDEN_STRINGS` unset the plant reds nothing at all -- 2853 passed, 21 skipped, zero failures, all three tests skipping at `tests/_forbidden_strings.py`'s guard -- so no configuration makes this a sole failure; the earlier claim that it was sole with the variable unset was measured false and removed. Reverted, confirmed green |
| 1.3 | PINNED | `tests/purge/test_sweep.py::test_tracked_files_raises_rather_than_silently_return_an_empty_universe` (non-vacuous walk) plus the `_MODIFIED_FILES_TABLE_SAMPLE` superset check. That tuple holds two entries, both under `.kiro/specs/`, evaluated from the source rather than read off the comment block above it, which names deliberately-excluded paths and is not the tuple's contents |
| 1.4 | UNPINNED | "Redact and retain the surrounding record" is a prose-shape obligation; no assertion distinguishes a redaction that kept the record from one that deleted it whole |
| 1.5 | UNPINNED | Declared in `bfe0ddf`: "the retained record itself is not [pinned]: deleting the entire licensing bullet leaves the suite green" |
| 1.6 | UNPINNED | Prose restatement obligation; `3099d92` lists it among the provenance record's unreached propositions |
| 1.7 | PINNED | `tests/purge/test_adopt.py`, per `e40f6ec`: "Reqs 1.7 and 5.3 are pinned here" |
| 2.1 | PINNED | `tests/purge/test_tree_removal.py::test_pyproject_has_no_sdist_build_target_section` |
| 2.2 | UNPINNED | No test reads `CLAUDE.md`'s Key References section |
| 2.3 | PINNED | Not preserved-only: `tests/test_forbidden_strings.py`'s standing guard was built by this spec in `7f447da`, not pre-existing. `test_standing_guard_scans_tracked_content_and_path_names` — re-confirmed this task: planting one of the removed-path `path`-category fragments from the out-of-repository match-data file, token-free, into a tracked doc reds this test plus `test_standing_guard_scans_sdist_members_content_and_names` (2 tests), reverted, confirmed green |
| 2.4 | UNPINNED | Confirmed in tasks.md's own Implementation Notes: "The ignore rule's survival is verifiable only mechanically... no test covers it" |
| 2.5 | UNPINNED | The exemption table's *existence* is pinned by `7f447da`'s reconciliation count, but "retained in a form carrying no identifying token, and not presented as present" is a semantic judgement no assertion reaches |
| 3.1 | PINNED | `221d60a`: "assert FINGERPRINTS -> frozenset(): sole failure. Same for WINDOW_LENGTHS" |
| 3.2 | PINNED | `221d60a`: "not offenders -> scan(...) or True: sole failure, full offender list" |
| 3.3 | PINNED | `221d60a` synthetic-control mutations plus `7f447da`'s two positive controls, each a sole failure |
| 3.4 | PINNED | Same synthetic-control evidence — invented values, no dependency on a removed file |
| 3.5 | UNPINNED | Declared by design: `7f447da` — "Req 3.5 is a commit-message act and is UNPINNED; this message is the act" |
| 3.6 | UNPINNED | `221d60a`: "Req 3.5, 3.6 and 11.9 are UNPINNED and say so: deleting every character of the loss statements leaves the suite green" |
| 3.7 | PINNED | `tests/purge/test_content_fingerprints_shape.py` and `tests/purge/test_fingerprints.py`, both scoped to Req 3.2 and 3.7 in their own docstrings |
| 4.1 | UNPINNED | `f1ef31b`'s own guard comment: "a token-free retention instruction still passes" |
| 4.2 | UNPINNED | Prose ("retained-then-reversed-on-2026-07-30 and why"); no assertion reaches it |
| 4.3 | UNPINNED | Cross-boundary-correction recording is prose; no assertion reaches it |
| 4.4 | UNPINNED | `tests/purge/test_manifest.py` pins the *capture* of the spec-status baseline, not a before/after comparison — that comparison is task 8.3's, unrun |
| 4.5 | UNPINNED | Framing obligation ("not as if never present, not as an error of judgement"); prose, no assertion reaches it |
| 5.1 | UNPINNED | At-any-commit-reachable-from-any-ref; the history replacement that would make this true has not run |
| 5.2 | UNPINNED | Same reasoning as 5.1 |
| 5.3 | PINNED | `tests/purge/test_adopt.py`, per `e40f6ec`: "Reqs 1.7 and 5.3 are pinned here" |
| 5.4 | UNPINNED | `3099d92`: "5.4 ... are prose obligations no assertion reaches" |
| 5.5 | UNPINNED | Redaction of example data in `distribution/design.md`; no test |
| 5.6 | UNPINNED | `3099d92`: "5.6 ... [is a] prose obligation no assertion reaches" |
| 6.1 | PINNED | Re-verified this task: reverting `Quiescence.quiet` to drop `extra_branches` from the check reds five tests, not four scoped to one module — `test_inspect_reports_every_branch_other_than_main`, `test_gate_halts_on_extra_branch_and_names_it`, `test_gate_appends_to_a_nonempty_log_without_truncating_it_on_halt` and `test_gate_does_not_rewrite_any_ref_on_halt` (4 of `tests/purge/test_preflight.py`'s own 26 tests) plus `tests/purge/test_rewrite_gate.py::test_a_failing_gate_emits_zero_commands`; the rest of the full 2873-test suite stayed green; reverted, confirmed green |
| 6.2 | PINNED | Same mutation as 6.1 — the halt-and-report path is what the five reddened tests pin |
| 6.3 | PINNED | `975e5bc`: "a test snapshots every byte of ref and reflog state before and after and requires them identical. Injecting a single ref write into the inspection reds that test alone" |
| 6.4 | PINNED | `975e5bc`: "both abandonment halt causes emptied: the tests asserted only that a HALT line existed... A halt whose cause is blank is the useless line this task exists to prevent" |
| 6.5 | PINNED | `tests/purge/test_rewrite_gate.py`, scoped to Req 6.5 in its own docstring; ordering pinned by the spy assertion that the gate is called first and a non-zero result emits nothing |
| 6.6 | PINNED | `975e5bc`'s abandonment-obligation mutations: empty tuple refused, blank-after-stripping entries refused |
| 7.1 | UNPINNED | Corrected in place: the prior row's claim that "Major 7 has not run" was false — tasks 7.1-7.7 are all `[x]` on this branch. Req 7.1 is carried by task 7.7 (`_Requirements: 7.1, 7.3, 10.3_`), done as a rehearsal against a throwaway repository, and by task 8.2 (`_Requirements: ..., 7.1, 7.7, ...`), the real swap against the working repository, which is `[ ]` and unrun. The criterion names a property of the completed replacement on the actual repository — Major 8's event, not Major 7's — so the label stays UNPINNED |
| 7.2 | UNPINNED | Corrected in place: the prior row's claim that "Major 7's own re-assertion (task 7.1) has not executed" was false. Task 7.1 is `[x]` and tasks.md's execution rules state "Task 7.1 stands as landed work: it ran on 2026-08-16 and its outcomes are durable"; `git for-each-ref refs/original` returns empty on this tree, confirmed this round. Req 7.2 is carried by task 7.1 (`_Requirements: ..., 7.2_`, done) and by task 8.3 (`_Requirements: 5.3, 7.2, ...`, unrun). The criterion still names a property of the completed history replacement, which is Major 8's event; today's empty `refs/original/` is the design-phase deletion and task 7.1's re-assertion holding coincidentally, not the criterion's own event, so the label stays UNPINNED |
| 7.3 | PINNED | Not preserved-only: `scripts/purge/verify.py` is production code, not a test. Re-run this task against the current tree (task 7.7 remediation; the row's mechanism changed under that fix, so this instruction and its count are re-measured, not carried over): mutating `check_reflog_and_unreachable_gone`'s `passed = not disallowed and fsck_clean` to `passed = True` reds 11 tests in `tests/purge/test_verify.py` plus `test_replace_rehearsal.py` unaffected -- every `test_check_reflog_and_unreachable_gone_*` test that asserts the row FAILS, which is 10 of the 14 in the module; the other four assert a pass or a raise and are unaffected (`..._fails_on_a_disallowed_commit_id`, `..._fails_on_a_reflog_id_whose_object_is_absent`, `..._fails_via_the_scan_alone_on_an_absent_id`, `..._fails_on_a_dangling_unreachable_object`, `..._scans_the_remotes_logs_subtree`, `..._scans_the_stash_log`, `..._fails_for_a_stale_reflog_on_a_second_branch`, `..._does_not_crash_on_non_utf8_committer_bytes`, `..._fails_on_a_zero_padded_filemode_warning`, `..._catches_a_64_hex_id`) plus `test_deliberately_incomplete_fixture_repository_fails_the_rows_it_should`; reverted, confirmed green (101 passed across both files) |
| 7.4 | PINNED | `tests/purge/test_verify.py`, scoped to Req 7.4 in its own docstring; `7d49c84`'s six-planted-defect fixture must fail the rows it should while passing the rest |
| 7.5 | PINNED | `7d49c84`: "The clone flag that makes a fresh clone evidence at all was unpinned... It is now pinned through the function" |
| 7.6 | PINNED | `tests/purge/test_verify.py`, scoped to Req 7.6 in its own docstring |
| 7.7 | PINNED | `tests/purge/test_verify.py`, scoped to Req 7.7 in its own docstring |
| 8.1 | PINNED | Re-run this task: `tests/purge/test_verify.py::test_probe_identifier_raises_on_unrecognised_status_not_reporting_gone` — collapsing `scripts/purge/verify.py::probe_identifier`'s non-200/non-404 branch into `served = False` (treating any unrecognised status as "gone") reds this test as the sole failure, reverted, confirmed green |
| 8.2 | UNPINNED | Remote reconciliation has not run |
| 8.3 | PINNED | Same test and mutation as 8.1 — `test_probe_identifier_raises_on_unrecognised_status_not_reporting_gone` is what pins that an unrecognised status is refused rather than silently classified |
| 8.4 | UNPINNED | Corrected in place (task 7.8): named the retired plan's task 8.5, replaced before it ran; the reconciliation action is current task 8.4 (titled "Push the renamed remote, then measure what both remotes serve" — "renamed" is Amendment 2's word for re-pointing `origin` at a pre-existing empty destination, not a claim that a repository was renamed; see §3 and §7 — `_Depends: 8.3_`; retitled twice on 2026-08-22 — by Amendment 2, once recreating a destination turned out to be unnecessary because one already existed; by Amendment 3, the old repository is RETAINED rather than deleted, so Requirement 8 was AMENDED TEXTUALLY -- its subject narrowed to the canonical repository, criterion 8.4 given an explicit exemption for the retained one, 8.7 widened to both and a new 8.8 added for the standing privacy duty. Not a scoping: an exemption, recorded as one), unrun — no module implements it yet. Re-corrected this round: the fact that the retired 8.1-8.5 were replaced before any ran is stated in tasks.md's execution rules ("The retired plan's tasks 7.2–7.4 and 8.1–8.5 ... were replaced before any of them ran"), not in the naming-convention note, which lists vocabulary and names no task number |
| 8.5 | PINNED | Re-run this task: emptying `scripts/purge/verify.py::compare_refs`'s `remote_only` computation to `()` reds six tests: `test_compare_refs_fails_when_the_remote_carries_a_ref_not_local`, `test_compare_refs_fails_on_both_directions_simultaneously_with_distinct_names`, `test_compare_refs_sorts_both_missing_from_remote_and_remote_only`, `test_check_remote_refs_match_fails_when_a_remote_only_ref_is_present_in_a_fixture`, `test_check_remote_refs_match_fails_when_refs_original_survives_on_the_remote`, `test_check_remote_refs_match_fails_when_a_pre_rewrite_tag_survives_on_the_remote`; reverted, confirmed green |
| 8.6 | UNPINNED | Recording the measurement is part two of this record, appended post-replacement |
| 8.7 | UNPINNED | *(widened by Amendment 3, 2026-08-22, to "neither the canonical repository nor the retained `fitdocs_oss`".)* True by the absence of any code path that publishes either repository, but that absence has not been asserted by a test |
| 8.8 | UNPINNED | *(added by Amendment 3, 2026-08-22.)* A recording duty — that `fitdocs_oss` must remain private for as long as it exists, and why — discharged by task 9.2 into the provenance record, which has not run. No test asserts the record's content (the same posture as 9.2's row below), and no test could assert the maintainer's future conduct the duty binds |
| 9.1 | PINNED | `tests/purge/test_provenance_record.py`, per `3099d92`: "Req 9.1 was otherwise wholly unpinned: before this test the document could be deleted entirely with the suite green" |
| 9.2 | UNPINNED | The document's existence and headings are pinned (9.1); whether its content is *true and complete* for both rewrites, and carries no address/material/token, is not |
| 9.3 | UNPINNED | Corrected in place (task 7.8): the prior row cited `docs/reference/commit-map.tsv` as a forthcoming Major 8 artifact. Amendment 1 rewrote this criterion — no pre-to-post commit map can exist by construction (Decision 6), and no module produces one: `check_commit_map_complete` was deleted from `scripts/purge/verify.py` at task 7.4 (its own docstring: "Four rows are deleted with the mechanism whose subject no longer exists"), confirmed this task by `grep -rn "commit-map\|commit_map\|CommitMap" scripts/ tests/`, which returns only prose describing the retirement and zero live code paths. The provenance record's history-replacement section (`design.md` `ProvenanceRecord`) that states this is written by task 9.2, after Major 8 runs; nothing exists yet to assert against |
| 9.4 | PINNED | Re-verified this task (evidence count corrected — the prior row's "two tests" was stale against the current suite): replacing `scripts/purge/pins.py::verify_rewrite`'s mismatch check (`if actual != expected:`) with `if False:` (never raising `PinRepairVerificationError`) reds five tests in `tests/purge/test_pins.py`, run scoped to that module: `test_verify_rewrite_raises_when_the_line_on_disk_does_not_match_the_outcome`, `test_verify_rewrite_catches_a_stale_value_that_is_not_the_first_line`, `test_verify_rewrite_catches_a_pin_on_disk_the_outcomes_do_not_account_for`, `test_apply_repair_verifies_every_pin_through_its_real_write_path`, `test_apply_repair_actually_calls_verify_rewrite_against_the_real_write`; the other 27 tests in the module stayed green; reverted, confirmed green (32 passed) |
| 9.5 | UNPINNED | Re-run this task: keeping this document's `## 6. Stated positions` heading and replacing its entire body with the sentence "No position is stated on any of these matters." leaves the suite green (2873 passed, 1 skipped) — only Req 9.1's heading/non-empty-body tests reach this section, and 9.5's own position is not appended until the post-rewrite commit, same reasoning as 9.6 |
| 9.6 | UNPINNED | Corrected in place: the prior row cited design.md `ProvenanceRecord`'s "Ordering detail that bites" heading, which exists only in the pre-amendment document (`git show 40eb36e:.kiro/specs/encumbered-content-purge/design.md`) and deferred a pointer to a commit map Decision 6 makes impossible. The regenerated `#### ProvenanceRecord` states instead: "The drain-report fixture's planned one-line pointer to the commit map is **cancelled** — there is no map for it to point at. The fixture's note instead records that its abbreviated commit id is a pre-replacement identifier and permanently unresolvable, written in the aftermath commit alongside the other Req 9 positions." That note is still unwritten today — it lands in the aftermath commit, after Major 9 — so the criterion (a stated position on the fixture) remains UNPINNED, but for the corrected reason: nothing forthcoming points at a map, because no map exists |
| 9.7 | PINNED | `tests/purge/test_tree_removal.py` and `tests/purge/test_rewrite_map_extraction.py`, both scoped to Req 9.7 |
| 9.8 | PINNED | Corrected in place (task 7.8): the prior row's mutation targeted `scripts/purge/pins.py::_looks_like_commit_id` and its four named tests, none of which exist any longer — task 7.5 re-scoped `pins.py` to the epoch convention (module docstring: "there is no map-driven path left anywhere in this module"), which deleted the per-item unresolvable/mapped distinction entirely. Re-corrected this round: the 2026-08-18 row's own re-measurement (`resolved=epoch` → `resolved=original`) reds 17 tests, and claimed no narrower sole-failure mutation exists because "`resolved=epoch` is the single line both 9.4 and 9.8 pin" — that claim is false. `resolve_pin`'s docstring itself states the rule this criterion needs: "a value that merely happens to be a prefix of `epoch` (or vice versa) is a different value and must still be rewritten". Mutating the *adjacent* line, the guard clause, from `if original == epoch:` to `if epoch.startswith(original):`, reds `test_resolve_pin_never_substitutes_a_plausible_alternative_for_the_epoch` alone — the test's `"9f00aaa"` originals entry, "a genuine PREFIX of EPOCH, still not equal to it", is misclassified as `already_current` (`resolved=None`) instead of being repaired to the epoch — while the rest of `tests/purge` (1749 passed, 1 failed) and the module (`tests/purge/test_pins.py`, 31 passed, 1 failed) stay green. Reverted (sha `e08fc838...cde16198` before and after, confirmed via `shasum -a 256`), confirmed green (32 passed). Both mutations are genuine and are kept: the wide-cascade one (`resolved=epoch`→`resolved=original`, 17 tests) pins that a repair always resolves to the epoch; the narrower one (the guard-clause prefix mutation, 1 test) pins the exact clause this criterion names — no plausible alternative is ever substituted, including one that is merely a prefix or superstring of the epoch |
| 10.1 | UNPINNED | Corrected in place: Amendment 1 reworded this criterion from "the rewritten tree" to "the replacement root's tree", matching the closing paragraph's "history replacement" vocabulary. Property of the replacement root's tree, which does not exist yet; the current tree's suite/ruff/format/mypy state is validated separately by task 6.2, not this criterion |
| 10.2 | PRESERVED-ONLY | `92a7566`: "Req 10.2 is PRESERVED-ONLY by the existing golden tests" |
| 10.3 | UNPINNED | Corrected in place (task 7.8): the prior row described the retired mechanism (an M0/M1 manifest diff across the rewrite). Amendment 1 rewrote this criterion to a tree-IDENTITY comparison with the certified pre-replacement tip, and `scripts/purge/verify.py::check_tree_identity` is the current implementation (`git rev-parse HEAD^{tree}` compared to the tree id captured at certification). Its mechanism is PINNED — mutating `passed = out == certified_tree_id` to `passed = True` reds exactly `tests/purge/test_verify.py::test_check_tree_identity_fails_when_the_recorded_tree_id_differs` and `::test_check_fresh_clone_reds_when_the_certified_tree_id_is_wrong`, and no other test in `test_verify.py` or `test_replace_rehearsal.py` (99 passed, 2 failed of 101; reverted, confirmed green, 101 passed) — but the criterion itself, a comparison against the replacement root the one-shot replacement has not yet produced, has not run: Major 8 (the replacement) is unrun, so this stays UNPINNED as a property of a completed replacement, the same posture 7.1/7.2 already state for their own Major-8-dependent criteria (corrected this round: Req 7.1 is carried by task 8.2 and Req 7.2 by task 8.3, both unrun — Major 8, not Major 7) |
| 10.4 | PINNED | `tests/purge/test_tree_removal.py`'s built-sdist check plus the same standing guard named at 2.3/11.1 (`tests/test_forbidden_strings.py`'s sdist/wheel member scans, opt-in) — one guard, one label across all three rows |
| 10.5 | UNPINNED | Corrected in place: the prior row quoted the superseded criterion verbatim ("treat the rewrite as incomplete... no push"). The amended text reads "If validation fails on the replacement root's tree, then the purge shall treat the replacement as incomplete and shall not push to the remote until validation is green." Procedural; no assertion reaches it directly, though 7.7's ordering is the closest analogue |
| 11.1 | PINNED | Not preserved-only: the standing guard was built by this spec in `7f447da`. Same guard as 2.3/10.4. Re-confirmed this task: planting the identity token into README.md reds three tests — `test_standing_guard_scans_tracked_content_and_path_names` plus the sdist- and wheel-member scans — reverted, confirmed green; scoped to the working tree today, the at-any-commit-in-history half is unreached before Major 7 |
| 11.2 | UNPINNED | `7f447da`: "Req 11.2's at-any-commit clause is beyond a working-tree test and stays with the history tasks" |
| 11.3 | UNPINNED | Commit-message rewriting is a Major 7 transform; has not run |
| 11.4 | UNPINNED | `tests/purge/test_tree_removal.py` pins the working-tree-today subset (no notice in `pyproject.toml`); the at-any-commit claim over all of history is unreached before Major 7 |
| 11.5 | UNPINNED | `bfe0ddf`: "11.5 and 11.6 are UNPINNED, established by mutation rather than by inference" |
| 11.6 | UNPINNED | Same as 11.5 |
| 11.7 | PINNED, with a declared UNPINNED carve-out | `79197c7`: "Req 11.7 is pinned for the documentation corpus and for re-introduction into both retired files, and UNPINNED for rendered CLI output by accepted and recorded decision" |
| 11.8 | PINNED | `tests/_forbidden_strings.py`'s meta-tests: `require()` with the variable unset must raise pytest's skip exception, not return; `load()` must raise (not return `None`) for each of the four broken-source cases |
| 11.9 | UNPINNED | `221d60a` and `f1dad15` both declare it prose/unpinned; it is discharged by this record's §5, not by an assertion |
| 11.10 | UNPINNED | No test scans configuration keys or environment-variable names for token-freeness; `FITDOCS_FORBIDDEN_STRINGS` is neutral by construction, unasserted |
| 11.11 | UNPINNED | `92a7566`: "Req 11.1, 11.11 and 11.12 are UNPINNED" |
| 11.12 | UNPINNED | Same as 11.11; the vocabulary table (`9612d28`) is not tested for the absence of an invented proper noun |
| 11.13 | UNPINNED | `e40f6ec`: "Req 11.13 is UNPINNED and declared, not claimed: deleting design.md's stated position leaves the suite green" |
| 12.1 | UNPINNED | *(added by Amendment 1; task 7.8)* Property of a completed retirement; `tasks.md` task 9.3 ("Retire the machinery", `_Requirements: 12.1, 12.3, 12.4, 12.5_`, `_Boundary: MachineryRetirement_`) is where the purge scripts package is deleted and has not run. Every one-shot module this criterion would retire — `scripts/purge/plan.py`, `rewrite.py`, `adopt.py`, `preflight.py`, and the replacement-only rows of `verify.py` — is still present in the tree today, confirmed by `ls scripts/purge/` this task |
| 12.2 | UNPINNED | *(added by Amendment 1; task 7.8)* Property of a completed retirement; `tasks.md` task 9.4 ("Prove every surviving guard still fails, then destroy the scratch", `_Requirements: 3.5, 12.2_`, `_Depends: 9.3_`) is where every surviving guard's mutation is re-run on the post-retirement tree and has not run. Today's guards do execute and are demonstrably able to fail (the same standing guard pinned at 2.3/10.4/11.1, plus 3.1-3.4), but that is evidence of the pre-retirement state, not the post-retirement claim this criterion makes |
| 12.3 | UNPINNED | *(added by Amendment 1; task 7.8)* Property of a completed retirement; task 9.3 is where the retirement's own deletion list is produced and has not run. The provenance record and Req 4/Req 9's recorded evidence exist today (this document, this section) but nothing yet asserts they survive the retirement step, which is exactly what this criterion requires |
| 12.4 | UNPINNED | *(added by Amendment 1; task 7.8)* Prose restatement obligation, same shape as 3.5/3.6/11.9's loss-statement criteria: no section stating what the retirement gave up exists yet, because task 9.3 — "Write provenance section 8: what machinery was removed, what each surviving guard still detects, and what verification capability was given up" — has not run |
| 12.5 | UNPINNED | *(added by Amendment 1; task 7.8)* Ordering constraint on when the retirement runs, not a runtime assertion; no code path checks "not yet public" before running it, the same absence-of-a-test posture already declared at 8.7 for "shall not make the repository public". `tasks.md` states the ordering in task 9.3's own body ("After the replacement is verified and before the repository is made public") and encodes the *sequencing* half mechanically — task 9.1 (Major 9's first task) is `_Depends: 8.4_` (Major 8's last task), so Major 9 cannot start before Major 8 finishes by task-dependency construction — but that dependency graph is plan discipline, not an assertion a mutation can red |

**Totals: 33 PINNED, 1 PRESERVED-ONLY, 48 UNPINNED — 82 of 82 criteria
classified.** *(Was 47 UNPINNED and 81 of 81 until Amendment 3 added criterion
8.8 on 2026-08-22; the new criterion is UNPINNED, and this total is the count
this section's exhaustiveness claim below refers to. An amendment that adds a
criterion must move these numbers with it — the claim is exhaustive or it is
false, and nothing mechanical guards it.)* The 33 PINNED figure folds in the one row labelled `PINNED,
with a declared UNPINNED carve-out` (11.7) alongside the 32 rows labelled
`PINNED` outright; that row is the spec's one declared exception to "one of
three labels" named in this section's opening paragraph, not a fourth
category. No criterion is left unclassified.

Of the 47 UNPINNED rows, 5 state an observed mutation (1.2, 1.5, 3.6, 9.5,
11.13), 2 cite a mutation a prior task ran without restating it (11.5, 11.6),
5 are declared by design in a commit message (3.5, 4.1, 11.9, 11.11, 11.12),
and the remaining 35 carry neither — unpinned because the event they
describe has not occurred or the obligation is prose no assertion reaches,
and there is no production line to mutate: 1.4, 1.6, 2.2, 2.4, 2.5, 4.2, 4.3,
4.4, 4.5, 5.1, 5.2, 5.4, 5.5, 5.6, 7.1, 7.2, 8.2, 8.4, 8.6, 8.7, 9.2, 9.3,
9.6, 10.1, 10.3, 10.5, 11.2, 11.3, 11.4, 11.10, 12.1, 12.2, 12.3, 12.4, 12.5.
Task 6.1 ran three of the five observed-mutation rows fresh — 1.2 and 9.5,
both UNPINNED, plus the same mutation pinning 6.1 and 6.2 (both PINNED, not
UNPINNED, named here only to record that task re-verified them) — through
`uv run pytest`, with `scripts/purge/__pycache__` cleared first, observed
red, then reverted and confirmed green. The other rows re-run by task 6.1
(2.3, 7.3, 8.1, 8.3, 8.5, 9.4, 9.8, 11.1 — all PINNED) were listed in their
own rows with the tests and mutations that task ran for each.

Task 7.8 re-verified 9.4, 9.8 and 10.3's mechanism fresh through
`uv run pytest`, with `scripts/purge/__pycache__` cleared first, each
observed red then reverted and confirmed green — recorded in each row above,
because task 7.5's re-scope of `pins.py` to the epoch convention and task
7.4's re-scope of `verify.py` to the fresh-root shape changed what the prior
evidence described without changing the label. It corrected 9.3's and 8.4's
rows in place (a withdrawn artifact and a retired task number respectively;
no re-classification, no mutation applicable) and added the five Req 12 rows
new at Amendment 1, all UNPINNED with a stated procedure, none of which has
a production line to mutate today because the machinery they describe has
not been built.

The 2026-08-19 remediation round corrected nine further rows in place —
7.1, 7.2, 8.4 (citation only), 9.6, 10.1 and 10.5 (vocabulary or
verbatim-quote corrections), 10.3 (its "Major-7-dependent" cross-reference),
and 5.1/8.6 (vocabulary only, outside both preamble lists) — none of
which changed a label, re-verified 9.3 unchanged as part of the
ten-criterion re-verification above, and re-ran 9.8's mutation evidence
fresh, adding a second, narrower sole-failure mutation (the `resolve_pin`
guard-clause prefix mutation) beside the pre-existing wide-cascade one; 9.8
stays PINNED. It also deleted two sentences the 2026-08-18 correction had
left in place — "Every other row below is unchanged from task 6.1's sweep"
and "no row in this table cites a withdrawn artifact as forthcoming after
this edit" — both false at the time they were written: 9.6 cited exactly
such a withdrawn artifact (design.md's pre-amendment "Ordering detail that
bites" heading) until this round's fix, and 7.3's own row already said its
mechanism was re-run and re-measured under "task 7.7 remediation", "not
carried over" from task 6.1 — that remediation landed at `831aa5c`, the
commit this branch's `HEAD` was at when this round began (confirmed via
`git log --oneline -5`), the commit immediately preceding this one.

This table is a snapshot at this task's commit. Every requirement whose label
depends on the history replacement having run (most of 5.x, 7.x, 8.x, all of
12.x, and the at-any-commit halves of 9.x and 11.x) is expected to move once
Major 8 and Major 9 land; re-run this sweep after the replacement rather than
trusting this table across that boundary.

## Scope of the 2026-08-08 prose-correction sweep

A rejection round on this record found seven false factual claims: three
transplanted numerals in the guard-record summaries above, a mislabelled row
(9.5) contradicting its own sibling (9.6), four rows citing "per prior
review" with neither a test name nor a mutation, three PRESERVED-ONLY rows
attributed to a guard this spec itself built or to production code rather
than a pre-existing test, two mutations whose reported blast radius was
narrower than what re-running them produced, and two citations that did not
resolve against the documents they named. This task fixed the nine sites the
review identified, re-running every mutation named at those nine sites
against the current tree (documented in each corrected row and in the
`## Status Report` this task ends with) rather than transcribing a number
from the rejection into the row. It additionally spot-checked, rather than
exhaustively re-ran, two adjacent claims this correction depends on: the
`bfe0ddf` and `3099d92` quotes underlying rows 1.5, 5.4 and 5.6 were
re-checked with `git log -1 --format=%B` against the literal fragments used
in this table (both resolve, allowing for the mid-sentence line wrap and
editorial `[pinned]` bracket already present in 1.5's row before this task).
The totals in this section were recomputed from a fresh `grep -c` count
against the table's own label column rather than carried forward by
arithmetic.

What this sweep did **not** do: re-run every mutation cited from a commit
message that neither this task nor the fix list above touched — the bulk of
the 30 rows in the "neither" bucket, and every PINNED row this task's rejection
did not name, whose evidence remains exactly what a prior task's
`grep -F`-verbatim check against its landing commit already established.
This task re-ran, itself, only the mutations named in the nine corrected
sites: 1.2, 2.3, 6.1/6.2, 7.3, 8.1/8.3, 8.5, 9.4, 9.5, 9.8, and the
tracked-README/removed-path-fragment plants underlying 2.3 and 11.1. Every
other row's evidence is carried forward, unexamined by this task, from the
prior round's own verification. **Zero residual false claims is not
claimed.** The rejection round that produced this sweep found seven false
sentences plus two rows that contradicted each other on inspection alone
(9.5 against 9.6, and 2.3/11.1 against 10.4); this task corrected all nine
sites the rejection named. A later reviewer applying the same mutation-based
scrutiny to a row this sweep did not itself re-run may still find one.

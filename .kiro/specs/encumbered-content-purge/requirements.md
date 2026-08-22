# Requirements Document

## Naming convention used by this document

This document is itself in scope for the purge it specifies — Req 1.3 covers
every tracked file — so it does not write the material it requires removed.
Throughout:

- **the withdrawn methodology** — the third-party running-load methodology
  evaluated during `training-load` and withdrawn from the shipped tool on
  2026-07-25 (training-load Amendment 2, commit `63863612b`).
- **the third party** / **the methodology's author** — the individual who
  authored it and holds its copyright and trademarks.
- **the identifying tokens** — the third party's personal name, the
  methodology's former proper name, and its trademarked abbreviation. Stated
  concretely only in scratch artifacts outside the repository, never in a
  tracked file.
- **the writeup** — the extracted methodology writeup under `docs/reference/`.
- **the extracted tables** — the two extracted lookup tables under a
  `docs/reference/` subdirectory named for the methodology.
- **the history replacement** — the one-shot destructive operation of this
  spec's execution phase: a fresh root commit whose tree is the certified tip,
  followed by recreation of the remote (Decision 6, Amendment 1, 2026-08-17).
  It supersedes the in-place history rewrite decided at discovery, which never
  ran. "The 2026-07-26 email rewrite" always names the earlier, separate
  operation.

A reader who needs the concrete strings before the purge runs will find them in
the working tree until it lands, and nowhere afterwards. That is the intended
end state, not an omission.

## Project Description (Input)

**Who has the problem.** The maintainer, who is about to publish this
repository and ship 0.1.0 as an sdist. Secondarily every future reader of the
repository, and the third party whose copyrighted material, personal contact
detail and personal name are currently in it.

**Current situation.** Three files in the working tree carry the third party's
copyright notice and a trademark notice, with redistribution permission never
obtained: the writeup (including
tables and worked examples transcribed verbatim from the source workbook) and
the two extracted tables. The methodology itself was withdrawn from the shipped
tool on 2026-07-25 (`training-load` Amendment 2, commit `63863612b`), but these
files were deliberately retained as a research record — a decision taken when
the repository was private, and reversed at Phase 5 discovery on 2026-07-30
because publishing the repository publishes them.

Deleting them from the working tree is not sufficient. The repository's
**root commit** introduced the writeup and both tables, so they are reachable
from every one of the commits on `main`, and `origin/main` already holds
them on GitHub. Two guards additionally read the material in order to work:
the packaging guard opens the writeup at test time and holds values transcribed
from it, and the documentation-guarantees guard opens the same file as a
positive control. Four approved documents still instruct that the material be
retained (`.kiro/steering/roadmap.md` — since amended,
`.kiro/steering/structure.md` — since amended,
`.kiro/specs/training-load/design.md`, `.kiro/specs/training-load/tasks.md`),
and `CLAUDE.md` points at the writeup as a key reference.

Two adjacent exposures sit on the same surface: the third party's personal
email address appears in tracked files, and the maintainer's personal email
address appears in cleartext in the prior rewrite map — at the time this was
written, a tracked file whose sole purpose was to document a prior history
rewrite that removed that same address from commit headers. That file is no
longer tracked: task 3.1 deleted it at `a705490`, and
`docs/reference/history-rewrites.md` is the successor record. The address
remains in the map's historical blobs, which is what Major 7 removes.

**A third exposure, added 2026-07-31: the third party's identity itself.** The
identifying tokens appear across the tracked tree, in tracked file *paths*, in
commit messages, and in historical paths belonging to a withdrawn
implementation package that no longer exists in the working tree but is fully
present in history — including that package's own copies of both lookup tables,
which are distinct blobs from the `docs/reference/` copies. A public,
search-indexed repository whose narrative is that a named individual's
copyrighted material was redistributed without permission and then purged is an
exposure the third party did not consent to, and one this purge can close in
the same operation rather than in a second history rewrite later.

**What should change.** Neither the writeup nor either table should be
reachable from any ref, local or remote, at any commit; a clone of the
published repository should contain no copy of them. No identifying token
should survive in the published tree, in its paths, in its commit messages, or
anywhere in its history. The guards that stop the material being re-added
should survive the deletion of what they currently read, and should still be
demonstrably able to fail. The steering and spec documents that instruct
retention should record the reversal honestly — neither as if retention had
never been decided, nor as if the material had never existed. No third party's
contact detail and no personal address of the maintainer should survive in the
published tree or its history. The purge should leave a durable record of what
was removed and when, which does not itself carry the removed material or the
removed identity.

**Depth, decided at discovery (2026-07-30) and widened 2026-07-31.** The
verbatim tables and the extracted writeup go, from tree and from history.
Discovery additionally decided that the methodology's *name* be retained
wherever it records the decision, on two stated grounds: that the
redistribution exposure is the verbatim material, and that a guard cannot
assert content is absent without naming it. **Both grounds have since been
overtaken and the decision is reversed** (Decision 5 below). Publication makes
the identity an exposure independent of the material, and the design phase
replaced the name-keyed guard data with content digests, so the guards no
longer need the name to recognise the tables. What is retained is the *fact* —
that a third-party methodology was evaluated, found to carry a redistribution
restriction, and withdrawn — without identifying whose.

**Constraints carried in from discovery.** The rewrite invalidates every
commit SHA in the repository, including every queue item's `pinned_at:` field
and a test fixture that names a commit in its own filename. Every unmerged
branch at rewrite time is orphaned, so the rewrite runs against a quiet tree —
scheduled by the maintainer for **2026-07-31 as a solo session**. A
force-push may not be sufficient to remove the objects from GitHub, which can
retain unreachable objects until it garbage-collects on a schedule the
maintainer does not control; what the remote still serves must be established
empirically rather than assumed. `refs/original/` held the only copies of two
never-pushed branches and expiring it destroys them. The values fingerprinted
by the content-keyed sdist guard must not be transcribed into any file in this
repository, including this spec's own documents — `.kiro/` currently ships in
the sdist and the guard scans by content.

Full context, evidence and the rejected alternatives:
`.kiro/specs/encumbered-content-purge/brief.md` and `.kiro/steering/roadmap.md`
› Phase 5.

## Introduction

This feature removes third-party copyrighted material, two personal email
addresses, and a third party's identity from the fitdocs repository — from the
working tree **and from every commit in its history, local and remote** —
before the repository is made public and 0.1.0 is published. It is a single
feature rather than several because deleting the material from the tree while
history still serves the same blobs achieves nothing this spec exists to
achieve, and because the identity erasure rides the same one-shot history
operation: performed separately it would cost a second whole-history operation
and a second remote reconciliation.

The work has two halves with different risk profiles and different notions of
"verified". The first is an ordinary reversible change: delete the material,
re-base onto a surviving oracle the two guards that currently read it, redact
the material and the identity reproduced elsewhere in the planning record, move
the four approved rulings that instruct retention, and retire the file that
documents a prior rewrite in cleartext. The second is one-shot and destructive:
the history replacement — a fresh root commit of the certified tip *(Amendment
1, 2026-08-17; formerly an in-place rewrite across every ref)* — verified by
unreachability rather than by a green test suite, followed by recreation of a
remote whose behaviour is then verified rather than assumed.

**Requirements are stated as properties of the repository and of the purge, not
as procedure.** Which oracle the re-based guards use, where a guard that must
match an identifying token obtains it, and what neutral vocabulary replaces the
erased tokens are design decisions this document deliberately leaves open —
each is required to be settled with evidence, and none is required to take a
particular form. *(Two questions this paragraph originally left open — how the
history operation is performed, and whether the remote must be deleted and
recreated — were settled by the maintainer in Decision 6, Amendment 1,
2026-08-17.)*

**No acceptance criterion below depends on a count, deliberately.** This
repository commits continuously, and every figure discovery wrote down was
superseded within a day — the commit total, the queue's pinned-reference total
and the remote's lag all moved again *during the first requirements phase
itself*, between the draft and the merge. Each criterion is therefore written
against "every" member of its class. What the criteria rest on instead is the
shape, which is stable: the material was introduced by the root commit and
never touched again, so every commit reaches it; every queue item carries a
`pinned_at:` field without exception; `origin/main` trails local `main` and
already holds the material. Measure those rather than quoting them — the
commands are in `.kiro/specs/encumbered-content-purge/brief.md` › Current
State.

### Decisions taken with the maintainer during requirements (2026-07-30)

Four questions were open after discovery and are settled here, because each
changes what the requirements say rather than how they are implemented:

1. **Purge depth extends to the whole planning record.** Discovery scoped the
   removal to the writeup and the two tables. Requirements research found that
   `.kiro/specs/training-load/research.md` reproduces the methodology's
   operative content in symbolic form — the two load formulas, the rule that
   generates the fingerprinted discount factors, and two workbook
   worked-example vectors — in a directory the maintainer has decided is
   public. The content-keyed guard does not catch it, because the guard
   fingerprints table *values* and that file holds the *generator*. Every
   tracked file is therefore in scope for the sweep, not just `docs/reference/`.
2. **`refs/original/` is destroyed, and with it the only copies of two
   implementation branches.** Their work is already on `main`; they are
   pre-2026-07-26 tips carrying the maintainer's personal address in their
   commit headers, so preserving them verbatim would preserve exactly what this
   spec removes.
3. **The provenance record carries a complete SHA map, and the open queue
   items' pins are repaired mechanically in the same change.** Discovery scoped
   this spec to *stating* a position once; the maintainer widened it so that
   open evidence keeps resolving after the rewrite. **Superseded in part by
   Decision 6 (Amendment 1, 2026-08-17):** under the replacement mechanism no
   map can exist; the pins are still repaired mechanically and uniformly, to a
   documented convention rather than through a map.
4. **The purge halts rather than orphans.** If the tree is not quiet, the
   history operation does not run.

### Decision taken during requirements re-generation (2026-07-31)

5. **The third party's identity is erased, not pseudonymised.** Discovery
   retained the methodology's name (see *Depth* above). The maintainer reversed
   this on 2026-07-31 and chose **total erasure with no replacement name**: the
   repository records that *a* third-party methodology was evaluated and
   withdrawn, and identifies neither the methodology nor its author. A
   pseudonym was offered and declined — inventing a substitute proper name was
   judged to risk colliding with a real person, in a repository whose narrative
   is about copyright and permission.

   Four consequences the maintainer accepted when taking this decision, each of
   which this document turns into a criterion rather than leaving implicit:

   - **The guards lose a short stable token.** Guards that today assert absence
     by matching the identifying tokens literally would become the last copies
     of those tokens — the same recursion Req 3.7 resolves for the table
     values. Req 11.6 carries it.
   - **The content-digest oracle cannot substitute here.** The design's oracle
     detects only multi-token windows clearing an entropy floor and explicitly
     does not detect a single isolated value; an identifying token is exactly
     that. Supplying the token to the guards from outside the repository at run
     time is the maintainer's proposed alternative and the leading candidate
     for design. Whatever mechanism is chosen, Req 11.7 forbids the failure
     mode it introduces: a guard that reports success when the token was never
     supplied and nothing was actually checked.
   - **Paths and commit messages are in scope, not only file contents.**
     Tracked file paths, historical paths belonging to a withdrawn
     implementation package that no longer exists in the tree, and commit
     messages all carry the tokens. Req 11.2 and 11.3 carry it.
   - **A retained prior-format fixture changes.** The recorded calculator
     identity in the retained v1 payload fixture carries a token. It was
     verified during this phase that no module under `src/` matches on that
     value — the identity is read out of the document and echoed into a
     message, never compared — so changing it alters no behaviour, and costs
     the fixture only its claim to be an authentic recovered artifact.
     Req 11.11 carries it.

   **This decision does not weaken the honesty requirement.** Requirement 4
   still demands that the reversal be recorded as a decision taken under
   different circumstances rather than an error of judgement. Anonymity applies
   to *whose* methodology it was, never to *whether* the evaluation, the
   retention and its reversal happened.

   **The limit of what erasure buys, stated so it is not oversold.** The
   repository will still describe a points-based running-load methodology
   supplied as a workbook by its author, trademarked, evaluated and withdrawn
   on a stated date for licensing reasons. A motivated reader can identify it.
   What erasure closes is the search-indexed association between a named
   individual and a public record of unlicensed redistribution — which is the
   exposure that matters and the one a purge can actually remove.

### Decision taken at Amendment 1 (2026-08-17)

6. **History is replaced, not rewritten in place.** Discovery decided a single
   in-place rewrite of every commit, on the stated ground that it "costs
   almost nothing today". The maintainer reversed the mechanism on 2026-08-17,
   before it ever ran: after the tip is certified clean by the guards and
   oracles the tree-phase majors built, the purge creates a **fresh root
   commit** whose tree is that certified tip, deletes and recreates the remote
   repository, and pushes the single new commit. Every unreachability property
   this document states is unchanged; only the mechanism achieving it changes.
   The grounds are recorded in the brief's amendment decision: the discovery
   cost claim was falsified by measurement, each pre-run review round kept
   finding real under-redaction defects in the rewrite rules, a replacement
   closes that defect class by construction rather than by enumeration, and
   the rewritten history's only consumer would have been the maintainer's
   local archaeology in a pre-release repository whose remote was to be
   force-replaced or recreated under either mechanism.

   Four consequences the maintainer accepted when taking this decision, each
   carried by a criterion rather than left implicit:

   - **No commit map can exist.** A fresh root has no post-replacement
     counterpart for any pre-replacement commit, so Decision 3's complete SHA
     map is impossible by construction. The provenance record instead states
     once that every pre-replacement identifier is permanently unresolvable.
     Req 9.3 and 9.8 carry it.
   - **Every pin repairs to a convention, not a mapping.** Open queue items'
     `pinned_at:` fields cannot be repaired commit-for-commit. Req 9.4 carries
     the replacement obligation: one documented convention, applied uniformly.
   - **Commit-level history and blame are lost.** The audit trail's tree-level
     record in `.kiro/` survives at the tip; Requirement 4's honesty
     obligations are unchanged and now do all of that work alone.
   - **The replacement machinery loses its purpose.** Tooling whose only
     purpose was to plan, execute, or verify an in-place rewrite — or the
     replacement itself — is retired once the replacement is verified, and the
     tip re-introduction guards survive the retirement. Requirement 12
     carries it.

   **This decision does not weaken any unreachability requirement.**
   Requirements 7, 8 and 11 still demand that the material, the addresses and
   the identity be unreachable from every ref, locally and on the remote, at
   every commit; the replacement satisfies them by carrying no pre-existing
   commit at all rather than by rewriting each one. *(Amendment 3, 2026-08-22:
   this sentence is true of the replacement mechanism, which is all it was
   written about, and is NOT a general guarantee. The retention ruling does
   weaken these requirements on the remote — `fitdocs_oss` keeps every
   pre-replacement commit reachable indefinitely — and Requirement 8's amended
   preamble states that narrowing and what it excludes. Read this sentence as
   scoped to the local replacement.)*

## Boundary Context

- **In scope**: deleting the writeup and both extracted tables from the working
  tree; sweeping every tracked file for reproduced material and redacting what
  is found; erasing the identifying tokens from tracked file contents, from
  tracked and historical paths, and from commit messages; re-basing the two
  guards that read the material onto an oracle that outlives it and restoring
  their ability to demonstrate failure; re-basing or retiring the guards that
  match the identifying tokens literally; reversing the four approved rulings
  that instruct retention and the pointers that go stale with them; removing the
  third party's contact detail and the maintainer's personal address from tree
  and history; retiring the prior rewrite map and replacing it with
  a provenance record carrying no personal address and no identity; repairing
  every open queue item's `pinned_at:`; the history replacement — a fresh root
  commit of the certified tip *(Amendment 1; formerly an in-place rewrite
  across all refs with `refs/original` and reflog expiry and garbage
  collection)*; verification that no object reaches the material or the
  identity locally or on the remote; recreation of the remote repository,
  verified rather than assumed; retirement of the machinery whose only purpose
  was the history operation, keeping the tip re-introduction guards
  *(Amendment 1)*.
- **Out of scope**: the `LICENSE` file, classifiers, project URLs, the `.kiro/`
  and `tests/` sdist exclusions, the README rewrite, the CI workflow, the
  changelog, and tag/publish — all owned by `distribution`. Re-litigating the
  withdrawal decision itself (`training-load` Amendment 2, closed). The
  gitignored source workbooks and the third-party page scans, which were never
  committed and stay on disk under their existing names. Any change to what the
  tool computes, to any rendered document, or to any shipped output value.
  Making the repository public, which is a separate later act.
- **Adjacent expectations**: `distribution` is downstream and unstarted; its
  Requirement 6 amendment and its unbuilt artifact-licensing gate remain its own
  work, and are expected to be written *after* this spec lands so that they
  amend once against the final state. This spec expects every peer session to
  have merged before the history replacement runs, and expects no session to run
  concurrently with it. The open queue item recording that the sdist guard has
  no positive control converges with this spec's guard work rather than
  remaining separate, because the re-oracling removes the last control that
  guard currently has.

## Requirements

### Requirement 1: Removal of the encumbered material from the working tree
**Objective:** As the maintainer, I want every verbatim copy and every faithful
reproduction of the withdrawn methodology gone from the working tree, so that
making the repository public does not redistribute a third party's copyrighted
material.

#### Acceptance Criteria

1. When the removal is complete, the fitdocs repository shall contain neither
   the writeup nor either extracted table at any path.
2. The fitdocs repository shall contain no file reproducing the withdrawn
   methodology's zone table, points-per-minute values, load formulas, per-repeat
   adjustment or discount values, discount-generating rule, performance-level or
   pace lookup rows, worked-example vectors, or weather and terrain
   pace-adjustment tables.
3. When the sweep for reproduced material runs, the purge shall cover every
   tracked file in the repository — including `.kiro/specs/`, `.kiro/steering/`,
   `.kiro/queue/`, `docs/`, `tests/` and `src/` — and not only
   `docs/reference/`.
4. Where a tracked file reproduces the material inside a record of the
   methodology's evaluation, sourcing, or withdrawal, the purge shall redact the
   reproduced content and retain the surrounding record.
5. The fitdocs repository shall retain the fact that a third-party methodology
   was evaluated and withdrawn wherever a document, commit message or guard
   records that decision, and shall retain no identifying token in doing so.
6. If removing a reproduction would leave a document asserting a conclusion
   whose stated basis no longer exists, then the purge shall restate that
   document's basis in terms that survive the removal rather than leave an
   unsupported claim.
7. The purge shall leave the gitignored source workbooks and third-party page
   scans on disk and uncommitted, and shall not add them to the repository.

### Requirement 2: Retirement of live references to the removed material
**Objective:** As a reader or a build of the published repository, I want no
configuration entry, key-reference pointer or comment that resolves to a file
that no longer exists, so that the repository does not describe itself
inaccurately and no build rule silently does nothing.

#### Acceptance Criteria

1. When the removal is complete, the fitdocs repository shall contain no
   packaging-configuration entry whose only effect was to exclude a removed path
   from a built artifact.
2. When the removal is complete, `CLAUDE.md` shall not present the removed
   writeup as a key reference.
3. The fitdocs repository shall contain no comment or prose pointer directing a
   reader to a removed path as a file they can open.
4. Where a repository rule remains necessary after the removal — in particular
   the ignore rule keeping the source workbooks out of the repository — the
   purge shall retain that rule and shall correct only the pointer and the
   explanatory comment that accompany it.
5. Where a tracked file names a removed path solely as the historical subject of
   its own removal, the purge shall retain that mention in a form carrying no
   identifying token, and shall not present the path as present or expected.

### Requirement 3: Re-introduction guards survive the removal and stay discriminating
**Objective:** As the maintainer, I want the guards that stop the material being
re-added to keep working after the material they currently read is deleted, and
to keep proving they could still fail, so that the removal does not silently
disarm the only mechanism preventing its reversal.

#### Acceptance Criteria

1. When the encumbered material is absent from the working tree, the
   re-introduction guards shall execute to completion and report a result,
   rather than error on a missing file or fail on an emptied source set.
2. The re-introduction guards shall detect the removed material in a scanned
   source tree and in a built artifact without any file in the fitdocs
   repository holding that material verbatim.
3. Where a guard asserts that content is absent, the guard shall additionally
   demonstrate in the same run that its matcher finds an instance which is
   genuinely present.
4. When the removal deprives a guard of its existing positive control, the purge
   shall provide a replacement control that depends on no removed file.
5. The purge shall record, for every re-based guard, the single-line mutation
   that makes that guard fail, together with observed evidence that the mutation
   was applied and the guard did fail.
6. Where re-basing a guard removes a property that guard previously held — in
   particular the ability to verify its detection data against the source files
   the data was transcribed from — the fitdocs repository shall state that the
   property is gone and that the detection data is thereafter unverifiable by
   construction, rather than leave the loss implicit.
7. If a guard's detection data would itself constitute a copy of the removed
   material or of an identifying token, then the purge shall not retain that
   data in the fitdocs repository in any form from which the material or the
   token can be read back.

### Requirement 4: Honest reversal of the approved retention rulings
**Objective:** As a future session reading the approved documents, I want them to
say that retention was decided and then reversed, and why, so that I neither
restore the material nor conclude it never existed.

#### Acceptance Criteria

1. When the reversal is complete, no steering document and no spec document
   shall instruct a session to retain, restore, or leave in place the removed
   material.
2. The fitdocs repository shall state, in each document that previously
   instructed retention, that the material was retained as a research record,
   that the retention was reversed on 2026-07-30, and the reason the reversal
   was taken.
3. Where a completed task in an approved spec carries an instruction this purge
   reverses, the fitdocs repository shall record the reversal as a declared
   cross-boundary correction made by this spec, and the purge shall not reopen
   the corrected spec or reset its approvals.
4. When the reversal is complete, `/kiro-spec-status training-load` shall report
   the same completion state it reported before the reversal.
5. The fitdocs repository shall not present the reversal as if the material had
   never been present, and shall not present the original retention as an error
   of judgement rather than a decision taken under different circumstances.

### Requirement 5: Removal of personal contact details
**Objective:** As the third party named in the repository and as the maintainer,
I want neither of our personal email addresses to survive publication, in the
tree or anywhere in history, so that publishing does not expose a contact detail
neither of us placed there for that purpose.

#### Acceptance Criteria

1. When the purge is complete, no file at any commit reachable from any ref
   shall contain the third party's personal email address.
2. When the purge is complete, no file at any commit reachable from any ref
   shall contain the maintainer's personal email address.
3. When the purge is complete, every commit reachable from any ref shall carry
   the maintainer's non-personal address in both its author and its committer
   headers.
4. Where a file's purpose was to document the removal of a personal address and
   it stated that address in order to do so, the purge shall replace that file
   with a record documenting the same removal without restating the address.
5. If a spec document uses the third party's address as example data in a
   configuration illustration, then the purge shall remove the address and leave
   the illustration otherwise intact.
6. The purge shall introduce no new personal email address into any file it
   creates or edits.

### Requirement 6: Quiescence precondition before the replacement
**Objective:** As a peer session with work on a branch, I want the history
replacement to refuse to run while my work is unlanded, so that a one-shot
destructive operation cannot orphan it without a deliberate decision.

#### Acceptance Criteria

1. When the purge reaches the history replacement, the purge shall first
   establish whether any branch other than `main` exists, whether any
   additional worktree exists, and whether any tracked file is modified or
   staged in any tree.
2. If any branch other than `main` exists, or any additional worktree exists, or
   any tree carries uncommitted tracked changes, then the purge shall halt
   without replacing anything and shall report exactly what it found.
3. When the purge halts on a quiescence check, the fitdocs repository shall be
   left in the state it held before the check, with no ref replaced and no
   history destroyed.
4. When the purge halts on a quiescence check, the purge shall record the halt
   and its cause in the shared agent log.
5. When the replacement proceeds, the purge shall record in the shared agent
   log that it is proceeding, before the first ref is replaced.
6. Where a branch is deliberately abandoned rather than landed, the purge shall
   proceed only after that abandonment is recorded, and shall name the abandoned
   branch in that record.

### Requirement 7: The material is unreachable from every local ref
**Objective:** As anyone who clones the published repository, I want no commit,
tree or blob in it to carry the removed material, so that the removal is a
property of the artifact rather than of its tip.

#### Acceptance Criteria

1. When the history replacement is complete, no object reachable from any ref
   in the fitdocs repository shall be a copy of a removed file or reproduce its
   content.
2. When the history replacement is complete, the fitdocs repository shall
   contain no ref under `refs/original/`, and the two implementation branches
   held only there shall no longer exist.
3. When the history replacement is complete, the fitdocs repository's reflogs
   shall reference no pre-replacement commit, and unreachable objects shall no
   longer be present in its object database.
4. The purge shall verify unreachability by inspecting what the repository
   actually contains after the replacement, and shall not treat a passing test
   suite as evidence of it.
5. When a fresh clone is taken from the replaced repository, the clone shall
   contain no copy of the removed material at any commit.
6. If a pre-replacement object identifier is requested directly from the
   replaced repository, then the request shall fail rather than return the
   object.
7. If verification shows the material still reachable after the replacement,
   then the purge shall correct and re-verify before any push, rather than push
   and replace a second time.

### Requirement 8: The canonical remote no longer serves the material, and the retained one stays private
**Objective:** As the maintainer publishing the repository, I want the removal to
hold on GitHub and not only on my machine, so that making the repository public
does not publish objects the remote is still willing to serve.

*(Amendment 3, 2026-08-22 — the subject of this requirement is narrowed, and
the narrowing is stated here rather than inferred in design prose.)* The
maintainer retains `fitdocs_oss` rather than deleting it, and re-points
`origin` at `fitdocs`, which becomes the canonical repository. **"The remote"
below therefore means the canonical repository — the one this project pushes
to and may one day make public.** `fitdocs_oss` is not a remote of it: after
8.4 re-points `origin` it is no repository's remote at all, and the criteria
below never reach it.

That narrowing is honest only if what it excludes is stated with it, so:
**the retained `fitdocs_oss` keeps serving the removed material, in full,
indefinitely.** The objective's *"on GitHub and not only on my machine"* is
therefore met for the canonical repository and **not** for GitHub as a whole,
and the completion claim this requirement supports is *"satisfied with respect
to the canonical repository"* — never a bare *"the remote no longer serves
it"*. No criterion of Requirement 7 or Requirement 11 needs the same
treatment: checked, and none of them mentions the remote at all — they bind
*"the fitdocs repository"*, *"the replaced repository"*, *"any tracked file"*
and *"any built artifact"*, none of which reaches `fitdocs_oss`. What does
need scoping is the Amendment 1 *prose* asserting that *"This decision does
not weaken any unreachability requirement"* — it names Requirements 7, 8 and
11 together and speaks of the remote, it was written of the replacement
mechanism, and it does not extend to this ruling, which does weaken
reachability on the remote, deliberately and by maintainer decision. It is
scoped in place where it appears. What keeps the excluded material unpublished is not this requirement
but `fitdocs_oss`'s privacy, which criterion 8 below makes a standing duty.

#### Acceptance Criteria

1. When the purge reaches remote reconciliation, the purge shall establish
   empirically what the canonical remote actually serves after the chosen
   reconciliation action, and shall not assume that any particular action — a
   forced update or repository recreation alike — removes the objects.
2. When the remote reconciliation is complete, a fresh clone taken from the
   canonical remote shall contain no copy of the removed material at any
   commit.
3. When the remote reconciliation is complete, a direct request to the
   canonical remote for a pre-replacement object identifier shall not return
   the removed material.
4. If the canonical remote still serves the removed material after the chosen
   reconciliation action, then the purge shall reconcile it by whatever
   further means the measurement shows to be sufficient, and shall not declare
   reconciliation complete while the measurement disagrees. *(Amendment 3: the
   retained `fitdocs_oss` serving that material is not this criterion's
   subject and does not bar completion — that exemption is the whole content
   of the narrowing above, and is recorded rather than achieved.)*
5. When the remote reconciliation is complete, the canonical remote's refs
   shall match the replaced local refs, and no pre-replacement ref shall
   remain on it.
6. The purge shall record the measurement it made of the canonical remote's
   behaviour and the reconciliation it chose, so that a later reader can tell
   which action was required rather than which was assumed. *(Amendment 3: the
   record shall also state the retention, its grounds, and what it excludes —
   a record that omits the retained copy fails this criterion.)*
7. The purge shall not make **either** repository public — neither the
   canonical repository nor the retained `fitdocs_oss`.
8. *(Amendment 3.)* The purge shall record that `fitdocs_oss` must remain
   private for as long as it exists, and why: it holds the removed material in
   full, and its privacy is the only thing keeping that material unpublished.
   This is a standing duty on the maintainer, not a measurement the purge
   takes once.

### Requirement 9: Provenance record and repair of invalidated commit references
**Objective:** As a future session following a queue item's evidence or auditing
what was removed, I want a durable record of both history operations and an
honest, uniform position on every pre-replacement commit reference, so that the
purge does not silently invalidate the repository's own audit trail.

#### Acceptance Criteria

1. When the purge is complete, the fitdocs repository shall contain a provenance
   record stating what was removed, when, why, and by which spec.
2. The provenance record shall document both the 2026-07-26 email rewrite and
   the history replacement, and shall carry no personal email address, no
   removed material and no identifying token.
3. The provenance record shall state that the history replacement preserved no
   pre-replacement commit, shall name the root commit it produced, and shall
   state once that every pre-replacement commit identifier is thereafter
   permanently unresolvable, there being no mapping by construction.
   *(Amendment 1; formerly a complete pre-to-post commit map.)*
4. When the purge is complete, no open queue item's `pinned_at:` field shall
   present a pre-replacement commit identifier as resolvable, and every open
   item shall be repaired to a single documented convention rather than by
   item-by-item improvisation. *(Amendment 1.)*
5. The fitdocs repository shall state a position on closed queue items' pinned
   references and on the queue schema documentation's example pin, whether that
   position is repair or declared staleness.
6. The fitdocs repository shall state a position on the tracked test fixture
   whose filename names a pre-replacement commit, whether that position is a
   rename or a recorded acceptance that the name is historical.
7. When the purge is complete, the prior rewrite map shall no longer exist in
   the working tree.
8. The purge shall substitute no plausible post-replacement commit for any
   pre-replacement reference — in a pin, a document, or the provenance record.
   *(Amendment 1; the prior per-pin unresolvability fallback is now the
   uniform rule, since no pre-replacement commit has a counterpart.)*

### Requirement 10: No validation or behaviour regression
**Objective:** As the maintainer, I want the replaced repository to be
functionally the repository I had, minus the removed material, so that a
history operation cannot quietly change what the tool does.

#### Acceptance Criteria

1. When the purge is complete, the full test suite, `ruff check`,
   `ruff format --check` and `mypy` shall all pass on the replacement root's
   tree.
2. The purge shall change no value the tool computes, no rendered document, and
   no shipped output.
3. When the replacement root's tree is compared with the certified
   pre-replacement tip tree, the two shall be identical. *(Amendment 1: every
   change this spec makes lands on `main` before the tip is certified, so the
   fresh root carries the certified tree unchanged; formerly a
   differ-only-in-enumerated-files comparison across the rewrite.)*
4. When a built sdist and a built wheel are inspected after the purge, neither
   shall contain the removed material at any path.
5. If validation fails on the replacement root's tree, then the purge shall
   treat the replacement as incomplete and shall not push to the remote until
   validation is green.

### Requirement 11: Erasure of the third party's identity
**Objective:** As the third party whose methodology was evaluated and withdrawn,
I want no form of my name or my trademarks to appear in the published repository
or its history, so that a public, search-indexed record of unlicensed
redistribution is not attached to my identity.

#### Acceptance Criteria

1. When the purge is complete, no file at any commit reachable from any ref
   shall contain an identifying token.
2. When the purge is complete, no path at any commit reachable from any ref
   shall contain an identifying token, including paths belonging to the
   withdrawn implementation package that no longer exists in the working tree.
3. When the purge is complete, no commit message at any commit reachable from
   any ref shall contain an identifying token.
4. When the purge is complete, no file at any commit reachable from any ref
   shall contain the third party's copyright notice or trademark notice.
5. The fitdocs repository shall retain the fact that a third-party methodology
   was evaluated, found to carry a redistribution restriction, and withdrawn,
   without identifying the methodology or its author.
6. Where a tracked file records a decision, an amendment, a licensing
   constraint, or a historical finding that named the third party, the purge
   shall redact the identity, retain the record, and not falsify what the record
   states.
7. If a guard detects re-introduction by matching an identifying token
   literally, then the purge shall re-base or retire that guard so that no
   identifying token is retained in the fitdocs repository in any form from
   which it can be read back.
8. Where a guard's detection depends on data supplied from outside the fitdocs
   repository, the guard shall report a distinguishable result when that data is
   absent, and shall not report success as though the check had run.
9. Where re-basing or retiring a guard gives up detection the fitdocs repository
   previously had, the fitdocs repository shall state what detection was given
   up, rather than leave the loss implicit.
10. The purge shall introduce no identifying token into any configuration key,
    environment-variable name, or documented example that a tracked file or a
    built artifact contains.
11. When the purge is complete, the recorded calculator identity in every
    retained prior-format payload fixture shall carry no identifying token, and
    the fitdocs repository shall record that the fixture is thereafter synthetic
    rather than an authentic recovered artifact.
12. The purge shall substitute no replacement proper name for an erased
    identifying token, and shall introduce no personal name of any third party
    into any file it creates or edits.
13. The fitdocs repository shall state a position on untracked state that the
    purge carries across and that still contains an identifying token, whether
    that position is redaction or a recorded acceptance that the state is never
    published.

### Requirement 12: Retirement of the replacement machinery *(added by Amendment 1, 2026-08-17)*
**Objective:** As the maintainer of the published repository, I want the
tooling that existed only to plan, execute, or verify the history operation
gone once that operation is verified, so that machinery with no remaining
purpose does not keep generating maintenance work, review findings, and false
confidence.

#### Acceptance Criteria

1. When the history replacement is verified, the fitdocs repository shall not
   retain modules, scripts, or tests whose only purpose was to plan, execute,
   or verify the in-place history rewrite or the history replacement.
2. The retirement shall retain every re-introduction guard Requirements 3 and
   11 require, and each retained guard shall still execute, still report a
   result, and still be demonstrably able to fail after the retirement.
3. The retirement shall retain the provenance record and the recorded evidence
   of the purge, and shall remove no record Requirement 4 or Requirement 9
   requires.
4. Where the retirement removes detection or verification capability the
   fitdocs repository previously had, the fitdocs repository shall state what
   was given up, rather than leave the loss implicit.
5. The retirement shall occur after the history replacement is verified and
   before the repository is made public.

# Brief: encumbered-content-purge

## Problem

fitdocs is about to be published: the repository goes public and 0.1.0 ships
as an sdist. Two files in the tree carry the third party's copyright notice
and a trademark notice, with redistribution permission never
obtained — and they are reachable from **every commit on `main` back to the
root**, so making the repository public publishes them whatever the working
tree looks like on the day.

The methodology was already withdrawn from the *shipped tool* (training-load
Amendment 2, 2026-07-25, `63863612b`). What was deliberately kept was the
research record. Publishing changes the calculus that decision was made
under: a private research record and a public one are not the same artifact.

Two smaller exposures ride the same surface — a third party's personal email
address in three tracked files, and the maintainer's personal Gmail in
cleartext in a tracked file whose entire reason for existing is to document a
prior rewrite that removed that address from commit headers.

## Current State

**The encumbered material** (both extracted verbatim from the third party's
workbook, per §6 of the writeup):

- **The reference writeup** — 183 lines: the zone table with
  points-per-minute, the continuous and interval point formulas with worked
  examples, per-repeat adjustment and discount-factor tables to eight decimal
  places, and weather/terrain pace-adjustment tables.
- **The performance-levels extracted table** — 73 rows, performance
  level → equivalent race times.
- **The paces-by-zones extracted table** — 74 rows, performance level →
  training pace range per zone.

The source `.xlsx` workbooks were **never committed** (`.gitignore:30`;
`git log --all --diff-filter=A -- '*.xlsx'` is empty). Same for the Banister
and Morton scans at the repo root (`.gitignore:41-42`).

**Three approved documents instructed, at discovery, that the material
stays**, and this spec reverses all three. None of those instructions still
stands:

- `.kiro/steering/roadmap.md` — the retention instruction is reversed in
  place, and the reversal is dated there
- `.kiro/steering/structure.md` — likewise reversed in place and dated there
- `.kiro/specs/training-load/design.md` (WithdrawnCalculatorRemoval) and its
  `tasks.md` task-5.2 bullet — both retention instructions were removed in
  `f1ef31b`, and each site now records the reversal instead

`CLAUDE.md:13-14` points at the writeup as a key reference and goes stale with
it.

**Two guards read the material to do their job**, and both break on deletion:

- `tests/load/test_packaging.py`'s deleted writeup-sourced-constant test
  opened the reference writeup at test time, and held five
  discount factors transcribed verbatim from it as `_WITHDRAWN_TABLE_VALUES` —
  the values are deliberately not reproduced here, see the constraint below.
- `tests/test_docs_guarantees.py`'s deleted writeup-mentions-the-methodology
  positive control opened the same file, proving the sibling absence-guard was
  not vacuous.

**History**: **exactly one** commit on `main` touches these paths — the **root
commit** (`32aed726e`, "Initial repo setup"), which introduced the writeup and
both CSVs and never modified them afterwards. That single fact is the whole
difficulty, and it cuts the opposite way from a larger number: the material is
not confined to a span of history that could be rewritten in isolation, it is
in the *initial tree*, so **every commit on `main` carries it** and a purge
rewrites all of them. No tags exist. `refs/original/refs/heads/*` retains the
pre-rewrite tips from 2026-07-26 — including the **only** copies of
`impl/athlete-benchmarks` and `impl/training-load`, which exist as no live
branch; one further commit touching these paths is reachable from those refs
and from nowhere else.

**Remote** *(as measured when this brief was written; superseded below —
`origin` is re-pointed by task 8.4)*: `origin` **was**
`git@github.com:joshua-stauffer/fitdocs_oss.git`, private, no other
contributors. `origin/main` was at `9e508e1` and fell further behind local
`main` with every merge — the CSVs were **already pushed**.

**Remote, superseded 2026-08-22**: the maintainer supplied
`git@github.com:joshua-stauffer/fitdocs.git` as Major 8's target, so what
Decision 6 anticipated as a delete-and-recreate under the same name is in fact
a **rename**, `fitdocs_oss` → `fitdocs`. Measured that day: the new repository
exists and is empty (`git ls-remote` exits 0 with zero refs) and the old one is
still live. The nine tracked references naming the old repository — the OSM
`User-Agent` in `src/fitdocs/tiles.py` and the ownership-contract URL in
`src/fitdocs/declaration.py` among them — were updated on `chore/repo-rename`
**before** task 8.1 certified the tip, because Req 10.3 makes the replacement
root's tree identical to that tip and Amendment 1 left no later redaction step.
The local working directory keeps its `fitdocs_oss` name; only the published
URLs moved.

**Remote, ruled 2026-08-22 (Amendment 3)**: `fitdocs_oss` is **retained** —
not deleted, not rewritten — and `fitdocs` becomes the canonical source. The
old repository therefore keeps serving the encumbered material indefinitely,
privately.

**Requirement 8 was amended textually** to admit that — its subject narrowed
to the canonical repository, criterion 8.4 given an explicit exemption for the
retained one, 8.7 widened to both, and a new 8.8 recording the standing
privacy duty. It is an **exemption**, not a scoping, and it appeals to no
precedent: an earlier draft called it a scoping and borrowed the
"recorded acceptance" pattern from Req 11.13 and Decision 7, and `design.md`'s
Amendment 3 retracts both — those two are authorised inside their own
criteria's text, where Requirement 8 authorised nothing. The narrowing's
ground is structural: task 8.4 re-points `origin` at `fitdocs`, after which
`fitdocs_oss` is no repository's remote at all.

What the ruling costs: the objective's *"on GitHub and not only on my
machine"* is **not** met for GitHub as a whole. `fitdocs_oss`'s privacy stops
being incidental and becomes the single property keeping the material
unpublished — and, per GitHub's documented fork behaviour, retention is also
what allows a private fork of it to persist where deletion would have reaped
one.

**Prior rewrite**: 2026-07-26, `git filter-branch --env-filter`, author and
committer email only; trees byte-identical. Its map was committed at a
tracked file that stated the maintainer's personal Gmail in cleartext on its
line 3, and shipped in the sdist. That file has since been retired; the
durable record now lives in the purge's provenance record.

**Third-party contact detail**: the third party's contact address appeared in
the reference writeup (its line 10, before removal),
`.kiro/specs/distribution/design.md:616`, and
`.kiro/specs/training-load/research.md:181`.

**Validation baseline**: the full suite, `ruff check`, `ruff format --check`
and `mypy` are all green on `main`, and must be green again on the rewritten
tree.

**Measure, do not quote.** Every count in this brief was superseded within a
day of being written, and the commit and queue figures moved again during the
requirements phase itself. The figures above are stated as properties for that
reason. Where a number is genuinely needed, derive it:

```
git show --stat 32aed726e   # the one commit introducing the removed material
git rev-list --count main                    # commits the rewrite touches
git rev-list --count origin/main..main       # how far the remote trails
grep -rl 'pinned_at:' .kiro/queue/           # SHA references the rewrite invalidates
uv run pytest --collect-only -q | tail -1    # suite size
```

## Desired Outcome

- Neither the writeup nor either table is reachable from any ref — local or on
  the remote — and a clone of the published repository contains no copy of
  them at any commit.
- The re-introduction guards still red if the material comes back, without the
  repository holding the material in order to recognise it.
- Steering and the training-load spec record the reversal honestly: not as if
  retention had never been decided, and not as if the material had never
  existed.
- No third party's contact detail and no personal address of the maintainer
  survives in the published tree or its history.
- Every peer branch in flight at purge time has landed; none is orphaned.
- The purge leaves a durable, self-describing record of what was removed and
  when, which does not itself carry the removed material.

## Approach

**Purge before publishing, while the repository is still private and has no
audience.** A history rewrite costs almost nothing today and grows more
expensive with every clone. This is a maintainer decision taken at discovery
(2026-07-30), together with two boundaries below.

Two majors, in order, because they have different risk profiles and different
notions of "verified":

1. **Tree removal and guard re-oracling** — an ordinary branch: delete the
   material, re-base the two guards on an oracle that survives it, move the
   three retention rulings, retire the rewrite map. Reversible; validated by
   the standard suite plus mutation evidence that the re-oracled guards can
   still fail.
2. **One history replacement of the resulting tree** — one-shot and
   destructive: certify the tip clean, create a fresh root commit whose tree
   is that certified tip, recreate the remote, and verify that no object at
   any commit reaches the removed material or the erased identity. Verified
   by unreachability, not by a green suite. *(As decided at discovery this
   major was an in-place rewrite of every commit, preserving a rewritten copy
   of the full history; that mechanism was replaced by Amendment 1 on
   2026-08-17, before it ever ran — see the amendment decision below. The
   discovery rationale in the paragraph above, "a history rewrite costs
   almost nothing today", is the claim the amendment measured and found
   false.)*

Splitting these into separate specs was considered and rejected: major 1's
"done" would be misleading on its own, because deleting from the tree while
history still serves the blobs achieves nothing this spec exists to achieve.

### Maintainer decisions taken at discovery (2026-07-30)

- **Depth: content only.** The verbatim tables and the extracted writeup go,
  from tree and history. The **name** stays where it records the decision —
  steering, spec documents, commit messages, and the guards that stop the
  material being re-added. Rationale: the redistribution exposure is the
  verbatim tables; a factual record that a methodology was evaluated and
  withdrawn is not redistribution. Rejected: scrubbing the name from shipped
  surfaces (costs the guards their subject), and total erasure (costs both the
  guard and the audit trail proving the removal, and rewrites nearly every
  tracked spec file).
- **`.kiro/` is public, and out of the sdist.** The planning record stays
  visible in the repository — it is the audit trail for this purge — while the
  package stays lean. The sdist exclusion is `distribution`'s work, not this
  spec's.
- **This spec lands before release work.** `distribution` proceeds at its own
  pace afterwards.

### Maintainer decision taken at Amendment 1 (2026-08-17)

- **History is replaced, not rewritten in place.** Major 2's mechanism as
  decided at discovery — a single `git filter-repo` pass over every commit,
  preserving a rewritten copy of the full history — is retired before ever
  running. In its place: after the tip is certified clean by the guards and
  oracles Majors 1–6 built, a **fresh root commit** is created whose tree is
  that certified tip, the remote repository is deleted and recreated, and the
  single new commit is pushed. Nothing in *Desired Outcome* changes — every
  unreachability property above stands — only the mechanism by which
  unreachability is achieved.

  Grounds, measured rather than assumed:

  - The discovery rationale "a history rewrite costs almost nothing today"
    was falsified by the work itself. Between spec initialization
    (2026-07-30) and this amendment, the rewrite's planning and verification
    machinery grew larger than the product it protects (measure:
    `wc -l scripts/purge/*.py; find tests/purge -name '*.py' | xargs wc -l`
    against `src/fitdocs`), and a substantial share of the open queue is
    findings about that machinery rather than about the product.
  - Each pre-run review round kept finding real under-redaction defects in
    the rewrite rules — matcher and rule sharing one implementation so
    neither could disagree, byte-domain versus text-domain regex divergence,
    case handling, tokens wrapped across line breaks and comment
    continuations. Every one was found before anything irreversible ran, and
    each was evidence that correctness of an in-place rewrite over every
    historical blob is an enumeration problem with a long tail.
  - A replacement is strictly stronger than a rewrite for every "unreachable
    from any ref" criterion: no rule set, however verified, can under-redact
    history that does not exist. The residual risk class the review rounds
    kept finding — a token shape the rules miss — is closed by construction
    rather than by enumeration.
  - The rewritten history's only consumer would have been the maintainer's
    local archaeology. The repository is pre-release and private, the remote
    is force-replaced or recreated under either mechanism, and GitHub's
    retention of unreachable objects (see *Constraints*) already made
    deleting and recreating the remote the likely endpoint of remote
    reconciliation anyway.

  What is given up, stated so it is not discovered later: commit-level
  history and `git blame`; the commit-message layer of the audit trail (the
  tree-level record in `.kiro/` survives at the tip, and Requirement 4's
  honesty obligations are unchanged); and every pre-replacement commit
  identifier at once, permanently, with **no mapping** — under a fresh root
  there is no post-replacement counterpart to map to, so the provenance
  record states that fact once instead of carrying a commit map.

- **The machinery retires with its purpose.** Once the replacement is
  verified, the modules, scripts and tests whose only purpose was to plan,
  execute or verify an in-place rewrite — or the replacement itself — go.
  The re-introduction guards that run against the tip stay, and must still
  demonstrably be able to fail. Rationale: machinery with no remaining
  purpose does not merely sit idle, it keeps generating maintenance work and
  review findings, which is a measurable share of why this spec's cost grew.

## Scope

- **In**: deleting the writeup and both tables from the working tree;
  re-basing the two guards that read them onto an oracle that outlives them;
  moving the retention rulings in `roadmap.md`, `structure.md`,
  `training-load/design.md` and `training-load/tasks.md`, and the pointer in
  `CLAUDE.md`; removing the third-party contact detail from the two spec files
  that survive; retiring the tracked rewrite-map file and replacing what
  it was for with a record carrying no personal address; retiring the now-dead
  `[tool.hatch.build.targets.sdist]` exclude entries; one history replacement
  — a fresh root commit of the certified tip *(Amendment 1; formerly an
  in-place rewrite across all refs with `refs/original` expiry, reflog expiry
  and garbage collection)*; recreation of the remote repository; local and
  remote verification that the material is unreachable at any commit;
  retirement of the machinery whose only purpose was the history operation,
  keeping the tip re-introduction guards *(Amendment 1)*.
- **Out**: `LICENSE`, classifiers, project URLs, the `.kiro/` and `tests/`
  sdist excludes, the README rewrite, the CI workflow, the changelog, and
  tag/publish — every one of these is `distribution`'s (see *Existing Spec
  Touchpoints*). Re-litigating the withdrawal itself. The gitignored `.xlsx`
  workbooks and Banister/Morton scans, which were never committed and stay on
  disk. Any change to what the tool computes.

## Boundary Candidates

- **Tree removal and rulings** — deletion plus the four documents that
  instruct retention; ordinary validation.
- **Guard re-oracling** — making a content guard work without holding the
  content; the only part of this spec with a genuine design choice.
- **History replacement and remote recreation** — one-shot, destructive,
  verified by unreachability across every ref *(Amendment 1; formerly the
  history rewrite and remote reconciliation)*.
- **Provenance record** — what replaces the rewrite map, and how a future
  session learns that a rewrite happened at all.

## Out of Boundary

- `distribution`'s packaging, documentation and release automation.
- The substance of the withdrawal decision (training-load Amendment 2, closed).
- The queue's `pinned_at:` SHA references, individually. The rewrite
  invalidates all of them at once; this spec owns *stating* that in one place,
  not repairing them one by one.

## Upstream / Downstream

- **Upstream** — **every unmerged branch must land first.** A root-commit
  rewrite orphans them all. In flight at discovery:
  `chore/sdist-content-keyed-guard` (+4, and it touches this spec's exact
  surface — `tests/load/test_packaging.py` and `pyproject.toml`),
  `chore/power-absent-sample-fill` (+2), `spec/fit-ingest-np-window-criterion`
  (+3). `refs/original/` additionally holds the only copies of two never-pushed
  implementation branches; whether those are worth preserving is a decision
  this spec must take rather than inherit.
- **Downstream** — `distribution`: once the material is out of the tree,
  Requirement 6's artifact-scanning gate changes subject for the second time.
  Every future clone of the repository. Any session reading a queue item's
  `pinned_at`.

## Existing Spec Touchpoints

- **Extends**: none.
- **Reverses**: `training-load`'s WithdrawnCalculatorRemoval retention ruling
  (`design.md`, `tasks.md:264`). A declared cross-boundary correction to a
  shipped spec, in this spec's own change — not a reopening of `training-load`.
- **Adjacent**: `distribution`. Its Requirement 6 already has a queued
  amendment
  (`.kiro/queue/2026-07-30-distribution-req6-assumes-a-bundled-calculator.md`,
  high) written before this purge was decided; that amendment should be
  written *after* this spec lands, so it amends once against the final state
  rather than twice. Its unbuilt artifact-licensing gate
  (`distribution/design.md:279-295`, and
  `.kiro/queue/2026-07-30-no-release-gate-on-the-publish-path.md`) stays
  `distribution`'s to build.

## Constraints

- **Force-push is authorised**: the repository is private with no other
  contributors, stated by the maintainer at discovery.
- **A force-push may not be sufficient on its own.** GitHub can retain
  unreachable objects after a forced update, leaving old blobs fetchable by
  SHA until it garbage-collects — which the maintainer does not control.
  *(Amendment 1 settles the question this constraint left open: the remote
  repository is deleted and recreated rather than force-pushed over, which
  removes the retention behaviour along with the repository. The empirical
  obligation survives as verification — establish what the recreated remote
  actually serves; do not assume recreation worked.)*
- **Do not transcribe the fingerprinted values into any file in this
  repository, including this spec's own documents.** The content-keyed sdist
  guard (`tests/load/test_packaging.py`, `_WITHDRAWN_CONTENT_FINGERPRINTS`, live on
  `main` since `07ae0a0`/`f0dbf2b`) scans every member of a built sdist by
  content, not path, and exempts exactly one file — its own module. `.kiro/`
  currently ships in the sdist, so a planning document that quotes the values
  reds the suite. This was found the honest way: the first draft of this brief
  listed all five and the guard failed the build. Write about them by
  reference.
- **The guard oracle problem.** A guard against specific content cannot
  recognise that content without some representation of it. Two candidates,
  for design to choose between with evidence: keep the five discount factors
  as de-minimis numeric constants, or store a salted digest and hash candidate
  literals found in the scanned artifact. The second holds no verbatim value;
  it costs a more complex scan and a salt that must itself be durable.
  Whichever is chosen, the guard owes mutation evidence that it can still fail
  — `.kiro/steering/change-protocol.md` › Fixture Discrimination, and the
  precedent in `.kiro/queue/2026-07-30-sdist-guard-has-no-positive-control.md`
  where a one-character change defeated a guard with 2286 tests green.
- **The rewrite invalidates every commit SHA in the repository.** *Every* queue
  item carries a `pinned_at:` field — open, closed, and the README's schema
  example alike, with no exceptions;
  `tests/fixtures/report_baseline_faa6d09.py` names a commit in its own
  filename; the retired rewrite-map file was a table of
  nothing but SHAs. Design owes a stated position on each class.
- **No validation regression**: the suite, `ruff check`, `ruff format --check`
  and `mypy` are green today and must be green after, on the rewritten tree.
- Personal data never lives in the repository — the data-root contract in
  `.kiro/steering/tech.md` — which this spec extends in practice from fitness
  data to personal contact details.

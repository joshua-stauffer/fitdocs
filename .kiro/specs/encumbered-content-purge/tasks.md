# Implementation Plan

## Naming convention used by this document

This document is in scope for the purge it plans — Req 1.3 puts every tracked
file in scope and Req 11.1 forbids an identifying token in any of them — so it
does not write the material or the identity it schedules for removal. It
inherits the vocabulary of `requirements.md` and `design.md`: **the withdrawn
methodology**, **the third party**, **the identifying tokens**, **the writeup**,
**the extracted tables**, **the withdrawn calculator package**, **the
token-bearing queue items**, **the source workbooks**, **the value constants**,
**the v1 payload fixture**, and — since Amendment 1 — **the history
replacement**, **the certified tip** and **the `.git` archive**. Any path not
written literally below is one of those.

## Execution rules that bind every task

- **No task rests on a count.** `requirements.md` refuses to let any criterion
  depend on one, because every figure discovery wrote down was superseded within
  a day. Three of this plan's own draft figures had already drifted before it was
  reviewed. Where a task says *every* member of a class, enumerate the class at
  execution time; where `design.md` quotes a number, treat it as a shape to
  re-measure, never as a budget.
- **Line citations are not used.** They drift on rebase and have already been
  falsified once in this spec. Locate by name.
- **Majors 1–6 landed as one branch and stand as the record of that work.**
  Major 7 is ordinary branch work again: it re-scopes the machinery for the
  replacement and must be merged, its worktree removed, before Major 8 starts,
  because the quiescence gate halts while any extra branch or worktree exists.
  Major 8 is the one-shot history replacement, run solo on `main` in the
  primary worktree. Major 9's aftermath tasks each land on a short-lived
  branch created on the new history, which restores the ordinary protocol.
- **Two probes, not one.** The value matcher finds reproduced tables; the
  forbidden-string matcher finds identifying tokens and removed-path fragments.
  Neither sees what the other sees, so an observable that names only one of them
  is vacuous for half the work it claims to cover.
- **Amendment 1 (2026-08-17) regenerated Majors 7–8 in place.** The retired
  plan's tasks 7.2–7.4 and 8.1–8.5 — the in-place rewrite, the clone
  adoption, the commit map and both manifest comparisons — were replaced
  before any of them ran. References to those task numbers inside the landed
  majors' bodies and the Implementation Notes describe the retired plan; M0,
  M1 and the spec-status baseline remain scratch evidence of Major-1-era
  claims and carry no cross-replacement role. Task 7.1 stands as landed work:
  it ran on 2026-08-16 and its outcomes are durable.
- **Decision 7's commitments are fixed constraints, not options** (maintainer,
  2026-08-17; stated in full in `design.md` › `HistoryReplacement`): the
  working directory and its untracked material are never moved and never
  deleted; the fresh object database arrives by swapping `.git`, never by an
  in-place prune; the old `.git` is archived, not deleted; the carry-over
  checklist is re-scoped to the `.git`-resident items with the shared agent
  log first among them. No task below proposes — and no implementer may
  substitute — an in-place prune, a clone adoption, or deletion of the old
  `.git` or the working directory.
- **The declared correction this plan carried at the retired task 8.3** — the
  M1 rename carve-out in `design.md` › ValidationGate — is superseded along
  with the comparison it corrected: Req 10.3 is now a tree identity, settled
  by one command, and no manifest comparison crosses the replacement.
- **This plan carries one new declared correction to `design.md`, applied in
  place by task 7.4.** Every `design.md` sentence stating the post-swap
  porcelain check as a bare porcelain status returning empty — enumerated at
  execution time; three at review time, in `HistoryReplacement` step 7, the
  `ReplacementVerification` table and `ValidationGate`'s restatement — is
  measured false in this repository: the root agent-log symlink is untracked
  and ignored by no rule, and Decision 7 guarantees untracked material
  survives the swap, so an untracked-files-included porcelain can never be
  empty and the row as written is a guaranteed swap-back trigger. The row is
  scoped to tracked files — the identity claim was always about tracked
  state coinciding with the root's tree. The same convention covers the
  provenance record's part one: 7.8 and 9.2 correct its forward-looking
  references in place, the historical record of what Majors 1–6 did is never
  rewritten, and `design.md`'s "stand as written" is Req 12.3's retention
  rule, not a bar on correcting a promise of an artifact Amendment 1
  withdrew.
- **It still carries one declared in-place deliverable**: task 3.3 wrote the
  neutral vocabulary into the `IdentityErasure` component of `design.md`
  rather than into a file of its own. The Component → file map gives
  `IdentityErasure` no module or file, so a new tracked artifact would have
  required amending that map, and the section already states the vocabulary
  rule. *(The original rule's other ground — co-location with the retired
  rewrite's path-renaming directives — went with the mechanism at Amendment 1;
  the deliverable itself stands and the landed tasks consumed it.)* Declared
  here because that is where this plan says such edits are declared — not a
  re-opening of the design phase, and no approval flag moved.

---

- [x] 1. Scaffold the purge tooling package and capture the pre-change baselines
  - Create the `scripts` package and the `scripts/purge` package, plus the
    `tests/purge` test package, so every later module has a home that already
    imports
  - Wire the single CLI entry point with **all nine subcommands present as
    stubs** — manifest, preflight, fingerprints, plan, rewrite, verify-local,
    adopt, verify-remote, pins. Later tasks fill in their own module and never
    edit the dispatch file, which is what makes Major 5 parallel-safe
  - Add `scripts` to the type-checking perimeter in the same change, per the
    sequencing rule stated in that config block
  - Build the manifest generator: path, mode and blob identifier per row, taken
    against a **named commit** rather than against the working tree, so the
    baseline can be regenerated after edits have started
  - Record the base commit identifier and emit the **M0** manifest against it —
    the commit before the first edit of this feature — to a scratch path outside
    the repository. M0's blob identifiers are what let 8.3 prove no golden
    document moved, after the commit itself has ceased to exist
  - Capture the **spec-status baseline** for `training-load` to the same scratch
    path. Unlike the manifests it is computed output, not a tracked file, so it
    cannot be recovered from a commit once the rewrite has run — and 6.2 has to
    compare against it
  - Observable: the CLI's help output lists all nine subcommands; the manifest
    subcommand writes M0 with one row per tracked path; the captured
    spec-status baseline records the requirement, criterion and completed-task
    counts and all six approval booleans; `uv run mypy` is clean with `scripts`
    inside the perimeter
  - _Requirements: 4.4, 10.3_

- [ ] 2. Detection: the oracles, the match data, and the one-shot acceptance

- [x] 2.1 Build the content-value matcher
  - Implement tokenisation, canonicalisation, entropy estimation, windowing,
    digesting and scanning of numeric values as the single shared definition; no
    guard and no script may write a second
  - Canonicalisation is format-independent: clock times to total seconds,
    decimals to a canonical float representation, so two spellings of one value
    canonicalise equal
  - Windowing emits minimal-length windows clearing the entropy floor, advancing
    the cursor past each emitted window and dropping a tail that cannot reach the
    floor rather than emitting it short
  - Scanning tries every offset, which is the property that makes a match
    phase-independent
  - State the entropy floor in the module as a named parameter with its
    rationale, not as a bare number
  - Add the module to the type-checking perimeter in the same change that creates
    it
  - Observable: unit tests show two spellings of one value canonicalising equal
    and two different values not; a run of trivially small integers emits no
    window; a match is found at a non-zero offset, and reducing the scan to
    offset zero reds that test and no other
  - _Requirements: 3.2, 3.7_
  - _Boundary: ContentOracle_

- [x] 2.2 Build the forbidden-string loader
  - Implement the loader that reads match data at run time from the file named by
    a single, neutrally-named environment variable, so the repository holds none
    of the strings it is forbidden to contain
  - Returning nothing is the **only** silent outcome and it happens **only** when
    the variable is unset; a variable that is set but names a missing, unreadable
    or empty file, or a path resolving inside the repository working tree, raises
    instead
  - Implement the skip-or-load helper the guards call, so an absent source is a
    distinguishable result and never a reported pass
  - Implement case-insensitive matching that returns **every** match rather than
    the first, so a failure can name what it found without the caller holding it
  - Implement the tree scanner over both a file's content and its **path name**,
    taking the scanned root as a parameter rather than a repository constant, so
    a positive control can run against a synthetic tree
  - Add the module to the type-checking perimeter in the same change that creates
    it
  - Sequential rather than parallel with 2.1 despite disjoint modules: both add a
    line to the same type-checking perimeter list
  - Observable: four separate tests show the loader **raising** for missing,
    unreadable, empty and in-repository sources — collapsing any of them into the
    unset outcome is the defect being pinned; a fifth shows the unset variable
    producing a skip, asserted as the skip exception rather than as a pass
  - _Requirements: 3.3, 3.4, 3.7, 11.8, 11.10_
  - _Boundary: ForbiddenStrings_

- [x] 2.3 Assemble the out-of-repository forbidden-string file
  - Build the match-data file itself, at a path **outside** the repository
    working tree, in the format 2.2's loader reads. Without it every token check
    in this plan degrades to a skip — which is exactly the failure Req 11.8
    exists to make visible — and six later tasks consume it: the stale-pointer
    enumeration, the standing guard's controls, the two verification runners and
    both acceptance runs
  - Populate **both** categories the format defines: every identifying token, and
    every removed-path fragment. The path category is what carries Req 2.3's
    stale-pointer enumeration, which has the same recursion problem as the tokens
    — a search for a removed path must name the removed path — and one
    out-of-repository source solves both
  - Enumerate the path fragments **while the material is still in the tree**, so
    this task must complete before 3.1. Enumerate the tokens from the tracked
    tree, the tracked path names and the commit messages, so the file covers what
    the history rewrite will have to match, not only what the tip carries
  - The file is never tracked, never enters a built artifact, and is destroyed
    with the working repository. Record its location and its category counts, not
    its contents, anywhere durable
  - Observable: the loader from 2.2 reads the file without raising and reports a
    non-empty value set; a deliberate probe confirms at least one entry of each
    category matches something currently in the tree, so the file is proven live
    rather than merely present; the file's resolved path is asserted to lie
    outside the repository working tree
  - _Requirements: 2.3, 11.7_
  - _Depends: 2.2_
  - _Boundary: ForbiddenStrings_

- [x] 2.4 Generate the fingerprints and run the one-shot evasion acceptance
  - Build the one-shot generator and run it **while the material is still on
    disk** — this task must complete before any deletion in Major 3
  - Emit the generated data as a separate module beside the matcher — salt,
    entropy floor, digest length, the digest set and the window lengths — so the
    matcher and its data can be reviewed apart. The salt is committed and
    published deliberately; the entropy floor carries the security
  - In the same invocation, run the catalogued evasions from the withdrawal-
    evasions queue item against the **real** files: a verbatim re-add, a renamed
    and reformatted re-add, a table pasted as language literals into an
    allowlisted module, and a copy under a different extension — plus the
    single-constant paste that is the only positive-detection evidence the
    existing guard has ever had
  - Record each evasion result pass or fail, for the provenance record. This is
    the last moment at which the oracle can be tested against its real subject;
    after 3.1 it can never be repeated
  - Observable: the generated data module holds a non-empty digest set and a
    non-empty window-length set; the acceptance run reports a pass/fail line per
    catalogued evasion; the writeup and both extracted tables are flagged and a
    control file without them is not
  - _Requirements: 3.2, 3.7_
  - _Depends: 2.1_
  - _Boundary: ContentOracle_

- [ ] 3. Tree: removal, inventory, vocabulary, and identity erasure

- [x] 3.1 Delete the encumbered material and the entries that existed only to exclude it
  - Extract the prior rewrite map's rows to a scratch artifact outside the
    repository **before** deleting the file — those rows are one of the three
    columns the commit map joins in 8.1, and the file does not survive this task.
    Its prose header is deliberately not extracted: that is where the
    maintainer's personal address lives
  - Delete the writeup, both extracted tables and the prior rewrite map from
    the working tree
  - Delete the packaging build-target section entirely — both exclusion entries
    and the comment above them, which reproduces the third party's copyright
    notice. This restores the packaging default and hands the exclusion question
    back to `distribution`, which owns it
  - Observable: none of the removed paths appears in `git ls-files`; the
    packaging configuration contains no build-target exclusion section; a built
    sdist contains no removed path; the extracted map rows exist at a scratch
    path outside the repository and their row count matches the prior map's
    pre-deletion row count
  - _Requirements: 1.1, 2.1, 9.7, 11.4_
  - _Depends: 2.3, 2.4_

- [x] 3.2 Produce the classified sweep inventory
  - Sweep every tracked file — the universe is `git ls-files`, not
    `docs/reference/` — through the value matcher, through a probe set for the
    **symbolic** reproductions no matcher can reach (the load formulas, the rule
    that generates the discount factors, the worked-example vectors), and through
    a probe set for all three personal identifiers including the git-constructed
    username-and-machine-name form
  - Run the stale-pointer enumeration separately, because no oracle covers it: a
    literal fixed-string search over the removed-path fragments supplied by 2.3,
    so the sweep's own input does not become the last copy of what it looks for
  - Run the token enumeration over tracked **contents** and tracked **path
    names**, which are different populations and drift independently
  - Classify every hit as stale pointer, dead packaging entry, guard, historical
    subject of its own removal retained under Req 2.5, or ignore rule with a
    stale pointer. The modified-files table in `design.md` names the sites that
    need work and is **not** the enumeration — a substantial share of the hits
    are the retained class, so "not in the table" must never silently mean "not
    considered"
  - Note for every later task in this major: fixed-string and Perl-regex search
    modes are required for word-boundaried probes; the extended-regex mode in
    this git build does not honour word boundaries and returns empty, which reads
    as a clean sweep
  - Observable: a classified inventory exists listing every hit with its
    disposition, retained for the provenance record; the inventory's file set is
    a superset of every file named in the modified-files table, and every extra
    is classified rather than dropped; re-running each enumeration reproduces the
    same hit set
  - _Requirements: 1.2, 1.3, 2.3_
  - _Depends: 2.1, 2.3, 3.1_
  - _Boundary: ReproductionSweep_

- [x] 3.3 Fix the neutral vocabulary and the identifier-renaming convention
  - Write the vocabulary down **once**, as the deliverable seven parallel tasks
    and the guard work all consume. Improvised per-file wording is how a sweep
    ends with five different names for one withdrawn thing
  - Fix the neutral prose forms — the ones this spec's own documents already use
    — and the replacement for every erased Python identifier, test function name
    and fixture constant, descriptive rather than coined
  - Fix the neutral stems for every token-bearing queue path, so 3.12 and the
    history rewrite in 7.2 apply the *same* stems and the tip and the history
    agree
  - **Substitute no replacement proper name anywhere.** That is the one outcome
    the maintainer explicitly declined, on the grounds that inventing a
    substitute risks colliding with a real person in a repository whose narrative
    is about copyright and permission
  - Observable: a written vocabulary table maps every erased form to its
    replacement, covering prose, identifiers, test function names, fixture
    constants and queue stems; every entry is checked against the forbidden-string
    file and none of the replacements matches it; no replacement is a proper noun
  - _Requirements: 1.5, 11.5, 11.12_
  - _Depends: 3.2_
  - _Boundary: IdentityErasure_

- [x] 3.4 Write part one of the provenance record
  - Create `docs/reference/history-rewrites.md` in the house style of that
    directory — no front matter, an H1 with an em-dash subtitle stating the
    document's disposition, a dated lede, and an explicit statement of what is
    not verifiable from the document itself
  - Section 1: what was removed, when, why and by which spec — **by description,
    never by value and never by name.** This is the section most likely to
    reintroduce a token by reflex, since its whole subject is what was removed
  - Section 2: the 2026-07-26 email rewrite described without restating either
    address, including that it left backup refs behind, and the disposition of
    the two branches those refs preserved. This section is what replaces the
    deleted rewrite map. **Corrected in place 2026-08-03**: this bullet read
    "destroys them and the two branches held only there", which hands the writer
    a conclusion the task supplies no evidence for. It got one attempt's invented
    reason rejected — measured from the deleted map's own header, neither branch
    was merged when the rewrite ran, and both landed afterwards by rebase. State
    the disposition on a basis you measure, or state that you did not measure it
  - Section 4: what is no longer verifiable — the guards' detection data cannot
    be checked against the files it came from, because those files exist nowhere;
    the purge's own probe sets, replacement specs and mailmap are scratch
    artifacts destroyed with the working repository. **Corrected in place
    2026-08-03**: this bullet listed the match-data file among them. That
    contradicts `design.md`'s destroyed-set enumeration and would instruct a
    future maintainer to destroy the only input the standing token guard has.
    The match-data file is **retained** out of repository, indefinitely — that
    retention is what makes the opt-in detection Section 5 describes possible
  - Section 5: what detection was given up — **exactly the three losses
    `design.md` enumerates, plus the residual initialism, and nothing else**: the
    contributor-documentation and CLI-output detections go entirely; the
    withdrawn-symbol scan is subsumed only for token-bearing names, so a
    re-introduction under a neutral name now passes; and detection becomes
    opt-in. **Corrected in place 2026-08-03**: this bullet's "an ordinary suite
    run no longer checks for a token at all" describes the state *after* Major 4
    retires those sites, not the state at this task, which lands in Major 3 —
    three standing token scans are live at this commit. Write each loss in the
    tense that is true when the document lands, and add no fourth or fifth item;
    the two an earlier attempt added each carried a false claim
  - Record the two carried-across untracked states and the position taken on
    each: the source workbooks accepted because they are never published and the
    ignore rule that keeps them out carries no token, and the shared agent log
    accepted with the symlink hazard named
  - Record the evasion-acceptance results from 2.4 and the classified inventory
    from 3.2
  - Refer to the commit map as **forthcoming**, never by path — it does not exist
    until 8.1, and a pointer written here would dangle between the merge of
    Major 6 and the post-rewrite commit
  - Observable: the file exists with sections 1, 2, 4 and 5 populated; the value
    matcher and the forbidden-string matcher both report zero matches against it;
    it names no email address and no path that no longer exists
  - _Requirements: 3.6, 5.4, 5.6, 9.1, 9.2, 11.9, 11.13_
  - _Depends: 2.4, 3.2_
  - _Boundary: ProvenanceRecord_

- [x] 3.5 (P) Redact the reference docs, the repository config and the source docstrings
  - Remove the writeup from the key references in `CLAUDE.md` and erase its
    tokens
  - Keep the ignore rule for the source workbooks — the pattern itself carries no
    token — and replace only the comment above it, which names the methodology,
    reproduces the third party's copyright notice and points at a removed path
  - Redact the token mentions in
    `docs/reference/banister-trimp-primary-sources.md`; one of them cites a
    token-bearing queue item id, which 3.12 moves — leave that citation for 3.12
    rather than half-correcting it here
  - Replace the sentence in the plugins docstring that names the withdrawn
    calculator with the token-free fact. **This is the only file under `src/`
    that carries a token**, and no test asserts on it
  - Replace the zone-table row in the document-editing docstring with a neutral
    example. This one is a **value reproduction, not a token** — the file matches
    zero on a token scan and is reachable only by the value matcher, so a
    token-only observable would pass over it untouched
  - Observable: none of these files matches the forbidden-string matcher **and**
    none matches the value matcher — both probes, because the ignore-rule comment
    carries a copyright notice and the document-editing docstring carries values,
    neither of which a token scan sees; the ignore rule still excludes the source
    workbooks; both docstrings read as complete sentences rather than as
    sentences with a hole in them
  - _Requirements: 1.2, 1.4, 1.5, 2.2, 2.4, 2.5, 11.1, 11.4, 11.6_
  - _Depends: 3.3_
  - _Boundary: ReproductionSweep, IdentityErasure_

- [x] 3.6 (P) Redact the training-load research log and restate the conclusions the redaction unsupports
  - Redact the reproduction sites in `.kiro/specs/training-load/research.md` —
    the load formulas, the discount-generating rule and the worked-example
    vectors — which the value matcher does not reach because it fingerprints
    table values and this file holds the generator
  - Remove the third party's contact address and erase the tokens; fix the
    reference list that goes stale with them
  - Apply the Req 1.6 procedure rather than an intention: for each redacted span,
    find every later claim whose only cited support falls inside it — the dense
    findings block here is immediately followed by an implications section and is
    drawn on further down — and either restate that claim on a surviving basis
    (the withdrawal decision, the licensing constraint, the shipped code) or
    withdraw it explicitly
  - Redact and retain: where a reproduction sits inside a record of evaluation,
    sourcing or withdrawal, the reproduction goes and the record stays. Deleting
    whole sentences because they contain a token would leave a repository that
    appears never to have evaluated anything, which breaks Req 11.5 and Req 4.5
    together
  - Observable: the document is re-read end to end and no sentence asserts a
    conclusion whose only cited support is a redacted span; the value matcher and
    the forbidden-string matcher both report zero matches; the document still
    records that a third-party methodology was evaluated, found to carry a
    redistribution restriction, and withdrawn
  - _Requirements: 1.2, 1.4, 1.6, 5.5, 11.1, 11.5, 11.6_
  - _Depends: 3.3_
  - _Boundary: ReproductionSweep, IdentityErasure_

- [x] 3.7 (P) Reverse the retention instructions in training-load and record the cross-boundary correction
  - Remove the **instruction**, not merely annotate it, at all three sites: the
    retention ruling inside the withdrawal component of that spec's `design.md`;
    the second, independent retention statement in that document's out-of-boundary
    list; and the task-5.2 bullet in its `tasks.md`. Req 4.1 forbids a document
    that instructs a session to retain, restore or leave in place
  - All three justify themselves by citing steering that no longer says that, so
    replace the **whole justification clause** in each. Restating a sentence as
    "not retained" while leaving the false premise standing is not a fix
  - State in each document that the material was retained as a research record,
    that the retention was reversed on 2026-07-30, and why — publishing the
    repository would publish it. Do not present the reversal as if the material
    had never been present, and do not present the original retention as an error
    of judgement rather than a decision taken under different circumstances
  - Rewrite the `tasks.md` bullet **body** and tag it with this spec's name and
    date, matching the existing amendment idiom. The bullet is not deleted, the
    checkbox is not touched, and the completed tally does not move
  - Add the cross-spec correction block to `design.md` and append an amendment
    entry and a phase-note paragraph to `spec.json`. **No approval flag, phase or
    readiness field moves**
  - Erase the tokens in these three documents and `spec.json`, including the
    approved component name built from one. Renaming it is a redaction, not a
    revision: its responsibilities, its requirement coverage and its boundary are
    untouched, and every reference to it — prose, headings and traceability rows
    — moves in the same change
  - Scope note: this task owns `design.md`, `tasks.md` and `spec.json` in that
    spec. Its `research.md` is 3.6's and its `brief.md` and `requirements.md` are
    3.8's — three parallel tasks, disjoint files, one spec directory
  - Observable: the forbidden-string matcher reports zero matches across the
    three documents and `spec.json` this task owns; no document in the spec
    instructs retention; the completed tally and all six approval booleans are
    byte-identical to the baseline captured in task 1; the traceability rows still
    trace after the component rename
  - _Requirements: 4.1, 4.2, 4.3, 4.5, 11.1, 11.5, 11.6_
  - _Depends: 3.3_
  - _Boundary: RetentionReversal, IdentityErasure_

- [x] 3.8 (P) Redact every remaining spec, including training-load's brief and requirements
  - Erase tokens in **every** spec directory the enumeration from 3.2 flags, not
    a fixed list. At the time of writing that reaches `plugin-api`,
    `threshold-load`, `athlete-benchmarks`, `wiki-contract`, `load-channels`,
    `fit-ingest`, the `distribution` brief, requirements and research documents,
    and this spec's own `brief.md` — but re-run the enumeration rather than
    trusting that sentence
  - **Explicitly included: `training-load`'s `brief.md` and `requirements.md`.**
    Both carry tokens, neither is a retention-instruction site, and both were
    missing from `design.md`'s modified-files table. They belong here under the
    redaction-only rule, not in 3.7
  - In the `distribution` design, remove the third party's address from the
    example configuration while leaving the illustration otherwise intact, and
    correct the path reference that goes stale with the deletion
  - Redact this spec's own `brief.md`: the third party's address and its
    identifying tokens. The brief was always in scope — Req 5.1 and Req 11.1 are
    unconditional over every file
  - **Redaction only.** No requirement, criterion, task or component is added,
    revised, withdrawn or renumbered, and no approval flag moves in any of these
    specs
  - Observable: re-running the token enumeration over `.kiro/specs/` returns only
    files owned by 3.6, 3.7 or already clean; a diff of the change shows no added
    requirement text, no changed checkbox tally and no moved approval flag in any
    spec
  - _Requirements: 1.2, 1.4, 5.5, 11.1, 11.5, 11.6_
  - _Depends: 3.3_
  - _Boundary: IdentityErasure, ContactRedaction_

- [x] 3.9 (P) Redact every token-bearing queue item's content
  - Erase tokens in **every** queue item the enumeration from 3.2 flags, open and
    closed alike. Do not work from a count: the figure in `design.md` had already
    drifted upward by the time this plan was written, and a task phrased as a
    closed enumeration invites an implementer to stop early
  - Redact the verbatim table rows reproduced in the withdrawal-evasions item and
    restate its evidence in terms that survive the redaction, so the item still
    records what it found
  - Contents only. Filenames, and the closures for every item this major's tree
    work resolves, are 3.12's — because a rename changes an item's id, and
    because two `(P)` peers must not both be performing the contract's three acts
    inside `.kiro/queue/`. The one closure outside 3.12 is 4.1's, which is
    sequential and in a later major; see the note there
  - Observable: re-running the token enumeration over `.kiro/queue/` returns only
    the token-bearing **path names** 3.12 owns, and zero content matches; the
    evasions item still states what it found without reproducing any table row;
    the value matcher also reports zero, since the redacted rows were values
  - _Requirements: 1.2, 1.4, 2.5, 11.1, 11.5, 11.6_
  - _Depends: 3.3_
  - _Boundary: IdentityErasure_

- [x] 3.10 (P) Correct the two steering documents
  - Correct the tense on the retention bullet in `roadmap.md` and on the "were
    kept … are to be deleted" sentence in `structure.md`, so both read as a
    completed record. Their existing retained-then-reversed wording is the model
    for the honesty rule and needs no rewriting, only tense
  - Correct the superseded Phase 5 constraints in `roadmap.md`, which still say
    unlanded work is orphaned by the rewrite where Requirement 6 says the purge
    halts. Steering is what every session loads as project memory, so a
    superseded constraint there outranks a settled requirement in practice
  - Repoint the rewrite-map citation at the provenance record created in 3.4, and
    correct the vocabulary example and the fixture mention that go stale with the
    erasure
  - Erase the tokens at every site in both documents
  - This edit **resolves** the open queue item recording the Phase 5 contradiction,
    but does **not** close it: 3.12 performs the contract's three acts, so that
    only one task writes closures into `.kiro/queue/`
  - Observable: the forbidden-string matcher reports zero matches in either
    document; the rewrite-map citation resolves to a file that exists; a re-read
    confirms Phase 5's constraints and Requirement 6 no longer contradict each
    other
  - _Requirements: 1.5, 2.2, 2.3, 4.1, 4.2, 4.5, 11.1, 11.5, 11.6_
  - _Depends: 3.3, 3.4_
  - _Boundary: RetentionReversal, IdentityErasure_

- [x] 3.11 (P) Neutralise the v1 payload fixture and the remaining test-tree token sites
  - Re-value the v1 payload fixture body with invented numbers, change the
    recorded calculator identity and display name to token-free values, and
    rename both fixture constants
  - Follow the rename in the sibling modules that import them, and update the
    assertions that match the recorded identity inside a skip message. **The
    rename and its importers must land together**: two of the affected modules
    are inside the type-checking perimeter, so a half-applied rename reds `mypy`
    rather than failing a test
  - Add the note that the fixture is **synthetic** from this commit forward
    rather than an authentic recovered artifact. That is the property the change
    costs, and it is stated rather than left implicit
  - Redact the tokens in the remaining test-tree sites that no guard owns —
    fixture detail strings and comments in the feature end-to-end module, the
    load package's conftest, and the stub-calculator module
  - Confirm before and after that no module under `src/` compares against the
    recorded identity — it is read out of the document, stored on the payload
    stamp and interpolated into a skip reason, never compared — so nothing
    computed, rendered or shipped moves
  - Observable: the token enumeration over `tests/` returns only the guard
    modules Major 4 owns; the full suite is green and `uv run mypy` is clean;
    every golden document's blob identifier is unchanged from the M0 manifest
  - _Requirements: 10.2, 11.1, 11.11, 11.12_
  - _Depends: 3.3_
  - _Boundary: IdentityErasure_

- [x] 3.12 Rename every token-bearing queue path and close what this branch resolves
  - Rename **every** queue path the enumeration from 3.2 flags, to the neutral
    stems fixed in 3.3. The queue contract makes the filename stem the item id,
    so Req 11.2 cannot be satisfied for them without a rename, and a rename is an
    id change. Items are renamed, never deleted — the contract's kept-not-deleted
    rule is preserved
  - **The flagged set includes at least one item already in the closed
    directory.** Closing preserves the stem, so an already-closed item still
    needs renaming; a task that only looks at open items misses it
  - **One flagged item is open and is also dropped**, by all three acts —
    flip the status, append a resolution section, move it into the closed
    directory — *and* renamed. A status flip alone is not enough here: its
    resume-command body instructs a session to update the writeup's framing and
    **not** to delete that file or its extracted tables, which is a live pointer
    to a removed path and a retention instruction at once. Rewrite that body
  - Close, by the same three acts, every other queue item this branch's tree work
    resolves — the docstring-vestige item and the Phase 5 constraints item. A
    prior session's in-place edit silently performed only two of the three, so
    verify the status line after rewriting it rather than verifying only that the
    file moved
  - Move every tracked file that cites a changed id onto the new id. Enumerate
    those citations rather than assuming a count: `design.md`'s figure counts the
    items' own self-references, and at least one citing file is outside
    `.kiro/queue/` entirely
  - Leave alone any citation written as a **placeholder** rather than as the
    literal id — this spec's own `design.md` refers to a flagged stem that way and
    carries no token as a result. Classify it in 3.2's inventory rather than
    leaving it unconsidered: after the rename it describes a stem that exists
    nowhere, so it is a stale pointer under Req 2.3. The stated position is
    **retained** — it is a record of what the rename did, in the document that
    specified it, and rewriting it would falsify that record
  - Explicit integration task: it crosses the boundaries of 3.5, 3.8, 3.9 and
    3.10 by design, because a rename and its citations cannot land separately
    without leaving a dangling id in between
  - Observable: the token enumeration over tracked **path names** returns empty;
    every citation of a changed id resolves to a file that exists, checked by
    enumerating citations after the move rather than against a remembered list;
    each closed or dropped item has a status line reading closed or dropped, a
    resolution section, **and** a location in the closed directory — all three
    verified, not two
  - _Requirements: 2.3, 2.5, 11.1, 11.2_
  - _Depends: 3.3, 3.5, 3.8, 3.9, 3.10_
  - _Boundary: IdentityErasure_

- [ ] 4. Guards: re-base what survives, retire what cannot

- [x] 4.1 Re-base the sdist guard onto the value oracle and retire its token-literal detections
  - **Deletions first, renames only over what survives.** These two sets overlap
    heavily and treating them as independent double-counts the work: most of the
    token-bearing constants in this module are the value tuples and the
    fingerprint tuple that the re-basing deletes outright, and one of the
    token-bearing test functions is deleted whole. Do the deletions, then rename
    what is left
  - Delete the value tuples and the plaintext fingerprint tuple, together with the
    comments quoting further values, and re-base both the source scan and the
    built-artifact scan onto the shared value matcher. These constants are today
    the largest in-repository copy of what the guard guards
  - Remove the module's self-exemption from its own scan: it existed because the
    module carried the material, and it no longer does
  - Keep every existing control — the non-zero scanned count, the byte-count
    equality, the wheel's module-prefix check and the equality-compared allowlist
    — and add the synthetic positive control: a table of **invented** values
    fingerprinted at test time, written into a temporary path and asserted
    flagged, with a sibling file lacking it asserted **not** flagged so the
    control cannot pass by matching everything
  - Assert the digest set and the window-length set are non-empty. An emptied set
    makes every absence assertion in this module vacuous, and that existing
    guarantee must survive the re-basing
  - Delete the withdrawn-symbol scan **whole** — its entire subject is the token
    tuple. From the package path-existence assertion and the two built-artifact
    member scans, delete the **token-matching assertions** while keeping the
    structural controls named above, which are not token-based and are not
    subsumed by the standing guard
  - Rename every token-bearing constant and test function that survives the
    deletions, to the forms fixed in 3.3
  - State in the module docstring that the detection data can no longer be
    verified against the files it was derived from and is unverifiable by
    construction from this commit forward, and which detections were retired into
    the standing token guard
  - Name each retired assertion and its reason **in this task's commit message**,
    together with the mutation evidence below, so a later reader finds a decision
    rather than an absence
  - Combines the erasure and the re-basing over this one module deliberately:
    both concerns touch the densest file in the change and splitting them would
    guarantee a conflict
  - Close the open queue item recording that this guard has no positive control,
    by the contract's three acts. Re-oracling removes the last control it had, so
    its subject and this task are the same work. **This is the one closure 3.12
    does not own, and the exception is deliberate**: the item is resolved by this
    task's guard work rather than by the tree work, it sits in a later major, and
    it is sequential — so the concurrency hazard that put every other closure in
    one task does not arise, and keeping the closure beside its evidence is worth
    more than the uniformity. Its *content* was already redacted by 3.9
  - Observable: the guard runs to completion and reports a result with the
    material absent from the tree; the synthetic control flags the invented table
    and not its sibling; the module matches zero on both the value matcher and
    the forbidden-string matcher; the named mutation is run through
    `uv run pytest`, observed red against **this** guard and not a cascade of
    siblings, reverted, observed green — and both mutation and result are in the
    commit message; the closed queue item has all three acts, verified
    individually
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 11.1, 11.7, 11.9_
  - _Depends: 2.4, 3.1, 3.3_
  - _Boundary: ReintroductionGuards, IdentityErasure_

- [x] 4.2 (P) Re-base the documentation guard onto a synthetic corpus and the withdrawal-pairing fact
  - Collapse the two corpus builders into one taking the scanned root as a
    parameter, and delete the read of the writeup
  - Re-base the positive control onto a synthetic corpus under a temporary path,
    so the control depends on no removed file
  - Delete the literal token-absence assertion and the two token-present controls.
    All three were built to fail on exactly the scenario Req 11 now mandates, so
    a complete scrub cannot be done without rewriting them; marking them expected-
    to-fail or deleting them silently would convert a designed tripwire into an
    unremarked gap
  - Re-base the steering tripwire onto the **neutral fact**: every steering
    document that records the evaluation also records the withdrawal, matched on
    withdrawal vocabulary rather than on an identity. This is weaker than the
    proper-name assertion it replaces — withdrawal vocabulary is common enough
    that the ever-present-token anti-pattern is a live risk — so assert the
    **pairing across documents**, never the mere presence of a word
  - Pin the pairing with a fixture that violates it: a synthetic steering tree in
    which one document records an evaluation without recording the withdrawal
    must red. A fixture already satisfying the property pins nothing
  - Name each retired assertion and its reason in this task's commit message,
    with the mutation evidence — the same obligation 4.1 and 4.4 carry
  - Observable: the guard runs to completion with the writeup absent; the
    violating synthetic tree reds the pairing assertion; the module matches zero
    on the forbidden-string matcher; the named mutation — the root parameter
    ignored so the builder always reads the real tree — is observed red, reverted
    green, and recorded in the commit message alongside the three retirements
  - _Requirements: 3.1, 3.3, 3.4, 3.5, 11.1, 11.5, 11.7, 11.9_
  - _Depends: 3.10_
  - _Boundary: ReintroductionGuards_

- [x] 4.3 (P) Stand up the standing forbidden-string guard over four surfaces
  - Build the single standing guard that scans, for every supplied string: every
    tracked file's **content**, every tracked **path name**, every sdist member,
    and every wheel member. The path-name surface is what carries Req 11.2
    forward as a standing property rather than a one-time act, and it subsumes
    the retired package path-existence assertion
  - Give it **two** positive controls, because it has two matchers: a synthetic
    tree under a temporary path holding one file whose content carries a supplied
    string and a second whose **name** does, with both asserted flagged and a
    third file carrying neither asserted not flagged. Without the second control
    the path-name scan is unpinned, and the path scan is the only thing carrying
    Req 11.2 forward
  - Run both controls **before** the absence scan, and make their failure an
    error rather than a skip
  - Report counts and locations to standard output and the matched strings only
    in the assertion message, so no forbidden string is ever written to a file
    inside the repository
  - Add the guard module to the type-checking perimeter. Three of the four guards
    being retired are already in it, so the perimeter must not shrink as a side
    effect of the retirement
  - Record the mutation evidence in this task's commit message
  - Observable: with a source supplied from a temporary path outside the
    repository, both planted instances are flagged and the third file is not;
    with the variable unset the guard skips and the meta-test asserts the skip
    exception rather than a pass; dropping the path-name scan while leaving the
    content scan reds a planted token-bearing filename and nothing else, observed
    and recorded in the commit message
  - _Requirements: 3.3, 3.4, 3.5, 11.2, 11.7, 11.8, 11.10_
  - _Depends: 2.2, 2.3_
  - _Boundary: ForbiddenStrings_

- [x] 4.4 Retire the CLI-output and contributor-documentation token detections
  - Delete the banned-token loop over the contributor documentation. The standing
    guard covers the same corpus from outside-supplied data
  - Delete the two CLI-output token assertions. Their subject is a named
    calculator that no longer exists in any form, the registry is provably empty
    on fresh import and that is asserted elsewhere in the suite, and retaining
    them retains the token
  - These are retired **entirely** rather than re-based, unlike those in 4.1.
    Name them and their reason in the commit message and confirm the loss is
    already stated in the provenance record's given-up-detection section from 3.4
  - Sequenced after 4.3 rather than parallel with it: retiring a detection before
    its replacement exists opens a window with no coverage at all
  - Observable: neither module matches the forbidden-string matcher; the full
    suite is green; the retired detections are named with their reason in the
    commit message
  - _Requirements: 11.1, 11.7, 11.9_
  - _Depends: 4.3_
  - _Boundary: ReintroductionGuards_

- [ ] 5. History tooling: the gated pipeline, built and tested before it runs

- [x] 5.1 (P) Build the quiescence gate
  - Implement the read-only inspection returning every branch other than `main`,
    every linked worktree, every dirty tracked path with its porcelain status,
    and any surviving backup refs. It must be safe to run at any moment and must
    open no ref for write and expire nothing
  - Implement the gate: zero to proceed, non-zero to halt, writing **exactly one
    line** to the shared agent log either way, before returning. On a halt the
    line names exactly what it found — every branch, every worktree path, every
    dirty path — because "not quiet" alone is useless to the peer who has to act
    on it. On a proceed the line is written before any caller touches a ref
  - Take the abandoned branch names as an **explicit caller input**, never
    derived from live refs. An earlier draft derived them from the backup refs;
    those refs were deleted during this spec's design phase, which would have
    made the tuple empty and discharged the abandonment obligation by accident
    rather than by decision — the gate would have passed silently. Surviving
    backup refs are reported for information only and never relax the check
  - Every worktree other than the primary one blocks, including this spec's own
  - Observable: each of the three halt conditions is tested independently and a
    quiet repository proceeds; the ref and reflog state is asserted byte-identical
    after an inspection; the gate refuses without a recorded abandonment naming
    both branches even when no backup ref exists
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_
  - _Depends: 1_
  - _Boundary: QuiescenceGate_

- [x] 5.2 (P) Build the redaction plan over every historical blob and every historical path
  - Implement **two** enumerations, not one. Content: every blob in the object
    database, through the value matcher, the forbidden-string matcher, and a
    probe set for the symbolic reproductions and all three personal identifiers.
    Paths: every path at every commit, through the forbidden-string matcher. The
    path enumeration is the one the prior draft did not have — content
    classification reaches the withdrawn calculator package's blobs and nothing
    reaches its path names
  - Use the complete path enumeration form. The added-files log filter is
    parent-relative and misses paths introduced by the root commit, which is
    exactly this case
  - Classify each content match as literal-replaceable or not pattern-tractable,
    and each path match as removed or renamed with its target stem — the same
    stems 3.3 fixed and 3.12 applied to the tree
  - Enumerate **blob identifiers, never basenames**. More encumbered table blobs
    exist in history than exist in the tree: the withdrawn calculator package
    carried its own copies at distinct paths, differing by a prepended copyright
    line. Any plan that de-duplicates by basename under-counts
  - Run the would-be-pruned check the rewrite depends on: for every commit, does
    at least one changed path survive the removal set? A commit that fails it
    halts the run rather than being silently retained empty or silently dropped
  - Emit identifiers and dispositions only. The probe set, the replacement specs
    and the mailmap contain the material, the addresses and the tokens by
    construction and live outside the repository
  - Observable: the emitted plan carries blob-id rows and path rows with
    dispositions and no content; the package's own table copies appear as
    identifiers distinct from the reference copies'; against a synthetic history
    where one commit touches only removed paths, the plan reports that commit and
    the run halts
  - _Requirements: 5.1, 7.1, 9.3, 11.1, 11.2_
  - _Depends: 1, 2.1, 2.3_
  - _Boundary: RedactionPlan_

- [x] 5.3 Build the gated rewrite driver
  - Call the gate first and refuse on a non-zero result. The gate cannot be
    skipped by forgetting it
  - Emit a **single** rewrite invocation carrying all four transforms — path
    removal, path renaming, content replacement and commit metadata — with
    empty-commit pruning explicitly disabled and every spec file passed by
    absolute path from outside the repository
  - Encode the three verified silent-under-removal hazards as rules, each of
    which under-removes without erroring:
    - **Directive order is load-bearing.** Every deletion line comes before every
      rename line, and a nested rename follows its parent-directory rename. A
      rename mutates the name that later filter lines match against; in a
      controlled run a rename placed before a deletion left the file **alive**
      under its new name
    - **Word-boundary anchors under-match.** The underscore is a word character,
      so an anchored pattern cannot match a token embedded in an identifier; an
      anchored expression set left a quarter of the token-bearing commit messages
      dirty, every survivor an identifier or a class name. Expressions are
      unanchored, case-insensitive, and ordered longest-phrase first so a
      multi-word phrase is consumed before its component words
    - **Empty-commit pruning is disabled deliberately.** Nothing would be pruned
      by measurement, but a pruned commit maps to forty zeros and would hole the
      complete mapping Req 9.3 requires
  - Never write the mailmap to the conventional repository-root path: that path
    is tracked, ships in the sdist under the packaging default, and would carry
    the address into precisely the artifact this spec exists to clean
  - Re-add the remote by hand afterwards, since the rewrite tool removes it
    deliberately and renames the remote-tracking refs into local heads
  - Observable: with an injected command runner, a failing gate emits **zero**
    commands and logs the halt; a passing one logs the proceeding line before the
    first emitted command; the generated path directives place every deletion
    before every rename; the generated expressions carry no word-boundary anchor.
    The driver is never executed for real in a test
  - _Requirements: 5.1, 5.2, 5.3, 6.5, 7.1, 7.2, 7.3, 11.1, 11.2, 11.3, 11.4_
  - _Depends: 5.1, 5.2_
  - _Boundary: HistoryRewrite_

- [x] 5.4 (P) Build the local verification runner
  - Implement every row of the verification table, and make each row **name the
    repository it runs against**. With three candidate subjects — the rewritten
    repository, a fresh verification clone taken from it, and the adopted working
    repository — a row run against the wrong one passes for free. The
    unreachable-object row in particular is vacuous against any fresh clone and
    is meaningful only against the rewritten source
  - Verification clones are taken without the local optimisation, and the
    alternates file is asserted absent. A local clone hardlinks the object
    directory including unreachable objects; a controlled experiment carried
    unreachable objects into one and none into the other
  - Take the forbidden-string source as a **required argument** and **fail** —
    never skip — when it is unset. This is the opposite of the test-suite guard's
    posture and is deliberate: a verification pass is a one-shot acceptance
    procedure with an operator present, not a routine run. Every token row is
    vacuous without it
  - Cover the path, blob, message, ref, metadata, old-identifier-refused,
    reflog-and-unreachable, commit-map-completeness, fresh-clone, built-artifact
    and absent-mailmap rows
  - Observable: the runner refuses to start without the source; each row's output
    names its subject repository; a deliberately incomplete fixture repository
    fails the rows it should and passes the rows it should, which is what proves
    the rows discriminate rather than merely run
  - _Requirements: 7.4, 7.5, 7.6, 7.7, 10.4_
  - _Depends: 1, 2.1, 2.3_
  - _Boundary: LocalVerification_

- [x] 5.5 (P) Build the clone-adoption carry-over
  - Implement the carry-over as an **asserted checklist, not a remembered one**,
    failing and naming any item it cannot find: the shared agent log under the
    common git directory **and the root symlink to it**, which a clone has
    neither end of; the gitignored real-activity corpus, which is the real-data
    verification set and is not recoverable from the repository; the gitignored
    source material at the repository root, which Req 1.7 requires stay on disk
    and untracked; and the data-root configuration if either form of it exists —
    check rather than assume
  - **Put the purge's own one-shot artifacts on the same checklist**: the M0 and
    M1 manifests, the spec-status baseline, the extracted prior-map rows, the
    rewrite's commit map, its first-changed-commits and suboptimal-issues
    artifacts, and the forbidden-string file. Every one is consumed *after* the
    adoption boundary by 8.1, 8.2, 8.3 or 8.4, none can be regenerated once the
    old repository is destroyed, and a checklist that enumerates only the
    user-visible state is exactly the kind that is remembered rather than asserted
  - Assert the configured commit identity is the non-personal address in **both**
    the local and the global scope before the clone is made. A fresh clone
    inherits global configuration, so this is the single setting whose drift
    would silently violate Req 5.3 on every post-rewrite commit
  - Build the clone at a scratch path and **move** it to the original absolute
    repository path. That path is load-bearing twice: it is the target of the
    root symlink, and it is the key under which this project's assistant memory
    is filed
  - Never carry the lost-and-found directory, which holds real activity files the
    data-root contract forbids in the repository directory, nor the second
    untracked copy of the rewrite map, which carries the maintainer's address in
    cleartext. Removing that class is an argument **for** adoption, not a cost of
    it
  - The tool never destroys the source repository. Until verification passes, the
    source is the only copy of anything
  - Observable: the checklist is asserted item by item and the run fails naming
    any missing item, demonstrated by removing one artifact and watching it fail;
    the identity precondition is asserted in both scopes; the tool has no code
    path that removes the source directory
  - _Requirements: 1.7, 5.3, 7.3, 11.13_
  - _Depends: 1_
  - _Boundary: CloneAdoption_

- [x] 5.6 (P) Build the pin repair tool
  - Repair the machine-consumed pin field mechanically from the commit map —
    open items, closed items and the queue schema's own example alike, giving
    **one** invariant rather than two classes. The follow-up skill runs a log
    range against that field, so a dead value breaks a skill
  - Leave every other commit reference exactly as written; they resolve through
    the commit map. Prose recording what was true at a moment would be falsified
    by rewriting it, and a peer session has already ruled that the frozen
    merged-at snapshots in the roadmap must not be corrected for that reason
  - **Report** every identifier-shaped token it did not rewrite, with a count.
    Silent non-repair would read as completeness
  - Record an unmappable pin as unresolvable and substitute nothing. At least one
    closed item holds a branch name rather than an identifier — a pre-existing
    schema violation — and it cannot be mapped
  - Verify a rewritten status line after rewriting it, not merely that the file
    moved
  - Observable: a mapped pin is rewritten, an unmappable one is reported and left
    alone, a second run changes nothing, and the unrepaired-token count is emitted
  - _Requirements: 9.4, 9.5, 9.8_
  - _Depends: 1_
  - _Boundary: ReferenceRepair_

- [x] 5.7 Build the remote measurement probe
  - Implement the only probe that can falsify retention: an authenticated web
    request for a pre-rewrite commit identifier, where a success response means
    still served and a not-found response means gone from that path
  - Make the tool refuse the two probes that cannot prove removal. The remote
    advertises tip-reachable and reachable identifier fetching but **not**
    arbitrary identifier fetching, so a retained-but-unreachable object is refused
    with the *same* error as one that is genuinely gone. A direct fetch by
    identifier is a false-negative machine, and a mirror clone plus an object
    read shares the blind spot
  - Implement the ref comparison in **both** directions: every local head present
    on the remote at the same identifier, **and** no ref on the remote that is not
    local. The second half is what catches a pre-rewrite ref left behind
  - Sequenced after 5.4 rather than parallel with it: both subcommands live in the
    same verification module
  - Observable: the probe reports a per-identifier served/gone result for a
    supplied sample; the ref comparison fails when a remote-only ref is present in
    a fixture; the two disqualified probes are unavailable rather than merely
    discouraged
  - _Requirements: 8.1, 8.3, 8.5_
  - _Depends: 5.4_
  - _Boundary: RemoteReconciliation_

- [ ] 6. Evidence, validation, and landing the tree work

- [x] 6.1 Classify every criterion and re-verify the claims in the changed tests
  - Run the completeness sweep, because this spec lists 76 criteria and
    incremental review does not terminate at that size: enumerate every criterion
    and classify it **pinned** — naming the test and the mutation it dies on —
    **preserved-only** — naming the pre-existing regression test — or **unpinned**
    — stated explicitly, with the mutation run that proves it. Criteria about the
    rewrite, the remote and the stated positions are expected to land in the third
    class and must be **declared** there rather than discovered by a reviewer
  - The per-guard mutation evidence is **not** produced here: 4.1, 4.2 and 4.3
    each run and record their own, in the commit that lands them, because a later
    task cannot write into an already-made commit message. This task collects
    those records and adds the one-line summary each owes the provenance record
  - Confirm each recorded mutation was run through `uv run pytest`. A bare
    interpreter invocation bypasses the cache-purging conftest and reads stale
    bytecode, which is how a real assertion gets recorded as non-discriminating —
    and the failure is intermittent by construction, so it reads as a flake
  - Confirm each recorded mutation redded the assertion it pins and not a cascade
    of siblings. If the target survived while siblings died, the assertion is
    vacuous and the siblings were doing the work
  - Grep the changed test files for consequence claims and mechanism
    justifications, then re-run every surviving claim or delete it. The word-list
    grep is a cheap first pass and has already missed nine such claims across five
    tasks; the obligation it cannot discharge is reading every factual sentence
    and executing what it asserts — rename the thing, call the function, print the
    field
  - Observable: a classification table covering all 76 criteria with none
    unclassified and every unpinned one carrying its proving mutation; three
    guard mutations located in their own commit messages and summarised in the
    provenance record; every claim in the changed test files either re-verified by
    execution or removed
  - _Requirements: 3.5, 5.6, 10.2_
  - _Depends: 4.1, 4.2, 4.3, 4.4_
  - _Boundary: ValidationGate, ProvenanceRecord_

- [x] 6.2 Validate the tree work and land it on main
  - Run the full class validation on the branch: the test suite, the linter, the
    formatter check and the type checker
  - Run the acceptance pass with the forbidden-string source **supplied** and
    confirm zero matches across tracked contents, tracked path names, the built
    sdist and the built wheel. This is the same mechanism that will keep
    reporting zero afterwards, which is what makes it the completion condition
    for the sweep
  - Compare the `training-load` spec-status report against the baseline captured
    in task 1: the same requirement and criterion counts, the same completed
    tally, the same six approval booleans, the same phase and readiness fields
  - Rebase onto current `main`, **re-run every validation command after the
    rebase** — pre-rebase green does not count — then merge fast-forward, remove
    the worktree and delete the branch
  - Write the merge to the shared agent log, naming what changed for a peer: the
    changed queue ids, the retired guards, the new environment variable and that
    the repository now detects a token only when that variable is supplied, and
    that the rewrite is next and the tree must stay quiet
  - **The worktree must be gone before Major 7 starts.** The quiescence gate
    halts while any extra worktree exists, including this one
  - Observable: all four validation commands green after the rebase; the supplied-
    source acceptance run reports zero matches on all four surfaces; the
    spec-status report matches the captured baseline field for field; `git
    worktree list` shows only the primary tree and `git branch` shows only `main`
  - _Requirements: 4.4, 10.1, 10.2, 10.3_
  - _Depends: 6.1_
  - _Boundary: ValidationGate_

- [x] 6.3 Empty the tip of every forbidden value and retire the reviewed-exemption table
  - **Added 2026-08-09, after task 7.2's preparation measured a conflict the
    design does not resolve.** `git filter-repo --replace-text` applies to the
    content of every blob and **cannot be scoped by path**, but 13 tracked files
    deliberately carry the values it would rewrite, sanctioned by
    `_CONTENT_EXEMPT_VALUES`. The same byte sequence must be redacted in
    historical prose and preserved in the detection tooling, and one global
    replacement cannot do both. Rewriting them makes every exemption stale and
    reds the suite on the rewritten tree — discovered in 8.3, *after* 7.4 has
    destroyed the original repository. Measured both ways on `f79622a`: a
    guarded rule set leaves 318 tokens surviving and still breaks a sanctioned
    path in 17 blobs; an unguarded one rewrites the sanctioned paths mid-string
  - The maintainer chose this resolution over a sentinel round-trip (which
    cannot reach the per-file token exemptions) and over `--file-info-callback`
    (which exists in filter-repo 2.47 and is path-aware, but is a fifth
    transform neither `design.md` nor `build_filter_repo_command` carries, added
    immediately before a one-shot run)
  - Move every detection needle **out of the repository**, sourcing it from the
    file `FITDOCS_FORBIDDEN_STRINGS` names, which is the mechanism task 2.2
    already built and six tasks already consume. This is the spec's own stated
    invariant — the repository holds none of the strings it is forbidden to
    contain — applied to the last 13 files that still violate it
  - The work list is **24 content hits across 13 files, and zero pathname
    hits**, which matches the 24 `(path, category, index)` exemption triples
    exactly. Three shapes: the removed-path tuple and token needles in
    `tests/purge/test_tree_removal.py`, `scripts/purge/sweep.py`,
    `scripts/purge/fingerprints.py`, `tests/purge/test_sweep.py`,
    `tests/purge/test_fingerprints.py` and
    `tests/test_forbidden_strings_source.py`; the prior-map filename in
    `scripts/purge/rewrite_map.py` and
    `tests/purge/test_rewrite_map_extraction.py`; and prose citations of that
    filename in four spec documents and one queue item
  - **Retire `_CONTENT_EXEMPT_VALUES` and the four tests that pin its
    behaviour** once the tree is clean. An exemption table with nothing to
    exempt is not merely dead — its own staleness check fails, because every
    triple points at a value no tracked file holds any more
  - A test that sources its needles from the out-of-repository file must
    **skip** when the variable is unset and **fail** when it is set and the
    value is absent. Collapsing those into a pass is the defect this whole
    mechanism exists to prevent (Req 11.8)
  - Observable: `scan_tree` over the tracked tree with the source supplied
    reports **zero** hits on both surfaces with **no exemption table consulted**;
    `_CONTENT_EXEMPT_VALUES` no longer exists; the suite is green with the
    variable set and green with it unset, with the complementary skip in each
    case naming which side it took
  - _Requirements: 3.3, 3.4, 11.7, 11.8, 11.10_
  - _Depends: 6.2_
  - _Boundary: ForbiddenStrings_

- [x] 6.4 Build the replacement-rule generator as a tested module
  - **Unblocked 2026-08-12.** `identity_leak_addresses` used to raise against
    any repository whose unreachable commit objects had been pruned — which is
    every fresh clone, and this working repository since the 2026-08-09
    pruning — because its consistency guard demanded that the
    reachability-*dependent* orphan-commit source corroborate the
    reachability-independent scan. The guard's instinct was right and its
    polarity was wrong: the two reachability-independent sources are now
    the contributing sources, the orphan-commit source contributes nothing to
    the denylist and is consulted only by the two guards, and a shape-matched
    candidate is discriminated from this suite's own synthetic fixtures by
    **tip-absence** rather than by a `tests/` path prefix. The derivation
    either returns a denylist the tip does not contain or it raises, so the
    **denylist is tip-disjoint by construction — as a set of case-folded
    email-shaped tokens**, which is the exact and only construction claim,
    measured by the `denylist & tip` assertion in
    `test_identity_denylist_is_exactly_the_leaks_the_tip_does_not_hold`.
    **The tip no-op itself remains a MEASUREMENT**, by
    `test_invariant_6_tip_no_op`, for the identity rule on the same footing
    as every other rule the generator emits: the rule matches substrings
    while the sanction compares whole tokens, so token-disjointness does not
    imply the pattern misses, and the per-token tiers are derived from the
    token list rather than from the tip at all. Two axes of that gap were
    found and closed separately (case folding in the tip comparison, then
    substring anchoring on the identity alternation, the latter a real
    invariant-4 mangling defect); a third is not assumed away.
    The denylist is now measured identical in this working repository, in a
    `--mirror` clone and in a `--no-local` clone. See
    `.kiro/queue/2026-08-10-6-4-identity-derivation-guard-unsatisfiable.md`
  - **Added 2026-08-09, after hand-generating the rules oscillated over five
    passes** — each pass satisfied one invariant and broke another, on the one
    artifact in this spec that cannot be corrected after it runs. The rules must
    be produced by a module with tests, like every other one-shot here
  - **`--replace-text` cannot preserve case.** `build_replacement_expressions`
    hard-codes an inline `(?i)`, under which a `The <token>` rule also matches
    `the <token>` and whichever is listed first wins for **both** — so the
    choice is capitalising ordinary prose or lowercasing sentence starts,
    measured at 36 lowercasings on the real corpus. Emit **case-sensitive**
    patterns (no `(?i)`) plus one rule per observed case variant. This is a
    deliberate departure from `build_replacement_expressions`; state it in the
    module rather than improvising it at the call site
  - Build the patterns at run time from the file `FITDOCS_FORBIDDEN_STRINGS`
    names. The in-repo vocabulary table carries only **replacements**, which are
    token-free by construction, so the module never holds what it replaces
  - **Six invariants, all measured against the real history, all holding at
    once** — holding five was the failure mode:
    1. zero identifying tokens left in surviving blob content
    2. zero identifying tokens left in commit messages
    3. zero identity leaks — the third party's given name, their email address,
       the maintainer's mailbox in blob content, the real machine hostname
    4. zero mangled forms (`withdrawnwithdrawn`, `the the`, `a the`,
       `an_withdrawn`, `Withdrawned`, the email-domain fragment)
    5. zero sentence-start lowercasings
    6. **the tip no-op invariant** — applying the rules to every blob at `HEAD`
       changes nothing. True only because 6.3 emptied the tip, and the cheapest
       proof the rules are scoped right
  - **Four traps already paid for, each of which cost a pass.** The third
    party's given name is an ordinary English word — unguarded it matched inside
    "Markdown" across 292 tip blobs, and word-boundary-guarded it still matches
    the standalone English verb throughout `.claude/skills/`; it has exactly two
    real uses in all history, both line-wrapped away from the surname, so the
    full-name rule must tolerate whitespace and the bare given name gets no rule
    at all. One `.local` hostname in the corpus is a **synthetic test fixture**
    in `tests/purge/test_sweep.py`, not a real machine. Tokens appear
    **adjectivally** ("a `<token>` symbol"), needing "a withdrawn symbol". And a
    shadowed duplicate rule is **not** safe to delete — removing some as dead
    destroyed capitalisation handling, because under `(?i)` they were the only
    case-preserving rules
  - Tests skip when `FITDOCS_FORBIDDEN_STRINGS` is unset and **fail** when it is
    set but a value is absent, never collapsing the two (Req 11.8)
  - Observable: all six invariants hold simultaneously, proven by tests rather
    than by a script run; the rendered table is reviewable with every token
    masked; no forbidden value enters any tracked file
  - _Requirements: 3.3, 3.4, 11.1, 11.2, 11.8_
  - _Depends: 6.3_
  - _Boundary: HistoryRewrite_

- [x] 6.5 Remove the copyright notice and the trademark mark, not only the name inside them
  - **Added 2026-08-16, on the maintainer's Req 11.4 decision.** Identity
    redaction removes the *name* from inside the notice and leaves the notice
    standing — after the rewrite, history would still carry
    `<copyright sign> <year> the third party. <reserved-rights phrase>` and
    the trademark mark. The maintainer chose, on 2026-08-12, that **the notice text
    itself must go**, over the reading that a notice naming nobody no longer
    attributes anything. Criterion 11.4 is unconditional over every reachable
    commit and task 7.2 is the only opportunity to act on it
  - **Measured at `40eb36e`, not carried forward from the earlier 42/16
    figures**: the reserved-rights phrase occurs **60 times in 42 reachable
    blobs across 17 paths** (`.kiro/queue` 10 paths including 2 closed,
    `.kiro/specs` 2, `tests/` 2, `pyproject.toml`, `.gitignore`,
    `docs/reference` 1); the trademark mark occurs **18 times in 16 blobs
    across 3 paths** (`.kiro/steering/roadmap.md` 14 occurrences,
    `.kiro/queue` 2, `docs/reference` 2). Re-measure against the tip 7.1
    freezes before generating the final rule set
  - **Corrected twice during implementation, and the correction is the
    lesson.** The phrase figure was first written as 46/28/13 from a FLAT
    pattern, then as 49/31/15 once wrap-tolerance was applied, and is
    60/42/17 once *comment-continuation* wrapping is counted too: the notice
    also wraps onto a following `#` comment line in `pyproject.toml` (10
    occurrences) and `tests/purge/test_tree_removal.py` (1), where the
    separator between two of its words is `\n# `, not whitespace. Each
    narrower pattern is a LOWER BOUND, and each gap is a set of notices a
    rule built on it leaves standing in a rewrite that gets one attempt.
    **Both the rules and every check on them must tolerate the same wrap
    shapes**, and the check must be implemented INDEPENDENTLY of the rule —
    the 11 comment-wrapped notices were invisible for a whole review round
    because the survivor counter called the same
    `_whitespace_tolerant_pattern` the rule was built from and therefore
    could not disagree with it. The trademark mark is a single character and
    cannot wrap; its 18/16/3 was re-measured and stands
  - **The emitted patterns are compiled as BYTES by the consumer, not as
    `str`.** `git filter-repo` opens the replacement file `'br'` and compiles
    every `regex:` line's raw bytes before it rewrites anything, so a pattern
    that is valid only as `str` — a `\u00a9` escape, say — aborts the entire
    one-shot run with the history untouched (measured both ways on throwaway
    `--no-local` clones: the rule set with one such pattern exits **1** with a
    traceback and leaves the tip identifier unchanged; the corrected set exits
    **0** and writes the new history in 33 seconds). Interpolate the
    character, never the escape, and never put a multi-byte character inside a
    character class: as bytes that class is a class of individual BYTES, and
    since the mark and the em dash share the lead byte `\xe2`, a class
    excluding the mark also stops at every dash, curly quote, ellipsis, `§`,
    `°`, guillemet and arrow in the corpus — under which a notice whose
    attribution contains one SURVIVES the real run while the in-process
    simulation redacts it.
    Prove it with a real `git filter-repo --replace-text` run on a throwaway
    `git clone --no-local`, not through the in-process simulation
  - **Scope the rules to the notice, never to `copyright` or the copyright
    sign alone.** At `40eb36e` the bare sign occurs **235** times across
    **51** paths and the word `copyright` **671** times word-boundaried
    across **40** — figures that move with every commit discussing this work,
    which is why they are pinned to a named commit rather than stated
    present-tense — the overwhelming majority of them
    unrelated — licence headers, packaging metadata and this spec's own prose
    *about* the notice. A rule keyed on either is catastrophic over-redaction
    of material the purge has no business touching, and it cannot be undone.
    The measured reserved-rights-phrase set carries no vendored third-party
    licence, so the notice phrase and the mark are the discriminating needles
  - **The case constraint from task 6.4 binds here.** `--replace-text`
    hard-codes `(?i)`, so emit case-**sensitive** rules, one per observed case
    variant, exactly as `build_rules` already does for tokens. Do not
    reintroduce an inline `(?i)`
  - **Anchor against an oracle, not against a green suite.** Task 6.4's
    adjacency table exists because four review rounds each found a real defect
    on an axis nobody had enumerated, and a proposed anchor that passed the
    whole suite disagreed with an oracle 48–60 times. A notice rule that
    matches a partial phrase is a new mangling source, which invariant 4
    forbids. Whatever boundary these rules need, derive its expectations from
    what the phrase actually is, and pin them the way the table does
  - **Req 11.6 still applies**: redact the identity, retain the record, do not
    falsify what the record states. A notice deleted to nothing can leave
    surrounding prose asserting a licensing constraint with no referent. The
    maintainer's framing is a neutral statement recording that redacted
    third-party material was present and withdrawn. **Req 11.12** forbids
    substituting any replacement proper name
  - **Fold in `requirements.md`'s own two defects**, which no task owns and
    which no matcher can flag: line 34 retains the literal reserved-rights
    phrase (a fragment of the very notice 11.4 removes, naming nobody so no
    guard sees it), and line 58 describes the prior rewrite map in the present
    tense though task 3.1 deleted it at `a705490`
  - All six of task 6.4's invariants must still hold **simultaneously** with
    the new rules in the set, invariant 4 (zero mangled forms) and invariant 6
    (the tip no-op) in particular
  - Observable: `build_rules` emits notice and trademark-mark rules; the six
    invariants hold with them present; a scan of reachable history under the
    full rule set reports **zero** surviving reserved-rights-phrase
    occurrences and **zero** trademark marks, while the unrelated copyright-sign
    population is **unchanged**; `requirements.md` carries neither defect; the
    masked table renders the new rules for maintainer approval
  - _Requirements: 11.4, 11.6, 11.12, 3.3, 3.4_
  - _Depends: 6.4_
  - _Boundary: HistoryRewrite_

- [ ] 7. Replacement machinery: the landed gate record, and the pipeline re-scoped for the fresh root

- [x] 7.1 Run the quiescence gate, record the abandonment, and clear the backup refs
  - *(Amendment 1, 2026-08-17: this task ran on 2026-08-16 under the retired
    rewrite plan and its outcomes are durable — the abandonment is recorded in
    the shared agent log and the backup refs are gone. The rationale below that
    cites the rewrite tool and "the clone in 7.2" describes the retired
    mechanism; under the replacement the gate re-runs inside 8.2 immediately
    before anything destructive, and unreachable objects never enter the fresh
    object database because it is populated by a reachable-only copy.)*
  - Run the gate from `main` in the primary worktree. If it halts, report exactly
    what it found and stop — the repository is left in the state it held before
    the check, with no ref rewritten and no history expired
  - Record the abandonment naming both branches held only in the backup refs
    before proceeding. Their work is already on `main`; they are pre-2026-07-26
    tips carrying the maintainer's personal address in their commit headers, so
    preserving them verbatim would preserve exactly what this spec removes
  - Delete the backup refs if present and **assert their absence either way**,
    using the ref-update mechanism rather than removing loose ref files: a ref can
    also exist packed, and the packed file has been observed stale, so a file
    removal would leave the packed copy behind
  - The order is about objects, not refs. The rewrite tool does not drop backup
    refs — it rewrites them **forward**, carrying the encumbered files and the
    personal address into the rewritten repository under new identifiers. Neither
    the deletion nor the assertion removes the unreachable objects; the clone in
    7.2 does, because it copies only reachable objects
  - Observable: the shared agent log carries either a halt line naming exactly
    what was found, or a proceeding line written before any ref moved plus an
    abandonment record naming both branches; no backup ref exists afterwards
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.2_
  - _Depends: 5.1, 6.2_
  - _Boundary: QuiescenceGate_

- [x] 7.2 (P) Move the surviving guard pieces into the surviving modules and re-scope the era signal
  - Move the whitespace-tolerant pattern helper out of the retiring
    replacement-rules module and into the shared forbidden-string helper, and
    make the retiring module import it from there for the remainder of its
    life — the dependency direction the design mandates, and what lets Major
    9's deletion remove the retiring module without breaking a survivor
  - Move the notice/mark tip guard — its word-tuple constants, its separator
    pattern, its independent survivor counter and its positive controls — from
    the retiring rules module and its test module into the shared
    forbidden-string helper and the standing guard module. The retiring rules
    module and its surviving rule tests import every moved constant from the
    new home for the remainder of their life — the rule builders consume the
    word tuple, the separator and the mark, so a re-spelled copy left behind
    in the retiring module would break the never-spelled-contiguously
    property while every observable stayed green. Three hard-won properties
    survive the move intact: the needle is never spelled contiguously in
    tracked source; the guard stays ungated and scans the working-tree
    content of tracked files; and the positive controls run in every wrap
    shape the guard claims to cover
  - Re-scope the source-liveness test's era signal for the replacement: the
    in-git-dir commit-map signal can never fire again, because the tool that
    wrote that file is retired unused — remove it — and the post-replacement
    posture must be selectable without depending on the provenance record's
    replacement section having landed, because 8.3 runs the suite with the
    source supplied before 9.2 writes that section. The replacement-era
    signal reads the repository's sole parentless commit: under the
    replacement its message is the fixed root message naming the provenance
    record, a shape no pre-replacement commit carries. The posture stays a
    named skip stating what it detected, never a silent pass — and a fixture
    pre-replacement repository must still read pre-replacement, asserted, so
    a permissive signal cannot turn the skip vacuous. The source-liveness
    module sits outside the Component → file map's lists; it is claimed here
    and deleted at 9.3 under the deletion list the design delegates to this
    plan
  - Re-run each moved guard's recorded single-line mutation at its new home,
    through `uv run pytest`, observed red then green on revert
  - Observable: the notice/mark guard reds from its new home on a planted
    needle in a synthetic tree; each moved constant and helper has exactly
    one definition, in the surviving module, and the retiring modules import
    rather than re-spell them; with the source supplied against a tree whose
    era signal reads post-replacement, the liveness test reports a named
    skip, and against a pre-replacement fixture it does not
  - _Requirements: 3.3, 11.8, 12.2_
  - _Boundary: MachineryRetirement, ForbiddenStrings_

- [x] 7.3 (P) Re-scope the carry-over checklist to the .git-resident items
  - The checklist's universe becomes the old `.git`: build it from a run-time
    enumeration of the old git directory's non-standard entries, with the
    shared agent log first among them, and halt for a decision on any foreign
    entry the enumeration finds that no item anticipates — silence is the
    failure mode, not the fallback
  - The doomed root becomes the old `.git` path. The hardened transfer
    semantics apply unchanged and narrower: a destination inside the doomed
    root refused, same-file aliasing refused, content compared by digest with
    symlinks digested as their targets, a link back into the doomed root
    refused, and the copy preserving symlinks rather than following them
  - Standard git furniture — refs, objects, logs, index, hook samples — and
    the lost-and-found directory are deliberately not carried: the archive
    keeps all of it, and the fresh `.git` must not inherit state from the
    history being replaced
  - Keep the commit-identity assertion the forge depends on
  - Re-run the checklist's recorded mutations against the re-scoped shape,
    through `uv run pytest`, observed red then green on revert
  - Observable: against a synthetic old git directory, the built checklist
    lists the agent log first, refuses an in-doomed-root destination, and
    halts on a planted foreign entry; the suite is green
  - _Requirements: 11.13_
  - _Boundary: HistoryReplacement_

- [x] 7.4 (P) Re-scope the verification rows to the replacement
  - Add the two new rows — the root tree identical to the recorded certified
    tip tree id, and exactly one commit reachable from all refs — and keep the
    reused rows: refs clean, headers clean, old identifiers refused, reflog
    and unreachable-objects clean, the message token scan, the fresh-clone
    re-run with the alternates assertion, and the built-artifact scans.
    Delete the rows whose subject no longer exists: commit-map completeness,
    mailmap absence, and the whole-history path, blob and message enumerations
  - The working-tree-coincides row is scoped to tracked files — the declared
    correction in the execution rules above — and every `design.md` sentence
    stating the bare porcelain form is amended in place, by the house
    annotation, in the same change, so an approved document does not keep
    asserting a check that reds by construction. The old-identifiers row's
    description gains the same-change annotation that its blob sample must
    be drawn from content absent from the certified tree, matching 8.1's
    survivorship constraint
  - Every row names the repository it runs against — the pre-swap fresh
    clone, the post-swap working repository, the verification clone, the
    remote — because a row run against the wrong one is not evidence
  - The runner takes the forbidden-string source as a required argument and
    fails, never skips, when it is absent — the opposite of the test-suite
    posture, and deliberate for a one-shot acceptance procedure with an
    operator present
  - Record the single-line mutation for the tree-identity row and every other
    new assertion, observed red then green through `uv run pytest`
  - Observable: run against a rehearsal repository, every row reports its
    result with its subject named; the tree-identity row reds against a
    repository whose root tree differs from the recorded id; the
    tracked-files-scoped coincidence row passes in the presence of a planted
    untracked file and reds on a modified tracked one; the deleted rows'
    functions no longer exist in the module
  - _Requirements: 3.5, 5.3, 7.4, 7.5, 7.6, 10.3, 10.4, 11.3_
  - _Boundary: ReplacementVerification_

- [x] 7.5 (P) Re-scope pin repair to the epoch convention
  - Repair applies one value — the replacement root's short commit id — to
    every open queue item's pin field, uniformly, with no per-item judgement;
    the map parameter and every map-driven path are removed, there being no
    map by construction
  - Closed items and their pins are untouched — declared stale rather than
    rewritten — and the repair is idempotent
  - Keep the line-level post-repair verification of every status and pin
    line, and the report of SHA-shaped tokens the repair did not rewrite, so
    silent non-repair cannot read as completeness
  - No plausible commit is ever substituted for a pre-replacement reference
  - Record the single-line mutation for each new assertion, observed red then
    green through `uv run pytest`
  - Observable: on a synthetic queue, every open item's pin equals the
    supplied epoch value, closed items are byte-identical afterwards, and the
    unrepaired-token count is reported; the suite is green
  - _Requirements: 9.4, 9.5, 9.8_
  - _Boundary: ReferenceRepair_

- [x] 7.6 Build the replacement driver and re-target the gating tests
  - One driver, one ordering, and the ordering is the design: the gate first,
    refusing on any non-zero result; the certified tip's commit and tree ids
    written into the proceeding line; the commit identity asserted
    non-personal in both git config scopes before the forge; the root forged
    parentless from the certified tree under a temporary ref; the fixed root
    commit message checked through the forbidden-string matcher before the
    forge; the reachable-only clone of that single ref, its branch renamed to
    the default and its alternates file asserted absent; the pre-swap rows;
    the asserted carry-over; the swap as two whole-directory moves; the
    archive readability check
  - Add the replace subcommand to the CLI dispatch — the one edit to the
    dispatch module this major makes — and extend every exact-equality pin
    that enumerates the subcommand surface in the same change: the name-set
    pin and the name-to-callable dispatch pin both red the moment the
    subcommand registers, and neither may be left for 7.8's validation to
    find as a surprise. The pins stay set and dict equalities, not literal
    counts, per this plan's no-count rule and the test module's own comment
  - A pre-swap row failure discards the scratch clone and returns to the
    forge with nothing touched. Nothing in the driver deletes the old `.git`,
    prunes an object database in place, or moves the working directory
  - Re-target the injected-runner gating tests at the replace driver: a
    failing preflight emits no commands and logs the halt; a passing one logs
    the proceeding line before the first emitted command; the driver is never
    executed for real in the suite
  - Record the single-line mutation for each new assertion, observed red then
    green through `uv run pytest`
  - Observable: with an injected runner, a passing run emits the command
    sequence in the design's order with the swap strictly after every
    pre-swap row, and a failing gate emits zero commands; the CLI's help
    output lists the replace subcommand
  - _Requirements: 5.3, 6.2, 6.5, 7.7, 11.3_
  - _Depends: 7.3, 7.4_
  - _Boundary: HistoryReplacement_

- [x] 7.7 Rehearse the forge, clone and swap end to end on a throwaway repository
  - Real git against a scratch repository, never the working one: forge a
    parentless root from a known tree, clone it reachable-only, carry a
    planted agent-log fixture across, swap, and assert on the result — tree
    identity with the source tree, a tracked-files-scoped porcelain status,
    exactly one reachable commit, a reflog referencing only the root, an empty
    unreachable-objects report, and the carried fixture present at its
    destination
  - Declared correction, applied when 7.7 lands: this bullet said "empty
    porcelain status", and that form is a guaranteed false red here, carrying
    task 7.4's amendment for the same reason. The rehearsal plants the
    untracked root agent-log symlink in the scratch working tree so Decision
    7 point 4's resolution observable is genuinely exercised, and Decision 7
    guarantees untracked material survives the swap — so an
    untracked-files-included porcelain can never be empty regardless of
    whether the swap is correct. The scoped row is the one that measures the
    identity claim; the rehearsal asserts the unscoped form is non-empty
    first, so the scoped row is not passing vacuously
  - Rehearse the rollback too: swap back from the archive and assert the
    original repository is restored intact, so the recovery path is exercised
    before it is ever needed
  - Observable: the rehearsal passes against a real throwaway repository,
    forward and rollback both asserted; no rehearsal step touched the working
    repository
  - _Requirements: 7.1, 7.3, 10.3_
  - _Depends: 7.6_
  - _Boundary: HistoryReplacement, ReplacementVerification_

- [x] 7.8 Land the machinery and classify the amended criteria
  - Full class validation in the worktree after the rebase — the suite, both
    ruff gates and mypy — with the forbidden-string source exported, then
    merge fast-forward and remove the worktree, restoring quiescence
  - Classify every criterion Amendment 1 added or rewrote — Requirements 6
    through 10 as amended, and 12 — as PINNED, PRESERVED-ONLY or UNPINNED,
    extending the tracked classification section task 6.1 wrote in the
    provenance record — not a scratch artifact, because 9.4 destroys the
    scratch and Req 12.3 retains the recorded evidence: PINNED naming the
    test and the mutation it dies on, PRESERVED-ONLY only after watching the
    named test red, UNPINNED stated with the mutation run that proves it.
    Criteria about the one-shot run and the stated positions are expected to
    land UNPINNED with a procedure, as their predecessors did
  - Correct the classification section's own frame in the same edit, as
    declared in-place corrections: its header still counts the pre-amendment
    criterion set, and the rows for the criteria Amendment 1 rewrote cite
    retired artifacts and retired task numbers
  - Observable: `main` carries the machinery with validation green recorded
    after the rebase; the shared agent log carries the merge line; the
    tracked classification covers every amended criterion with none left
    unclassified, and no row of it cites a withdrawn artifact as forthcoming
  - _Requirements: 3.5_
  - _Depends: 7.2, 7.5, 7.7_
  - _Boundary: ValidationGate, ProvenanceRecord_

- [x] 8. Execution: the one-shot history replacement, solo on main

- [x] 8.1 Certify the tip
  - Preconditions, not assumptions: every peer branch landed, every extra
    worktree gone, nothing uncommitted anywhere — the state the gate will
    demand — and the forbidden-string source present and loadable
  - Run the acceptance battery against the exact tip that will be replaced:
    the full suite, both ruff gates and mypy green; the standing token guard
    with the source supplied reporting zero matches across tracked contents,
    tracked paths, sdist members and wheel members; the value oracle likewise
    zero
  - Certification is a property of one commit: if `main` moves for any reason
    afterwards, certify again before proceeding — the replacement carries
    whatever the certified tree contains, and there is no later redaction
    step to catch what certification missed
  - Capture the recorded sample of pre-replacement identifiers to the scratch
    evidence path while the old history still exists: the old root commit,
    the certified tip, a spread of further commit ids, and blob ids drawn
    only from content that is absent from the certified tree. The
    survivorship constraint is load-bearing: blob ids are content-addressed,
    so a blob of surviving content is re-created identically in the fresh
    repository and would make the refusal row red by construction — assert
    at capture time that no sampled blob exists in the certified tree.
    Commit ids need no such filter; no pre-replacement commit survives.
    8.3's refusal row and 8.4's remote probes consume exactly this sample,
    the row's implementation refuses an empty one by design, and under the
    replacement no commit map exists to supply it — nothing else creates it
  - Observable: recorded evidence names the certified commit id and its tree
    id and shows each command green, gathered through `uv run pytest` with
    the single complementary skip present — which is how a live source is
    distinguished from an unset one; the identifier sample exists at the
    scratch path, non-empty, with the old root and the certified tip in it
  - _Requirements: 10.1, 10.2_
  - _Depends: 7.8_
  - _Boundary: ValidationGate_

- [x] 8.2 Run the gated replacement through the swap
  - One driver invocation on `main` in the primary worktree. If the gate
    halts, it reports exactly what it found, leaves the repository in the
    state it held before the check, and records the halt and its cause in the
    shared agent log; the halt is the end of the run, not an obstacle to
    route around
  - On proceed, the log carries the proceeding line — the certified tip's
    commit and tree ids, and the abandonment record naming both abandoned
    branches — before anything else happens
  - The forge and the clone follow the driver's fixed ordering: identity
    asserted, root message checked, parentless root from the certified tree,
    reachable-only clone of that single ref, pre-swap rows green — a pre-swap
    failure discards the clone and re-forges with nothing touched
  - Every `.git`-resident carried item — the shared agent log first — is
    asserted present and digest-identical at its destination before the swap
    proceeds; a foreign entry in the old git directory halts the run for a
    decision
  - The swap is two whole-directory moves: the old `.git` out, whole, to the
    archive path outside the working tree; the fresh `.git` into its place.
    The working directory and its untracked material — the data directory,
    the source workbooks, the reference scans — are never moved and never
    deleted
  - The archive's absolute path goes to the shared agent log, and the stated
    position on the archive under Req 11.13 is recorded acceptance: never
    tracked, never published, its eventual deletion a maintainer act outside
    this spec
  - Observable: after the run, the all-refs commit count is exactly one and
    the tracked-files-scoped porcelain status is empty — the untracked
    material Decision 7 preserves, the agent-log symlink among it, is
    expected to remain; the root symlink to the shared agent log resolves
    again; the old tip resolves inside the archive and a connectivity-only
    fsck of the archive is clean; the log carries the proceeding line, the
    carry-over assertions and the archive path
  - _Requirements: 1.7, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 7.1, 7.7, 10.3, 11.1, 11.2, 11.3, 11.4, 11.13_
  - _Depends: 8.1_
  - _Boundary: QuiescenceGate, HistoryReplacement_

- [x] 8.3 Verify the replaced repository by inspection, and treat any red as swap-back
  - Run every post-swap row against the working repository with the source
    supplied: a single reachable commit; the root tree identical to the
    certified tip tree id; the single default head and nothing under the
    backup-ref namespace; author and committer headers carrying the
    non-personal identity only; the root message through the token matcher;
    the standing guard's four surfaces at zero; the reflog referencing only
    the root; the unreachable-objects report empty; every identifier in the
    sample 8.1 recorded — the old root and the old tip among them — refused
  - Take the reachable-only verification clone, assert its alternates file
    absent, re-run the rows against it, and build the sdist and the wheel
    from it, scanning every member on both probes
  - Run the ordinary validation battery on the replaced repository: green
    includes the standing token guard skipping without the source; a separate
    operator run with the source supplied is its own recorded evidence, and
    in that run the source-liveness test reports its named post-replacement
    skip rather than a failure — 7.2's era re-scope is what makes that the
    correct outcome here, and a failure from it is validation red like any
    other
  - Any red: set the fresh `.git` aside, swap the archive back, stop with the
    evidence. No remote action of any kind happens before every row above is
    a recorded green — the archive is the only copy of the old history **on
    this machine** *(Amendment 3: no longer the only copy anywhere, since the
    retained `fitdocs_oss` keeps the old history permanently. That widens the
    margin and relaxes nothing here: this gate is local and runs before any
    remote is consulted)*
  - Observable: every row reports a pass with its subject repository named;
    the identifier probes are non-zero for every sampled pre-replacement
    commit and blob; both artifact scans report zero; both suite runs are
    recorded
  - _Requirements: 5.3, 7.2, 7.3, 7.4, 7.5, 7.6, 10.1, 10.3, 10.4, 10.5, 11.1, 11.2, 11.3_
  - _Depends: 8.2_
  - _Boundary: ReplacementVerification_

- [x] 8.4 Push the renamed remote, then measure what both remotes serve
  - *(Amendment 2, 2026-08-22; `design.md`'s section of that name. Not
    training-load's Amendment 2, which this spec's prose also cites.)*
    Decision 6 assumed a delete-and-recreate
    under the same name. What the maintainer supplied instead is a **rename**:
    `git@github.com:joshua-stauffer/fitdocs.git`, a repository that already
    exists and is empty, standing beside the still-live `fitdocs_oss`. Two
    consequences for this task. **Nothing here deletes anything** — nothing
    runs `gh repo delete`, nothing runs `gh auth refresh`, and the token's
    missing `delete_repo` scope is no longer a blocker. *(Amendment 2 reached
    that state by putting the deletion out of band as a maintainer act;
    Amendment 3 went further and cancelled it — `fitdocs_oss` is retained. The
    conclusion for this task is the same and is stated directly here, so no
    bullet of it has to be read through an amendment.)* **There is nothing to
    recreate** — the destination already exists, so this task reduces to
    re-point, push, and measure. **Requirement 8 WAS amended** — textually, by
    Amendment 3, in `requirements.md`: its subject is the canonical repository
    throughout, 8.4 carries an explicit exemption for the retained
    `fitdocs_oss`, 8.7 is widened to both repositories, and a new 8.8 records
    the standing privacy duty. Read the criteria as they now stand, not
    through this bullet. The subject ambiguity that forced it: **8.1–8.6 all
    say a bare "the remote"** (8.4 twice) and **8.7 says "the repository"** —
    which is why every row below names its subject explicitly. The nine tracked references naming the old
    repository were moved ahead of 8.1 on `chore/repo-rename`, so the
    certified tree already names the new one
  - *(Amendment 3, 2026-08-22, supersedes the deletion half above.)* The
    maintainer's ruling: **`fitdocs_oss` is retained** — not deleted, not
    rewritten — and `fitdocs` becomes the canonical source. So there is no
    out-of-band deletion to wait for, and the rows below measure a **standing
    position** rather than a transition. Every bullet below states its own
    subject and its own outcome; none of them needs the amendment history
    above to be executed correctly
  - **`fitdocs_oss`, the retained repository — measure its position and record
    it.** Re-verify it is still **private**, fork-free, PR-free and issue-free,
    and record all four results with their date. **`private` is the most
    urgent of the four, and under retention it is now a standing property
    rather than a one-time check**: a `fitdocs_oss` that is or becomes public
    publishes the encumbered material outright, which falsifies the premise
    the whole purge rests on — the brief's *"private, no other contributors"* —
    and which no amount of local replacement reconciles. If it is not private,
    stop and report; do not push until the exposure is assessed
  - The fork half of the same measurement is **not** redundant with the
    destination check below and must not be dropped as such — and retention
    *inverts* its motive rather than softening it. **Both earlier statements
    of this obligation's grounds were wrong**, and the correction is the
    reason it now matters more. Measured against GitHub's *About forks* →
    *Visibility of forks* (<https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/about-forks>, fetched 2026-08-22): *"private repository
    forks are private"* and *"You cannot change the visibility of a fork by
    itself"*, so a fork of the private `fitdocs_oss` cannot be public — the
    previous draft's *"a fork can be public even when its parent is not"* is
    **false**. And the same page's deletion table pairs *"A private repository
    is deleted"* with *"Its private forks are also deleted"*, so the draft
    before that — *"a fork keeps pre-replacement objects reachable after the
    parent is deleted"* — was **also false** for a private parent. The true position is the opposite of both: **deletion
    would have reaped any private fork automatically, and retention is
    precisely what lets one persist** — a permanent, full second copy of the
    encumbered history inside another account, which cross-fork object access
    then makes fetchable by SHA across the network (`research.md:693` at
    `1618b33`; `research.md:264` at `1618b33` records the clones-and-forks
    reachability warning, and neither line speaks to fork visibility, so
    neither is cited for that). GitHub's own page puts the residual duty on
    the maintainer: *"You are responsible for ensuring that people who have
    lost access to a repository delete any confidential information or
    intellectual property."* No criterion in Requirement 8 covers forks, so
    this is still the only place the obligation is operationalised. If a fork
    exists, stop and report before anything is pushed — a surviving fork is
    the state Req 8.4 forbids declaring reconciliation complete over
  - **The destination — measure before pushing into it.** Re-verify
    `fitdocs` is still private, fork-free, PR-free and issue-free, and still
    carries zero refs — pushing into a repository that acquired content since
    it was measured is not a case to discover afterwards. The nil-cost claim
    is re-measured, not trusted
  - **And confirm the destination is not itself a fork.** "Fork-free" above
    means *has no forks*; it does not mean *is not one*. Confirm `fitdocs` is
    not a fork of `fitdocs_oss` and shares no fork network with it — via the
    repository's `fork` and `parent`/`source` fields, not by inspecting refs.
    This is the one way pushing while the old repository is still live could
    actually do harm: a repository inside `fitdocs_oss`'s fork network can
    serve that network's objects by SHA (`research.md:693` at `1618b33`), so
    the fresh root would sit in a namespace from which pre-replacement objects
    remain fetchable — defeating Req 8.2 and 8.3 against the **new** URL,
    which is precisely what this task exists to establish. The 2026-08-22
    measurement recorded in the queue item (*"exists and is empty, `git
    ls-remote` exits 0 with zero refs"*) **cannot** distinguish an empty fork
    from an empty standalone repository, so it does not discharge this. If it
    is a fork, stop and report: the destination must be replaced, not pushed
    to
  - **Record the retention as a stated position, against the amended
    Requirement 8.** `fitdocs_oss` stays live and keeps serving
    pre-replacement material indefinitely; that is the maintainer's ruling of
    2026-08-22, and Requirement 8 was **amended textually** to admit it —
    read `requirements.md`'s Req 8 preamble and criterion 8.4's exemption for
    the operative wording. Record it in those terms.
    **Do not describe this as a mere scoping, and do not appeal to the
    "recorded acceptance" pattern of Req 11.13 or Decision 7**: an earlier
    draft did both and `design.md`'s Amendment 3 retracts them — it is an
    exemption, and those two precedents are authorised inside their own
    criteria's text where Requirement 8 authorised nothing. The narrowing's
    actual ground is structural: this task re-points `origin` at `fitdocs`,
    after which `fitdocs_oss` is no repository's remote at all. **This is what
    makes the task completable**: an earlier draft barred completion "pending
    the deletion", which under this ruling never comes
  - Re-point the `origin` remote at the new URL; push the root; set the
    default branch
  - Measure rather than assume: a fresh clone from the new remote contains
    exactly one commit whose id is the root and whose tree is the certified
    tree, and an authenticated web request for each identifier in the sample
    8.1 recorded — the old root and the old tip among them — returns
    not-found **against `fitdocs`**. Probe **both** URLs anyway: under
    retention the old one is expected to keep finding the material
    permanently, and recording that measured fact — rather than omitting the
    probe because its answer is known — is what makes the recorded position
    above auditable instead of merely asserted. A fetch by identifier is
    disqualified as evidence both ways, as already measured
  - Compare refs in both directions **against `fitdocs`, the new remote** —
    naming the subject because Req 8.5, which this row implements, is one of
    the criteria that says a bare "the remote": every local head on it at the
    same id, and no ref on it that is not local
  - If any probe **against the new remote** shows pre-replacement material
    served: stop and report, reconcile by whatever further means the
    measurement shows sufficient, and do not declare completion while the
    measurement disagrees — a stop-and-report outcome, not a retry loop.
    Probes against the retained `fitdocs_oss` are expected to find it
    permanently; under Amendment 3 that is the **accepted standing position**
    recorded above, not a reconciliation failure and not a not-yet-complete,
    and the distinction must appear in the record rather than being resolved
    by which URL was probed
  - Record the retention ruling, the narrowing of Requirement 8 and what it
    excludes, the retained
    repository's measured private/fork/PR/issue position, the push, and every
    probe output and its date — which action was required versus which was
    assumed — as the evidence 9.2 writes into the provenance record's remote
    section. That the rename made recreation unnecessary, and that the
    retention made deletion unnecessary, are both part of the record rather
    than omissions
  - **Do not make either repository public** — `fitdocs` is not published by
    this spec, and `fitdocs_oss`'s privacy is now load-bearing rather than
    incidental, because it is the only thing keeping the retained material
    unpublished
  - Observable: dated per-identifier probe results recorded against both URLs,
    the retained one expected non-zero; the fresh remote clone carries the
    root commit only; the ref comparison agrees in both directions; **both**
    repositories are still private
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_
  - _Depends: 8.3_
  - _Boundary: RemoteRecreation_

- [ ] 9. Aftermath: references, record part two, and retirement

- [ ] 9.1 Repair every open pin and document the epoch convention
  - On a short-lived branch created on the new history — the ordinary
    protocol is back — run the pin repair with the replacement root's short
    id across every open queue item
  - Amend the queue README's schema section in the same change: a pin equal
    to the replacement root records that the item's evidence predates the
    replacement and that its original pin is permanently unresolvable; update
    the README's own example pin to the convention value
  - Closed items stay untouched; the unrepaired SHA-shaped token count is
    reported; no plausible value is substituted anywhere
  - Observable: every open item's pin equals the replacement root's short id
    and resolves in a fresh clone; the README defines the convention and its
    example pin carries the convention value; the repair report carries the
    unrepaired count
  - _Requirements: 9.4, 9.5, 9.8_
  - _Depends: 8.4_
  - _Boundary: ReferenceRepair_

- [ ] 9.2 Complete the provenance record's part two
  - Section 3, the history replacement: the mechanism — a fresh root of the
    certified tip by a `.git` swap, the old `.git` archived, the remote
    **renamed** rather than deleted-and-recreated *(Amendment 2, 2026-08-22)*
    and the old repository **retained** rather than deleted *(Amendment 3,
    same date)* — record what actually happened, not what Decision 6 planned —
    the grounds by pointer to the brief's amendment
    decision, the root commit named, and the statement, made once, that every
    pre-replacement commit identifier is thereafter permanently unresolvable,
    there being no mapping by construction
  - Section 6, the remaining stated positions: the pin convention and its
    README documentation; the closed items' declared staleness; the tracked
    fixture filename retained as historical and permanently unresolvable,
    with the one-line note in the drain-report test recording the same — the
    retired plan's commit-map pointer is cancelled; the unrepaired SHA-shaped
    token count; the `.git` archive described by role and never by path; and
    the carried untracked states with their positions
  - Section 7, the remote: the push to the renamed destination, the
    **retention** of `fitdocs_oss` with its grounds, the exemption
    Requirement 8 was amended to carry and what that exemption excludes, that repository's measured private/fork/PR/issue position,
    and the probe outputs and their dates from 8.4 against **both** URLs —
    which action was required versus which was assumed. **Neither a recreation
    nor a deletion occurred**; record that the rename made the first
    unnecessary and the maintainer's ruling made the second moot, rather than
    writing steps nobody ran. Req 8.6 asks which action was required, and a
    record naming a step nobody performed fails it as surely as an omission.
    State plainly that the retained repository still serves the material and
    that Requirement 8 is satisfied with respect to the canonical repository —
    the honest form of the claim, and the one a later auditor can check
  - **And write the standing duty into the record, not just the measurement**
    (Req 8.8): `fitdocs_oss` must remain private for as long as it exists,
    because it holds the removed material in full and its privacy is the only
    thing keeping that material unpublished. A dated observation that it *was*
    private is not that duty — a future maintainer reading this record must
    find the obligation, not merely evidence that it once held. Record with it
    that any fork of it is a second permanent copy in another account, and
    that GitHub places the duty to have such copies deleted on the maintainer
  - Correct every forward-looking reference to the retired mechanism in part
    one, in the same edit, as declared in-place corrections — enumerated at
    execution time, not from this list; at review time they include two
    forthcoming-commit-map promises, a clone attributed to a retired task
    number, and the scratch-destruction tie to the retired rewrite. Section
    3's no-mapping-by-construction statement must not land in a file whose
    earlier sections promise a map. Forward-looking promises are corrected;
    the historical record of what Majors 1–6 did is not rewritten
  - One falsifiable proposition per sentence, every sentence tracing to a
    criterion or a section obligation — the discipline 3.4 paid three review
    rounds to learn
  - Observable: the three sections are populated; the drain-report test
    carries its note; the record matches zero on both probes; every open pin
    the record describes resolves in the replaced repository
  - _Requirements: 3.6, 8.6, 8.8, 9.1, 9.2, 9.3, 9.5, 9.6, 9.8, 11.9, 11.13_
  - _Depends: 9.1_
  - _Boundary: ProvenanceRecord_

- [ ] 9.3 Retire the machinery
  - After the replacement is verified and before the repository is made
    public, as its own ritual change on the new history — never riding the
    replacement itself
  - Delete the purge scripts package entire, and the purge test package less
    the two relocations: the oracle test module and the fingerprint shape
    test module move to the test root, because their subjects survive. The
    source-liveness test module retires with the machinery: its subject —
    verifying the match data against a history that carries the tokens —
    cannot exist after the replacement, and the loss is declared, not silent
  - The enumerated deletion list this task produces is the Req 12.1 position:
    every deleted module has planning, executing or verifying the history
    operation as its only purpose, and anything retained is a named survivor
    or carries a stated retained purpose
  - Update the type-checking perimeter in the same change: the scripts tree
    leaves, the surviving helpers stay, and the checked perimeter of
    surviving modules does not shrink
  - Write provenance section 8: what machinery was removed, what each
    surviving guard still detects, and what verification capability was given
    up — whole-history scanning, the quiescence gate, the manifest and
    baseline tooling, the remote retention probes, pin repair, the rule
    generator, and the match-data liveness check — stated in the durable
    record, not only in a commit message
  - Observable: no purge scripts package and no purge test package exist in
    the tree; the two relocated test modules run from the test root; the
    suite, both ruff gates and mypy are green; section 8 is populated
  - _Requirements: 12.1, 12.3, 12.4, 12.5_
  - _Depends: 9.2_
  - _Boundary: MachineryRetirement_

- [ ] 9.4 Prove every surviving guard still fails, then destroy the scratch
  - On the post-retirement tree, re-run every surviving guard's recorded
    single-line mutation through `uv run pytest`: observed red, reverted,
    observed green. Revert from a snapshot copy taken before the first
    mutation, never with a git checkout of uncommitted work, and assert every
    anchor matched exactly the expected number of times — a harness that
    reverts through git deletes the work it is measuring
  - A survivor that cannot be made to fail is a finding, not a formality: it
    means the retirement removed something the guard depended on
  - Destroy everything in the out-of-repository scratch directory except the
    forbidden-string source, which is standing guard data and survives
    indefinitely; the `.git` archive is not scratch and is governed by
    Decision 7
  - Observable: a per-survivor ledger records each mutation red and the
    reverted green on the post-retirement tree; the scratch directory holds
    the forbidden-string source and nothing else
  - _Requirements: 3.5, 12.2_
  - _Depends: 9.3_
  - _Boundary: MachineryRetirement_

---

## Implementation Notes

Written by the session that implemented Majors 1–2. Each entry is a contract a
later task in *this* spec must honour, or a trap that cost a review round.

**Set `FITDOCS_FORBIDDEN_STRINGS` before running the suite.** Its location and
category counts are in the shared agent log (`NOTE`, "SCRATCH ARTIFACT
LOCATION"); the contents are recorded nowhere and must stay that way. Unset,
every token check degrades to a **skip** and the run still exits 0 — a pass
count tells you nothing about whether the check ran. Two complementary skips
exist by design, one firing with the variable set and one unset; that is Req
11.8's distinguishable-absence contract, not a gap.

**An artifact-producing function must read back what it wrote.** This cost
three rounds on 2.4 in three different places: a wrong-slice digest set, a
module rendered under a fresh salt, and a record filtered to `if r.passed`
that silently dropped every failing probe. All three passed a green suite
because the tests asserted only that the output *existed*. Load the artifact
back, compare it field-by-field and in order against the run that produced it,
and put a **deliberately failing case** in the fixture — a pass-filter mutation
is invisible when every probe passes, and counts alone do not catch it.

**Every walk needs a positive control.** Empty the collection and watch it red.
Content mutations cannot expose a vacuous walk, and a sibling test covering the
same content mutations will hide one indefinitely — one survived five review
rounds and ~100 reviewer mutations that way.

**3.1 — the sdist exclusion block now has four entries, not two.** The task
text says "both exclusion entries"; `scripts/` and `tests/purge/` were added in
task 1 because hatchling's default sdist include is the working tree minus
`.gitignore`. The instruction to delete the section *entirely* is unambiguous,
so nothing breaks — but do not expect two.

**3.2 — two path entries in the match data have token-free basenames.** Four
tracked files reference them under a different prefix or bare, so a search
keyed only on the full paths will pass over those lines. Run the two bare
basenames as an **additional ad-hoc probe**; do not add them as entries, which
would be wrong — they persist in queue items Req 2.5 deliberately retains, and
4.3's absence guard would then red against files the purge keeps.

**3.2 — the purge's own new files are sweep hits.** `scripts/purge/fingerprints.py`
and `tests/purge/test_fingerprints.py` carry token-category matches and post-date
design.md's modified-files table, so they exist only as sweep results. Classify
them explicitly rather than discovering them late.

**3.4 — the acceptance record is already token-free and path-free.** Probe names
are opaque `source-N` labels and there is no path field, so it can be folded
into the provenance record without re-importing what the purge removed. It holds
a pass/fail line per catalogued evasion, which is what Req 11.9's losses need.

**3.4 — a second abbreviation survives.** The initialism of a three-word term
whose expansion contains the surname is *not* in the match data, correctly:
requirements.md defines the identifying tokens as the personal name, the former
proper name and "its trademarked abbreviation" (singular), and design.md retires
the old banned-word loop entirely rather than re-basing it. But the bare
initialism remains in ~14 places including two out-of-scope test modules. Name
that residue when writing up the Req 11.9 losses, rather than leaving it an
unstated consequence of "the loop is gone".

**4.2/4.3 — `scan_tree` does no tracked/ignored filtering.** design.md's
ForbiddenStrings Service Interface says "every **tracked** file", but the
implementation walks everything under `root` and would descend `.venv/` and
`dist/` against a real repository. **4.3 must restrict `root`** (a tracked-only
view, or drive `matches` from `git ls-files`); it cannot be fixed by passing a
different root alone. The walk deliberately covers dot-paths — `.kiro/` is where
this repo's token-bearing prose lives — and there is a fixture pinning that.

**4.3 — an unreadable file is silent.** A file whose content cannot be read
(unreadable mode, broken symlink) yields **no hit and no report**, so an
unreadable tracked file passes the scan clean. 4.3 owes a report of files it
could not read; absence of a hit is not absence of the value.

**4.x — name the value-level detection loss at the guard site.** A lone pasted
constant is no longer detected: one token at ~19.9 bits cannot clear the 96-bit
entropy floor, so no fingerprint can exist for it under any salt. This is
declared in design.md and in `tests/_content_oracle.py`, but design.md's plan
for the re-based packaging guard requires that guard's docstring to state only
the lost verifiability (Req 3.6) and the retired token detections (Req 11.9).
State this loss there too, so a reader finds the decision where the capability
used to live.

**Do not hand-edit or regenerate `tests/_content_fingerprints.py` after 3.1.**
It is irreproducible once the material is deleted. Its shape guard is
`tests/purge/test_content_fingerprints_shape.py`.

---

Written by the session that implemented 3.1–3.2.

**The inventory 3.4 folds in is the out-of-repository `sweep-inventory.tsv`.**
322 hits across 77 tracked files, 2 unreadable records, plus a `.meta.json`
carrying `counts_by_disposition`, `unreadable_*` and a `recount_command` that
genuinely recounts. It is regenerated from the **staged** tree (`git add -N`),
because the sweep's universe is `git ls-files` and the purge's own new files
are untracked until commit — measured on the tree that merges, not the one on
disk. Re-run `scripts/purge/build_sweep_inventory.py` rather than editing it;
it reproduces byte-identically. `scripts/purge/sweep.py` is the one sweep
implementation — six passes, `classify_hit`, the TSV round-trip. Consume it.

**A figure in `design.md` or a task brief is a shape, and three have now
drifted.** Re-measured: **3** tracked sites for the third party's address, not
four (the fourth was inside the writeup 3.1 deleted); **5** files reachable
only via the token-free basename probe, not four; and the sdist exclusion
block had four entries, not two. Re-measure every count you are handed.

**A pass that finds nothing and a pass that never ran are indistinguishable in
the artifact.** The value matcher legitimately finds **0** in the current tree
now that 3.1 has deleted the material — proven a true negative by running the
real fingerprint set against the pre-deletion blobs from history, where it
flags all three. If a later task sees an empty pass, prove it that way before
believing it.

**Both content-reading passes report the same unreadable path, so each masks
the other at the `run_full_sweep` level.** A test at the aggregate level alone
cannot tell a half-fix from a fix — verified, after a half-fix shipped exactly
that way. Pin per-function, not only per-pipeline.

**`run_identity_probe_sweep` keeps its own copy of the exit-1-vs-real-error
split** rather than routing through `_git_grep_files`, because it needs `-o`
match output rather than the helper's `-l -z` path list. Both copies are
independently tested; if you change one, change both.

**The vocabulary lives in `design.md`'s `IdentityErasure` section, not in a
file of its own** — declared in the execution rules above. Every one of
3.5–3.12 and the 4.x guards reads it from there. It fixes prose forms, the
`training-load` component name, the calculator's class symbol *and* its dotted
module path, citations of deleted test names, Python identifiers including
locals, fixture stems and queue stems. **Take the form from the table; do not
improvise one.** Two `(P)` tasks writing different replacements for one erased
form is the failure it exists to prevent, and the first draft omitted exactly
the four classes that more than one task touches.

**Requirement 11.1 binds the purge's own tooling.** A bare identifying token
shipped into `tests/purge/test_sweep.py` inside a literal search command in a
comment, and a self-check written by hand missed it. The discriminating test
is mechanical: run the match data's token and path entries as **fixed
strings** and require every token hit to tie 1:1 with a path hit on the same
line — a path fragment is fine, a bare token is not.

---

Written by the session that implemented 3.4, after three rejections and a
root-cause investigation. Task 3.4 carries three corrections declared in place
above; this note records why, because the reason generalises to every prose
deliverable in this spec — 3.4 is not the last one.

**A prose record is verified per proposition, not per sentence.** 3.4 was
rejected three times for false factual claims while every mechanical check was
green: both matchers clean on content and path, every cited path resolving, no
address, suite and lint at baseline. Round 3 tried the obvious countermeasure —
enumerate every factual sentence, run the command that decides it, record the
output — and the reviewer confirmed 17 of ~20 re-run entries exactly, so the
method works where it reaches. It still failed, because the document averaged
**2.52 independently falsifiable propositions per sentence** (65% of sentences
carried more than one, the densest carried seven), and **four of five false
claims were sub-sentence clauses**. Sentence-level enumeration under-covers the
claim set by 2.5× and, worse, institutionalises the miss: one row per sentence
invites one command per sentence, and the sentence's dominant clause is the true
one. Round 3's inventory marked an entry VERIFIED on a `grep` for test function
names that could not decide a whole-suite claim, with the contradicting mutation
recorded on the very next line. **Write one falsifiable proposition per
sentence** — no em-dash appositive carrying a second claim, no semicolon
compound, no `, because` / `, so` tail asserting a further fact. That is what
makes the inventory sound, and it is cheaper than the fourth review round.

**Delete rather than restate.** ~30 of 84 prose sentences served no acceptance
criterion in the task, in `design.md`'s section list, or in any listed
requirement — and **every** proven-false claim and three of five overclaims lived
in that accreted set. Told that deletion was the cheap terminating move, one
round reported `CLAIMS_DELETED: none` and rewrote every claim, arguing a true
statement always existed. A true statement usually does exist; writing it is what
kept costing rounds, and that round installed two fresh false claims. Every
sentence must trace to a bullet, a `design.md` section, or a listed requirement.

**A claim repaired in one place survives in another.** Round 2's finding was
fixed at one site and left standing 130 lines later, where the cross-reference
then pointed the reader at the sentence contradicting it. One proposition per
sentence is also what stops a claim existing twice at two truth values.

**Nothing pins the truth of prose, so nothing reds when a repair writes
something false.** Established by mutation: planting a personal address in this
document leaves the suite fully green, and deleting the document entirely leaves
it at 2573 passed. Only Req 9.2's removed-material half is genuinely PINNED (a
planted value literal reds the sdist guard) and its token half only partly — the
personal name reds `test_docs_guarantees.py`'s filesystem `rglob` over `docs/`,
the trademarked abbreviation reds nothing. **Declare these UNPINNED rather than
letting a reviewer find them**, and prefer the two cheap mechanical gates that do
exist: every enumeration must sum to its own headline figure, and every numeral
must trace to a task-mandated data set.

**Do not enumerate a document's factual claims by reading.** That faculty missed
11 sentences and mis-marked 3 in the one round that tried hardest. A mechanical
split is scratch review evidence, not shipped tooling — `_Boundary:
ProvenanceRecord_` is a document with no module in the Component-to-file map, and
every `scripts/purge/` module has its own task and boundary.

---

Written by the session that implemented 3.5.

**Nothing in the suite pins a redaction. Every redaction task in Major 3 should
expect to declare its requirements UNPINNED.** Established by mutation on 3.5,
not by reading: reverting all five of its content redactions to their pre-edit
blobs — restoring the tokens, the third party's copyright notice, the stale
pointer, the removed-path key reference and the reproduced zone-table row —
leaves the suite at **2588 passed, 1 skipped, exit 0**. Deleting the source-
workbook ignore rule *and* planting an unignored workbook at the repository root
also leaves it green. Deleting the retained historical mentions leaves it green.
The one src-scanning token guard matches a CamelCase class name and two dotted
module paths only, so a **bare prose token in a docstring is invisible to it** —
which is why the single token-bearing file under `src/` was never caught by the
suite that ships it.

`PRESERVED-ONLY` is a claim that some pre-existing test would catch the
regression. For a redaction there is almost never such a test, and 3.5's first
report claimed it for three requirements where mutation showed nothing pinned
them. **Do not label a requirement PRESERVED-ONLY without watching a named test
go red.** A declared UNPINNED is an acceptable outcome under this repo's
protocol; a mislabelled one tells a later session a guard exists that does not.
3.5's corrected classification is UNPINNED for all nine of its sections.

**The ignore rule's survival is verifiable only mechanically.** `git check-ignore
-v` against a planted path, never by reading the pattern — no test covers it.

**A `(P)` redaction may be forced into a peer's test file, and that is not scope
creep.** 3.5 had to trim two entries from `_MODIFIED_FILES_TABLE_SAMPLE` in
`tests/purge/test_sweep.py`, because that tuple asserts the sweep still *hits*
those files and 3.5's own redaction is what stops it. Reviewer-verified as
forced, not a weakening: re-inserting either entry reds the test against the
current tree. **But the tuple is on a decay path** — every one of its ten
surviving entries names a file 3.6–3.12 are scheduled to redact, each forcing
the same removal, with only a non-empty check standing between it and vacuity.
Queued rather than fixed here.

---

Written by the session that implemented 3.9–3.12, all of Major 4, and
5.1–5.4. Every entry below cost at least one review round.

**Nothing in Major 3 pins a redaction, and Major 4's guards changed that only
for the surfaces they name.** The standing forbidden-string guard now scans
every tracked file's content, every tracked path name, and both built
artifacts — but it is **opt-in**: with the variable unset a planted token
leaves the suite green, by Req 11.8's contract. Before 4.3 landed, a token
planted in `README.md` left the suite green *with* the variable set. Do not
read a green suite as evidence about tokens unless you know the variable was
live, which the single complementary skip is how you know.

**A safety obligation needs a violating fixture at every layer that forwards
it.** The abandonment obligation was defeatable three times: derived from
backup refs that hold zero entries (5.1), accepting a tuple containing one
blank string (5.1 again), and hardcoded `True` by the driver while every test
stayed green (5.3). The gate itself was correct every time. The tell was an
asymmetry — hardcoding the *sibling* argument redded two tests instantly.
Parametrize a forwarded boolean over both values.

**Assert whole values, not membership.** In 5.3 the tests pinned regex
anchoring and directive ordering and left green every mutation that decided
*which repository gets destroyed* — the inversion flag, the target directory,
and which of two repository arguments the command was built from. One
whole-tuple equality closed all three and then withstood all 15 element drops
and 14 adjacent swaps.

**A loop over a collection does not pin the collection.** Dropping a member
leaves every remaining iteration green. 5.2 fixed an index-0 anchor with a
whole-set loop and still could not detect the set shrinking; an independent
count anchor beside the loop is what closed it, and that anchor later caught a
cross-module truncation.

**A coverage pin on the first member of a walk is defeated by exactly the
truncation it exists to catch.** 4.3's wheel anchor was the archive's first
member, so truncating to one member stayed green. Its sdist anchor was a `.py`
file, so filtering members to `.py` only dropped every `.md` while the anchor
stayed satisfied — and that is a *plausible* narrowing, not an artificial
slice. Anchor with two non-adjacent members of different kinds.

**Fixing one half of a symmetric guard and believing the guard is covered.**
5.2's containment check compares a resolved destination against a resolved
repository root. Round 2 pinned `.resolve()` on the destination; the identical
call on the other operand, three lines away, stayed unpinned for two more
rounds while the failure it allowed was real. Ask whether a "no unpinned
clauses remain" claim is *true* as a separate step.

**Never state a property of git, `filter-repo` or the stdlib without running
it.** 4.4's CLI retirement rested on "the listing renders from a registry
provably empty at fresh import" — disproved by building a synthetic installed
distribution: the registry read empty while the rendered table named the
planted calculator, because registration happens *during* discovery. 5.4
removed an archive guard on "extractfile returns `None` for non-regular
members" — it returns a reader for symlinks and *raises* when the target is
absent, which crashed the artifacts row on this project's own sdist.

**Opportunistic mutation converges slowly and dishonestly.** 5.4 took five
rounds because targets were chosen by what caught the eye, each round closing
with "the bounded remainder" and each being wrong. Enumerating the module
mechanically — every git flag, every format token, every loop source, every
comparison, every branch — found three material survivors at once and made the
remainder closed-form. This applies to reviewers as much as implementers.

**An exemption is as wide as whatever it excepts, and it goes stale silently.**
4.1 replaced a one-file self-exemption with an unbounded one by decoding to
text and skipping what would not decode — one stray byte in front of the real
table shipped it undetected. 4.3's exemption table was surface-blind (a token
in a *filename* was exempted by an entry meant for detection *data*) and keyed
by path rather than value. 4.4's own deletions then left three entries pointing
at files that no longer matched, so re-introducing the retired needle into the
two files it had just cleaned was silently exempt on every surface.

**Prose in a test file is a claim, and this major's rejections were mostly
prose.** Species seen: a mutation-caught note for a mutation that does not red
the test; a "non-gameable" claim disproved by planting the escape it named; a
requirement number cited for a rule belonging to the *task* of the same number;
a task brief quoted as a specification document; and a de-tokenised quotation
of a commit subject that has never existed. Verify per proposition, one
falsifiable proposition per sentence, and `grep -F` anything you quote.

**A guard over a module that must itself call something dangerous cannot
discriminate on names — the information is in the arguments, the count, and
the syntactic position.** Task 5.5's "no code path removes the source
directory" guard oscillated through three mechanisms before a debug pass
root-caused it. `adopt.py` legitimately needs `subprocess.run` and
`shutil.move`, and *each of those names alone suffices to destroy the source*
(`git clean -xdff`; `move(source_repo, decoy)`), so every name-set rule --
blocklist *or* allowlist -- must admit both and thereby admit destruction. The
shape that works is three orthogonal arms: a closed allowlist of the module's
own effectful surface (bounded by the module, not by the reviewer's
imagination, which is why it terminates), argument pinning on the admitted
names, and position pinning so an admitted name may appear only as a call
callee. Counts belong in the pin too: aggregating call shapes into a `set`
made a *second* identical call site invisible, and moving the source aside
onto a decoy path is indistinguishable from removing it.

**Replacing a detection mechanism means owning everything the old one caught.**
Round 2 swapped a substring scan for an AST walk, closed the four shapes it was
rejected for, and silently lost two the substring scan had caught -- then round
3's fix reinstalled those same two shapes one arm over. Both rounds read as
fixes and passed their own author's mutation table. Take the union, and
re-plant every shape from every prior round before reporting.

**Prose is where this spec's rejections live, and the grep is not what catches
them.** Four of five rounds on task 5.5 shipped exactly one false factual
sentence; the round that shipped none was the one that read every sentence and
made each happen. The false ones were ordinary: a docstring denying a vacuity
that was real, a drift claim disproved by adding one constant elsewhere, a
"positive-control walk" that passed having scanned nothing, and a
cross-reference miscounting its own siblings.

---

Written by the session that implemented 7.2, after three rejections and a debug
escalation. The code half took one round; the other three were all prose.

**A test that installs a double must assert the double is in effect**, via an
observation the undoubled call could not produce: capture the unpatched result
first, then assert the patched result differs, then assert the value. Three
tests here monkeypatched `subprocess.run` and asserted against a `tmp_path`
that was not a git repository — where the *unpatched* call returns the same
`()` / `""` the patch was supposed to produce. All three passed; all three
pinned nothing; an ordinary `from subprocess import run` refactor silently
defeated the guard they existed to be. This is the `pre-satisfied fixture`
anti-pattern applied to **doubles** rather than to input data, and every
example in `change-protocol.md`'s table is about data — which is why an agent
applying that table faithfully still ships it. Queued for steering.

**Write the mutation sweep to a file before writing the fixtures, and the
prose last.** A sweep that is *asserted rather than produced* has a selection
effect: rows that yielded a test survive as comments, rows concluding "no test
needed" leave no trace — and the unrecorded half is exactly where a real
`--all` hole hid behind a claim to have covered "every git flag". Each
reviewer then re-ran the sweep by hand and found new ground, which reads as
non-convergence when it is really an unrecorded artifact.

**Delete a population-quantifying claim; do not correct it.** Every false
claim in this task counted or characterised the fixture population — and the
remediation edit is exactly what changes that population, so a correction
written inside the edit describes the file the author *read*, not the file the
author is *producing*. It is stale at the moment of writing. Three rounds,
three corrections, three new false claims, each born from the fix for the
last. Re-derive any number you keep, mechanically, after the final edit.

**An "equivalent mutant" declaration needs the same evidence as a test.** One
row here was declared unpinned-by-construction because "no real `git` produces
distinguishing output" — verbatim the argument the same round used to justify
*needing* its monkeypatch fixtures. The distinguishing fixture took fifteen
lines. `roots[0]` vs `roots[-1]` under a preceding `len(roots) != 1` guard is
a genuine equivalence and is declared in the sweep file; that one was checked.

---

Written by the session that implemented 7.3.

**The prose is where this module's rounds go, and the fix is deletion.** 7.3's
code passed review on the first pass and was re-verified sound three times —
no coverage lost across 24 dropped tests, the three-arm destruction guard
un-widenable under seven attacks, the halt correct against the real `.git`,
30+7 reviewer mutations with zero survivors. Every subsequent rejection was a
false sentence in a docstring, and each round's *correction* produced the
next one. Five rounds. When a module's docstrings carry more claims than the
tests can support, cut the claims; do not improve them.

**A forced substring is not a licence for the sentence around it.**
`tests/purge/test_cli.py` pins the literal `CloneAdoption` for the `adopt`
stub, so the retired component's name cannot be deleted from `run()`. The
round that discovered this reframed it truthfully — and then appended a new
invented clause describing the 7.6 driver's call order, which inverted
`design.md` steps 3 and 6. Keep the forced token, add nothing.

**Defer an ordering claim to the document that owns it, after checking that
document actually states it.** `run()` now says the call order is stated by
`design.md` › `HistoryReplacement`, not here. That is only honest because
that section names `adopt.assert_commit_identity` at step 3 and
`adopt.assert_carry_over` at step 6 literally. A deferral to a silent
document is a false claim wearing a citation.

**`move_clone` is the one function `design.md` never names.** Step 7 states
where its operation sits, but the module also says the swap's two moves are
"kept out of this module". Task 7.6 should either call `move_clone` for the
fresh-`.git` move or the design should say which helper performs it —
otherwise 7.6 reimplements the refuse-if-target-exists guard `move_clone`
already provides.

---

Written by the session that implemented 7.4, after three review rounds. The
mechanism was right in round one; everything after it was documentation.

**A guard's docstring is a claim about the guard, and needs executing like any
claim about git.** This is the one lesson that generalises, and it was learned
by contrast within a single round. The round that fixed the reflog rationale
*ran* `check_reflog_and_unreachable_gone` against a `--no-local` clone, found
it reports **not clean** every time (a clone writes three `clone: from ...`
reflog entries), and caught two of its own draft sentences that way before
submitting — including one calling the verification clone "bare", which
`rev-parse --is-bare-repository` flatly refutes. The single sentence it
*reasoned* to instead — that the new design-table parser reds on a row
**added** — was false, and a 14th row left the module green.

**"Vacuous against a fresh clone" was true of one half of a function and false
of the other.** The unreachable-object half is genuinely vacuous (a
`--no-local` clone has none by construction); the reflog half is the opposite —
it reds by construction. A sentence citing the module docstring while widening
its scope past the half it was written about is how that shipped. The correct
reason a row is excluded from the fresh-clone re-run can be *either* "cannot
fail" or "cannot pass"; they are not interchangeable and only measurement
tells you which.

**A row run against the wrong repository passes for free, and the design's two
halves disagree about which rows run against the verification clone.** The
fresh-clone row says "re-run the rows above"; the per-row column marks exactly
one row `C`. 7.4 implements four and says so as a judgment call rather than
presenting a criterion — an earlier draft's criterion ("marked `F, W` only")
excluded three rows and included three others under the same marking. Queued.

**Pinning a tuple's order against a document needs a count anchor, or it is
addition-blind.** A monotonic `str.index` cursor catches a dropped or reordered
row and steps silently over an inserted one. The count anchor closes it and is
what `change-protocol.md` asks of every walking guard — verified by removing
the anchor, inserting a 14th row, and watching all 89 tests stay green.

---

Written by the session that implemented 7.5, after four review rounds. Two of
the four rejections were the controller's own fixtures, which is the point of
the entry.

**A test that installs a double must assert the double's EFFECT, not its
precondition.** The fixture added to pin the read-back through
`apply_repair`'s real write path asserted only that the starting content
differed from what the double would write. Measured: replacing the double's
body with `return 0` left the whole module green **and** silently un-pinned
the very mutation the fixture existed to kill — the untouched stale content
mismatched too, so the raise still happened, for the wrong reason. The fix is
one line after the `raises` block asserting the file now holds what the double
wrote. This is the same rule this spec put in the shared log three tasks
earlier, applied wrongly by the session that wrote the rule down; knowing it
is not the same as checking it.

**Discriminate on the property the requirement names.** The fixture for "the
read-back compares every pin" gave its extra on-disk pin a *different* value,
so it discriminated on value and a duplicate-collapsing read-back sailed
through. The same value in both positions makes the COUNT the only difference,
and kills four count-blind shapes at once.

**A remediation prescribed by a reviewer is a hypothesis, not a fix.** Three in
a row were incomplete on this one read-back path: the reviewer's prescribed
two-outcome test did not kill `_pin_values(...)[:1]`; its follow-up suggestion
did not kill `outcomes[:1]`; and the controller's own fixture did not kill a
no-op double. Each gap appeared only on running the mutation. Run the
prescription before believing it, and grep-confirm the mutation text landed —
one mutation in this task silently failed to apply and returned a green suite
that would have been recorded as evidence.

**Classify survivors by direction before treating them as findings.**
Permissive survivors (accepting what should be refused) are defects;
over-strict and equivalent mutants are not. `expected` here is always a
constant tuple of the epoch repeated, so every permutation-insensitive
comparison is unkillable by construction — a dead axis, not a gap. Saying so
explicitly is what stops a later round re-finding it.

---

Written by the session that implemented 7.6, the destructive driver, after
three review rounds. The structure was right in round one; every rejection
after it was pinning or prose.

**"The code is safe" and "the module is guarded" are different claims, and
only the second survives the next edit.** `replace.py` shipped with no
effectful-surface guard while `adopt.py`, which does strictly less, had one.
A reviewer planted `git clean -xdff` against the working tree and a
move-aside-and-back of the repository root, and both left the suite green.
Neither was a defect in the code as written; both were defects in what the
tests would notice. A module that performs an irreversible operation needs
the guard *before* the operation, not after someone edits it.

**Counts in the pin are what catch the evasion that looks legitimate.** The
sharpest probe against the finished guard was a shadowed receiver — `log =
old_git_dir / "packed-refs"` then `log.open("a")` — which presents an
*admitted* receiver and an *admitted* mode and is invisible to both. It is
caught because it is a second `open` call and the count arm fires. Every
other arm passed it.

**A shape check is not an existence check, and the difference decides whether
the archive is real.** `_assert_archive_readable` used `git rev-parse
--verify --quiet`, which validates only the SHAPE of a 40-hex id: measured on
git 2.54.0 it exits 0 and echoes the id back for an object that does not
exist, while `git cat-file -e` exits 1. This is the last gate before the
archive becomes the only copy of the old history on this machine *(as written
it said "before the remote is deleted, after which the archive is the only
copy" — true of the plan at the time; Amendment 3 retains the remote, so the
archive is not the only copy anywhere. The gate's value is unchanged)*. The test had been written *around* the weakness — it used a
deliberately non-hex bogus id, which passes under either implementation and
so pinned nothing about which check was used.

**A guard firing on your own change is the guard working; updating its pin is
where guards die.** Changing the archive argv redded Arm B immediately. The
pin had to move with it — and the only honest way to do that is to establish
the new shape is strictly stronger and that nothing else was relaxed, which
is a different exercise from making the test pass.

**Line citations drift, and this plan already says not to use them.** Five
`replace.py:NNN` references in new comments were each exactly 27 lines low by
the time the file was finished. They were replaced with symbol names, not
recomputed.

**A flat grep will not find a quotation that wraps.** Checking a design.md
quote with `grep -c` returned zero and looked like a fabricated citation; the
text wraps at `archived / whole` and is verbatim once whitespace is
collapsed. This spec built a wrap-tolerant matcher for exactly this and the
lesson still had to be re-learned while *auditing someone else's* citation.

---

Written by the session that implemented 7.7 and 7.8, closing Major 7. Six
review rounds across three changes, three rejections, all substantive.

**A summary of a change is a claim about the change; the diff is the change.**
7.8 must classify every criterion Amendment 1 touched. The first pass took that
work list from `spec.json`'s prose description of the amendment, concluded four
criteria qualified, and wrote that enumeration into the durable provenance
record as fact -- where it then licensed skipping everything else. One command
refuted it. Four rows were left stale, three of them false against the tree.
Where a task says "everything the amendment touched", the amendment diff IS the
work list.

**Ask what the subject actually contains before you pin it.** Retiring a test
whose premise died with the old mechanism dropped a real property: the
replacement pins covered two reflog subtrees that a faithful reproduction of
the driver showed the post-swap repository does not have. Blinding the walk to
the subtree it DOES have left the full suite green. The older lesson was
"updating a pin is where guards die"; the sharper one is that a pin aimed at a
structure the production path never produces is decoration.

**A git command that filters input it cannot resolve is a false-negative
machine, and this spec has now met three.** `rev-parse --verify` validates
shape, not existence. `status --porcelain` reds on untracked files that survive
by design. `git reflog show --all` silently omits entries whose objects are
absent and still exits 0 -- so after a replacement, where pre-replacement
objects are gone by construction, both an emptiness check and a naive
resolve-check pass vacuously on the exact failure Req 7.3 names. Ask what a
command does with input it cannot resolve BEFORE resting a verification row on
it.

**When a fix and its predecessor keep swapping which side is wrong, stop
rewriting and measure the whole table.** One paragraph describing a two-armed
assertion flipped from understating one arm to overstating it across three
rounds, each error introduced by the edit correcting the previous, and both
were falsifiable in ninety seconds with `stat` and `rev-parse`. It was closed
by the reviewer supplying measured text and the parent applying it verbatim --
free re-authoring was the mechanism of the oscillation.

**"No narrower mutation exists" is a claim that needs a search.** A row
justified a 17-test blast radius as architecturally unavoidable; the adjacent
line yields a sole failure. Asserting unavoidability understated the record's
own strongest evidence.

**Delete a count you cannot verify by a sound method.** A population figure was
removed from the provenance record rather than defended; an independent
computation later showed it had been right. Deleting was still correct -- the
diff, not a paragraph, is the authority on extent.

---

Written by the session that implemented 7.7. **APPROVED after three rejections
and four review rounds.** The first five reviewer dispatches died on
server-side API 529 errors, four before their first tool call; the parent ran a
bounded mutation pass itself and recorded it as a downgrade rather than an
equivalent artifact. Once the API recovered, real reviews ran and rejected
three times. Across them the reviewers ran ~30 mutations of their own with one
survivor, and every rejection was a real defect.

**The code converged in round one; the PROSE oscillated for three rounds, and
that is the lesson.** The rehearsal itself was sound from the start — every
independent probe since has confirmed it. What flipped was one paragraph
describing what a two-armed assertion detects: round 1 said the stat arm was
inert ("only the `HEAD` comparison carries real weight"), round 2 said it was
sovereign ("the sole detector of `.git` itself being replaced or rewritten"),
and both were falsifiable in ninety seconds with `stat` and `rev-parse`. The
paragraph kept flipping because each author *reasoned* about the two arms
instead of measuring all four cells of a two-by-two table. It was closed by
the reviewer supplying measured-true text and the parent applying it verbatim
— deliberately not by dispatching another agent to re-author it, since free
re-authoring was the mechanism of the oscillation. **When a fix and its
predecessor keep swapping which side is wrong, stop rewriting and go measure
the whole table.**

**The verification row's contract can be a rewrite-era leftover, and 7.4's
re-scoping pass missed one.** `verify.py::check_reflog_and_unreachable_gone`
demands `git reflog show --all` report literally nothing. Measured twice
independently (implementer, then parent, real git 2.54.0): after the shipped
`run_replace` path, that command reports four entries — two per ref, `clone:
from <src>` and `Branch: renamed ...` — every one resolving to the forged root.
Req 7.3's actual text holds; the row's stricter contract does not. `fsck` is
empty and `rev-list --all --count` is 1, so only the reflog half is broken.
Left unfixed, **Major 8's `verify-local` false-reds on a correct replacement**
and fires swap-back for nothing. Same defect class as the porcelain false red
7.4 corrected, and for the same reason: written when the mechanism was an
in-place rewrite, where reflogs COULD hold pre-rewrite commits. Under
Decision 7 the fresh `.git` is a clone that never saw the old history.

**A declared exemption from the mutation gate is itself a claim.** The
implementer exempted `_assert_untouched` — the assertion protecting the real
repository — arguing no meaningful mutation existed. Measuring found three, two
of which fire: a new entry inside `.git` (mtime) and a moved `HEAD` are caught;
**a move-aside-and-back of `.git` is not**, because a rename preserves the
inode and leaves the directory's own mtime alone. That is the same evasion a
reviewer planted successfully against `replace.py` one task earlier. Queued.

**The mutation lever for a test-orchestrated step is test-side, and that is
fine.** The rollback half is driven by the test's own `adopt.move_clone` calls,
so no single-line production mutation isolates it. Neutering the rollback reds
`assert not archive_dir.exists()` immediately, and the post-swap assertions
already established the restored state was FALSE beforehand — so the rollback
assertions are not vacuous, which is the property that mattered.

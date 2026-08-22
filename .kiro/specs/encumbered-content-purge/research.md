# Research & Design Decisions — encumbered-content-purge

## Naming convention used by this document

This log is a tracked file and therefore in scope for the purge it researches
(Req 1.3, Req 11.1). It uses `design.md`'s vocabulary — *the withdrawn
methodology*, *the third party*, *the identifying tokens*, *the writeup*, *the
extracted tables*, *the withdrawn calculator package* — and writes no identifying
token, no personal address and no extracted value. Sections dated 2026-07-31 were
added when requirements Decision 5 reversed the name-retention ruling; earlier
sections were retro-fitted to the same convention in the same pass, and two of
their conclusions were **corrected rather than deleted** where the reversal
falsified them.

## Summary

- **Feature**: `encumbered-content-purge`
- **Discovery Scope**: Complex Integration — a one-shot destructive operation
  across the whole object database, plus a permanent change to the mechanism
  that guards against its reversal.
- **Key Findings**:
  1. **The re-introduction guard's detection data is nine plaintext literals,
     not digests.** The fingerprint constant in `tests/load/test_packaging.py`
     is a concatenation of three tuples of verbatim value strings; there is no
     `hashlib` import in the module. The guard is therefore the largest single
     in-repo copy of the removed tables, it ships in the sdist, and it exempts
     itself from its own scan by path.
  2. **`git filter-repo` rewrites `refs/original/` forward rather than dropping
     it**, carrying the encumbered files and the maintainer's personal address
     into the rewritten repository under new SHAs. Verified on a throwaway
     clone. Those refs were then deleted mid-session — but **deleting a ref does
     not delete its objects**: 496 commit objects carrying the personal address
     remain unreachable in the object database. What removes them is the
     `--no-local` clone, which copies only reachable objects.
  3. **`git fetch origin <sha>` cannot measure GitHub retention.** GitHub
     advertises `allow-reachable-sha1-in-want` but not `allow-any-sha1-in-want`,
     so an unreachable-but-stored object is refused with the same error as an
     absent one. The authenticated web-UI SHA probe is the only measurement
     that can falsify retention.
  4. A per-value digest oracle cannot satisfy Requirement 3.7 at any KDF cost,
     because the removed values are low-entropy by format. An entropy-gated
     **window** digest can, and measures cheaper and strictly more accurate
     than the substring matcher it replaces.
  5. The reproduction sweep found four sites beyond the known one, including a
     complete worked-example vector used as a live migration test fixture and
     the guard module itself.

  6. **The content-digest oracle cannot guard an identity, by construction.**
     The scheme detects multi-token windows clearing a 96-bit entropy floor and
     explicitly does not detect a single isolated value; an identifying token is
     exactly one isolated low-entropy token. Any design that reaches for "digest
     the name like the tables" is wrong, and the temptation is strong enough that
     the limit is now stated twice in `design.md`.
  7. **Six guards across four modules detect re-introduction by matching an
     identifying token literally, and three further assertions require the token
     to still exist.** The second group are positive controls built to fail
     exactly on the scenario Req 11 mandates. A complete scrub cannot be
     performed without rewriting both groups.
  8. **History holds four encumbered table blobs, not two, and 19 token-bearing
     paths.** The withdrawn calculator package carried its own copies of both
     lookup tables at distinct blob ids, differing from the `docs/reference/`
     copies by a prepended copyright line. Content classification reaches those
     blobs; nothing in the prior design reached the path *names*.
  9. **No commit is pruned by the removal set**, verified across all 433: every
     commit that touches a removed path also touches a surviving one. That is
     what keeps Req 9.3's commit map complete, and `--prune-empty never` converts
     it from a measured accident into a structural guarantee.

## Research Log

### Guard anatomy — what the two re-introduction guards actually do

- **Context**: Requirement 3 requires both guards to survive deletion of what
  they read, keep a positive control, and hold no data from which the material
  can be read back. Choosing a replacement oracle requires knowing the current
  mechanism exactly.
- **Sources consulted**: `tests/load/test_packaging.py` (614 lines),
  `tests/test_docs_guarantees.py` (802 lines), `pyproject.toml`, the three
  `conftest.py` files, `git grep` across all 539 tracked files.
- **Findings**:
  - The fingerprint constant (`:150-154`) is the concatenation of three
    value tuples (5 items at `:103-109`, 2 at `:126-129`, 2 at `:133-136`).
    All five constant names carry an identifying token. Nine plaintext
    strings in total. Matching
    is `value in text` (`:285`) and `fp.encode() in content` (`:576`) — raw
    substring, no normalisation, case-sensitive.
  - The shipped-module constant guard opens the writeup
    at `:244-246` and globs `docs/reference/**/*.csv` at `:266`, purely as an
    **anti-drift cross-check** that the literals are still verbatim quotations.
    Deletion makes it raise `FileNotFoundError` before the actual scan runs.
  - The sdist record-and-path guard reads no
    removed file. It exempts its own source by exact path at `:567` — a
    self-exemption that exists *because* the module carries the material.
  - `tests/test_docs_guarantees.py`: the absence guard is at `:116-154`
    (a literal token-absence assertion), its positive control at `:221-248`,
    which opens the writeup at `:238-240` and additionally asserts the
    *un-excluded* corpus violates the sibling's property — that second
    assertion is the load-bearing one. After deletion no file in
    `README.md` + `docs/**/*.md` contains the name, so the exclusion filter at
    `:214` becomes a no-op and the control has nothing to point at.
  - The steering-pairing guard (`:157-202`) holds a control
    (`assert mentioning`, `:193`) that is a **live tripwire**: it fails if the
    purge ever scrubs the identity from steering. Discovery's name-retention
    decision kept it green; **requirements Decision 5 reverses that decision**,
    so this control now fails by construction and is re-based rather than
    preserved — see the identity findings appended below.
  - `[tool.hatch.build.targets.sdist]` exists solely for this purge; both
    `exclude` entries and its 13-line comment are dead on deletion.
  - `[tool.mypy].files` covers `tests/test_docs_guarantees.py` but **not**
    `tests/load/test_packaging.py`.
  - House conventions to inherit: every walking guard carries an explicit
    non-vacuity control; allowlists are module-local and compared by
    **equality**, not subset (`_LOAD_MODULE_ALLOWLIST`, `:384-385`), so a
    phantom entry reds as loudly as a missing one; the strongest
    self-guarding-allowlist idiom is `tests/test_docs_guarantees.py:325,343-344`.
- **Implications**: the oracle must be replaced, not patched; the
  self-exemption at `:567` loses its justification; and the docs-guarantees
  control must be rebuilt on a synthetic corpus rather than a real file.

### Reproduction sweep — what the purge must actually redact

- **Context**: Decision 1 widened the sweep from `docs/reference/` to every
  tracked file. Requirement 1.2 enumerates nine classes of content that may
  not survive anywhere.
- **Sources consulted**: `git ls-files` (539 files), `git grep -P` (note: this
  git build does not honour `\b` under `-E`; several probes returned empty
  until redone with `-P` or `-F`).
- **Findings** — reproductions, by site:
  | Site | What is reproduced |
  |---|---|
  | `.kiro/specs/training-load/research.md:51-58` | Densest site in the tree: both load formulas symbolically, the discount-**generating** rule as a closed-form expression, both worked-example vectors as full input to output pairs, zone count with points-per-minute endpoints, per-zone repeat domains, validation ranges |
  | `.kiro/specs/training-load/research.md:357, :478` | Both worked-example totals; one zone-table row |
  | `tests/load/test_packaging.py:103-136, :100, :117, :234` | Nine table values verbatim, plus three more quoted in comments and a docstring |
  | `tests/load/test_render.py:616-626` | The v1 payload fixture body constant — a complete worked-example vector: point total, zone number, zone label, interval structure, HR-basis percentage, together in one dict |
  | `src/fitdocs/load/docedit.py:387` | A zone-table row in a shipped docstring |
  | `.kiro/steering/roadmap.md:473` | The interval structure string as a vocabulary example |
  | `.kiro/queue/2026-07-27-withdrawal-evasions-one-level-up.md:36-37` | Two pace rows and one race-equivalent row, self-described as copied verbatim |
- **Findings** — judged **not** reproductions, with reasoning:
  - `.kiro/specs/training-load/research.md:61-62` names the *input dimensions*
    the weather and terrain tables require, not their values. Naming an input
    dimension transmits nothing.
  - The two worked-example point totals appear as bare scalars at ~15 further
    sites (`src/fitdocs/load/docedit.py:365`, `src/fitdocs/load/render.py:451`,
    and stub-calculator fixtures across `tests/load/`). A scalar with no
    inputs, no zone and no attribution transmits nothing of the methodology.
    The repository reached this conclusion independently:
    `tests/load/test_packaging.py:98-101` records that one of these totals was
    **tried as a fingerprint and dropped because it collides with unrelated
    float-formatting examples**.
  - Withdrawn requirement stubs at
    `.kiro/specs/training-load/requirements.md:314-327` and the marker-name
    lists in `.kiro/specs/distribution/` are names only.
- **Implications**: the sweep is a one-time act over the tree, and the two
  guards do not and cannot replace it — the content-keyed oracle detects value
  tables, not symbolic formulas. That limit is declared in the design rather
  than left implicit.

### Contact details — the exposure is larger than the requirements assumed

- **Context**: Requirement 5 assumed three sites for the third party's address
  and one file for the maintainer's.
- **Findings**:
  - Third-party address: **four** tracked sites, not three. The fourth is this
    spec's own `brief.md:86`. Requirement 5.1 is absolute ("no file at any
    commit"), so the brief is in scope for its own redaction. The
    `.kiro/specs/distribution/design.md:616` site is **example config data**
    inside a proposed `release/licensing.toml` block, which is what
    Requirement 5.5 anticipates.
  - Maintainer's personal address: exactly one tracked site, line 3 of the
    prior rewrite map, inside the prose header. Verified by scanning every
    blob in the entire object database.
  - **The 2026-07-26 rewrite is incomplete in this clone, and its residue
    outlived the refs that held it.** When first measured, 602 commits were
    reachable from all refs: 428 on `main` carrying the non-personal address,
    and **174 carrying the personal address, reachable only from
    `refs/original/`** — a partition verified exact in both directions. Those
    refs were deleted later the same day. Re-measured 2026-07-31 after the
    deletion: every ref-reachable commit is clean, and `git fsck --unreachable`
    reports 384 unreachable commits, 1146 trees, 118 blobs, with **496 commit
    objects in the object database still carrying the personal address**. The
    exposure moved from reachable to unreachable; it did not go away.
  - A **third** personal identifier exists: the reflog-only dangling commit
    `e97fff7a` ("Initial repo setup") carries, in both headers, a
    git-constructed address of the form `<username>@<machine-name>.local`. It is
    not reachable from any ref, so Requirement 5.3 does not reach it;
    Requirement 7.3 does. **This log stated the identifier literally until
    2026-07-31**, which made a tracked, reachable file the only copy of it in the
    repository — the same recursion Req 3.7 resolves for the table values,
    reached by accident rather than by design. It is now described rather than
    quoted, and `design.md` adds it to the redaction probe set so the history
    sweep does not depend on this file having been the only site.
  - No commit **message** anywhere in history contains an email address.
- **Implications**: path filtering alone misses three of the four third-party
  sites; content replacement is mandatory. Deleting the `.tsv` is necessary but
  not sufficient while `refs/original/` stands.

### History-rewrite tooling

- **Context**: choose the tool and establish, rather than assume, what it does
  to `refs/original/`, the reflog, the remote and the commit map.
- **Sources consulted**: [git-filter-branch man
  page](https://git-scm.com/docs/git-filter-branch); [git-filter-repo
  manual](https://raw.githubusercontent.com/newren/git-filter-repo/main/Documentation/git-filter-repo.txt);
  [git-filter-repo
  source](https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo);
  [converting-from-bfg-repo-cleaner](https://github.com/newren/git-filter-repo/blob/main/Documentation/converting-from-bfg-repo-cleaner.md);
  `git-config(1)` local man page, git 2.54.0. Plus dry runs on throwaway
  `--no-local` clones.
- **Findings**:
  - `git filter-branch`'s own man page: *"its use is not recommended. Please
    use an alternative history filtering tool such as git filter-repo"*. BFG is
    additionally disqualified — it protects the HEAD commit's file hierarchy by
    default, and these files are present at the tip.
  - Nothing is installed locally (`which git-filter-repo`, `pipx`, `brew`,
    `import git_filter_repo` all negative). `git-filter-repo` is a **single
    Python file**; running it as `python3 git-filter-repo …` against git 2.54.0
    was verified to work with no install step.
  - **`refs/original/` is rewritten forward, not dropped.** After a purge run
    with those refs present, `refs/original/refs/heads/main` still existed and
    `git log --all --format=%ae` still listed the personal address. This is the
    single most important operational finding.
  - filter-repo's fresh-clone `sanity_check()` requires, among others: repo
    fully packed, exactly one remote named `origin`, every `refs/heads/X`
    equal to `refs/remotes/origin/X`, every reflog at most one entry, no stash,
    and **exactly one worktree**. This repository fails at least three. The
    supported answer is to operate on a `git clone --no-local`, not to reach
    for `--force`.
  - filter-repo **removes the `origin` remote** after rewriting, and renames
    `refs/remotes/origin/*` into `refs/heads/*`.
  - A non-`--partial` run unconditionally runs `git reflog expire --expire=now
    --all` and `git gc --prune=now`. Verified post-run: `.git/logs/HEAD` empty,
    `count-objects` 0 loose, `fsck --unreachable --dangling` empty.
  - **Commit map**: `.git/filter-repo/commit-map`, one `<old> <new>` line per
    commit, *including unchanged commits*; deleted commits get an all-zeros new
    SHA. The dry run produced **428 lines for 428 commits**, root commit
    included. This satisfies Requirement 9.3 with no extra tooling. Siblings:
    `ref-map`, `changed-refs`, `suboptimal-issues`, and
    **`first-changed-commits`** — the exact artifact GitHub Support asks for.
  - Removing a root-commit path needs no special flag. Commit count preserved
    (428 → 428); the root commit had 65 files, 3 removed, so it does not become
    empty and is retained. `--prune-empty=auto` only prunes commits that
    *become* empty.
  - `suboptimal-issues` reported **44 abbreviated SHAs quoted inside commit
    messages** left as-is by design; they dangle after the rewrite.
  - Two distinct mechanisms are needed and both run in one pass:
    `--replace-text` for blob **content**, and `--mailmap` / `--email-callback`
    for commit **metadata**.
- **Implications**: the rewrite runs in a fresh clone; `refs/original/*` is
  deleted in the source first; the commit map is a free by-product; `origin`
  must be re-added by hand afterwards.

### GitHub retention of unreachable objects

- **Context**: Requirement 8.1 forbids assuming a force-push removes the
  objects, and requires an empirical measurement.
- **Sources consulted**: [GitHub — Removing sensitive data from a
  repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository);
  [Truffle Security — Anyone can Access Deleted and Private Repo Data on
  GitHub](https://trufflesecurity.com/blog/anyone-can-access-deleted-and-private-repo-data-github);
  [Neodyme — Hidden GitHub Commits](https://neodyme.io/en/blog/github_secrets/);
  `git-config(1)`; direct read-only probes of `origin`.
- **Findings**:
  - GitHub's docs are explicit that a force-push is **not** sufficient:
    *"those commits may still be accessible in any clones or forks of your
    repository, directly via their SHA-1 hashes in cached views on GitHub, and
    through any pull requests that reference them"*, and *"Once you have pushed
    a commit to GitHub, you should consider any sensitive data in the commit
    compromised."*
  - The documented remedy is **contacting GitHub Support** to dereference PRs,
    run server-side gc and remove cached views. Support *"won't remove
    non-sensitive data, and will only assist … where we determine that the risk
    can't be mitigated by rotating affected credentials"* — licensed
    third-party text is not a rotatable credential, so the design must not
    assume Support will act.
  - Deleting and recreating the repository is **not mentioned** in the article
    — neither recommended nor forbidden.
  - Probing `origin` directly showed it advertises
    `allow-tip-sha1-in-want` and `allow-reachable-sha1-in-want`, but **not**
    `allow-any-sha1-in-want`. Per `git-config(1)`,
    `uploadpack.allowAnySHA1InWant` is *"By default not set."*
    Confirmed empirically: fetching a reachable non-tip ancestor succeeds;
    fetching an absent SHA fails with `upload-pack: not our ref`.
  - **Therefore `git fetch origin <old-sha>` is a false-negative machine**: a
    retained-but-unreachable object is refused with exactly the same error as a
    deleted one. Same blind spot for `git clone --mirror` + `cat-file`.
  - No retention **duration** is documented anywhere. Secondary sources quote
    git's generic 2-week `gc.pruneExpire` default, which is a statement about
    local git, not about GitHub's servers.
- **Implications**: the only probe that can falsify retention is an
  authenticated `GET https://github.com/<owner>/<repo>/commit/<old-sha>`
  (200 = still served, 404 = gone). Because no expiry is documented, a
  *measurement* can only ever be a point-in-time observation — the only
  construction that gives a **guarantee** is a repository that never stored the
  objects.

### Local verification — which commands are actually complete

- **Findings**:
  - Path enumeration must be object-graph based:
    `git rev-list --all | xargs -n1 git ls-tree -r --name-only`.
    `git log --all --diff-filter=A --name-only` is **not** complete — it is
    parent-relative, so it misses paths introduced by the root commit, which is
    exactly this case.
  - Content enumeration: `git rev-list --objects --all` piped through
    `git cat-file --batch`.
  - `git cat-file -e <sha>` answers "is this object in the store", not "is it
    reachable" — the right primitive for proving a blob is physically gone.
  - **`git clone --local` is not evidence.** It hardlinks the whole object
    directory including unreachable objects. A controlled experiment carried
    169 unreachable objects into a `--local` clone and 0 into a `--no-local`
    clone; pack link counts (2 vs 1) confirm the mechanism. Verification clones
    must use `--no-local`, and `.git/objects/info/alternates` must be absent.
  - `git fsck --unreachable --dangling` is meaningful against the rewritten
    **source** repository and vacuous against a fresh clone.
  - `refs/original/` expiry is not a reflog matter — those are real refs and
    must be deleted with `git update-ref --stdin`.
  - Default `gc.reflogExpire` is 90 days and `gc.pruneExpire` 2 weeks, both
    unset here, so a plain `git gc` after a rewrite prunes nothing useful.

### Live repository hazards found while researching

- `.git/packed-refs` is **stale right now** (records `main 80cc5c5` while the
  loose ref is current). Benign for git, but a live instance of the classic
  "deleted a ref by removing the loose file, packed copy resurrected it"
  hazard. Delete refs only via `git update-ref -d` / `--stdin`.
- A linked worktree keeps its own `HEAD`, index and reflog under
  `.git/worktrees/<name>/`, which pin pre-rewrite objects against `gc` even
  after the main reflog is expired. `git count-objects -v` currently warns
  `garbage found: .git/worktrees/fitdocs-purge-design/refs`.
- `.git/ORIG_HEAD` exists and `.git/logs/HEAD` has ~303 entries.
- A peer session removed `impl/load-channels` and its worktree during this
  research run — concurrency is live, which is what Requirement 6 is for.

### Identity surface — where the tokens actually are (2026-07-31)

- **Context**: Requirement 11 puts file contents, tracked paths, historical
  paths and commit messages in scope. Sizing all four was a precondition for
  deciding rename-versus-delete and for scoping the cross-spec edit.
- **Sources consulted**: `git grep -licE`, `git ls-files`,
  `git rev-list --all | xargs -n1 git ls-tree -r --name-only`,
  `git log --all --grep -i`, plus a full read of the four guard modules.
- **Findings**:
  - **63 tracked files** carry a token: 9 specs, 13 queue items, both steering
    documents, the test tree, `pyproject.toml`, `.gitignore`, `CLAUDE.md`, and
    exactly **one** docstring under `src/`. The `src/` hit is prose in a
    dataclass docstring with no test asserting on it — zero behavioural cost.
  - **5 tracked paths** and **19 historical paths** carry one. Requirements
    recorded 18 historical paths a day earlier; the difference is ordinary drift
    of the kind those documents warn about, not a disagreement.
  - The withdrawn calculator package is present in the tree of **83 of 433**
    commits and was touched by 7.
  - **26 of 433 commit messages** carry a token, several in the *subject*.
  - Classification of the token sites in executable surfaces: ~150 are comment
    or docstring prose, 8 are module-private Python identifiers, 6 are guard
    detection data, 6 are path strings, and 12 are string literals in fixtures.
    **None is compared against by any module under `src/`.**
  - The v1 payload fixture's recorded calculator identity is read via
    `inspect_payload`, stored on the payload stamp, and f-stringed into a skip
    reason by the engine. Traced end to end: no equality test, no dict key, no
    registry lookup anywhere in `src/`. Two *test* assertions match it inside a
    skip message and move with the fixture.
- **Implications**: Req 11.11 changes no behaviour and Req 10.2 survives intact;
  the cross-spec edit is broad but uniformly redaction-only; and the guard work,
  not the prose sweep, is where the difficulty is.

### Rewrite mechanics for paths, renames and messages (2026-07-31)

- **Context**: the prior design's rewrite carried two transforms. Requirement 11
  adds path renaming and commit-message rewriting, and all four must ride one
  pass or cost a second whole-history rewrite.
- **Sources consulted**: the `git-filter-repo` manual and source, plus dry runs
  on seven throwaway `--no-local` clones.
- **Findings**:
  - `--invert-paths` and `--path-rename` **do** combine in one invocation.
    `--invert-paths` flips only the filter verdict; rename directives are a
    separate modification applied to survivors. `--paths-from-file` is the only
    form expressing filters and renames as one ordered list.
  - **Directive order is load-bearing and fails silently.** Directives apply in
    file order and a rename mutates the name later filters match against. With a
    rename line before a deletion line for a file inside the renamed directory,
    the file **survived** under its new name; reversing the order removed it.
    Every deletion line must precede every rename line.
  - `--replace-message` exists and shares `--replace-text`'s parser and syntax
    (`literal:` / `glob:` / `regex:`, optional `==>`, default replacement a
    placeholder string). Neither expressions file's content lands in the
    rewritten object database — verified by scanning it afterwards.
  - **Word-boundary anchors under-match.** `_` is a word character, so
    `\b`-anchored patterns cannot match a token inside an identifier: a
    `\b`-anchored set left **6 of 26** messages dirty, every survivor an
    identifier or a class name. Expressions must be unanchored,
    case-insensitive, and ordered longest-phrase first.
  - **`--prune-empty=auto` does prune**, and a pruned commit maps to forty zeros
    in the commit map — a hole in Req 9.3. Verified on a synthetic history
    (6 commits in, 4 out, 6 map entries, 2 all-zeros).
  - **Short-SHA references in messages are rewritten by default**, matched as
    hex runs of 7 to 40 characters and re-abbreviated to the same length. A
    6-character reference is left alone; so is a reference to a commit that did
    not survive. This **falsifies the prior design's stated position** that such
    references are left as-is.
  - Full combined dry run: **433 commits in, 433 out**, zero all-zeros rows,
    zero token-bearing paths remaining, old blobs unreachable after
    filter-repo's automatic reflog-expire and gc.
- **Implications**: one invocation is sufficient; the three silent-failure modes
  above are encoded as explicit rules in `design.md` rather than left to the
  implementer; and one prior stated position is corrected rather than carried
  forward.

### Untracked state that survives adoption (2026-07-31)

- **Context**: Req 11.13 requires a stated position on carried-across untracked
  state that still contains an identifying token.
- **Findings**: two such states exist. The two gitignored source workbooks carry
  tokens in their **filenames**; the ignore rule that excludes them is a bare
  `*.xlsx` pattern carrying no token, so nothing tracked names them once the
  comment above that rule is rewritten. The shared agent log carries tokens
  across sixteen lines of its content; it lives under the common git directory,
  is never tracked, and its root symlink ships in the sdist as a **dangling**
  link whose target is not archived.
- **Implications**: both take recorded acceptance rather than redaction.
  Redacting the agent log was considered and rejected — it is the append-only
  record peer sessions coordinate through, and rewriting it would falsify what
  earlier sessions said, the same objection Req 11.6 raises against falsifying a
  record. One standing hazard is recorded instead: a future packaging change that
  follows symlinks would turn a non-leak into a leak.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|---|---|---|---|---|
| Rewrite in place with `--force` | Run filter-repo against the working repository, overriding its sanity checks | No clone step; worktrees and machine-local files stay put | Overrides checks that exist precisely for this situation; leaves reflogs, `ORIG_HEAD` and linked-worktree logs pinning old objects; `refs/original` rewritten forward | **Rejected** |
| Rewrite in a fresh `--no-local` clone, then adopt the clone | Clone, delete `refs/original` first, filter, verify, then replace the working repository with the rewritten clone | Passes every sanity check unforced; old objects cannot survive because they were never copied; matches the tool's own intended model | Machine-local and gitignored files must be carried across deliberately, including the shared agent log | **Selected** |
| Two separate specs (tree removal, then history) | Split the two majors | Smaller units | Major 1's "done" is misleading on its own — deleting from the tree while history serves the same blobs achieves nothing | **Rejected at discovery** |

## Design Decisions

### Decision: replace the value oracle with entropy-gated window digests

- **Context**: Requirement 3.2 requires the guards to keep detecting the
  removed material without any file holding it verbatim; Requirement 3.7
  forbids retaining detection data "in any form from which the material can be
  read back". Today's data is nine plaintext literals.
- **Alternatives considered**:
  1. **Keep the literals as de-minimis constants.** Directly violates 3.7 and
     leaves the guard shipping the largest in-repo copy of the tables.
  2. **Per-value digest, salted.** The salt must live in the repository for the
     guard to run on a fresh clone (3.1), so it only defeats precomputed
     tables. The values are low-entropy *by format*: an 8-decimal fraction is
     10^8 candidates, a `MM:SS` clock time is ~3.6×10^3. Brute-force is
     seconds.
  3. **Per-value digest, key-stretched (scrypt/PBKDF2).** Raises the cost per
     candidate but not the candidate count. At 50 ms/candidate a `MM:SS` value
     falls in minutes. **No KDF cost can rescue a 12-bit secret.**
  4. **Shape-only guard** — forbid any bundled data table under `src/fitdocs/`.
     Holds no content and resists renaming, but detects *any* table rather than
     *this* material, which is not what 3.2 asks for. Its subject is the
     breadth question owned by two other queue items.
  5. **Entropy-gated window digests** (selected).
- **Selected approach**: fingerprint **ordered windows of consecutive numeric
  and clock-time tokens**, not individual values. The source file is tokenised
  in document order and canonicalised (clock times to total seconds, decimals
  to a canonical float repr). Starting at each offset, tokens are accumulated
  until the window's estimated guessing entropy — summed per token from its
  **format class**, which is the only thing an attacker needs to know — clears
  a floor; that window is digested with a repository-resident salt and the
  cursor advances past it. Scanning digests every window length present, at
  every offset, so a match is phase-independent.
- **Rationale**: reading a value back requires guessing every token in a window
  simultaneously and in order. The threshold is the security property, and it
  is stated rather than assumed.
- **Measured** (prototype over the real files at `1b98cae`, values never
  printed):
  | Measurement | Result |
  |---|---|
  | Source tokens | 225 (writeup), 767 + 1460 (the two CSVs) |
  | Stored digests at a 96-bit floor | **400**, 16 hex chars each — 6.4 KB |
  | Window lengths produced | 3 to 20 tokens |
  | Whole-tree scan, 538 files, 67,045 tokens | **2.50 s** |
  | False positives tree-wide | **0** — the only three matches are the three files being removed |
  | Re-added verbatim / renamed and reindented / re-embedded as Python dict literals | detected in all three |
- **Trade-offs**:
  - **Strictly better** than the substring matcher on reformatting: today a
    trailing-zero variant, a different precision or a comma decimal separator
    all evade the guard. Canonicalisation defeats all three.
  - **Strictly better** on false positives: the collision that forced a
    worked-example total to be dropped as a fingerprint
    (`tests/load/test_packaging.py:98-101`) cannot recur, because a lone scalar
    never forms a window.
  - **Weaker on isolated scalars.** A single pasted value is not detected. This
    is a deliberate consequence of the entropy floor, it coincides with the
    class the repository already judged undetectable-without-collisions, and it
    is declared in `design.md` rather than left implicit.
  - **Verified limitation**: the prototype does **not** flag today's
    `tests/load/test_packaging.py`, whose nine literals are scattered across
    three tuples with comments between them. The scan is therefore not, on its
    own, proof that the guard module is clean — the tree-wide sweep is.
- **Follow-up**: the salt is durable and published; it carries none of the
  security. Record that in the module docstring so a later session does not
  "improve" the scheme by hiding it.

### Decision: rewrite in a fresh clone and adopt it

- **Context**: filter-repo's sanity checks, plus finding that reflogs,
  `ORIG_HEAD` and linked-worktree logs all pin pre-rewrite objects.
- **Selected approach**: quiesce → record the abandonment of the two
  `refs/original` branches → delete `refs/original/*` in the source →
  `git clone --no-local` → filter-repo in the clone → verify → adopt the clone
  as the working repository → destroy the old repository directory.
- **Rationale**: old objects cannot survive an adoption boundary they were
  never copied across. Every sanity check passes unforced.
- **Trade-offs**: gitignored and machine-local state must be carried over
  deliberately. The list is concrete and short, and **the shared agent log
  (`.git/agent-log`) is on it** — it is not tracked, so a fresh clone loses the
  repository's multi-session memory unless it is copied by hand.
- **Follow-up**: `git worktree prune` and a re-`uv sync` after adoption.

### Decision: repair the machine-consumed field, resolve the rest through the map

- **Context**: Requirement 9.4 requires open items' `pinned_at:` to resolve.
  Requirements 9.5 and 9.6 require a *stated position* on closed items, the
  README's schema example, and a test fixture whose filename names a commit.
  The sweep found the blast radius is far wider than the requirements assumed:
  **163** files carry `pinned_at:` (111 open, 51 closed, plus `README.md:40`),
  76 distinct SHAs, all currently resolving; **40** further genuine commit pins
  sit in spec prose, `roadmap.md` and `.claude/hooks/queue-commit-guard.py`;
  and `.kiro/queue/` bodies hold roughly **496** hex tokens in evidence
  sections and resume commands.
- **Selected approach**: mechanically repair **`pinned_at:` only** — open,
  closed, and the README example alike, giving one invariant rather than two
  classes. Every other commit reference is left exactly as written and is
  resolvable through the provenance map. The repair tool **reports** every
  SHA-shaped token it did not rewrite, and that count goes into the provenance
  record.
- **Rationale**: `pinned_at:` is the only field any tooling resolves as a
  commit — `/kiro-queue` runs `git log --oneline <pinned_at>..HEAD` against it.
  Everything else is prose recording what was true at a moment. Rewriting
  prose SHAs would falsify the record; a peer session has already ruled that
  the frozen "merged at `<sha>` with N tests green" snapshots in `roadmap.md`
  must not be "corrected" for exactly this reason.
- **Trade-offs**: ~536 prose references stay superseded-but-resolvable. That is
  the map's whole purpose.
- **Known unresolvable**: `.kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md:12`
  holds a **branch name** in `pinned_at:`, not a SHA — a pre-existing schema
  violation. It cannot be mapped, so Requirement 9.8 applies: record it as
  unresolvable rather than substitute a plausible commit.

### Decision: the fixture filename is accepted as historical

- **Context**: Requirement 9.6 requires a position on
  `tests/fixtures/report_baseline_faa6d09.py`.
- **Alternatives considered**: rename to the post-rewrite SHA — touches the
  filename, `_PRE_TASK_CLI_COMMIT`, three header mentions, and prose in
  `.kiro/specs/inbox/tasks.md:194`, `roadmap.md:800` and a closed queue item,
  propagating a second cross-boundary edit into another approved spec.
- **Selected approach**: keep the name; record it as historical and resolvable
  through the map; add a one-line pointer in `tests/test_cli_drain_report.py`.
- **Rationale**: the baseline is **vendored precisely so no test resolves it
  against git** — that was the fix for a prior defect where a shallow clone
  turned a green tree into a `CalledProcessError`. The name is a human-read
  label, not a machine-consumed reference, which is exactly the distinction
  that decides the queue-pin question the other way.

### Decision: measure the remote, then move to a repository that never held the objects

- **Context**: Requirement 8.1 forbids assuming; 8.4 permits reconciliation up
  to deleting and recreating the remote.
- **Selected approach**: force-push, then probe the authenticated web URL for a
  set of pre-rewrite commit SHAs, record the result, then reconcile. Because no
  expiry is documented and the git protocol cannot see retention, the
  recommended reconciliation is to publish to a **new empty repository** and
  delete the old one.
- **Rationale**: this repository is private, fork-free and PR-free, so the two
  documented persistence vectors mostly evaporate — but the cached-view /
  direct-SHA vector remains and has no published expiry. A repository that
  never stored the objects has nothing to retain; that converts a
  point-in-time measurement into a structural guarantee, at near-zero cost
  here. The measurement is still taken and recorded because 8.1 and 8.6 require
  it, and because it is the evidence justifying the stronger action.
- **Trade-offs**: the repository name is briefly unclaimed between delete and
  recreate. Stars, forks, issues and PRs would be lost — there are none.
- **Follow-up**: if the maintainer prefers to keep the existing repository,
  the fallback is force-push plus a GitHub Support request carrying
  `.git/filter-repo/first-changed-commits`, with the probe repeated over
  following days. Support may decline: licensed third-party text is not a
  rotatable credential.

### Decision: fold the roadmap Phase 5 divergence into this spec

- **Context**: `.kiro/queue/2026-07-30-phase5-constraints-outrank-settled-requirements.md`
  reports that `roadmap.md` Phase 5 still states three constraints the
  requirements phase settled the other way. The queue item was filed **after**
  `requirements.md` merged, so no acceptance criterion covers it.
- **Selected approach**: correct all three passages in this spec, declared
  openly in `design.md` as an addition to scope.
- **Rationale**: `roadmap.md:804-811` still says unlanded work is *orphaned* by
  the rewrite, while Requirement 6 says the purge *halts* — and steering is
  what every session loads as project memory, while `requirements.md` is not. A
  purge session holding steering and not requirements would read that as
  authorisation to proceed over a peer's unlanded work, **today**. The purge
  edits Phase 5 anyway for three other reasons, so the marginal cost is a few
  lines.

### Decision: erase the identity with no replacement name, and move token detection outside the repository

- **Context**: Req 11.7 forbids retaining an identifying token "in any form from
  which it can be read back", and six guards currently detect re-introduction by
  matching one literally. Req 11.8 constrains whatever replaces them.
- **Alternatives considered**:
  1. **Keep the token literals as de-minimis constants.** Directly violates
     Req 11.7 and leaves the guards as the last copies of the identity in a
     public repository — the exact recursion Req 3.7 already resolved for values.
  2. **Digest the tokens with the content oracle.** Impossible: the oracle
     declines single isolated low-entropy values by construction, and a name is
     one. Adding a per-value mode would reintroduce the brute-force weakness the
     oracle was built to avoid.
  3. **Substitute a pseudonym and guard on that.** Offered to the maintainer and
     declined: inventing a substitute proper name risks colliding with a real
     person in a repository whose narrative is about copyright and permission.
  4. **Retire the guards and detect nothing.** Cheapest, and it is what happens
     to three of the six anyway — but it silently gives up standing detection of
     the one thing publication makes irreversible.
- **Selected approach**: one shared source reads the forbidden strings at run
  time from a file named by `FITDOCS_FORBIDDEN_STRINGS`, refuses a path that
  resolves inside the repository, and **skips distinguishably** when the variable
  is unset. One standing guard scans tracked contents, tracked path names, and
  both built artifacts. The remaining literal guards are retired and the lost
  detection is stated.
- **Rationale**: it is the only construction that satisfies Req 11.7 without
  giving up detection entirely, and the in-repo-path refusal is what stops the
  obvious convenience from undoing it.
- **Trade-offs**: detection becomes opt-in and only the maintainer can enable it;
  a renamed re-introduction under a neutral name now passes. Both are stated
  under Req 11.9 rather than discovered later.
- **Follow-up**: the Req 11.8 meta-tests are the load-bearing assertions — that
  `require` raises pytest's skip exception when unset, and that a *broken* source
  raises rather than degrading into the absent case. Collapsing "broken" into
  "absent" is how a guard comes to report success having checked nothing.

### Decision: delete the withdrawn calculator package from history rather than rename it

- **Context**: Req 11.2 requires no path at any commit to contain a token. The
  withdrawn calculator package and its test mirror account for 13 of the 19
  token-bearing historical paths and neither exists in the working tree.
- **Alternatives considered**:
  1. **Rename to a neutral path.** Preserves the narrative that a calculator was
     implemented and withdrawn, at its original paths.
  2. **Delete from history.** Removes path and content together.
- **Selected approach**: delete.
- **Rationale**: the package's modules implement the load formulas Req 1.2 names,
  and its own copies of both lookup tables are encumbered material Req 7.1
  requires gone by content regardless. A rename would relocate encumbered content
  and a copyright notice to a token-free path, leaving both still to remove.
  Deletion settles path and content in one rule. Nothing depends on it: it was
  withdrawn on 2026-07-25 and is absent from the tip.
- **Trade-offs**: the implementation history of the withdrawn calculator is no
  longer inspectable. The *fact* survives in the commit messages, the specs and
  the provenance record, which is what Req 11.5 asks for.
- **Follow-up**: verified that deleting it prunes no commit; the three
  token-bearing queue paths take the opposite treatment (renamed, because their
  content is a record worth keeping) and their ids change with them.

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| `refs/original/` rewritten forward, carrying the material and the personal address into the "purged" repository | Delete `refs/original/*` if present and assert absence either way; the `--no-local` clone is what actually drops the objects. Verified failure mode, not a hypothetical |
| Req 6.6's abandonment record discharged by accident because the refs it was derived from vanished | The abandoned branch names are an **explicit input** to `QuiescenceGate`, never derived from live refs — this nearly happened during the design phase itself |
| The mailmap written to a tracked `.mailmap`, shipping the personal address in the sdist | Mailmap is a `$TMPDIR` scratch artifact passed by absolute path; a post-rewrite check asserts no `.mailmap` in the tree |
| Personal `.fit` data in `.git/lost-found/` and a second copy of the rewrite map in `.git/` carried forward by anyone salvaging the old `.git/` | Both named in `CloneAdoption` as deliberately not carried; adoption is what removes them |
| A linked worktree's own reflog and index pin pre-rewrite objects | Quiescence gate refuses to proceed while any additional worktree exists (Req 6.1); adoption of a fresh clone makes it moot |
| `--replace-text` patterns miss a historical spelling of a symbolic reproduction | The redaction plan is computed by scanning **every historical blob**, not guessed; the post-rewrite whole-object-database scan is the gate, and Req 7.7 forbids pushing before it is clean |
| Verification performed with `git clone --local` proves nothing | `--no-local` mandated and `alternates` checked; the 169-vs-0 experiment is recorded so the reason survives |
| `git fetch <old-sha>` read as proof of removal | Recorded as a false-negative machine; the web probe is the only measurement that can falsify retention |
| The shared agent log is lost when the clone is adopted | Named explicitly in the carry-over list, alongside `.fitdocs/data-root`, the gitignored workbooks and the page scans |
| The purge scrubs the identity and silently disarms a guard | **This risk was realised, not avoided.** Requirements Decision 5 mandates the scrub, so `tests/test_docs_guarantees.py:193` now fails by construction. Mitigation is re-basing it onto the withdrawal *fact* plus the externally-supplied token guard, with the lost detection stated under Req 11.9 |
| The re-based guard's data becomes unverifiable and nobody knows | Req 3.6 requires it stated; it is stated in the guard module docstring **and** the provenance record |
| Abbreviated SHAs quoted inside commit messages dangle | **The earlier "not rewritten" position was wrong.** filter-repo translates 7-to-40-character hex runs in messages by default; only shorter refs and refs to non-surviving commits are left, and those are reported in `suboptimal-issues`. The provenance record states that count and its reason |

| Directive order in the paths file silently un-deletes a file | Every deletion line precedes every rename line; verified failure mode reproduced on a throwaway clone, and the rule is stated in `design.md` rather than left to the implementer |
| `\b`-anchored replacement expressions leave tokens inside identifiers | Expressions are unanchored and case-insensitive, longest phrase first; the post-rewrite gate is that **zero** messages match the forbidden-string set, not that the mapping was applied |
| A pruned commit puts a hole in the Req 9.3 commit map | `--prune-empty never` passed explicitly, *and* the plan step halts if any commit's diff lies entirely inside the removal set |
| The forbidden-string guard passes having checked nothing | Unset is a **skip**, asserted by a meta-test; a broken source **raises** rather than degrading to the absent case, asserted separately for each of four broken cases |
| The forbidden-string file is "helpfully" placed in the repository | The source refuses a path resolving inside the working tree, so the convenience cannot be taken |
| The prose sweep deletes whole sentences containing a token, leaving a repository that appears never to have evaluated anything | Req 11.5 is a retention obligation and Req 11.6 forbids falsifying a record; the four site kinds and their treatments are enumerated under `IdentityErasure` |
| A later session invents a replacement proper name to fill the hole | Req 11.12 forbids it and `design.md` states the maintainer's reason — a coined proper name risks colliding with a real person |

## References

- [git-filter-branch man page](https://git-scm.com/docs/git-filter-branch) — the deprecation notice recommending filter-repo
- [git-filter-repo manual](https://raw.githubusercontent.com/newren/git-filter-repo/main/Documentation/git-filter-repo.txt) — `--invert-paths`, `--replace-text`, `--mailmap`, commit-map format, "Why is my origin removed?"
- [git-filter-repo source](https://raw.githubusercontent.com/newren/git-filter-repo/main/git-filter-repo) — `sanity_check()` and `cleanup()`, read to establish exact behaviour rather than infer it
- [converting-from-bfg-repo-cleaner](https://github.com/newren/git-filter-repo/blob/main/Documentation/converting-from-bfg-repo-cleaner.md) — BFG's default HEAD protection
- [GitHub — Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository) — force-push is not sufficient; Support process; cached views
- [Truffle Security — Anyone can Access Deleted and Private Repo Data on GitHub](https://trufflesecurity.com/blog/anyone-can-access-deleted-and-private-repo-data-github) — cross-fork object references; GitHub's "working as expected" response
- [Neodyme — Hidden GitHub Commits](https://neodyme.io/en/blog/github_secrets/) — unreachable commits remain viewable by SHA
- `git-config(1)`, git 2.54.0 — `uploadpack.allowAnySHA1InWant` / `allowReachableSHA1InWant`
- `.kiro/steering/change-protocol.md` › Fixture Discrimination — the mutation-evidence gate every new assertion in this spec owes
- `.kiro/queue/2026-07-30-sdist-guard-has-no-positive-control.md` — converges into Requirements 3.3/3.4
- `.kiro/queue/2026-07-30-phase5-constraints-outrank-settled-requirements.md` — folded in, see the decision above
- `git-filter-repo` `--paths-from-file`, `--path-rename`, `--replace-message`, `--prune-empty` — directive ordering, expression syntax, and the 7-to-40-character short-SHA rewrite rule, all verified on throwaway clones rather than inferred
- `.kiro/specs/encumbered-content-purge/requirements.md` › Decision 5 — total erasure with no replacement name, and the four consequences the maintainer accepted

## Amendment 1 regeneration — discovery and synthesis (2026-08-17)

Scoped design regeneration after Decision 6 (fresh root replaces the in-place
rewrite) and Decision 7 (in-place mechanism: `.git` swap, old `.git` archived,
carry-over re-scoped to `.git`-resident items). Requirements re-approved by the
maintainer the same day. Discovery was integration-focused: what exists, what
the replacement can reuse, and what Requirement 12's retirement entangles.

### Findings

- **Machinery inventory at 73344d6**: fourteen modules under `scripts/purge/`
  (7,532 lines) and seventeen test modules under `tests/purge/`. Of these, the
  replacement reuses `preflight.py` unchanged, re-scopes `adopt.py`,
  `verify.py` and `pins.py`, and needs one new thin driver; everything else
  was built for the retired mechanism and retires unused.
- **Two retirement entanglements, both measured by import inspection, both
  resolved by re-homing into the surviving module**:
  1. `tests/_forbidden_strings.py` (survivor) lazily imports
     `_whitespace_tolerant_pattern` from `scripts/purge/replacements.py`
     (retiree) — the arrow is backwards against the design's stated
     dependency direction and predates Amendment 1.
  2. The notice/mark tip guard
     (`test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`)
     and its never-spelled-contiguously constants live in
     `tests/purge/test_replacements.py` / `replacements.py` — it is a tip
     re-introduction guard Req 12.2 requires kept, hosted inside machinery
     Req 12.1 requires deleted. The rules-facing invariant-6 tip-no-op guards,
     by contrast, retire with the rules: their subject is the rule set.
- **The pin contract**: `/kiro-queue` runs
  `git log --oneline <pinned_at>..HEAD -- <context paths>`, so a repaired pin
  must resolve in every clone of the replacement. 155 open entries at
  measurement (a shape, not a budget).
- **Reusable verification rows**: `verify.py`'s ref, metadata,
  old-identifier-refusal, reflog/unreachable, message, fresh-clone, artifact
  and remote-probe functions apply to the replacement unchanged; the
  commit-map, mailmap and whole-history enumeration rows have no subject left.
- **Provenance record state**: part one (sections 1, 2, 4, 5, 6 plus evidence
  appendices) is landed; section 3 and the remainder of section 6 were never
  written, so re-specifying part two contradicts nothing already recorded.

### Design decisions

- **Fresh `.git` by reachable-only copy, not by construction in place**: forge
  the parentless root with `git commit-tree` on the certified tip's tree, then
  `git clone --no-local` that single ref. The new object database's contents
  are exactly {root, certified tree, blobs} by a property this spec has
  already measured (a `--no-local` clone carries zero unreachable objects),
  which is Decision 7's "swap, never prune" made mechanical. Rejected
  alternative: `git init` plus object import, which would re-derive what the
  clone semantics already guarantee.
- **Pin epoch convention (Req 9.4)**: every open `pinned_at:` becomes the
  replacement root's short id. Keeps the machine consumer working with correct
  semantics (`<root>..HEAD` = everything since the replacement), is uniform,
  resolves forever, and is documented in the queue README rather than
  improvised. Explicitly distinguished from a Req 9.8 substitution: the root
  is an epoch marker, not a claimed counterpart.
- **Retirement in two phases**: R0 re-homes the two entangled survivors before
  deletion; R1 deletes after the replacement is verified (Req 12.5), as its
  own ritual change. Two `tests/purge/` modules relocate rather than retire
  (`test_content_oracle.py`, `test_content_fingerprints_shape.py`) because
  their subjects survive.
- **Scratch disposition**: only the forbidden-string source survives — it is
  standing guard data, not machinery. The `.git` archive is governed by
  Decision 7, not by scratch rules.
- **Ordering constraint surfaced by synthesis**: the archive's readability is
  asserted *before* the remote deletion, because from that moment the archive
  is the only copy of the old history anywhere.

### Simplifications taken

The replacement design deletes rather than adapts: no redaction plan, no
replacement rules, no commit map, no clone adoption, no multi-transform
invocation. `RedactionPlan` has no successor component — nothing about the
replacement is classified, because nothing pre-existing survives into it. The
execution sections got shorter; the safety argument moved from "every rule
verified against every historical blob" to "one tree identity plus one
reachable-only copy", which is the whole point of Decision 6.

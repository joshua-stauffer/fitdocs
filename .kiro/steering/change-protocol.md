# Change Protocol

How a change lands in this repo — source, tests, steering, skills, hooks,
specs, docs, config. One ritual for all of them. `concurrency.md` owns
multi-session coordination (claims, choke points, the shared log); this
document owns the lifecycle every change follows, solo or not.

**Read the shared log before you start, every time** —
`cat "$(git rev-parse --git-common-dir)/agent-log"`. Peer sessions are
invisible from inside your own worktree, so this read is how you find out
whether `concurrency.md` applies to you at all. Assuming you are solo because
nothing in your tree says otherwise is how conflicts get made.

## The Rule

**A non-trivial change is made in its own worktree on its own branch, and is
done only when it is merged to `main` with validation green and `main` is
pushed to `origin`. Every commit is pushed the moment it is made, on every
branch.** `main` is an integration branch, not a workbench, and this machine
is not where the repository lives.

This started as an implementation rule and, for a while, was obeyed only
there. Steering edits, skill rewrites, hook changes and spec revisions went
straight onto `main` and sat uncommitted for days. That is backwards: those
files decide how every later session behaves, so an unreviewed, unvalidated,
uncommitted diff does more damage in `.kiro/steering/` or `.claude/skills/`
than in `src/`. The artifact type does not change the ritual.

The push half was added on 2026-09-16, the day a subagent's
`cd <uncreated dir> && rm -rf .git && git init` ran in the main tree — the
`cd` failed, the rest executed — and deleted the repository database: every
local object, ref and reflog. At that moment `main` was eight commits ahead of
`origin/main` and the entire Phase 7 spec batch sat on one worktree branch that
had never been pushed. It was recovered only because the working trees
survived and a session happened to hold a copy of the log; had the remote been
current, recovery would have been `git clone`. **A commit that exists on one
machine is not landed anywhere.** The remote is the durable copy, and the only
way it is guaranteed current is to make it current as each commit is made — a
push deferred to "when the branch merges" is a push that is not there when the
tree dies mid-branch.

## Triage

**Trivial** — may be done on `main`, still committed with a real message and
pushed:

- a typo, whitespace, or formatting fix that changes no instruction and no
  behavior
- a stale path or link corrected to the file it already meant
- appending an item to `.kiro/queue/` (session bookkeeping — exempt by
  design, see Enforcement)
- machine-local files that are never committed (`.fitdocs/data-root`,
  `.venv/`)

**Non-trivial** — worktree, branch, merge-back. This is the default:

- anything under `src/`, `tests/`, or `pyproject.toml`
- a `.kiro/steering/*` edit that adds, removes, reverses, or re-scopes a rule
- anything under `.claude/skills/**`, `.claude/hooks/**`, or
  `.claude/settings.json`
- a new or revised `requirements.md`, `design.md`, or `tasks.md`
- anything spanning more than a couple of files, or that you would want a
  reviewer to see

The test, when the lists don't settle it: **if this edit is wrong, does a
later session behave differently?** Yes → non-trivial. Prose that instructs an
agent is behavior; treat it like code.

## Lifecycle

```bash
# 0. Read the log, then claim what you are about to work on
LOG="$(git rev-parse --git-common-dir)/agent-log"; cat "$LOG"
printf '%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "<session>" CLAIM "<what> (worktree ../fitdocs-<slug>, branch chore/<slug>)" >> "$LOG"

# 1. Branch. impl/<spec> for spec work, chore/<slug> for everything else
git worktree add ../fitdocs-<slug> -b chore/<slug>
cd ../fitdocs-<slug>
uv sync                              # .venv/ is gitignored: one per worktree

# 2. Machine-local config is NOT in git — recreate it per worktree
mkdir -p .fitdocs && echo "<data-root path>" > .fitdocs/data-root
# (or export FITDOCS_DATA; see the data-root contract in tech.md)

# 3. Make the change. Commit as you go, on the branch, and push each commit in
#    the same line. -u on the first push records the upstream the Stop guard reads.
git add <paths> && git commit -m "..." && git push -u origin chore/<slug>
git add <paths> && git commit -m "..." && git push

# 4. Integrate — part of finishing, not a follow-up
git fetch && git rebase main         # resolve conflicts here, in your tree
git push --force-with-lease origin chore/<slug>   # the rebase made new commits: push them
<validation for the change class>    # AFTER the rebase, against integrated work
git switch main && git merge --ff-only chore/<slug> && git push origin main

# 5. Tear down — the local branch and its remote copy
git worktree remove ../fitdocs-<slug> && git branch -d chore/<slug>
git push origin --delete chore/<slug>
```

A branch whose base is uncommitted work in another tree cannot be created this
way. That is a signal, not an exception: land the base first.

## Push On Commit

Every commit is pushed to `origin` in the same breath it is made — `commit &&
push` on one line, never a later step. There is no branch this does not apply
to and no commit small enough to skip it.

- **First commit on a branch**: `git push -u origin <branch>`. The `-u`
  records the upstream; the Stop guard judges the branch against it, and a
  branch holding commits with no upstream is a block in its own right.
- **Every later commit**: `git push`.
- **After a rebase**: `git push --force-with-lease origin <branch>`. The
  rebase made new commits and orphaned the ones on the remote; the lease
  refuses if anything else moved the branch meanwhile. This is the only
  sanctioned force, it applies only to your own `chore/`/`impl/` branch, and
  bare `--force` is never used.
- **After a `--ff-only` merge to `main`, and after a trivial commit on
  `main`**: `git push origin main`. Name the remote and branch — `main`'s
  tracking config is exactly the kind of local state the `.git` loss erased,
  and an explicit refspec does not depend on it. `main` is never
  force-pushed. If the push is rejected as non-fast-forward, `origin/main`
  moved without passing through this machine: `git fetch`, rebase onto
  `origin/main`, re-run validation, push again.
- **Teardown**: `git push origin --delete <branch>` alongside the local
  `git branch -d`. Once `main` holds the commits and is pushed, the remote
  branch is a duplicate that would otherwise accumulate forever.

A remote branch is not a review request and not a message to peers — the
shared log is. It is a backup that costs one command and is current by
construction — the backup that was not there on 2026-09-16.

## Definition of Done

Identical for every change class:

1. The change is complete, or its unfinished parts are named explicitly
2. Validation for the class is green (below)
3. The branch is rebased onto current `main`
4. Validation is re-run **after** the rebase — pre-rebase green does not count
5. Merged `--ff-only` to `main`, and `main` pushed to `origin`; worktree and
   branch removed, locally and on the remote
6. Nothing left uncommitted, in any tree; nothing left unpushed, on any branch
   — `git rev-list origin/main..main` is empty
7. The merge is in the shared log, along with anything a peer needs to know
   about what it changed for them

Uncommitted work is not done. Committed work that exists only on this machine
is not done either — it is one `rm -rf` from never having happened. A merged
branch whose validation only ran before the rebase is not done. Work a peer
cannot see landing is not done either — the log line is what makes the merge
visible from inside another worktree. If merge-back is genuinely blocked, that
is a finding to report — not a state to leave behind.

## Validation By Class

| Change class | Green means |
|---|---|
| `src/`, `tests/`, `pyproject.toml` | `uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy` (scope is config-driven via `[tool.mypy].files`, not a path argument, so it cannot drift from this row) |
| `.kiro/steering/**` | The edited doc read end to end, plus a grep across `.kiro/steering/` and `CLAUDE.md` for statements the edit just contradicted — every copy of the rule moves in the same change |
| `.claude/skills/**` | The skill exercised once end to end on a real target, or an explicit statement of why it cannot be run and what was inspected instead |
| `.claude/hooks/**` | A synthetic payload fed to every branch — at least one that fires and one that passes — with the output shown. Hooks fail silent; only execution proves them |
| `.claude/settings.json` | Valid JSON *and* the configured behavior observed once |
| `.kiro/specs/**` | `/kiro-spec-status <feature>` clean, and `spec.json` approvals reflecting what actually happened |

A change spanning classes owes the validation of each.

## Fixture Discrimination

Any change that ships a test owes this, whatever its class. A green suite says
the assertions ran; it does not say they *could have failed*. Thirteen
insensitive assertions landed in a single day across three specs and three
independent sessions. Not one was a wrong assertion, not one had incorrect
production code behind it, and not one was caught by reading — every single one
was found by mutation, and only when a reviewer thought to invent the right
one. **Green is not the evidence. The mutation is the evidence.**

An insensitive assertion is strictly worse than a missing one. A missing test
is visible in coverage; an assertion that cannot fail tells every later session
the behavior is pinned while pinning nothing.

### The gate

A new assertion is done when you have:

1. **Named** the single-line mutation to *production* code that should make it
   fail — deleting a call, flipping a comparison, replacing a branch with
   `True`, returning the input unchanged.
2. **Run** it, and observed the assertion go red.
3. **Reverted** the mutation and confirmed green.

An assertion whose mutation you cannot name is not done. Group assertions that
one mutation kills; the unit of evidence is the mutation, not the `assert`.

**Steps 2 and 3 are only worth what the interpreter actually ran.** CPython
validates a `.pyc` against the source's **mtime and size**, and the mutations
this gate mandates routinely change neither — `= 2` to `= 3`, `< 1` to `< 0`,
dropping a `not`. Apply/observe/revert typically completes inside one filesystem
mtime second, at which point the cached bytecode still looks valid and the
interpreter keeps executing the mutated code. Reproduced here on a byte-identical
tree: `git diff` empty, the source reading `LOAD_PAYLOAD_VERSION = 2`, the
interpreter reporting `3`.

Both observations are corruptible, and the dangerous direction is the mutation
rather than the revert: if the mutation never takes effect the suite stays green
and you conclude a real assertion does not discriminate — a confident,
evidence-backed, wrong conclusion, which is the precise failure this gate exists
to prevent. It is intermittent by construction (it needs same-size *and*
same-second), so it reads as a flake.

You do not have to remember a cleanup step, because a step an agent must remember
is a step that gets skipped. The root `conftest.py` purges every `__pycache__`
under `src/` before the first import and sets `sys.dont_write_bytecode`, so a
stale entry cannot exist during a pytest run; `tests/test_bytecode_hygiene.py`
pins both halves. What this asks of you is only: **run mutations through `uv run
pytest`.** A bare `uv run python -c` bypasses the conftest and reads the stale
cache — that is how the hazard was found.

Three properties the evidence must have, each learned by watching it be absent:

- **Sole failure.** The mutation must red the assertion *you are pinning* and
  ideally nothing else. A mutation that reddens thirteen tests proves the suite
  is alive, not that this assertion discriminates. If the target survives while
  siblings die, the assertion is vacuous and the siblings were doing the work.
- **Reachability.** Verify the scenario the assertion names is actually reached.
  Most instances were not wrong assertions but unreachable ones: a decoy that
  was never present, a defence-in-depth guard shadowing the gate under test, a
  state the fixture never enters. Assert the precondition, not just the
  postcondition.
- **Falsity in the starting state.** Before asserting a post-condition, confirm
  it is FALSE beforehand. Asserting `state is UNSUPPORTED` after a re-render
  proves nothing when the *prior* state was also `UNSUPPORTED`.

### Named anti-patterns

Each observed, each verified by mutation, each having passed review by reading.

| Anti-pattern | Rule |
|---|---|
| **Pre-satisfied fixture** — input already in the asserted state (entries already sorted; `{"value": 190}` already an `int`) | The fixture must violate the property the code establishes. Deleting `sorted()` or `int()` must red. |
| **Confounded fixture** — two orderings co-vary, so two rules are indistinguishable (value and date both ascending: `max(key=date)` ≡ `max(key=value)`) | Vary one dimension against the other. The requirement names *one* rule; the fixture must defeat the others. |
| **Tied values** — an N-to-N mapping asserted against repeated values (`1/0/1/0/0`) | Pairwise-distinct values, or the pairwise swaps stay green. Four of ten did. |
| **Unreachable scenario** — the decoy is absent, or a second guard rejects the case first (both calculators support the activity; every `recompute` drove a state that never hits the passthrough) | Assert the scenario is live before asserting the outcome. A case a second rule also rejects pins the second rule. |
| **Post-condition true beforehand** — the asserted end state is also the start state | Assert it is false first, or assert the transition. |
| **Ever-present token** — `assert "Unsupported" in output` against a label printed on every run | Assert the count, the value, or the position — never mere presence of something always emitted. |
| **Self-referential compare** — printed output compared against a report captured from the same run | Assert the captured subject is non-trivial *before* comparing. An all-zero report passes against itself. |
| **Vacuous introspection** — `hasattr(Cls, "field")` on a dataclass field (an annotation is never a class attribute, so it is `False` either way); `dir(SomeProtocol)` omitting annotation-only members; `assert x is not None` | Use `__annotations__`, `dataclasses.fields()`, or the typing introspection that sees what you mean. Prove the guard rejects by adding the thing it forbids. |
| **Vacuous walk** — an AST or filesystem guard that passes having scanned zero files (`Path(__file__).parents[N]` is depth-sensitive and goes silent) | Every walking guard needs a positive control: `assert scanned, "the walk is looking at the wrong directory"`. |
| **Indistinguishable outcome** — a test whose observable is identical under both behaviors (an up-front abort and a lazy one both leave the bytes unchanged) | Find a different observable, or say plainly that this clause is unpinned. |
| **Stale bytecode** — a sibling of *vacuous walk*: evidence that appears to have been gathered but was not, because a same-size mutation reverted in the same second left a valid-looking `.pyc` and the interpreter never ran what you wrote | Observe mutations through `uv run pytest`, which the root `conftest.py` makes cache-proof. Never conclude "does not discriminate" from a bare `uv run python -c`. |

### Prose is not evidence

A comment or docstring claiming discrimination is itself untested, and a false
claim is worse than none — it tells the next editor the coverage exists. Four
such claims shipped in one group ("Mutation caught: … verified by hand" on
guards a reviewer then broke with the suite green; "tracked as follow-up work"
naming a queue item that did not exist).

Before submitting, run:

```
grep -rniE "verified|caught|proven|tracked|regardless|always|never|impossible|evidence|implicit|outright|immediate|would (have )?(fail|catch|red)|could not (produce|be satisfied)|cannot be satisfied by|nothing else (can|could)" <changed-test-files>
```

and re-run every surviving claim, or delete it. `-E` is load-bearing: under
plain BRE `grep` the unescaped `(`/`)`/`?` in this pattern match nothing and
the command exits 1, which reads as a clean pass on a file full of true
positives.

**The grep nets phrasings, not claims — a clean grep is not evidence that no
false claims remain.** It has already missed nine across five tasks and two
specs, six of them in a single run, none using any word above. All nine
share a shape no word list can enumerate: a **consequence claim** ("so a
later rename does not fail this suite", "a nested helper cannot hide
either") or a **mechanism-justification claim** ("this exclusion exists
because `|` is a union type", "the aliases prevent unused-import warnings").
An author reaches for this kind of ordinary declarative prose exactly when
explaining *why* the code is shaped as it is — which is precisely when they
are least likely to have re-tested the belief. Widening the vocabulary closes
the instance that prompted it and predicts nothing about the next phrasing.

The obligation the grep cannot discharge: **read every factual sentence in a
changed test file, matched or not, and for any sentence asserting a
consequence or justifying a mechanism, make it happen and observe** — rename
the thing, indent the arithmetic, call the function and print the field. Not
reasoning about the sentence; executing it. Treat the grep as a cheap first
pass, never as the check itself.

### The completeness half

A per-assertion gate is necessary and not sufficient. On a task listing more
than a handful of requirements, incremental review does not terminate: three
rounds found three, then two, then two more, each round correct and each
finding new ground. What ended it was an **exhaustive sweep** — enumerate every
requirement the task lists and classify each:

- **PINNED** — naming the test and the mutation it dies on
- **PRESERVED-ONLY** — naming the pre-existing regression test that covers it
- **UNPINNED** — stating so explicitly, with the mutation run that proves it

That bounded the remainder and closed it in one round. An unpinned clause
declared honestly is an acceptable outcome; an unpinned clause discovered by a
reviewer is a rejection.

### Converging vs oscillating

Remediation rounds on this class fail in two distinct ways, and they need
opposite responses:

- **Converging but incomplete** — each round finds new, real ground. Stop
  discovering incrementally and run the exhaustive sweep.
- **Oscillating** — each fix installs a new confound in place of the old one
  (moving a fixture off a digit collision destroyed the boundary coverage that
  fixture existed for). Escalate to a debug subagent. The lesson generalises:
  message-content assertions and boundary assertions need *different*
  fixtures — one distinctive value cannot serve both, because making a value
  distinctive pushes it away from the boundary.

## Enforcement

`.claude/hooks/change-guard.py`, wired to `PreToolUse` and `Stop` in
`.claude/settings.json`:

- **PreToolUse** denies `Edit`/`Write`/`NotebookEdit` to a versioned repo path
  whose tree is on `main`, and denies `git commit` into a tree on `main`. It
  judges the tree the write lands in, not the session's working directory —
  reading a leading `cd`/`pushd` and any `git -C` out of the command, so the
  lifecycle above works as written. A session rooted at `main` can drive edits
  and commits into its worktree, and one rooted in a worktree cannot reach
  back into `main`. It does not fire
  outside the repo, on gitignored files, on `.git/`, on `.kiro/queue/` items,
  or in any tree already on a branch.
- **Stop** blocks once if the session wrote tracked files that are still
  uncommitted, if it is sitting on a branch holding commits `main` doesn't
  have, if that branch holds commits its upstream lacks (or has commits and
  no upstream at all — never pushed), or if `main` holds commits
  `origin/main` lacks. `main` is judged against `origin/main` by name, from
  any tree, because it is everyone's; a tree with no remote configured is
  out of scope.

To declare a change trivial, create the session's marker — the block message
prints the exact command with the id filled in:

```bash
touch "${TMPDIR:-/tmp}/fitdocs-trivial-<session-id>"
```

It has to be its own tool call: `PreToolUse` judges a command before any of it
runs, so `touch … && git commit …` is still denied as a whole.

That is deliberate, separate, and visible in the transcript, which is the
point: trivial becomes a claim someone made, not a default the session drifted
into. It waives the worktree, never the commit.

The guard covers file tools and `git commit`. Writes made through other shell
commands are on the honor system, and a guard whose git commands fail lets the
write through. The push check judges the branch the session stopped in plus
`main`, so a worktree branch driven from a session rooted at `main` is seen
only once its commits reach `main` — the same blind spot the merge-back check
has always had. It is a ratchet against drift, not a security boundary.

## Not Allowed

- Editing steering, skills, or hooks on `main` because "it's only docs"
- Leaving a session's changes uncommitted for a later session to find
- Leaving a branch unmerged and calling the work done
- Committing without pushing — `commit && push` is one line; a commit that
  exists on one machine is not landed
- `git push --force`. `--force-with-lease`, on your own branch, after a
  rebase, is the only force; `main` is never force-pushed
- Merging without re-running validation after the rebase
- Declaring a change trivial after the guard blocked it, to get past the guard
- Starting work without reading the log, or landing it without saying so there
- `git add -A` / `git add .` — stage paths you named

---
_Document the contract, not the current branch list_

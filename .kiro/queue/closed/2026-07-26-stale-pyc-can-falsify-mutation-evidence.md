---
id: 2026-07-26-stale-pyc-can-falsify-mutation-evidence
title: A same-second, same-size mutation revert leaves a stale .pyc, so mutation evidence can be false in both directions
status: done
importance: high
importance_why: The fixture-discrimination gate that just became protocol rests entirely on "apply the mutation, observe red, revert, observe green" — and this makes both observations unreliable without a cache clear nobody currently performs.
effort: S
kind: bug
area: .kiro/steering/change-protocol.md, .claude/skills/kiro-impl, tooling
created: 2026-07-26
surfaced_by: /kiro-queue sweep — verifying the payload/doc-version item's mutation evidence
pinned_at: 43dd31b
resume_command: "do: add a bytecode-cache clear to the fixture-discrimination gate in .kiro/steering/change-protocol.md and the kiro-impl/kiro-review templates -- mutation and revert must each be followed by clearing __pycache__ (or running pytest with PYTHONDONTWRITEBYTECODE=1), because a same-second same-size revert leaves the interpreter running mutated code [queue: .kiro/queue/2026-07-26-stale-pyc-can-falsify-mutation-evidence.md]"
context:
  - .kiro/steering/change-protocol.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
  - pyproject.toml
blocked_by: []
---

## What

CPython's default bytecode invalidation compares the **mtime and size** of the
source file against the values recorded in the `.pyc` header. A mutation of the
kind the discrimination gate mandates — "flip a comparison", "change a
constant", "replace a branch with `True`" — very often changes **neither**:

- `LOAD_PAYLOAD_VERSION: Final[int] = 2` → `= 3` is the same size.
- `if x < 1:` → `if x < 0:` is the same size.
- `no_prompt=no_prompt` → `no_prompt=True` is not, but many are.

And the whole apply/observe/revert cycle typically completes inside **one
filesystem mtime second**. When size is unchanged and the revert lands in the
same second as the `.pyc` write, Python considers the cached bytecode valid and
**keeps executing the mutated code**.

Observed directly in this repo at `43dd31b`:

```
$ stat -f "pyc  mtime=%m size=%z" src/fitdocs/load/__pycache__/render.cpython-311.pyc
pyc  mtime=1785094844 size=23132
$ stat -f "src  mtime=%m size=%z" src/fitdocs/load/render.py
src  mtime=1785094844 size=18391          # same second

$ grep -c "LOAD_PAYLOAD_VERSION: Final\[int\] = 2" src/fitdocs/load/render.py
1                                          # source says 2
$ uv run python -c "from fitdocs.load.render import LOAD_PAYLOAD_VERSION as v; print(v)"
3                                          # interpreter says 3
$ uv run pytest -q
7 failed, 1852 passed                      # on a byte-identical, fully reverted tree

$ find . -name __pycache__ -type d -not -path "./.venv/*" -exec rm -rf {} +
$ uv run pytest -q
1859 passed
```

`git diff src/` was **empty** throughout. The tree was correct; the interpreter
was not.

## Why it matters

`.kiro/steering/change-protocol.md` § Fixture Discrimination became binding
protocol on 2026-07-26 (`17ff340`). Its entire evidence model is:

> 1. **Named** the single-line mutation… 2. **Run** it, and observed the
> assertion go red. 3. **Reverted** the mutation and confirmed green.

Both observations are corruptible by this, in both directions:

- **False green on revert.** The revert looks clean, `git diff` is empty, but
  the suite is still running mutated code. If the mutation happened to be
  benign for the tests that ran, an implementer reports "reverted, confirmed
  green" while the cache holds something else. Every "reverted byte-identically
  and confirmed green" claim in the repo is only as good as the cache state.
- **False negative on the mutation — the dangerous one.** If the `.pyc`
  predates the mutation and the mtime/size collide, the mutation *never takes
  effect* and the suite stays green. The implementer concludes the assertion
  does not discriminate. That leads directly to either "declared UNPINNED" for
  a clause that is in fact pinned, or worse, to rewriting a working test to
  chase a mutation that was never applied.

The second failure mode is precisely the one the gate exists to prevent, and it
would produce a *confident, evidence-backed, wrong* conclusion — which is
harder to catch than no evidence at all.

Note this also affects the reviewer half. `change-protocol.md` says "on a guard
task the reviewer's mutations are the deliverable; the implementer's are a
claim" — but a reviewer's mutations run through the same cache.

## Evidence

Beyond the reproduction above:

- `pyproject.toml` sets no `PYTHONDONTWRITEBYTECODE`, and there is no
  `conftest.py` cache hygiene, no `Makefile`, no CI workflow — so nothing in
  the repo clears bytecode between mutation rounds. Confirmed by inspection.
- CPython uses hash-based `.pyc` invalidation only when explicitly compiled
  with `--invalidation-mode checked-hash` (PEP 552); the default for runtime
  compilation is timestamp+size, so this is the shipped behaviour, not a local
  misconfiguration.
- This sweep ran roughly a dozen mutation cycles across six items before the
  collision surfaced, which is the point: it is intermittent by construction —
  it needs same-size AND same-second — so it will not reproduce reliably and is
  easy to dismiss as a flake.

## How to pick it up

1. Reproduce it deliberately before changing anything, so the fix is aimed at a
   confirmed mechanism: mutate a constant in place with `sed` (preserving
   length), run the suite, `cp` the original back within the same second, and
   check `stat` on the source and its `.pyc`.
2. Decide the mitigation. Cheapest and most robust is to make bytecode caching
   irrelevant during verification rather than to remember a cleanup step:
   - `PYTHONDONTWRITEBYTECODE=1` in the pytest invocation or `[tool.pytest.ini_options] env`, or
   - `-p no:cacheprovider` plus an explicit `find … -name __pycache__ -exec rm -rf` in the documented mutation recipe, or
   - `sys.dont_write_bytecode` in `conftest.py`.
   Prefer whichever cannot be forgotten by an agent following the template.
3. Write it into the places that mandate the cycle, not just one:
   `.kiro/steering/change-protocol.md` § Fixture Discrimination (the
   authoritative 3-step gate), and the implementer/reviewer prompt templates
   that restate it. All three currently say "revert and confirm green" with no
   cache step.
4. Consider adding the failure mode to the § Named anti-patterns table — it is
   a sibling of **vacuous walk**: evidence that appears to have been gathered
   but was not.

Done means: an agent following the documented mutation recipe cannot observe a
stale result, and the protocol says why the step exists so nobody removes it as
noise.

## Open questions

- Should previously recorded discrimination evidence be re-verified? Most of it
  is probably sound (mtimes usually differ), and re-running every mutation in
  the repo is expensive. A cheaper answer: only re-verify claims where the
  mutation was same-size AND the recorded result was "no change / stays green",
  since that is the direction that yields a wrong conclusion rather than a
  visible failure.


## Resolution

**Done 2026-07-26** — `e5d7319`, branch `chore/queue-top-ten`.

Reproduced deliberately before fixing: a same-size mutation of
`LOAD_PAYLOAD_VERSION` reverted within one filesystem second left `git diff`
empty, the source reading `2`, and the interpreter reporting `3`.

Fixed structurally rather than procedurally. The root `conftest.py` purges every
`__pycache__` under `src/` before the first import, sets
`sys.dont_write_bytecode`, and exports `PYTHONDONTWRITEBYTECODE` so the eight
test modules that spawn a `sys.executable` subprocess cannot re-create the
caches mid-run -- which they were doing, caught by the new guard rather than
predicted. `tests/test_bytecode_hygiene.py` pins both halves; all three conftest
lines are individually mutation-verified.

End-to-end: on a byte-identical tree the bare interpreter reported `3` and a
single `uv run pytest` run restored it to `2`.

`change-protocol.md` § Fixture Discrimination gained the mechanism, the "run
mutations through `uv run pytest`" instruction, and a `stale bytecode` row in
the named anti-patterns table; the implementer, reviewer and `kiro-review`
templates gained the same instruction where they restate the cycle.

The item's open question -- whether prior discrimination evidence should be
re-verified -- is NOT answered here and was not attempted.

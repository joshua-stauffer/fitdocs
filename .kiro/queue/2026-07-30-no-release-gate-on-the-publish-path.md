---
id: 2026-07-30-no-release-gate-on-the-publish-path
title: A distribution can be built and published without the test suite ever running, so the withdrawn-methodology content guard is not on the publish path
status: open
importance: high
importance_why: The only mechanism preventing two CSVs carrying the third party's copyright notice from reaching PyPI is a pytest test, and nothing forces that test to run before `uv build && uv publish`. A licensing guard the release path can skip is not a guard.
effort: M
kind: gap
area: distribution, tests/load/test_packaging.py, pyproject.toml
created: 2026-07-30
surfaced_by: adversarial review of chore/sdist-content-keyed-guard (queue-tier1 batch)
pinned_at: c3d2201
resume_command: "/kiro-impl distribution [queue: .kiro/queue/2026-07-30-no-release-gate-on-the-publish-path.md] Implement the licensing gate that inspects built artifacts and refuses to publish encumbered material, which distribution/design.md already specifies"
context:
  - .kiro/specs/distribution/design.md
  - tests/load/test_packaging.py
  - pyproject.toml
  - .claude/hooks/change-guard.py
blocked_by: []
---

## What

`tests/load/test_packaging.py` holds the guard that stops the withdrawn
methodology's tables from shipping in a distribution. As of
`chore/sdist-content-keyed-guard` it is content-keyed and genuinely
discriminating — a rename no longer defeats it.

It is still only a **pytest test**. There is no continuous integration in this
repository and no release gate, so nothing causes it to run before a
distribution is built and uploaded. A maintainer who runs `uv build && uv
publish` on a checkout where the `pyproject.toml` exclude has silently stopped
matching ships the encumbered files, and no mechanism in the repository
objects.

`.kiro/specs/distribution/design.md` already specifies the missing piece:
"a licensing gate that inspects built artifacts and refuses to publish
encumbered material" (`design.md:16`, elaborated at `:279-295`). It is
unimplemented.

## Why it matters

This is a licensing surface, not defence-in-depth. The two CSVs under
the extracted tables carried the third party's copyright notice, and the
methodology they belong to was withdrawn from this project for exactly that
reason. **Superseded 2026-08-01**: `encumbered-content-purge` task 3.1 deleted
the extracted tables and the writeup from the working tree entirely, per
Requirement 4's reversal of their retention. Whether the release-gate concern
still has a subject worth guarding — a future re-addition, rather than this
specific artifact — is a decision for whoever next picks this up.

The failure is silent and the actor is innocent: the person publishing a
release is not the person who renamed a directory, and neither of them gets a
warning. Every other mechanism protecting this surface — the `pyproject.toml`
exclude, the content scan, the withdrawal guards — is downstream of a human
choosing to run the suite.

Note also that `.claude/hooks/change-guard.py` binds *agent sessions*, not a
human at a shell. The one enforcement mechanism this repo does have does not
reach the publish path either.

## Evidence

Gathered at `9e508e1` by the reviewer on `chore/sdist-content-keyed-guard`, and
independently re-confirmed by the parent session:

```
$ ls -a | grep -i 'github\|gitlab\|circleci'
NO CI CONFIG DIRS
$ find . -maxdepth 3 -name '*.yml' -o -maxdepth 3 -name '*.yaml'
(no output)
```

No workflow files exist anywhere in the tree, so no automated run of
`uv run pytest` gates anything.

The reviewer separately demonstrated that the guard, when it *does* run, is
load-bearing: deleting the writeup line from `pyproject.toml`'s exclude list
produces a sole failure, and renaming the extracted tables' directory
reds the content scan naming both CSVs. That is the protection which the
publish path can currently bypass entirely.

The specified-but-unbuilt gate: `.kiro/specs/distribution/design.md:16`,
`:166`, `:279-295`.

## How to pick it up

1. Read `.kiro/specs/distribution/design.md:279-295` — the gate is already
   designed, so this is an implementation task rather than a design one. Check
   whether `distribution`'s `tasks.md` (currently 0/33) already carries a task
   for it before adding one.
2. Decide where the gate binds. A pytest test is not enough on its own; the
   candidates are a `hatch`/`hatchling` build hook that fails the build itself,
   a `Makefile`/`just` release target that runs the suite first, or CI on tag.
   The build hook is the strongest, because it cannot be bypassed by forgetting
   a step.
3. Reuse, do not reimplement, the content-keyed matcher now in
   `tests/load/test_packaging.py`. If the gate and the test drift apart, the
   repo has two answers to one question — which is the defect class this queue
   is full of.
4. Done looks like: `uv build` itself fails on a tree where the encumbered
   tables would be packaged, demonstrated by the `git mv` reproduction, with
   the test suite still passing in the normal tree state.

## Open questions

- Should the gate refuse the **build** or only the **publish**? Refusing the
  build is stricter and catches the error earlier, but makes local
  experimentation with packaging harder.
- Does this want to wait for the `distribution` spec to be worked properly
  (0/33 tasks, `phase: tasks-generated`), or land standalone first given it
  protects a licensing surface today?

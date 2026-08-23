---
id: 2026-07-31-agent-log-symlink-ships-in-sdist
title: The root `agent-log` symlink ships in the sdist, and its target now carries the identity the purge erases
status: open
importance: medium
importance_why: Not a leak today (dangling symlink, no content archived), but it is invisible to the Req 10.4 artifact scan by construction, so nothing would catch it turning into one.
effort: S
kind: gap
area: distribution, encumbered-content-purge, pyproject.toml, tests/load/test_packaging.py
created: 2026-07-31
surfaced_by: /kiro-spec-design encumbered-content-purge
pinned_at: c3d2201
resume_command: "/kiro-spec-requirements distribution [queue: .kiro/queue/2026-07-31-agent-log-symlink-ships-in-sdist.md] Decide whether the root agent-log symlink is excluded from the sdist or asserted absent"
context:
  - .kiro/specs/distribution/design.md
  - .kiro/specs/encumbered-content-purge/design.md
  - tests/load/test_packaging.py
  - pyproject.toml
blocked_by:
  - encumbered-content-purge
---

## What

The repository root holds an untracked, un-ignored symlink `agent-log`
pointing at `.git/agent-log`, the shared multi-session log. Hatchling's
default sdist contents include it, so it is a member of the built source
distribution. It is archived as a **symlink**, not as a file, so its target's
bytes do not ship and an extracted sdist gets a dangling link.

Two facts make this worth a decision rather than a shrug. First, the sdist
content guard skips it by construction — it filters on `member.isfile()`,
which is `False` for a symlink — so the Req 10.4 "no removed material in a
built artifact" scan is **blind to this member**. Second, as of
`encumbered-content-purge`, the symlink's target carries identifying tokens
that the whole purge exists to erase. The combination is a member that no
guard inspects, pointing at content the repository is committed to not
publishing.

`encumbered-content-purge` records this as a revalidation trigger and assigns
it to `distribution`; it is out of that spec's boundary and deliberately not
fixed there. Nothing currently owns the decision.

## Why it matters

Today this is not a leak: the content is not archived. The exposure is that
nothing would notice if that changed. Any packaging change that resolves
symlinks — a hatchling default change, a switch of build backend, an explicit
`force-include`, or a release built from a tarball produced by some other tool
— converts a harmless dangling link into a shipped copy of the shared agent
log, which carries a third party's identity across sixteen lines. The guard
that exists precisely to catch material reaching a built artifact cannot see
this member, so the failure would be silent and would land in a published
artifact on PyPI.

`encumbered-content-purge` deletes the repository's other copies of that
identity from tree and history at considerable cost, including a one-shot
whole-history rewrite. Leaving an unguarded path by which it can re-enter a
shipped artifact undercuts that work.

## Evidence

All gathered at `ff52586`.

The symlink exists and is untracked:

```
$ ls -l agent-log
lrwxr-xr-x  1 josh  staff  14 Jul 27 23:20 agent-log -> .git/agent-log
$ git status --short
?? agent-log
```

It is an sdist member, archived as a symlink (`uv build --sdist`, then
`tarfile` inspection of `fitdocs-0.1.0.tar.gz`):

```
MEMBER: fitdocs-0.1.0/agent-log  issym=True  isfile=False
        linkname='.git/agent-log'  size=0
total members: 546
```

The content guard skips non-regular members —
`tests/load/test_packaging.py:553-554`:

```python
for member in sdist.getmembers():
    if not member.isfile() or member.name in _SDIST_WITHDRAWN_ALLOWLIST:
```

The module's own docstring at `:456` already states that symlink members are
excluded by `isfile()`. That is correct behaviour for a content scan and is
exactly why this member needs a different check.

The target carries the identity:

```
$ grep -icE '<identifying tokens>' "$(git rev-parse --git-common-dir)/agent-log"
16
```

It carries no encumbered table values (checked against two known fingerprint
values: 0 hits), so the exposure is the identity only.

## How to pick it up

1. Read `.kiro/specs/encumbered-content-purge/design.md` › *Revalidation
   Triggers* and › `CloneAdoption` › the Req 11.13 position. That is where the
   hazard is stated and why the purge declined to fix it. Then read
   `.kiro/specs/distribution/design.md` for how that spec currently reasons
   about sdist contents.
2. Decide between three options, which are genuinely different and not
   interchangeable: (a) exclude the symlink from the sdist in `pyproject.toml`
   — cheapest, but re-adds a `[tool.hatch.build.targets.sdist]` section that
   `encumbered-content-purge` deletes, so the two specs must agree; (b) assert
   in the packaging guard that no sdist member is a symlink, which is the
   option that would have *caught* this and generalises beyond `agent-log`;
   (c) move the shared log so no root symlink is needed at all, which touches
   `.kiro/steering/concurrency.md` and every session's first command.
3. Whichever is chosen, the guard change is the part that must not be skipped:
   a fix in `pyproject.toml` alone leaves the artifact scan just as blind as
   it is now.

**Done** means: a built sdist either has no symlink members or has them
explicitly allowlisted by name, a test fails if a new unexplained symlink
member appears, and the mutation that proves that test discriminates is
recorded per `change-protocol.md` › Fixture Discrimination.

## Open questions

- Should the guard forbid symlink members outright, or allowlist them by name
  the way `_SDIST_WITHDRAWN_ALLOWLIST` handles content exemptions? Outright refusal
  is stronger but may collide with something `distribution` wants to ship later.
- This item is `blocked_by: encumbered-content-purge` because option (a)
  reintroduces a packaging section that spec removes, and because the sdist
  defaults it establishes are the baseline any fix must be written against.
  If the chosen option is (b), the block may not be real — check before
  deferring on it.

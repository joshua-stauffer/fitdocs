---
id: 2026-08-22-the-new-remote-renames-the-repository-and-nine-tracked-urls-still-name-the-old-one
title: The supplied remote renames the repository, and nine tracked references — two in shipped source — still name the old one
status: done
importance: high
importance_why: Req 10.3 makes the replacement root's tree IDENTICAL to the certified tip and there is no later redaction step, so whatever task 8.1 certifies is what ships — including URLs that will 404 after the rename.
effort: M
kind: gap
area: encumbered-content-purge, src/fitdocs
created: 2026-08-22
surfaced_by: /kiro-impl encumbered-content-purge (maintainer supplied the remote URL; parent measured the delta)
pinned_at: aa884cc
resume_command: "do: decide whether the fitdocs_oss -> fitdocs rename lands before task 8.1 certifies the tip, and if so update the nine tracked references and their pins"
context:
  - src/fitdocs/tiles.py
  - src/fitdocs/declaration.py
  - README.md
  - .kiro/specs/encumbered-content-purge/brief.md
blocked_by: []
---

## What

The maintainer supplied the remote for Major 8:

    git@github.com:joshua-stauffer/fitdocs.git

Measured 2026-08-22: that repository **exists and is empty** (`git ls-remote`
exits 0 with zero refs). The current `origin`,
`git@github.com:joshua-stauffer/fitdocs_oss.git`, **also still exists**, with
`refs/heads/main` at `73344d6`.

So this is not a delete-and-recreate under the same name, as Decision 6
anticipated. It is a **rename**: `fitdocs_oss` → `fitdocs`. The URL itself is
not a forbidden value (checked with the matcher, positive control first), so
writing it into tracked files is safe.

**Nine tracked references still name the old repository**, and two of them are
in shipped source:

| Site | What it is |
|---|---|
| `src/fitdocs/tiles.py` | the OSM `User-Agent` string the tool sends on every tile fetch |
| `src/fitdocs/declaration.py` | the published ownership-contract URL written into generated documents |
| `tests/test_tiles.py` | asserts `USER_AGENT.endswith(...fitdocs_oss)` — pins the old name |
| `tests/declaration_golden/workouts.AGENTS.md` | golden output carrying the contract URL |
| `tests/declaration_golden/fit-archive.AGENTS.md` | golden output carrying the contract URL |
| `README.md` ×3 | the UA example and two ownership-contract links |
| `.kiro/specs/route-maps/design.md` | the UA the politeness requirement specifies |

`.kiro/specs/encumbered-content-purge/brief.md` also records the old URL as
`origin`, and `design.md` twice names the archive directory
`fitdocs_oss-git-archive-<UTC date>` — that one is a local archive name, not a
URL, and is harmless either way.

## Why it matters, and why it gates task 8.1

Requirement 10.3 makes the replacement root's tree **identical** to the
certified tip, and Amendment 1 removed every later redaction step by design —
the replacement carries whatever the certified tree contains. Task 8.1 says so
in its own words: *"there is no later redaction step to catch what
certification missed."*

So if the tip is certified while those nine references name `fitdocs_oss`, the
fresh root — the first and only commit of the published repository — ships:

- a `User-Agent` advertising a URL that 404s, sent to OSM's servers on every
  tile fetch, against a politeness requirement whose whole point is being
  identifiable and contactable; and
- an ownership-contract link that 404s, written into **every generated
  document** the tool produces.

That is a worse outcome than the encumbered content this purge exists to
remove, because it ships broken outward-facing references rather than merely
retaining private ones.

## The decision

Three coherent options, and the first is probably right.

**(a) Land the rename before 8.1.** Update the nine references, move the
`tests/test_tiles.py` pin with them (it will red — that is the guard working),
regenerate the two goldens, and re-certify. Ordinary reversible branch work,
but it must land on `main` and the worktree must be gone again before Major 8,
because the gate halts while any extra branch or worktree exists.

**(b) Keep the old repository alive as a redirect.** GitHub serves redirects
for renamed repositories, but this is a *new* repository next to an existing
one, not a rename performed through GitHub — so no redirect exists, and the old
one is scheduled for deletion. This option only works if the maintainer renames
`fitdocs_oss` → `fitdocs` **through GitHub** instead of deleting it, which also
conflicts with Decision 6's delete-and-recreate.

**(c) Ship as-is and fix afterwards.** Cheapest now, and it means the published
0.1.0's first commit contains two dead outward-facing URLs, with the fix landing
as a second commit on a history that was just deliberately reduced to one.

## How to pick it up

Confirm with the maintainer which option, since (a) is real work that must
land, and be gone, before Major 8 starts. If (a): treat the
`tests/test_tiles.py` assertion as a pin that moves WITH the change, and state
that the new shape is strictly no weaker — this repo's standing lesson is that
updating a pin is where guards die. The two goldens must be regenerated, not
hand-edited.

Whichever is chosen, `brief.md`'s recorded `origin` should be corrected in the
same change so the spec's own record of the remote is not stale, and task 8.4's
delete-half should be re-read: the maintainer is doing the deletion out of
band, and what is left to automate is recreate-push-and-measure against the new
URL.

## Resolution — 2026-08-22, `chore/repo-rename`

**Option (a), URLs only**, ruled by the maintainer. All nine references now
name `github.com/joshua-stauffer/fitdocs`; the local working directory, the
package name and the local archive-name convention keep `fitdocs_oss`, which is
why the `/Users/josh/code/fitdocs_oss/...` filesystem paths recorded in other
queue items were deliberately left alone.

Option (b) was already dead on measurement rather than on preference: the new
repository exists *alongside* the old one, so no GitHub rename occurred and no
redirect is being served.

Two findings worth keeping:

- **`README.md` holds a fourth `github.com/joshua-stauffer/` URL that must NOT
  move**: line 23's `.../fitdocs.ai`, a different repository. Because
  `.../fitdocs` is a strict substring of `.../fitdocs.ai`, any future
  count-based or substring-based check over these URLs will trip on it. The
  rename was driven off the `fitdocs_oss` anchor, which cannot match `.ai`, so
  line 23 is untouched — the exact-anchor-count assertion is what surfaced it.
- **`docs/ownership-contract.md` is tracked**, so the rewritten contract URL
  resolves once the replacement root is pushed. `pyproject.toml` still has no
  `[project.urls]`, so `declaration.py`'s comment about deriving the URL by
  hand remains accurate and there is no second site to keep in sync.

The `tests/test_tiles.py` pin moved with the change and is strictly no weaker:
same exact-suffix shape, and it fails against the old name. Both halves were
mutation-proved through `uv run pytest` (reverted from a snapshot copy, never
from git): reverting the UA to `fitdocs_oss` reds
`test_default_fetch_sends_descriptive_user_agent_and_timeout` alone, 1 failed /
37 passed; reverting `CONTRACT_DOCUMENTATION_URL` reds both golden
parametrisations. The goldens were regenerated via
`uv run python -m tests.test_declaration_goldens`, not hand-edited, and were
confirmed red first.

Validation on the branch: 4176 passed / 1 skipped — the baseline exactly, with
the single named complementary skip — plus `ruff check`, `ruff format --check`
and bare `uv run mypy` clean.

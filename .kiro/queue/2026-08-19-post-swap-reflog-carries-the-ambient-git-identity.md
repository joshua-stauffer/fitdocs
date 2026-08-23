---
id: 2026-08-19-post-swap-reflog-carries-the-ambient-git-identity
title: The fresh .git's reflog records the operator's ambient git identity and the source path, and nothing clears it
status: open
importance: low
importance_why: Ruled 2026-08-22 — the observed identity is not a forbidden value, so this is optional hygiene, not a Major 8 blocker. Kept open only for the discretionary clone-identity choice.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/replace.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7 remediation review; reproduced independently by the parent)
pinned_at: c3d2201
resume_command: "do: decide whether the post-swap .git/logs identity lines are in scope for the purge, and if so how they are cleared, before task 8.2 swaps .git"
context:
  - scripts/purge/replace.py
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/queue/2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-swap.md
blocked_by: []
---

## What

Every reflog line carries the identity of whoever performed the ref update —
the on-disk format is `<old> <new> <name> <email> <timestamp> <tz>\t<message>`.
The fresh `.git` that the replacement swaps in is produced by `git clone`
followed by `git branch -m`, so its `logs/HEAD` and `logs/refs/heads/main`
record the **ambient global git identity of the machine running the purge**,
plus the **filesystem path of the source repository** in the clone message.

This is not governed by `run_replace`'s `non_personal_address` /
`non_personal_name` arguments. Those reach `adopt.assert_commit_identity` and
the metadata verification row; they do not affect what `git clone` writes into
the reflog.

Nothing clears it: the sibling queue item
`2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-swap.md`
establishes that no reflog clearing happens anywhere in the driver, and the
maintainer's approved fix direction for the verification row deliberately does
NOT add any.

## Why it matters

The replaced repository is the one the maintainer keeps and works in. The
spec's scope is stated as the working tree and every commit "local and remote",
and Req 11's identity concerns are not limited to committed objects.

Two mitigating facts, stated so this is not over-escalated:

- **Reflogs are never pushed.** `git push` transfers objects and refs, not
  `logs/`. So the *published* repository is unaffected, and Req 8's remote
  measurements are not at risk.
- The address observed is a GitHub `users.noreply.github.com` address, which
  may or may not be one of the two personal addresses this purge targets. That
  is exactly the check that has not been run.

What makes it worth a ruling rather than a shrug: this is a *new* identity
string written *into* the repository **by the purge itself**, during the
irreversible step, after every verification row has been designed. It would be
a poor outcome for the operation that removes identities to introduce one.

## Evidence

Reproduced independently by the parent session at `7da5ce3`, real git 2.54.0,
against a throwaway repository under the session scratchpad (never the real
repository). The source repo's LOCAL config was deliberately set to a
non-personal identity to prove the ambient one wins:

    git -C <src> config user.email  ->  noreply@fitdocs.example
    git -C <src> config user.name   ->  fitdocs maintainer

After `git clone --no-local --single-branch --branch <tmp>` and
`git branch -m`, the clone's `.git/logs/HEAD` held three lines, each carrying
the machine's global identity (name and email) rather than the source repo's
local one, and the first line embedded the absolute source path in its
`clone: from <path>` message. The clone had no local `user.email` of its own.

The reviewer independently observed the same thing by instrumenting the
rehearsal against the real driver path.

## RULING, 2026-08-22: the observed identity is NOT a forbidden value

The question that decided everything else has been answered by measurement,
with a positive control run first so a dead matcher could not fake a clean
result:

    source loaded, entries: 9
    positive control (a known value matches): True
    reflog ADDRESS is a forbidden value: False
    reflog NAME   is a forbidden value: False

The address the reflog carries is the maintainer's GitHub `users.noreply`
address -- the **non-personal replacement** address the 2026-07-26 rewrite
substituted *in*, not one of the two personal addresses this purge removes.
The maintainer's own name is likewise not a forbidden value: Requirement 11
targets a **third party's** identity, not the maintainer's.

**Consequence: this is not a Major 8 blocker.** The post-swap reflog contains
no forbidden string, so it violates no criterion, and 8.2 may proceed without
clearing it. What remains is optional hygiene, below, not an obligation.

**A correction this ruling forced.** The sentence previously here said the
loader's repo-boundary check "misfires outside pytest". That was false, and it
was written from a misuse: `tests._forbidden_strings.load()` takes
**`repo_root`** as its argument, and it had been passed the *source file path*,
so it correctly reported the source as lying inside the "repository working
tree" it had been handed. Called with the real repo root it works outside
pytest exactly as inside. Use pytest for MUTATION runs (the bytecode-staleness
hazard) -- not for reading this source.

## How to pick it up

Optional hygiene only, at the maintainer's discretion. If a ruling to clear it
is taken anyway, the cheap and non-destructive options are:

(a) run the clone and rename with the non-personal identity in the environment
    (`GIT_COMMITTER_NAME` / `GIT_COMMITTER_EMAIL`, or a `-c user.name=... -c
    user.email=...` on the clone and rename commands), so the reflog is written
    with the intended identity in the first place — this is the option that
    needs no deletion and no new destructive step; or

(b) delete `.git/logs` in the scratch clone before the swap, which also
    disposes of the embedded source path, and re-verify.

Prefer (a) if the reflog is to be kept at all, because it fixes the cause
rather than the artifact. Whichever is chosen, the decision belongs in the
provenance record's stated positions alongside the other accepted residues.

**Sequencing: this must be settled before 8.2 swaps `.git`.** Afterwards the
lines are in the repository the maintainer keeps, and the only remedies left
are destructive ones applied to a just-verified repository.

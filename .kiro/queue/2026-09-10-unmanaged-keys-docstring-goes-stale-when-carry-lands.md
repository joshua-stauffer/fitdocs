---
id: 2026-09-10-unmanaged-keys-docstring-goes-stale-when-carry-lands
title: unmanaged_keys' docstring describes the user-key carry in the future tense and nobody owns flipping it when 2.x lands
status: open
importance: medium
importance_why: The sentence documents a live data-loss window; it is true today and becomes false the moment the carry is wired in, and no task's boundary currently assigns the edit.
effort: S
kind: gap
area: effort-tags, src/fitdocs/contract.py, .kiro/specs/effort-tags/tasks.md
created: 2026-09-10
surfaced_by: /kiro-impl effort-tags tasks 1.1-1.3 (three adversarial reviews)
pinned_at: 25366bd
resume_command: "do: assign the unmanaged_keys docstring's future-tense carry sentence to task 2.1 or 2.2 and add it to that task's detail bullets, so it is flipped in the same change that wires the carry in"
context:
  - src/fitdocs/contract.py
  - .kiro/specs/effort-tags/tasks.md
  - .kiro/specs/effort-tags/design.md
blocked_by: []
---

## What

`unmanaged_keys`' docstring in `src/fitdocs/contract.py` currently reads:

> A user-owned key -- the effort tag's keys -- is never reported here
> (Req 1.4, 4.7): only a key in neither class is unmanaged. The verbatim
> carry that makes that exemption safe arrives with task 1.3; until it
> lands, a user-owned key is dropped by a rewrite without a warning.

That sentence is **true right now** and was written deliberately, after three
review rounds rejected two earlier formulations for claiming the carry already
existed. It documents a real interim window: task 1.1 exempted user-owned keys
from the unmanaged-key warning, so a hand-added `effort:` key is no longer
reported — but nothing preserves it either until the carry is wired into the
rewrite path.

The problem is ownership of the *next* edit. Task 1.3 landed
`user_owned_lines`, so "arrives with task 1.3" is now imprecise — the function
exists; what does not exist is any caller. The sentence becomes outright false
when task 2.1/2.2 wires the carry into `build_frontmatter` and `sync`/`regen`.
**No task's detail bullets currently mention this docstring**, and task 1.3's
review boundary explicitly forbade touching it (correctly — 1.3 could not make
the sentence true).

The `## Implementation Notes` in `tasks.md` instruct tasks 1.2/1.3 to update it
"when those mechanisms land", but two consecutive reviews accepted it untouched
because neither task could honestly flip it.

## Why it matters

This is the one sentence in the codebase that tells a reader the silent
data-loss window exists. If it goes stale in the false direction, it tells
every future session that user keys are preserved when they are not — and it
sits in a leaf module that four specs read.

The failure mode is not hypothetical: three of this spec's review rounds were
spent on exactly this docstring making claims about behavior that had not
landed.

## Evidence

At `25366bd`; the docstring is on branch `impl/effort-tags` at commit `2a52bf2`
(tasks 1.1-1.3 complete, `user_owned_lines` published, no caller).

- `grep -rn "user_owned_lines" src/` on that branch returns the definition and
  the `__all__` entry only — no call site.
- `.kiro/specs/effort-tags/tasks.md` `## Implementation Notes` names tasks
  1.2/1.3 as the updaters; both reviews accepted it unchanged, on the grounds
  that neither task makes the sentence true.
- Tasks 2.1 and 2.2's detail bullets (`tasks.md`, the "Core: preservation
  through the rewrite path" section) do not mention `unmanaged_keys` or its
  docstring.

## How to pick it up

1. Read the docstring in `src/fitdocs/contract.py` (`unmanaged_keys`) and tasks
   2.1 and 2.2 in `.kiro/specs/effort-tags/tasks.md`.
2. Decide which of the two actually closes the window — 2.1 lands the carried
   lines in the builder, 2.2 carries them through every rewrite in sync and
   regen. The window closes when a rewrite preserves the key, so 2.2 is the
   likelier owner, but read both.
3. Add an explicit bullet to that task: flip the sentence to the present tense
   in the same change, and pin it — the ownership-contract conformance test or
   the sync tests are the natural place, so the docstring cannot drift back.
4. Done means: no task can land the carry while leaving a docstring that says
   the carry has not landed, and the reverse claim is pinned by a test rather
   than by review attention.

## Open questions

Whether the sentence should name a task at all. Task-numbered prose in a
production module is what made the earlier formulations wrong twice; a
description of the *behavior* ("a user-owned key is preserved across a
rewrite") with no task reference would not need this queue item to exist.
Worth deciding as a general convention for this repo rather than for this
sentence alone.

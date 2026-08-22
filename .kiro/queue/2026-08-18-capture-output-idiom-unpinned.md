---
id: 2026-08-18-capture-output-idiom-unpinned
title: _root_commit_ids' capture idiom is unpinned, though its failure direction is safe
status: open
importance: low
importance_why: A reviewer could not construct a repository where the two idioms diverge, and the only failure direction is loud; recorded as cheap hardening, not a hole.
effort: S
kind: gap
area: encumbered-content-purge, tests/test_forbidden_strings_source.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 4)
pinned_at: dac1a7a
resume_command: "do: pin the capture idiom in _root_commit_ids (tests/test_forbidden_strings_source.py) so swapping capture_output=True for stdout=PIPE, stderr=STDOUT reds, or record it as a declared-unpinned row"
context:
  - tests/test_forbidden_strings_source.py
blocked_by: []
---

## What

Replacing `capture_output=True` with `stdout=PIPE, stderr=STDOUT` in
`_root_commit_ids` survives the whole module. Merging stderr into stdout would
let diagnostic text be parsed as commit ids.

## Why it matters

Low, and the reason is worth recording rather than rediscovering. The
reviewer that found it tried to build a divergence and could not: across five
broken-repository shapes (dangling ref, garbage ref content, ref-to-blob,
branch/tag name collision, dangling symref, bogus replace ref),
`git rev-list --all --max-parents=0` either exits 0 with empty stderr or exits
128 -- and the existing `returncode != 0` guard discards the latter.

The only failure direction is also safe: roots can only be over-counted, which
makes a post-replacement repository read pre-replacement and hard-fail at task
8.3, never the reverse.

## Evidence

Reported by the task 7.2 reviewer as its one surviving mutation out of nine
own-designed probes, explicitly classified non-substantive and routed to
follow-ups rather than treated as a rejection ground.

Confirmed at `dac1a7a`: `capture_output=True` appears at
`tests/test_forbidden_strings_source.py:221`, `:262` and `:277`.

Not independently re-derived by the controller.

## How to pick it up

Either add a monkeypatched-`subprocess.run` test asserting the kwargs the
helper passes -- capturing the unpatched result and asserting the double is in
effect, per the double-assertion rule -- or add a declared-unpinned row stating
the reviewer's reachability argument. Done either way; the point is that the
next reviewer finds a decision rather than re-derives the five-shape search.

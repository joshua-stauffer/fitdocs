---
id: 2026-08-18-two-root-fixture-ordering-is-unstable
title: A two-root fixture depends on git's tie-break between same-timestamp roots
status: open
importance: low
importance_why: Intermittent by construction and reads as a flake; the test it affects is a sibling that still passes, but the docstring states the ordering as settled.
effort: S
kind: bug
area: encumbered-content-purge, tests/test_forbidden_strings_source.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 3)
pinned_at: c3d2201
resume_command: "do: make the two-root fixtures in tests/test_forbidden_strings_source.py order-independent, or give their roots distinct commit timestamps, and delete the docstring sentence stating the ordering as measured"
context:
  - tests/test_forbidden_strings_source.py
blocked_by: []
---

## What

Two fixtures build a repository with two parentless roots sharing a commit
timestamp. Git's tie-break between them is not stable, and a docstring states
the resulting order as a settled measurement.

## Why it matters

Intermittency is the expensive kind of defect here: it reads as a flake, and
this spec has a recorded instance of a same-second hazard being misdiagnosed
that way. The affected assertion is a sibling that still passes for the right
reason, so the live risk is low -- but the docstring tells a later reader the
ordering is determined when it is not.

## Evidence

Reported by the task 7.2 reviewer, which observed it directly: across four
runs of the `len(roots) < 1` mutant,
`test_two_root_commits_read_pre_replacement_even_when_one_names_the_record`
redded once and passed three times.

The reviewer's judgement, which I have not independently re-run: the
docstring's *conclusion* (that the sibling is ordering-dependent and the newer
test is not) is thereby strengthened rather than undermined; only the
"measured against this git installation" framing overstates determinism.

## How to pick it up

Open the two-root fixtures in `tests/test_forbidden_strings_source.py`. Give
the two roots distinct committer timestamps (`GIT_COMMITTER_DATE`), or assert
over the root set rather than a positional element. Delete the sentence
claiming the ordering was measured -- per this spec's standing rule, delete a
claim rather than correct it. Done when repeated runs of the same mutant give
the same verdict every time.

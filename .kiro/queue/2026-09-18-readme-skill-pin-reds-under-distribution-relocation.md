---
id: 2026-09-18-readme-skill-pin-reds-under-distribution-relocation
title: The README Agent-skills pin is README-scoped with a `## Plugins` adjacency clause; distribution's README relocation (Req 10.7) will red it
status: open
importance: medium
importance_why: Bites the next spec to touch README structure; the design claims the opposite ('relocation keeps it green').
effort: S
kind: inconsistency
area: distribution, build-training-block, tests/test_docs_guarantees.py, README.md
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: when distribution's docs tasks relocate README sections, move test_agent_skills_readme_section_documents_install_verify_and_update's section lookup and adjacency pin with them (or scope the pin to wherever the section lands); update build-training-block design.md:946's relocation claim"
context:
  - tests/test_docs_guarantees.py
  - README.md
  - .kiro/specs/build-training-block/design.md
  - .kiro/specs/distribution/requirements.md
  - .kiro/specs/distribution/tasks.md
blocked_by: []
---

## What
`.kiro/specs/build-training-block/design.md:946` says the docs pin searches
the corpus "so distribution's later relocation into `docs/wiki-integration.md`
keeps it green". As shipped, `tests/test_docs_guarantees.py:975-999` scopes
every positive clause to README's `## Agent skills` section and pins that the
first heading after `## Plugins` is `## Agent skills`. Moving the section out
of README, or inserting a section between the two, reds the test.

## Why it matters
Distribution Req 10.7 explicitly allows relocating README content into
`docs/`. Its implementer will hit a red test whose design says it cannot go
red, and may weaken it the wrong way.

## Evidence
- `tests/test_docs_guarantees.py:984` (README-only regex), the adjacency
  block below it; 3.2 review round 3 mutations: section moved above
  `## Plugins`, moved before `## Training blocks`, moved to EOF, and a
  `## X` spliced between -- each reds.
- Why it was scoped: a corpus-wide `copy` was pre-satisfied by `## Inbox`
  ("an archived copy") -- Implementation Notes 3.2.

## How to pick it up
Read the test and the design line; decide whether the pin follows the section
(preferred) or the section stays in README. Record the decision in the
build-training-block design amendment (sibling queue item) and in
distribution's tasks for its docs major.

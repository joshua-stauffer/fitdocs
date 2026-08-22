---
id: 2026-07-26-pycache-masks-length-preserving-mutations
title: A stale __pycache__ silently discards byte-length-preserving mutations, producing false PINNED results
status: done
importance: high
importance_why: Invalidates fixture-discrimination evidence repo-wide — the gate the whole change protocol now rests on — and one instance was a real survivor on an acceptance clause a task names verbatim.
effort: S
kind: gap
area: .kiro/steering/change-protocol.md, .claude/skills/kiro-impl/templates/
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, round-4 review)
pinned_at: 84e5e56
resume_command: "do: mandate a __pycache__ clear in change-protocol.md § Fixture Discrimination and in the kiro-impl implementer/reviewer templates, so no mutation result is reported from a possibly-stale cache"
context:
  - .kiro/steering/change-protocol.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
blocked_by: []
---

## What
CPython validates a cached `.pyc` against the source file's mtime **and size**
only. A mutation that preserves byte length — `and` → `or `, `x` → `y`, a
constant swapped for another of equal width — applied within the same
mtime granularity can therefore leave the cached bytecode in use. The suite
then executes the **original** code while the mutant is on disk, and the
mutation reports as "killed by nothing": a **false PINNED**.

This defeats the fixture-discrimination gate precisely where it is most
load-bearing, because the gate's whole premise is that the mutation, not the
green suite, is the evidence.

## Why it matters
Every `PINNED` claim in this repo produced without clearing the cache is
unverified — including claims already recorded as evidence in `tasks.md`
Implementation Notes, in queue items, and in the shared agent log. The gate
landed on 2026-07-26 (`17ff340`) and is now mandatory for every change that
ships a test, so the blast radius is every future task as well as the
backlog.

The failure is silent and biased toward false confidence: it never reports a
passing test as failing, only a defective test as sound.

## Evidence
Reported and reproduced by the round-4 reviewer subagent of
`athlete-benchmarks` task 3.2, which ran 22 mutations: two were
byte-length-preserving and were silently not applied until it cleared
`__pycache__` and re-ran with `-p no:cacheprovider`. One of the two then
became a **real survivor** — the mutation moving `save_profile`'s
`parse_benchmarks(document)` re-check to after `data_root.mkdir(...)` /
`tempfile.mkstemp(...)`, which leaks a `.athlete-*.tmp` and an fd on a refused
save. That is Req 6.7's "leaving no partial or temporary file behind on
failure", quoted verbatim in task 3.2's own bullet 2.

Not independently re-reproduced in the session that filed this item; the
underlying mtime+size validation rule is documented CPython behavior
(`importlib._bootstrap_external.SourceLoader.path_stats` / the `.pyc` header),
and the reviewer's own before/after runs are the instance evidence.

A separate consequence observed in the same review: a mutation harness that
applies two edits to one file in a single run can silently apply only the
last. Any harness should assert the mutated source differs from the original
after writing.

## How to pick it up
Read `.kiro/steering/change-protocol.md` § Fixture Discrimination — the
three-step gate ("Named / Run / Reverted") is where the instruction belongs,
since that is the text both templates quote. Then add the same line to
`.claude/skills/kiro-impl/templates/implementer-prompt.md` (Step 5) and
`templates/reviewer-prompt.md` (check 5.5), and to `kiro-review/SKILL.md`
§ 5.5 if it carries its own copy.

The command to mandate:

    find . -name __pycache__ -type d -prune -exec rm -rf {} + ; uv run pytest -q -p no:cacheprovider

Done when: the gate text requires it, both templates carry it, and the
protocol says plainly that a mutation result obtained any other way is not
evidence. Consider also adding the weaker fallback rule — prefer
length-*changing* mutations — for sessions that forget.

## Open questions
Whether to retro-verify existing PINNED claims. A full re-run is expensive;
the cheaper option is to state in the protocol that pre-dated claims are
unverified, and re-check only when a guard is next touched.

## Resolution

Closed 2026-07-29. Resolved more completely than the item asked. The item
requested a mandated `__pycache__` clear in `change-protocol.md` and in the
kiro-impl templates; what landed is a structural fix plus the documentation:

- `conftest.py:38-56` deletes every `__pycache__` under `src/` before anything
  imports it and sets `sys.dont_write_bytecode`, so a stale entry cannot exist
  during a pytest run — no step for an agent to remember.
- `tests/test_bytecode_hygiene.py` pins both halves
  (`test_the_session_does_not_write_bytecode_for_the_package_under_test`,
  `test_no_bytecode_cache_exists_under_src_during_the_run`).
- `.kiro/steering/change-protocol.md:142-164` documents the hazard and its
  direction, and it has a named anti-pattern row ("Stale bytecode", :197).
- The mandate reached all three skill destinations:
  `.claude/skills/kiro-impl/templates/implementer-prompt.md:74-78`,
  `.claude/skills/kiro-impl/templates/reviewer-prompt.md:96-100`, and
  `.claude/skills/kiro-review/SKILL.md:124-127`.

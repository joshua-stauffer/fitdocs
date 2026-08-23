---
id: 2026-07-26-scope-canonicalisation-duplicated
title: The benchmark scope-resolution case rule is reimplemented in the profile store, and a future alias would make files unwritable
status: open
importance: medium
importance_why: A one-line alias added to benchmarks.py turns every save of an affected profile into a hard ProfileError; the duplication is the reason save_profile needs a re-parse net at all.
effort: M
kind: inconsistency
area: athlete-benchmarks, src/fitdocs/benchmarks.py, src/fitdocs/load/profile.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, debug pass + rounds 3-5 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-scope-canonicalisation-duplicated.md] Give fitdocs.benchmarks a public scope-canonicalisation helper and have the profile store consume it"
context:
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/specs/athlete-benchmarks/tasks.md
  - src/fitdocs/benchmarks.py
  - src/fitdocs/load/profile.py
  - tests/load/test_profile.py
blocked_by: []
---

## What
`parse_benchmarks` resolves a `[benchmarks.<scope>]` table name to a `Sport`
case-insensitively, via `_resolve_scope` and `_SCOPE_BY_LOWER_SPORT`
(`src/fitdocs/benchmarks.py:192`, `:210-227`). The profile store's write path
must know the same rule, because it has to fold a hand-edited
`[benchmarks.Run]` into the canonical `[benchmarks.run]` before merging — but
it reimplements it independently as a set literal at
`src/fitdocs/load/profile.py:480`:

    canonical_scopes = {ATHLETE_SCOPE, *(sport.value.lower() for sport in Sport)}

The two agree today only because the rule is currently pure `.lower()`. The
store's own docstring flags the divergence risk and declares the fix
out of that task's boundary.

## Why it matters
The rules diverge the moment `benchmarks.py` gains any alias that is not a
lowercase `Sport` value — the natural example being `bike` → `Ride`. The
parser would then accept `[benchmarks.bike]`, the store's canonicaliser would
not recognise it, and it would be left unfolded alongside a canonical
`[benchmarks.ride]`. Because `save_profile` re-parses the assembled document
before writing, the result is not corruption but a **hard refusal**: every
save of such a profile raises `ProfileError` until the user hand-edits the
file. Loud rather than lossy, which is the intended posture — but the file is
unwritable, and the cause is a duplicated constant rather than anything the
user did.

The duplication is also the *only* reason `save_profile`'s re-parse net exists
(see Open questions).

## Evidence
Duplication, at `84e5e56`:
- `src/fitdocs/load/profile.py:480` — `canonical_scopes = {ATHLETE_SCOPE, *(sport.value.lower() for sport in Sport)}`
- `src/fitdocs/benchmarks.py:192` — `_SCOPE_BY_LOWER_SPORT: Final[dict[str, Sport]] = {...}`, consumed by `_resolve_scope` at `:210-227`

Consequence measured by the closing reviewer subagent of task 3.2, not
re-reproduced in this session: adding `"bike": Sport.RIDE` to
`_SCOPE_BY_LOWER_SPORT` and driving a real on-disk file through
`load_profile` / `save_profile` produced

    ProfileError: refusing to write .../athlete.toml: the assembled document
    would not be readable back: benchmarks.ride...

## How to pick it up
Read `src/fitdocs/benchmarks.py:192-227` for the resolution rule, then
`_canonicalize_benchmarks_region` in `src/fitdocs/load/profile.py` (~`:460-510`)
for the copy. Add a public helper to `fitdocs.benchmarks` — something of the
shape `canonical_scope_key(scope_name: str) -> str` — and consume it from all
three places that currently know the rule: `_resolve_scope`,
`benchmarks_to_document`, and the store's canonicaliser. `benchmarks.py` is
task 1.2's module, so this is a deliberate cross-task change; note it in that
task's Implementation Notes.

Done when: the rule exists once, all three call sites use it, and adding an
alias to the helper is provably enough to make a hand-edited file using that
alias round-trip. Add that alias-round-trip test — it is the regression the
duplication currently allows.

## Open questions
1. Once the helper lands, `save_profile`'s re-parse net loses its only stated
   purpose. The net has **no reachable trigger in today's codebase**: every
   production construction is `AthleteProfile(data=...)`, which parses in
   `__post_init__`, and `object.__new__` appears nowhere in `src/`, so both
   tests exercising the net must hand-forge a profile with
   `object.__new__` + `object.__setattr__`. Decide then whether the net and
   its two tests stay as defence-in-depth or are retired together.
2. `src/fitdocs/load/profile.py:487-488`'s non-`Mapping` scope-table branch is
   unreachable dead code — `parse_benchmarks` rejects that state eagerly — and
   would silently substitute `{}` if it ever were reached. Worth removing or
   converting to an assertion while in this code.
3. The store currently *refuses* an unmergeable collision across two scope
   spellings. A softer resolution was verified viable by the round-4 reviewer:
   fold only the **recognized** kind keys into the canonical table and leave an
   unmergeable **unrecognized** key under its original spelling — neither lossy
   nor refusing, and the parser tolerates the resulting shape. Consider it if
   the refusal proves annoying in practice.

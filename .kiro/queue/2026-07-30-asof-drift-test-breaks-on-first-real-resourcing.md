---
id: 2026-07-30-asof-drift-test-breaks-on-first-real-resourcing
title: The ASOF drift-discrimination test is coupled to the real registry's cleanliness, so the first genuine re-sourcing breaks it
status: open
importance: medium
importance_why: Benign in kind — it fails loudly, not silently — but it fails for the wrong reason at exactly the moment someone is doing the delicate work the gate exists to protect, and they will have to decide whether they broke something or the test was always going to do this.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_sources.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.2, round-4 review follow-up)
pinned_at: 7b82aff
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-asof-drift-test-breaks-on-first-real-resourcing.md] Give the ASOF drift test a synthetic clean registry so it survives the first real re-sourcing"
context:
  - tests/metrics/test_sources.py
  - src/fitdocs/metrics/sources.py
  - src/fitdocs/contract.py
blocked_by: []
---

## What

`test_constant_registry_asof_reddens_when_it_drifts_from_doc_version` in
`tests/metrics/test_sources.py` proves the conditional `ASOF` pin
discriminates: it passes a drifted `ASOF` and asserts the pin raises.

It passes the **real** `sources.CONSTANT_SOURCES` to that pin. The pin is
guarded by the clean-registry condition — it only fires while no constant
carries a `previous_value`. So the first genuine re-sourcing silences the pin,
and this test then fails with `DID NOT RAISE` even though nothing is wrong.

## Why it matters

Medium rather than low, for one reason: **it breaks at the worst moment.**

The person who trips it is, by construction, the person performing the first
real re-sourcing — moving a published constant's value and advancing
`DOC_VERSION` to match. That is the delicate operation this whole migration
gate exists to protect. They will be staring at a `DID NOT RAISE` in a test
named "reddens when it drifts", and will have to work out from scratch whether
they have broken the gate or whether the test was always going to do this.

It is not a silent failure, which is why it is not worse. But the gate's
credibility at that moment is the entire point of having built it, and a
spurious failure there costs exactly the confidence the gate is supposed to
supply.

There is a mild irony worth recording: the test is coupled to reality for the
same reason the pin itself needed to be — round 3 of this task rejected a
version of the pin whose precondition was synthetic, because that severed it
from the real constants. The right split is that the **pin** must see reality
(so an untethered `ASOF` reds) while the **discrimination test** for that pin
need not (it is demonstrating a mechanism, not a state).

## Evidence

Observed by the task 13.2 round-4 reviewer while running acceptance case 2, at
the tree that became `7b82aff`.

Adding a real `previous_value=99.0` to `TSS_SCALE` in
`src/fitdocs/metrics/sources.py` and running `uv run pytest` produced four
failures. Three are the intended "today's registry is clean" locks firing
loudly, which is correct. The fourth was
`test_constant_registry_asof_reddens_when_it_drifts_from_doc_version`, failing
with `DID NOT RAISE` — the reviewer had to relax it alongside the three locks
before the acceptance case could be evaluated.

The pin itself is sound and stays sound: with `ASOF` drifted to 3 against a
clean registry, `test_constant_trigger_is_quiet_against_the_real_registry`
reds as a sole failure (`CONSTANT_REGISTRY_ASOF_DOC_VERSION (3) must match
contract.DOC_VERSION (4)`).

## How to pick it up

1. Open `test_constant_registry_asof_reddens_when_it_drifts_from_doc_version`
   in `tests/metrics/test_sources.py` and find where it passes
   `sources.CONSTANT_SOURCES` to the pin helper.
2. Build a **synthetic clean registry** for that call — a small tuple of
   `CitedConstant` values with `previous_value=None` — so the test demonstrates
   the mechanism without depending on the real registry's state. The sibling
   test `test_constant_registry_asof_pin_is_quiet_once_a_constant_moves`
   already constructs a synthetic *moved* registry; mirror its shape.
3. Leave the pin's own call site in
   `test_constant_trigger_is_quiet_against_the_real_registry` reading the real
   registry — that coupling is deliberate and is what makes an untethered
   `ASOF` detectable. Do not "fix" both.
4. Verify by mutation: `CONSTANT_REGISTRY_ASOF_DOC_VERSION 4 → 3` must still
   red, and adding a real `previous_value` to a registry constant must **not**
   red this drift test any more.

Done looks like: the first real re-sourcing reds only the "today's registry is
clean" locks it is genuinely supposed to update, and no discrimination test
fails for a reason unrelated to the change.

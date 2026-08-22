---
id: 2026-07-26-prompt-answer-rejected-by-store-becomes-failure
title: A session-validated prompt answer the store then rejects escapes the prompt flow as a document failure instead of a re-ask
status: open
importance: medium
importance_why: A user typing a legitimate-looking answer to a legitimate prompt gets the document reported as failed rather than being re-asked, and the flow's own contract says a declined field is an ordinary outcome.
effort: M
kind: gap
area: athlete-benchmarks, src/fitdocs/load/prompts.py, .kiro/specs/athlete-benchmarks/design.md
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.2 reviewer FOLLOW_UPS)
pinned_at: f7bdf97
resume_command: "do: decide how collect_missing_fields should handle a value the session accepted but the store rejects -- re-ask, decline, or propagate -- and record the decision in athlete-benchmarks design.md's PromptFlowIntegration before implementing [queue: .kiro/queue/2026-07-26-prompt-answer-rejected-by-store-becomes-failure.md]"
context:
  - src/fitdocs/load/prompts.py
  - src/fitdocs/load/profile.py
  - src/fitdocs/benchmarks.py
  - .kiro/specs/athlete-benchmarks/design.md
blocked_by: []
---

## What
`collect_missing_fields` delegates range and parse validation to the session,
which re-asks until it has a valid in-range value or a decline. It then hands
that value to the store. But the store applies validation the session knows
nothing about — and when the store rejects, the exception escapes the flow
entirely.

Concretely: an `AthleteField(kind="float", ...)` declaring a benchmark for a
whole-beat quantity. The session happily accepts `190.5` — it is a float, and in
range. `AthleteProfile.with_benchmark` then raises
`ValueError: max_hr_bpm value must be a whole number of beats per minute, got
190.5`. That propagates out of `collect_missing_fields` into the engine's
per-document `except Exception`, so the document is reported **failed** rather
than the field being re-asked or declined.

Two validation authorities disagree and only one of them can re-ask.

## Why it matters
The prompt flow's whole contract is that a field it cannot fill is an *ordinary*
outcome: return it still-missing, persist nothing, continue the pass
(Req 3.4/3.5, 8.5/8.6). A rejected answer is the one case that breaks that
contract, and it does so in the direction that looks like a crash. The user's
answer was reasonable and the prompt gave no indication a fraction was illegal.

Note the shape **pre-exists for flat fields** via `with_value`, so this is not
introduced by athlete-benchmarks — but 4.2 widened it to the benchmark path, and
design's `PromptFlowIntegration` is silent on it, which is why it is worth a
decision rather than a silent inheritance.

## Evidence
At `f7bdf97`, driving the flow directly (reviewer-measured during task 4.2
review):

```
AthleteField(kind="float", benchmark=BenchmarkRef(BenchmarkKind.MAX_HR_BPM, None))
answer 190.5
-> ValueError: max_hr_bpm value must be a whole number of beats per minute, got 190.5
   raised out of collect_missing_fields
```

The two validation sites: the session's parse/range loop in
`src/fitdocs/load/prompts.py` (`_prompt_until_accepted`), and the store's
`_validate_benchmark_value` / `_validate` reached through
`with_benchmark` / `with_value` in `src/fitdocs/load/profile.py`. `INTEGRAL_KINDS`
in `src/fitdocs/benchmarks.py` is what makes a whole-beat quantity reject a
fraction.

## Open questions
Three candidate resolutions, and this is a product decision:
1. **Re-ask** — catch the store's rejection, `inform` the user why, and loop. Most user-friendly; puts store validation inside the prompt loop.
2. **Decline** — treat it as a declined field: still-missing, nothing persisted, reason reported. Cheapest, consistent with the flow's existing "cannot fill it" path.
3. **Forbid the declaration** — make a `kind`/quantity mismatch a *declaration* error caught when the calculator is registered, so the illegal prompt can never be presented. Fixes the cause rather than the symptom, but needs a registry-time check.

Option 3 is the only one that prevents the bad prompt from being shown at all,
and it composes with either of the others as defence in depth.

## How to pick it up
1. Read `_prompt_until_accepted` in `src/fitdocs/load/prompts.py` and the validation in `AthleteProfile.with_value` / `with_benchmark` — the two authorities and what each knows.
2. Read design's `#### PromptFlowIntegration` (`.kiro/specs/athlete-benchmarks/design.md` ~line 975); it specifies the presence and persistence branches and says nothing about a rejected value. The decision belongs there first.
3. Done looks like: the decision recorded in design, and a test driving a `kind`/quantity mismatch that asserts the chosen behavior — with a mutation proving the assertion can fail (the current behavior raises, so asserting "does not raise" is only meaningful if you check what happens *instead*).

Note the flat-field half is pre-existing, so scope the fix deliberately: fixing
only the benchmark path leaves two prompt fields behaving differently.

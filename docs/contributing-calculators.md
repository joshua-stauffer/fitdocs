# Contributing a load calculator

fitdocs computes training load through a pluggable seam: every methodology is
a `LoadCalculator` registered by id. **fitdocs ships exactly one built-in
methodology, `threshold`** — the load layer is otherwise only the contract,
the registry, the athlete profile store, the prompt flow, and the document
integration, and the built-in needs no privileged path: it registers through
the same `register()`/`validate_calculator()` gate a plugin author's
calculator does. Every other training load a user sees comes from a
calculator a plugin author or a downstream project registered. You can add
one — a running system, a cycling or strength model, anything — **without
touching core code**. This page shows
how; the authoritative, always-current source of truth is the docstrings in
[`src/fitdocs/load/types.py`](../src/fitdocs/load/types.py).

This page covers the contract only — *writing* a calculator. For how to
*distribute or load* one (a packaged distribution's entry-point declaration,
the local plugin file/directory alternative, the public import surface, and
diagnosing why a calculator isn't showing up), see
[`docs/plugins.md`](plugins.md).

Two principles govern every calculator: **absent data yields a typed "not
computed", never a fabricated value**, and **estimates derived from noisy
recorded data are confirmed by the user, never silently guessed**.

## 1. Implement the contract

A calculator satisfies the `LoadCalculator` protocol (structural — no base
class to inherit). Declare its identity and the sports it covers, declare the
athlete inputs it needs, and implement `compute`.

`compute` takes five arguments: the activity, its derived metrics, a
read-only view of the athlete profile, the interaction session, and a
**`LoadContext`** — the per-pass state (Section 5 below covers it in full).

Below is a complete, self-contained worked example. It is not a real
methodology — the "load" it produces is illustrative arithmetic — but every
name, signature, and outcome it uses is the shipped contract, and this exact
block is type-checked in this repository's test suite so it cannot drift
silently.

<!-- doctest: worked-example start -->
```python
from __future__ import annotations

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs.load import (
    AthleteField,
    Computed,
    InteractionSession,
    LoadCalculator,
    LoadContext,
    LoadOutcome,
    LoadResult,
    MissingInputs,
    NotComputed,
    ProfileView,
)
from fitdocs.load.types import NonSelectedValue, QualityFlag


class ExampleCalculator:
    """A worked example only -- not fitdocs' own `threshold` built-in."""

    calculator_id = "example-pace-load"
    display_name = "Example Pace Load"
    supported_modalities = frozenset({Modality.RUN})

    def supports(self, activity: Activity) -> bool:
        """Optional narrowing (Req 1.14). Always gate on the declared
        modality first, then narrow further -- never widen beyond
        ``supported_modalities``."""
        if activity.modality not in self.supported_modalities:
            return False
        # This methodology needs at least one recorded split beyond the
        # whole-activity lap; decline before any prompting rather than
        # surfacing a confusing missing-inputs outcome later.
        return len(activity.laps) >= 2

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (
            AthleteField(
                key="example-pace-load.threshold_pace_s_per_km",
                label="Threshold pace (seconds per km)",
                kind="float",
                minimum=120.0,
                maximum=600.0,
                help_text=(
                    "Your lactate-threshold pace, from a recent time trial."
                ),
            ),
        )

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        threshold = profile.get_number(
            "example-pace-load.threshold_pace_s_per_km"
        )
        if threshold is None:
            # Belt-and-suspenders: the engine's generic prompt flow already
            # tried to collect this field before calling `compute`. A
            # non-interactive pass can still leave it absent -- never
            # substitute a value.
            return MissingInputs(fields=self.required_athlete_fields())

        if metrics.avg_pace_s_per_km is None:
            return NotComputed(
                reason="no recorded pace to compare against the confirmed "
                "threshold"
            )
        pace_value = threshold / metrics.avg_pace_s_per_km * 100.0

        # A candidate channel this methodology *could* have preferred, but
        # did not select -- reported, never silently dropped (Req 1.8).
        if metrics.avg_heart_rate_bpm is None:
            hr_candidate = NonSelectedValue(
                key="hr",
                label="Heart-rate-based estimate",
                value=None,
                reason="activity recorded no heart-rate stream",
            )
        else:
            hr_candidate = NonSelectedValue(
                key="hr",
                label="Heart-rate-based estimate",
                value=metrics.avg_heart_rate_bpm / 2.0,  # illustrative only
                reason=(
                    "this methodology prefers pace over heart rate when "
                    "both are available"
                ),
            )

        confirmed = session.confirm(
            f"Use an estimated load of {pace_value:.1f} from pace data?",
            default=True,
        )
        if confirmed is not True:
            # A decline or a non-interactive session both land here --
            # absence is never consent (Req 9.1).
            return NotComputed(reason="pace-based estimate not confirmed")

        # Quality flags are records, never adjustments (Req 1.9): carrying
        # one never changes `value` above. The three verdicts mean:
        #   "detected"     -- the check ran and found the condition.
        #   "not-detected" -- the check ran and did NOT find the condition.
        #   "not-assessed" -- the check could not run at all (e.g. the data
        #                     it needs was absent). Never conflate this with
        #                     "not-detected", which claims a check that ran.
        cadence_flag = QualityFlag(
            key="cadence-lock",
            label="Cadence lock",
            verdict="not-detected",
            detail="cadence varied by more than 2 rpm across recorded samples",
        )
        recency_flag = QualityFlag(
            key="activity-date",
            label="Activity date on record",
            verdict="not-assessed" if context.activity_date is None else "detected",
            detail=(
                "document carries no parseable date"
                if context.activity_date is None
                else f"activity recorded on {context.activity_date.isoformat()}"
            ),
        )

        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=pace_value,  # THE load -- the only value that counts
                basis="pace relative to confirmed threshold pace",
                non_selected=(hr_candidate,),
                flags=(cadence_flag, recency_flag),
                inputs_used=(("Threshold pace", f"{threshold:.0f} s/km"),),
                notes=(
                    "Illustrative worked example only -- not a real "
                    "methodology.",
                    # `context.settings` is the resolved `[load]` table for
                    # this pass -- read it, never open fitdocs.toml or a
                    # clock yourself.
                    f"[load] configuration for this pass: {context.settings!r}",
                ),
            )
        )


def _conformance_check(
    activity: Activity,
    metrics: DerivedMetrics,
    profile: ProfileView,
    session: InteractionSession,
    context: LoadContext,
) -> None:
    """You do not need this in your own calculator -- delete it when you
    copy this example. It exists only so fitdocs' own test suite can prove
    this page has not drifted from the shipped contract.

    Never called -- exists only so mypy checks two things about the
    class above: the assignment below is what makes it a *checked
    implementation* of the LoadCalculator contract rather than merely code
    that uses its names (mypy --strict only accepts it if
    ExampleCalculator's members actually satisfy the shipped Protocol's
    signatures, so a drifted `compute` signature fails right here); the
    keyword call below it additionally checks that the Protocol's own
    parameter names still match what this guide documents -- a bare
    parameter rename in the shipped contract would not fail the assignment
    alone, since positional-parameter names are not otherwise significant
    to structural typing, but it fails this keyword call immediately."""
    _conformance: LoadCalculator = ExampleCalculator()
    _conformance.compute(
        activity=activity,
        metrics=metrics,
        profile=profile,
        session=session,
        context=context,
    )
```
<!-- doctest: worked-example end -->

- **`calculator_id`** is the stable registry key and the value written to a
  document's `load_methodology` frontmatter. Keep it short and unique.
- **`supported_modalities`** is a `frozenset[Modality]`
  (`Modality.RUN | BIKE | SWIM | STRENGTH | OTHER`). Declare only what you
  genuinely score.
- **`required_athlete_fields()`** declares each `AthleteField` with its `kind`,
  its inclusive `minimum`/`maximum` validation range, and `help_text`. The
  engine's generic prompt flow is driven entirely by these declarations — it
  asks for any missing field, validates against the range, persists the answer
  to `athlete.toml` (once, so the user is never re-asked), and only then calls
  your `compute`. **You never write field-prompting code**; a dotted `key` such
  as `"example-pace-load.threshold_pace_s_per_km"` scopes the value under an
  `[example-pace-load]` table so methodologies never collide. For a
  *benchmark* field declared via `AthleteField.benchmark`, the generic flow
  may additionally ask the athlete whether an accepted answer also applies to
  earlier activities, back to the activity that prompted it — your
  calculator never sees or handles that question.

Read `profile` values with `profile.get_number(key)` — it returns
`float | None` (dotted keys work), and `None` means absent, never a default.

## 2. Answer the support question (optional)

Before collecting any athlete input, the engine asks whether your calculator
covers a given activity — prompt-free, athlete-data-free. It asks through its
own module-level `supports_activity(calculator, activity)` (defined in
`fitdocs.load.types` and re-exported from `fitdocs.load`, like every other
name this guide teaches); **you never call that yourself.** What you write is an
*optional* method on your own class:

```python
def supports(self, activity: Activity) -> bool:
    ...
```

- **`LoadCalculator` does not declare `supports`** — it is not a Protocol
  member, so it is never mandatory. A calculator that defines nothing
  answers the question by its declared `supported_modalities` alone, for
  free.
- If you do define `supports`, it may only ever **narrow** what
  `supported_modalities` already declares — never widen it. **Always gate on
  the modality membership test first**, exactly as the worked example above
  does:

  ```python
  def supports(self, activity: Activity) -> bool:
      if activity.modality not in self.supported_modalities:
          return False
      return ...  # your narrower condition
  ```

  A `supports` that skips this guard can answer `True` for a modality it
  never declared, which breaks the registry's `for_modality` prefilter — a
  real defect caught in review of this contract, not a hypothetical one.

## 3. Outcome semantics (be honest)

`compute` returns exactly one member of the closed `LoadOutcome` union:
`Computed | Unsupported | MissingInputs | NotComputed`. Choosing the right one
is the whole contract:

- **`Unsupported(reason=...)`** — the activity's sport is outside your scope.
  The engine already filters most of these out via `supports_activity`
  before `compute` is ever called, but a calculator may still decline this
  way from inside `compute` for a reason `supports` did not or could not
  express. Never force a number for an unsupported sport.
- **`MissingInputs(fields=...)`** — a required athlete input is still absent
  after the generic prompt flow (e.g. a non-interactive run, or the user
  declined). Name the still-missing fields; **do not substitute a value.**
- **`NotComputed(reason=...)`** — nothing was computed, and this is why.
  Covers every case that is neither an unsupported sport nor a missing
  input: a declined confirmation, a non-interactive pass reaching a
  confirmation gate, or a methodology that could score no channel at all
  for this activity. This is the renamed "nothing was computed" outcome —
  it is not defined in terms of any confirmation step, and it is not named
  after one.
- **`Computed(result=LoadResult(...))`** — return this **only** with a real,
  user-confirmed result.

`compute` must **never raise** for missing or malformed athlete data — return
a typed outcome instead. Absent data is a typed absence; a fabricated or
defaulted value is a contract violation.

## 4. The result shape: one load, everything else is diagnostic

`LoadResult.value` is **the only value that counts** — the activity's load.
Everything else on `LoadResult` is diagnostic and must never be read as the
load by anything downstream:

- **`non_selected`** — a tuple of `NonSelectedValue`, one entry per value your
  methodology *computed but did not select*. Report one whenever you had a
  genuine alternative candidate, whether or not you could actually compute
  it:
  - You computed it but preferred a different channel: set `value` to the
    number, and phrase `reason` as *why the selected value won*, not why the
    alternative is wrong (`"this methodology prefers pace over heart rate
    when both are available"`).
  - You could not compute it at all (a stream was absent, a required field
    could not be collected for that channel): set `value=None` — **never
    coerce a missing candidate to `0`** — and phrase `reason` as *what was
    missing* (`"activity recorded no heart-rate stream"`).
  - If your methodology genuinely has no alternatives, leave `non_selected`
    empty. Do not invent placeholder entries for channels that were never in
    play.
- **`flags`** — a tuple of `QualityFlag`, one entry per quality check you ran
  about the data behind `value`. A flag is a record, never an adjustment:
  raising one must never change `value`. Each carries one of three verdicts:
  - `"detected"` — the check ran and found the condition it looks for.
  - `"not-detected"` — the check ran and did **not** find the condition.
  - `"not-assessed"` — the check could not run at all, typically because the
    data it depends on was absent. Do not report `"not-detected"` when you
    never actually ran the check — that claims more than you know.
  If your methodology raises no quality concerns for this result, leave
  `flags` empty rather than fabricating an all-clear entry.

A single-value result with nothing to report is valid and expected: supply
empty `non_selected` and `flags` tuples rather than manufacturing entries to
fill them.

## 5. Aggregating over recorded samples (Req 9.2)

When a value your calculator derives comes from a recorded sample stream
(heart rate, power, cadence, or any other per-sample channel), that
derivation must be an aggregate over the samples *actually recorded* —
**never treat a missing sample as a zero.** Averaging a gappy power stream by
dividing by the activity's total duration instead of the count of samples
that were actually recorded silently drags the result toward zero and
fabricates the gaps as "no effort," which is exactly the fabricated-`0`
failure this contract exists to prevent.

This is a documented postcondition, not something the `LoadCalculator`
protocol or `uv run mypy` can enforce for you — a calculator whose recorded
samples are gappy is responsible for its own aggregation math staying honest
about what was actually recorded.

## 6. Reading configuration and the activity's date: only through `LoadContext`

`compute`'s fifth parameter, `context: LoadContext`, is the **only** route to
two things: the resolved `[load]` configuration for this pass
(`context.settings`) and the activity's own recorded local calendar date
(`context.activity_date`, `None` when the document records none). A
calculator must never open `fitdocs.toml` itself, never import
`fitdocs.settings` or `fitdocs.load.settings` to re-read it, and never read a
clock (`datetime.now()`, `date.today()`) to stand in for the activity's date.

**`profile: ProfileView` is stored athlete data only.** It exposes exactly
`get_number(key) -> float | None` and carries nothing about *this pass* — no
activity date, no configured window, no resolved settings. If you find
yourself wanting to smuggle per-pass state onto the profile (writing the
activity's date into `athlete.toml`, or caching the resolved settings as
instance state on your calculator between calls so a later `compute` can
"remember" them) — don't. That workaround was tried and rejected while this
contract was drawn; per-pass state belongs on `context`, every call, and
nowhere else. A calculator instance is expected to be reused across many
activities in one pass, so anything it stashes on `self` between calls is
either wrong for the next activity or a duplicate of what `context` already
carries for free.

## 7. Talk to the user only through the session

All dialog goes through the injected `InteractionSession`. Never call
`input()`, `print()`, `typer`, or `rich` yourself — that keeps your calculator
drivable by any front end and by scripted tests. The primitives:

`confirm(question, *, default=True) -> bool | None`,
`ask_int(...) -> int | None`, `ask_float(...) -> float | None`,
`choose(question, options, ...) -> int | None`, and `inform(message) -> None`
(output only).

**Every ask returns `None` when the user declines or the session is
non-interactive — treat `None` as "do not compute" and return `NotComputed`.**
Absence is never consent.

```python
zone = session.ask_int("Confirm the training zone", minimum=1, maximum=10, default=est)
if zone is None:
    return NotComputed(reason="training zone not confirmed")
```

**Confirmation-gate anything derived from noisy data.** If you estimate a
value from recorded HR, pace, or laps, surface the estimate for the user to
confirm or override rather than silently using it, exactly as the worked
example's `session.confirm(...)` call does.

### Optional: per-field confirmation hints

To echo derived context right after the user answers a field, add an
additive `athlete_field_hints` mapping to your calculator instance, keyed by
`AthleteField.key`:

```python
def __init__(self) -> None:
    self.athlete_field_hints = {
        "example-pace-load.threshold_pace_s_per_km": self._threshold_hint,
    }
```

The engine reads it generically (via `getattr`, so it is not part of the
protocol) and, after a valid answer, echoes `hint(value)` and asks the user to
confirm the field.

## 8. Register it

Register your calculator so the engine can find it by id and by modality:

```python
from fitdocs.load import register

register(ExampleCalculator())
```

Importing `fitdocs.load` registers its own `threshold` built-in — on a
fresh interpreter `available()` returns exactly `(THRESHOLD_CALCULATOR,)`
until a plugin author or a downstream methodology calls `register()` to add
another. A duplicate id raises
`DuplicateCalculatorIdError`. Once registered, `for_modality(modality)`
returns your calculator for its sports and `fitdocs load --calculator
example-pace-load` selects it explicitly (still declining any sport it does
not support).

## 9. Test against your methodology's own published numbers

A new calculator must reproduce **its own methodology's published examples**,
so your numbers are verifiable, not just internally consistent — pin a unit
test to the worked example(s) your methodology's own source publishes (a
paper, a workbook, a reference implementation you are porting), not merely to
whatever your code happens to output today.

Drive `compute` in tests with a scripted `InteractionSession` (queued
answers) — never a real terminal — to cover confirm, override, decline, and
the non-interactive path. Cover every `LoadOutcome` variant your calculator
can reach, and assert the `non_selected`/`flags` shape directly: that a value
your methodology could not compute carries `value=None` rather than a
fabricated `0`, and that a verdict is `"not-assessed"` only when the
underlying check genuinely never ran.

## 10. Bundled data and licensing

If your methodology ships lookup tables or reference data, add them as
package data under your calculator's own package and load them with
`importlib.resources` so they resolve from an installed tool, fully offline
— never a network fetch at compute time. Most Python build backends
(hatchling among them) include package data files by default; add a
packaging test that asserts your data ships in the built wheel and loads
from a real install, so a packaging regression is caught before a release
rather than by a user's missing-file error.

**Data shipped inside a calculator package must be redistributable.** If the
data is not yours to redistribute freely, do not bundle it — either omit it
and document how a user obtains their own copy, or keep an explicit
licensing/attribution note in the file header so it travels with every copy
of the file, and add a test that guards the note against being silently
dropped when the data is refreshed.

---

Re-read the docstrings in
[`src/fitdocs/load/types.py`](../src/fitdocs/load/types.py) when in doubt —
they are the contract this page teaches, and they are the first thing to
change if this page and the shipped code ever disagree.

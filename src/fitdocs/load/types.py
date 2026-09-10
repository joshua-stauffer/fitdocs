"""The load-calculator contract: the pluggable seam every methodology plugs into.

This module is the bottom of the load dependency chain. It declares *what* a
training-load methodology is -- its identity, the sports it covers, the athlete
inputs it needs, its typed outcomes -- and the interaction primitives a
calculator speaks through, without knowing *how* any of it is wired: no I/O, no
prompting, no registry, no document editing, and no imports from other
``fitdocs.load.*`` modules. Its only non-stdlib imports are the fit-ingest
public model/metrics types it consumes (Req 1.1-1.4). The single exception is
:class:`LoadContext`'s reference to :class:`~fitdocs.load.settings.LoadSettings`,
which is imported under ``if TYPE_CHECKING:`` for the annotation only and is
never a runtime import (Req 14.7).

**The support question (Req 1.14) is asked through one module-level function,
never a Protocol method.** ``Protocol`` method bodies are inherited only by
*explicit* subclasses of the Protocol (``typing`` semantics) -- a plain
duck-typed class that merely provides the right attributes never receives a
default. Declaring ``supports`` as a :class:`LoadCalculator` Protocol member
with a default body (design.md's original mechanism, ~1508-1520) would
therefore make ``supports`` *mandatory* for structural conformance under
mypy --strict, and a genuinely duck-typed calculator that omits it would
register cleanly and then raise ``AttributeError`` the first time the layer
called ``calculator.supports(activity)`` -- exactly the plugin-author shape
:mod:`docs/plugins.md` and the installed plugin fixture use. That contradicts
Req 1.14's core: *"a methodology that declares nothing more specific shall
answer it by its declared modalities"* with **no subclassing and no
registration-time mutation required**. So :func:`supports_activity` is the
single entry point instead: it returns a calculator's own ``supports`` when
the calculator happens to define one (an *optional*, off-protocol capability,
exactly like :attr:`LoadCalculator`'s existing ``athlete_field_hints`` seam
read via ``getattr`` elsewhere in this layer), and falls back to the modality
membership test otherwise. ``LoadCalculator`` itself declares no ``supports``
member, so a duck-typed calculator carrying only ``supported_modalities`` and
the 5-arg ``compute`` still satisfies the Protocol structurally (verified
against mypy --strict on ``src/``). A calculator that does define ``supports``
may only ever *narrow* its declared modalities, never widen them -- not
mechanically enforced here, but required of every implementation, since it is
what lets the registry's modality prefilter and this question compose safely
(design.md ~1183).

Two invariants make the seam safe:

* **Outcomes are a closed union.** :data:`LoadOutcome` has exactly four
  variants -- computed, unsupported, missing-inputs, not-computed. Downstream
  handling must be exhaustive; an ``assert_never`` fallthrough turns a dropped
  variant into a static (mypy --strict) error rather than a silent runtime gap.
* **Absence is never consent.** Every :class:`InteractionSession` primitive
  returns ``None`` when the user declines or the session is non-interactive, so
  a calculator can never mistake "no answer" for approval and fabricate a load
  value (Req 9.1).

All contract types are ``@dataclass(frozen=True)`` and every sequence field is a
``tuple`` so results render deterministically downstream.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Literal, Protocol

from fitdocs import Activity, DerivedMetrics, Modality, Sport
from fitdocs.benchmarks import Benchmark, BenchmarkKind

if TYPE_CHECKING:  # annotation-only; no runtime edge (Req 14.7)
    from fitdocs.load.settings import LoadSettings

__all__ = [
    "AthleteField",
    "BenchmarkRef",
    "Computed",
    "InteractionSession",
    "LoadCalculator",
    "LoadContext",
    "LoadOutcome",
    "LoadResult",
    "MissingInputs",
    "NonSelectedValue",
    "NotComputed",
    "ProfileView",
    "QualityFlag",
    "Unsupported",
    "supports_activity",
]


@dataclass(frozen=True)
class BenchmarkRef:
    """Identifies the benchmark table an :class:`AthleteField` collects into
    (Req 7.1, 8.1) -- discipline and quantity, never a value path."""

    kind: BenchmarkKind
    """Which benchmark quantity this field collects."""
    discipline: Sport | None
    """The discipline this field's benchmark is scoped to, or ``None`` for
    the athlete-wide scope."""


@dataclass(frozen=True)
class AthleteField:
    """One athlete input a methodology declares it requires.

    The engine's generic prompt flow is driven entirely by these declarations,
    so a calculator never writes prompting code of its own (Req 1.1, 3.1).
    """

    key: str
    """Profile key; dotted for methodology-scoped tables,
    e.g. ``"mycalc.custom_threshold"``. When :attr:`benchmark` is set, ``key``
    identifies the *table* the entry lives in (``benchmarks.<scope>.<kind>``)
    rather than a value path -- the field is collected as a dated benchmark,
    not a flat profile value (Req 8.1)."""
    label: str
    """Human prompt label, e.g. ``"Custom threshold"``."""
    kind: Literal["int", "float"]
    """Numeric parse/validation kind for the prompt flow."""
    minimum: float | None
    """Inclusive lower bound for validation, or ``None`` for unbounded."""
    maximum: float | None
    """Inclusive upper bound for validation, or ``None`` for unbounded."""
    help_text: str | None = None
    """What the value means and how to find it; shown when prompting."""
    benchmark: BenchmarkRef | None = None
    """When set, this field is collected as a dated benchmark rather than a
    flat profile value; ``key`` is then the identity of the table it lives in
    (``benchmarks.<scope>.<kind>``), not a value path (Req 8.1)."""


@dataclass(frozen=True)
class NonSelectedValue:
    """One value a methodology computed but did not select as the activity's
    load (Req 1.8).

    Deliberately serves two cases distinguished by ``value is None``: a value
    the methodology *did* compute but chose not to select (``value`` set), and
    a candidate it could not compute at all (``value is None``). The latter is
    never coerced to ``0.0`` -- absent data stays absent (Req 9.1, 1.11).
    """

    key: str
    """Methodology-owned identifier, e.g. ``"hr"``."""
    label: str
    """Display label, e.g. ``"HR channel"``."""
    value: float | None
    """The computed value; ``None`` when none was computed."""
    reason: str
    """Why this is not the activity's load; never empty."""


@dataclass(frozen=True)
class QualityFlag:
    """One quality verdict a methodology raised about the data behind its
    result (Req 1.9).

    A flag is a record, never an adjustment: carrying one never alters the
    selected :attr:`LoadResult.value`.
    """

    key: str
    """What was checked, e.g. ``"cadence-lock"``."""
    label: str
    """Display label."""
    verdict: Literal["detected", "not-detected", "not-assessed"]
    """The quality verdict."""
    detail: str
    """The basis for the verdict; never empty."""


@dataclass(frozen=True)
class LoadResult:
    """A successfully computed training-load result (Req 1.2).

    Carries everything a document render and the machine-readable payload need,
    with no back-reference to how it was computed. Sequence fields are tuples so
    identical inputs render byte-identically.

    :attr:`value` is the only field of its kind: no diagnostic entry in
    :attr:`non_selected` or :attr:`flags` shares its name, type position, or
    frontmatter projection, so no consumer can mistake a diagnostic for the
    activity's load (Req 1.10). A methodology with nothing to diagnose supplies
    empty ``non_selected`` and ``flags`` tuples -- nothing is fabricated on its
    behalf (Req 1.11).
    """

    calculator_id: str
    """Stable methodology identifier, e.g. ``"mycalc"``."""
    display_name: str
    """Human-readable methodology name, e.g. ``"My Custom Calculator"``."""
    value: float
    """THE activity's load -- the one value that counts."""
    basis: str
    """What ``value`` was derived from; never empty."""
    non_selected: tuple[NonSelectedValue, ...]
    """Values the methodology computed but did not select; empty when none
    (Req 1.8, 1.11)."""
    flags: tuple[QualityFlag, ...]
    """Quality flags raised about the data behind ``value``; empty when none
    (Req 1.9, 1.11)."""
    inputs_used: tuple[tuple[str, str], ...]
    """Ordered ``(label, value)`` pairs of the inputs that produced ``value``."""
    notes: tuple[str, ...]
    """Estimation basis, caveats, and user overrides, in display order."""


@dataclass(frozen=True)
class Computed:
    """Outcome: the calculator produced a confirmed load result (Req 1.2)."""

    result: LoadResult


@dataclass(frozen=True)
class Unsupported:
    """Outcome: the activity's sport is outside the calculator's scope (Req 1.3).

    No load value is ever produced for such an activity; :attr:`reason` names
    the sport.
    """

    reason: str


@dataclass(frozen=True)
class MissingInputs:
    """Outcome: required athlete inputs are absent and could not be collected.

    Names the still-missing fields so the caller can report them; the
    calculator never substitutes values (Req 1.4).
    """

    fields: tuple[AthleteField, ...]


@dataclass(frozen=True)
class NotComputed:
    """Outcome: nothing was computed, and this is why (Amendment 3).

    Covers every case in which a methodology reaches no load value without
    that being an unsupported sport or a missing input: a non-interactive
    pass, a user declining a required confirmation, or a methodology that
    could score no channel for this activity. :attr:`reason` states which.
    """

    reason: str


LoadOutcome = Computed | Unsupported | MissingInputs | NotComputed
"""The closed set of calculator outcomes. Handling must be exhaustive: fold it
with an ``assert_never`` fallthrough so a new variant is a static error."""


@dataclass(frozen=True)
class LoadContext:
    """Everything about *this pass and this activity* a calculator may need
    that is neither the activity itself nor the athlete profile (Amendment 3).

    The engine builds one per activity and passes it as :meth:`LoadCalculator.
    compute`'s fifth parameter (Req 1.12). It is the *only* route by which a
    calculator reaches the resolved ``[load]`` configuration or the activity's
    own date -- a calculator opens no settings file and reads no clock.

    Frozen with exactly these two members; it never grows a third without a
    requirements revision (Req 1.12, 1.13).
    """

    activity_date: date | None
    """The document's own recorded local calendar date -- the same value the
    file name is built from -- or ``None`` when the document records none.
    Never a clock read, a UTC instant, or a time-zone conversion."""
    settings: LoadSettings
    """The resolved ``[load]`` configuration for this pass (Req 14.5)."""


class ProfileView(Protocol):
    """Minimal read-only view of the athlete profile consumed by calculators.

    Satisfied later by ``AthleteProfile`` in the profile store; declaring it
    here keeps the contracts module free of any store dependency and the
    dependency direction one-way (store depends on contracts, never the
    reverse).

    **Stays a store view (Amendment 3, Req 1.13).** It exposes stored athlete
    data only -- it must never grow the activity's date, a configured window,
    or the resolved load configuration. Those are per-pass state and belong on
    :class:`LoadContext`; keeping them off this protocol is what keeps its
    documented meaning true and the import direction one-way.
    """

    def get_number(self, key: str) -> float | None:
        """Return the numeric profile value at ``key`` (dotted for scoped
        tables), or ``None`` when absent -- never a fabricated default."""
        ...

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        """Return the benchmark of ``kind``/``discipline`` applicable to an
        activity dated ``on``, or ``None`` when none applies (Req 7.1, 7.7).

        ``discipline`` and ``on`` are explicit arguments, never encoded into a
        key string (Req 7.5). ``on`` is the *activity's* date -- this member
        holds no bound date of its own and never assumes today's (Amendment 3).
        Absent an athlete-declared exception, never returns an entry measured
        after ``on``; the one exception (*athlete-benchmarks* Amendment 1,
        3.10) is an entry the athlete explicitly declared, via its own
        ``applies_from``, to reach back to or before ``on`` -- this member
        itself never applies a later measurement on its own."""
        ...

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        """Report whether any benchmark of ``kind``/``discipline`` is on file
        at all, independent of whether one applies to any particular date
        (Req 7.2)."""
        ...


class InteractionSession(Protocol):
    """The primitives a calculator's confirmation dialogs speak through.

    Every question-asking method returns ``None`` when the user declines or the
    session is non-interactive. Callers MUST treat ``None`` as "do not compute":
    absence is never consent (Req 3.4, 3.5, 9.1). :meth:`inform` is
    output-only and always safe to call.
    """

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        """Yes/no confirmation; ``None`` means no answer was given."""
        ...

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        """Prompt for a bounded integer; ``None`` means no answer was given."""
        ...

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        """Prompt for a bounded float; ``None`` means no answer was given."""
        ...

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        """Prompt to pick an option index; ``None`` means no answer was given."""
        ...

    def inform(self, message: str) -> None:
        """Emit an informational message (no answer expected)."""
        ...


class LoadCalculator(Protocol):
    """The pluggable methodology contract (Req 1.1).

    A methodology declares its identity, the sports it supports, and the athlete
    inputs it requires, then computes a typed :data:`LoadOutcome` for an
    activity. Implementations are registered by identifier; new methodologies
    slot in without touching core code.
    """

    calculator_id: str
    """Stable, unique methodology identifier used for registry addressing."""
    display_name: str
    """Human-readable methodology name for prompts and rendered results."""
    supported_modalities: frozenset[Modality]
    """The movement modalities this methodology scores; others get ``Unsupported``."""

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        """The athlete inputs this methodology declares it needs (Req 1.1)."""
        ...

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        """Compute a typed load outcome for ``activity``.

        Preconditions: the engine has already verified this calculator supports
        the activity's modality and has run the generic prompt flow for the
        declared missing fields. A calculator may still return
        :class:`MissingInputs` (e.g. a non-interactive pass left a required
        field absent). ``context`` is the only route to the resolved ``[load]``
        configuration and the activity's own recorded date (Req 1.12) -- a
        calculator opens no settings file and reads no clock itself.

        Postconditions: never raises for missing or malformed athlete data --
        it returns a typed outcome instead; and never returns :class:`Computed`
        without the user confirmation the methodology requires (a non-interactive
        or declined confirmation yields :class:`NotComputed`), so no load value
        is ever fabricated (Req 1.4, 9.1). Where a value is derived from a
        recorded sample stream (e.g. heart rate, power, cadence samples), that
        derivation must be an aggregate over the samples *actually recorded* --
        never treating missing samples as zeros (Req 9.2; see
        ``docs/contributing-calculators.md`` "Aggregating over recorded
        samples" for the calculator-author-facing version of this rule).
        This obligation is stated here as a documented postcondition and is
        not enforced by this module; enforcing it for a given methodology's
        math is that methodology's own requirement.
        """
        ...


def supports_activity(calculator: LoadCalculator, activity: Activity) -> bool:
    """Does ``calculator`` cover ``activity``? The one place the training-load
    layer asks this question (Amendment 3, Req 1.14).

    Prompt-free and athlete-data-free: callers ask this before collecting any
    athlete input, so a methodology that declines never causes a prompt. When
    ``calculator`` defines its own ``supports(activity) -> bool`` (an
    additive, off-protocol capability -- :class:`LoadCalculator` declares no
    such member, mirroring how ``athlete_field_hints`` is read elsewhere in
    this layer), that answer is used. Otherwise the answer is the modality
    membership test :attr:`LoadCalculator.supported_modalities` already
    declares, so a calculator that writes nothing more specific answers this
    for free, with no subclassing and no registration-time mutation of the
    calculator object.

    A calculator that does define ``supports`` must only ever *narrow* its
    declared modalities, never widen them -- a calculator the modality filter
    drops can never be reinstated here. This is a documented obligation on
    every ``supports`` implementation, not mechanically enforced by this
    function, and it is what lets the registry's modality prefilter and this
    question compose safely (design.md ~1183): task 3.2's arbitration and
    task 4.1's engine gate both call this function rather than dispatching to
    ``calculator.supports`` directly, so this is the single seam either of
    them needs to change if the mechanism ever does.
    """
    custom = getattr(calculator, "supports", None)
    if callable(custom):
        return bool(custom(activity))
    return activity.modality in calculator.supported_modalities

"""Benchmark value vocabulary (design: BenchmarkVocabulary).

This is a top-level **leaf** module: it owns the vocabulary of what an athlete
benchmark *is* -- the quantities that can be recorded, which of them are
scoped to a discipline versus to the athlete as a whole, which of them are
whole-number quantities, and the immutable :class:`Benchmark` value that
carries one dated measurement. This task also lands the parser
(:func:`parse_benchmarks`) and its inverse serializer
(:func:`benchmarks_to_document`) for the decoded ``athlete.toml``
``[benchmarks]`` region; date-aware selection and staleness computation are
added by a later task in this module.

The module performs **no file I/O** and imports no ``fitdocs.load.*`` module --
dependency direction stays ``cli -> engine/prompts -> profile ->
benchmarks/athlete -> model`` (design: Allowed Dependencies). Discipline
values reuse the shipped :class:`fitdocs.Sport` vocabulary rather than
defining a parallel one; the reserved :data:`ATHLETE_SCOPE` token never
collides with a ``Sport`` value, so the two vocabularies cannot be confused
for one another.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Final

from fitdocs import Sport


class BenchmarkError(Exception):
    """A benchmark entry is malformed or violates a vocabulary invariant.

    A plain domain error: callers above this leaf module (``athlete.py``,
    ``load/profile.py``) re-raise it in their own file-level voice, exactly as
    ``athlete.py`` re-raises ``ZoneSpec``'s ``ValueError`` today. The message
    names the offending discipline, quantity or value so a hand-edited file
    can be corrected without fitdocs installed.
    """


class BenchmarkKind(StrEnum):
    """A benchmark quantity. The value is the TOML key and carries its unit."""

    FTP_WATTS = "ftp_watts"
    LTHR_BPM = "lthr_bpm"
    THRESHOLD_PACE_S_PER_KM = "threshold_pace_s_per_km"
    MAX_HR_BPM = "max_hr_bpm"
    RESTING_HR_BPM = "resting_hr_bpm"


ATHLETE_SCOPE: Final[str] = "athlete"
"""Reserved discipline-table name for whole-athlete quantities. No ``Sport``
value lowercases to this token, so the two vocabularies cannot collide."""

DISCIPLINE_SCOPED: Final[frozenset[BenchmarkKind]] = frozenset(
    {
        BenchmarkKind.FTP_WATTS,
        BenchmarkKind.LTHR_BPM,
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
    }
)
"""Quantities scoped to a named discipline rather than to the athlete as a
whole: threshold power, threshold heart rate and threshold pace."""

ATHLETE_SCOPED: Final[frozenset[BenchmarkKind]] = frozenset(
    {BenchmarkKind.MAX_HR_BPM, BenchmarkKind.RESTING_HR_BPM}
)
"""Quantities scoped to the athlete as a whole: maximum and resting heart rate."""

INTEGRAL_KINDS: Final[frozenset[BenchmarkKind]] = frozenset(
    {
        BenchmarkKind.LTHR_BPM,
        BenchmarkKind.MAX_HR_BPM,
        BenchmarkKind.RESTING_HR_BPM,
    }
)
"""Quantities recorded in whole beats per minute; a fractional value is
rejected rather than rounded or truncated."""


@dataclass(frozen=True)
class Benchmark:
    """One dated measurement of an athlete's threshold value.

    Immutable. Natural key: ``(discipline, kind, measured_on)`` -- validated
    unique within a parsed set by the parser this leaf's next task adds.
    ``discipline`` is ``None`` exactly when ``kind`` is in
    :data:`ATHLETE_SCOPED`; ``None`` otherwise means an unset discipline is a
    programming error, checked by the selection layer, not by this value type.
    """

    kind: BenchmarkKind
    discipline: Sport | None
    value: float
    measured_on: date
    note: str | None = None
    applies_from: date | None = None
    """*Amendment 1.* The athlete's declaration that this measurement also
    stands in for activities dated on or after this date which no
    earlier-measured entry covers. Trailing and defaulted so every existing
    keyword construction is unchanged. ``None`` (the default) means the
    entry applies from its own ``measured_on`` only, exactly as before;
    when set, it is a bare calendar date no later than ``measured_on``
    (enforced by the parser, not by this value type)."""


@dataclass(frozen=True)
class BenchmarkSet:
    """An immutable, validated collection of benchmark entries.

    Task 1.2 lands the container the parser returns. Task 1.3 (design:
    BenchmarkSelection) adds date-aware applicability (:meth:`applicable`)
    and undated presence (:meth:`has`): pure lookups that never fall back
    across scope or discipline and never fabricate a value. *Amendment 1*:
    the tool itself still never applies a later measurement on its own --
    :meth:`applicable` only ever returns an entry measured after the query
    date when the athlete's own ``applies_from`` declaration on that entry
    reaches back to or before the query date (3.10).

    Determinism (3.8) does **not** rest on ``entries`` being held in any
    particular canonical order -- the parser rejects a duplicate
    ``(discipline, kind, measured_on)`` key (2.7), so at most one entry can
    ever match a given ``(kind, discipline, measured_on)`` triple, and
    ``applicable`` picks the greatest ``measured_on`` among the entries that
    qualify by an unambiguous ``max`` over that key (tier 1) or the least
    ``measured_on`` among the ``applies_from``-qualifying entries (tier 2,
    Amendment 1) -- both unambiguous for the same reason. The result is
    therefore independent of stored order by construction:
    ``test_applicable_repeated_calls_stay_equal_regardless_of_entry_order``
    proves this for tier 1 and
    ``test_applicable_tier2_repeated_calls_stay_equal_regardless_of_entry_order``
    proves it for tier 2, each with candidates whose stored order and
    selection order disagree so a stored-order-dependent implementation
    (e.g. "last/first in iteration order") would fail them.
    """

    entries: tuple[Benchmark, ...]

    def applicable(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date
    ) -> Benchmark | None:
        """Return the benchmark applicable to an activity on ``on``.

        Two-tier (design: BenchmarkSelection; Amendment 1, 3.10):

        Tier 1 (3.1-3.4): among entries for the requested ``(kind,
        discipline)`` whose ``measured_on`` is on or before ``on``, returns
        the one with the latest such date. A tier-1 entry always wins over
        a tier-2 one, whatever their values -- the measurement-system case
        (a Stryd FTP must not rescale Apple Watch runs) is preserved because
        an entry measured on or before the activity always beats a
        retroactive one.

        Tier 2 (3.3 revised, 3.10, 3.11): consulted only when tier 1 finds
        nothing. Among the same ``(kind, discipline)`` entries whose
        ``applies_from`` is not ``None`` and is on or before ``on``, returns
        the one with the *smallest* ``measured_on`` -- the measurement
        closest after the activity. The tier-2 minimum is unambiguous because
        ``(discipline, kind, measured_on)`` is unique within a parsed set.

        Returns ``None`` when neither tier qualifies -- whether because no
        entry exists at all or because every recorded entry falls after
        ``on`` with no ``applies_from`` reaching back far enough. An entry
        carrying neither a qualifying ``measured_on`` nor a qualifying
        ``applies_from`` is never returned. Never substitutes an entry from
        another discipline, from the athlete-wide scope, or any default
        (9.5). The tool itself never applies a later measurement on its
        own; only the athlete's explicit, per-entry ``applies_from``
        declaration does.

        ``discipline`` must agree with ``kind``'s scope (``None`` exactly for
        an :data:`ATHLETE_SCOPED` quantity); a mismatch is a programming
        error and raises :class:`ValueError` rather than silently returning
        nothing or borrowing another scope's entry.
        """
        _check_selection_scope(kind, discipline)
        candidates = [
            entry
            for entry in self.entries
            if entry.kind is kind and entry.discipline == discipline
        ]
        qualifying = [entry for entry in candidates if entry.measured_on <= on]
        if qualifying:
            return max(qualifying, key=lambda entry: entry.measured_on)

        retroactive = [
            entry
            for entry in candidates
            if entry.applies_from is not None and entry.applies_from <= on
        ]
        if not retroactive:
            return None
        return min(retroactive, key=lambda entry: entry.measured_on)

    def has(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        """Report whether any entry for ``(kind, discipline)`` is on file at
        all, ignoring dates entirely (3.5) -- so a caller can distinguish
        "no benchmark of this kind is on file" from "one exists but none
        applies yet".

        Same scope precondition as :meth:`applicable`.
        """
        _check_selection_scope(kind, discipline)
        return any(
            entry.kind is kind and entry.discipline == discipline
            for entry in self.entries
        )


def _check_selection_scope(kind: BenchmarkKind, discipline: Sport | None) -> None:
    """Enforce ``BenchmarkSet.applicable``/``has``'s scope precondition.

    Unlike ``_check_scope`` (below), which rejects a *parsed file* entry
    recorded in the wrong scope with a domain :class:`BenchmarkError`, this
    guards a *caller-supplied query*: passing a ``discipline`` that disagrees
    with ``kind``'s scope is a programming error in the calling code, not
    malformed data, so it raises the ordinary :class:`ValueError` design
    specifies (design: BenchmarkSelection preconditions) rather than
    ``BenchmarkError``.
    """
    if kind in ATHLETE_SCOPED and discipline is not None:
        raise ValueError(
            f"{kind.value} is an athlete-wide quantity; query it with "
            f"discipline=None, not discipline={discipline!r}"
        )
    if kind in DISCIPLINE_SCOPED and discipline is None:
        raise ValueError(
            f"{kind.value} is a discipline-scoped quantity; query it with an "
            f"explicit discipline, not discipline=None"
        )


_SCOPE_BY_LOWER_SPORT: Final[dict[str, Sport]] = {
    sport.value.lower(): sport for sport in Sport
}
"""Case-insensitive lookup from a discipline table name to its ``Sport``.

Ambiguity 1 (discipline-table case sensitivity): the design's own physical
data model (`athlete.toml` example) spells discipline tables lowercase
(``[[benchmarks.run.ftp_watts]]``) right alongside the lowercase reserved
``athlete`` scope, in a file requirement 1.1 requires to stay hand-editable.
A strict ``Sport(value)`` lookup would force the awkward
``[[benchmarks.Run.ftp_watts]]`` instead. Hand-editability wins: the scope
token is matched case-insensitively against ``Sport``'s own spellings (and
against the reserved ``athlete`` token), so both ``run`` and ``Run`` resolve
to ``Sport.RUN``. An unrecognized name -- in any case -- is still rejected
per 2.5.
"""


def _resolve_scope(scope_name: str, *, path: str) -> Sport | None:
    """Resolve a decoded discipline-table name to a ``Sport`` or ``None``.

    ``None`` denotes the reserved athlete-wide scope. Matching is
    case-insensitive (see ``_SCOPE_BY_LOWER_SPORT``'s docstring); an
    unrecognized name raises naming the offending value and listing the
    recognized ones (2.5).
    """
    lowered = scope_name.lower()
    if lowered == ATHLETE_SCOPE:
        return None
    if lowered in _SCOPE_BY_LOWER_SPORT:
        return _SCOPE_BY_LOWER_SPORT[lowered]
    recognized = ", ".join(sorted({ATHLETE_SCOPE, *_SCOPE_BY_LOWER_SPORT}))
    raise BenchmarkError(
        f"{path}: {scope_name!r} is not a recognized discipline; "
        f"recognized names are {recognized}"
    )


def _check_scope(kind: BenchmarkKind, discipline: Sport | None, *, path: str) -> None:
    """Reject a quantity recorded in the wrong scope (2.6)."""
    if kind in ATHLETE_SCOPED and discipline is not None:
        raise BenchmarkError(
            f"{path}: {kind.value} is an athlete-wide quantity and must be "
            f"recorded under the {ATHLETE_SCOPE!r} scope, not a discipline"
        )
    if kind in DISCIPLINE_SCOPED and discipline is None:
        raise BenchmarkError(
            f"{path}: {kind.value} is a discipline-scoped quantity and must be "
            f"recorded under a named discipline, not the {ATHLETE_SCOPE!r} scope"
        )


def _validate_value(raw: object, kind: BenchmarkKind, *, path: str) -> float:
    """Validate one entry's ``value`` (2.1, 2.2, 2.3).

    Ambiguity 2 (``value: float`` vs. "stored as ``int``"): design.md's
    service interface annotates ``Benchmark.value: float`` but its invariants
    list states "every integral-kind value is a whole number stored as
    ``int``". Both are honored: the annotation stays ``float`` (Python's
    numeric tower accepts ``int`` there), but the value actually *stored* for
    an :data:`INTEGRAL_KINDS` member is converted to ``int`` here, so the
    serializer round-trips ``190`` rather than emitting a synthetic ``190.0``
    the user never wrote. A non-integral quantity keeps whatever numeric type
    TOML decoded (``int`` or ``float``) unchanged.
    """
    if raw is None:
        raise BenchmarkError(f"{path}.value is missing")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise BenchmarkError(
            f"{path}.value must be a number, got {raw!r} ({type(raw).__name__})"
        )
    numeric = float(raw)
    if not math.isfinite(numeric) or numeric <= 0:
        raise BenchmarkError(
            f"{path}.value must be a finite, positive number, got {raw!r}"
        )
    if kind in INTEGRAL_KINDS:
        if not numeric.is_integer():
            raise BenchmarkError(
                f"{path}.value ({kind.value}) must be a whole number of beats "
                f"per minute, got {raw!r}"
            )
        return int(numeric)
    return raw


def _validate_measured_on(raw: object, *, path: str) -> date:
    """Validate one entry's ``measured_on`` (2.4).

    ``datetime.datetime`` subclasses ``datetime.date``, so an
    ``isinstance(raw, date)`` check would silently accept a date-time. The
    check is therefore the stricter ``type(raw) is date``.
    """
    if raw is None:
        raise BenchmarkError(f"{path}.measured_on is missing")
    if type(raw) is not date:
        raise BenchmarkError(
            f"{path}.measured_on must be a bare calendar date with no time "
            f"or time zone component, got {raw!r} ({type(raw).__name__})"
        )
    return raw


def _validate_applies_from(raw: object, measured_on: date, *, path: str) -> date | None:
    """Validate one entry's optional ``applies_from`` (Amendment 1: 1.12, 2.11).

    Absent (``None``) is accepted -- the entry then applies from its own
    ``measured_on`` only, exactly as before. When present it is held to
    exactly ``measured_on``'s bare-date strictness (``type(raw) is date``,
    so a ``datetime`` -- which subclasses ``date`` -- is rejected even
    though it would pass a looser ``isinstance`` check), and it must not
    fall *after* ``measured_on``; ``applies_from == measured_on`` is
    accepted and behaves as if absent.
    """
    if raw is None:
        return None
    if type(raw) is not date:
        raise BenchmarkError(
            f"{path}.applies_from must be a bare calendar date with no time "
            f"or time zone component, got {raw!r} ({type(raw).__name__})"
        )
    if raw > measured_on:
        raise BenchmarkError(
            f"{path}.applies_from ({raw.isoformat()}) must not fall after "
            f"{path}.measured_on ({measured_on.isoformat()})"
        )
    return raw


def _validate_note(raw: object, *, path: str) -> str | None:
    """Validate one entry's optional ``note``."""
    if raw is None or isinstance(raw, str):
        return raw
    raise BenchmarkError(
        f"{path}.note must be a string, got {raw!r} ({type(raw).__name__})"
    )


def parse_benchmarks(document: Mapping[str, object]) -> BenchmarkSet:
    """Parse the decoded ``[benchmarks]`` region of ``athlete.toml``.

    ``document`` is the already-decoded top-level mapping; only its
    ``benchmarks`` key is read. An absent region yields an empty set (1.9,
    1.10). Every entry is validated; malformed input raises
    :class:`BenchmarkError` naming the offending discipline, quantity or
    value (2.1-2.8) rather than being dropped, coerced or guessed (2.10).
    Unrecognized keys inside an entry table, and unrecognized quantity names
    under a recognized discipline table, are ignored for forward
    compatibility (1.10); an unrecognized *discipline* table is rejected
    (2.5) because it cannot be safely assumed to be a future addition.
    """
    raw = document.get("benchmarks")
    if raw is None:
        return BenchmarkSet(entries=())
    if not isinstance(raw, Mapping):
        raise BenchmarkError(
            f"benchmarks must be a table, got {raw!r} ({type(raw).__name__})"
        )

    entries: list[Benchmark] = []
    seen: set[tuple[Sport | None, BenchmarkKind, date]] = set()

    for scope_name, scope_table in raw.items():
        scope_path = f"benchmarks.{scope_name}"
        discipline = _resolve_scope(str(scope_name), path=scope_path)
        if not isinstance(scope_table, Mapping):
            raise BenchmarkError(
                f"{scope_path} must be a table, got {scope_table!r} "
                f"({type(scope_table).__name__})"
            )

        for kind_name, kind_entries in scope_table.items():
            try:
                kind = BenchmarkKind(kind_name)
            except ValueError:
                # Unrecognized quantity name: forward-compat, ignored (1.10).
                continue

            kind_path = f"{scope_path}.{kind_name}"
            _check_scope(kind, discipline, path=kind_path)

            if not isinstance(kind_entries, list):
                raise BenchmarkError(
                    f"{kind_path} must be an array of tables, got "
                    f"{kind_entries!r} ({type(kind_entries).__name__})"
                )

            for index, entry in enumerate(kind_entries):
                entry_path = f"{kind_path}[{index}]"
                if not isinstance(entry, Mapping):
                    raise BenchmarkError(
                        f"{entry_path} must be a table, got {entry!r} "
                        f"({type(entry).__name__})"
                    )

                value = _validate_value(entry.get("value"), kind, path=entry_path)
                measured_on = _validate_measured_on(
                    entry.get("measured_on"), path=entry_path
                )
                note = _validate_note(entry.get("note"), path=entry_path)
                applies_from = _validate_applies_from(
                    entry.get("applies_from"), measured_on, path=entry_path
                )

                key = (discipline, kind, measured_on)
                if key in seen:
                    raise BenchmarkError(
                        f"{kind_path} has more than one entry measured on "
                        f"{measured_on.isoformat()}"
                    )
                seen.add(key)

                entries.append(
                    Benchmark(
                        kind=kind,
                        discipline=discipline,
                        value=value,
                        measured_on=measured_on,
                        note=note,
                        applies_from=applies_from,
                    )
                )

    return BenchmarkSet(entries=tuple(entries))


@dataclass(frozen=True)
class BenchmarkAge:
    """The verdict ``(age_days, window_days, is_stale)`` for one benchmark
    evaluated against one activity date (design: StalenessCalculation).

    Derived, never stored -- computed fresh by :func:`benchmark_age` for each
    query rather than carried on :class:`Benchmark`.

    *Amendment 1 (4.6 revised):* ``age_days`` is negative when the benchmark
    was measured *after* the activity -- the legitimate tier-2 (retroactive)
    case, not an error condition. A caller reads the sign directly as the
    arithmetic fact "measured after this activity"; it is not a sentinel to
    special-case. A negative ``age_days`` is never stale, since it can never
    exceed a positive ``window_days``.
    """

    age_days: int
    window_days: int
    is_stale: bool


def benchmark_age(
    *, activity_date: date, measured_on: date, window_days: int
) -> BenchmarkAge:
    """Compute a benchmark's age and staleness verdict as of an activity date.

    Pure: depends only on ``activity_date``, ``measured_on`` and
    ``window_days`` (4.5) -- reads no file and consults no clock, so
    regenerating a document for a past activity reproduces the verdict it
    got originally (4.3). Touches no :class:`Benchmark` value; it reports a
    fact, never adjusts one (4.7).

    ``age_days`` is ``(activity_date - measured_on).days`` (4.1) and
    ``is_stale`` is ``age_days > window_days`` (4.2): an age equal to the
    window is current, one day beyond it is stale. Both the age and the
    window accompany the verdict (4.4).

    *Amendment 1 (4.6 revised):* ``measured_on > activity_date`` no longer
    raises. Selection's tier-2 fallback (:meth:`BenchmarkSet.applicable`)
    legitimately yields a benchmark measured after the activity it applies
    to when the athlete declared it retroactive, and that entry must still
    reach staleness. In that case ``age_days`` is **negative** and
    ``is_stale`` is ``False`` (a negative age is never greater than a
    positive window) -- the sign of the age is the arithmetic fact a caller
    reads as "measured after this activity", not a sentinel value. A
    ``window_days`` below one day is a programming error and still raises.
    """
    if window_days < 1:
        raise ValueError(f"window_days must be at least 1, got {window_days!r}")

    age_days = (activity_date - measured_on).days
    return BenchmarkAge(
        age_days=age_days,
        window_days=window_days,
        is_stale=age_days > window_days,
    )


def benchmarks_to_document(entries: Sequence[Benchmark]) -> dict[str, object]:
    """Serialize benchmark entries into the ``{"benchmarks": ...}`` region.

    The inverse of :func:`parse_benchmarks`. Entries are grouped by scope
    (the reserved athlete-wide token or a lowercased discipline name -- the
    hand-editable spelling ambiguity 1 chose) and quantity, and each group is
    emitted in ascending ``measured_on`` order (6.6).

    ``note`` and ``applies_from`` are emitted only when present -- never as an
    explicit ``None``. That omission is load-bearing for the profile store's
    rewrite merge (``fitdocs.load.profile._merge_benchmarks_document``), which
    overlays the emitted record onto the existing raw entry: an omitted key
    leaves an existing value untouched, an explicit ``None`` would erase it.
    """
    grouped: dict[str, dict[str, list[dict[str, object]]]] = {}
    for entry in sorted(entries, key=lambda benchmark: benchmark.measured_on):
        scope_key = (
            ATHLETE_SCOPE
            if entry.discipline is None
            else entry.discipline.value.lower()
        )
        kind_table = grouped.setdefault(scope_key, {})
        kind_list = kind_table.setdefault(entry.kind.value, [])
        record: dict[str, object] = {
            "value": entry.value,
            "measured_on": entry.measured_on,
        }
        if entry.applies_from is not None:
            record["applies_from"] = entry.applies_from
        if entry.note is not None:
            record["note"] = entry.note
        kind_list.append(record)

    return {"benchmarks": grouped}

"""Strength set extraction: ``set_mesgs`` -> :class:`StrengthSet` tuple (Req 6.1-6.5).

:func:`extract_sets` maps each decoded ``set`` message onto the model's
:class:`StrengthSet` contract, one entry per message in the RECORDED order
(Req 6.1). Every recorded field is read verbatim by FIT key with ``dict.get`` so
an unrecorded field becomes ``None`` while a recorded ``0`` -- notably a
bodyweight set's ``weight=0.0`` -- is preserved as a real zero, never dropped by
truthiness (Req 6.2, 12.3). ``start_time`` is converted from raw FIT-epoch
seconds with the shared :func:`fitdocs.model.fit_datetime` helper.

Exercise-name resolution has two layers (Req 6.3):

* **Primary (free recordings)** -- standard watch files carry ``category`` (an
  exercise-category string; a FIT array whose first entry is used) and
  ``category_subtype`` (a raw int; likewise the first array entry). The exercise
  name is looked up in the SDK Profile table
  ``Profile['types'][f'{category}_exercise_name'][subtype]``.
* **Optional refinement (structured workouts)** -- ``exercise_title`` messages
  exist only for structured workouts. When a set's ``wkt_step_index`` matches an
  ``exercise_title``'s ``message_index``, that title's ``wkt_step_name`` wins over
  the Profile lookup. Free recordings carry no such messages and never depend on
  them.

Resolution failure at ANY step -- an absent or unknown category, an absent
subtype, a category with no ``*_exercise_name`` table, or a subtype missing from
that table -- leaves ``exercise_name = None``; the name is never inferred,
defaulted, or fabricated (Req 6.3, 6.5). Activities without any set messages
yield an EMPTY tuple without error -- the normal case for the user's real watch
files, whose strength recordings carry no ``set_mesgs`` at all (Req 6.4).

This module depends only on :mod:`fitdocs.model`, the standard library, and the
SDK Profile lookup tables; it never touches the SDK decoder, the metrics layer,
or sibling ingest modules.
"""

from __future__ import annotations

from datetime import datetime

# garmin-fit-sdk ships no type stubs / py.typed marker; ignore the untyped
# import here -- ``Profile`` supplies the per-category exercise-name lookup tables.
from garmin_fit_sdk import Profile  # type: ignore[import-untyped]

from fitdocs.ingest._fields import float_or_none, int_or_none, str_or_none
from fitdocs.model import StrengthSet, fit_datetime

# The SDK Profile's ``types`` table holds one ``{category}_exercise_name`` mapping
# (raw int subtype -> name string) per exercise category; it is a plain nested dict.
_EXERCISE_NAME_TYPES = Profile["types"]


def extract_sets(
    set_mesgs: list[dict[str, object]],
    exercise_title_mesgs: list[dict[str, object]],
) -> tuple[StrengthSet, ...]:
    """Map ``set_mesgs`` onto :class:`StrengthSet` in recorded order (Req 6.1-6.5).

    ``set_mesgs`` is the decoded ``set_mesgs`` list; ``exercise_title_mesgs`` is
    the decoded ``exercise_title_mesgs`` list (empty for free watch recordings).
    Returns one :class:`StrengthSet` per set message in the ORIGINAL recorded
    order. Every unrecorded field is ``None`` and recorded zeros are preserved
    (Req 6.2, 12.3); the exercise name resolves via the SDK Profile lookup,
    refined by a matching ``exercise_title`` when one is present, and stays
    ``None`` when unresolvable (Req 6.3, 6.5). An empty ``set_mesgs`` yields an
    empty tuple with no error (Req 6.4).
    """
    titles_by_index = _titles_by_index(exercise_title_mesgs)
    return tuple(_build_set(mesg, titles_by_index) for mesg in set_mesgs)


def _build_set(mesg: dict[str, object], titles_by_index: dict[int, str]) -> StrengthSet:
    """Map one set message onto a :class:`StrengthSet`.

    Recorded fields are read verbatim by FIT key: absent keys become ``None`` and
    recorded zeros (bodyweight ``weight=0.0``) are preserved (Req 6.2, 12.3). The
    exercise name resolves from the set's category/subtype, with a matching
    ``exercise_title`` overriding the Profile result when present (Req 6.3).
    """
    category = _category(mesg)
    subtype = _subtype(mesg)
    return StrengthSet(
        set_type=str_or_none(mesg.get("set_type")),
        start_time=_start_time(mesg),
        duration_s=float_or_none(mesg.get("duration")),
        repetitions=int_or_none(mesg.get("repetitions")),
        weight_kg=float_or_none(mesg.get("weight")),
        category=category,
        exercise_name=_resolve_exercise_name(
            category, subtype, mesg.get("wkt_step_index"), titles_by_index
        ),
        message_index=int_or_none(mesg.get("message_index")),
    )


def _titles_by_index(
    exercise_title_mesgs: list[dict[str, object]],
) -> dict[int, str]:
    """Index ``exercise_title`` messages by ``message_index`` -> ``wkt_step_name``.

    Only titles carrying both an integer ``message_index`` and a string
    ``wkt_step_name`` contribute; the mapping is empty for free recordings, which
    carry no ``exercise_title`` messages at all.
    """
    titles: dict[int, str] = {}
    for title in exercise_title_mesgs:
        index = title.get("message_index")
        name = title.get("wkt_step_name")
        if isinstance(index, int) and isinstance(name, str):
            titles[index] = name
    return titles


def _resolve_exercise_name(
    category: str | None,
    subtype: int | None,
    wkt_step_index: object,
    titles_by_index: dict[int, str],
) -> str | None:
    """Resolve a set's exercise name, or ``None`` when unresolvable (Req 6.3, 6.5).

    A matching ``exercise_title`` (its ``message_index`` equal to the set's
    ``wkt_step_index``) wins over the Profile lookup. Otherwise the name comes from
    ``Profile['types'][f'{category}_exercise_name'][subtype]``. Any missing input,
    absent table, or absent subtype entry yields ``None`` -- never a guess.
    """
    # Structured-workout refinement: a matching exercise_title name wins (Req 6.3).
    if isinstance(wkt_step_index, int):
        refined = titles_by_index.get(wkt_step_index)
        if refined is not None:
            return refined

    # Primary path: the SDK Profile category/subtype lookup (free recordings).
    if category is None or subtype is None:
        return None
    table = _EXERCISE_NAME_TYPES.get(f"{category}_exercise_name")
    if not isinstance(table, dict):
        return None
    name = table.get(subtype)
    return name if isinstance(name, str) else None


def _category(mesg: dict[str, object]) -> str | None:
    """The exercise-category string: first array entry or scalar, else ``None``.

    FIT records ``category`` as an array; the SDK collapses a single entry to a
    scalar. Either way the first/only entry is used when it is a string (Req 6.2);
    an absent, empty, or non-string category yields ``None``.
    """
    value = _first(mesg.get("category"))
    return value if isinstance(value, str) else None


def _subtype(mesg: dict[str, object]) -> int | None:
    """The exercise-category subtype: first array entry or scalar int, else ``None``.

    As with ``category``, ``category_subtype`` is a FIT array the SDK may collapse
    to a scalar; the first/only integer entry is used, and anything absent or
    non-integer yields ``None`` (no Profile lookup key can be built).
    """
    value = _first(mesg.get("category_subtype"))
    return value if isinstance(value, int) else None


def _first(value: object) -> object:
    """First entry of a FIT array field, the scalar itself, or ``None`` if empty."""
    if isinstance(value, list | tuple):
        return value[0] if value else None
    return value


def _start_time(mesg: dict[str, object]) -> datetime | None:
    """Convert a set's raw FIT-epoch ``start_time`` to a UTC datetime, or ``None``.

    With the decoder's ``convert_datetimes_to_dates=False``, ``start_time`` arrives
    as raw integer seconds since the FIT epoch; an absent start stays ``None``
    (Req 2.4).
    """
    value = mesg.get("start_time")
    if value is None:
        return None
    if isinstance(value, int):
        return fit_datetime(value)
    raise TypeError(f"expected an integer FIT timestamp, got {type(value).__name__}")

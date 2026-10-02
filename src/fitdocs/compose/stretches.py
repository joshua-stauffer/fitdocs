"""Whole-second instants and stretches cut at the pauses of either file.

Pure: no I/O, no clock. A sample's instant is its activity's recorded start
plus its offset as a POSIX second; a sample without a whole-second instant has
none (``None``) and is never joined. Stretches of an extra's samples are cut
where either the extra or the base resumes after a gap (channel-merge Req 3.1,
3.2; design.md § Stretches).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from fitdocs.model import Activity

PAUSE_GAP_S: Final[int] = 1
"""A step of more than this many seconds between samples is a pause."""


def instants(activity: Activity) -> tuple[int | None, ...]:
    """Per sample, the POSIX second of ``start_time + time_s[i]``.

    ``None`` for every sample when no start is recorded, and for a sample whose
    instant is not a whole second.
    """
    offsets = activity.samples.time_s
    start = activity.start_time
    if start is None:
        return (None,) * len(offsets)
    base = start.timestamp()
    out: list[int | None] = []
    for offset in offsets:
        total = base + offset
        whole = int(total)
        out.append(whole if whole == total else None)
    return tuple(out)


def resume_instants(instants: Sequence[int | None]) -> frozenset[int]:
    """Each instant that follows its nearest earlier instant by more than
    ``PAUSE_GAP_S``: the first instant after a pause."""
    resumes: set[int] = set()
    previous: int | None = None
    for instant in instants:
        if instant is None:
            continue
        if previous is not None and instant - previous > PAUSE_GAP_S:
            resumes.add(instant)
        previous = instant
    return frozenset(resumes)


def split_stretches(
    extra: Sequence[int | None], base: Sequence[int | None]
) -> tuple[range, ...]:
    """Index ranges over ``extra``, one per stretch, in file order.

    A sample at instant ``t`` belongs to the stretch numbered by how many cut
    points (the resume instants of either file) are at or before ``t``. Each
    range runs from the stretch's first to its last member; a sample without an
    instant belongs to none, and a stretch with no member yields no range.
    """
    cuts = sorted(resume_instants(extra) | resume_instants(base))
    first: dict[int, int] = {}
    last: dict[int, int] = {}
    for index, instant in enumerate(extra):
        if instant is None:
            continue
        number = sum(1 for cut in cuts if cut <= instant)
        first.setdefault(number, index)
        last[number] = index
    return tuple(range(first[n], last[n] + 1) for n in sorted(first))

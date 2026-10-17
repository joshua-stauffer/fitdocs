"""Rolling maximum-heart-rate evidence from sustained session peaks."""

from collections.abc import Collection, Sequence
from datetime import date, timedelta
from math import floor

from . import sources
from .types import Evidence, SessionPeak


def max_evidence(
    sessions: Sequence[SessionPeak], *, hand_dates: Collection[date] = ()
) -> tuple[Evidence, ...]:
    days = sorted({session.day for session in sessions})
    evidence: list[Evidence] = []
    for day in days:
        start = day - timedelta(days=sources.MAX_WINDOW_DAYS.value - 1)
        floor_day = max((hand for hand in hand_dates if hand < day), default=None)
        if floor_day is not None:
            start = max(start, floor_day + timedelta(days=1))
        window = [session for session in sessions if start <= session.day <= day]
        if len(window) < sources.MAX_TOP_SESSIONS.value:
            continue
        top = sorted(
            window,
            key=lambda session: (-session.peak_bpm, session.day, session.document),
        )[: sources.MAX_TOP_SESSIONS.value]
        median = top[1]
        peaks = ", ".join(f"{session.peak_bpm:.1f}" for session in top)
        evidence.append(
            Evidence(
                day=day,
                value=floor(median.peak_bpm + sources.ROUNDING_HALF_OFFSET.value),
                key="workouts",
                document=median.document,
                series=None,
                inputs=(
                    "median of the three highest "
                    f"{sources.MAX_PEAK_WINDOW_S.value}-second "
                    f"sustained peaks ({peaks} bpm) among {len(window)} sessions "
                    f"dated {start.isoformat()} to {day.isoformat()}"
                ),
                summary=(
                    f"workout heart rate, {sources.MAX_WINDOW_DAYS.value} days "
                    f"ending {day.isoformat()}"
                ),
            )
        )
    return tuple(evidence)

"""Rolling maximum-heart-rate evidence from sustained session peaks."""

from collections.abc import Sequence
from datetime import timedelta
from math import floor

from . import sources
from .types import Evidence, SessionPeak


def max_evidence(sessions: Sequence[SessionPeak]) -> tuple[Evidence, ...]:
    days = sorted(
        {
            day
            for session in sessions
            for day in (
                session.day,
                session.day + timedelta(days=sources.MAX_WINDOW_DAYS.value),
            )
        }
    )
    evidence: list[Evidence] = []
    for day in days:
        start = day - timedelta(days=sources.MAX_WINDOW_DAYS.value - 1)
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

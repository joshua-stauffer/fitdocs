"""A session's sustained peak from recorded heart-rate samples."""

from __future__ import annotations

import fitdocs.load.qa.cadence as cadence
from fitdocs.load.qa.types import FlagSettings
from fitdocs.model import Modality, Samples

from . import sources
from .types import NoEvidenceReason


def _stretch_peak(stretch: list[tuple[float, float]]) -> float | None:
    times = [t for t, _ in stretch]
    hrs = [hr for _, hr in stretch]
    window = sources.MAX_PEAK_WINDOW_S.value
    if not times or times[-1] - times[0] < window:
        return None

    areas = [0.0]
    for i in range(len(times) - 1):
        areas.append(areas[-1] + (times[i + 1] - times[i]) * hrs[i])

    best = 0.0
    right = 0
    for left, start in enumerate(times):
        end = start + window
        if end > times[-1]:
            break
        while right + 1 < len(times) and times[right + 1] <= end:
            right += 1
        end_area = areas[right] + (end - times[right]) * hrs[right]
        best = max(best, (end_area - areas[left]) / window)

    left = 0
    for right, end in enumerate(times):
        start = end - window
        if start < times[0]:
            continue
        while left + 1 < len(times) and times[left + 1] <= start:
            left += 1
        start_area = areas[left] + (start - times[left]) * hrs[left]
        best = max(best, (areas[right] - start_area) / window)
    return best


def session_peak(
    samples: Samples, *, modality: Modality, flags: FlagSettings
) -> float | NoEvidenceReason:
    if all(hr is None for hr in samples.heart_rate_bpm):
        return NoEvidenceReason.NO_HEART_RATE
    if (
        cadence.detect(samples, modality=modality, settings=flags).outcome
        is cadence.CadenceLockOutcome.LOCKED
    ):
        return NoEvidenceReason.CADENCE_LOCKED

    spans = (
        tuple(
            span
            for span in cadence.span_statistics(
                samples, window_s=flags.cadence_lock_window_s, settings=flags
            )
            if span.locked
        )
        if modality is Modality.RUN
        else ()
    )
    span_index = 0
    stretches: list[list[tuple[float, float]]] = []
    previous: tuple[float, float] | None = None
    for t, hr in zip(samples.time_s, samples.heart_rate_bpm, strict=True):
        while span_index < len(spans):
            span = spans[span_index]
            if t < span.start_s + span.duration_s:
                break
            span_index += 1
        if span_index < len(spans) and spans[span_index].start_s <= t:
            continue
        if hr is None or not (
            sources.MAX_PLAUSIBLE_LOW_BPM.value
            <= hr
            <= sources.MAX_PLAUSIBLE_HIGH_BPM.value
        ):
            continue
        if previous is not None:
            prev_t, prev_hr = previous
            if t <= prev_t:
                continue
            if abs(hr - prev_hr) / (t - prev_t) > sources.MAX_RATE_BPM_PER_S.value:
                continue
        if previous is None or t - previous[0] > sources.MAX_GAP_S.value:
            stretches.append([])
        stretches[-1].append((t, float(hr)))
        previous = (t, float(hr))

    best: float | None = None
    for stretch in stretches:
        peak = _stretch_peak(stretch)
        if peak is not None:
            best = peak if best is None else max(best, peak)
    return NoEvidenceReason.NO_SUSTAINED_STRETCH if best is None else best

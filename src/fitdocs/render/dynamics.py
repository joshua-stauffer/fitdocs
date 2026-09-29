"""The Running Dynamics section: its table and its chart (design: DynamicsSection).

The section summarizes the twelve running-dynamics channels
(:data:`fitdocs.model.DYNAMICS_CHANNELS`) recorded on a run: one table row per
channel that has at least one recorded sample, and one chart of the first two
chartable channels of :data:`CHART_PRECEDENCE`.

Two rules govern everything here (Req 7.3, 8.3):

- **Recorded samples only.** Every average, percentile and coverage figure is
  computed over the samples that hold a value; a ``None`` sample is excluded,
  never counted as ``0``. A channel with no recorded sample has no row, and a
  section with no row is ``None`` (Req 7.6).
- **Closed set.** Only :data:`DYNAMICS_DISPLAY` channels are rendered;
  ``Activity.record_developer_fields`` is never read (Req 6.5), and balance
  labels carry no side word (Req 7.5).

Rendering is pure: it returns markdown and :class:`~fitdocs.render.Asset` values
and touches no filesystem. The x-axis is the telemetry chart's own, via
:func:`fitdocs.render.sections.chart_axis` (Req 8.2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from fitdocs import Samples
from fitdocs.layout import asset_rel_path
from fitdocs.render import Asset, DocContext
from fitdocs.render.charts.hero import HeroChartSpec, HeroSeries, render_hero_chart
from fitdocs.render.charts.palette import (
    DYNAMICS_PRIMARY_COLOR,
    DYNAMICS_SECONDARY_COLOR,
)
from fitdocs.render.sections import chart_axis

__all__ = [
    "CHART_PRECEDENCE",
    "DYNAMICS_DISPLAY",
    "DynamicsDisplay",
    "DynamicsRow",
    "dynamics_chart_spec",
    "dynamics_rows",
    "dynamics_section",
]


@dataclass(frozen=True)
class DynamicsDisplay:
    """How one dynamics channel is labelled and scaled for display."""

    channel: str  # a DYNAMICS_CHANNELS name
    label: str
    unit: str  # display unit
    factor: float  # model unit -> display unit
    decimals: int


@dataclass(frozen=True)
class DynamicsRow:
    """One table row: figures in display units over recorded samples only."""

    display: DynamicsDisplay
    average: float
    p10: float
    p90: float
    coverage_pct: int


DYNAMICS_DISPLAY: Final[tuple[DynamicsDisplay, ...]] = (
    DynamicsDisplay("stance_time_ms", "Ground contact time", "ms", 1.0, 0),
    DynamicsDisplay(
        "stance_time_balance_pct", "Ground contact time balance", "%", 1.0, 1
    ),
    DynamicsDisplay("vertical_oscillation_mm", "Vertical oscillation", "cm", 0.1, 1),
    DynamicsDisplay(
        "vertical_oscillation_balance_pct", "Vertical oscillation balance", "%", 1.0, 1
    ),
    DynamicsDisplay("vertical_ratio_pct", "Vertical ratio", "%", 1.0, 1),
    DynamicsDisplay("step_length_mm", "Step length", "m", 0.001, 2),
    DynamicsDisplay(
        "leg_spring_stiffness_kn_m", "Leg spring stiffness", "kN/m", 1.0, 1
    ),
    DynamicsDisplay(
        "leg_spring_stiffness_balance_pct", "Leg spring stiffness balance", "%", 1.0, 1
    ),
    DynamicsDisplay("form_power_w", "Form power", "w", 1.0, 0),
    DynamicsDisplay("air_power_w", "Air power", "w", 1.0, 0),
    DynamicsDisplay("impact_bw", "Impact", "bw", 1.0, 1),
    DynamicsDisplay(
        "impact_loading_rate_balance_pct", "Impact loading rate balance", "%", 1.0, 1
    ),
)

CHART_PRECEDENCE: Final[tuple[str, ...]] = (
    "stance_time_ms",
    "leg_spring_stiffness_kn_m",
    "vertical_oscillation_mm",
    "form_power_w",
    "step_length_mm",
    "vertical_ratio_pct",
)

_DISPLAY_BY_CHANNEL: Final[dict[str, DynamicsDisplay]] = {
    d.channel: d for d in DYNAMICS_DISPLAY
}
_SERIES_COLORS: Final[tuple[str, str]] = (
    DYNAMICS_PRIMARY_COLOR,
    DYNAMICS_SECONDARY_COLOR,
)
_HEADER: Final[str] = (
    "| Metric | Average | 10th–90th percentile | Coverage |\n| --- | --- | --- | --- |"
)


def _channel(samples: Samples, name: str) -> Sequence[float | None]:
    channel: Sequence[float | None] = getattr(samples, name)
    return channel


def _nearest_rank(ordered: Sequence[float], k: int) -> float:
    """Nearest-rank k-th percentile of sorted values, rank in integers."""
    rank = (k * len(ordered) + 99) // 100
    return ordered[max(rank - 1, 0)]


def dynamics_rows(samples: Samples) -> tuple[DynamicsRow, ...]:
    """One row per channel with a recorded sample, in display order (Req 7.2, 7.3)."""
    total = len(samples.time_s)
    rows: list[DynamicsRow] = []
    for display in DYNAMICS_DISPLAY:
        present = [v for v in _channel(samples, display.channel) if v is not None]
        if not present:
            continue
        ordered = sorted(present)
        factor = display.factor
        rows.append(
            DynamicsRow(
                display=display,
                average=sum(present) / len(present) * factor,
                p10=_nearest_rank(ordered, 10) * factor,
                p90=_nearest_rank(ordered, 90) * factor,
                coverage_pct=round(len(present) / total * 100),
            )
        )
    return tuple(rows)


def _fmt(value: float, decimals: int) -> str:
    """Fixed decimals; a text that reads as zero prints unsigned, never ``-0.0``."""
    text = f"{value:.{decimals}f}"
    if float(text) == 0:
        text = text.lstrip("-")
    return text


def _row_markdown(row: DynamicsRow) -> str:
    d = row.display
    avg = _fmt(row.average, d.decimals)
    lo = _fmt(row.p10, d.decimals)
    hi = _fmt(row.p90, d.decimals)
    return f"| {d.label} | {avg} {d.unit} | {lo}–{hi} {d.unit} | {row.coverage_pct}% |"


def _scaled(value: float | None, factor: float) -> float | None:
    """A sample in display units; an absent sample stays ``None``."""
    return value * factor if value is not None else None


def dynamics_chart_spec(ctx: DocContext) -> HeroChartSpec | None:
    """The chart of the first two precedence channels that have data (Req 8.1, 8.5)."""
    samples = ctx.activity.samples
    chosen = [
        name
        for name in CHART_PRECEDENCE
        if any(v is not None for v in _channel(samples, name))
    ][:2]
    if not chosen:
        return None
    axis = chart_axis(samples)
    if axis is None:
        return None
    series: list[HeroSeries] = []
    for slot, name in enumerate(chosen):
        display = _DISPLAY_BY_CHANNEL[name]
        raw = _channel(samples, name)
        values = tuple(_scaled(raw[i], display.factor) for i in axis.indices)
        series.append(
            HeroSeries(
                label=display.label,
                unit=display.unit,
                color=_SERIES_COLORS[slot],
                values=values,
            )
        )
    return HeroChartSpec(
        x=axis.x, x_unit=axis.unit, series=tuple(series), backdrop=None
    )


def dynamics_section(ctx: DocContext) -> tuple[str, tuple[Asset, ...]] | None:
    """The section body and assets, or ``None`` when nothing is recorded (Req 7.6)."""
    rows = dynamics_rows(ctx.activity.samples)
    if not rows:
        return None
    body = "\n".join([_HEADER, *(_row_markdown(r) for r in rows)])
    spec = dynamics_chart_spec(ctx)
    if spec is None:
        return body, ()
    rel = asset_rel_path(ctx.doc_stem, "dynamics")
    asset = Asset(rel_path=rel, content=render_hero_chart(spec))
    return f"{body}\n\n![Running dynamics chart]({rel})", (asset,)

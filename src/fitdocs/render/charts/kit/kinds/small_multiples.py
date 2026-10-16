"""The ``small-multiples`` kind: one small line panel per facet value.

Panels are laid out left to right and top to bottom in facet order (first
appearance, dates ascending, an absent facet last), every panel with identical
geometry and drawn in one line style, so the panel's title, not its colour,
identifies it. All panels share one x scale; they share one y scale unless the
request asks for ``independent`` ones. A shared axis is labelled once per row or
column of panels. A panel whose rows hold nothing drawable still draws its title,
its axes and a ``No values`` message. A row without an x or a y is counted in the
chart's note and description, never drawn as zero.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Final

from fitdocs.render.charts.kit import frame
from fitdocs.render.charts.kit.cartesian import (
    category_order,
    duplicate_problem,
    numbers,
)
from fitdocs.render.charts.kit.data import ValueKind
from fitdocs.render.charts.kit.format import (
    ABSENT,
    axis_title,
    clean_text,
    format_duration,
    format_value,
)
from fitdocs.render.charts.kit.layout import (
    FONT_TEXT,
    PAD,
    FramePlan,
    Rect,
    fit_text,
    plan_frame,
    text_width,
)
from fitdocs.render.charts.kit.marks import line_series
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import (
    NumericScale,
    ScaleType,
    Side,
    Tick,
    numeric_scale,
)
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
    svg_options,
)
from fitdocs.render.charts.kit.theme import TEXT, ink, series_style
from fitdocs.render.charts.svg import el, fmt_num, text
from fitdocs.units import UnitFamily, unit_named

PANEL_LIMIT: Final = 12
SM_ROW_LIMIT: Final = 2000
PANEL_HEIGHT: Final = 140.0
PANEL_MIN_WIDTH: Final = 180.0
_MAX_COLUMNS: Final = 6
_PROBE_HEIGHT: Final = 1000
_NO_VALUES: Final = "No values"


def _panel_labels(bound: BoundChart) -> list[str]:
    """Each row's panel label: its formatted facet value, or the absent label."""
    column = bound.columns["facet"]
    return [
        ABSENT if v is None else format_value(v, column, with_unit=False)
        for v in bound.values("facet")
    ]


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    problems: list[ChartProblem] = []
    facet = bound.columns["facet"]
    panels = len(category_order(bound, "facet"))
    if panels > PANEL_LIMIT:
        problems.append(
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"{bound.spec.name} draws at most {PANEL_LIMIT} panels; "
                f"this data has {panels}.",
                f"Filter the facet column to at most {PANEL_LIMIT} values.",
                channel="facet",
                column=facet.name,
                rows=panels,
            )
        )
    rows = len(bound.rows)
    if rows > SM_ROW_LIMIT:
        problems.append(
            bound.problem(
                ProblemCode.OVER_BOUND,
                f"{bound.spec.name} draws at most {SM_ROW_LIMIT} rows; "
                f"this data has {rows}.",
                "Aggregate the rows (for example by day or week) or limit them "
                f"to at most {SM_ROW_LIMIT}.",
                rows=rows,
            )
        )
    problems.extend(duplicate_problem(bound, ("facet", "x"), skip_absent=("x",)))
    return tuple(problems)


def _overhangs(scale: NumericScale, plot: Rect) -> tuple[float, float]:
    """How far the x tick labels reach past the panel plot's left and right."""
    left = right = 0.0
    for tick in scale.ticks:
        at = scale.position(tick.value)
        half = text_width(tick.label, FONT_TEXT) / 2
        left = max(left, half - (at - PAD))
        right = max(right, at + half - plot.right)
    return left, right


def _is_duration(bound: BoundChart, channel: str) -> bool:
    column = bound.columns[channel]
    if column.kind is ValueKind.DURATION:
        return True
    unit = None if column.unit is None else unit_named(column.unit)
    return unit is not None and unit.family is UnitFamily.DURATION


def _extremes(
    bound: BoundChart, channel: str, rows: list[int], scale: NumericScale
) -> tuple[str, str]:
    """The smallest and largest present value of ``channel`` in ``rows``."""
    column = bound.columns[channel]
    values = bound.values(channel)
    numeric = numbers(bound, channel)
    lowest = min(rows, key=lambda i: numeric[i] or 0.0)
    highest = max(rows, key=lambda i: numeric[i] or 0.0)

    def shown(index: int) -> str:
        seconds = numeric[index]
        if _is_duration(bound, channel) and seconds is not None:
            return format_duration(seconds, hours=scale.hours)
        return format_value(values[index], column, with_unit=True)

    return shown(lowest), shown(highest)


def _axis_title(scale: NumericScale) -> str:
    return axis_title(scale.column, clock_date=scale.clock_date, hours=scale.hours)


def _label(x: float, y: float, content: str, *, anchor: str | None = None) -> str:
    attrs = {"x": fmt_num(x), "y": fmt_num(y)}
    if anchor is not None:
        attrs["text-anchor"] = anchor
    attrs["font-size"] = fmt_num(FONT_TEXT)
    attrs.update(ink(TEXT))
    return el("text", attrs, [text(content)])


def _in_one_form(scales: list[NumericScale]) -> list[NumericScale]:
    """Scales whose duration labels agree: the hour form wins if any has it."""
    if len({s.hours for s in scales}) < 2:
        return scales
    return [
        s
        if s.hours
        else dataclasses.replace(
            s,
            hours=True,
            ticks=tuple(
                Tick(t.value, format_duration(t.value, hours=True)) for t in s.ticks
            ),
        )
        for s in scales
    ]


def _draw(bound: BoundChart) -> str:
    width = bound.width
    xs = numbers(bound, "x")
    ys = numbers(bound, "y")
    x_col, y_col = bound.columns["x"], bound.columns["y"]
    shared = bound.choice("y_axes") == "shared"
    order = category_order(bound, "facet")
    row_labels = _panel_labels(bound)

    drawable = [
        i for i in range(len(bound.rows)) if xs[i] is not None and ys[i] is not None
    ]
    # A row without x cannot be placed and counts under x; y counts its absent
    # values only among the rows that have an x (design: Undrawn counting).
    counts = tuple(
        (name, n)
        for name, n in (
            ("x", sum(1 for x in xs if x is None)),
            (
                "y",
                sum(
                    1
                    for x, y in zip(xs, ys, strict=True)
                    if x is not None and y is None
                ),
            ),
        )
        if n
    )
    note = frame.not_drawn_note(counts)
    lines = [] if note is None else [note]

    def outer_plan(height: int) -> FramePlan:
        return plan_frame(
            width,
            height,
            legend=(),
            y_label_width=0.0,
            x_label_overhang=0.0,
            has_x_title=True,
            has_y_title=True,
            notes=len(lines),
        )

    probe = outer_plan(_PROBE_HEIGHT)
    requested = bound.integer("columns")
    panels = len(order)
    columns = (
        requested
        if requested is not None
        else max(
            1,
            min(
                panels,
                _MAX_COLUMNS,
                math.floor(probe.plot.width / PANEL_MIN_WIDTH),
            ),
        )
    )
    grid_rows = math.ceil(panels / columns)
    frame_px = _PROBE_HEIGHT - probe.plot.height

    def auto_height(count: int) -> int:
        return math.ceil(count * PANEL_HEIGHT + frame_px)

    height = bound.height
    if not drawable:
        return frame.no_data(bound, height=auto_height(1) if height is None else height)
    if height is None:
        height = auto_height(grid_rows)

    outer = outer_plan(height)
    panel_w = math.floor(outer.plot.width / columns + 1e-6)
    panel_h = math.floor(outer.plot.height / grid_rows + 1e-6)

    def panel_plan(y_label_width: float, x_label_overhang: float) -> FramePlan:
        return plan_frame(
            panel_w,
            panel_h,
            legend=(),
            y_label_width=y_label_width,
            x_label_overhang=x_label_overhang,
            has_x_title=False,
            has_y_title=False,
            notes=0,
        )

    first = panel_plan(0.0, 0.0)
    members: dict[str, list[int]] = {label: [] for label in order}
    for index, label in enumerate(row_labels):
        members[label].append(index)
    present: dict[str, list[int]] = {
        label: [i for i in rows if xs[i] is not None and ys[i] is not None]
        for label, rows in members.items()
    }

    def y_scale_over(rows: list[int]) -> NumericScale:
        return numeric_scale(
            [y for i in rows if (y := ys[i]) is not None],
            y_col,
            first.plot.bottom,
            first.plot.top,
            scale=ScaleType.LINEAR,
            include_zero=False,
            nice=True,
            horizontal=False,
        )

    y_scales: dict[str, NumericScale | None]
    if shared:
        one = y_scale_over(drawable)
        y_scales = dict.fromkeys(order, one)
        title_scale = one
    else:
        with_values = [label for label in order if present[label]]
        built = _in_one_form([y_scale_over(present[label]) for label in with_values])
        y_scales = dict.fromkeys(order)
        y_scales.update(zip(with_values, built, strict=True))
        title_scale = built[0]
    drawn_y = [s for s in y_scales.values() if s is not None]
    label_width = max(
        (text_width(t.label, FONT_TEXT) for s in drawn_y for t in s.ticks),
        default=0.0,
    )
    x_rows = [i for i, x in enumerate(xs) if x is not None]
    x_present = [x for i in x_rows if (x := xs[i]) is not None]

    def x_axis(plot: Rect) -> NumericScale:
        return numeric_scale(
            x_present,
            x_col,
            plot.left,
            plot.right,
            scale=(
                ScaleType.LINEAR
                if x_col.kind in (ValueKind.NUMBER, ValueKind.DURATION)
                else ScaleType.TIME
            ),
            include_zero=False,
            nice=False,
            horizontal=True,
        )

    provisional = panel_plan(label_width, 0.0)
    left, right = _overhangs(x_axis(provisional.plot), provisional.plot)
    final = panel_plan(label_width + left, right)
    x_scale = x_axis(final.plot)
    plot = final.plot
    style = series_style(0)

    parts: list[str] = []
    for index, label in enumerate(order):
        col, grid_row = index % columns, index // columns
        has_below = index + columns < panels
        y_scale = y_scales[label]
        has_values = bool(present[label])
        inside: list[str] = []
        if y_scale is not None:
            inside.append(frame.grid(y_scale, plot, horizontal_lines=True))
        if y_scale is not None and has_values:
            points = sorted(
                ((x, ys[i]) for i in members[label] if (x := xs[i]) is not None),
                key=lambda p: p[0],
            )
            pixels = [
                (x_scale.position(x), None if y is None else y_scale.position(y))
                for x, y in points
            ]
            inside.append(el("g", {"class": "ck-marks"}, line_series(pixels, style)))
        x_drawn = dataclasses.replace(x_scale, ticks=()) if has_below else x_scale
        y_base = y_scale if y_scale is not None else title_scale
        y_drawn = (
            y_base
            if y_scale is not None and (not shared or col == 0)
            else dataclasses.replace(y_base, ticks=())
        )
        inside.append(frame.axis(x_drawn, plot, Side.BOTTOM, title="", plan=final))
        inside.append(frame.axis(y_drawn, plot, Side.LEFT, title="", plan=final))
        inside.append(
            _label(
                plot.left,
                final.title_y,
                fit_text(clean_text(label), plot.width, FONT_TEXT),
            )
        )
        if not has_values:
            inside.append(
                _label(
                    plot.left + plot.width / 2,
                    plot.top + plot.height / 2,
                    _NO_VALUES,
                    anchor="middle",
                )
            )
        shift = (
            f"translate({fmt_num(outer.plot.left + col * panel_w)},"
            f"{fmt_num(outer.plot.top + grid_row * panel_h)})"
        )
        parts.append(el("g", {"transform": shift}, inside))

    x_title = _axis_title(x_scale)
    y_title = _axis_title(title_scale)
    centre = outer.plot.left + outer.plot.width / 2
    titles: list[str] = []
    if outer.x_title_y is not None:
        titles.append(
            _label(
                centre,
                outer.x_title_y,
                fit_text(
                    clean_text(x_title),
                    2 * min(centre - PAD, outer.width - PAD - centre),
                    FONT_TEXT,
                ),
                anchor="middle",
            )
        )
    if outer.y_title_y is not None:
        titles.append(
            _label(
                outer.plot.left,
                outer.y_title_y,
                fit_text(
                    clean_text(y_title),
                    outer.width - PAD - outer.plot.left,
                    FONT_TEXT,
                ),
            )
        )
    body = [
        *parts,
        el("g", {"class": "ck-axis"}, titles),
        frame.title_text(outer, bound.request.title),
        frame.notes(outer, lines),
    ]
    x_low, x_high = _extremes(bound, "x", x_rows, x_scale)
    y_low, y_high = _extremes(bound, "y", drawable, title_scale)
    drawn_titles = {"x": x_title, "y": y_title}
    channels = [
        (name, drawn_titles.get(name, column)) for name, column in bound.columns.items()
    ]
    description = frame.describe(
        "small-multiples",
        bound.request.title,
        channels,
        rows=len(bound.rows),
        series=None,
        undrawn=counts,
        ranges=[(x_title, x_low, x_high), (y_title, y_low, y_high)],
    )
    return frame.document(
        width,
        height,
        title=bound.request.title,
        description=description,
        body=[part for part in body if part],
    )


KIND: Final = KindSpec(
    name="small-multiples",
    description="A grid of small line charts, one per facet value",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x",
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
            True,
            "The horizontal position in every panel: a number, duration, date "
            "or date-time.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical value: a number or duration.",
        ),
        ChannelSpec(
            "facet",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN, ValueKind.DATE),
            True,
            "One panel per value of this column, titled with the value.",
        ),
    ),
    options=svg_options(
        OptionSpec(
            "y_axes",
            OptionType.CHOICE,
            "Whether every panel shares one y scale or has its own.",
            "shared",
            choices=("shared", "independent"),
        ),
        OptionSpec(
            "columns",
            OptionType.INTEGER,
            "The number of panel columns; unset, it follows the chart width.",
            None,
            minimum=1,
            maximum=_MAX_COLUMNS,
        ),
        height=None,
    ),
    bound=MarkBound(
        PANEL_LIMIT,
        "panels",
        OverBound.REFUSE,
        f"At most {PANEL_LIMIT} panels and {SM_ROW_LIMIT} rows.",
    ),
    max_series=None,
    draw=_draw,
    check=_check,
)

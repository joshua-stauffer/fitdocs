"""Text measurement, truncation and the plot rectangle (chart-kit Req 6.3,
7.3, 7.4).

Space for text is reserved from one fixed per-character width estimate
(``CHAR_EM``), never from a font. Nothing here reads a font, a clock or the
environment.

Fixed two-pass rule (the caller's, i.e. scales/frame): y ticks are chosen from
the plot height, then the left margin follows from the widest y label, then x
ticks are chosen on the provisional width, then the right margin follows from
the widest x label, then x ticks are chosen once more on the final width.
``plan_frame`` is called once per pass with the label widths known at that point.

Vertical stack, top to bottom: ``PAD``; the title (baseline ``PAD +
FONT_TITLE``); ``PAD`` of space; the legend rows (``LEGEND_ROW`` each); the
y-axis title row (baseline ``FONT_TEXT`` below the rows, then ``PAD`` of space)
when there is one; the plot; the x tick labels (baseline ``TICK_LEN + TICK_GAP +
FONT_TEXT`` below the plot); the x-axis title (``X_TITLE_DROP`` lower) when there
is one; one ``NOTE_ROW`` per note; ``PAD``. The last baseline sits at ``height -
PAD``. Absent titles are ``None``, never a position.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Literal

from fitdocs.render.charts.kit.theme import SeriesStyle

CHAR_EM: Final = 0.64  # hero.py: 7.0 px at 11 px
FONT_TITLE: Final = 13
FONT_TEXT: Final = 11
FONT_NO_DATA: Final = 13
PAD: Final = 8.0
TICK_LEN: Final = 5.0
TICK_GAP: Final = 3.0
LEGEND_ROW: Final = 18.0
LEGEND_SWATCH: Final = 20.0
LEGEND_GAP: Final = 4.0
LEGEND_ITEM_GAP: Final = 14.0
NOTE_ROW: Final = 15.0

_X_TITLE_DROP: Final = 16.0
_MIN_RIGHT: Final = 16.0
_RIGHT_OVERHANG_PAD: Final = 4.0
_LEGEND_LABEL_SHARE: Final = 0.3
_ELLIPSIS: Final = "…"


@dataclass(frozen=True)
class Rect:
    left: float
    top: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height


@dataclass(frozen=True)
class LegendEntry:
    label: str
    style: SeriesStyle
    swatch: Literal["line", "shape", "block"]


@dataclass(frozen=True)
class FramePlan:
    width: int
    height: int
    title_y: float
    legend_rows: tuple[tuple[tuple[LegendEntry, float], ...], ...]  # rows of (entry, x)
    legend_top: float
    plot: Rect
    y_title_y: float | None
    x_labels_y: float
    x_title_y: float | None
    notes_y: tuple[float, ...]


def text_width(text: str, font_px: float) -> float:
    return len(text) * font_px * CHAR_EM


def fit_text(text: str, max_px: float, font_px: float) -> str:
    """``text`` if it fits ``max_px``; else its longest prefix ``p`` with
    ``text_width(p + "…") <= max_px``, plus ``…``; at minimum one character plus
    ``…``."""
    if text_width(text, font_px) <= max_px:
        return text
    for n in range(len(text) - 1, 0, -1):
        if text_width(text[:n] + _ELLIPSIS, font_px) <= max_px:
            return text[:n] + _ELLIPSIS
    return text[:1] + _ELLIPSIS


def _legend_rows(
    legend: Sequence[LegendEntry], width: int
) -> tuple[tuple[tuple[LegendEntry, float], ...], ...]:
    limit = width - PAD
    cap = _LEGEND_LABEL_SHARE * width
    rows: list[list[tuple[LegendEntry, float]]] = []
    x = PAD
    for source in legend:
        entry = dataclasses.replace(
            source, label=fit_text(source.label, cap, FONT_TEXT)
        )
        entry_w = LEGEND_SWATCH + LEGEND_GAP + text_width(entry.label, FONT_TEXT)
        end = x + entry_w
        if not rows or end > limit:
            x = PAD
            end = x + entry_w
            rows.append([])
        rows[-1].append((entry, x))
        x = end + LEGEND_ITEM_GAP
    return tuple(tuple(row) for row in rows)


def plan_frame(
    width: int,
    height: int,
    *,
    legend: Sequence[LegendEntry],
    y_label_width: float,
    x_label_overhang: float,
    has_x_title: bool,
    has_y_title: bool,
    notes: int,
    right_label_width: float = 0.0,
) -> FramePlan:
    title_y = PAD + FONT_TITLE
    legend_top = title_y + PAD
    rows = _legend_rows(legend, width)
    top = legend_top + len(rows) * LEGEND_ROW
    y_title_y: float | None = None
    if has_y_title:
        y_title_y = top + FONT_TEXT
        top = y_title_y + PAD

    bottom = height - PAD - notes * NOTE_ROW
    x_title_y: float | None = None
    if has_x_title:
        bottom -= _X_TITLE_DROP
    labels_drop = TICK_LEN + TICK_GAP + FONT_TEXT
    bottom -= labels_drop
    x_labels_y = bottom + labels_drop
    last = x_labels_y
    if has_x_title:
        x_title_y = x_labels_y + _X_TITLE_DROP
        last = x_title_y
    notes_y = tuple(last + NOTE_ROW * (i + 1) for i in range(notes))

    left = PAD + y_label_width + TICK_GAP + TICK_LEN
    right_margin = (
        max(_MIN_RIGHT, x_label_overhang + _RIGHT_OVERHANG_PAD) + right_label_width
    )
    plot = Rect(
        left,
        top,
        max(0.0, width - left - right_margin),
        max(0.0, bottom - top),
    )
    return FramePlan(
        width,
        height,
        title_y,
        rows,
        legend_top,
        plot,
        y_title_y,
        x_labels_y,
        x_title_y,
        notes_y,
    )

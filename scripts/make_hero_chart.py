"""Writes or checks the docs site's demo-data hero chart.

Invoked as ``python -m scripts.make_hero_chart`` from the repository root.
It renders ``website/assets/hero-chart.svg`` with the real fitdocs hero
renderer (``fitdocs.render.charts.hero``) from closed-form demo series, so the
image can be regenerated and its drift checked (requirements 3.5, 3.6).

* ``python -m scripts.make_hero_chart`` writes the SVG to ``--output``.
* ``python -m scripts.make_hero_chart --check`` compares instead: it never
  writes, and exits 1 when the file is missing or differs.

This is not site-build logic: it may import ``fitdocs`` (design: Allowed
Dependencies) and it never ships in a built artifact.

Reproducibility. Every series value is rounded to ``DECIMALS`` decimals inside
:func:`demo_spec`, so the renderer receives the same floats wherever ``exp``
and ``sin`` differ in their last bit. From there the renderer uses only
IEEE-754 basic operations and its own two-decimal formatting.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from fitdocs.render.charts.hero import HeroChartSpec, HeroSeries, render_hero_chart
from fitdocs.render.charts.palette import HR_COLOR, POWER_COLOR

OUTPUT: Final = Path("website/assets/hero-chart.svg")

# Decimals every series value is rounded to inside demo_spec.
DECIMALS: Final = 1

_STEP_MIN: Final = 0.5
_DURATION_MIN: Final = 60
# (start minute, end minute) of the three work intervals.
_INTERVALS: Final = ((10.0, 18.0), (22.0, 30.0), (34.0, 42.0))
_WARMUP_END_MIN: Final = 10.0
_COOLDOWN_START_MIN: Final = 46.0
_HR_LAG_TAU_MIN: Final = 1.5


def _power_w(minute: float) -> float:
    """Closed-form demo power: warm-up ramp, three intervals, cool-down."""
    ripple = 6.0 * math.sin(minute * 1.7)
    if minute < _WARMUP_END_MIN:
        base = 90.0 + 8.0 * minute
    elif minute >= _COOLDOWN_START_MIN:
        base = max(90.0, 150.0 - 4.5 * (minute - _COOLDOWN_START_MIN))
    elif any(start <= minute < end for start, end in _INTERVALS):
        base = 260.0
    else:
        base = 140.0
    return base + ripple


def demo_spec() -> HeroChartSpec:
    """The hero chart's demo data: power vs heart rate over a one-hour session.

    These are demo data generated from closed-form functions of time, never an
    athlete's data. There is no randomness and no file input. x runs 0-60 min
    in 0.5 min steps; power is a warm-up ramp, three work intervals and a
    cool-down; heart rate is a first-order lag of power; the backdrop is a
    smooth synthetic elevation profile. Every series value is rounded to
    ``DECIMALS`` decimals so the rendered SVG is identical across platforms
    whose libm may differ in the last bit of ``exp`` and ``sin``.
    """
    steps = int(_DURATION_MIN / _STEP_MIN) + 1
    minutes = [i * _STEP_MIN for i in range(steps)]
    power = [_power_w(m) for m in minutes]

    alpha = 1.0 - math.exp(-_STEP_MIN / _HR_LAG_TAU_MIN)
    hr = 95.0
    heart_rate: list[float] = []
    for p in power:
        target = 70.0 + 0.45 * p
        hr += alpha * (target - hr)
        heart_rate.append(hr)

    elevation = [
        120.0 + 30.0 * math.sin(m / 9.5) + 12.0 * math.sin(m / 3.1 + 1.0)
        for m in minutes
    ]

    return HeroChartSpec(
        x=tuple(round(m, DECIMALS) for m in minutes),
        x_unit="min",
        series=(
            HeroSeries(
                "Power",
                "W",
                POWER_COLOR,
                tuple(round(v, DECIMALS) for v in power),
            ),
            HeroSeries(
                "Heart rate",
                "bpm",
                HR_COLOR,
                tuple(round(v, DECIMALS) for v in heart_rate),
            ),
        ),
        backdrop=tuple(round(v, DECIMALS) for v in elevation),
    )


def render() -> str:
    """The demo hero chart as an SVG string."""
    return render_hero_chart(demo_spec())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.make_hero_chart",
        description=(
            "Write the demo-data hero chart SVG, or with --check compare it "
            "against the file on disk without writing."
        ),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help=f"SVG path to write or check (default: {OUTPUT})",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare instead of writing; exit 1 when the file differs",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    args = _build_parser().parse_args(argv)
    svg = render().encode("utf-8")
    output: Path = args.output
    if args.check:
        if output.is_file() and output.read_bytes() == svg:
            return 0
        print(
            f"{output} is missing or differs from the generated chart; "
            "regenerate with: python -m scripts.make_hero_chart",
            file=sys.stderr,
        )
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(svg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""The Running Dynamics section table and chart (running-dynamics task 3.2).

Pins :mod:`fitdocs.render.dynamics` against design § DynamicsSection and
requirements 6.5, 7.2-7.6, 8.1, 8.3-8.5. Contexts are a real parsed run whose
``Samples`` are replaced by hand-built ones, so each fixture states exactly the
channels and holes under test.
"""

from __future__ import annotations

import dataclasses
import re
from datetime import timedelta, timezone

import pytest

from fitdocs import DerivedMetrics, Samples, compute_metrics, parse_fit
from fitdocs.model import DYNAMICS_CHANNELS
from fitdocs.render import DocContext
from fitdocs.render import dynamics as dynamics_module
from fitdocs.render.charts.palette import (
    DYNAMICS_PRIMARY_COLOR,
    DYNAMICS_SECONDARY_COLOR,
)
from fitdocs.render.dynamics import (
    CHART_PRECEDENCE,
    DYNAMICS_DISPLAY,
    dynamics_chart_spec,
    dynamics_rows,
    dynamics_section,
)

_STEM = "2021-09-07-run-1946"
_HEADER = (
    "| Metric | Average | 10th–90th percentile | Coverage |\n| --- | --- | --- | --- |"
)
_Channel = tuple[float | None, ...]


def _samples(
    n: int,
    *,
    distance_m: _Channel | None = None,
    **dynamics: _Channel,
) -> Samples:
    """``n`` samples one minute apart; unnamed dynamics channels stay empty."""
    blank: _Channel = (None,) * n
    return Samples(
        time_s=tuple(60.0 * i for i in range(n)),
        heart_rate_bpm=blank,
        power_w=blank,
        cadence_rpm=blank,
        speed_mps=blank,
        distance_m=distance_m if distance_m is not None else blank,
        altitude_m=blank,
        latitude_deg=blank,
        longitude_deg=blank,
        temperature_c=blank,
        **dynamics,
    )


def _ctx(run_fit_bytes: bytes, samples: Samples) -> DocContext:
    activity = dataclasses.replace(parse_fit(run_fit_bytes), samples=samples)
    metrics: DerivedMetrics = compute_metrics(activity)
    return DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem=_STEM,
        source_refs=("fit-archive/aaaa.fit",),
        tz=timezone(timedelta(hours=-6)),
    )


def _polylines(svg: str) -> list[str]:
    """The stroke colour of every polyline, in document order."""
    return re.findall(r'<polyline[^>]*stroke="([^"]+)"', svg)


# --- the display table ------------------------------------------------------


def test_display_table_covers_the_twelve_channels_in_registry_order() -> None:
    assert tuple(d.channel for d in DYNAMICS_DISPLAY) == DYNAMICS_CHANNELS
    assert len(DYNAMICS_DISPLAY) == 12
    assert set(CHART_PRECEDENCE) <= set(DYNAMICS_CHANNELS)
    assert len(set(CHART_PRECEDENCE)) == len(CHART_PRECEDENCE) == 6


# --- rows: presence and order (7.2) -----------------------------------------


def test_one_row_per_present_channel_in_display_order_none_for_all_none() -> None:
    # Keywords are given in an order that differs from display order; air power
    # is present as a channel but holds no value.
    samples = _samples(
        3,
        impact_bw=(1.0, 2.0, 3.0),
        air_power_w=(None, None, None),
        form_power_w=(50.0, 60.0, 70.0),
        vertical_ratio_pct=(7.0, 8.0, 9.0),
        stance_time_ms=(240.0, 250.0, 260.0),
    )
    assert samples.air_power_w == (None, None, None)
    labels = [r.display.label for r in dynamics_rows(samples)]
    assert labels == ["Ground contact time", "Vertical ratio", "Form power", "Impact"]


def test_no_rows_when_no_channel_has_a_value() -> None:
    assert dynamics_rows(_samples(3)) == ()
    assert dynamics_rows(_samples(0)) == ()


# --- figures over recorded samples only (7.2, 7.3) --------------------------


def test_average_p10_p90_on_thirty_pairwise_distinct_values() -> None:
    # Pairwise-distinct, shuffled (the sorted order is 200, 201, 203, 206, ...,
    # 451, 470, 489, 509): the 3rd smallest is 203, the 4th is 206, the 27th is
    # 451, the 28th is 470, and the mean is 309.33.
    values = (
        200.0, 223.0, 279.0, 368.0, 489.0, 213.0, 260.0, 339.0, 451.0, 206.0,
        243.0, 313.0, 416.0, 201.0, 229.0, 290.0, 383.0, 509.0, 218.0, 269.0,
        353.0, 470.0, 209.0, 251.0, 326.0, 433.0, 203.0, 236.0, 301.0, 399.0,
    )  # fmt: skip
    assert len(set(values)) == len(values) == 30
    (row,) = dynamics_rows(_samples(30, stance_time_ms=values))
    assert row.average == pytest.approx(309.3333333)
    assert row.p10 == 203.0
    assert row.p90 == 451.0
    assert row.coverage_pct == 100


def test_none_samples_are_excluded_from_every_figure_never_counted_as_zero() -> None:
    samples = _samples(
        8,
        stance_time_ms=(None, 190.0, None, 100.0, None, None, 130.0, None),
    )
    (row,) = dynamics_rows(samples)
    assert row.average == pytest.approx(140.0)
    assert row.p10 == 100.0
    assert row.p90 == 190.0


def test_coverage_is_recorded_over_total_rounded_like_the_coverage_table() -> None:
    # 3 of 8 is 37.5 and 5 of 8 is 62.5: round-half-even gives 38 and 62, which
    # truncation (37, 62), ceiling (38, 63) and half-up (38, 63) do not.
    samples = _samples(
        8,
        stance_time_ms=(None, 1.0, 2.0, None, 3.0, None, None, None),
        form_power_w=(1.0, 2.0, None, 3.0, None, 4.0, 5.0, None),
    )
    rows = {r.display.channel: r for r in dynamics_rows(samples)}
    assert rows["stance_time_ms"].coverage_pct == 38
    assert rows["form_power_w"].coverage_pct == 62


# --- display units, decimals, signs, labels (7.4, 7.5) ----------------------


def test_every_channel_renders_its_label_unit_decimals_and_factor(
    run_fit_bytes: bytes,
) -> None:
    """Two samples per channel, so p10 is the smaller and p90 the larger value.
    Each expected row is written out literally, so a changed decimal count,
    factor, unit or label on any of the twelve entries prints a different row."""
    samples = _samples(
        2,
        stance_time_ms=(240.4, 251.6),
        stance_time_balance_pct=(49.26, 50.94),
        vertical_oscillation_mm=(91.4, 98.6),
        vertical_oscillation_balance_pct=(48.26, 51.94),
        vertical_ratio_pct=(7.26, 8.94),
        step_length_mm=(1234.0, 1246.0),
        leg_spring_stiffness_kn_m=(8.26, 8.74),
        leg_spring_stiffness_balance_pct=(47.26, 52.94),
        form_power_w=(60.4, 70.6),
        air_power_w=(180.4, 191.6),
        impact_bw=(2.04, 2.16),
        impact_loading_rate_balance_pct=(46.26, 53.94),
    )
    section = dynamics_section(_ctx(run_fit_bytes, samples))
    assert section is not None
    assert section[0].splitlines()[2:14] == [
        "| Ground contact time | 246 ms | 240–252 ms | 100% |",
        "| Ground contact time balance | 50.1 % | 49.3–50.9 % | 100% |",
        "| Vertical oscillation | 9.5 cm | 9.1–9.9 cm | 100% |",
        "| Vertical oscillation balance | 50.1 % | 48.3–51.9 % | 100% |",
        "| Vertical ratio | 8.1 % | 7.3–8.9 % | 100% |",
        "| Step length | 1.24 m | 1.23–1.25 m | 100% |",
        "| Leg spring stiffness | 8.5 kN/m | 8.3–8.7 kN/m | 100% |",
        "| Leg spring stiffness balance | 50.1 % | 47.3–52.9 % | 100% |",
        "| Form power | 66 w | 60–71 w | 100% |",
        "| Air power | 186 w | 180–192 w | 100% |",
        "| Impact | 2.1 bw | 2.0–2.2 bw | 100% |",
        "| Impact loading rate balance | 50.1 % | 46.3–53.9 % | 100% |",
    ]


def test_units_and_decimals_in_rendered_rows(run_fit_bytes: bytes) -> None:
    samples = _samples(
        2,
        stance_time_ms=(240.4, 251.6),
        vertical_oscillation_mm=(91.0, 99.0),
        step_length_mm=(1234.0, 1246.0),
        leg_spring_stiffness_kn_m=(8.25, 8.75),
        form_power_w=(60.4, 70.6),
        impact_bw=(2.04, 2.16),
    )
    section = dynamics_section(_ctx(run_fit_bytes, samples))
    assert section is not None
    lines = section[0].splitlines()
    assert "| Ground contact time | 246 ms | 240–252 ms | 100% |" in lines
    assert "| Vertical oscillation | 9.5 cm | 9.1–9.9 cm | 100% |" in lines
    assert "| Step length | 1.24 m | 1.23–1.25 m | 100% |" in lines
    assert "| Leg spring stiffness | 8.5 kN/m | 8.2–8.8 kN/m | 100% |" in lines
    assert "| Form power | 66 w | 60–71 w | 100% |" in lines
    assert "| Impact | 2.1 bw | 2.0–2.2 bw | 100% |" in lines


def test_a_value_that_rounds_to_zero_prints_unsigned_but_real_negatives_keep_sign(
    run_fit_bytes: bytes,
) -> None:
    samples = _samples(
        2,
        impact_bw=(-0.04, -0.03),
        impact_loading_rate_balance_pct=(-2.5, -2.5),
    )
    section = dynamics_section(_ctx(run_fit_bytes, samples))
    assert section is not None
    lines = section[0].splitlines()
    assert "| Impact | 0.0 bw | 0.0–0.0 bw | 100% |" in lines
    assert "| Impact loading rate balance | -2.5 % | -2.5–-2.5 % | 100% |" in lines


def test_balance_labels_carry_no_side_word(run_fit_bytes: bytes) -> None:
    samples = _samples(
        2,
        stance_time_balance_pct=(49.2, 50.8),
        vertical_oscillation_balance_pct=(49.2, 50.8),
        leg_spring_stiffness_balance_pct=(49.2, 50.8),
        impact_loading_rate_balance_pct=(49.2, 50.8),
    )
    section = dynamics_section(_ctx(run_fit_bytes, samples))
    assert section is not None
    lines = section[0].splitlines()
    assert lines[2:] == [
        "| Ground contact time balance | 50.0 % | 49.2–50.8 % | 100% |",
        "| Vertical oscillation balance | 50.0 % | 49.2–50.8 % | 100% |",
        "| Leg spring stiffness balance | 50.0 % | 49.2–50.8 % | 100% |",
        "| Impact loading rate balance | 50.0 % | 49.2–50.8 % | 100% |",
    ]
    assert not re.search(r"\b(left|right)\b", section[0], re.IGNORECASE)


# --- the chart: selection and order (8.1, 8.5) ------------------------------

_TEN = tuple(float(v) for v in range(100, 110))


def test_chart_plots_first_two_precedence_channels_in_order(
    run_fit_bytes: bytes,
) -> None:
    samples = _samples(
        10,
        vertical_oscillation_mm=_TEN,
        step_length_mm=_TEN,
        leg_spring_stiffness_kn_m=_TEN,
        stance_time_ms=_TEN,
    )
    spec = dynamics_chart_spec(_ctx(run_fit_bytes, samples))
    assert spec is not None
    assert [s.label for s in spec.series] == [
        "Ground contact time",
        "Leg spring stiffness",
    ]
    assert [s.color for s in spec.series] == [
        DYNAMICS_PRIMARY_COLOR,
        DYNAMICS_SECONDARY_COLOR,
    ]
    assert spec.backdrop is None


def test_chart_skips_absent_precedence_channels_and_converts_to_display_units(
    run_fit_bytes: bytes,
) -> None:
    samples = _samples(
        10,
        form_power_w=_TEN,
        step_length_mm=_TEN,
        vertical_oscillation_mm=_TEN,
        vertical_ratio_pct=_TEN,
        stance_time_balance_pct=_TEN,
    )
    spec = dynamics_chart_spec(_ctx(run_fit_bytes, samples))
    assert spec is not None
    assert [(s.label, s.unit) for s in spec.series] == [
        ("Vertical oscillation", "cm"),
        ("Form power", "w"),
    ]
    assert spec.series[0].values == pytest.approx(tuple(v / 10 for v in _TEN))
    assert spec.series[1].values == _TEN


def test_chart_series_align_with_the_shared_axis_indices(run_fit_bytes: bytes) -> None:
    # Sample 2 has no distance, so the km axis drops it; the series must drop
    # the same sample and keep the others at their own positions.
    distance = (0.0, 1000.0, None, 3000.0, 4000.0)
    samples = _samples(
        5,
        distance_m=distance,
        stance_time_ms=(210.0, 220.0, 230.0, 240.0, 250.0),
    )
    spec = dynamics_chart_spec(_ctx(run_fit_bytes, samples))
    assert spec is not None
    assert spec.x_unit == "km"
    assert spec.x == (0.0, 1.0, 3.0, 4.0)
    assert spec.series[0].values == (210.0, 220.0, 240.0, 250.0)


def test_no_chart_when_only_unchartable_channels_are_present(
    run_fit_bytes: bytes,
) -> None:
    samples = _samples(
        10,
        stance_time_balance_pct=_TEN,
        vertical_oscillation_balance_pct=_TEN,
        leg_spring_stiffness_balance_pct=_TEN,
        air_power_w=_TEN,
        impact_bw=_TEN,
        impact_loading_rate_balance_pct=_TEN,
    )
    ctx = _ctx(run_fit_bytes, samples)
    assert dynamics_chart_spec(ctx) is None
    section = dynamics_section(ctx)
    assert section is not None
    body, assets = section
    assert len(dynamics_rows(samples)) == 6  # the section itself is not empty
    assert "![" not in body
    assert assets == ()


def test_no_chart_when_no_sample_has_an_x_value(
    run_fit_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``Samples`` rejects a dynamics value beside an empty ``time_s``, so the
    axis is stubbed empty to reach the branch."""
    samples = _samples(3, stance_time_ms=(1.0, 2.0, 3.0))
    ctx = _ctx(run_fit_bytes, samples)
    assert dynamics_chart_spec(ctx) is not None
    monkeypatch.setattr(dynamics_module, "chart_axis", lambda _samples: None)
    assert dynamics_chart_spec(ctx) is None
    section = dynamics_section(ctx)
    assert section is not None
    assert section[1] == ()


_PRECEDENCE_PAIRS = (
    (
        "stance_time_ms",
        "leg_spring_stiffness_kn_m",
        "Ground contact time",
        "Leg spring stiffness",
    ),
    (
        "leg_spring_stiffness_kn_m",
        "vertical_oscillation_mm",
        "Leg spring stiffness",
        "Vertical oscillation",
    ),
    ("vertical_oscillation_mm", "form_power_w", "Vertical oscillation", "Form power"),
    ("form_power_w", "step_length_mm", "Form power", "Step length"),
    ("step_length_mm", "vertical_ratio_pct", "Step length", "Vertical ratio"),
)


@pytest.mark.parametrize(
    ("first", "second", "first_label", "second_label"), _PRECEDENCE_PAIRS
)
def test_each_adjacent_precedence_pair_charts_in_precedence_order(
    run_fit_bytes: bytes, first: str, second: str, first_label: str, second_label: str
) -> None:
    """Only these two channels are present; the expected order is written out
    here, not read from ``CHART_PRECEDENCE``."""
    samples = _samples(10, **{second: _TEN, first: _TEN})
    spec = dynamics_chart_spec(_ctx(run_fit_bytes, samples))
    assert spec is not None
    assert [s.label for s in spec.series] == [first_label, second_label]


def test_the_precedence_pairs_are_the_adjacent_pairs_of_the_chart_precedence() -> None:
    assert all(
        a[1] == b[0]
        for a, b in zip(_PRECEDENCE_PAIRS[:-1], _PRECEDENCE_PAIRS[1:], strict=True)
    )
    assert tuple(p[0] for p in _PRECEDENCE_PAIRS) + (_PRECEDENCE_PAIRS[-1][1],) == (
        "stance_time_ms",
        "leg_spring_stiffness_kn_m",
        "vertical_oscillation_mm",
        "form_power_w",
        "step_length_mm",
        "vertical_ratio_pct",
    )


# --- gaps (8.3) -------------------------------------------------------------


def test_a_run_of_none_in_a_charted_series_yields_separate_polylines(
    run_fit_bytes: bytes,
) -> None:
    full = tuple(200.0 + 7 * i for i in range(12))
    gapped = tuple(None if 4 <= i <= 6 else v for i, v in enumerate(full))
    other = tuple(50.0 + 3 * i for i in range(12))

    control = dynamics_section(
        _ctx(
            run_fit_bytes,
            _samples(12, stance_time_ms=full, leg_spring_stiffness_kn_m=other),
        )
    )
    assert control is not None
    assert _polylines(control[1][0].content) == [
        DYNAMICS_PRIMARY_COLOR,
        DYNAMICS_SECONDARY_COLOR,
    ]

    ctx = _ctx(
        run_fit_bytes,
        _samples(12, stance_time_ms=gapped, leg_spring_stiffness_kn_m=other),
    )
    spec = dynamics_chart_spec(ctx)
    assert spec is not None
    assert spec.series[0].values[4:7] == (None, None, None)
    section = dynamics_section(ctx)
    assert section is not None
    assert _polylines(section[1][0].content) == [
        DYNAMICS_PRIMARY_COLOR,
        DYNAMICS_PRIMARY_COLOR,
        DYNAMICS_SECONDARY_COLOR,
    ]


# --- omission, link, determinism (7.6, 8.4) ---------------------------------


def test_section_is_none_when_no_channel_has_a_value(run_fit_bytes: bytes) -> None:
    assert dynamics_section(_ctx(run_fit_bytes, _samples(4))) is None
    assert (
        dynamics_section(
            _ctx(run_fit_bytes, _samples(4, air_power_w=(None, None, None, None)))
        )
        is None
    )


def test_link_asset_and_determinism(run_fit_bytes: bytes) -> None:
    samples = _samples(
        3,
        stance_time_ms=(240.0, 250.0, 260.0),
        form_power_w=(60.0, 65.0, 70.0),
    )
    ctx = _ctx(run_fit_bytes, samples)
    section = dynamics_section(ctx)
    assert section is not None
    body, assets = section
    link = f"![Running dynamics chart](assets/{_STEM}-dynamics.svg)"
    assert body == (
        f"{_HEADER}\n"
        "| Ground contact time | 250 ms | 240–260 ms | 100% |\n"
        "| Form power | 65 w | 60–70 w | 100% |\n"
        f"\n{link}"
    )
    (asset,) = assets
    assert asset.rel_path == f"assets/{_STEM}-dynamics.svg"
    assert f"]({asset.rel_path})" in body
    assert asset.content.startswith("<svg")
    assert "<script" not in asset.content
    assert dynamics_section(ctx) == section

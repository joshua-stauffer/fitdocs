"""Hero chart generator: drift, demo-data-only, rounding (requirements 3.5, 3.6).

Every test carries a ``Dies on:`` line. For the generator tests it names a
change to ``scripts/make_hero_chart.py``; for the tests of this module's own
scan helpers it names a change to the helper. Tests do not write into the
repository tree; output paths live in ``tmp_path``.
"""

from __future__ import annotations

import ast
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import scripts.make_hero_chart as hero

from fitdocs.render.charts.hero import HeroChartSpec, HeroSeries, render_hero_chart
from fitdocs.render.charts.palette import HR_COLOR, POWER_COLOR

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKED_IN = REPO_ROOT / "website" / "assets" / "hero-chart.svg"


def _spec_numbers(spec: HeroChartSpec) -> list[float]:
    """Every numeric sample in ``spec`` (x, each series, the backdrop)."""
    numbers: list[float] = list(spec.x)
    for series in spec.series:
        numbers += [v for v in series.values if v is not None]
    if spec.backdrop is not None:
        numbers += [v for v in spec.backdrop if v is not None]
    return numbers


def _over_precise(spec: HeroChartSpec, decimals: int) -> list[float]:
    """The samples of ``spec`` that carry more than ``decimals`` decimals."""
    return [v for v in _spec_numbers(spec) if round(v, decimals) != v]


def _read_calls(source: str) -> list[str]:
    """Names of file-read constructs anywhere in the module ``source`` except
    inside ``def main``, which reads the checked-in file under ``--check``.

    Raises when ``main`` is not defined, so a renamed ``main`` cannot make the
    scan skip nothing while looking at the wrong module.
    """
    tree = ast.parse(source)
    mains = [
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
    ]
    if not mains:
        raise LookupError("main not found: the scan is looking at the wrong module")
    skipped = {id(n) for main in mains for n in ast.walk(main)}
    found: list[str] = []
    for node in ast.walk(tree):
        if id(node) in skipped:
            continue
        if isinstance(node, ast.Name) and node.id in {"open", "csv"}:
            found.append(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in {
            "open",
            "read_text",
            "read_bytes",
            "csv",
        }:
            found.append(node.attr)
        elif isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name == "csv"]
        elif isinstance(node, ast.ImportFrom) and node.module == "csv":
            found.append("csv")
    return found


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "scripts.make_hero_chart", *args],
        cwd=REPO_ROOT,
        env={
            k: v
            for k, v in os.environ.items()
            if k
            not in {
                "FITDOCS_SITE_CONTENT",
                "FITDOCS_FORBIDDEN_STRINGS",
                "FITDOCS_DATA",
            }
        },
        capture_output=True,
        text=True,
        check=False,
    )


def test_render_equals_checked_in_svg_byte_for_byte() -> None:
    """3.5, 3.6: the committed image is what the generator renders today.

    Dies on: changing the interval count in ``demo_spec`` from 3 to 2, or the
    heart-rate lag constant ``_HR_LAG_TAU_MIN``, without regenerating the file.
    """
    checked_in = CHECKED_IN.read_bytes()
    assert len(checked_in) > 2000, "the checked-in chart is trivially small"
    assert hero.render().encode("utf-8") == checked_in


def test_checked_in_svg_draws_both_demo_series() -> None:
    """3.5: the image is the power-vs-HR chart, not an empty frame.

    Dies on: dropping the power series from ``demo_spec`` (regenerated file
    loses its ``POWER_COLOR`` polylines and its legend entry).
    """
    svg = CHECKED_IN.read_text(encoding="utf-8")
    assert svg.startswith("<svg")
    assert f'stroke="{HR_COLOR}"' in svg
    assert f'stroke="{POWER_COLOR}"' in svg
    assert 'class="backdrop"' in svg


def test_check_passes_on_the_checked_in_file() -> None:
    """3.6: ``--check`` with the default output path exits 0 from the repo root.

    Dies on: pointing ``OUTPUT`` at a different file name.
    """
    result = _run_cli("--check")
    assert result.returncode == 0, result.stderr


def test_check_exits_one_on_a_tampered_copy_and_leaves_it_alone(
    tmp_path: Path,
) -> None:
    """3.6: drift under ``--check`` is exit 1 and nothing is written.

    Dies on: ``main`` writing the rendered SVG to the path before comparing
    (the tampered bytes would be replaced) or comparing with ``!=`` flipped.
    """
    copy = tmp_path / "hero-chart.svg"
    tampered = CHECKED_IN.read_bytes().replace(b"<svg", b"<svg data-x='1'", 1)
    assert tampered != CHECKED_IN.read_bytes(), "the tamper changed nothing"
    copy.write_bytes(tampered)
    assert hero.main(["--check", "--output", str(copy)]) == 1
    assert copy.read_bytes() == tampered


def test_check_exits_zero_on_a_matching_copy(tmp_path: Path) -> None:
    """3.6: an identical copy passes and stays identical.

    Dies on: ``--check`` returning 1 unconditionally.
    """
    copy = tmp_path / "hero-chart.svg"
    copy.write_bytes(CHECKED_IN.read_bytes())
    before = copy.stat().st_mtime_ns
    assert hero.main(["--check", "--output", str(copy)]) == 0
    assert copy.stat().st_mtime_ns == before


def test_check_on_a_missing_file_is_drift_and_creates_nothing(
    tmp_path: Path,
) -> None:
    """3.6: no file to compare against is drift, and ``--check`` stays read-only.

    Dies on: ``--check`` writing the file when it is absent.
    """
    target = tmp_path / "nested" / "hero-chart.svg"
    assert hero.main(["--check", "--output", str(target)]) == 1
    assert not target.parent.exists()


def test_check_drift_message_names_the_regenerate_command(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """3.6: a failing check tells the reader how to regenerate.

    Dies on: deleting the stderr message in the drift branch.
    """
    copy = tmp_path / "hero-chart.svg"
    copy.write_text("<svg/>", encoding="utf-8")
    assert hero.main(["--check", "--output", str(copy)]) == 1
    err = capsys.readouterr().err
    assert "scripts.make_hero_chart" in err
    assert str(copy) in err


def test_write_mode_writes_the_rendered_svg_and_creates_parents(
    tmp_path: Path,
) -> None:
    """3.6: without ``--check`` the SVG is written to ``--output``.

    Dies on: ``main`` ignoring ``--output`` or not creating the parent directory.
    """
    target = tmp_path / "out" / "hero-chart.svg"
    assert not target.exists()
    assert hero.main(["--output", str(target)]) == 0
    assert target.read_bytes() == CHECKED_IN.read_bytes()


def test_write_mode_replaces_stale_content(tmp_path: Path) -> None:
    """3.6: an existing stale file is overwritten, not appended to.

    Dies on: opening the output in append mode.
    """
    target = tmp_path / "hero-chart.svg"
    target.write_text("stale", encoding="utf-8")
    assert hero.main(["--output", str(target)]) == 0
    assert target.read_bytes() == CHECKED_IN.read_bytes()


def test_default_output_is_the_website_asset() -> None:
    """3.6: the documented default path.

    Dies on: changing ``OUTPUT`` to any other path.
    """
    assert Path("website/assets/hero-chart.svg") == hero.OUTPUT
    assert (REPO_ROOT / hero.OUTPUT).read_bytes() == CHECKED_IN.read_bytes()


def test_demo_spec_shape_is_a_workout() -> None:
    """3.5: 0-60 min in half-minute steps, HR lagging a three-interval power.

    Dies on: computing HR from power without the lag (``hr = target``), as a
    pure delay of power instead of a first-order lag, or changing the grid
    step or the interval count.
    """
    spec = hero.demo_spec()
    assert spec.x_unit == "min"
    assert spec.x[0] == 0.0 and spec.x[-1] == 60.0
    assert all(b - a == 0.5 for a, b in zip(spec.x, spec.x[1:], strict=False))
    by_label = {s.label: s for s in spec.series}
    assert set(by_label) == {"Power", "Heart rate"}
    assert by_label["Power"].color == POWER_COLOR
    assert by_label["Heart rate"].color == HR_COLOR
    power = [v for v in by_label["Power"].values if v is not None]
    hr = [v for v in by_label["Heart rate"].values if v is not None]
    assert len(power) == len(hr) == len(spec.x) == 121
    assert spec.backdrop is not None and len(spec.backdrop) == 121

    threshold = (max(power) + min(power)) / 2
    rises = [i for i in range(1, len(power)) if power[i] >= threshold > power[i - 1]]
    assert len(rises) == 3
    for rise in rises:
        # Heart rate responds at the step itself (a pure delay would not) and
        # is still climbing eight samples (4 min) after it.
        assert hr[rise] - hr[rise - 1] > 5.0
        assert hr[rise + 8] - hr[rise] > 10.0
    assert hr.index(max(hr)) > power.index(max(power))


def test_demo_spec_values_are_rounded_to_the_fixed_decimals() -> None:
    """3.5: every sample is at most ``DECIMALS`` decimals, so libm noise is gone.

    Dies on: removing the ``round`` from the power, HR or backdrop series
    inside ``demo_spec``. (Removing it from x changes nothing: every x is a
    multiple of 0.5, which is exact.)
    """
    numbers = _spec_numbers(hero.demo_spec())
    assert len(numbers) > 300, "the scan is looking at almost nothing"
    assert _over_precise(hero.demo_spec(), hero.DECIMALS) == []


def test_decimals_detector_flags_an_unrounded_series() -> None:
    """3.5: the detector used above does reject an unrounded value.

    Dies on: ``_over_precise`` returning ``[]`` (the noisy fixture below goes
    unflagged).
    """
    good = hero.demo_spec()
    noisy = HeroChartSpec(
        x=good.x,
        x_unit=good.x_unit,
        series=(
            HeroSeries(
                "Power", "W", POWER_COLOR, tuple(i + 0.123456 for i in range(121))
            ),
            good.series[1],
        ),
        backdrop=good.backdrop,
    )
    assert _over_precise(good, hero.DECIMALS) == []
    assert len(_over_precise(noisy, hero.DECIMALS)) == 121


def test_generator_module_reads_no_files_outside_main() -> None:
    """3.5: demo data come from closed-form series, not a file.

    The scan covers the whole module except ``main``.

    Dies on: adding ``Path(...).read_text()`` (or ``open``/``csv``) anywhere in
    ``scripts/make_hero_chart.py`` outside ``main``: in ``demo_spec``, in a
    helper such as ``_power_w``, or at module level.
    """
    source = Path(hero.__file__).read_text(encoding="utf-8")
    assert _read_calls(source) == []


def test_render_is_the_renderer_output_of_demo_spec() -> None:
    """3.5: ``render()`` is the real renderer applied to ``demo_spec()``.

    Dies on: ``render()`` post-processing the SVG, e.g. truncating the closing
    ``</svg>`` (regenerating the file would hide that from the byte test).
    """
    assert hero.render() == render_hero_chart(hero.demo_spec())


def test_checked_in_svg_is_well_formed_with_a_line_per_series() -> None:
    """3.5: the committed file parses as SVG and draws both series.

    Dies on: ``render()`` truncating ``</svg>`` with the file regenerated, or
    dropping either series' polylines.
    """
    root = ET.fromstring(CHECKED_IN.read_bytes())
    ns = "{http://www.w3.org/2000/svg}"
    assert root.tag == f"{ns}svg"
    strokes = [p.get("stroke") for p in root.iter(f"{ns}polyline")]
    assert strokes.count(HR_COLOR) >= 1
    assert strokes.count(POWER_COLOR) >= 1


def test_read_scan_flags_a_module_level_read() -> None:
    """A read at module level, used later by ``demo_spec``, is flagged.

    Dies on: ``_read_calls`` scanning function bodies only.
    """
    source = (
        "DATA = Path('x').read_text()\n"
        "def demo_spec():\n    return DATA\n"
        "def main():\n    pass\n"
    )
    assert _read_calls(source) == ["read_text"]


def test_read_scan_flags_a_helper_passed_by_name() -> None:
    """A read in a helper that is only passed by name (``map(_h, ...)``) is flagged.

    Dies on: ``_read_calls`` scanning only ``demo_spec``'s own body.
    """
    source = (
        "def demo_spec():\n    return list(map(_h, [1]))\n"
        "def _h(v):\n    return Path('x').read_text()\n"
        "def main():\n    pass\n"
    )
    assert _read_calls(source) == ["read_text"]


def test_read_scan_flags_a_two_level_helper_chain() -> None:
    """A read two calls below ``demo_spec`` is flagged.

    Dies on: ``_read_calls`` scanning only ``demo_spec``'s own body.
    """
    source = (
        "def demo_spec():\n    return _a()\n"
        "def _a():\n    return _b()\n"
        "def _b():\n    return open('x')\n"
        "def main():\n    pass\n"
    )
    assert _read_calls(source) == ["open"]


def test_read_scan_ignores_reads_inside_main() -> None:
    """``main`` may read the checked-in file; that is not flagged.

    Dies on: ``_read_calls`` no longer skipping ``main`` (the real module's
    ``--check`` read would then fail the module-wide test).
    """
    source = (
        "def demo_spec():\n    return 1\n"
        "def main():\n    return Path('x').read_bytes()\n"
    )
    assert _read_calls(source) == []


@pytest.mark.parametrize(
    "body",
    [
        "open('x')",
        "Path('x').open()",
        "Path('x').read_text()",
        "Path('x').read_bytes()",
        "csv.reader([])",
        "import csv",
        "from csv import reader",
    ],
)
def test_read_scan_flags_each_forbidden_construct(body: str) -> None:
    """The AST scan finds each construct it claims to forbid.

    Dies on: dropping the matching name from the scan's sets in ``_read_calls``.
    """
    source = f"def demo_spec():\n    {body}\ndef main():\n    pass\n"
    assert _read_calls(source) != []


def test_read_scan_is_not_vacuous_on_a_missing_main() -> None:
    """The scan refuses a module that has no ``main`` to skip.

    Dies on: ``_read_calls`` returning a result instead of raising when
    ``main`` is absent.
    """
    with pytest.raises(LookupError):
        _read_calls("def other():\n    open('x')\n")
    real = Path(hero.__file__).read_text(encoding="utf-8")
    assert "def main" in real
    assert _read_calls(real) == []

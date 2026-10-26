"""Property tests for the windowed line simplifier (compact-chart-assets 2.1).

Tolerance (Req 1.1, 2.1), kept endpoints (1.2, 2.2), linear work (1.6, 2.5),
determinism (5.1) and purity (5.4: an import allow-list). The point-to-polyline
distance used to judge the output is computed here, independently of the module
under test.
"""

from __future__ import annotations

import ast
import math
import random
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from fitdocs.render.charts import polyline
from fitdocs.render.charts.polyline import (
    COORD_PLACES,
    THIN_TOLERANCE,
    Point,
    points_attr,
    thin,
)

BOUND = 0.5
# Design postcondition 2: tolerance plus the rounding error of both coordinates.
POSTCONDITION_2 = THIN_TOLERANCE + math.sqrt(2) * 0.5 * 10**-COORD_PLACES
WINDOW = 512  # the design's window; test_window_constants pins the module's


def _seg_dist(p: Point, a: Point, b: Point) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    if L2 == 0.0:
        return math.hypot(p[0] - ax, p[1] - ay)
    t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / L2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def _dist_to_line(p: Point, line: tuple[Point, ...]) -> float:
    if len(line) == 1:
        return math.hypot(p[0] - line[0][0], p[1] - line[0][1])
    return min(_seg_dist(p, line[i], line[i + 1]) for i in range(len(line) - 1))


def _worst(run: list[Point], out: tuple[Point, ...]) -> float:
    return max(_dist_to_line(p, out) for p in run)


# --- seeded runs -------------------------------------------------------------


def _sine(n: int = 900) -> list[Point]:
    return [(i * 0.5, 40 + 30 * math.sin(i / 25)) for i in range(n)]


def _noisy_walk(n: int = 1500) -> list[Point]:
    rng = random.Random(11)
    y = 100.0
    out = []
    for i in range(n):
        y += rng.uniform(-1.2, 1.2)
        out.append((i * 0.3, y))
    return out


def _steps(n: int = 1200) -> list[Point]:
    return [(i * 0.4, 20.0 + 15.0 * ((i // 60) % 4)) for i in range(n)]


def _spikes() -> list[Point]:
    # Flat line with one-sample spikes of height 2 (between 0.5 and 3 units).
    return [(i * 1.0, 50.0 + (2.0 if i % 97 == 50 else 0.0)) for i in range(1100)]


def _loop(n: int = 1300) -> list[Point]:
    run = [
        (
            100 + 60 * math.cos(2 * math.pi * i / (n - 1)),
            100 + 60 * math.sin(2 * math.pi * i / (n - 1)),
        )
        for i in range(n)
    ]
    run[-1] = run[0]  # exact closure: a zero-length chord, not a 1e-16 one
    return run


def _back_and_forth(n: int = 1000) -> list[Point]:
    # Out along a gentle wiggle and back along (almost) the same track.
    rng = random.Random(5)
    out = [(i * 0.4, 30 + 4 * math.sin(i / 17)) for i in range(n // 2)]
    back = [(x, y + rng.uniform(-0.8, 0.8)) for x, y in reversed(out)]
    return out + back


def _non_monotone_x(n: int = 1100) -> list[Point]:
    rng = random.Random(3)
    return [
        (80 + 50 * math.sin(i / 31) + rng.uniform(-0.4, 0.4), i * 0.2) for i in range(n)
    ]


RUNS: dict[str, Callable[[], list[Point]]] = {
    "sine": _sine,
    "noisy_walk": _noisy_walk,
    "steps": _steps,
    "spikes": _spikes,
    "loop": _loop,
    "back_and_forth": _back_and_forth,
    "non_monotone_x": _non_monotone_x,
}


@pytest.mark.parametrize("name", sorted(RUNS))
def test_every_input_point_within_half_unit_of_output(name: str) -> None:
    run = RUNS[name]()
    out = thin(run)
    worst = _worst(run, out)
    assert worst <= POSTCONDITION_2
    assert worst <= BOUND
    # The run must actually be reduced, else the bound is trivially met.
    assert len(out) < len(run)


def test_fixtures_have_detail_between_half_and_three_units() -> None:
    # A simplifier with epsilon 3.0 must break the bound on these runs: the
    # same algorithm at 3.0 leaves some point farther than 0.5 from its output.
    for name in ("spikes", "noisy_walk", "back_and_forth"):
        run = RUNS[name]()
        coarse = thin_at(run, 3.0)
        assert _worst(run, coarse) > BOUND, name


def thin_at(run: list[Point], eps: float) -> tuple[Point, ...]:
    saved = polyline.THIN_TOLERANCE
    polyline.THIN_TOLERANCE = eps
    try:
        return thin(run)
    finally:
        polyline.THIN_TOLERANCE = saved


def test_tolerance_is_applied_at_0_3_by_behaviour() -> None:
    # Chord (0,0)-(8,6), length 10. For a grid point (x, y) its distance to the
    # chord is 0.02 * |4*(10y - 30) - 3*(10x - 40)|, so these coordinates are
    # exact at 1 decimal (rounding cannot confound) and sit at 0.28 and 0.32.
    below = (3.8, 3.2)
    above = (4.0, 3.4)
    assert polyline._distance(below, (0.0, 0.0), (8.0, 6.0)) == pytest.approx(0.28)  # noqa: SLF001
    assert polyline._distance(above, (0.0, 0.0), (8.0, 6.0)) == pytest.approx(0.32)  # noqa: SLF001
    assert thin([(0.0, 0.0), below, (8.0, 6.0)]) == ((0.0, 0.0), (8.0, 6.0))
    assert thin([(0.0, 0.0), above, (8.0, 6.0)]) == ((0.0, 0.0), above, (8.0, 6.0))


def test_spikes_survive() -> None:
    run = _spikes()
    out = set(thin(run))
    spikes = [p for p in run if p[1] > 51]
    assert len(spikes) >= 10
    assert all((round(x, 1), round(y, 1)) in out for x, y in spikes)


def test_point_beyond_chord_end_is_measured_to_the_segment() -> None:
    # (8, 0.1) is 0.1 from the infinite chord line (0,0)-(5,0) but 3.0 from
    # the chord segment: it must be kept.
    run = [(0.0, 0.0), (8.0, 0.1), (5.0, 0.0)]
    assert thin(run) == ((0.0, 0.0), (8.0, 0.1), (5.0, 0.0))


def test_non_monotone_x_keeps_path_order() -> None:
    run = _non_monotone_x()
    out = thin(run)
    ys = [p[1] for p in out]
    assert ys == sorted(ys)  # y rises along the path; x does not
    xs = [p[0] for p in out]
    assert xs != sorted(xs)  # precondition: x really is non-monotone


@pytest.mark.parametrize("name", sorted(RUNS))
def test_endpoints_kept_rounded(name: str) -> None:
    run = RUNS[name]()
    out = thin(run)
    assert out[0] == (round(run[0][0], COORD_PLACES), round(run[0][1], COORD_PLACES))
    assert out[-1] == (round(run[-1][0], COORD_PLACES), round(run[-1][1], COORD_PLACES))


def test_closed_loop_in_one_window_is_not_collapsed() -> None:
    # 300 points fit one window, so the top-level chord has zero length.
    run = _loop(300)
    assert len(run) <= WINDOW
    assert run[0] == run[-1]  # exactly closed: the chord has zero length
    out = thin(run)
    assert len(out) > 8
    assert _worst(run, out) <= BOUND


def test_short_runs() -> None:
    assert thin([]) == ()
    assert thin([(1.04, 2.06)]) == ((1.0, 2.1),)
    assert thin([(1.04, 2.06), (3.0, 4.0)]) == ((1.0, 2.1), (3.0, 4.0))
    # Two inputs that round to the same point collapse to one.
    assert thin([(1.01, 2.01), (1.04, 1.99)]) == ((1.0, 2.0),)


def test_duplicates_from_rounding_removed() -> None:
    # Only the two forced endpoints survive a run this small, and they
    # collide after rounding.
    run = [(1.01, 2.0), (1.04, 2.0), (1.02, 2.0)]
    assert (round(run[0][0], 1), round(run[0][1], 1)) == (
        round(run[-1][0], 1),
        round(run[-1][1], 1),
    )
    assert thin(run) == ((1.0, 2.0),)


def _lingering_run() -> list[Point]:
    """100 moving points, 1100 jittered within +-0.03 of (198, 0), 100 moving."""
    rng = random.Random(9)
    moving_in = [(2.0 * i, 0.0) for i in range(100)]
    linger = [
        (198 + rng.uniform(-0.03, 0.03), rng.uniform(-0.03, 0.03)) for _ in range(1100)
    ]
    moving_out = [(198 + 2.0 * (i + 1), 0.0) for i in range(100)]
    return moving_in + linger + moving_out


def test_window_boundaries_that_round_together_are_deduplicated() -> None:
    run = _lingering_run()
    assert len(run) == 1300
    # Preconditions: the window boundaries (512, 1024) are distinct input
    # points that round to the same output point, and are consecutive among
    # the points RDP keeps (everything between them is within tolerance).
    assert run[512] != run[1024]
    assert (round(run[512][0], 1), round(run[512][1], 1)) == (198.0, 0.0)
    assert (round(run[1024][0], 1), round(run[1024][1], 1)) == (198.0, 0.0)
    out = thin(run)
    assert all(a != b for a, b in zip(out, out[1:], strict=False))
    assert out == ((0.0, 0.0), (198.0, 0.0), (398.0, 0.0))


def test_output_not_longer_than_input() -> None:
    for name, make in RUNS.items():
        run = make()
        assert len(thin(run)) <= len(run), name
    tiny = [(0.0, 0.0), (1.0, 5.0), (2.0, 0.0)]
    assert len(thin(tiny)) <= 3


def test_deterministic_and_input_untouched() -> None:
    run = _noisy_walk()
    snapshot = list(run)
    a = thin(run)
    b = thin(run)
    assert a == b
    assert run == snapshot
    assert points_attr(a) == points_attr(b)


def test_points_attr_one_place_and_negative_zero() -> None:
    assert points_attr([(1.04, 2.0), (3.25, -0.01), (-0.04, 5.5)]) == "1,2 3.2,0 0,5.5"
    assert points_attr([]) == ""


# --- windowing ---------------------------------------------------------------


def test_imports_are_pure_and_clockless() -> None:
    allowed = {
        "__future__",
        "math",
        "collections.abc",
        "typing",
        "fitdocs.render.charts.svg",
    }
    tree = ast.parse(Path(polyline.__file__).read_text(encoding="utf-8"))
    imported: list[str] = []
    forbidden_calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0
            imported.append(node.module or "")
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", "")
            if name in {"__import__", "import_module"}:
                forbidden_calls.append(name)
        elif isinstance(node, ast.Name) and node.id == "importlib":
            forbidden_calls.append("importlib")
    assert imported, "the walk saw no imports: it is looking at the wrong file"
    assert set(imported) <= allowed, sorted(set(imported) - allowed)
    assert not forbidden_calls


def test_window_constants() -> None:
    assert (THIN_TOLERANCE, polyline.THIN_WINDOW, COORD_PLACES) == (0.3, 512, 1)


def test_window_boundary_point_kept_once() -> None:
    # A zig-zag whose every vertex is a corner far beyond tolerance: nothing
    # may be dropped, and the boundary index (512) is neither lost nor doubled.
    n = 2 * WINDOW + 1
    run = [(float(i), 10.0 * (i % 2)) for i in range(n)]
    out = thin(run)
    assert len(out) == n
    assert out == tuple(run)


def test_window_boundary_is_a_vertex_of_a_straight_run() -> None:
    # Collinear points: unwindowed RDP would keep only the two ends. Windowed,
    # each shared boundary index is kept, so exactly the window ends remain.
    n = 3 * WINDOW + 1
    run = [(float(i), 0.5 * i) for i in range(n)]
    out = thin(run)
    assert out == tuple(
        (float(i), 0.5 * i) for i in (0, WINDOW, 2 * WINDOW, 3 * WINDOW)
    )


# --- linear bound ------------------------------------------------------------


def _convex_arc(n: int) -> list[Point]:
    return [
        (
            1000 * math.cos(math.pi * i / (2 * (n - 1))),
            1000 * math.sin(math.pi * i / (2 * (n - 1))),
        )
        for i in range(n)
    ]


def test_distance_evaluations_at_most_n_times_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n = 100_000
    real = polyline._distance  # noqa: SLF001
    calls = 0

    def counting(p: Point, a: Point, b: Point) -> float:
        nonlocal calls
        calls += 1
        assert calls <= n * WINDOW, "distance evaluations exceed n * WINDOW"
        return real(p, a, b)

    monkeypatch.setattr(polyline, "_distance", counting)
    thin(_convex_arc(n))
    assert 0 < calls <= n * WINDOW


def _count_evaluations(
    monkeypatch: pytest.MonkeyPatch, run: list[Point], window: int | None = None
) -> int:
    if window is not None:
        monkeypatch.setattr(polyline, "THIN_WINDOW", window)
    real = polyline._distance  # noqa: SLF001
    calls = 0

    def counting(p: Point, a: Point, b: Point) -> float:
        nonlocal calls
        calls += 1
        return real(p, a, b)

    monkeypatch.setattr(polyline, "_distance", counting)
    thin(run)
    return calls


def test_production_window_bounds_the_work(monkeypatch: pytest.MonkeyPatch) -> None:
    # A zigzag of growing amplitude, (i, +-i): every split peels one point off
    # an end, so unwindowed RDP is quadratic and exceeds n * 512.
    n = 4000
    run = [(float(i), float(i if i % 2 == 0 else -i)) for i in range(n)]
    windowed = _count_evaluations(monkeypatch, run)
    assert 0 < windowed <= n * WINDOW
    unwindowed = _count_evaluations(monkeypatch, run, 10**9)
    assert unwindowed > n * WINDOW  # precondition: the bound is binding


def test_window_size_bounds_the_work(monkeypatch: pytest.MonkeyPatch) -> None:
    # At the production window of 512 the windowed and unwindowed counts on a convex arc
    # are both far below n * 512, so the bound above cannot tell them apart.
    # A small window can: n * 4 is below the unwindowed count on this arc.
    run = _convex_arc(20_000)
    unwindowed = _count_evaluations(monkeypatch, run, 10**9)
    assert unwindowed > len(run) * 4  # precondition: the bound is binding
    windowed = _count_evaluations(monkeypatch, run, 4)
    assert 0 < windowed <= len(run) * 4


def test_convex_arc_completes_quickly() -> None:
    run = _convex_arc(100_000)
    start = time.perf_counter()
    out = thin(run)
    assert time.perf_counter() - start < 60.0
    assert _worst(run[::97] + [run[-1]], out) <= BOUND

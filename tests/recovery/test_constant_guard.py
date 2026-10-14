"""Numeric literals in the two recovery computation modules."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from typing import cast

import pytest

from fitdocs.recovery import constants

_Site = tuple[str | None, str | None, int | float]
_MODULES = ("constants.py", "baselines.py")
_EXEMPTIONS: dict[str, Counter[_Site]] = {
    "constants.py": Counter(
        {
            ("ROLLING_DAYS", "value", 7): 1,
            ("MIN_ROLLING_VALUES", "value", 3): 1,
            ("BASELINE_DAYS", "value", 60): 1,
            ("MIN_BASELINE_VALUES", "value", 30): 1,
            ("RANGE_SD_MULTIPLE", "value", 0.5): 1,
            ("PLEWS_2013_SPORTS_MED", "year", 2013): 1,
            ("PLEWS_2013_IJSPP", "year", 2013): 1,
            ("PLEWS_2014_IJSPP", "year", 2014): 1,
            ("VESTERINEN_2016", "year", 2016): 1,
            ("BASELINES_VERSION", None, 1): 1,
            (None, None, 1): 1,  # rolling window excludes the judged day for lookback
        }
    ),
    "baselines.py": Counter(
        {
            ("xs", None, 1): 3,  # inclusive range start and reverse iteration
            ("xs", None, 0): 1,  # tuple value slot
            ("ys", None, 0): 2,  # exclusive range stop and tuple value slot
            ("ys", None, 1): 1,  # reverse iteration
            ("sd", None, 1): 1,  # sample denominator
            ("sd", None, 2): 1,  # squared deviations
            (None, "value", 0): 1,  # daily tuple value slot
            (None, "origin", 1): 1,  # daily tuple origin slot
        }
    ),
}


def _numeric_sites(text: str) -> Counter[_Site]:
    tree = ast.parse(text)
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    sites: Counter[_Site] = Counter()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or type(node.value) not in (int, float):
            continue
        target = None
        slot = None
        child: ast.AST = node
        while child in parents:
            parent = parents[child]
            if isinstance(parent, ast.keyword) and slot is None:
                slot = parent.arg
            if isinstance(parent, ast.AnnAssign) and isinstance(
                parent.target, ast.Name
            ):
                target = parent.target.id
                break
            if (
                isinstance(parent, ast.Assign)
                and len(parent.targets) == 1
                and isinstance(parent.targets[0], ast.Name)
            ):
                target = parent.targets[0].id
                break
            child = parent
        sites[(target, slot, cast(int | float, node.value))] += 1
    return sites


def _check_literals(name: str, text: str) -> None:
    found = _numeric_sites(text)
    allowed = _EXEMPTIONS.get(name, Counter())
    assert found == allowed, f"{name}: unexpected/stale numeric sites {found - allowed}"


def _scan_modules(package: Path) -> None:
    scanned = []
    for name in _MODULES:
        path = package / name
        if path.exists():
            scanned.append(name)
            _check_literals(name, path.read_text(encoding="utf-8"))
    assert scanned, "the walk is looking at the wrong directory"


def test_computation_modules_have_no_uncited_literals() -> None:
    _scan_modules(Path(constants.__file__).resolve().parent)


def test_synthetic_uncited_literal_is_rejected() -> None:
    with pytest.raises(AssertionError, match="unexpected/stale numeric"):
        _check_literals("baselines.py", "range_multiple = 0.5")


def test_scan_rejects_an_empty_directory(tmp_path: Path) -> None:
    with pytest.raises(AssertionError, match="wrong directory"):
        _scan_modules(tmp_path)


def test_scan_includes_baselines_when_present(tmp_path: Path) -> None:
    (tmp_path / "baselines.py").write_text("multiple = 0.5", encoding="utf-8")
    with pytest.raises(AssertionError, match="unexpected/stale numeric"):
        _scan_modules(tmp_path)


def test_duplicate_exempted_site_is_rejected() -> None:
    original = Path(constants.__file__).read_text(encoding="utf-8")
    _check_literals("constants.py", original)
    repeated = original.replace("value=0.5,", "value=(0.5 + 0.5),", 1)
    with pytest.raises(AssertionError, match="unexpected/stale numeric"):
        _check_literals("constants.py", repeated)


def test_scan_checks_both_existing_modules(tmp_path: Path) -> None:
    original = Path(constants.__file__).read_text(encoding="utf-8")
    _check_literals("constants.py", original)
    (tmp_path / "constants.py").write_text(original, encoding="utf-8")
    (tmp_path / "baselines.py").write_text("multiple = 0.5", encoding="utf-8")
    with pytest.raises(AssertionError, match="unexpected/stale numeric"):
        _scan_modules(tmp_path)

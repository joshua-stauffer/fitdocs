"""The one unit vocabulary (`fitdocs.units`) and its projection into the index.

Pins chart-kit requirements 2.2, 2.3 and 2.5 against design § UnitVocabulary;
2.1 (the index reads the one list, not a copy) through a subprocess that
truncates `UNITS` before importing `index/schema.py` and a source check of
that module's `UNIT_SUFFIXES` assignment and import; and (16.4, 18.5) the
import guard on `fitdocs/units.py` with its positive control.
"""

from __future__ import annotations

import ast
import dataclasses
import os
import subprocess
import sys
from pathlib import Path

import pytest

from fitdocs import units as units_module
from fitdocs.index.schema import UNIT_SUFFIXES
from fitdocs.units import UNITS, Unit, UnitFamily, unit_for_column, unit_named

Q = UnitFamily.QUANTITY

# The original `UNIT_SUFFIXES` literal with append-only unit amendments.
PRE_CHANGE_UNIT_SUFFIXES: tuple[tuple[str, str], ...] = (
    ("_s_per_km", "seconds per kilometre"),
    ("_local", "local"),
    ("_kn_m", "kilonewtons per metre"),
    ("_kcal", "kilocalories"),
    ("_mps", "metres per second"),
    ("_bpm", "beats per minute"),
    ("_rpm", "revolutions per minute"),
    ("_deg", "degrees"),
    ("_pct", "percent"),
    ("_utc", "UTC"),
    ("_mm", "millimetres"),
    ("_ms", "milliseconds"),
    ("_bw", "body weights"),
    ("_kg", "kilograms"),
    ("_km", "kilometres"),
    ("_m", "metres"),
    ("_s", "seconds"),
    ("_w", "watts"),
    ("_c", "degrees Celsius"),
    ("_ml_per_kg_min", "millilitres per kilogram per minute"),
    ("_brpm", "breaths per minute"),
)

# token, phrase, symbol, family, decimals, spaced (design § UnitVocabulary).
# The design leaves `spaced` as "-" for s_per_km, local, utc and s (families
# PACE, CLOCK, CLOCK, DURATION); those rows take the dataclass default, True.
DESIGN_TABLE: tuple[tuple[str, str, str, UnitFamily, int, bool], ...] = (
    ("s_per_km", "seconds per kilometre", "min/km", UnitFamily.PACE, 0, True),
    ("local", "local", "local time", UnitFamily.CLOCK, 0, True),
    ("kn_m", "kilonewtons per metre", "kN/m", Q, 1, True),
    ("kcal", "kilocalories", "kcal", Q, 0, True),
    ("mps", "metres per second", "m/s", Q, 2, True),
    ("bpm", "beats per minute", "bpm", Q, 0, True),
    ("rpm", "revolutions per minute", "rpm", Q, 0, True),
    ("deg", "degrees", "°", Q, 1, False),
    ("pct", "percent", "%", UnitFamily.PERCENT, 1, False),
    ("utc", "UTC", "UTC", UnitFamily.CLOCK, 0, True),
    ("mm", "millimetres", "mm", Q, 0, True),
    ("ms", "milliseconds", "ms", Q, 0, True),
    ("bw", "body weights", "BW", Q, 2, True),
    ("kg", "kilograms", "kg", Q, 1, True),
    ("km", "kilometres", "km", Q, 1, True),
    ("m", "metres", "m", Q, 0, True),
    ("s", "seconds", "h:mm:ss", UnitFamily.DURATION, 0, True),
    ("w", "watts", "W", Q, 0, True),
    ("c", "degrees Celsius", "°C", Q, 1, True),
    ("ml_per_kg_min", "millilitres per kilogram per minute", "mL/kg/min", Q, 1, True),
    ("brpm", "breaths per minute", "br/min", Q, 1, True),
)


def test_projection_equals_pre_change_literal_in_order() -> None:
    assert len(UNIT_SUFFIXES) == len(PRE_CHANGE_UNIT_SUFFIXES) == 21
    for index, (expected, actual) in enumerate(
        zip(PRE_CHANGE_UNIT_SUFFIXES, UNIT_SUFFIXES, strict=True)
    ):
        assert actual == expected, f"row {index}"
    assert UNIT_SUFFIXES == PRE_CHANGE_UNIT_SUFFIXES


def test_table_has_twenty_one_rows() -> None:
    assert len(UNITS) == len(DESIGN_TABLE) == 21


@pytest.mark.parametrize("index", range(len(DESIGN_TABLE)))
def test_row_matches_design_table(index: int) -> None:
    token, phrase, symbol, family, decimals, spaced = DESIGN_TABLE[index]
    unit = UNITS[index]
    assert unit.token == token
    assert unit.phrase == phrase
    assert unit.symbol == symbol
    assert unit.family is family
    assert unit.decimals == decimals
    assert unit.spaced is spaced


def test_tokens_are_unique() -> None:
    tokens = [u.token for u in UNITS]
    assert len(set(tokens)) == len(tokens) == 21


def test_suffix_is_underscore_plus_token() -> None:
    for unit in UNITS:
        assert unit.suffix == "_" + unit.token


def test_unit_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        UNITS[0].symbol = "x"  # type: ignore[misc]


def test_family_values() -> None:
    assert {f.name: f.value for f in UnitFamily} == {
        "QUANTITY": "quantity",
        "DURATION": "duration",
        "PACE": "pace",
        "PERCENT": "percent",
        "CLOCK": "clock",
    }


def _token(name: str) -> str | None:
    unit = unit_for_column(name)
    return None if unit is None else unit.token


def test_lookup_prefers_most_specific_suffix() -> None:
    # `avg_pace_s_per_km` also ends with `_km`; `leg_spring_stiffness_kn_m`
    # also ends with `_m`; `moving_time_s` ends only with `_s`.
    assert "avg_pace_s_per_km".endswith("_km")
    assert "leg_spring_stiffness_kn_m".endswith("_m")
    assert _token("avg_pace_s_per_km") == "s_per_km"
    assert _token("leg_spring_stiffness_kn_m") == "kn_m"
    assert _token("moving_time_s") == "s"
    assert _token("start_time_local") == "local"


def test_lookup_matches_only_at_the_end_of_the_name() -> None:
    # Each name contains a documented suffix, but not at its end.
    assert _token("avg_hr_bpm_max") is None
    assert _token("km_split_count") is None
    assert _token("pct_rank") is None
    assert _token("_s_per_km_x") is None
    # A trailing suffix still wins when an earlier one sits mid-name.
    assert _token("bpm_to_km") == "km"


def test_lookup_none_when_no_suffix() -> None:
    assert unit_for_column("distance") is None
    assert unit_for_column("") is None


def test_lookup_requires_underscore_boundary() -> None:
    # "distancem" ends with the letter m but not with the suffix "_m".
    assert unit_for_column("distancem") is None


def test_cadence_is_labelled_as_its_suffix_names_it() -> None:
    unit = unit_for_column("cadence_rpm")
    assert unit is not None
    assert unit.symbol == "rpm"
    assert unit.phrase == "revolutions per minute"


def test_lookup_returns_the_table_row() -> None:
    for unit in UNITS:
        assert unit_for_column("some_col" + unit.suffix) is unit


def test_unit_named_round_trips_every_token() -> None:
    for unit in UNITS:
        assert unit_named(unit.token) is unit


def test_unit_named_rejects_non_tokens() -> None:
    assert unit_named("spm") is None
    assert unit_named("_km") is None
    assert unit_named("") is None


def test_unit_type_is_exported() -> None:
    assert all(isinstance(u, Unit) for u in UNITS)


# --- leaf-import guard -------------------------------------------------------


def _imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                modules.add("." * node.level + (node.module or ""))
            elif node.module is not None:
                modules.add(node.module)
    return modules


def _non_stdlib(source: str) -> set[str]:
    return {
        name
        for name in _imported_modules(source)
        if name.startswith(".") or name.split(".")[0] not in sys.stdlib_module_names
    }


def test_units_imports_only_the_standard_library() -> None:
    assert units_module.__file__ is not None
    seen = _imported_modules(Path(units_module.__file__).read_text(encoding="utf-8"))
    # positive control: the walk saw the module's own `from enum import ...`
    assert "enum" in seen
    # the exact set, so a dynamic import cannot hide behind the stdlib check
    assert seen == {"__future__", "dataclasses", "enum", "typing"}
    tree = ast.parse(Path(units_module.__file__).read_text(encoding="utf-8"))
    assert not [
        n for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id == "__import__"
    ]
    assert _non_stdlib(Path(units_module.__file__).read_text(encoding="utf-8")) == set()


def test_import_guard_rejects_a_fitdocs_import() -> None:
    assert _non_stdlib("import fitdocs.model\n") == {"fitdocs.model"}
    assert _non_stdlib("from fitdocs import model\n") == {"fitdocs"}
    assert _non_stdlib("from . import x\n") == {"."}
    assert _non_stdlib("import enum\nfrom dataclasses import dataclass\n") == set()


# --- the index reads the one list (2.1) --------------------------------------


def test_index_schema_projects_units_without_a_second_copy() -> None:
    import fitdocs.index.schema as schema_module

    assert schema_module.__file__ is not None
    tree = ast.parse(Path(schema_module.__file__).read_text(encoding="utf-8"))
    values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "UNIT_SUFFIXES"
        and node.value is not None
    ]
    assert len(values) == 1
    nodes = list(ast.walk(values[0]))
    assert not [
        n for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]
    assert any(isinstance(n, ast.Name) and n.id == "UNITS" for n in nodes)
    imported = [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "fitdocs.units"
        and not node.level
        for alias in node.names
    ]
    assert imported == ["UNITS"]


def test_index_unit_suffixes_follow_a_truncated_units_table() -> None:
    assert units_module.__file__ is not None
    src_root = str(Path(units_module.__file__).resolve().parents[1])
    code = (
        "import fitdocs.units as u\n"
        "u.UNITS = u.UNITS[:2]\n"
        "import fitdocs.index.schema as s\n"
        "print(s.UNIT_SUFFIXES)\n"
    )
    env = {**os.environ, "PYTHONPATH": src_root}
    out = subprocess.run(
        [sys.executable, "-B", "-c", code],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout.strip()
    assert out == "(('_s_per_km', 'seconds per kilometre'), ('_local', 'local'))"

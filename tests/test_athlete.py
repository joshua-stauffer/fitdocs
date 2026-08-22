"""Tests for the read-only athlete-inputs reader (Req 8.3).

These exercise :func:`fitdocs.athlete.load_athlete_inputs`, the strictly
read-only mapping from an optional ``<data_root>/athlete.toml`` onto fit-ingest
:class:`~fitdocs.AthleteInputs` / :class:`~fitdocs.ZoneSpec` (design:
AthleteInputsReader, ``src/fitdocs/athlete.py``).

Two invariants govern every case:

* *Absent is not an error.* A missing ``athlete.toml`` yields ``None`` -- the
  athlete-inputs source is optional (Req 8.3).
* *Malformed fails loudly.* Invalid TOML, a wrong value type, a boolean where a
  number is expected, or non-ascending / empty zone dividers all raise
  :class:`~fitdocs.athlete.AthleteFileError`. Silently dropping a bad zone would
  change the rendered document invisibly, so nothing is ever swallowed.

The reader is read-only *by construction*: it never creates the file, never
prompts, and writes nothing on any path (asserted against a tree snapshot).
Unknown keys are ignored so training-load can extend the file later without
breaking this layer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs import AthleteInputs, ZoneSpec
from fitdocs.athlete import (
    ATHLETE_FILE,
    ATHLETE_SCHEMA_VERSION,
    VERSION_KEY,
    AthleteFileError,
    check_schema_version,
    load_athlete_inputs,
)
from fitdocs.benchmarks import BenchmarkKind

# --- helpers ----------------------------------------------------------------


def _write_athlete(data_root: Path, content: str) -> Path:
    """Write ``<data_root>/athlete.toml`` with *content* and return its path."""
    path = data_root / ATHLETE_FILE
    path.write_text(content)
    return path


def _snapshot(root: Path) -> set[Path]:
    """Every path under *root*, for asserting the reader wrote nothing."""
    return set(root.rglob("*"))


# --- Absent file -> None (never an error) (Req 8.3) -------------------------


def test_absent_file_returns_none(tmp_path: Path) -> None:
    """No ``athlete.toml`` at all -> ``None``; absence is not an error (Req 8.3)."""
    assert load_athlete_inputs(tmp_path) is None


def test_absent_file_writes_nothing(tmp_path: Path) -> None:
    """Reading an absent file never creates it or writes anything (Req 8.3)."""
    before = _snapshot(tmp_path)

    assert load_athlete_inputs(tmp_path) is None

    assert _snapshot(tmp_path) == before


# --- Complete file -> full AthleteInputs (Req 8.3) --------------------------


def test_complete_file_maps_all_thresholds_and_zones(tmp_path: Path) -> None:
    """A complete file maps every threshold and all three zone specs (Req 8.3)."""
    _write_athlete(
        tmp_path,
        """
        ftp_watts = 250.0
        resting_hr_bpm = 45
        max_hr_bpm = 190
        hr_zones = [120, 140, 160, 175]
        power_zones = [150, 200, 250, 300]
        pace_zones = [240, 270, 300, 330]
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(
        ftp_watts=250.0,
        resting_hr_bpm=45,
        max_hr_bpm=190,
        hr_zones=ZoneSpec(dividers=(120.0, 140.0, 160.0, 175.0)),
        power_zones=ZoneSpec(dividers=(150.0, 200.0, 250.0, 300.0)),
        pace_zones=ZoneSpec(dividers=(240.0, 270.0, 300.0, 330.0)),
    )
    # Dividers are mapped verbatim (and normalized to floats) onto each channel.
    assert result is not None
    assert result.hr_zones is not None
    assert result.hr_zones.dividers == (120.0, 140.0, 160.0, 175.0)
    assert result.power_zones is not None
    assert result.power_zones.dividers == (150.0, 200.0, 250.0, 300.0)
    assert result.pace_zones is not None
    assert result.pace_zones.dividers == (240.0, 270.0, 300.0, 330.0)


def test_complete_file_writes_nothing(tmp_path: Path) -> None:
    """Reading a valid file mutates nothing on disk (read-only, Req 8.3)."""
    _write_athlete(tmp_path, "ftp_watts = 250.0\nresting_hr_bpm = 45\n")
    before = _snapshot(tmp_path)

    load_athlete_inputs(tmp_path)

    assert _snapshot(tmp_path) == before


def test_integer_ftp_is_accepted_as_a_number(tmp_path: Path) -> None:
    """``ftp_watts`` accepts a TOML integer and normalizes it to float (Req 8.3)."""
    _write_athlete(tmp_path, "ftp_watts = 250\n")

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(ftp_watts=250.0)


# --- Partial file -> present keys mapped, rest None (Req 8.3) ----------------


def test_partial_file_maps_only_present_keys(tmp_path: Path) -> None:
    """Only the keys present are mapped; every other field stays ``None`` (Req 8.3)."""
    _write_athlete(
        tmp_path,
        """
        max_hr_bpm = 188
        hr_zones = [110, 130, 150, 170]
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(
        max_hr_bpm=188,
        hr_zones=ZoneSpec(dividers=(110.0, 130.0, 150.0, 170.0)),
    )
    assert result is not None
    assert result.ftp_watts is None
    assert result.resting_hr_bpm is None
    assert result.power_zones is None
    assert result.pace_zones is None


def test_empty_file_yields_all_none_inputs(tmp_path: Path) -> None:
    """A present-but-empty file yields inputs with every field ``None`` (Req 8.3)."""
    _write_athlete(tmp_path, "")

    assert load_athlete_inputs(tmp_path) == AthleteInputs()


# --- Unknown keys ignored for forward compatibility (Req 8.3) ---------------


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    """Unknown keys (training-load's future fields) are ignored, no error (Req 8.3)."""
    _write_athlete(
        tmp_path,
        """
        ftp_watts = 260.0
        methodology = "some-methodology"
        weekly_target = 350
        [some_future_table]
        anything = "goes"
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(ftp_watts=260.0)


# --- Malformed TOML -> AthleteFileError (Req 8.3) ---------------------------


def test_malformed_toml_raises(tmp_path: Path) -> None:
    """Syntactically invalid TOML raises AthleteFileError, not a raw parse error."""
    _write_athlete(tmp_path, "ftp_watts = = 250\nthis is not toml")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


# --- Wrong value types -> AthleteFileError (Req 8.3) ------------------------


def test_string_threshold_raises(tmp_path: Path) -> None:
    """A non-numeric ``ftp_watts`` raises AthleteFileError (Req 8.3)."""
    _write_athlete(tmp_path, 'ftp_watts = "fast"\n')

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_float_where_integer_expected_raises(tmp_path: Path) -> None:
    """An integer threshold rejects a TOML float (strict typing, Req 8.3)."""
    _write_athlete(tmp_path, "resting_hr_bpm = 45.5\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_zone_not_a_list_raises(tmp_path: Path) -> None:
    """A zone key that is a scalar rather than a list raises (Req 8.3)."""
    _write_athlete(tmp_path, "hr_zones = 150\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_zone_list_with_non_number_raises(tmp_path: Path) -> None:
    """A zone list containing a non-number raises rather than dropping it (Req 8.3)."""
    _write_athlete(tmp_path, 'hr_zones = [120, "x", 160]\n')

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


# --- Non-ascending / empty dividers -> AthleteFileError (Req 8.3) -----------


def test_non_ascending_dividers_raise(tmp_path: Path) -> None:
    """Descending dividers surface ZoneSpec's ValueError as an error (Req 8.3)."""
    _write_athlete(tmp_path, "hr_zones = [150, 120]\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_non_strictly_ascending_dividers_raise(tmp_path: Path) -> None:
    """Equal adjacent dividers are not strictly ascending and raise (Req 8.3)."""
    _write_athlete(tmp_path, "power_zones = [200, 200, 250]\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_empty_zone_list_raises(tmp_path: Path) -> None:
    """An empty zone list is not a valid ZoneSpec and raises (Req 8.3)."""
    _write_athlete(tmp_path, "pace_zones = []\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


# --- bool-is-int guard: reject a TOML boolean where a number is expected ----


def test_bool_where_integer_expected_raises(tmp_path: Path) -> None:
    """A TOML boolean is never accepted as an int threshold (bool-is-int guard)."""
    _write_athlete(tmp_path, "resting_hr_bpm = true\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_bool_where_number_expected_raises(tmp_path: Path) -> None:
    """A TOML boolean is never accepted as a float threshold (bool-is-int guard)."""
    _write_athlete(tmp_path, "ftp_watts = true\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_bool_inside_zone_list_raises(tmp_path: Path) -> None:
    """A TOML boolean divider is rejected, never coerced to 0/1 (bool-is-int guard)."""
    _write_athlete(tmp_path, "hr_zones = [120, true, 160]\n")

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


# --- Loud failures still write nothing (read-only by construction) ----------


def test_malformed_file_writes_nothing(tmp_path: Path) -> None:
    """Even on a raised error the reader writes nothing (read-only, Req 8.3)."""
    _write_athlete(tmp_path, "hr_zones = [150, 120]\n")
    before = _snapshot(tmp_path)

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)

    assert _snapshot(tmp_path) == before


# --- Schema version guard (Req 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 9.1) ----------


def test_absent_version_key_defaults_to_earliest_version(tmp_path: Path) -> None:
    """No ``profile_version`` key at all is treated as version 1 (Req 1.8)."""
    path = tmp_path / ATHLETE_FILE
    assert check_schema_version({}, path) == 1


def test_explicit_earliest_version_is_accepted(tmp_path: Path) -> None:
    """An explicit ``profile_version = 1`` is accepted and returned as-is (Req 1.6)."""
    path = tmp_path / ATHLETE_FILE
    assert check_schema_version({VERSION_KEY: 1}, path) == 1


def test_current_supported_version_is_accepted(tmp_path: Path) -> None:
    """The current supported version is accepted and returned as-is (Req 1.6)."""
    path = tmp_path / ATHLETE_FILE
    assert (
        check_schema_version({VERSION_KEY: ATHLETE_SCHEMA_VERSION}, path)
        == ATHLETE_SCHEMA_VERSION
    )


def test_non_integer_version_raises(tmp_path: Path) -> None:
    """A string-valued ``profile_version`` is refused (not a range violation).

    Req 1.7."""
    path = tmp_path / ATHLETE_FILE

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: "thirty-one"}, path)

    message = str(exc_info.value)
    assert str(path) in message
    # Normalize away the path so a digit embedded in the pytest tmp dir (e.g.
    # ".../pytest-2286/...") can never be mistaken for a token in the message
    # body itself.
    body = message.replace(str(path), "<path>")
    assert "thirty-one" in body
    assert f"1 and {ATHLETE_SCHEMA_VERSION}" in body


def test_boolean_version_raises(tmp_path: Path) -> None:
    """A boolean ``profile_version`` is refused even though ``bool`` subclasses
    ``int`` and its value (``True`` == ``1``) would otherwise pass every range
    check (Req 1.7)."""
    path = tmp_path / ATHLETE_FILE

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: True}, path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert "True" in body
    assert f"1 and {ATHLETE_SCHEMA_VERSION}" in body


def test_sub_minimum_version_raises(tmp_path: Path) -> None:
    """A ``profile_version`` below 1 is refused (Req 1.7)."""
    path = tmp_path / ATHLETE_FILE

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: -31337}, path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert "-31337" in body
    assert f"1 and {ATHLETE_SCHEMA_VERSION}" in body


def test_zero_version_raises(tmp_path: Path) -> None:
    """A ``profile_version`` of exactly 0 -- the value directly on the ``< 1``
    boundary -- is refused (Req 1.7)."""
    path = tmp_path / ATHLETE_FILE

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: 0}, path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert "0" in body
    assert f"1 and {ATHLETE_SCHEMA_VERSION}" in body


def test_above_supported_version_raises(tmp_path: Path) -> None:
    """A ``profile_version`` newer than what this fitdocs supports is refused.

    Req 1.7."""
    path = tmp_path / ATHLETE_FILE
    declared = ATHLETE_SCHEMA_VERSION + 997

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: declared}, path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert str(declared) in body
    assert f"({ATHLETE_SCHEMA_VERSION})" in body


def test_one_past_supported_version_raises(tmp_path: Path) -> None:
    """A ``profile_version`` of ``ATHLETE_SCHEMA_VERSION + 1`` -- the value
    directly on the ``> ATHLETE_SCHEMA_VERSION`` boundary -- is refused
    (Req 1.7)."""
    path = tmp_path / ATHLETE_FILE
    declared = ATHLETE_SCHEMA_VERSION + 1

    with pytest.raises(AthleteFileError) as exc_info:
        check_schema_version({VERSION_KEY: declared}, path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert str(declared) in body
    assert f"({ATHLETE_SCHEMA_VERSION})" in body


def test_load_athlete_inputs_refuses_unrecognized_version(tmp_path: Path) -> None:
    """``load_athlete_inputs`` refuses a file whose declared version is newer
    than this fitdocs supports (Req 1.7)."""
    _write_athlete(
        tmp_path,
        f"profile_version = {ATHLETE_SCHEMA_VERSION + 997}\nftp_watts = 250.0\n",
    )

    with pytest.raises(AthleteFileError):
        load_athlete_inputs(tmp_path)


def test_load_athlete_inputs_reads_normally_with_no_declared_version(
    tmp_path: Path,
) -> None:
    """A file with no ``profile_version`` key still reads its flat keys (Req 1.8)."""
    _write_athlete(tmp_path, "ftp_watts = 250.0\n")

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(ftp_watts=250.0)


def test_benchmarks_present_under_older_declared_version_still_read(
    tmp_path: Path,
) -> None:
    """A ``[benchmarks]`` table under an old declared version does not block the
    flat keys this reader projects (Req 1.6, 1.10)."""
    _write_athlete(
        tmp_path,
        """
        profile_version = 1
        ftp_watts = 250.0

        [benchmarks]
        anything = "goes"
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result == AthleteInputs(ftp_watts=250.0)


# --- Req 1.11 prohibition clause: override/reinterpret (flat key present) --
#
# Only three of the five ``BenchmarkKind`` quantities have a corresponding
# flat :class:`AthleteInputs` field at all -- ``ftp_watts``, ``resting_hr_bpm``
# and ``max_hr_bpm``. ``lthr_bpm`` and ``threshold_pace_s_per_km`` have no flat
# counterpart in :class:`AthleteInputs` (see ``src/fitdocs/metrics/types.py``),
# so there is no flat-key code path for this reader to derive/override/
# reinterpret them from *at all* -- structurally, not merely untested.
#
# Zone keys (``hr_zones``/``power_zones``/``pace_zones``): no ``BenchmarkKind``
# *is* a zone quantity (:mod:`fitdocs.benchmarks` defines five scalar kinds
# only), but that does not mean no benchmark can *produce* one -- a zone set
# computed as percentages of a benchmarked max HR is the textbook way HR
# zones are built, and Req 1.11 names zones *first* among the flat keys it
# protects. That derivation is exactly what the whole-``AthleteInputs``
# equality assertion below rules out: every case here constructs a benchmark
# for one scalar quantity and asserts the *entire* result equals an
# ``AthleteInputs`` with every other field -- including all three zone
# fields -- at its untouched default, so a reader that derived a zone from
# the benchmarked value under test would fail here, not slip through unseen.
_FLAT_QUANTITY_ATTRS = {kind.value for kind in BenchmarkKind} & set(
    AthleteInputs.__dataclass_fields__
)


def test_flat_quantity_attrs_cover_every_benchmark_kind_with_a_flat_counterpart() -> (
    None
):
    """Self-maintaining guard for the parametrized cases below: if a future
    ``BenchmarkKind`` gains a flat ``AthleteInputs`` counterpart, this reds
    before the new quantity could silently ship unpinned."""
    assert {"ftp_watts", "resting_hr_bpm", "max_hr_bpm"} == _FLAT_QUANTITY_ATTRS


_OVERRIDE_CASES = [
    # (attr, benchmark scope, flat literal, expected flat value, benchmark literal)
    pytest.param(
        "ftp_watts", "run", "250.0", 250.0, "300.0", id="ftp_watts-flat-lt-benchmark"
    ),
    pytest.param(
        "ftp_watts", "run", "300.0", 300.0, "250.0", id="ftp_watts-flat-gt-benchmark"
    ),
    pytest.param(
        "resting_hr_bpm",
        "athlete",
        "45",
        45,
        "60",
        id="resting_hr_bpm-flat-lt-benchmark",
    ),
    pytest.param(
        "resting_hr_bpm",
        "athlete",
        "60",
        60,
        "45",
        id="resting_hr_bpm-flat-gt-benchmark",
    ),
    pytest.param(
        "max_hr_bpm", "athlete", "188", 188, "200", id="max_hr_bpm-flat-lt-benchmark"
    ),
    pytest.param(
        "max_hr_bpm", "athlete", "200", 200, "188", id="max_hr_bpm-flat-gt-benchmark"
    ),
]


@pytest.mark.parametrize(
    ("attr", "scope", "flat_literal", "expected", "benchmark_literal"), _OVERRIDE_CASES
)
def test_flat_key_not_overridden_or_reinterpreted_by_benchmark(
    tmp_path: Path,
    attr: str,
    scope: str,
    flat_literal: str,
    expected: float,
    benchmark_literal: str,
) -> None:
    """A flat threshold key is never *overridden* or *reinterpreted* from a
    ``[benchmarks]`` entry for the same quantity when the flat key is present
    (Req 1.11, prohibition clause). Covers the three quantities that have a
    flat :class:`AthleteInputs` counterpart -- ``ftp_watts``, ``resting_hr_bpm``,
    ``max_hr_bpm`` -- in *both* value directions: each quantity appears once
    with the flat value below the benchmark's and once above. A single
    direction only catches an override that always prefers the benchmark; a
    monotonic *reinterpretation* such as ``min(flat, benchmark)`` or
    ``max(flat, benchmark)`` would still coincidentally reproduce the flat
    value in one direction, so both directions are required to rule out
    either shape -- neither can hide behind the other.

    Asserts *whole-dataclass* equality, not only the benchmarked attribute:
    a per-attribute assertion alone would not notice a benchmark used to
    derive a *different* field (e.g. a zone set built from a benchmarked max
    HR), so every other field is pinned at its untouched default too."""
    assert attr in _FLAT_QUANTITY_ATTRS
    key = attr  # BenchmarkKind's TOML spelling equals AthleteInputs' field name here.
    _write_athlete(
        tmp_path,
        f"""
        profile_version = 2
        {key} = {flat_literal}

        [[benchmarks.{scope}.{key}]]
        value = {benchmark_literal}
        measured_on = 2024-01-01
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result is not None
    assert getattr(result, attr) == expected, "the benchmarked field itself"
    assert result == AthleteInputs(**{attr: expected})


# --- Req 1.11 prohibition clause: derive (flat key absent) ------------------


@pytest.mark.parametrize(
    ("attr", "scope", "benchmark_literal"),
    [
        pytest.param("ftp_watts", "run", "285.0", id="ftp_watts"),
        pytest.param("resting_hr_bpm", "athlete", "50", id="resting_hr_bpm"),
        pytest.param("max_hr_bpm", "athlete", "200", id="max_hr_bpm"),
    ],
)
def test_absent_flat_key_is_not_derived_from_a_benchmark_of_the_same_quantity(
    tmp_path: Path, attr: str, scope: str, benchmark_literal: str
) -> None:
    """No flat key is on file at all -- only a ``[benchmarks]`` entry for the
    same quantity -- and the corresponding :class:`AthleteInputs` field stays
    ``None`` rather than being *derived* from it (Req 1.11, prohibition
    clause). This is a distinct code path from the override tests above: an
    implementation could correctly prefer an existing flat value (passing
    every override case) while still falling back to deriving one from the
    benchmark only when the flat key is wholly absent -- a mutation reachable
    by no fixture that always seeds both keys.

    Asserts *whole-dataclass* equality, not only the benchmarked attribute,
    for the same reason as the override cases above: a per-attribute
    assertion would not notice a benchmark used to derive a *different*
    absent field (e.g. a zone set), only the one under test."""
    assert attr in _FLAT_QUANTITY_ATTRS
    key = attr
    _write_athlete(
        tmp_path,
        f"""
        profile_version = 2

        [[benchmarks.{scope}.{key}]]
        value = {benchmark_literal}
        measured_on = 2024-01-01
        """,
    )

    result = load_athlete_inputs(tmp_path)

    assert result is not None
    assert getattr(result, attr) is None, "the benchmarked field itself"
    assert result == AthleteInputs()


def test_data_root_is_byte_identical_after_reading_an_existing_file(
    tmp_path: Path,
) -> None:
    """Reading an existing, valid file changes not one byte on disk (Req 9.1).

    The observable is that the whole *data root* is byte-identical, not just
    the file the reader parsed -- so this snapshots the tree (structure, via
    ``_snapshot``) and every file's bytes (content), not only ``athlete.toml``.
    """
    path = _write_athlete(
        tmp_path, "profile_version = 1\nftp_watts = 250.0\nresting_hr_bpm = 45\n"
    )
    # An unrelated sibling file, included in the tree snapshot below.
    sibling = tmp_path / "notes.md"
    sibling.write_text("unrelated data-root content\n")

    before_tree = _snapshot(tmp_path)
    before_bytes = {p: p.read_bytes() for p in before_tree if p.is_file()}

    load_athlete_inputs(tmp_path)

    assert _snapshot(tmp_path) == before_tree
    after_bytes = {p: p.read_bytes() for p in before_tree if p.is_file()}
    assert after_bytes == before_bytes
    assert path.read_bytes() == before_bytes[path]
    assert sibling.read_bytes() == before_bytes[sibling]


def test_version_guard_runs_before_any_field_is_projected(tmp_path: Path) -> None:
    """``load_athlete_inputs`` refuses an unrecognized declared version before
    projecting any field -- even when every flat key is also malformed, the
    raised error names only the version, not any field (Req 1.7)."""
    declared = ATHLETE_SCHEMA_VERSION + 997
    path = _write_athlete(
        tmp_path,
        f"""
        profile_version = {declared}
        ftp_watts = "not-a-number"
        resting_hr_bpm = "not-a-number"
        max_hr_bpm = "not-a-number"
        hr_zones = "not-a-list"
        power_zones = "not-a-list"
        pace_zones = "not-a-list"
        """,
    )

    with pytest.raises(AthleteFileError) as exc_info:
        load_athlete_inputs(tmp_path)

    message = str(exc_info.value)
    assert str(path) in message
    body = message.replace(str(path), "<path>")
    assert VERSION_KEY in body
    assert str(declared) in body
    for field in (
        "ftp_watts",
        "resting_hr_bpm",
        "max_hr_bpm",
        "hr_zones",
        "power_zones",
        "pace_zones",
    ):
        assert field not in body


def test_version_two_is_the_newest_schema_this_fitdocs_accepts(
    tmp_path: Path,
) -> None:
    """``ATHLETE_SCHEMA_VERSION`` is pinned to 2; that value is accepted and one
    past it is refused (Req 1.6, 1.7)."""
    path = tmp_path / ATHLETE_FILE

    assert ATHLETE_SCHEMA_VERSION == 2
    assert check_schema_version({VERSION_KEY: 2}, path) == 2

    with pytest.raises(AthleteFileError):
        check_schema_version({VERSION_KEY: 3}, path)

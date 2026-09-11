"""Tests for the athlete profile store (task 1.4, Req 2.1-2.7).

The store owns the full lifecycle of ``<data_root>/athlete.toml``: an absent
file reads as an empty profile (never an error, Req 2.3); the first persisted
answer creates the file and every save stamps ``profile_version`` (Req 2.1,
2.2); unmanaged keys and whole tables survive a rewrite verbatim (Req 2.5);
methodology fields are scoped to a table named after their calculator (Req
2.7); values are validated against the declaring :class:`AthleteField` before
persisting (Req 2.6); and malformed content or a non-numeric value at an
accessed key fails loudly as a :class:`ProfileError` (Req 2.4).

The critical seam these tests guard: an ``int``-kind field MUST serialize as a
TOML *integer*, never a float, because the read-only workout-docs reader
(:func:`fitdocs.athlete.load_athlete_inputs`) strictly rejects a float where it
expects an int. So the raw written text is asserted, not just the round-trip.
"""

from __future__ import annotations

import copy
import tomllib
from datetime import date
from pathlib import Path

import pytest
import tomli_w

from fitdocs import Sport
from fitdocs.athlete import ATHLETE_SCHEMA_VERSION
from fitdocs.benchmarks import (
    ATHLETE_SCOPE,
    Benchmark,
    BenchmarkKind,
    BenchmarkSet,
)
from fitdocs.load.profile import (
    PROFILE_FILENAME,
    AthleteProfile,
    ProfileError,
    _canonicalize_benchmarks_region,
    load_profile,
    save_profile,
)
from fitdocs.load.types import AthleteField

# --- field declarations used to drive validated writes ---------------------
MAX_HR = AthleteField(
    key="max_hr_bpm",
    label="Tested max HR",
    kind="int",
    minimum=120,
    maximum=220,
)
HPL = AthleteField(
    key="acme.hpl",
    label="Acme Performance Level",
    kind="int",
    minimum=1,
    maximum=69,
)
FTP = AthleteField(
    key="ftp_watts",
    label="FTP",
    kind="float",
    minimum=50,
    maximum=600,
)
UNBOUNDED_INT = AthleteField(
    key="probe.count",
    label="Probe count",
    kind="int",
    minimum=None,
    maximum=None,
)


# --- lifecycle: absent file (Req 2.3) --------------------------------------
def test_absent_file_reads_as_empty_profile(tmp_path: Path) -> None:
    profile = load_profile(tmp_path)

    assert profile.data == {}
    assert profile.get_number("max_hr_bpm") is None
    assert profile.get_number("acme.hpl") is None
    # Reading must never create the file.
    assert not (tmp_path / PROFILE_FILENAME).exists()


# --- lifecycle: first save creates + stamps version (Req 2.1, 2.2) ---------
def test_save_creates_file_with_version_and_round_trips(tmp_path: Path) -> None:
    profile = load_profile(tmp_path).with_value(MAX_HR, 200)
    save_profile(tmp_path, profile)

    path = tmp_path / PROFILE_FILENAME
    assert path.is_file()
    assert f"profile_version = {ATHLETE_SCHEMA_VERSION}" in path.read_text()

    reloaded = load_profile(tmp_path)
    assert reloaded.get_number("max_hr_bpm") == 200.0
    assert reloaded.get_number("profile_version") == float(ATHLETE_SCHEMA_VERSION)


# --- methodology scoping (Req 2.7) -----------------------------------------
def test_methodology_field_scoped_to_named_table(tmp_path: Path) -> None:
    profile = load_profile(tmp_path).with_value(HPL, 42)
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    # It lands under [acme] as hpl, not as a flat "acme.hpl" key.
    assert raw["acme"] == {"hpl": 42}
    assert load_profile(tmp_path).get_number("acme.hpl") == 42.0


def test_different_calculator_ids_do_not_collide(tmp_path: Path) -> None:
    other = AthleteField(
        key="garmin.hpl", label="Garmin HPL", kind="int", minimum=1, maximum=69
    )
    profile = load_profile(tmp_path).with_value(HPL, 42).with_value(other, 7)
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert raw["acme"]["hpl"] == 42
    assert raw["garmin"]["hpl"] == 7


# --- unknown-key preservation (Req 2.5) ------------------------------------
def test_unknown_keys_and_tables_preserved_on_rewrite(tmp_path: Path) -> None:
    seed = (
        "max_hr_bpm = 195\n"
        "hr_zones = [120.0, 140.0, 160.0, 180.0]\n"
        'custom_top = "keep me"\n'
        "\n"
        "[other]\n"
        'note = "survives"\n'
        "value = 3\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path).with_value(HPL, 42)
    save_profile(tmp_path, profile)

    raw = tomllib.loads(path.read_text())
    # Every seeded key/table survives verbatim...
    assert raw["max_hr_bpm"] == 195
    assert raw["hr_zones"] == [120.0, 140.0, 160.0, 180.0]
    assert raw["custom_top"] == "keep me"
    assert raw["other"] == {"note": "survives", "value": 3}
    # ...and the new managed values are present alongside them.
    assert raw["acme"]["hpl"] == 42
    assert raw["profile_version"] == ATHLETE_SCHEMA_VERSION


# --- int serialization seam (Req 2.5, workout-docs read contract) ----------
def test_int_field_serializes_as_toml_integer(tmp_path: Path) -> None:
    profile = load_profile(tmp_path).with_value(MAX_HR, 200).with_value(HPL, 42)
    save_profile(tmp_path, profile)

    text = (tmp_path / PROFILE_FILENAME).read_text()
    # Raw text: a bare integer, never a float literal (the seam workout-docs
    # reads strictly rejects a float where it wants an int).
    assert "max_hr_bpm = 200" in text
    assert "200.0" not in text
    assert "hpl = 42" in text
    assert "42.0" not in text

    raw = tomllib.loads(text)
    assert isinstance(raw["max_hr_bpm"], int)
    assert not isinstance(raw["max_hr_bpm"], bool)
    assert isinstance(raw["acme"]["hpl"], int)


def test_float_field_serializes_as_toml_float(tmp_path: Path) -> None:
    profile = load_profile(tmp_path).with_value(FTP, 250)
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert isinstance(raw["ftp_watts"], float)
    assert raw["ftp_watts"] == 250.0


# --- validation rejection: nothing persisted (Req 2.6) ---------------------
def test_value_below_minimum_rejected_and_nothing_persisted(tmp_path: Path) -> None:
    base = load_profile(tmp_path)

    with pytest.raises(ValueError):
        base.with_value(MAX_HR, 119)

    assert base.data == {}
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_value_above_maximum_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_profile(tmp_path).with_value(MAX_HR, 221)
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_non_integral_value_for_int_field_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_profile(tmp_path).with_value(MAX_HR, 199.5)
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_bool_value_rejected_even_though_bool_is_int(tmp_path: Path) -> None:
    # An unbounded int field so only the bool guard (not a range check) can fire.
    with pytest.raises(ValueError):
        load_profile(tmp_path).with_value(UNBOUNDED_INT, True)
    assert not (tmp_path / PROFILE_FILENAME).exists()


# --- loud failure on malformed / non-numeric content (Req 2.4) -------------
def test_malformed_toml_raises_profile_error(tmp_path: Path) -> None:
    (tmp_path / PROFILE_FILENAME).write_text("this is = = not valid toml [[[")

    with pytest.raises(ProfileError) as exc:
        load_profile(tmp_path)

    assert PROFILE_FILENAME in str(exc.value)


def test_get_number_on_non_numeric_value_raises_naming_the_key(tmp_path: Path) -> None:
    (tmp_path / PROFILE_FILENAME).write_text('max_hr_bpm = true\nname = "josh"\n')

    # load_profile must NOT eagerly validate every value...
    profile = load_profile(tmp_path)

    # ...but accessing a non-numeric value is the loud config-error path.
    with pytest.raises(ProfileError) as exc_bool:
        profile.get_number("max_hr_bpm")
    assert "max_hr_bpm" in str(exc_bool.value)

    with pytest.raises(ProfileError) as exc_str:
        profile.get_number("name")
    assert "name" in str(exc_str.value)


# --- atomic write (Req 2.1, 2.5) -------------------------------------------
def test_save_leaves_no_temp_files_and_parses_cleanly(tmp_path: Path) -> None:
    profile = load_profile(tmp_path).with_value(MAX_HR, 200)
    save_profile(tmp_path, profile)

    names = sorted(p.name for p in tmp_path.iterdir())
    assert names == [PROFILE_FILENAME]
    assert not any(p.name.endswith(".tmp") for p in tmp_path.iterdir())
    # The single surviving file parses cleanly.
    tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())


def test_save_replaces_existing_file_wholly(tmp_path: Path) -> None:
    first = load_profile(tmp_path).with_value(MAX_HR, 200).with_value(HPL, 42)
    save_profile(tmp_path, first)

    # A fresh document that drops the acme table entirely.
    save_profile(tmp_path, AthleteProfile(data={"max_hr_bpm": 190}))

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert raw["max_hr_bpm"] == 190
    assert "acme" not in raw
    assert raw["profile_version"] == ATHLETE_SCHEMA_VERSION


# --- immutability (no-mutation contract) -----------------------------------
def test_with_value_returns_new_object_and_deep_copies(tmp_path: Path) -> None:
    base = AthleteProfile(data={"max_hr_bpm": 195, "other": {"k": 1}})

    updated = base.with_value(HPL, 42)

    assert updated is not base
    # The original's data is untouched...
    assert base.data == {"max_hr_bpm": 195, "other": {"k": 1}}
    assert "acme" not in base.data
    # ...and nested tables were deep-copied, not shared.
    assert base.data["other"] is not updated.data["other"]
    # The update carries both the old and the new values.
    assert updated.get_number("max_hr_bpm") == 195.0
    assert updated.get_number("acme.hpl") == 42.0


# --- dated-measurement write path (task 3.2, Req 1.1, 6.1-6.9, 9.2-9.4) -----
def test_with_benchmark_round_trip_upserts_sorts_and_preserves(
    tmp_path: Path,
) -> None:
    seed = (
        "max_hr_bpm = 190\n"
        'custom_top = "keep me"\n'
        "\n"
        "[other]\n"
        'note = "survives"\n'
        "\n"
        "[[benchmarks.athlete.resting_hr_bpm]]\n"
        "value = 50\n"
        "measured_on = 2024-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    later = date(2026, 6, 1)
    earlier = date(2025, 1, 1)

    profile = load_profile(tmp_path)
    # Written in descending date order deliberately: a deleted sort would
    # leave the file in exactly this (wrong) order. The value is made to
    # *counter*-vary with the date (earlier's final value, 300, is greater
    # than later's, 240) so a sort-by-value mutant produces a list distinct
    # from the correct sort-by-date one -- a same-direction fixture would
    # let the two sorts agree by coincidence.
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=240, measured_on=later
    )
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=290, measured_on=earlier
    )
    # Persisting twice on one (discipline, kind, date) must replace, never
    # duplicate (6.3).
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=300, measured_on=earlier
    )
    save_profile(tmp_path, profile)

    text = path.read_text()
    raw = tomllib.loads(text)

    # Unmanaged flat keys, an unmanaged table, and pre-existing benchmark
    # history all survive verbatim (6.4).
    assert raw["max_hr_bpm"] == 190
    assert raw["custom_top"] == "keep me"
    assert raw["other"] == {"note": "survives"}
    assert raw["benchmarks"]["athlete"]["resting_hr_bpm"][0]["value"] == 50
    assert isinstance(raw["benchmarks"]["athlete"]["resting_hr_bpm"][0]["value"], int)

    # Never creates a flat threshold key from this path (6.8).
    assert "ftp_watts" not in raw

    # Version stamped with the shared schema constant (6.5).
    assert raw["profile_version"] == ATHLETE_SCHEMA_VERSION

    entries = raw["benchmarks"]["run"]["ftp_watts"]
    assert len(entries) == 2, "same-date write must replace, not append (6.3)"
    assert [entry["measured_on"] for entry in entries] == [
        earlier,
        later,
    ], "entries must be emitted in ascending measured_on order (6.6)"
    assert entries[0]["value"] == 300, "the later same-date write must win"
    # Plain, human-readable TOML: native date/numeric types, not stringified (9.3).
    assert isinstance(entries[0]["measured_on"], date)
    assert isinstance(entries[0]["value"], (int, float))
    assert not isinstance(entries[0]["value"], str)

    # The written file still parses and round-trips through the reader.
    reloaded = load_profile(tmp_path)
    assert (
        reloaded.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=earlier
        ).value
        == 300
    )
    assert (
        reloaded.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=later
        ).value
        == 240
    )


# Every `BenchmarkKind` covered: the write-path prohibition (Req 6.8) names
# "any new flat threshold key", not only the three that
# `fitdocs.athlete.load_athlete_inputs` currently projects back into
# `AthleteInputs` -- `lthr_bpm` and `threshold_pace_s_per_km` have no flat
# reader-side counterpart today, but a user could still hand-write one, and
# `with_benchmark`'s own docstring promises this for every kind, not a subset.
_UPDATE_CASES = [
    # (kind, discipline, scope table, flat literal, benchmark value)
    pytest.param(
        BenchmarkKind.FTP_WATTS, Sport.RUN, "run", "250.0", 300.0, id="ftp_watts"
    ),
    pytest.param(BenchmarkKind.LTHR_BPM, Sport.RUN, "run", "165", 150, id="lthr_bpm"),
    pytest.param(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        Sport.RUN,
        "run",
        "300.0",
        280.0,
        id="threshold_pace_s_per_km",
    ),
    pytest.param(
        BenchmarkKind.MAX_HR_BPM, None, "athlete", "188", 200, id="max_hr_bpm"
    ),
    pytest.param(
        BenchmarkKind.RESTING_HR_BPM, None, "athlete", "45", 60, id="resting_hr_bpm"
    ),
]


@pytest.mark.parametrize(
    ("kind", "discipline", "scope", "flat_literal", "benchmark_value"), _UPDATE_CASES
)
def test_with_benchmark_never_updates_an_existing_flat_threshold_key(
    tmp_path: Path,
    kind: BenchmarkKind,
    discipline: Sport | None,
    scope: str,
    flat_literal: str,
    benchmark_value: float,
) -> None:
    """A flat threshold key already on file is preserved, never updated, when
    a benchmark of the *same* quantity is persisted (Req 6.8, update clause).
    Covers all five ``BenchmarkKind`` quantities -- ``ftp_watts``,
    ``lthr_bpm``, ``threshold_pace_s_per_km``, ``max_hr_bpm``,
    ``resting_hr_bpm`` -- not only ``max_hr_bpm``: the requirement and
    ``with_benchmark``'s own docstring promise this for every kind, and
    ``lthr_bpm``/``threshold_pace_s_per_km`` have no reader-side counterpart
    today but could still be hand-written flat keys this store must not
    touch. Each case's flat and benchmark values are deliberately different,
    so an implementation that copied the benchmark onto the flat key would
    produce the benchmark's value, not the flat one -- equal values would
    make the mutation invisible.

    The assertion spans both :meth:`AthleteProfile.with_benchmark` and
    :func:`save_profile`: it is the round-tripped *file* that is inspected
    (via a fresh ``tomllib.loads`` after ``save_profile``), not
    ``profile.data`` in memory, so a future write-path split between the two
    functions can't silently drop half of this coverage.
    """
    key = kind.value
    seed = f"{key} = {flat_literal}\n"
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    # Precondition: the flat key is live before the benchmark write.
    raw_before = tomllib.loads(path.read_text())
    assert key in raw_before

    profile = profile.with_benchmark(
        kind,
        discipline=discipline,
        value=benchmark_value,
        measured_on=date(2025, 1, 1),
    )
    save_profile(tmp_path, profile)

    raw_after = tomllib.loads(path.read_text())
    # Precondition confirmed live: the benchmark of the same quantity was
    # actually applied, with a value distinct from the flat key's.
    assert raw_after["benchmarks"][scope][key][0]["value"] == benchmark_value
    # Postcondition: the flat key is unchanged, not derived from or replaced
    # by the benchmark just written (Req 6.8).
    assert raw_after[key] == raw_before[key]


@pytest.mark.parametrize(
    ("kind", "discipline", "scope", "flat_literal", "benchmark_value"), _UPDATE_CASES
)
def test_with_benchmark_never_creates_a_flat_threshold_key(
    tmp_path: Path,
    kind: BenchmarkKind,
    discipline: Sport | None,
    scope: str,
    flat_literal: str,
    benchmark_value: float,
) -> None:
    """No flat threshold key is created by persisting a benchmark of that
    quantity when no such flat key was on file to begin with (Req 6.8,
    creation clause). Covers all five ``BenchmarkKind`` quantities -- reusing
    ``_UPDATE_CASES`` for the kind/discipline/scope/benchmark-value shape, but
    seeding *no* flat key, unlike the update-clause test above. Previously
    only ``ftp_watts`` was pinned here (the pre-existing
    ``test_with_benchmark_round_trip_upserts_sorts_and_preserves``); a
    kind-discriminating implementation that created a flat key for every
    *other* quantity while correctly leaving ``ftp_watts`` alone shipped
    green until this was added."""
    path = tmp_path / PROFILE_FILENAME
    key = kind.value

    profile = load_profile(tmp_path)
    profile = profile.with_benchmark(
        kind,
        discipline=discipline,
        value=benchmark_value,
        measured_on=date(2025, 1, 1),
    )
    save_profile(tmp_path, profile)

    raw_after = tomllib.loads(path.read_text())
    # Precondition confirmed live: the benchmark was actually persisted.
    assert raw_after["benchmarks"][scope][key][0]["value"] == benchmark_value
    # Postcondition: no flat key was created for it (Req 6.8).
    assert key not in raw_after


# --- upsert key must be (discipline, kind, measured_on) in full (Req 6.3) --
def test_with_benchmark_upsert_key_includes_quantity_not_just_discipline_and_date(
    tmp_path: Path,
) -> None:
    """A same-discipline, same-date write of a *different* quantity must not
    evict a sibling quantity recorded on that same discipline and date.

    An ``anchor`` entry on a different date keeps the ``run.lthr_bpm`` group
    non-empty after the colliding-date entry would be wrongly evicted, so an
    incomplete group is actually written (not merely a group silently left
    alone) -- the store never deletes a whole ``(scope, kind)`` group it saw
    no fresh data for, so a fixture with no surviving sibling in the group
    would let this bug hide behind that unrelated preservation behavior.
    """
    d = date(2025, 1, 1)
    anchor = date(2020, 1, 1)

    profile = load_profile(tmp_path)
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RUN, value=140, measured_on=anchor
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RUN, value=165, measured_on=d
    )
    # Same discipline, same date, but a *different* quantity.
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=300, measured_on=d
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    lthr_dates = {
        entry["measured_on"] for entry in raw["benchmarks"]["run"]["lthr_bpm"]
    }
    assert lthr_dates == {anchor, d}, (
        "an upsert key missing the quantity would let the FTP write on the "
        "same discipline and date evict the sibling LTHR entry at that date"
    )
    assert raw["benchmarks"]["run"]["ftp_watts"][0]["value"] == 300


def test_with_benchmark_upsert_key_includes_discipline_not_just_quantity_and_date(
    tmp_path: Path,
) -> None:
    """A same-quantity, same-date write on a *different* discipline must not
    evict a sibling discipline's entry for that same quantity and date.

    Same ``anchor``-entry rationale as the quantity-key sibling test above.
    """
    d = date(2025, 1, 1)
    anchor = date(2020, 1, 1)

    profile = load_profile(tmp_path)
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, value=210, measured_on=anchor
    )
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, value=220, measured_on=d
    )
    # Same quantity, same date, but a *different* discipline.
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=300, measured_on=d
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    ride_dates = {
        entry["measured_on"] for entry in raw["benchmarks"]["ride"]["ftp_watts"]
    }
    assert ride_dates == {anchor, d}, (
        "an upsert key missing the discipline would let the RUN write for "
        "the same quantity and date evict the sibling RIDE entry at that date"
    )
    assert raw["benchmarks"]["run"]["ftp_watts"][0]["value"] == 300


def test_with_benchmark_rejects_athlete_scoped_quantity_given_a_discipline(
    tmp_path: Path,
) -> None:
    base = load_profile(tmp_path)

    with pytest.raises(ValueError, match="athlete-wide"):
        base.with_benchmark(
            BenchmarkKind.MAX_HR_BPM,
            discipline=Sport.RUN,
            value=190,
            measured_on=date(2026, 1, 1),
        )

    assert base.data == {}
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_with_benchmark_rejects_discipline_scoped_quantity_with_no_discipline(
    tmp_path: Path,
) -> None:
    base = load_profile(tmp_path)

    with pytest.raises(ValueError, match="discipline-scoped"):
        base.with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=None,
            value=250,
            measured_on=date(2026, 1, 1),
        )

    assert base.data == {}
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_with_benchmark_rejects_fractional_bpm_value_and_leaves_profile_unchanged(
    tmp_path: Path,
) -> None:
    base = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=165,
        measured_on=date(2025, 1, 1),
    )
    before = copy.deepcopy(dict(base.data))
    assert before != {}  # something is genuinely at stake, not a trivial no-op

    with pytest.raises(ValueError, match="whole number"):
        base.with_benchmark(
            BenchmarkKind.LTHR_BPM,
            discipline=Sport.RUN,
            value=172.5,
            measured_on=date(2025, 6, 1),
        )

    assert base.data == before
    assert not (tmp_path / PROFILE_FILENAME).exists()


def test_with_benchmark_rejects_non_positive_value(tmp_path: Path) -> None:
    """Seeds a real, pre-existing file rather than starting from an absent
    one: Req 6.9's wording is "leaving the file exactly as it was", which an
    absent-file fixture cannot distinguish from "left absent" -- the file
    must come back byte-identical, not merely still-missing.
    """
    seed = (
        "max_hr_bpm = 190\n"
        "\n"
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 250\n"
        "measured_on = 2025-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    before = path.read_bytes()

    with pytest.raises(ValueError, match="positive"):
        load_profile(tmp_path).with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=0,
            measured_on=date(2025, 6, 1),
        )

    assert path.read_bytes() == before


def test_with_benchmark_returns_new_object_without_mutating_original(
    tmp_path: Path,
) -> None:
    """Also pins the Req 6.4 deep-copy clause: an unmanaged *nested* table
    must not be shared between ``base.data`` and ``updated.data`` (M: drop
    ``copy.deepcopy(dict(self.data))`` at ``with_benchmark``'s
    ``document = ...`` line, in favour of a bare ``dict(self.data)``).
    """
    base = AthleteProfile(data={"max_hr_bpm": 195, "other": {"nested": {"k": 1}}})

    updated = base.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2026, 1, 1),
    )

    assert updated is not base
    assert base.data == {"max_hr_bpm": 195, "other": {"nested": {"k": 1}}}
    assert "benchmarks" not in base.data
    assert not base.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN)
    assert updated.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN)
    # The unmanaged nested table is deep-copied, never shared (Req 6.4).
    assert base.data["other"] is not updated.data["other"]
    assert (
        base.data["other"]["nested"]  # type: ignore[index]
        is not updated.data["other"]["nested"]  # type: ignore[index]
    )


# --- unrecognized benchmark content survives a rewrite (Req 6.4, 1.10) -----
def test_with_benchmark_and_save_preserve_unrecognized_benchmark_content(
    tmp_path: Path,
) -> None:
    """A rewrite via ``with_benchmark`` + ``save_profile`` must not destroy
    content :func:`~fitdocs.benchmarks.parse_benchmarks` deliberately leaves
    alone for forward compatibility (1.10): an unrecognized quantity table
    under a recognized discipline, and an unrecognized key inside a
    recognized entry table -- even when that entry's ``value`` is the one
    being replaced.
    """
    seed = (
        "[[benchmarks.run.future_kind_w]]\n"
        "value = 500\n"
        "measured_on = 2025-01-01\n"
        "\n"
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 250\n"
        "measured_on = 2025-01-01\n"
        'sensor = "stryd"\n'
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=date(2025, 1, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads(path.read_text())
    # The unrecognized quantity table survives whole.
    assert raw["benchmarks"]["run"]["future_kind_w"] == [
        {"value": 500, "measured_on": date(2025, 1, 1)}
    ]
    # The recognized entry's value was genuinely updated...
    ftp_entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert ftp_entry["value"] == 260
    # ...but the unrecognized key on that same entry still survives.
    assert ftp_entry["sensor"] == "stryd"


# --- save_profile re-sorts benchmarks even bypassing with_benchmark (6.6) --
def test_save_profile_sorts_benchmarks_written_directly_bypassing_with_benchmark(
    tmp_path: Path,
) -> None:
    """``save_profile`` must canonicalize benchmark ordering on its own --
    not merely inherit an already-sorted document from ``with_benchmark``.
    Constructs ``profile.data`` by hand, in descending date order, and calls
    ``save_profile`` directly, never going through ``with_benchmark``.
    """
    document = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": 280, "measured_on": date(2026, 6, 1)},
                    {"value": 250, "measured_on": date(2025, 1, 1)},
                ]
            }
        }
    }
    save_profile(tmp_path, AthleteProfile(data=document))

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entries = raw["benchmarks"]["run"]["ftp_watts"]
    assert [entry["measured_on"] for entry in entries] == [
        date(2025, 1, 1),
        date(2026, 6, 1),
    ], "save_profile must sort ascending even when profile.data was hand-built"


# --- atomic rename mechanism itself (Req 6.7) -------------------------------
def test_save_profile_uses_os_replace_for_atomic_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[Path, Path]] = []
    real_replace = __import__("os").replace

    def spy_replace(src: object, dst: object) -> None:
        calls.append((Path(str(src)), Path(str(dst))))
        real_replace(src, dst)

    monkeypatch.setattr("fitdocs.load.profile.os.replace", spy_replace)

    profile = load_profile(tmp_path).with_value(MAX_HR, 200)
    save_profile(tmp_path, profile)

    assert len(calls) == 1
    src, dst = calls[0]
    assert dst == tmp_path / PROFILE_FILENAME
    assert src.parent == tmp_path
    assert src.name.startswith(".athlete-")
    assert src != dst


# --- benchmark value validation sub-clauses (Req 6.9) -----------------------
def test_with_benchmark_rejects_bool_value(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_profile(tmp_path).with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=True,
            measured_on=date(2025, 1, 1),
        )


def test_with_benchmark_rejects_non_finite_value_distinctly_from_non_positive(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="finite") as exc_nan:
        load_profile(tmp_path).with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=float("nan"),
            measured_on=date(2025, 1, 1),
        )
    assert "positive" not in str(exc_nan.value)

    with pytest.raises(ValueError, match="finite") as exc_inf:
        load_profile(tmp_path).with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=float("inf"),
            measured_on=date(2025, 1, 1),
        )
    assert "positive" not in str(exc_inf.value)


def test_with_benchmark_writes_bpm_value_as_toml_integer(tmp_path: Path) -> None:
    """The written entry must be a bare TOML integer, not a synthetic float,
    for a beats-per-minute quantity (``_validate_benchmark_value``'s own
    ``int(numeric)`` cast).

    Asserted on ``profile.data`` directly -- *before* any
    ``save_profile`` -- rather than on a written-and-reloaded file. A round
    trip through ``save_profile`` re-derives the persisted value from
    ``profile.benchmarks.entries``, which is parsed via
    :func:`fitdocs.benchmarks.parse_benchmarks`; that parser applies its own
    independent ``int`` cast for an :data:`~fitdocs.benchmarks.INTEGRAL_KINDS`
    quantity and would silently repair a missing cast in
    ``_validate_benchmark_value`` before the file is ever written, hiding
    exactly the mutation this test targets. Reading ``profile.data`` right
    after ``with_benchmark`` observes what that method itself stored.
    """
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=165.0,
        measured_on=date(2025, 1, 1),
    )

    benchmarks = profile.data["benchmarks"]
    assert isinstance(benchmarks, dict)
    entry = benchmarks["run"]["lthr_bpm"][0]
    assert entry["value"] == 165
    assert isinstance(entry["value"], int)

    save_profile(tmp_path, profile)
    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    written_entry = raw["benchmarks"]["run"]["lthr_bpm"][0]
    assert written_entry["value"] == 165
    assert isinstance(written_entry["value"], int)


# --- note is part of the recorded entry (design Service Interface) ---------
def test_with_benchmark_note_survives_to_the_written_document(
    tmp_path: Path,
) -> None:
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2025, 1, 1),
        note="ramp test",
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert raw["benchmarks"]["run"]["ftp_watts"][0]["note"] == "ramp test"


def test_save_removes_temp_file_when_write_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = load_profile(tmp_path).with_value(MAX_HR, 200)

    def boom(document: object, handle: object) -> None:
        raise RuntimeError("simulated write failure")

    monkeypatch.setattr("fitdocs.load.profile.tomli_w.dump", boom)

    with pytest.raises(RuntimeError):
        save_profile(tmp_path, profile)

    # No partial or temp file left behind, and the target was never created.
    assert list(tmp_path.iterdir()) == []


# --- round-3 repair: merge base must be keyed by canonical scope identity --
def test_save_canonicalizes_uppercase_run_scope_so_reload_succeeds(
    tmp_path: Path,
) -> None:
    """A hand-edited file spelling the discipline table uppercase
    (``[[benchmarks.Run.ftp_watts]]``) must not survive a save as two scope
    tables the parser resolves to the same ``Sport`` -- that duplicates
    every entry it covers and makes the file permanently unloadable (the
    round-2 defect). No ``with_benchmark`` call is involved: this exercises
    ``save_profile``'s own canonicalisation of the merge base, independent
    of the write path that already emits the canonical spelling (M1).
    """
    seed = "[[benchmarks.Run.ftp_watts]]\nvalue = 250\nmeasured_on = 2025-01-01\n"
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    save_profile(tmp_path, profile)

    # A duplicate (discipline, kind, measured_on) across "Run" and "run"
    # would make parse_benchmarks -- and hence load_profile -- raise.
    reloaded = load_profile(tmp_path)
    benchmark = reloaded.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2025, 1, 1)
    )
    assert benchmark is not None
    assert benchmark.value == 250

    raw = tomllib.loads(path.read_text())
    scope_tables = [key for key in raw["benchmarks"] if key.lower() == "run"]
    assert len(scope_tables) == 1, (
        "exactly one scope table must resolve to Sport.RUN after the save"
    )


def test_save_canonicalizes_uppercase_athlete_scope_so_reload_succeeds(
    tmp_path: Path,
) -> None:
    """Same defect, the reserved ``athlete`` token (M2)."""
    seed = "[[benchmarks.ATHLETE.max_hr_bpm]]\nvalue = 190\nmeasured_on = 2025-01-01\n"
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    save_profile(tmp_path, profile)

    reloaded = load_profile(tmp_path)
    benchmark = reloaded.benchmark(
        BenchmarkKind.MAX_HR_BPM, discipline=None, on=date(2025, 1, 1)
    )
    assert benchmark is not None
    assert benchmark.value == 190

    raw = tomllib.loads(path.read_text())
    scope_tables = [key for key in raw["benchmarks"] if key.lower() == "athlete"]
    assert len(scope_tables) == 1, (
        "exactly one scope table must resolve to the athlete scope after the save"
    )


def test_save_canonicalizes_every_uppercased_recognized_scope(
    tmp_path: Path,
) -> None:
    """A guard over every recognized scope spelling -- every ``Sport`` plus
    the reserved ``ATHLETE_SCOPE`` token -- each seeded uppercase on disk,
    must canonicalize and reload cleanly. Loops so a fake scope alias, or a
    serializer that emitted the wrong case, could not hide behind a fixture
    that only covers one scope (M6). Includes the positive control that the
    loop scans at least one scope, so it cannot pass vacuously.
    """
    scanned = 0
    for index, token in enumerate((ATHLETE_SCOPE, *(sport.value for sport in Sport))):
        scanned += 1
        data_root = tmp_path / f"scope-{index}"
        data_root.mkdir()
        kind = "max_hr_bpm" if token == ATHLETE_SCOPE else "ftp_watts"
        seed = (
            f"[[benchmarks.{token.upper()}.{kind}]]\n"
            "value = 150\n"
            "measured_on = 2025-01-01\n"
        )
        path = data_root / PROFILE_FILENAME
        path.write_text(seed)

        profile = load_profile(data_root)
        save_profile(data_root, profile)
        load_profile(data_root)  # must not raise

        raw = tomllib.loads(path.read_text())
        canonical = token.lower()
        matching = [key for key in raw["benchmarks"] if key.lower() == canonical]
        assert len(matching) == 1, f"{token!r} did not canonicalize to one table"

    assert scanned, "positive control: the loop must scan at least one scope"


def test_save_folds_colliding_unrecognized_kind_without_dropping_either_spelling(
    tmp_path: Path,
) -> None:
    """An unrecognized quantity table appearing under both an uppercase and a
    lowercase spelling of the same discipline, at *different* dates, must
    survive with both entries intact after a save -- concatenation, not a
    silent last-spelling-wins drop (M7). A recognized entry on an unrelated
    date is included so the merge path actually runs and touches this scope.
    """
    seed = (
        "[[benchmarks.Run.future_kind]]\n"
        "value = 111\n"
        "measured_on = 2024-01-01\n"
        "\n"
        "[[benchmarks.run.future_kind]]\n"
        "value = 222\n"
        "measured_on = 2024-06-01\n"
        "\n"
        "[[benchmarks.run.lthr_bpm]]\n"
        "value = 150\n"
        "measured_on = 2020-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    save_profile(tmp_path, profile)

    raw = tomllib.loads(path.read_text())
    future_entries = raw["benchmarks"]["run"]["future_kind"]
    dates = {entry["measured_on"] for entry in future_entries}
    assert dates == {date(2024, 1, 1), date(2024, 6, 1)}, (
        "both colliding-spelling entries for the unrecognized kind must "
        "survive, neither dropped"
    )


def test_save_concatenates_unrecognized_kind_collision_in_spelling_order(
    tmp_path: Path,
) -> None:
    """Concatenation order follows on-disk scope-spelling order (``Run``
    before ``run``), not a resort by date -- dates are deliberately reversed
    relative to spelling order so a resort-by-date would produce the
    opposite list (M: ``[*prior, *kind_entries]`` -> ``[*kind_entries,
    *prior]`` in ``_canonicalize_benchmarks_region``).
    """
    seed = (
        "[[benchmarks.Run.future_kind]]\n"
        "value = 111\n"
        "measured_on = 2024-06-01\n"
        "\n"
        "[[benchmarks.run.future_kind]]\n"
        "value = 222\n"
        "measured_on = 2024-01-01\n"
        "\n"
        "[[benchmarks.run.lthr_bpm]]\n"
        "value = 150\n"
        "measured_on = 2020-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    save_profile(tmp_path, profile)

    raw = tomllib.loads(path.read_text())
    future_entries = raw["benchmarks"]["run"]["future_kind"]
    assert [entry["measured_on"] for entry in future_entries] == [
        date(2024, 6, 1),
        date(2024, 1, 1),
    ], "concatenation must preserve on-disk spelling order, not resort by date"


def test_save_refuses_scalar_collision_across_scope_spellings_for_unrecognized_kind(
    tmp_path: Path,
) -> None:
    """A scalar value duplicated for the same unrecognized quantity key
    across two spellings of one discipline cannot be merged automatically
    -- the store must refuse loudly rather than silently keep only the
    last-spelling's value (Req 6.4; M: replace the collision-refusal branch
    with ``target[kind_key] = kind_entries``).

    Also pins the refusal message's ``origin_scope`` bookkeeping: it must
    name *both* raw on-disk spellings (``Run`` and ``run``), the one piece
    of information that makes this refusal actionable rather than a naked
    "something collided" (M: ``first_spelling =
    origin_scope[(canonical_key, kind_key)]`` -> ``first_spelling =
    canonical_key``, which would report ``benchmarks.run.future_note and
    benchmarks.run.future_note`` -- the same spelling twice).
    """
    seed = (
        "[benchmarks.Run]\n"
        'future_note = "KEEP-ME-UPPER"\n'
        "\n"
        "[benchmarks.run]\n"
        'future_note = "keep-me-lower"\n'
        "\n"
        "[[benchmarks.run.lthr_bpm]]\n"
        "value = 150\n"
        "measured_on = 2020-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    before = path.read_text()

    profile = load_profile(tmp_path)
    with pytest.raises(
        ProfileError,
        match=r"benchmarks\.Run\.future_note and benchmarks\.run\.future_note",
    ):
        save_profile(tmp_path, profile)

    assert path.read_text() == before, (
        "a refused save must leave the file exactly as it was"
    )
    assert sorted(p.name for p in tmp_path.iterdir()) == [PROFILE_FILENAME], (
        "a refused save must leave no temporary file behind (Req 6.7)"
    )


def test_save_refuses_mapping_collision_across_scope_spellings_for_unrecognized_kind(
    tmp_path: Path,
) -> None:
    """Same defect, a table (``Mapping``) value on both sides instead of a
    scalar -- the ``else`` branch's collision case is not limited to
    strings/numbers (M: replace the collision-refusal branch with
    ``target[kind_key] = kind_entries``).
    """
    seed = (
        "[benchmarks.Run.future_note]\n"
        "a = 1\n"
        "\n"
        "[benchmarks.run.future_note]\n"
        "b = 2\n"
        "\n"
        "[[benchmarks.run.lthr_bpm]]\n"
        "value = 150\n"
        "measured_on = 2020-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    before = path.read_text()

    profile = load_profile(tmp_path)
    with pytest.raises(ProfileError):
        save_profile(tmp_path, profile)

    assert path.read_text() == before


def test_save_refuses_list_vs_scalar_collision_for_unrecognized_kind(
    tmp_path: Path,
) -> None:
    """Pins ``_is_entry_list``'s actual predicate, not merely that the
    collision branch runs: one spelling holds a raw entry array, the other a
    plain string, for the same unrecognized quantity key. The real
    predicate refuses to merge a string as if it were an entry list; a
    ``return True`` stub would instead let ``[*prior, *"not-a-list"]``
    silently splice the string's characters in (M: ``_is_entry_list`` ->
    ``return True``).
    """
    seed = (
        "[[benchmarks.Run.future_kind]]\n"
        "value = 1\n"
        "measured_on = 2024-01-01\n"
        "\n"
        "[benchmarks.run]\n"
        'future_kind = "not-a-list"\n'
        "\n"
        "[[benchmarks.run.lthr_bpm]]\n"
        "value = 150\n"
        "measured_on = 2020-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    before = path.read_text()

    profile = load_profile(tmp_path)
    with pytest.raises(ProfileError):
        save_profile(tmp_path, profile)

    assert path.read_text() == before


def test_canonicalize_benchmarks_region_deep_copies_nested_entry_tables() -> None:
    """The merge base must never alias the caller's original nested tables
    or entry dicts -- a later in-place overlay
    (:func:`~fitdocs.load.profile._merge_benchmarks_document`) writing into
    the returned structure must not reach back into ``existing`` (Req 6.4;
    M: drop the ``copy.deepcopy`` wrapping ``existing`` in
    ``_canonicalize_benchmarks_region``, replacing it with a bare
    ``dict(existing)``).
    """
    existing: dict[str, object] = {
        "run": {
            "future_kind": [{"value": 1, "measured_on": date(2024, 1, 1)}],
        }
    }

    canonicalized = _canonicalize_benchmarks_region(existing)

    run_table = canonicalized["run"]
    existing_run_table = existing["run"]
    assert isinstance(run_table, dict)
    assert isinstance(existing_run_table, dict)
    assert run_table["future_kind"] is not existing_run_table["future_kind"]
    assert run_table["future_kind"][0] is not existing_run_table["future_kind"][0]  # type: ignore[index]


def test_save_refuses_document_reassembled_from_a_hand_forged_duplicate_benchmark_set(
    tmp_path: Path,
) -> None:
    """Exercises the re-parse net's *mechanism* via a construction no
    production caller can perform: ``data`` carries no benchmarks at all,
    but ``benchmarks`` -- reachable only by bypassing
    ``__post_init__``'s own parse with ``object.__new__`` +
    ``object.__setattr__``, as done here -- holds two entries sharing a
    ``(discipline, kind, measured_on)`` key. Neither ``data`` nor the
    canonicaliser can see this; only re-parsing the *assembled* document
    (not ``profile.data``) catches it (M: ``parse_benchmarks(document)`` ->
    ``parse_benchmarks(profile.data)`` at the ``save_profile`` call site).
    This is not a scenario any production code path reaches -- see
    :func:`fitdocs.load.profile.save_profile`'s docstring for what the net
    actually guards in production (a future scope-alias divergence between
    this module's canonicaliser and ``benchmarks.py``'s resolver).
    """
    profile = object.__new__(AthleteProfile)
    object.__setattr__(profile, "data", {})
    object.__setattr__(
        profile,
        "benchmarks",
        BenchmarkSet(
            entries=(
                Benchmark(
                    kind=BenchmarkKind.FTP_WATTS,
                    discipline=Sport.RUN,
                    value=250,
                    measured_on=date(2025, 1, 1),
                ),
                Benchmark(
                    kind=BenchmarkKind.FTP_WATTS,
                    discipline=Sport.RUN,
                    value=999,
                    measured_on=date(2025, 1, 1),
                ),
            )
        ),
    )

    with pytest.raises(ProfileError):
        save_profile(tmp_path, profile)

    assert not (tmp_path / PROFILE_FILENAME).exists(), (
        "a refused save must not create the target file"
    )
    assert list(tmp_path.iterdir()) == [], (
        "a refused save must leave no temporary file behind either (Req 6.7)"
    )


def test_save_refuses_a_document_the_reader_would_reject_and_leaves_file_untouched(
    tmp_path: Path,
) -> None:
    """Bypasses both ``with_benchmark`` and the canonicaliser: hand-assembles
    an ``AthleteProfile`` whose raw ``data`` already carries a same-date
    collision for a *recognized* quantity across two scope spellings, under
    a kind this save's own fresh entries never touch -- so
    ``_canonicalize_benchmarks_region``'s fold-and-concatenate rule (which
    does not deduplicate by date) cannot repair it on its own. Constructing
    this shape through the normal ``AthleteProfile(data=...)`` constructor
    would be rejected at ``__post_init__`` itself (the eager parse already
    rejects the duplicate resolved case-insensitively), so the object is
    assembled by setting the frozen fields directly -- the only way to reach
    ``save_profile`` with this shape and exercise its own re-parse safety
    net. This is the mutant that distinguishes step 2 (the re-parse) from
    step 1 (the canonicaliser) (M3, M4; Req 6.7, 6.9).
    """
    collide_date = date(2025, 1, 1)
    seed_document: dict[str, object] = {
        "benchmarks": {
            "Run": {"ftp_watts": [{"value": 250, "measured_on": collide_date}]},
            "run": {"ftp_watts": [{"value": 999, "measured_on": collide_date}]},
        }
    }
    path = tmp_path / PROFILE_FILENAME
    with path.open("wb") as handle:
        tomli_w.dump(seed_document, handle)
    before = path.read_bytes()

    profile = object.__new__(AthleteProfile)
    object.__setattr__(profile, "data", seed_document)
    object.__setattr__(
        profile,
        "benchmarks",
        BenchmarkSet(
            entries=(
                Benchmark(
                    kind=BenchmarkKind.LTHR_BPM,
                    discipline=Sport.RUN,
                    value=150,
                    measured_on=date(2020, 1, 1),
                ),
            )
        ),
    )

    with pytest.raises(ProfileError):
        save_profile(tmp_path, profile)

    assert path.read_bytes() == before, (
        "a refused save must leave the file exactly as it was (Req 6.7)"
    )


def test_with_benchmark_writes_whole_number_float_kind_value_as_toml_integer(
    tmp_path: Path,
) -> None:
    """``FTP_WATTS`` is not an ``INTEGRAL_KINDS`` quantity, yet a whole-number
    value must still round-trip as a bare TOML integer -- never a synthetic
    float -- exactly as ``fitdocs.benchmarks._validate_value`` does for
    identical input arriving through the parser (M5, Req 9.3).
    """
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=date(2025, 1, 1),
    )
    save_profile(tmp_path, profile)

    text = (tmp_path / PROFILE_FILENAME).read_text()
    assert "value = 260" in text
    assert "260.0" not in text

    raw = tomllib.loads(text)
    written_value = raw["benchmarks"]["run"]["ftp_watts"][0]["value"]
    assert written_value == 260
    assert type(written_value) is int


def test_save_stamps_current_schema_version_over_a_stale_seeded_one(
    tmp_path: Path,
) -> None:
    """A file already on disk with an older ``profile_version`` (and a
    benchmark, so the migration this branch performs -- moving the schema
    constant from 1 to the current version -- is actually exercised by a
    save that does something) must have its version overwritten, not merely
    defaulted when absent. A ``document.setdefault(VERSION_KEY, ...)``
    instead of an unconditional assignment would leave the stale version in
    place since the key is already present (Req 6.5).
    """
    seed = (
        "profile_version = 1\n"
        "\n"
        "[[benchmarks.athlete.max_hr_bpm]]\n"
        "value = 190\n"
        "measured_on = 2025-01-01\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)

    profile = load_profile(tmp_path)
    save_profile(tmp_path, profile)

    reloaded = load_profile(tmp_path)
    assert reloaded.get_number("profile_version") == float(ATHLETE_SCHEMA_VERSION)


def test_save_omits_benchmarks_table_when_profile_has_no_benchmarks(
    tmp_path: Path,
) -> None:
    """A profile with no benchmarks at all must leave the written document
    without a ``benchmarks`` table -- not write an empty one no caller
    asked for.
    """
    profile = load_profile(tmp_path).with_value(MAX_HR, 200)
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert "benchmarks" not in raw


def test_with_benchmark_note_omission_keeps_prior_note_but_explicit_note_replaces_it(
    tmp_path: Path,
) -> None:
    """Overlay-not-replace's documented note behavior, pinned in both
    directions: omitting ``note`` on a same-date rewrite keeps the prior
    note (``None`` means "not supplied", not "erase"); supplying an explicit
    note replaces it.
    """
    d = date(2025, 1, 1)
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=d,
        note="ramp test",
    )
    save_profile(tmp_path, profile)

    # Rewrite the same date, omitting note -- must keep it.
    reloaded = load_profile(tmp_path)
    updated = reloaded.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=255, measured_on=d
    )
    save_profile(tmp_path, updated)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 255
    assert entry["note"] == "ramp test", "an omitted note must not erase the prior one"

    # Rewrite again with an explicit note -- must replace.
    reloaded_again = load_profile(tmp_path)
    replaced = reloaded_again.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=d,
        note="new note",
    )
    save_profile(tmp_path, replaced)

    raw2 = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry2 = raw2["benchmarks"]["run"]["ftp_watts"][0]
    assert entry2["value"] == 260
    assert entry2["note"] == "new note"


# --- applies_from: carry, refusal, and round trip (Amendment 1, Req 6.10) -


def test_with_benchmark_carries_applies_from_onto_entry_discipline_scoped(
    tmp_path: Path,
) -> None:
    """A discipline-scoped kind's ``with_benchmark`` carries ``applies_from``
    onto the built :class:`Benchmark` (asserted directly on
    ``profile.benchmarks.entries``, before any save)."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=333,
        measured_on=date(2025, 3, 10),
        applies_from=date(2025, 2, 1),
    )

    assert len(profile.benchmarks.entries) == 1
    entry = profile.benchmarks.entries[0]
    assert entry.applies_from == date(2025, 2, 1)
    assert entry.measured_on == date(2025, 3, 10)


def test_with_benchmark_carries_applies_from_onto_entry_athlete_scoped(
    tmp_path: Path,
) -> None:
    """Same carry for an athlete-wide (``discipline=None``) kind."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190,
        measured_on=date(2025, 1, 15),
        applies_from=date(2024, 12, 1),
    )

    assert len(profile.benchmarks.entries) == 1
    entry = profile.benchmarks.entries[0]
    assert entry.applies_from == date(2024, 12, 1)


def test_with_benchmark_rejects_applies_from_after_measured_on_discipline_scoped(
    tmp_path: Path,
) -> None:
    """A value falling after ``measured_on`` raises ``ValueError`` naming
    ``applies_from`` and both dates, and stores nothing (6.10 via 6.9).

    Seeds a real, non-empty profile file first -- the same shape as
    ``test_with_benchmark_rejects_non_positive_value`` -- so that the
    "unchanged" assertions compare against a state that is genuinely at
    stake: an empty starting profile makes ``base.data == data_before`` the
    tautology ``{} == {}`` (the first round of review replaced both snapshots
    with bare literals and the module stayed green).
    """
    seed = (
        "resting_hr_bpm = 52\n"
        "\n"
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 233\n"
        "measured_on = 2024-07-19\n"
    )
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    bytes_before = path.read_bytes()
    base = load_profile(tmp_path)
    data_before = copy.deepcopy(dict(base.data))
    entries_before = base.benchmarks.entries
    assert data_before != {}  # something is genuinely at stake, not a no-op
    assert len(entries_before) == 1

    with pytest.raises(ValueError) as excinfo:
        base.with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=311,
            measured_on=date(2025, 4, 5),
            applies_from=date(2025, 4, 6),
        )

    message = str(excinfo.value)
    assert "applies_from" in message
    assert "2025-04-06" in message and "2025-04-05" in message
    assert base.data == data_before
    assert base.benchmarks.entries == entries_before
    assert path.read_bytes() == bytes_before


def test_with_benchmark_rejects_applies_from_after_measured_on_athlete_scoped(
    tmp_path: Path,
) -> None:
    """The same refusal for an athlete-wide quantity, over a seeded non-empty
    profile whose existing entry is itself athlete-scoped."""
    seed = "[[benchmarks.athlete.max_hr_bpm]]\nvalue = 187\nmeasured_on = 2024-10-28\n"
    path = tmp_path / PROFILE_FILENAME
    path.write_text(seed)
    bytes_before = path.read_bytes()
    base = load_profile(tmp_path)
    data_before = copy.deepcopy(dict(base.data))
    entries_before = base.benchmarks.entries
    assert data_before != {}
    assert len(entries_before) == 1

    with pytest.raises(ValueError) as excinfo:
        base.with_benchmark(
            BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=195,
            measured_on=date(2025, 2, 2),
            applies_from=date(2025, 2, 3),
        )

    message = str(excinfo.value)
    assert "applies_from" in message
    assert "2025-02-03" in message and "2025-02-02" in message
    assert base.data == data_before
    assert base.benchmarks.entries == entries_before
    assert path.read_bytes() == bytes_before


def test_with_benchmark_accepts_applies_from_equal_to_measured_on(
    tmp_path: Path,
) -> None:
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=321,
        measured_on=date(2025, 5, 5),
        applies_from=date(2025, 5, 5),
    )

    entry = profile.benchmarks.entries[0]
    assert entry.applies_from == date(2025, 5, 5)


def test_with_benchmark_round_trip_resolves_tier2_discipline(
    tmp_path: Path,
) -> None:
    """Save then reload, and resolve through :meth:`AthleteProfile.benchmark`
    (tier 2) for an activity strictly between ``applies_from`` and
    ``measured_on``; also assert the *false* side (before ``applies_from``)
    is ``None`` and that presence is ``True`` either way (reachability both
    sides)."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=345,
        measured_on=date(2025, 8, 20),
        applies_from=date(2025, 7, 1),
    )
    save_profile(tmp_path, profile)

    reloaded = load_profile(tmp_path)
    resolved = reloaded.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2025, 7, 15)
    )
    assert resolved is not None
    assert resolved.value == 345
    assert resolved.applies_from == date(2025, 7, 1)

    assert (
        reloaded.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2025, 6, 30)
        )
        is None
    )
    assert reloaded.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


def test_with_benchmark_round_trip_resolves_tier2_athlete(
    tmp_path: Path,
) -> None:
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=188,
        measured_on=date(2025, 6, 10),
        applies_from=date(2025, 5, 1),
    )
    save_profile(tmp_path, profile)

    reloaded = load_profile(tmp_path)
    resolved = reloaded.benchmark(
        BenchmarkKind.MAX_HR_BPM, discipline=None, on=date(2025, 5, 15)
    )
    assert resolved is not None
    assert resolved.value == 188

    assert (
        reloaded.benchmark(
            BenchmarkKind.MAX_HR_BPM, discipline=None, on=date(2025, 4, 30)
        )
        is None
    )
    assert reloaded.has_benchmark(BenchmarkKind.MAX_HR_BPM, discipline=None) is True


def test_with_benchmark_and_save_writes_applies_from_key_to_toml(
    tmp_path: Path,
) -> None:
    """Pins the serializer path *through the store* -- read the file bytes
    and parse independently with ``tomllib``, not only the in-memory
    profile."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=350,
        measured_on=date(2025, 9, 9),
        applies_from=date(2025, 9, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["applies_from"] == date(2025, 9, 1)


def test_with_benchmark_rewrite_with_applies_from_overlays_a_different_existing_one(
    tmp_path: Path,
) -> None:
    """A same-``measured_on`` rewrite that carries ``applies_from`` overlays
    an existing raw entry's *different* ``applies_from`` -- the new one
    wins."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-03-01\n"
        "applies_from = 2024-01-10\n"
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=205,
        measured_on=date(2024, 3, 1),
        applies_from=date(2024, 2, 20),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["applies_from"] == date(2024, 2, 20)
    assert entry["value"] == 205


def test_with_benchmark_rewrite_without_applies_from_preserves_existing_one(
    tmp_path: Path,
) -> None:
    """A same-``measured_on`` rewrite that omits ``applies_from`` leaves the
    existing raw entry's ``applies_from`` untouched -- and the value *did*
    change, so this pins a real overlay, not a no-op rewrite."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-05-05\n"
        "applies_from = 2024-04-05\n"
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=222,
        measured_on=date(2024, 5, 5),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 222, "the rewrite must be real, not a no-op"
    assert entry["applies_from"] == date(2024, 4, 5), (
        "an omitted applies_from must not erase the prior one"
    )


def test_with_benchmark_mixed_group_preserves_and_adds_plain_entries_in_date_order(
    tmp_path: Path,
) -> None:
    """A group with one entry carrying ``applies_from`` and one without, then
    a third ``with_benchmark`` on a new date without ``applies_from``: the
    existing dated entries keep their own applies_from-or-absence, the new
    entry is plain, and the emitted order is ascending ``measured_on``."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2023-01-01\n"
        "applies_from = 2022-12-01\n"
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 210\n"
        "measured_on = 2023-06-01\n"
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=220,
        measured_on=date(2023, 9, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    group = raw["benchmarks"]["run"]["ftp_watts"]
    assert [e["measured_on"] for e in group] == [
        date(2023, 1, 1),
        date(2023, 6, 1),
        date(2023, 9, 1),
    ]
    assert group[0]["applies_from"] == date(2022, 12, 1)
    assert "applies_from" not in group[1]
    assert "applies_from" not in group[2]


def test_with_benchmark_preserves_unrecognized_key_alongside_applies_from(
    tmp_path: Path,
) -> None:
    """6.4: an existing raw entry carrying both ``applies_from`` and an
    unrecognized key survives a same-date rewrite with both intact."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 100\n"
        "measured_on = 2022-05-05\n"
        "applies_from = 2022-04-01\n"
        'sensor = "stryd"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=150,
        measured_on=date(2022, 5, 5),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 150
    assert entry["applies_from"] == date(2022, 4, 1)
    assert entry["sensor"] == "stryd"


def test_profile_version_name_retired_in_favor_of_shared_schema_constant() -> None:
    import fitdocs.load.profile as profile_module

    assert not hasattr(profile_module, "PROFILE_VERSION")
    assert "PROFILE_VERSION" not in profile_module.__all__

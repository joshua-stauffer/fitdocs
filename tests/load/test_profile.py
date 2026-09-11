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
    BenchmarkSource,
    BenchmarkSourceKind,
)
from fitdocs.load import profile as profile_module
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


# --- with_benchmark provenance argument (design: BenchmarkProvenance, 2.2) -
def test_with_benchmark_accepts_derived_source_and_writes_full_record(
    tmp_path: Path,
) -> None:
    """A discipline-scoped ``with_benchmark`` call carrying a full derived
    ``source`` writes all five recognized keys, in the fixed emitted order,
    onto the written entry (Req 5.2, 5.6)."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2025, 1, 1),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="riegel_race_equivalence",
            document="workouts/2025-01-01-run.md",
            inputs="official distance, official time",
            citation="riegel_1981",
        ),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["run"]["ftp_watts"][0]["source"]
    assert source["kind"] == "derived"
    assert source["method"] == "riegel_race_equivalence"
    assert source["document"] == "workouts/2025-01-01-run.md"
    assert source["inputs"] == "official distance, official time"
    assert source["citation"] == "riegel_1981"
    assert list(source) == ["kind", "method", "document", "inputs", "citation"], (
        "the inner key order is owned by the merge's own emitted order, not "
        "tomllib's arbitrary dict order -- tomllib preserves on-disk order, "
        "so this pins _SOURCE_RECOGNIZED_KEYS' order directly"
    )


def test_with_benchmark_accepts_derived_source_athlete_wide(
    tmp_path: Path,
) -> None:
    """The same shape, but for an athlete-scoped quantity -- vary scope
    independently of the origin class so an athlete-scope-only regression
    cannot pass silently."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190,
        measured_on=date(2025, 2, 2),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="max_effort",
            document="workouts/2025-02-02-run.md",
            inputs="observed peak",
            citation="some_key",
        ),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["athlete"]["max_hr_bpm"][0]["source"]
    assert source["kind"] == "derived"
    assert source["method"] == "max_effort"


def test_with_benchmark_accepts_measured_source_with_no_details(
    tmp_path: Path,
) -> None:
    """A measured origin requires none of the four detail fields, and the
    written record carries the ``kind`` key alone (Req 5.2)."""
    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=260,
        measured_on=date(2025, 3, 3),
        source=BenchmarkSource(kind=BenchmarkSourceKind.MEASURED),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["run"]["ftp_watts"][0]["source"]
    assert source == {"kind": "measured"}


@pytest.mark.parametrize("missing", ["method", "document", "inputs", "citation"])
def test_with_benchmark_rejects_derived_source_missing_required_field(
    tmp_path: Path, missing: str
) -> None:
    """A derived origin missing any one of the four detail fields is refused
    before anything is stored (Req 5.2, 5.9)."""
    details = {
        "method": "riegel_race_equivalence",
        "document": "workouts/2025-01-01-run.md",
        "inputs": "official distance, official time",
        "citation": "riegel_1981",
    }
    details[missing] = None
    base = load_profile(tmp_path)

    with pytest.raises(ValueError, match=missing):
        base.with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=250,
            measured_on=date(2025, 1, 1),
            source=BenchmarkSource(kind=BenchmarkSourceKind.DERIVED, **details),
        )

    assert base.data == {}
    assert not (tmp_path / PROFILE_FILENAME).exists()


@pytest.mark.parametrize("blank", ["method", "document", "inputs", "citation"])
def test_with_benchmark_rejects_derived_source_with_empty_string_field(
    tmp_path: Path, blank: str
) -> None:
    """An empty string is not a valid detail field either -- ``None`` and
    ``""`` are both refused, distinguishing "absent" from "merely falsy but
    present" is not a defence this check is meant to draw (Req 5.2, 5.9)."""
    details = {
        "method": "riegel_race_equivalence",
        "document": "workouts/2025-01-01-run.md",
        "inputs": "official distance, official time",
        "citation": "riegel_1981",
    }
    details[blank] = ""
    base = load_profile(tmp_path)

    with pytest.raises(ValueError, match=blank):
        base.with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=250,
            measured_on=date(2025, 1, 1),
            source=BenchmarkSource(kind=BenchmarkSourceKind.DERIVED, **details),
        )

    assert base.data == {}
    assert not (tmp_path / PROFILE_FILENAME).exists()


# --- the source overlay rule (design: ProfileDerivedWrite, 2.2) ------------
def test_with_benchmark_rewrite_without_source_removes_existing_derived_source(
    tmp_path: Path,
) -> None:
    """Writing a prompt-style answer (no ``source``) over a date that held a
    derived entry leaves no source behind, while a ``note`` *and* an
    ``applies_from`` date already on that entry both survive -- the named
    asymmetry between provenance and the note/applies-from inherit-on-absent
    rule (Req 5.3, 6.6)."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-01-01\n"
        'note = "hand-typed from a lab test"\n'
        "applies_from = 2023-12-01\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "riegel_race_equivalence"\n'
        'document = "workouts/2024-01-01-run.md"\n'
        'inputs = "official distance, official time"\n'
        'citation = "riegel_1981"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=205,
        measured_on=date(2024, 1, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 205
    assert "source" not in entry, "an omitted source must not inherit"
    assert entry["note"] == "hand-typed from a lab test"
    assert entry["applies_from"] == date(2023, 12, 1)


def test_with_benchmark_rewrite_without_source_removes_record_with_unknown_key(
    tmp_path: Path,
) -> None:
    """The absent-fresh half removes the whole inherited record, including an
    unrecognized inner key: 5.6's carry-through applies to a rewrite *of the
    record* (the present half), and here there is no record to carry it into
    (Req 5.3, 6.6)."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-01-01\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "riegel_race_equivalence"\n'
        'document = "workouts/2024-01-01-run.md"\n'
        'inputs = "official distance, official time"\n'
        'citation = "riegel_1981"\n'
        'confidence = "high"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=205,
        measured_on=date(2024, 1, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 205
    assert "source" not in entry


def test_with_benchmark_rewrite_without_source_removes_source_athlete_wide(
    tmp_path: Path,
) -> None:
    """The athlete-wide companion to the discipline-scoped removal case
    above, per the task's fixture rule: every overlay branch gets both an
    athlete-wide and a discipline-scoped fixture."""
    seed = (
        "[[benchmarks.athlete.max_hr_bpm]]\n"
        "value = 190\n"
        "measured_on = 2024-02-02\n"
        'note = "field test"\n'
        "applies_from = 2024-01-15\n"
        "\n"
        "[benchmarks.athlete.max_hr_bpm.source]\n"
        'kind = "derived"\n'
        'method = "max_effort"\n'
        'document = "workouts/2024-02-02-run.md"\n'
        'inputs = "observed peak"\n'
        'citation = "some_key"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=192,
        measured_on=date(2024, 2, 2),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["athlete"]["max_hr_bpm"][0]
    assert entry["value"] == 192
    assert "source" not in entry
    assert entry["note"] == "field test"
    assert entry["applies_from"] == date(2024, 1, 15)


def test_with_benchmark_rewrite_with_source_overlays_keys_preserving_unrecognized(
    tmp_path: Path,
) -> None:
    """Refreshing a derived entry at a date whose raw ``source`` table
    carries an unrecognized inner key leaves that key in the written file,
    while the five recognized keys take the new values -- a whole-table
    replace would drop the unrecognized key (Req 5.6, 5.7)."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-03-01\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "old_method"\n'
        'document = "workouts/old.md"\n'
        'inputs = "old inputs"\n'
        'citation = "old_citation"\n'
        'confidence = "high"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=210,
        measured_on=date(2024, 3, 1),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="new_method",
            document="workouts/new.md",
            inputs="new inputs",
            citation="new_citation",
        ),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["run"]["ftp_watts"][0]["source"]
    assert source["method"] == "new_method"
    assert source["document"] == "workouts/new.md"
    assert source["inputs"] == "new inputs"
    assert source["citation"] == "new_citation"
    assert source["confidence"] == "high", (
        "an unrecognized inner key must survive a refresh"
    )


def test_with_benchmark_rewrite_with_source_overlays_recognized_keys_athlete_wide(
    tmp_path: Path,
) -> None:
    """The athlete-wide companion to the overlay case above."""
    seed = (
        "[[benchmarks.athlete.max_hr_bpm]]\n"
        "value = 188\n"
        "measured_on = 2024-04-04\n"
        "\n"
        "[benchmarks.athlete.max_hr_bpm.source]\n"
        'kind = "derived"\n'
        'method = "old_method"\n'
        'document = "workouts/old.md"\n'
        'inputs = "old inputs"\n'
        'citation = "old_citation"\n'
        'confidence = "high"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=191,
        measured_on=date(2024, 4, 4),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="new_method",
            document="workouts/new.md",
            inputs="new inputs",
            citation="new_citation",
        ),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["athlete"]["max_hr_bpm"][0]["source"]
    assert source["method"] == "new_method"
    assert source["confidence"] == "high"


def test_with_benchmark_rewrite_with_measured_source_clears_stale_recognized_keys(
    tmp_path: Path,
) -> None:
    """A fresh ``source`` that is present but carries fewer recognized
    fields than the inherited raw table (a measured origin overlaying a
    derived one's detail fields) removes the now-stale recognized keys --
    the overlay is key-by-key against the *fresh* record's own five names,
    not a mere ``dict.update`` that would leave ``old_method`` etc. behind
    alongside a now-contradictory ``kind = "measured"``. The unrecognized
    ``confidence`` key still survives."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-05-05\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "old_method"\n'
        'document = "workouts/old.md"\n'
        'inputs = "old inputs"\n'
        'citation = "old_citation"\n'
        'confidence = "high"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=215,
        measured_on=date(2024, 5, 5),
        source=BenchmarkSource(kind=BenchmarkSourceKind.MEASURED),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    source = raw["benchmarks"]["run"]["ftp_watts"][0]["source"]
    assert source["kind"] == "measured"
    assert "method" not in source
    assert "document" not in source
    assert "inputs" not in source
    assert "citation" not in source
    assert source["confidence"] == "high"


def test_with_benchmark_rewrite_without_source_removes_measured_inherited_source(
    tmp_path: Path,
) -> None:
    """The absent-fresh removal rule (Req 5.3, 6.6) is not conditioned on the
    inherited source's ``kind``: a ``measured`` inherited source is removed
    just as a ``derived`` one is when the fresh entry at that date carries no
    ``source`` at all. The rewritten value differs from the seed so this
    fixture cannot be satisfied by a same-value special case (that axis is
    pinned separately, see the ``same value`` test below)."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-07-07\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "measured"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=205,
        measured_on=date(2024, 7, 7),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 205
    assert "source" not in entry, (
        "a measured inherited source must not survive an absent-fresh rewrite"
    )


def test_with_benchmark_rewrite_without_source_removes_derived_source_same_value(
    tmp_path: Path,
) -> None:
    """The absent-fresh removal rule also applies when the rewritten value is
    identical to the value the derived source described -- the removal is not
    conditioned on the value changing."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-08-08\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "riegel_race_equivalence"\n'
        'document = "workouts/2024-08-08-run.md"\n'
        'inputs = "official distance, official time"\n'
        'citation = "riegel_1981"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=200,
        measured_on=date(2024, 8, 8),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert entry["value"] == 200
    assert "source" not in entry, (
        "a derived inherited source must not survive an absent-fresh "
        "rewrite even when the rewritten value is unchanged"
    )


def test_with_benchmark_rewrite_elsewhere_in_group_preserves_untouched_sourced_entry(
    tmp_path: Path,
) -> None:
    """A ``with_benchmark`` call touching one date in a group must not
    disturb a *different*, untouched entry in the same group -- including its
    full ``source`` record and the unrecognized inner key on it (Req 5.7).
    The group also carries a sourceless sibling, asserted to survive as well,
    so keeping only the first or only the last entry both fail."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-01-01\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "derived"\n'
        'method = "riegel_race_equivalence"\n'
        'document = "workouts/2024-01-01-run.md"\n'
        'inputs = "official distance, official time"\n'
        'citation = "riegel_1981"\n'
        'confidence = "high"\n'
        "\n"
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 210\n"
        "measured_on = 2024-06-01\n"
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    profile = load_profile(tmp_path).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=220,
        measured_on=date(2024, 12, 1),
    )
    save_profile(tmp_path, profile)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    entries_by_date = {
        e["measured_on"]: e for e in raw["benchmarks"]["run"]["ftp_watts"]
    }
    assert date(2024, 1, 1) in entries_by_date, (
        "the untouched sourced entry must survive a rewrite elsewhere in its group"
    )
    assert entries_by_date[date(2024, 6, 1)]["value"] == 210
    assert "source" not in entries_by_date[date(2024, 6, 1)]
    assert entries_by_date[date(2024, 1, 1)]["source"] == {
        "kind": "derived",
        "method": "riegel_race_equivalence",
        "document": "workouts/2024-01-01-run.md",
        "inputs": "official distance, official time",
        "citation": "riegel_1981",
        "confidence": "high",
    }


def test_malformed_source_in_loaded_file_raises_naming_file_and_entry_path(
    tmp_path: Path,
) -> None:
    """A ``source`` record whose ``kind`` is outside the published vocabulary
    is rejected at load time, in the profile layer's own voice: the message
    names the file and the entry path (Req 5.5)."""
    seed = (
        "[[benchmarks.run.ftp_watts]]\n"
        "value = 200\n"
        "measured_on = 2024-06-06\n"
        "\n"
        "[benchmarks.run.ftp_watts.source]\n"
        'kind = "guessed"\n'
    )
    (tmp_path / PROFILE_FILENAME).write_text(seed)

    with pytest.raises(ProfileError) as excinfo:
        load_profile(tmp_path)

    message = str(excinfo.value)
    assert PROFILE_FILENAME in message
    assert "benchmarks.run.ftp_watts" in message


def test_save_reparse_refuses_hand_forged_incomplete_derived_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``save_profile``'s pre-write re-parse also proves the ``source`` round
    trip: a hand-forged ``Benchmark`` whose derived ``source`` is missing its
    required detail fields serializes to a shape the parser would reject,
    and the refusal happens before any temporary file is created -- a
    construction ``with_benchmark`` itself would refuse, reached here only by
    bypassing it entirely, exactly as the existing hand-forged-duplicate test
    bypasses it for the natural-key collision (Req 5.5, 6.7). ``tempfile.mkstemp``
    (as the profile module itself calls it) is replaced with a function that
    fails the test if reached, so "before any temporary file is created" is an
    observed ordering, not merely a side effect that a cleanup ``unlink`` would
    also leave looking true."""

    def _mkstemp_should_not_be_reached(**kwargs: object) -> tuple[int, str]:
        pytest.fail("mkstemp reached before the re-parse refused")

    monkeypatch.setattr(
        profile_module.tempfile, "mkstemp", _mkstemp_should_not_be_reached
    )

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
                    measured_on=date(2025, 7, 7),
                    source=BenchmarkSource(kind=BenchmarkSourceKind.DERIVED),
                ),
            )
        ),
    )

    with pytest.raises(ProfileError):
        save_profile(tmp_path, profile)

    assert not (tmp_path / PROFILE_FILENAME).exists()
    assert list(tmp_path.iterdir()) == []


def test_save_profile_round_trips_a_full_derived_source_on_a_hand_assembled_profile(
    tmp_path: Path,
) -> None:
    """The positive counterpart: ``save_profile`` re-emits benchmarks
    independently of ``with_benchmark``, and a hand-assembled profile
    carrying a valid ``source`` round-trips through it and reloads to an
    identical typed value."""
    profile = AthleteProfile(
        data={
            "benchmarks": {
                "run": {
                    "ftp_watts": [
                        {
                            "value": 240,
                            "measured_on": date(2025, 8, 8),
                        }
                    ]
                }
            }
        }
    )
    object.__setattr__(
        profile,
        "benchmarks",
        BenchmarkSet(
            entries=(
                Benchmark(
                    kind=BenchmarkKind.FTP_WATTS,
                    discipline=Sport.RUN,
                    value=240,
                    measured_on=date(2025, 8, 8),
                    source=BenchmarkSource(
                        kind=BenchmarkSourceKind.DERIVED,
                        method="riegel_race_equivalence",
                        document="workouts/2025-08-08-run.md",
                        inputs="official distance, official time",
                        citation="riegel_1981",
                    ),
                ),
            )
        ),
    )

    save_profile(tmp_path, profile)

    reloaded = load_profile(tmp_path)
    entry = reloaded.benchmarks.entries[0]
    assert entry.source == BenchmarkSource(
        kind=BenchmarkSourceKind.DERIVED,
        method="riegel_race_equivalence",
        document="workouts/2025-08-08-run.md",
        inputs="official distance, official time",
        citation="riegel_1981",
    )


# --- derived subset (design: ProfileDerivedWrite, task 2.3, Req 6.1, 6.3,
# 6.4, 6.5, 6.6, 6.7, 6.8) ------------------------------------------------
#
# Fixture matrix (layers x scopes x kinds x group shapes), all seeded onto a
# hand-written file at once so one write exercises every shape:
#   - top level:             a non-benchmark flat key (``max_hr_bpm`` -- the
#                            *athlete-input* key of that name, unrelated to
#                            the benchmark quantity sharing its spelling) and
#                            a calculator sub-table (``[mycalc]``); neither is
#                            benchmark content at all, so both must survive a
#                            derived-subset write byte-for-byte (Req 6.6).
#   - athlete/max_hr_bpm:    MIXED group (hand-written w/ applies_from, no
#                            note; derived), athlete-wide scope.
#   - athlete/resting_hr_bpm: ALL-DERIVED group, but its scope table survives
#                            because max_hr_bpm keeps it non-empty.
#   - run/threshold_pace_s_per_km: MIXED group (hand-written w/ note and an
#                            unrecognized inner key "sensor"; derived),
#                            discipline-scoped.
#   - run/vo2max_score:      an unrecognized quantity table under a
#                            recognized discipline -- never touched at all.
#   - ride/ftp_watts:        ALL-DERIVED group, sharing its scope with a
#                            MIXED group (below) -- so dropping this group
#                            alone must NOT drop the "ride" table.
#   - ride/lthr_bpm:         MIXED group -- a *measured* entry (``source =
#                            {"kind": "measured", "lab": "xyz"}``, an
#                            unrecognized inner key) alongside a derived
#                            entry, so a measured entry is exercised in the
#                            same fixture as a hand-written one, and "ride" is
#                            no longer the sole-group scope-drop case.
#   - swim/lthr_bpm:         ALL-DERIVED group that IS the sole group under
#                            its scope, so the whole "swim" table must be
#                            dropped, not just the group.


def _derived_source(
    method: str, *, document: str, inputs: str, citation: str
) -> dict[str, object]:
    return {
        "kind": "derived",
        "method": method,
        "document": document,
        "inputs": inputs,
        "citation": citation,
    }


def _seed_derived_subset_document() -> dict[str, object]:
    return {
        # A non-benchmark flat key (the athlete-input field of the same
        # name, in a wholly different namespace than benchmarks.athlete.
        # max_hr_bpm) and a calculator sub-table -- neither is benchmark
        # content, and both must survive a derived-subset write untouched.
        "max_hr_bpm": 190,
        "mycalc": {"custom_threshold": 42},
        "benchmarks": {
            "athlete": {
                "max_hr_bpm": [
                    {
                        "value": 190,
                        "measured_on": date(2024, 1, 1),
                        "applies_from": date(2023, 6, 1),
                    },
                    {
                        "value": 192,
                        "measured_on": date(2024, 6, 1),
                        "source": _derived_source(
                            "hr_ceiling_v1",
                            document="workouts/2024-06-01-run.md",
                            inputs="recorded hr stream",
                            citation="cite_a",
                        ),
                    },
                ],
                "resting_hr_bpm": [
                    {
                        "value": 45,
                        "measured_on": date(2024, 3, 1),
                        "source": _derived_source(
                            "resting_hr_v1",
                            document="workouts/2024-03-01-run.md",
                            inputs="recorded hr stream",
                            citation="cite_a",
                        ),
                    },
                ],
            },
            "run": {
                "threshold_pace_s_per_km": [
                    {
                        "value": 300,
                        "measured_on": date(2024, 2, 1),
                        "note": "watch effort",
                        "sensor": "stryd",
                    },
                    {
                        "value": 290,
                        "measured_on": date(2024, 7, 1),
                        "source": _derived_source(
                            "riegel_race_equivalence",
                            document="workouts/2024-07-01-run.md",
                            inputs="official distance, official time",
                            citation="riegel_1981",
                        ),
                    },
                ],
                "vo2max_score": [
                    {"value": 55, "measured_on": date(2024, 5, 1)},
                ],
            },
            "ride": {
                "ftp_watts": [
                    {
                        "value": 250,
                        "measured_on": date(2024, 4, 1),
                        "source": _derived_source(
                            "ftp_v1",
                            document="workouts/2024-04-01-ride.md",
                            inputs="power stream",
                            citation="cite_a",
                        ),
                    },
                ],
                "lthr_bpm": [
                    {
                        "value": 155,
                        "measured_on": date(2024, 8, 1),
                        "source": {"kind": "measured", "lab": "xyz"},
                    },
                    {
                        "value": 160,
                        "measured_on": date(2024, 8, 5),
                        "source": _derived_source(
                            "sustained_effort_mean_hr",
                            document="workouts/2024-08-05-ride.md",
                            inputs="recorded hr stream",
                            citation="cite_a",
                        ),
                    },
                ],
            },
            "swim": {
                "lthr_bpm": [
                    {
                        "value": 150,
                        "measured_on": date(2024, 9, 1),
                        "source": _derived_source(
                            "sustained_effort_mean_hr",
                            document="workouts/2024-09-01-swim.md",
                            inputs="recorded hr stream",
                            citation="cite_a",
                        ),
                    },
                ],
            },
        },
    }


def _seed_derived_subset_profile(tmp_path: Path) -> Path:
    """Write :func:`_seed_derived_subset_document` to disk as the
    hand-written starting file, and return its path."""
    save_profile(tmp_path, AthleteProfile(data=_seed_derived_subset_document()))
    return tmp_path / PROFILE_FILENAME


def _seed_derived_entries() -> tuple[Benchmark, ...]:
    """The six derived entries the seed document carries, as typed
    :class:`Benchmark` values -- exactly what a derivation pass finding the
    same six tags again would hand to
    :meth:`AthleteProfile.with_derived_benchmarks`. The seed's *measured*
    ``ride/lthr_bpm`` entry (2024-08-01) is deliberately absent: a measured
    entry is never supplied to ``with_derived_benchmarks``, only retained by
    it."""
    return (
        Benchmark(
            kind=BenchmarkKind.MAX_HR_BPM,
            discipline=None,
            value=192,
            measured_on=date(2024, 6, 1),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="hr_ceiling_v1",
                document="workouts/2024-06-01-run.md",
                inputs="recorded hr stream",
                citation="cite_a",
            ),
        ),
        Benchmark(
            kind=BenchmarkKind.RESTING_HR_BPM,
            discipline=None,
            value=45,
            measured_on=date(2024, 3, 1),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="resting_hr_v1",
                document="workouts/2024-03-01-run.md",
                inputs="recorded hr stream",
                citation="cite_a",
            ),
        ),
        Benchmark(
            kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
            discipline=Sport.RUN,
            value=290,
            measured_on=date(2024, 7, 1),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="riegel_race_equivalence",
                document="workouts/2024-07-01-run.md",
                inputs="official distance, official time",
                citation="riegel_1981",
            ),
        ),
        Benchmark(
            kind=BenchmarkKind.FTP_WATTS,
            discipline=Sport.RIDE,
            value=250,
            measured_on=date(2024, 4, 1),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="ftp_v1",
                document="workouts/2024-04-01-ride.md",
                inputs="power stream",
                citation="cite_a",
            ),
        ),
        Benchmark(
            kind=BenchmarkKind.LTHR_BPM,
            discipline=Sport.RIDE,
            value=160,
            measured_on=date(2024, 8, 5),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="sustained_effort_mean_hr",
                document="workouts/2024-08-05-ride.md",
                inputs="recorded hr stream",
                citation="cite_a",
            ),
        ),
        Benchmark(
            kind=BenchmarkKind.LTHR_BPM,
            discipline=Sport.SWIM,
            value=150,
            measured_on=date(2024, 9, 1),
            source=BenchmarkSource(
                kind=BenchmarkSourceKind.DERIVED,
                method="sustained_effort_mean_hr",
                document="workouts/2024-09-01-swim.md",
                inputs="recorded hr stream",
                citation="cite_a",
            ),
        ),
    )


def test_is_recorded_distinguishes_hand_written_derived_and_absent(
    tmp_path: Path,
) -> None:
    """``is_recorded`` is ``True`` for the hand-written entry itself and for
    a *measured* entry, ``False`` for a derived entry at the same
    kind/discipline on a different date, ``False`` for a key nothing
    occupies at all, and ``False`` when only the discipline or only the kind
    at an otherwise-occupied date differs from what is on file -- proving
    the query's key is checked component-by-component, not merely "some
    entry exists on this date" (Req 6.1, design: ProfileDerivedWrite)."""
    _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    assert profile.is_recorded(
        BenchmarkKind.MAX_HR_BPM, discipline=None, measured_on=date(2024, 1, 1)
    ), "the hand-written entry itself must read as recorded"
    assert not profile.is_recorded(
        BenchmarkKind.MAX_HR_BPM, discipline=None, measured_on=date(2024, 6, 1)
    ), "a derived entry at that key must not read as recorded"
    assert not profile.is_recorded(
        BenchmarkKind.MAX_HR_BPM, discipline=None, measured_on=date(2099, 1, 1)
    ), "an absent key must not read as recorded"

    # A measured entry -- source present but not derived -- reads exactly
    # like a hand-written one (source absent): both are "recorded" (Req 6.1).
    assert profile.is_recorded(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RIDE, measured_on=date(2024, 8, 1)
    ), "a measured entry must read as recorded, the same as a hand-written one"

    # The kind and discipline both belong to the query key -- an entry at
    # the right date under the wrong discipline, or the wrong kind, must not
    # be found (a query ignoring either component would wrongly match here).
    assert not profile.is_recorded(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RIDE,
        measured_on=date(2024, 2, 1),  # the hand-written run/threshold_pace date
    ), "the hand-written entry at this date is scoped to Run, not Ride"
    assert not profile.is_recorded(
        BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        measured_on=date(2024, 1, 1),  # the hand-written max_hr_bpm date
    ), "the hand-written entry at this date is max_hr_bpm, not resting_hr_bpm"


def test_with_derived_benchmarks_empty_set_removes_derived_preserves_rest(
    tmp_path: Path,
) -> None:
    """Writing an empty derived set removes every derived entry -- including
    a whole group and its scope table when they held nothing else -- while
    every hand-written and measured entry (with its ``note``,
    ``applies_from``, and unrecognized inner keys both at the entry level
    and inside a measured ``source``), every unrecognized quantity table,
    and every non-benchmark top-level key and table, survives exactly as it
    was (Req 6.1, 6.3, 6.4, 6.6)."""
    path = _seed_derived_subset_profile(tmp_path)

    pre = tomllib.loads(path.read_text())
    # Precondition: every shape this test claims to remove or preserve is
    # actually present before the call -- not merely asserted afterward.
    assert pre["max_hr_bpm"] == 190
    assert pre["mycalc"]["custom_threshold"] == 42
    assert len(pre["benchmarks"]["athlete"]["max_hr_bpm"]) == 2
    assert "resting_hr_bpm" in pre["benchmarks"]["athlete"]
    assert len(pre["benchmarks"]["run"]["threshold_pace_s_per_km"]) == 2
    assert "ftp_watts" in pre["benchmarks"]["ride"]
    assert len(pre["benchmarks"]["ride"]["lthr_bpm"]) == 2
    assert "swim" in pre["benchmarks"]

    profile = load_profile(tmp_path)
    updated = profile.with_derived_benchmarks(())
    save_profile(tmp_path, updated)

    raw = tomllib.loads(path.read_text())

    # Non-benchmark content is untouched: a flat top-level key this store
    # does not manage at all, and a whole calculator sub-table.
    assert raw["max_hr_bpm"] == 190
    assert raw["mycalc"] == {"custom_threshold": 42}

    # The whole-derived group that shared a scope with a surviving group:
    # the group is gone, the scope table survives.
    assert "resting_hr_bpm" not in raw["benchmarks"]["athlete"]
    assert raw["benchmarks"]["athlete"]["max_hr_bpm"] == [
        {
            "value": 190,
            "measured_on": date(2024, 1, 1),
            "applies_from": date(2023, 6, 1),
        }
    ]

    # The mixed discipline-scoped group: derived entry gone, hand-written
    # entry survives with its note and its unrecognized inner key.
    assert raw["benchmarks"]["run"]["threshold_pace_s_per_km"] == [
        {
            "value": 300,
            "measured_on": date(2024, 2, 1),
            "note": "watch effort",
            "sensor": "stryd",
        }
    ]

    # The unrecognized quantity table is untouched, byte-for-byte in shape.
    assert raw["benchmarks"]["run"]["vo2max_score"] == [
        {"value": 55, "measured_on": date(2024, 5, 1)}
    ]

    # The all-derived group sharing "ride" with a mixed group: the group is
    # gone, but "ride" itself survives because lthr_bpm's measured entry
    # keeps it non-empty.
    assert "ftp_watts" not in raw["benchmarks"]["ride"]
    assert raw["benchmarks"]["ride"]["lthr_bpm"] == [
        {
            "value": 155,
            "measured_on": date(2024, 8, 1),
            "source": {"kind": "measured", "lab": "xyz"},
        }
    ]

    # The whole-derived group that was the *sole* group under its scope:
    # the scope table itself is dropped, not left empty.
    assert "swim" not in raw["benchmarks"]


def test_with_derived_benchmarks_replaces_prior_derived_value_dropping_old(
    tmp_path: Path,
) -> None:
    """A second derivation run that finds a *different* date for the same
    quantity replaces the old derived entry outright -- it does not retain
    the stale one alongside the new one (the named mutation this task's
    pin must die on: retaining derived entries instead of replacing them)."""
    path = _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    # Precondition: the old derived date is present before the call.
    assert any(
        entry.kind is BenchmarkKind.MAX_HR_BPM and entry.measured_on == date(2024, 6, 1)
        for entry in profile.benchmarks.entries
    )

    refreshed_max_hr = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=200,
        measured_on=date(2024, 9, 1),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="hr_ceiling_v1",
            document="workouts/2024-09-01-run.md",
            inputs="recorded hr stream",
            citation="cite_a",
        ),
    )
    other_derived = _seed_derived_entries()[1:]  # unchanged resting/pace/ftp

    updated = profile.with_derived_benchmarks((refreshed_max_hr, *other_derived))
    save_profile(tmp_path, updated)

    raw = tomllib.loads(path.read_text())
    dates = [
        entry["measured_on"] for entry in raw["benchmarks"]["athlete"]["max_hr_bpm"]
    ]
    assert date(2024, 6, 1) not in dates, "the stale derived date must not survive"
    assert dates == [date(2024, 1, 1), date(2024, 9, 1)]


def test_with_derived_benchmarks_empty_write_from_all_derived_drops_benchmarks_table(
    tmp_path: Path,
) -> None:
    """A profile whose *only* benchmark content is one derived entry,
    written through ``with_derived_benchmarks(())``, leaves the document
    with no ``benchmarks`` table at all -- not a bare, empty one -- mirroring
    the rule ``save_profile`` already applies to a benchmark-free profile.
    A second empty write from the resulting file is byte-identical (Req 6.4,
    6.5, 6.6)."""
    path = tmp_path / PROFILE_FILENAME
    seed = AthleteProfile(
        data={
            "benchmarks": {
                "ride": {
                    "ftp_watts": [
                        {
                            "value": 250,
                            "measured_on": date(2024, 4, 1),
                            "source": _derived_source(
                                "ftp_v1",
                                document="workouts/2024-04-01-ride.md",
                                inputs="power stream",
                                citation="cite_a",
                            ),
                        }
                    ]
                }
            }
        }
    )
    save_profile(tmp_path, seed)
    # Precondition: the benchmarks table -- and the entry inside it -- are
    # actually present before the empty write.
    pre = tomllib.loads(path.read_text())
    assert pre["benchmarks"]["ride"]["ftp_watts"][0]["value"] == 250

    save_profile(tmp_path, load_profile(tmp_path).with_derived_benchmarks(()))
    first_bytes = path.read_bytes()
    raw = tomllib.loads(path.read_text())
    assert "benchmarks" not in raw

    save_profile(tmp_path, load_profile(tmp_path).with_derived_benchmarks(()))
    second_bytes = path.read_bytes()
    assert first_bytes == second_bytes


def test_with_derived_benchmarks_twice_produces_byte_identical_files(
    tmp_path: Path,
) -> None:
    """Writing the same derived set twice, from a fresh load each time,
    leaves the file byte-identical (Req 6.5)."""
    path = _seed_derived_subset_profile(tmp_path)
    derived = _seed_derived_entries()

    save_profile(tmp_path, load_profile(tmp_path).with_derived_benchmarks(derived))
    first_bytes = path.read_bytes()

    save_profile(tmp_path, load_profile(tmp_path).with_derived_benchmarks(derived))
    second_bytes = path.read_bytes()

    assert first_bytes == second_bytes


@pytest.mark.parametrize(
    "bad_source",
    [None, BenchmarkSource(kind=BenchmarkSourceKind.MEASURED)],
    ids=["absent", "measured"],
)
def test_with_derived_benchmarks_rejects_entry_without_derived_provenance(
    tmp_path: Path, bad_source: BenchmarkSource | None
) -> None:
    """An entry lacking derived provenance is refused before anything is
    stored -- a backstop behind the pass's own filter (Req 6.1)."""
    profile = load_profile(tmp_path)
    bad_entry = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=250,
        measured_on=date(2025, 1, 1),
        source=bad_source,
    )

    with pytest.raises(ValueError, match="derived provenance"):
        profile.with_derived_benchmarks((bad_entry,))


def test_with_derived_benchmarks_rejects_entry_colliding_with_retained_entry(
    tmp_path: Path,
) -> None:
    """A supplied derived entry may never occupy the same key as a retained
    non-derived entry, storing nothing on the collision (Req 6.1)."""
    _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    colliding = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=999,
        measured_on=date(2024, 1, 1),  # the hand-written entry's own date
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="hr_ceiling_v1",
            document="workouts/2024-01-01-run.md",
            inputs="recorded hr stream",
            citation="cite_a",
        ),
    )

    with pytest.raises(ValueError, match="collides"):
        profile.with_derived_benchmarks((colliding,))


def test_with_derived_benchmarks_accepts_entry_at_retained_date_under_other_discipline(
    tmp_path: Path,
) -> None:
    """The collision key is ``(discipline, kind, measured_on)`` in full: a
    derived entry sharing a retained entry's *date and kind* but a different
    *discipline* is not a collision at all and must be accepted (a
    collision check that dropped ``discipline`` from the key would wrongly
    refuse this)."""
    _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    same_date_other_discipline = Benchmark(
        kind=BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RIDE,  # the hand-written entry at this date is Run
        value=280,
        measured_on=date(2024, 2, 1),  # the hand-written run/threshold_pace date
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="riegel_race_equivalence",
            document="workouts/2024-02-01-ride.md",
            inputs="official distance, official time",
            citation="riegel_1981",
        ),
    )

    updated = profile.with_derived_benchmarks((same_date_other_discipline,))
    save_profile(tmp_path, updated)

    raw = tomllib.loads((tmp_path / PROFILE_FILENAME).read_text())
    assert raw["benchmarks"]["ride"]["threshold_pace_s_per_km"] == [
        {
            "value": 280,
            "measured_on": date(2024, 2, 1),
            "source": {
                "kind": "derived",
                "method": "riegel_race_equivalence",
                "document": "workouts/2024-02-01-ride.md",
                "inputs": "official distance, official time",
                "citation": "riegel_1981",
            },
        }
    ]


def test_with_derived_benchmarks_allows_refreshing_a_derived_entry_at_the_same_key(
    tmp_path: Path,
) -> None:
    """The collision backstop is scoped to *retained* (non-derived) entries
    only -- a derived entry may freely occupy the same key an existing
    derived entry already held (a same-key refresh), which must not be
    rejected as a collision."""
    path = _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    refreshed = Benchmark(
        kind=BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=195,
        measured_on=date(2024, 6, 1),  # same key as the seed's derived entry
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="hr_ceiling_v1",
            document="workouts/2024-06-01-run.md",
            inputs="recorded hr stream",
            citation="cite_a",
        ),
    )

    updated = profile.with_derived_benchmarks((refreshed,))
    save_profile(tmp_path, updated)

    raw = tomllib.loads(path.read_text())
    max_hr_entries = raw["benchmarks"]["athlete"]["max_hr_bpm"]
    assert len(max_hr_entries) == 2, "the same-key refresh must not duplicate the entry"
    refreshed_entry = next(
        entry for entry in max_hr_entries if entry["measured_on"] == date(2024, 6, 1)
    )
    assert refreshed_entry["value"] == 195


def test_with_derived_benchmarks_overlays_stale_derived_entry_field_by_field(
    tmp_path: Path,
) -> None:
    """A fresh derived entry landing at the *same* ``measured_on`` as a
    stale derived entry already on file is NOT dropped and replaced
    wholesale -- it is overlaid onto that stale record through the same
    :func:`_merge_benchmarks_document` :meth:`with_benchmark` uses. The
    stale entry's ``note``, its ``applies_from`` date, its unrecognized
    entry-level key and its unrecognized inner ``source`` key all survive;
    only the five recognized ``source`` fields are refreshed to the new
    derivation's values (design: ProfileDerivedWrite)."""
    seed: dict[str, object] = {
        "benchmarks": {
            "ride": {
                "ftp_watts": [
                    {
                        "value": 240,
                        "measured_on": date(2024, 4, 1),
                        "note": "stale note",
                        "applies_from": date(2024, 3, 1),
                        "widget": "gadget",
                        "source": {
                            "kind": "derived",
                            "method": "ftp_v0",
                            "document": "workouts/2024-04-01-old.md",
                            "inputs": "old inputs",
                            "citation": "old_cite",
                            "extra": "keepme",
                        },
                    }
                ]
            }
        }
    }
    with (tmp_path / PROFILE_FILENAME).open("wb") as handle:
        tomli_w.dump(seed, handle)
    path = tmp_path / PROFILE_FILENAME

    # Precondition: the stale record's fields are what this test claims to
    # overlay, not something already matching the fresh values below.
    pre_entry = tomllib.loads(path.read_text())["benchmarks"]["ride"]["ftp_watts"][0]
    assert pre_entry["value"] == 240
    assert pre_entry["source"]["method"] == "ftp_v0"

    profile = load_profile(tmp_path)
    fresh = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=260,
        measured_on=date(2024, 4, 1),  # the same date as the stale derived entry
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="ftp_v1",
            document="workouts/2024-04-01-new.md",
            inputs="new inputs",
            citation="new_cite",
        ),
    )

    updated = profile.with_derived_benchmarks((fresh,))
    save_profile(tmp_path, updated)

    raw = tomllib.loads(path.read_text())
    entries = raw["benchmarks"]["ride"]["ftp_watts"]
    assert len(entries) == 1, "the same-date refresh must not duplicate the entry"
    entry = entries[0]

    # The value and the five recognized source fields are refreshed.
    assert entry["value"] == 260
    assert entry["source"]["method"] == "ftp_v1"
    assert entry["source"]["document"] == "workouts/2024-04-01-new.md"
    assert entry["source"]["inputs"] == "new inputs"
    assert entry["source"]["citation"] == "new_cite"

    # The stale entry's note, applies_from, unrecognized entry-level key and
    # unrecognized inner source key all survive the overlay untouched.
    assert entry["note"] == "stale note"
    assert entry["applies_from"] == date(2024, 3, 1)
    assert entry["widget"] == "gadget"
    assert entry["source"]["extra"] == "keepme"


def test_with_derived_benchmarks_refuses_unreadable_document_at_construction(
    tmp_path: Path,
) -> None:
    """An entry that carries derived provenance but an incomplete detail
    record serializes to a shape the profile reader would reject; the
    refusal surfaces at :class:`AthleteProfile` construction inside
    ``with_derived_benchmarks`` itself -- via the same eager
    :meth:`AthleteProfile.__post_init__` re-parse every profile goes
    through -- as a :class:`ProfileError`, before ``save_profile`` or any
    file write is ever reached (Req 6.7).

    This method never touches the filesystem -- ``save_profile`` is not
    called here at all -- so "the file is left untouched" is not an
    observable this test can pin; that half of Req 6.7 (a refused *write*
    leaves the target file byte-identical) is PRESERVED-ONLY by
    ``test_save_refuses_a_document_the_reader_would_reject_and_leaves_file_untouched``,
    which drives the refusal through ``save_profile`` directly and asserts
    the file's bytes are unchanged.
    """
    _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    incomplete = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,  # a fresh group -- no collision with anything retained
        value=250,
        measured_on=date(2030, 1, 1),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED
        ),  # missing detail fields
    )

    with pytest.raises(ProfileError):
        profile.with_derived_benchmarks((incomplete,))


def test_with_derived_benchmarks_returns_new_object_without_mutating_original(
    tmp_path: Path,
) -> None:
    """``with_derived_benchmarks`` returns a fresh :class:`AthleteProfile`
    without mutating ``self`` -- the base profile's own ``data``, including
    an unmanaged nested table, is left exactly as it was (M: mutate
    ``self.data`` in place instead of building a fresh ``document`` via
    ``copy.deepcopy``)."""
    base = AthleteProfile(
        data={
            "max_hr_bpm": 195,
            "other": {"nested": {"k": 1}},
            "benchmarks": {
                "run": {
                    "threshold_pace_s_per_km": [
                        {
                            "value": 300,
                            "measured_on": date(2024, 2, 1),
                        }
                    ]
                }
            },
        }
    )

    fresh = Benchmark(
        kind=BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=250,
        measured_on=date(2026, 1, 1),
        source=BenchmarkSource(
            kind=BenchmarkSourceKind.DERIVED,
            method="ftp_v1",
            document="workouts/2026-01-01-ride.md",
            inputs="power stream",
            citation="cite_a",
        ),
    )

    data_before = copy.deepcopy(dict(base.data))
    assert "ride" not in base.data["benchmarks"]  # type: ignore[operator]

    updated = base.with_derived_benchmarks((fresh,))

    assert updated is not base
    assert updated.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE)
    assert base.data == data_before
    assert "ride" not in base.data["benchmarks"]  # type: ignore[operator]
    # The unmanaged nested table is deep-copied, never shared (Req 6.6).
    assert base.data["other"] is not updated.data["other"]
    assert (
        base.data["other"]["nested"]  # type: ignore[index]
        is not updated.data["other"]["nested"]  # type: ignore[index]
    )


def test_save_profile_after_with_derived_benchmarks_write_leaves_no_temp_files(
    tmp_path: Path,
) -> None:
    """Persisting a profile built by ``with_derived_benchmarks`` goes
    through the existing atomic save path: no partial or temporary file is
    left behind (Req 6.8)."""
    _seed_derived_subset_profile(tmp_path)
    profile = load_profile(tmp_path)

    updated = profile.with_derived_benchmarks(())
    save_profile(tmp_path, updated)

    leftovers = [p for p in tmp_path.iterdir() if p.name != PROFILE_FILENAME]
    assert leftovers == []

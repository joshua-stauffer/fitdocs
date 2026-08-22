"""Tests for the profile store's benchmark reads (task 3.1, Req 1.1, 2.9, 2.10,
3.7, 7.1, 7.2, 7.4, 7.7, 9.5).

Three things this task adds to :class:`~fitdocs.load.profile.AthleteProfile`
that the rest of the suite does not otherwise exercise:

* Construction is *eager*: the schema-version guard and the benchmark parser
  both run in ``__post_init__``, not on first query, so a malformed store
  fails before a caller can act on it at all (Req 2.9, 2.10).
* :class:`~fitdocs.load.profile.ProfileError` is now a subclass of
  :class:`fitdocs.athlete.AthleteFileError`, so one file has one catchable
  voice (Req 2.10).
* Two new read queries -- :meth:`~fitdocs.load.profile.AthleteProfile.benchmark`
  (date-scoped applicability) and
  :meth:`~fitdocs.load.profile.AthleteProfile.has_benchmark` (undated
  presence) -- delegate to :class:`fitdocs.benchmarks.BenchmarkSet` and carry
  no per-activity or per-pass state of their own (Req 7.1, 7.2, 7.4, 7.7,
  9.5).
"""

from __future__ import annotations

import inspect
import tomllib
from datetime import date
from pathlib import Path

import pytest

from fitdocs import Sport
from fitdocs.athlete import ATHLETE_SCHEMA_VERSION, AthleteFileError
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.profile import AthleteProfile, ProfileError, load_profile


def _body(message: str, *paths: Path | str) -> str:
    """Normalize every embedded path out of ``message`` before token assertions.

    A pytest ``tmp_path`` carries the session counter and always ends in a
    digit, so asserting a bare digit/token against a raw message risks
    matching the *path*, not the body (documented pitfall from task 2.1).
    """
    body = message
    for path in paths:
        body = body.replace(str(path), "<path>")
    return body


# --- eager construction: ordering (Req 2.9, 2.10) ---------------------------


def test_malformed_benchmarks_raises_at_construction_before_any_write(
    tmp_path: Path,
) -> None:
    """A malformed ``[benchmarks]`` region raises at construction, before any
    caller code runs. ``tmp_path`` is never written to by this test (no
    ``save_profile`` call is made here)."""
    malformed = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": -5, "measured_on": date(2024, 1, 1)},
                ]
            }
        }
    }

    with pytest.raises(ProfileError):
        # Construction is the only statement expected to run to completion
        # short of raising; nothing below it should ever execute.
        AthleteProfile(data=malformed)

    assert list(tmp_path.iterdir()) == []


def test_malformed_benchmarks_message_names_the_file() -> None:
    malformed = {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": -5, "measured_on": date(2024, 1, 1)},
                ]
            }
        }
    }

    with pytest.raises(ProfileError) as exc:
        AthleteProfile(data=malformed)

    message = str(exc.value)
    assert "athlete.toml" in message
    body = _body(message)
    assert "ftp_watts" in body


def test_declared_future_schema_version_raises_at_construction() -> None:
    """A document declaring a ``profile_version`` newer than this fitdocs
    supports raises at construction, via the schema-version guard that runs
    in ``__post_init__``."""
    with pytest.raises(AthleteFileError):
        AthleteProfile(data={"profile_version": ATHLETE_SCHEMA_VERSION + 1})


def test_refused_schema_version_message_surfaces_before_benchmark_parsing() -> None:
    """A document that is *both* version-refused and benchmark-malformed
    raises the version-refused message, not the benchmark one -- proving the
    schema-version guard runs before :func:`~fitdocs.benchmarks.parse_benchmarks`,
    not after it. A fixture that only fails one of the two checks cannot
    distinguish the two orderings, since either ordering would raise the same
    way; this one fails both, so only the winning check's message can appear."""
    doc = {
        "profile_version": ATHLETE_SCHEMA_VERSION + 1,
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": -5, "measured_on": date(2024, 1, 1)},
                ]
            }
        },
    }

    with pytest.raises(AthleteFileError) as exc:
        AthleteProfile(data=doc)

    message = str(exc.value)
    assert "athlete.toml" in message
    body = _body(message)
    assert "newer than the schema version" in body
    assert "finite, positive number" not in body


# --- error type: one catchable voice (Req 2.10) -----------------------------


def test_profile_error_is_an_athlete_file_error() -> None:
    """Catching the athlete-inputs reader's error type must also catch a
    profile-store construction failure -- the whole point of the subclass
    relationship."""
    malformed = {
        "benchmarks": {
            "athlete": {
                "resting_hr_bpm": [
                    {"value": 0, "measured_on": date(2024, 1, 1)},
                ]
            }
        }
    }

    with pytest.raises(AthleteFileError):
        AthleteProfile(data=malformed)


def test_profile_error_instance_is_athlete_file_error_instance() -> None:
    malformed = {"benchmarks": {"athlete": {"resting_hr_bpm": [{"value": 0}]}}}
    try:
        AthleteProfile(data=malformed)
        pytest.fail("expected ProfileError")
    except ProfileError as exc:
        assert isinstance(exc, AthleteFileError)


# --- undated applicability query returns nothing (Req 3.7, 9.5) ------------


def _document_with_ftp(*entries: tuple[str, float]) -> dict[str, object]:
    """Build a decoded ``athlete.toml``-shaped document with dated FTP entries
    for ``Sport.RUN``. Each entry is ``(iso_date, value)``."""
    return {
        "benchmarks": {
            "run": {
                "ftp_watts": [
                    {"value": value, "measured_on": date.fromisoformat(when)}
                    for when, value in entries
                ]
            }
        }
    }


def test_undated_applicability_query_returns_nothing_though_benchmarks_exist() -> None:
    """An activity with no parseable date has no applicable benchmark, full
    stop -- even when real benchmarks are on file, so the ``None`` result is a
    decision, not a vacuous consequence of an empty set."""
    profile = AthleteProfile(data=_document_with_ftp(("2023-01-01", 250.0)))

    assert (
        profile.benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=None)
        is None
    )
    # The entry genuinely is on file -- presence stays true.
    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN)


# --- presence vs. applicability are separable (Req 3.5, 7.1, 7.2) ----------


def test_future_history_gives_presence_true_and_applicability_none() -> None:
    """A history entirely in the future: presence must stay true (something
    genuinely is on file) while an applicability query for an earlier date
    finds nothing yet."""
    profile = AthleteProfile(data=_document_with_ftp(("2099-01-01", 400.0)))

    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True
    assert (
        profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 6, 1)
        )
        is None
    )


def test_empty_history_gives_presence_false() -> None:
    profile = AthleteProfile(data={})

    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is False
    assert (
        profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 6, 1)
        )
        is None
    )


# --- no per-activity state: one instance, many dates (Req 7.4, 7.7) --------


def test_one_profile_instance_answers_two_dates_differently() -> None:
    """The store binds nothing to a particular activity: the same profile
    instance, queried with two different dates, gives the two different
    answers a date-aware selection implies."""
    profile = AthleteProfile(
        data=_document_with_ftp(("2023-01-01", 250.0), ("2024-06-01", 300.0))
    )

    early = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2023, 6, 1)
    )
    late = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 12, 1)
    )

    assert early is not None and early.value == 250.0
    assert late is not None and late.value == 300.0


def test_load_profile_signature_is_unchanged() -> None:
    """The profile loader's signature is unchanged by this task: still exactly
    one positional ``data_root`` parameter, returning an ``AthleteProfile``."""
    params = list(inspect.signature(load_profile).parameters)
    assert params == ["data_root"]


# --- absent file: empty profile, creates nothing (Req 1.9, 9.2) ------------


def test_absent_file_yields_empty_profile_and_creates_nothing_in_the_root(
    tmp_path: Path,
) -> None:
    """Snapshot the *whole* data root, not just the athlete file: an absent
    file must yield an empty profile without creating anything at all."""
    sibling = tmp_path / "some_workout.md"
    sibling.write_text("unrelated content\n")
    before = sorted(p.name for p in tmp_path.iterdir())

    profile = load_profile(tmp_path)

    assert profile.data == {}
    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is False
    after = sorted(p.name for p in tmp_path.iterdir())
    assert after == before


# --- parsed benchmarks and the raw document never disagree (design intent) -


def test_parsed_benchmarks_and_raw_document_agree_after_a_reload(
    tmp_path: Path,
) -> None:
    (tmp_path / "athlete.toml").write_text(
        "[[benchmarks.run.ftp_watts]]\nvalue = 280\nmeasured_on = 2024-03-01\n"
    )

    profile = load_profile(tmp_path)
    raw = tomllib.loads((tmp_path / "athlete.toml").read_text())

    resolved = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2024, 6, 1)
    )
    assert resolved is not None
    raw_entry = raw["benchmarks"]["run"]["ftp_watts"][0]
    assert resolved.value == raw_entry["value"]
    assert resolved.measured_on == raw_entry["measured_on"]

"""Frontmatter schema, key omission, identity, and byte-stable emission.

These pin :func:`fitdocs.render.frontmatter.build_frontmatter` against the
approved schema (design §FrontmatterBuilder; Req 5.1, 5.2, 5.6, 3.4): a fixed
key order, keys omitted entirely when their value is absent (never ``null``,
``0``, or a placeholder -- 5.2), the canonical session ``uuid`` included only
when recorded (5.6), ``indoor`` only when true, ``sources`` rendered verbatim
in append order with the last entry the current render source (3.4), genuine
recorded zeros preserved (13.3), and byte-identical output for identical input
(4.1). Contexts are built over real parsed activities so the contract is proven
against the fit-ingest public API, with a fixed timezone so local dates and
times are deterministic.
"""

from __future__ import annotations

import dataclasses
from datetime import timedelta, timezone, tzinfo

import yaml

from fitdocs import DerivedMetrics, compute_metrics, parse_fit
from fitdocs.contract import DOC_VERSION
from fitdocs.render import DocContext
from fitdocs.render.frontmatter import build_frontmatter

# A fixed offset zone: the run/ride fixtures start 2021-09-08 01:46:40 UTC, so
# local time is 2021-09-07 19:46:40-06:00 -- pinned and deterministic.
TZ: tzinfo = timezone(timedelta(hours=-6))

_REFS: tuple[str, ...] = ("fit-archive/aaaa.fit", "fit-archive/bbbb.fit")

# The canonical form of the fixture's 16-byte SESSION UUID (bytes 100..115).
_EXPECTED_UUID = "64656667-6869-6a6b-6c6d-6e6f70717273"


def _ctx(
    fit_bytes: bytes,
    *,
    source_refs: tuple[str, ...] = _REFS,
    doc_stem: str = "2021-09-07-run-1946",
    activity_replace: dict[str, object] | None = None,
    metrics: DerivedMetrics | None = None,
) -> DocContext:
    activity = parse_fit(fit_bytes)
    if activity_replace:
        activity = dataclasses.replace(activity, **activity_replace)
    return DocContext(
        activity=activity,
        metrics=metrics if metrics is not None else compute_metrics(activity),
        athlete=None,
        doc_stem=doc_stem,
        source_refs=source_refs,
        tz=TZ,
    )


def test_rich_run_frontmatter_is_exact(run_fit_bytes: bytes) -> None:
    """A rich run renders the full schema in the fixed key order, wrapped in
    ``---`` fences. The run has no session UUID, is outdoor, and records no
    power -- so ``uuid``, ``indoor``, and ``avg_power_w`` are absent, proving
    omission is the single emission path, not a special case."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    assert out == (
        "---\n"
        "title: Run 2021-09-07 19:46\n"
        "type: workout\n"
        "generator: fitdocs\n"
        "doc_version: 5\n"
        "date: '2021-09-07'\n"
        "start_time: '2021-09-07T19:46:40-06:00'\n"
        "sport: Run\n"
        "modality: run\n"
        "distance_km: 0.03\n"
        "moving_time: 0:09\n"
        "avg_hr_bpm: 133\n"
        "elevation_gain_m: 9.0\n"
        "calories_kcal: 60\n"
        "sources:\n"
        "- fit-archive/aaaa.fit\n"
        "- fit-archive/bbbb.fit\n"
        "---\n"
    )


def test_wrapper_and_valid_yaml(run_fit_bytes: bytes) -> None:
    """Output is a fenced block whose interior is valid YAML."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    assert out.startswith("---\n")
    assert out.endswith("---\n")
    body = out[len("---\n") : -len("---\n")]
    data = yaml.safe_load(body)
    assert data["type"] == "workout"
    assert data["doc_version"] == DOC_VERSION == 5


def test_fixed_key_order(run_fit_bytes: bytes) -> None:
    """Top-level keys appear in the schema's fixed order."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    keys = [
        line.split(":", 1)[0]
        for line in out.splitlines()
        if line and not line.startswith(("-", " ")) and line != "---"
    ]
    assert keys == [
        "title",
        "type",
        "generator",
        "doc_version",
        "date",
        "start_time",
        "sport",
        "modality",
        "distance_km",
        "moving_time",
        "avg_hr_bpm",
        "elevation_gain_m",
        "calories_kcal",
        "sources",
    ]


def test_absent_metric_key_is_omitted_not_nulled(run_fit_bytes: bytes) -> None:
    """The run records no power: ``avg_power_w`` is absent entirely, and no
    ``null``/placeholder leaks into the document (5.2)."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    assert "avg_power_w" not in out
    assert "null" not in out
    assert "None" not in out


def test_absent_elevation_key_is_omitted(ride_fit_bytes: bytes) -> None:
    """The ride records no elevation gain: the key is omitted, while the power
    it *does* record is present."""
    out = build_frontmatter(_ctx(ride_fit_bytes))
    assert "elevation_gain_m" not in out
    assert "avg_power_w: 200" in out


def test_uuid_present_when_session_uuid_recorded(
    session_dev_fields_fit_bytes: bytes,
) -> None:
    """When the activity records a well-formed 16-byte SESSION UUID, the
    canonical form is emitted as the document identity (5.6)."""
    out = build_frontmatter(_ctx(session_dev_fields_fit_bytes))
    assert f"uuid: {_EXPECTED_UUID}\n" in out
    data = yaml.safe_load(out[len("---\n") : -len("---\n")])
    assert data["uuid"] == _EXPECTED_UUID


def test_uuid_absent_when_not_recorded(run_fit_bytes: bytes) -> None:
    """The run has no SESSION UUID developer field: no ``uuid`` key, and no
    sha256 fallback (that identity lives in ``sources``)."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    assert "uuid:" not in out


def test_indoor_present_only_when_true(run_fit_bytes: bytes) -> None:
    """``indoor: true`` appears only for an indoor activity; an outdoor one
    omits the key (never ``indoor: false``)."""
    outdoor = build_frontmatter(_ctx(run_fit_bytes))
    assert "indoor" not in outdoor

    indoor = build_frontmatter(
        _ctx(run_fit_bytes, activity_replace={"is_indoor": True})
    )
    assert "indoor: true\n" in indoor
    assert "indoor: false" not in indoor


def test_sources_rendered_verbatim_in_append_order(run_fit_bytes: bytes) -> None:
    """``sources`` is the verbatim, append-ordered list; the last entry is the
    current render source (3.4)."""
    refs = ("fit-archive/first.fit", "fit-archive/second.fit", "fit-archive/third.fit")
    out = build_frontmatter(_ctx(run_fit_bytes, source_refs=refs))
    data = yaml.safe_load(out[len("---\n") : -len("---\n")])
    assert data["sources"] == list(refs)
    assert data["sources"][-1] == "fit-archive/third.fit"


def test_sources_omitted_when_empty(run_fit_bytes: bytes) -> None:
    """An empty ``source_refs`` omits the key rather than emitting an empty
    list."""
    out = build_frontmatter(_ctx(run_fit_bytes, source_refs=()))
    assert "sources" not in out


def test_true_zero_metrics_emitted_as_values(run_fit_bytes: bytes) -> None:
    """A genuine recorded ``0`` is a real value, not absence: zeroed distance
    and power are emitted, never omitted (13.3)."""
    base = parse_fit(run_fit_bytes)
    zeroed = dataclasses.replace(compute_metrics(base), distance_m=0.0, avg_power_w=0.0)
    out = build_frontmatter(_ctx(run_fit_bytes, metrics=zeroed))
    assert "distance_km: 0.0\n" in out
    assert "avg_power_w: 0\n" in out


def test_title_degrades_without_start_time(run_fit_bytes: bytes) -> None:
    """With no recorded start time the title falls back to sport + doc stem (a
    non-empty, deterministic string) and the local date/time keys are omitted
    rather than fabricated."""
    out = build_frontmatter(
        _ctx(
            run_fit_bytes,
            doc_stem="undated-run-0123456789ab",
            activity_replace={"start_time": None},
        )
    )
    assert "title: Run undated-run-0123456789ab\n" in out
    assert "date:" not in out
    assert "start_time:" not in out


def test_output_is_byte_identical_across_calls(run_fit_bytes: bytes) -> None:
    """Identical context yields byte-identical frontmatter on every call
    (4.1)."""
    ctx = _ctx(run_fit_bytes)
    assert build_frontmatter(ctx) == build_frontmatter(ctx)

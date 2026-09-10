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
from fitdocs.contract import DOC_VERSION, user_owned_lines
from fitdocs.render import DocContext, render_document
from fitdocs.render.frontmatter import build_frontmatter

# A fixed offset zone: the run/ride fixtures start 2021-09-08 01:46:40 UTC, so
# local time is 2021-09-07 19:46:40-06:00 -- pinned and deterministic.
TZ: tzinfo = timezone(timedelta(hours=-6))

_REFS: tuple[str, ...] = ("fit-archive/aaaa.fit", "fit-archive/bbbb.fit")

# The canonical form of the fixture's 16-byte SESSION UUID (bytes 100..115).
_EXPECTED_UUID = "64656667-6869-6a6b-6c6d-6e6f70717273"

# The exact rich-run block (effort-tags task 2.1's empty-tuple pin reuses this
# byte-for-byte so the assertion cannot silently loosen from the pre-carry
# expectation pinned above).
_EXACT_RICH_RUN_BLOCK = (
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


def _ctx(
    fit_bytes: bytes,
    *,
    source_refs: tuple[str, ...] = _REFS,
    doc_stem: str = "2021-09-07-run-1946",
    activity_replace: dict[str, object] | None = None,
    metrics: DerivedMetrics | None = None,
    user_frontmatter: tuple[str, ...] = (),
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
        user_frontmatter=user_frontmatter,
    )


def test_rich_run_frontmatter_is_exact(run_fit_bytes: bytes) -> None:
    """A rich run renders the full schema in the fixed key order, wrapped in
    ``---`` fences. The run has no session UUID, is outdoor, and records no
    power -- so ``uuid``, ``indoor``, and ``avg_power_w`` are absent, proving
    omission is the single emission path, not a special case."""
    out = build_frontmatter(_ctx(run_fit_bytes))
    assert out == _EXACT_RICH_RUN_BLOCK


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


def test_empty_user_frontmatter_matches_pre_carry_block_exactly(
    run_fit_bytes: bytes,
) -> None:
    """An explicit empty tuple -- the default, and every first-time render --
    reproduces the exact block byte-for-byte (effort-tags Req 1.2, 1.3, 4.6):
    the carry is a pure addition, never a change to the untagged case."""
    out = build_frontmatter(_ctx(run_fit_bytes, user_frontmatter=()))
    assert out == _EXACT_RICH_RUN_BLOCK


def test_carried_lines_appended_after_managed_block_before_fence(
    run_fit_bytes: bytes,
) -> None:
    """Carried user-owned lines land after the last managed key and before
    the closing fence, and the whole block still parses as a mapping
    containing the user keys (effort-tags Req 4.5)."""
    carried = ("effort: race", "effort_time_s: 3600")
    out = build_frontmatter(_ctx(run_fit_bytes, user_frontmatter=carried))

    sources_index = out.index("sources:")
    effort_index = out.index("effort: race")
    assert sources_index < effort_index
    assert out.endswith("effort: race\neffort_time_s: 3600\n---\n")

    data = yaml.safe_load(out[len("---\n") : -len("---\n")])
    assert data["effort"] == "race"
    assert data["effort_time_s"] == 3600


def test_observable_single_carried_line_ends_block(run_fit_bytes: bytes) -> None:
    """The task's stated observable: a context carrying ``effort: race`` ends
    the block with ``effort: race\\n---\\n``."""
    out = build_frontmatter(_ctx(run_fit_bytes, user_frontmatter=("effort: race",)))
    assert out.endswith("effort: race\n---\n")


def test_carried_lines_byte_identical_and_nontrivial(run_fit_bytes: bytes) -> None:
    """Two calls over an identical context carrying lines are byte-identical
    (4.6), and the output is provably non-trivial: it differs from the same
    context's untagged rendering and actually contains the carried text (a
    constant function would satisfy byte-identity alone)."""
    carried = ("effort: race", "effort_time_s: 3600")
    ctx = _ctx(run_fit_bytes, user_frontmatter=carried)
    first = build_frontmatter(ctx)
    second = build_frontmatter(ctx)
    assert first == second
    assert "effort: race\neffort_time_s: 3600\n" in first
    assert first != build_frontmatter(_ctx(run_fit_bytes))


def test_carried_lines_round_trip_with_block_scalar(run_fit_bytes: bytes) -> None:
    """Scanning the builder's output with :func:`user_owned_lines` returns
    exactly the tuple that was passed in, for a set that includes a
    block-scalar value (effort-tags Req 4.5, 4.6) -- exercising the
    continuation path, not just single-line entries."""
    carried = (
        "effort: race",
        "effort_event: |",
        "  [[Boston Marathon 2024]]",
    )
    out = build_frontmatter(_ctx(run_fit_bytes, user_frontmatter=carried))
    assert user_owned_lines(out.split("\n")) == carried


def test_carried_tag_never_reaches_body_or_assets(run_fit_bytes: bytes) -> None:
    """A carried effort tag changes only the frontmatter block: the rendered
    document's body and assets are byte-for-byte identical with and without
    it (effort-tags Req 2.7) -- the tag is never rendered into the body and
    never changes a computed metric, load value, or chart on its account.

    ``build_frontmatter(ctx)`` is exactly the leading slice of
    ``render_document(ctx).markdown`` (both draw the frontmatter from the same
    context), so slicing it off isolates the body that follows for direct
    comparison.
    """
    tagged_ctx = _ctx(
        run_fit_bytes, user_frontmatter=("effort: race", "effort_time_s: 3600")
    )
    untagged_ctx = _ctx(run_fit_bytes, user_frontmatter=())

    tagged = render_document(tagged_ctx)
    untagged = render_document(untagged_ctx)

    tagged_body = tagged.markdown[len(build_frontmatter(tagged_ctx)) :]
    untagged_body = untagged.markdown[len(build_frontmatter(untagged_ctx)) :]

    assert tagged_body == untagged_body
    assert tagged.assets == untagged.assets


def test_doc_context_field_order_has_user_frontmatter_after_map_data() -> None:
    """The design fixes ``user_frontmatter`` immediately after ``map_data`` in
    :class:`DocContext`'s declaration order; every construction site in-repo
    is keyword-only so nothing observes this today, but the order is
    design-normative, so it is pinned here rather than left silently
    swappable."""
    field_names = [f.name for f in dataclasses.fields(DocContext)]
    assert field_names[-2:] == ["map_data", "user_frontmatter"]

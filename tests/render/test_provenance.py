"""The Channel Sources section (channel-merge task 3.2; Req 4.1-4.6, 4.8).

Pins :func:`fitdocs.render.provenance.channel_sources_section` against
design.md § ChannelSourcesSection with hand-built compositions: the exact body
text, the label table held equal to the two tables the page already uses, and
the reverse-direction import guard (design.md § Guards).

The views section at the end places the section in every view (task 3.3).
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
from collections.abc import Mapping
from datetime import timedelta, timezone
from pathlib import Path
from typing import Final

import pytest

import fitdocs.render
from fitdocs import Samples, compute_metrics, parse_fit
from fitdocs.compose.composer import compose_activity
from fitdocs.compose.types import (
    ChannelProvenance,
    ExtraAlignment,
    SourceContribution,
    StretchLag,
)
from fitdocs.identity.kinds import SourceKind
from fitdocs.model import DeviceInfo, Modality
from fitdocs.render import DocContext, render_document
from fitdocs.render.attribution import recording_device
from fitdocs.render.dynamics import DYNAMICS_DISPLAY
from fitdocs.render.provenance import CHANNEL_LABELS, channel_sources_section
from fitdocs.render.sections import _COVERAGE_CHANNELS
from tests.fixtures import builder, merge

_SENTENCE: Final[str] = (
    "Each channel below comes from one file: the base when it records the "
    "channel, otherwise the highest-ranked extra that records it."
)
_HEADER: Final[str] = (
    "| File | Role | Kind | Channels | Alignment |\n| --- | --- | --- | --- | --- |"
)
_FALLBACK: Final[str] = "at exact timestamps (no lag established)"


def _ctx(run_fit_bytes: bytes, provenance: ChannelProvenance | None) -> DocContext:
    activity = parse_fit(run_fit_bytes)
    return DocContext(
        activity=activity,
        metrics=compute_metrics(activity),
        athlete=None,
        doc_stem="2021-09-07-run-1946",
        source_refs=("fit-archive/aaaa.fit",),
        tz=timezone(timedelta(hours=-6)),
        channel_provenance=provenance,
    )


def _contrib(
    sha256: str,
    kind: SourceKind,
    channels: tuple[str, ...],
    *,
    manufacturer: str | None = None,
    alignment: ExtraAlignment | None = None,
) -> SourceContribution:
    return SourceContribution(
        sha256=sha256,
        kind=kind,
        manufacturer=manufacturer,
        devices=(),
        channels=channels,
        alignment=alignment,
    )


def _stretches(*keys: str | None) -> tuple[StretchLag, ...]:
    """One stretch per key, in the order given; lag 0 on the fallback."""
    return tuple(
        StretchLag(
            start=10 * i, stop=10 * i + 10, lag_s=0 if key is None else 1, key=key
        )
        for i, key in enumerate(keys)
    )


def _body(*rows: str) -> str:
    return "\n".join([_SENTENCE, "", _HEADER, *rows])


_BASE_RUN_CHANNELS: Final[tuple[str, ...]] = (
    "heart_rate_bpm",
    "cadence_rpm",
    "speed_mps",
    "distance_m",
    "altitude_m",
    "latitude_deg",
    "longitude_deg",
)


# --- the body text (Req 4.1, 4.2, 4.3, 4.4, 4.5) -----------------------------


def test_run_composition_is_exact(run_fit_bytes: bytes) -> None:
    """A phone-copy base and a Stryd-style original donating power and
    dynamics, aligned at three distance stretches: the whole body."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.PHONE_COPY, _BASE_RUN_CHANNELS),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("power_w", "stance_time_ms", "form_power_w"),
                manufacturer="stryd",
                alignment=ExtraAlignment(0, _stretches("distance_m") * 3),
            ),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | phone copy "
        "| Heart rate, Cadence, Speed, Distance, Altitude, GPS | – |",
        "| `fit-archive/bbbb.fit` | extra | original (stryd) "
        "| Power, Ground contact time, Form power | 3 stretches: 3 by distance |",
    )


def test_shifted_ride_with_one_stretch_is_singular_and_names_the_shift(
    run_fit_bytes: bytes,
) -> None:
    """A recorded shift of +3600 s subtracted from the extra reads as "-1 h"
    (the extra was moved back one hour); one stretch is singular. The phone
    copy's recorded manufacturer is not printed."""
    provenance = ChannelProvenance(
        base=_contrib(
            "aaaa", SourceKind.ORIGINAL, ("distance_m",), manufacturer="garmin"
        ),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.PHONE_COPY,
                ("heart_rate_bpm",),
                manufacturer="development",
                alignment=ExtraAlignment(3600, _stretches("power_w")),
            ),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | original (garmin) | Distance | – |",
        "| `fit-archive/bbbb.fit` | extra | phone copy | Heart rate "
        "| moved -1 h to the base's clock; 1 stretch: 1 by power |",
    )


def test_a_negative_shift_reads_as_a_positive_move(run_fit_bytes: bytes) -> None:
    """-7200 s subtracted means the extra moved forward two hours: "+2"."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, ("distance_m",)),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("power_w",),
                alignment=ExtraAlignment(-7200, _stretches("distance_m")),
            ),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | original | Distance | – |",
        "| `fit-archive/bbbb.fit` | extra | original | Power "
        "| moved +2 h to the base's clock; 1 stretch: 1 by distance |",
    )


def test_mixed_stretches_count_each_kind_in_the_fixed_order(
    run_fit_bytes: bytes,
) -> None:
    """Two by distance, three by power and one fallback, given in a file order
    that is neither the print order nor grouped; a second, non-donating extra
    ranks after it and shows the absence marker twice."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, ("heart_rate_bpm",)),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("power_w",),
                manufacturer="stryd",
                alignment=ExtraAlignment(
                    0,
                    _stretches(None, "power_w", "distance_m", "power_w", "power_w")
                    + _stretches("distance_m"),
                ),
            ),
            _contrib("cccc", SourceKind.UNKNOWN, ()),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | original | Heart rate | – |",
        "| `fit-archive/bbbb.fit` | extra | original (stryd) | Power "
        f"| 6 stretches: 2 by distance, 3 by power, 1 {_FALLBACK} |",
        "| `fit-archive/cccc.fit` | extra | unknown | – | – |",
    )


def test_zero_counts_are_omitted(run_fit_bytes: bytes) -> None:
    """Only the fallback is non-zero: no "0 by distance" or "0 by power"."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, ("distance_m",)),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("power_w",),
                alignment=ExtraAlignment(0, _stretches(None, None)),
            ),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | original | Distance | – |",
        "| `fit-archive/bbbb.fit` | extra | original | Power "
        f"| 2 stretches: 2 {_FALLBACK} |",
    )


def test_non_donating_extra_shows_the_absence_marker(run_fit_bytes: bytes) -> None:
    """An extra supplying nothing: the marker in both Channels and Alignment."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.PHONE_COPY, ("heart_rate_bpm",)),
        extras=(_contrib("bbbb", SourceKind.ORIGINAL, (), manufacturer="stryd"),),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | phone copy | Heart rate | – |",
        "| `fit-archive/bbbb.fit` | extra | original (stryd) | – | – |",
    )


def test_longitude_alone_reads_as_gps_once(run_fit_bytes: bytes) -> None:
    """Latitude and longitude share the label; either one, or both, is one
    mention."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, ("longitude_deg",)),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("latitude_deg", "temperature_c", "longitude_deg"),
                alignment=ExtraAlignment(0, _stretches("distance_m")),
            ),
        ),
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) == _body(
        "| `fit-archive/aaaa.fit` | base | original | GPS | – |",
        "| `fit-archive/bbbb.fit` | extra | original | GPS, Temperature "
        "| 1 stretch: 1 by distance |",
    )


# --- no section (Req 4.6) ----------------------------------------------------


def test_a_context_built_without_provenance_carries_none(
    run_fit_bytes: bytes,
) -> None:
    """Every existing constructor call omits the field."""
    activity = parse_fit(run_fit_bytes)
    ctx = DocContext(
        activity=activity,
        metrics=compute_metrics(activity),
        athlete=None,
        doc_stem="2021-09-07-run-1946",
        source_refs=("fit-archive/aaaa.fit",),
        tz=timezone(timedelta(hours=-6)),
    )
    assert ctx.channel_provenance is None
    assert channel_sources_section(ctx) is None


def test_no_provenance_is_no_section(run_fit_bytes: bytes) -> None:
    assert channel_sources_section(_ctx(run_fit_bytes, None)) is None


def test_provenance_without_extras_is_no_section(run_fit_bytes: bytes) -> None:
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, _BASE_RUN_CHANNELS), extras=()
    )
    assert channel_sources_section(_ctx(run_fit_bytes, provenance)) is None


def test_the_section_writes_no_frontmatter_key(run_fit_bytes: bytes) -> None:
    """Req 4.8: the body carries no frontmatter fence."""
    provenance = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.ORIGINAL, ("distance_m",)),
        extras=(_contrib("bbbb", SourceKind.UNKNOWN, ()),),
    )
    body = channel_sources_section(_ctx(run_fit_bytes, provenance))
    assert body is not None
    assert "---\n" not in body.replace("| --- | --- | --- | --- | --- |", "")


# --- the label table (Req 4.3) -----------------------------------------------


def test_labels_cover_every_samples_channel_but_time() -> None:
    expected = {f.name for f in dataclasses.fields(Samples)} - {"time_s"}
    assert len(expected) == 21
    assert set(CHANNEL_LABELS) == expected


def test_labels_equal_the_coverage_table_for_every_channel_it_names() -> None:
    assert len(_COVERAGE_CHANNELS) == 8
    for channel, label in _COVERAGE_CHANNELS:
        assert CHANNEL_LABELS[channel] == label, channel


def test_labels_equal_the_dynamics_display_for_every_channel_it_names() -> None:
    assert len(DYNAMICS_DISPLAY) == 12
    for display in DYNAMICS_DISPLAY:
        assert CHANNEL_LABELS[display.channel] == display.label, display.channel


def test_longitude_shares_the_gps_label() -> None:
    assert CHANNEL_LABELS["longitude_deg"] == CHANNEL_LABELS["latitude_deg"] == "GPS"


# --- the reverse-direction guard (design.md § Guards) ------------------------

_RENDER_DIR: Final[Path] = Path(fitdocs.render.__file__).parent
_ARCHIVE: Final[str] = "fitdocs.compose.archive"
_PROVENANCE_ALLOWED: Final[frozenset[str]] = frozenset(
    {
        "fitdocs.render",
        "fitdocs.render.format",
        "fitdocs.layout",
        "fitdocs.compose.types",
        "fitdocs.compose.alignment",
        "fitdocs.identity.kinds",
    }
)


def _package_of(rel_path: str) -> str:
    """The package a render file's relative imports resolve against."""
    return ".".join(("fitdocs", "render", *Path(rel_path).parts[:-1]))


def _targets(
    source: str, *, package: str = "fitdocs.render", every_name: bool = False
) -> frozenset[str]:
    """Every absolute dotted target the source imports; relative imports are
    resolved against ``package``. A name imported from a package counts as the
    submodule beside the package: with ``every_name`` for any name, else only
    for one that is a module on this tree."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module
            else:
                try:
                    base = importlib.util.resolve_name(
                        "." * node.level + (node.module or ""), package
                    )
                except ImportError:
                    continue
            if base is None:
                continue
            found.add(base)
            for alias in node.names:
                dotted = f"{base}.{alias.name}"
                if every_name or _is_module(dotted):
                    found.add(dotted)
    return frozenset(found)


def _is_module(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError):
        return False


def _render_sources() -> dict[str, str]:
    return {
        p.relative_to(_RENDER_DIR).as_posix(): p.read_text(encoding="utf-8")
        for p in sorted(_RENDER_DIR.rglob("*.py"))
    }


def _imports_archive(source: str, package: str = "fitdocs.render") -> bool:
    return any(
        t == _ARCHIVE or t.startswith(_ARCHIVE + ".")
        for t in _targets(source, package=package, every_name=True)
    )


def test_the_target_scan_sees_each_spelling_of_an_archive_import() -> None:
    """Synthetic sources: absolute and relative spellings are found, a sibling
    is not; relative names resolve from the file's own package."""
    assert _imports_archive("import fitdocs.compose.archive")
    assert _imports_archive("from fitdocs.compose.archive import compose_listed")
    assert _imports_archive("from fitdocs.compose import archive")
    assert _imports_archive("from ..compose import archive")
    assert _imports_archive("from ..compose.archive import compose_listed")
    assert _imports_archive("from ...compose import archive", "fitdocs.render.charts")
    assert _imports_archive("import fitdocs.compose.archive.thing")
    assert not _imports_archive("import fitdocs.compose.archived")
    assert not _imports_archive("from ..compose import types")
    assert not _imports_archive("from fitdocs.compose import types")
    assert not _imports_archive("from fitdocs.compose.types import ChannelProvenance")
    sections = _targets("from . import sections", every_name=True)
    assert "fitdocs.render.sections" in sections
    assert "fitdocs.render.sections" in _targets("from .sections import X")
    assert "fitdocs.render.sections" in _targets(
        "from ..sections import X", package="fitdocs.render.charts"
    )


def _archive_offenders(sources: Mapping[str, str]) -> list[str]:
    """The files (relative paths, sorted) that import the archive adapter, each
    resolved against its own package."""
    return sorted(
        name
        for name, text in sources.items()
        if _imports_archive(text, _package_of(name))
    )


def _provenance_targets(
    source: str | None = None, *, every_name: bool = False
) -> frozenset[str]:
    """The targets of provenance.py (or of ``source`` standing in for it),
    resolved against the package provenance.py lives in."""
    return _targets(
        _render_sources()["provenance.py"] if source is None else source,
        package=_package_of("provenance.py"),
        every_name=every_name,
    )


def test_provenance_targets_resolve_against_the_render_package() -> None:
    targets = _provenance_targets(
        "from .. import contract\nfrom . import sections", every_name=True
    )
    assert "fitdocs.contract" in targets
    assert "fitdocs.render.sections" in targets


def test_package_of_names_each_files_own_package() -> None:
    assert _package_of("views.py") == "fitdocs.render"
    assert _package_of("__init__.py") == "fitdocs.render"
    assert _package_of("charts/map.py") == "fitdocs.render.charts"
    assert _package_of("charts/__init__.py") == "fitdocs.render.charts"


def test_the_offender_scan_resolves_each_file_against_its_own_package() -> None:
    # An offender is first and another last, so a scan that drops either end
    # of the mapping misses one.
    sources = {
        "charts/map.py": "from ...compose import archive",
        "format.py": "from ..compose import types",
        "charts/svg.py": "from ..format import ABSENT",
        "views.py": "from ..compose import archive",
    }
    assert _archive_offenders(sources) == ["charts/map.py", "views.py"]


def test_target_resolution_of_names_and_unresolvable_levels() -> None:
    """A name is a target only when it is a module (or with ``every_name``); a
    relative import that climbs past the top package yields nothing."""
    plain = _targets("from fitdocs.render import sections, DocContext")
    assert "fitdocs.render.sections" in plain
    assert "fitdocs.render.DocContext" not in plain
    every = _targets("from fitdocs.render import DocContext", every_name=True)
    assert "fitdocs.render.DocContext" in every
    assert _targets("from .... import x") == frozenset()
    assert _targets("import fitdocs.layout") == {"fitdocs.layout"}


def test_no_render_module_imports_the_archive_adapter() -> None:
    sources = _render_sources()
    for expected in (
        "provenance.py",
        "views.py",
        "__init__.py",
        "charts/map.py",
        "charts/__init__.py",
    ):
        assert expected in sources, f"the walk missed {expected}"
    assert _archive_offenders(sources) == []


def test_provenance_imports_only_its_allowed_dependencies() -> None:
    fitdocs_targets = {t for t in _provenance_targets() if t.split(".")[0] == "fitdocs"}
    # The positive control: the scan read this module's real imports.
    assert "fitdocs.compose.types" in fitdocs_targets
    assert "fitdocs.compose.alignment" in fitdocs_targets
    assert fitdocs_targets <= _PROVENANCE_ALLOWED, sorted(
        fitdocs_targets - _PROVENANCE_ALLOWED
    )


@pytest.mark.parametrize(
    "forbidden",
    ["fitdocs.contract", "fitdocs.render.sections", "fitdocs.render.dynamics"],
)
def test_provenance_never_imports_the_named_modules(forbidden: str) -> None:
    assert not any(
        t == forbidden or t.startswith(forbidden + ".")
        for t in _provenance_targets(every_name=True)
    )


# --- the section in every view (task 3.3; Req 4.6, 4.7, 8.2) -----------------

_VIEW_FIXTURES: Final[dict[str, tuple[str, Modality]]] = {
    "run": ("run_fit_bytes", Modality.RUN),
    "ride": ("ride_fit_bytes", Modality.BIKE),
    "strength": ("strength_fit_bytes", Modality.STRENGTH),
    "generic": ("minimal_fit_bytes", Modality.OTHER),
}
_VIEW_HEADING: Final[str] = "## Channel Sources"
_DEVICES_HEADING: Final[str] = "## Device & Data Quality"


def _view_fit_bytes(view: str, request: pytest.FixtureRequest) -> bytes:
    name, _ = _VIEW_FIXTURES[view]
    if name == "minimal_fit_bytes":
        return builder.minimal_fit_bytes()
    value = request.getfixturevalue(name)
    assert isinstance(value, bytes)
    return value


def _composed_provenance() -> ChannelProvenance:
    return ChannelProvenance(
        base=_contrib("aaaa", SourceKind.PHONE_COPY, ("heart_rate_bpm",)),
        extras=(
            _contrib(
                "bbbb",
                SourceKind.ORIGINAL,
                ("power_w",),
                manufacturer="stryd",
                alignment=ExtraAlignment(0, _stretches("distance_m")),
            ),
        ),
    )


def _h2(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("## ")]


@pytest.mark.parametrize("view", list(_VIEW_FIXTURES))
def test_a_composed_context_ends_every_view_with_the_section(
    view: str, request: pytest.FixtureRequest
) -> None:
    """Last ``##`` section, directly after Device & Data Quality, in all views."""
    fit = _view_fit_bytes(view, request)
    ctx = _ctx(fit, _composed_provenance())
    assert ctx.activity.modality is _VIEW_FIXTURES[view][1]  # the view under test
    headings = _h2(render_document(ctx).markdown)
    assert headings.count(_VIEW_HEADING) == 1
    assert headings[-1] == _VIEW_HEADING
    assert headings[-2] == _DEVICES_HEADING


@pytest.mark.parametrize("view", list(_VIEW_FIXTURES))
def test_the_section_is_the_provenance_body_under_its_heading(
    view: str, request: pytest.FixtureRequest
) -> None:
    """The page equals the same page without provenance plus the heading and the
    body ``channel_sources_section`` returns, appended at the end."""
    fit = _view_fit_bytes(view, request)
    ctx = _ctx(fit, _composed_provenance())
    body = channel_sources_section(ctx)
    assert body is not None
    without = render_document(_ctx(fit, None)).markdown
    assert without.endswith("\n")
    # The donor is a non-Garmin contributor, so a Garmin-recorded fixture's
    # attribution line widens to name other devices (task 3.3's attribution
    # step); every other byte of the page is unchanged.
    # The generic fixture records no device, so its page has no such line.
    sole = _attribution_lines(without)
    assert len(sole) == (0 if view == "generic" else 1)
    expected = without
    for line in sole:
        widened = line.replace("Data source: ", "Data sources: ") + " and other devices"
        expected = expected.replace(line, widened, 1)
    assert render_document(ctx).markdown == (f"{expected}\n{_VIEW_HEADING}\n\n{body}\n")


@pytest.mark.parametrize("view", list(_VIEW_FIXTURES))
def test_without_provenance_or_extras_no_view_renders_the_section(
    view: str, request: pytest.FixtureRequest
) -> None:
    """A differential render: a context holding provenance with no extra is
    byte-identical to one holding none, in markdown and in assets."""
    fit = _view_fit_bytes(view, request)
    bare = render_document(_ctx(fit, None))
    composed = render_document(_ctx(fit, _composed_provenance()))
    # the differential is non-trivial: provenance with an extra does change the page
    assert composed.markdown != bare.markdown
    base_only = ChannelProvenance(
        base=_contrib("aaaa", SourceKind.PHONE_COPY, ("heart_rate_bpm",)), extras=()
    )
    no_extras = render_document(_ctx(fit, base_only))
    assert no_extras.markdown == bare.markdown
    assert no_extras.assets == bare.assets
    assert _VIEW_HEADING not in _h2(bare.markdown)
    assert "Channel Sources" not in bare.markdown


# --- the Garmin attribution over a composed page (intervals-connector Req 8.4) --


def _device(index: int, manufacturer: str, product_name: str) -> DeviceInfo:
    return DeviceInfo(
        device_index=index,
        manufacturer=manufacturer,
        product_name=product_name,
        serial_number=None,
        software_version=None,
        battery_status=None,
    )


def _attribution_lines(markdown: str) -> list[str]:
    return [line for line in markdown.splitlines() if line.startswith("Data source")]


def _contrib_with_devices(
    channels: tuple[str, ...], devices: tuple[DeviceInfo, ...]
) -> SourceContribution:
    return dataclasses.replace(
        _contrib("bbbb", SourceKind.ORIGINAL, channels), devices=devices
    )


def test_ride_pair_reads_garmin_and_other_devices() -> None:
    """The Garmin-original base plus the HealthFit copy donating heart rate."""
    garmin_bytes, copy_bytes = merge.ride_pair_fit_bytes()
    base = parse_fit(garmin_bytes)
    composition = compose_activity(base, [parse_fit(copy_bytes)])
    extra = composition.provenance.extras[0]
    # preconditions: the copy donates and its recording device is not a Garmin
    assert "heart_rate_bpm" in extra.channels
    assert "heart_rate_bpm" not in composition.provenance.base.channels
    donor_recorder = recording_device(extra.devices)
    assert donor_recorder is not None
    assert donor_recorder.manufacturer != "garmin"
    ctx = dataclasses.replace(
        _ctx(garmin_bytes, composition.provenance),
        activity=composition.activity,
    )
    # falsity in the starting state: the base alone is a sole Garmin source
    alone = render_document(_ctx(garmin_bytes, None)).markdown
    assert _attribution_lines(alone) == ["Data source: Garmin SyntheticGarminEdge"]
    composed = render_document(ctx).markdown
    assert _attribution_lines(composed) == [
        "Data sources: Garmin SyntheticGarminEdge and other devices"
    ]


def _garmin_base_ctx(
    run_fit_bytes: bytes, extras: tuple[SourceContribution, ...]
) -> DocContext:
    ctx = _ctx(
        run_fit_bytes,
        ChannelProvenance(
            base=_contrib("aaaa", SourceKind.ORIGINAL, ("heart_rate_bpm",)),
            extras=extras,
        ),
    )
    activity = dataclasses.replace(
        ctx.activity, devices=(_device(0, "garmin", "edge_1040"),)
    )
    return dataclasses.replace(ctx, activity=activity)


def test_a_non_donating_extra_adds_no_other_devices(run_fit_bytes: bytes) -> None:
    ctx = _garmin_base_ctx(
        run_fit_bytes, (_contrib_with_devices((), (_device(0, "stryd", "pod"),)),)
    )
    assert ctx.channel_provenance is not None
    assert ctx.channel_provenance.extras[0].channels == ()  # donates nothing
    assert _attribution_lines(render_document(ctx).markdown) == [
        "Data source: Garmin edge_1040"
    ]


def test_a_non_donating_garmin_extra_is_not_named(run_fit_bytes: bytes) -> None:
    ctx = _garmin_base_ctx(
        run_fit_bytes,
        (_contrib_with_devices((), (_device(0, "garmin", "fenix_7"),)),),
    )
    assert _attribution_lines(render_document(ctx).markdown) == [
        "Data source: Garmin edge_1040"
    ]


def test_a_donating_garmin_extra_is_named_after_the_base(
    run_fit_bytes: bytes,
) -> None:
    ctx = _garmin_base_ctx(
        run_fit_bytes,
        (
            _contrib_with_devices((), (_device(0, "stryd", "pod"),)),
            _contrib_with_devices(("power_w",), (_device(0, "garmin", "fenix_7"),)),
        ),
    )
    assert _attribution_lines(render_document(ctx).markdown) == [
        "Data sources: Garmin edge_1040 and Garmin fenix_7"
    ]


def test_every_donating_extra_is_read_in_rank_order_by_its_recording_device(
    run_fit_bytes: bytes,
) -> None:
    ctx = _garmin_base_ctx(
        run_fit_bytes,
        (
            _contrib_with_devices(
                ("power_w",),
                (_device(1, "stryd", "pod"), _device(0, "garmin", "fenix_7")),
            ),
            _contrib_with_devices(("cadence_rpm",), (_device(0, "garmin", "fr965"),)),
            _contrib_with_devices((), (_device(0, "stryd", "pod"),)),
        ),
    )
    assert _attribution_lines(render_document(ctx).markdown) == [
        "Data sources: Garmin edge_1040, Garmin fenix_7 and Garmin fr965"
    ]

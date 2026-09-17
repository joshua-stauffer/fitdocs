"""The public package surface: ``fitdocs``'s top-level re-exports.

The package root re-exports exactly one stable public API: the two entry-point
functions (:func:`~fitdocs.ingest.parse_fit`,
:func:`~fitdocs.metrics.compute_metrics`), the model types, the metric-input and
result types, and the decode error taxonomy. These tests verify every name
imports, is the *same object* as its defining module exposes, is listed in
``fitdocs.__all__``, and that the two entry points compose end to end -- all
without triggering a circular import.

:mod:`fitdocs.contract` is pinned here too. It is not re-exported from the
package root -- consumers import the module -- but it *is* a published surface:
the ownership contract, the in-tree declarations, and every command that reads a
document all name its constants, so a rename is a user-visible change. Pinning
``contract.__all__`` makes an accidental addition or removal fail loudly rather
than drift into the documentation.

:mod:`fitdocs.declaration` is pinned the same way and for the same reason: the
in-tree ``AGENTS.md`` ownership declaration is a published surface an LLM wiki
agent reads, so its exported names -- the filename, the documentation URL, the
state enum, the outcome type, and the four functions -- are user-visible too.

:mod:`fitdocs.audit` is pinned the same way: the read-only contract inspection
is a published surface a maintainer or an automation calls directly, so its
finding-kind enum, its two dataclasses, and its one entry point are
user-visible too.

:mod:`fitdocs.docio` is pinned the same way (2026-07-22 amendment, task 7.2,
see `spec.json`'s amendments): it is the shared filesystem read behind the
*writing* paths -- `sync` and the load engine resolve a document's frontmatter
through it, while `audit` keeps its own `_read_document` because a finding has
to name the unreadable *cause* and reuses only docio's symlink strings. Those
strings are what every caller's finding or warning names, so its exported
surface is as user-visible as the other three leaves pinned here.

:mod:`fitdocs.load.channels` is pinned the same way (load-channels task 4.1,
design: ChannelSurface / PublicSurfacePin, Req 9.1-9.7): the result
vocabulary, the three ``compute`` entry points under channel-qualified
names, the heart-rate weighting seam with its shipped instance, and the
provenance records are what ``threshold-load`` and ``activity-qa-flags``
consume, so a rename or removal there is user-visible too. The three
``*_compute`` identities are pinned in a **fresh interpreter**
(``test_channels_compute_identities_in_a_fresh_interpreter`` below), not
in-process: ``tests/load/channels/test_pace.py`` calls
``importlib.reload(pace)`` mid-suite, which replaces ``pace.compute`` with a
new function object for the rest of the process -- an in-process ``is``
check against a package-level binding captured at import time would then
pass or fail depending on whether this module happens to collect before or
after that reload, which is exactly what a fresh subprocess avoids.
"""

from __future__ import annotations

import ast
import dataclasses
import importlib.util
import subprocess
import sys
from pathlib import Path

import fitdocs
import fitdocs.audit
import fitdocs.benchmarks
import fitdocs.contract
import fitdocs.declaration
import fitdocs.docio
import fitdocs.history
import fitdocs.history.engine
import fitdocs.history.model
import fitdocs.history.page
import fitdocs.history.series
import fitdocs.history.settings
import fitdocs.ingest
import fitdocs.ingest.errors
import fitdocs.load
import fitdocs.load.channels
import fitdocs.load.registry
import fitdocs.load.settings
import fitdocs.load.threshold.calculator
import fitdocs.load.types
import fitdocs.metrics
import fitdocs.metrics.types
import fitdocs.model
import fitdocs.performance
import fitdocs.performance.engine
import fitdocs.performance.types
import fitdocs.plans
import fitdocs.plans.block_page
import fitdocs.plans.corpus
import fitdocs.plans.engine
import fitdocs.plans.model
import fitdocs.plans.page
import fitdocs.plans.planned_page
import fitdocs.plans.resolution
import fitdocs.plans.settings
import fitdocs.plans.source

# Every name the package root must re-export, paired with its defining object.
_EXPECTED = {
    "parse_fit": fitdocs.ingest.parse_fit,
    "compute_metrics": fitdocs.metrics.compute_metrics,
    "Activity": fitdocs.model.Activity,
    "Samples": fitdocs.model.Samples,
    "SessionSummary": fitdocs.model.SessionSummary,
    "Lap": fitdocs.model.Lap,
    "StrengthSet": fitdocs.model.StrengthSet,
    "DeviceInfo": fitdocs.model.DeviceInfo,
    "Provenance": fitdocs.model.Provenance,
    "Sport": fitdocs.model.Sport,
    "Modality": fitdocs.model.Modality,
    "SCHEMA_VERSION": fitdocs.model.SCHEMA_VERSION,
    "fit_datetime": fitdocs.model.fit_datetime,
    "AthleteInputs": fitdocs.metrics.types.AthleteInputs,
    "ZoneSpec": fitdocs.metrics.types.ZoneSpec,
    "DerivedMetrics": fitdocs.metrics.types.DerivedMetrics,
    "TrimpWeighting": fitdocs.metrics.types.TrimpWeighting,
    "FitDecodeError": fitdocs.ingest.errors.FitDecodeError,
    "NotFitFileError": fitdocs.ingest.errors.NotFitFileError,
    "FitIntegrityError": fitdocs.ingest.errors.FitIntegrityError,
}


def test_every_public_name_is_importable_and_correct() -> None:
    for name, expected in _EXPECTED.items():
        assert hasattr(fitdocs, name), f"fitdocs is missing {name}"
        assert getattr(fitdocs, name) is expected, f"{name} is the wrong object"


def test_direct_from_import_binds_the_public_names() -> None:
    from fitdocs import (  # noqa: F401
        SCHEMA_VERSION,
        Activity,
        AthleteInputs,
        DerivedMetrics,
        DeviceInfo,
        FitDecodeError,
        FitIntegrityError,
        Lap,
        Modality,
        NotFitFileError,
        Provenance,
        Samples,
        SessionSummary,
        Sport,
        StrengthSet,
        TrimpWeighting,
        ZoneSpec,
        compute_metrics,
        fit_datetime,
        parse_fit,
    )

    assert parse_fit is fitdocs.ingest.parse_fit
    assert compute_metrics is fitdocs.metrics.compute_metrics
    assert Activity is fitdocs.model.Activity
    assert NotFitFileError is fitdocs.ingest.errors.NotFitFileError


def test_all_lists_exactly_the_public_names() -> None:
    assert set(fitdocs.__all__) == set(_EXPECTED)
    # __all__ has no duplicates.
    assert len(fitdocs.__all__) == len(set(fitdocs.__all__))


def test_end_to_end_parse_then_compute_via_public_names(ride_fit_bytes: bytes) -> None:
    activity = fitdocs.parse_fit(ride_fit_bytes)
    assert isinstance(activity, fitdocs.Activity)
    assert activity.schema_version == fitdocs.SCHEMA_VERSION

    metrics = fitdocs.compute_metrics(activity, fitdocs.AthleteInputs(ftp_watts=250))
    assert isinstance(metrics, fitdocs.DerivedMetrics)
    # avg power comes straight from the ride session summary.
    assert metrics.avg_power_w == 200


# --- fitdocs.load: the plugin-author public surface (plugin-api, Req 5.2, 5.5)
#
# This is deliberately an INCLUSION check, not an ``__all__``-equality pin like
# the ones below it: ``fitdocs.load.__all__`` also lists ``registry``, which
# the plugin-api design's "Public-surface ownership" section explicitly
# declares NOT part of the plugin-author surface (an implementation detail
# plugin authors never import directly). ``threshold-load`` supersedes
# ``training-load``'s Req 13.2 "this spec ships no calculator": fitdocs now
# ships exactly one, ``THRESHOLD_CALCULATOR`` (id ``"threshold"``), added to
# this surface by threshold-load task 4.1 (``BuiltInRegistration`` /
# ``PublicSurfacePin``) -- the calculator export only, no ``ProfileView``
# member. This test asserts every ENUMERATED name is importable and identical
# to its defining object, and never asserts or forbids names beyond that
# enumeration -- deleting any one of them fails the test below; adding
# ``registry`` to it would be a test bug, not a regression, so it is
# deliberately absent from ``_LOAD_EXPECTED``.
_LOAD_EXPECTED = {
    "LoadCalculator": fitdocs.load.types.LoadCalculator,
    "AthleteField": fitdocs.load.types.AthleteField,
    "LoadContext": fitdocs.load.types.LoadContext,
    "ProfileView": fitdocs.load.types.ProfileView,
    "InteractionSession": fitdocs.load.types.InteractionSession,
    "LoadOutcome": fitdocs.load.types.LoadOutcome,
    "LoadResult": fitdocs.load.types.LoadResult,
    "NonSelectedValue": fitdocs.load.types.NonSelectedValue,
    "QualityFlag": fitdocs.load.types.QualityFlag,
    "Computed": fitdocs.load.types.Computed,
    "Unsupported": fitdocs.load.types.Unsupported,
    "MissingInputs": fitdocs.load.types.MissingInputs,
    "NotComputed": fitdocs.load.types.NotComputed,
    "LoadSettings": fitdocs.load.settings.LoadSettings,
    "DEFAULT_LOAD_SETTINGS": fitdocs.load.settings.DEFAULT_LOAD_SETTINGS,
    "LoadSettingsError": fitdocs.load.settings.LoadSettingsError,
    "register": fitdocs.load.registry.register,
    "get": fitdocs.load.registry.get,
    "supports_activity": fitdocs.load.types.supports_activity,
    "available": fitdocs.load.registry.available,
    "for_modality": fitdocs.load.registry.for_modality,
    "UnknownCalculatorError": fitdocs.load.registry.UnknownCalculatorError,
    "InvalidCalculatorError": fitdocs.load.registry.InvalidCalculatorError,
    "DuplicateCalculatorIdError": fitdocs.load.registry.DuplicateCalculatorIdError,
    "Benchmark": fitdocs.benchmarks.Benchmark,
    "BenchmarkKind": fitdocs.benchmarks.BenchmarkKind,
    "BenchmarkAge": fitdocs.benchmarks.BenchmarkAge,
    "BenchmarkRef": fitdocs.load.types.BenchmarkRef,
    "benchmark_age": fitdocs.benchmarks.benchmark_age,
    "THRESHOLD_CALCULATOR": fitdocs.load.threshold.calculator.THRESHOLD_CALCULATOR,
}


def test_every_load_plugin_surface_name_is_importable_and_correct() -> None:
    for name, expected in _LOAD_EXPECTED.items():
        assert hasattr(fitdocs.load, name), f"fitdocs.load is missing {name}"
        assert getattr(fitdocs.load, name) is expected, f"{name} is the wrong object"


def test_every_load_plugin_surface_name_is_in_load_all() -> None:
    """Every ``_LOAD_EXPECTED`` name is also listed in ``fitdocs.load.__all__``.

    ``getattr``/``from ... import`` above succeed regardless of ``__all__``
    membership -- both bind through the module's own attributes, not through
    ``__all__``. ``tests/test_docs_guarantees.py``'s doc-sync check only
    catches an *extra*, undocumented name (``set(__all__) - documented``),
    the direction that shrinks on removal. So deleting a name from
    ``fitdocs.load.__all__`` (e.g. ``THRESHOLD_CALCULATOR``) left the suite
    fully green until this assertion existed (REMEDIATION ROUND 1 finding 4)
    -- this is what actually pins the published ``__all__`` surface in the
    removal direction.
    """
    missing = set(_LOAD_EXPECTED) - set(fitdocs.load.__all__)
    assert not missing, f"missing from fitdocs.load.__all__: {sorted(missing)}"


def test_load_plugin_surface_direct_from_import_binds_the_public_names() -> None:
    from fitdocs.load import (  # noqa: F401
        DEFAULT_LOAD_SETTINGS,
        THRESHOLD_CALCULATOR,
        AthleteField,
        Benchmark,
        BenchmarkAge,
        BenchmarkKind,
        BenchmarkRef,
        Computed,
        DuplicateCalculatorIdError,
        InteractionSession,
        InvalidCalculatorError,
        LoadCalculator,
        LoadContext,
        LoadOutcome,
        LoadResult,
        LoadSettings,
        LoadSettingsError,
        MissingInputs,
        NonSelectedValue,
        NotComputed,
        ProfileView,
        QualityFlag,
        UnknownCalculatorError,
        Unsupported,
        available,
        benchmark_age,
        for_modality,
        get,
        register,
        supports_activity,
    )

    assert LoadCalculator is fitdocs.load.types.LoadCalculator
    assert LoadOutcome is fitdocs.load.types.LoadOutcome
    assert register is fitdocs.load.registry.register
    assert get is fitdocs.load.registry.get
    assert available is fitdocs.load.registry.available
    assert for_modality is fitdocs.load.registry.for_modality
    assert supports_activity is fitdocs.load.types.supports_activity
    assert Benchmark is fitdocs.benchmarks.Benchmark
    assert BenchmarkKind is fitdocs.benchmarks.BenchmarkKind
    assert BenchmarkAge is fitdocs.benchmarks.BenchmarkAge
    assert BenchmarkRef is fitdocs.load.types.BenchmarkRef
    assert benchmark_age is fitdocs.benchmarks.benchmark_age
    assert (
        THRESHOLD_CALCULATOR is fitdocs.load.threshold.calculator.THRESHOLD_CALCULATOR
    )


# Every name the document contract publishes: the vocabulary, the versions, the
# region-ownership policy, the fresh-region texts, the pure readers, and the
# marker helpers it re-exports from ``docmerge`` so a consumer needs one import.
_CONTRACT_SURFACE = {
    # versions
    "CONTRACT_VERSION",
    "DOC_VERSION",
    # document vocabulary
    "DATE_KEY",
    "DOC_VERSION_KEY",
    "FRONTMATTER_FENCE",
    "GENERATOR",
    "GENERATOR_KEY",
    "INDOOR_KEY",
    "LOAD_KEYS",
    "LoadReading",
    "MANAGED_KEYS",
    "MODALITY_KEY",
    "SOURCES_KEY",
    "SPORT_KEY",
    "START_TIME_KEY",
    "TYPE_KEY",
    "UUID_KEY",
    "WORKOUT_TYPE",
    # the effort-tag vocabulary (task 1.1; the reader and the line carry are
    # published by tasks 1.2 and 1.3)
    "EFFORT_KEY",
    "EFFORT_DISTANCE_KEY",
    "EFFORT_TIME_KEY",
    "EFFORT_EVENT_KEY",
    "EFFORT_KEYS",
    "USER_KEYS",
    "EffortKind",
    "EffortTag",
    "EffortTagProblem",
    "InvalidEffortTag",
    # provenance
    "DOC_BANNER",
    "GENERATED_PREFIX",
    "is_generated",
    # region ownership policy
    "LOAD_NOT_COMPUTED",
    "LOAD_REGION",
    "NOTES_PLACEHOLDER",
    "NOTES_REGION",
    "PRESERVED_REGIONS",
    "TOOL_REGIONS",
    "USER_REGIONS",
    "WORKOUT_PLACEHOLDER",
    "WORKOUT_REGION",
    # pure readers
    "document_date",
    "document_indoor",
    "document_load",
    "document_modality",
    "document_sport",
    "document_start_time",
    "document_uuid",
    "document_version",
    "effort_tag",
    "format_session_uuid",
    "frontmatter_close_index",
    "is_workout_document",
    "parse_frontmatter",
    "sha_of_ref",
    "source_refs",
    "unmanaged_keys",
    "user_owned_lines",
    # re-exported marker grammar
    "begin_marker",
    "end_marker",
    "region_block",
}


def test_contract_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.contract.__all__) == _CONTRACT_SURFACE
    assert len(fitdocs.contract.__all__) == len(set(fitdocs.contract.__all__))


def test_every_contract_name_is_bound_on_the_module() -> None:
    for name in _CONTRACT_SURFACE:
        assert hasattr(fitdocs.contract, name), f"fitdocs.contract is missing {name}"


def test_contract_is_not_re_exported_from_the_package_root() -> None:
    """The contract is a module-level surface, not a package-root name.

    Keeping it out of ``fitdocs.__all__`` is what lets the root stay the narrow
    parse/compute API while the contract stays importable by every layer.
    """
    assert not set(fitdocs.__all__) & _CONTRACT_SURFACE


# Every name the in-tree ownership-declaration module publishes: the
# conventional filename, the published-contract documentation URL, the
# declaration-state enum, the outcome type, and the text-composition and
# placement functions.
_DECLARATION_SURFACE = {
    "CONTRACT_DOCUMENTATION_URL",
    "DECLARATION_FILENAME",
    "DeclarationOutcome",
    "DeclarationState",
    "declaration_path",
    "declaration_text",
    "ensure_declarations",
    "inspect_declarations",
}


def test_declaration_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.declaration.__all__) == _DECLARATION_SURFACE
    assert len(fitdocs.declaration.__all__) == len(set(fitdocs.declaration.__all__))


def test_every_declaration_name_is_bound_on_the_module() -> None:
    for name in _DECLARATION_SURFACE:
        assert hasattr(fitdocs.declaration, name), (
            f"fitdocs.declaration is missing {name}"
        )


def test_declaration_is_not_re_exported_from_the_package_root() -> None:
    """The declaration module is a module-level surface, not a package-root name."""
    assert not set(fitdocs.__all__) & _DECLARATION_SURFACE


# Every name the read-only contract audit publishes: the finding-kind enum,
# the two dataclasses, and the single entry point.
_AUDIT_SURFACE = {
    "AuditReport",
    "Finding",
    "FindingKind",
    "audit",
}


def test_audit_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.audit.__all__) == _AUDIT_SURFACE
    assert len(fitdocs.audit.__all__) == len(set(fitdocs.audit.__all__))


def test_every_audit_name_is_bound_on_the_module() -> None:
    for name in _AUDIT_SURFACE:
        assert hasattr(fitdocs.audit, name), f"fitdocs.audit is missing {name}"


def test_audit_is_not_re_exported_from_the_package_root() -> None:
    """The audit module is a module-level surface, not a package-root name."""
    assert not set(fitdocs.__all__) & _AUDIT_SURFACE


# Every name the shared document-read leaf publishes: the one reader function
# plus the symlink-refusal detail/remedy strings every caller reuses.
_DOCIO_SURFACE = {
    "REMEDY_REPLACE_SYMLINK",
    "SYMLINK_DETAIL",
    "read_frontmatter",
}


def test_docio_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.docio.__all__) == _DOCIO_SURFACE
    assert len(fitdocs.docio.__all__) == len(set(fitdocs.docio.__all__))


def test_every_docio_name_is_bound_on_the_module() -> None:
    for name in _DOCIO_SURFACE:
        assert hasattr(fitdocs.docio, name), f"fitdocs.docio is missing {name}"


def test_docio_is_not_re_exported_from_the_package_root() -> None:
    """The docio module is a module-level surface, not a package-root name."""
    assert not set(fitdocs.__all__) & _DOCIO_SURFACE


# Every name ``fitdocs.load.channels`` publishes (load-channels task 4.1,
# design: ChannelSurface, Req 9.1-9.7): the channel-result vocabulary and the
# sufficiency value it is scored against, the three computation entry points
# under channel-qualified names, the heart-rate weighting seam with its one
# shipped instance, and the provenance records. ``load/settings.py``'s
# ``[load.sufficiency]`` projection (``load_load_settings``, owned by
# ``training-load``) is deliberately absent -- this package hands out the
# *type* the projection produces (``SufficiencySettings``), never a reader.
_CHANNELS_SURFACE = {
    # result vocabulary and sufficiency value (types.py)
    "ChannelId",
    "InsufficiencyReason",
    "StreamCoverage",
    "ChannelLoad",
    "ChannelInsufficient",
    "ChannelOutcome",
    "SufficiencySettings",
    "require_kind",
    "DEFAULT_MIN_STREAM_COVERAGE",
    "DEFAULT_MIN_DURATION_S",
    # three computation entry points, channel-qualified
    "power_compute",
    "heart_rate_compute",
    "pace_compute",
    # heart-rate weighting seam and its one shipped instance (weighting.py)
    "HeartRateIntensityModel",
    "BANISTER_TRIMP_MODEL",
    # provenance records (sources.py)
    "Citation",
    "VerificationStatus",
    "Divergence",
    "CITATIONS",
    "DIVERGENCES",
    "BLOCKED_CITATIONS",
}


def test_channels_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.load.channels.__all__) == _CHANNELS_SURFACE
    # __all__ has no duplicates.
    assert len(fitdocs.load.channels.__all__) == len(set(fitdocs.load.channels.__all__))


def test_channels_init_binds_exactly_its_published_surface() -> None:
    """Task 4.1 remediation round 2: pin the names ``__init__.py`` actually
    *binds* via re-export, not only ``__all__``. ``__all__`` and the module's
    bound names are two independent facts about the file -- nothing forces
    them to agree -- and ``test_channels_all_lists_exactly_its_published_
    surface`` above checks only ``__all__``. Task 1.1's AST guard
    (``test_package_imports_cleanly`` in ``tests/load/channels/
    test_sources.py``) permits any number of ``X as X`` re-exports from this
    package's own leaves, so a name added there without a matching ``__all__``
    entry -- e.g. ``from fitdocs.load.channels.sufficiency import evaluate as
    evaluate`` -- passes that guard, passes every canonical validation
    command, and is invisible to every other assertion in this file, yet
    ``fitdocs.load.channels.evaluate`` resolves and is a genuine, undeclared
    public name. This test walks the same AST and asserts the set of bound
    names equals the published surface directly, so an added, renamed or
    removed re-export reds here regardless of ``__all__``'s state.

    Mutation caught (verified, not inferred): adding exactly
    ``from fitdocs.load.channels.sufficiency import evaluate as evaluate`` in
    isort position reds this test as a sole failure (measured: ``1 failed,
    2674 passed, 5 skipped``, failing at this test's ``bound_names ==
    _CHANNELS_SURFACE`` assertion). Before this test existed, that same
    mutation left ``pytest``, ``ruff check``, ``ruff format --check`` and
    ``mypy`` all green -- that is exactly what made it invisible to the
    round-1 surface pin.
    """
    spec = importlib.util.find_spec("fitdocs.load.channels")
    assert spec is not None and spec.origin is not None
    tree = ast.parse(Path(spec.origin).read_text(), filename=spec.origin)
    bound_names: set[str] = set()
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ImportFrom) and node.module != "__future__":
            for alias in node.names:
                bound_names.add(alias.asname or alias.name)
    assert bound_names, (
        "the walk found no re-exported names -- wrong file or guard broken"
    )
    assert bound_names == _CHANNELS_SURFACE


def test_every_channels_name_is_bound_on_the_module() -> None:
    for name in _CHANNELS_SURFACE:
        assert hasattr(fitdocs.load.channels, name), (
            f"fitdocs.load.channels is missing {name}"
        )


def test_channels_surface_is_not_flattened_into_the_load_package_root() -> None:
    """``fitdocs.load.__all__`` must not re-export any channel-surface name
    directly -- a consumer reaches the channel layer through
    ``fitdocs.load.channels``, never through a name flattened onto
    ``fitdocs.load`` itself, the same layering ``_CONTRACT_SURFACE`` and its
    siblings already pin one level up."""
    assert not set(fitdocs.load.__all__) & _CHANNELS_SURFACE


def test_channel_load_field_names_match_the_spec_through_the_package_surface() -> None:
    """Task 4.1: extend the surface pin so the members of the computed-load
    value cannot drift accidentally, checked through the *published* name
    (``fitdocs.load.channels.ChannelLoad``), not only through
    ``types.py`` directly (already pinned in
    ``tests/load/channels/test_types.py``). ``dataclasses.fields`` is used
    rather than ``hasattr``: a field declared *without* a default is a class
    annotation only, and ``hasattr`` reports ``False`` for it regardless of
    whether the field exists (measured: ``hasattr(ChannelLoad, "channel")``
    is ``False`` even though ``channel`` is a real, required field). A field
    declared *with* a default -- ``ChannelLoad.notes``,
    ``ChannelInsufficient.observed`` and ``ChannelInsufficient.required``
    below all have one -- *is* a class attribute and ``hasattr`` reports
    ``True`` for it (also measured), so ``hasattr`` alone cannot be trusted
    to enumerate a dataclass's fields either way; ``dataclasses.fields``
    is the only introspection that is accurate for all of them."""
    field_names = {
        f.name for f in dataclasses.fields(fitdocs.load.channels.ChannelLoad)
    }
    assert field_names == {
        "channel",
        "load",
        "intensity",
        "anchor",
        "scored_duration_s",
        "coverage",
        "inputs_used",
        "notes",
    }


def test_channel_insufficient_fields_match_the_spec_through_the_package_surface() -> (
    None
):
    field_names = {
        f.name for f in dataclasses.fields(fitdocs.load.channels.ChannelInsufficient)
    }
    assert field_names == {"channel", "reason", "detail", "observed", "required"}


def test_insufficiency_reason_members_match_the_spec_through_the_package_surface() -> (
    None
):
    """Two assertions pin two different things: the *value set* (below) is
    blind to an aliased member -- ``Enum.__iter__`` and set/dict comprehension
    over the enum both skip aliases entirely, and an alias adds nothing to
    ``len(...)`` either, so a member added as an alias of an existing value
    (e.g. ``PROBE_ALIAS = "no_benchmark"``) would pass both the value-set
    check and the count check silently (measured: it reds only at the
    ``__members__`` assertion below). ``__members__`` (a ``mappingproxy``) is
    the one view that lists every name bound on the enum, canonical or
    aliased, so an aliased member is caught only there."""
    assert {member.value for member in fitdocs.load.channels.InsufficiencyReason} == {
        "no_benchmark",
        "benchmarks_inconsistent",
        "stream_absent",
        "stream_coverage",
        "too_short",
        "model_not_defined",
        "not_computable",
    }
    assert len(fitdocs.load.channels.InsufficiencyReason) == 7
    assert set(fitdocs.load.channels.InsufficiencyReason.__members__) == {
        "NO_BENCHMARK",
        "BENCHMARKS_INCONSISTENT",
        "STREAM_ABSENT",
        "STREAM_COVERAGE",
        "TOO_SHORT",
        "MODEL_NOT_DEFINED",
        "NOT_COMPUTABLE",
    }


def test_channels_compute_identities_in_a_fresh_interpreter() -> None:
    """Every re-exported name in ``fitdocs.load.channels`` must be the exact
    same object its defining leaf module exposes -- run in a fresh
    interpreter (not in-process) so the result is independent of whether
    ``tests/load/channels/test_pace.py``'s ``importlib.reload(pace)`` has
    already run in this pytest session (see the module docstring above)."""
    script = (
        "import fitdocs.load.channels as channels\n"
        "import fitdocs.load.channels.heart_rate as heart_rate\n"
        "import fitdocs.load.channels.pace as pace\n"
        "import fitdocs.load.channels.power as power\n"
        "import fitdocs.load.channels.sources as sources\n"
        "import fitdocs.load.channels.types as types\n"
        "import fitdocs.load.channels.weighting as weighting\n"
        "assert channels.power_compute is power.compute, 'power_compute'\n"
        "assert channels.heart_rate_compute is heart_rate.compute, "
        "'heart_rate_compute'\n"
        "assert channels.pace_compute is pace.compute, 'pace_compute'\n"
        "assert channels.HeartRateIntensityModel is "
        "weighting.HeartRateIntensityModel, 'HeartRateIntensityModel'\n"
        "assert channels.BANISTER_TRIMP_MODEL is "
        "weighting.BANISTER_TRIMP_MODEL, 'BANISTER_TRIMP_MODEL'\n"
        "assert channels.ChannelId is types.ChannelId, 'ChannelId'\n"
        "assert channels.InsufficiencyReason is types.InsufficiencyReason, "
        "'InsufficiencyReason'\n"
        "assert channels.StreamCoverage is types.StreamCoverage, "
        "'StreamCoverage'\n"
        "assert channels.ChannelLoad is types.ChannelLoad, 'ChannelLoad'\n"
        "assert channels.ChannelInsufficient is types.ChannelInsufficient, "
        "'ChannelInsufficient'\n"
        "assert channels.ChannelOutcome is types.ChannelOutcome, "
        "'ChannelOutcome'\n"
        "assert channels.SufficiencySettings is types.SufficiencySettings, "
        "'SufficiencySettings'\n"
        "assert channels.require_kind is types.require_kind, 'require_kind'\n"
        "assert channels.DEFAULT_MIN_STREAM_COVERAGE is "
        "types.DEFAULT_MIN_STREAM_COVERAGE, 'DEFAULT_MIN_STREAM_COVERAGE'\n"
        "assert channels.DEFAULT_MIN_DURATION_S is "
        "types.DEFAULT_MIN_DURATION_S, 'DEFAULT_MIN_DURATION_S'\n"
        "assert channels.Citation is sources.Citation, 'Citation'\n"
        "assert channels.VerificationStatus is sources.VerificationStatus, "
        "'VerificationStatus'\n"
        "assert channels.Divergence is sources.Divergence, 'Divergence'\n"
        "assert channels.CITATIONS is sources.CITATIONS, 'CITATIONS'\n"
        "assert channels.DIVERGENCES is sources.DIVERGENCES, 'DIVERGENCES'\n"
        "assert channels.BLOCKED_CITATIONS is sources.BLOCKED_CITATIONS, "
        "'BLOCKED_CITATIONS'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


def _discovered_load_subpackages() -> list[str]:
    """The immediate sub-packages of ``fitdocs.load`` on disk (task 6.4, Req
    14.7's fresh-interpreter import-direction guard, corrected 2026-07-25).

    Discovered rather than named: the ruling that introduced this guard first
    wrote it as "at minimum ``import fitdocs.load.qa`` and ``import
    fitdocs.load.types``" -- but the quality-assurance sub-package belongs to
    ``activity-qa-flags`` and does not exist in this checkout, so a literal
    name reddens the gate the day it is written. Enumerating what is actually
    on disk means today's assertion covers exactly the sub-packages that
    exist (``channels``), and each of ``load-channels``, ``threshold-load``
    and ``activity-qa-flags``' sub-packages is covered the moment it lands --
    with no edit to this test required.
    """
    load_dir = Path(fitdocs.__file__).resolve().parent / "load"
    return sorted(
        child.name
        for child in load_dir.iterdir()
        if child.is_dir()
        and not child.name.startswith("_")
        and (child / "__init__.py").is_file()
    )


def test_no_circular_import_in_a_fresh_interpreter() -> None:
    """A cold ``import fitdocs`` must not deadlock or raise on the re-export
    chain, and (Req 14.7, task 6.4) neither must a cold import of the load
    package, its contract module, its settings module, or any of its
    discovered sub-packages -- each proven in its own **separate, fresh**
    interpreter, one ``subprocess.run`` per entry point rather than one
    process importing all of them, because an in-process re-import after a
    prior entry point already populated ``sys.modules`` is a cache hit and
    would not catch the cycle this guard exists for (the reason task 3.3's
    ``LoadSettings`` reference in ``load/types.py`` is ``TYPE_CHECKING``-only
    rather than a runtime import -- pinned directly, not just via this
    fresh-interpreter proof, by
    ``test_load_types_never_imports_load_settings_at_runtime`` below).

    Extended in place (task 6.4) rather than left beside a parallel test, per
    the task's own "extend the existing test rather than adding a parallel
    one" instruction. Each entry point below runs in its *own* subprocess:
    stringing them together with ``;`` into a single process (the shape this
    test previously used for the load-package entries) makes every import
    after the first a ``sys.modules`` cache hit, which is exactly the failure
    mode this guard exists to catch.
    """
    subpackages = _discovered_load_subpackages()
    assert subpackages, (
        "expected at least one discovered fitdocs.load sub-package "
        "(load/channels exists on this branch) -- if this is empty the "
        "discovery logic itself is broken, not the property under test"
    )

    entry_points = [
        (
            "import fitdocs; "
            "from fitdocs import parse_fit, compute_metrics, Activity, "
            "AthleteInputs, ZoneSpec, NotFitFileError; "
            "print('import ok')"
        ),
        "import fitdocs.load; print('import ok')",
        "import fitdocs.load.types; print('import ok')",
        "import fitdocs.load.settings; print('import ok')",
        *(f"import fitdocs.load.{name}; print('import ok')" for name in subpackages),
    ]
    for code in entry_points:
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, f"{code!r} failed:\n{result.stderr}"
        assert "import ok" in result.stdout, (
            f"{code!r} produced no marker; stdout={result.stdout!r}"
        )


def test_load_types_never_imports_load_settings_at_runtime() -> None:
    """Req 14.7's named clause, pinned directly rather than only inferred
    from a fresh-interpreter import succeeding: "the contract module's
    reference to the resolved settings type shall exist for type checking
    only and shall never be a runtime import."

    A fresh-interpreter import of ``fitdocs.load.types`` (proven above)
    cannot discriminate this on its own: ``fitdocs.load.__init__`` already
    eagerly imports ``registry`` -> ``types`` -> (were the guard removed)
    ``settings``, but a *separate* interpreter that imports ``fitdocs.load``
    first already has ``fitdocs.load.settings`` in ``sys.modules`` via
    ``fitdocs.load.settings``'s own sibling import path before ``types.py``'s
    top level ever runs -- so an unconditional runtime import there is a
    ``sys.modules`` cache hit, not an ``ImportError``, and stays completely
    silent. This instead loads ``load/types.py`` directly off disk via
    ``importlib`` under a synthetic module name -- the same off-disk-exec
    technique
    ``tests/load/test_settings.py::test_settings_module_leaks_no_dynamic_import_of_load_types``
    uses for the settings module's own runtime-import guard (the sibling
    ``test_settings_module_does_not_import_load_types_at_runtime`` no longer
    shares this technique as of load-channels task 2.3 remediation round 1:
    it moved to a static, resolution-based AST walk, because ``settings.py``
    now has a legitimate runtime import of a different ``fitdocs.load.*``
    submodule and the old subprocess/``sys.modules`` isolation trick could no
    longer tell that import apart from the forbidden one) -- bypassing
    ``fitdocs.load``'s package ``__init__`` entirely, and asserts
    ``fitdocs.load.settings`` never lands in ``sys.modules`` as a side effect
    of executing ``types.py``'s own top-level statements.

    Mutation caught: making ``types.py``'s ``TYPE_CHECKING`` guard around
    ``from fitdocs.load.settings import LoadSettings`` unconditional puts
    ``fitdocs.load.settings`` in ``sys.modules`` the moment ``types.py``'s
    top level runs and reddens this test as a **sole** failure -- confirmed
    by running exactly that mutation (all 1849 other tests stayed green),
    not inferred from reading the source.
    """
    types_path = (
        Path(__file__).resolve().parent.parent / "src" / "fitdocs" / "load" / "types.py"
    )
    module_name = "_isolated_load_types"
    script = (
        "import sys\n"
        "import importlib.util\n"
        f"spec = importlib.util.spec_from_file_location({module_name!r}, "
        f"{str(types_path)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        f"sys.modules[{module_name!r}] = module\n"
        "spec.loader.exec_module(module)\n"
        "assert 'fitdocs.load.settings' not in sys.modules, "
        "'fitdocs.load.types must not import fitdocs.load.settings at "
        "runtime'\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "OK" in result.stdout


# --------------------------------------------------------------------------- #
# fitdocs.history (load-history task 5.4, Req 2.4, 7.5): the package's
# published surface, pinned once every task that appends to
# ``fitdocs.history.__all__`` (2.2, 3.2, 4.2, 5.1, 5.2) has landed. Unlike the
# leaf-module surfaces above, this pin also asserts *identity against each
# name's own defining submodule* (not just against ``fitdocs.contract``): the
# package root re-exports names gathered from five different submodules
# (``engine``, ``model``, ``page``, ``series``, ``settings``), so a local
# shadow bound directly in ``__init__.py`` -- e.g. a stray
# ``run_history = lambda *a, **k: None`` added after the real import --
# would satisfy every ``hasattr``/``__all__`` check here and still be a
# different object from ``fitdocs.history.engine.run_history``, exactly the
# class of drift the module-surface pins above (``_CHANNELS_SURFACE`` et al.)
# do not need to catch because those modules define every name they publish
# themselves.
# --------------------------------------------------------------------------- #

_HISTORY_SURFACE = {
    "HISTORY_FRONTMATTER_KEYS",
    "HISTORY_TITLE",
    "HISTORY_TYPE",
    "HISTORY_VERSION",
    "HISTORY_VERSION_KEY",
    "DEFAULT_HISTORY_SETTINGS",
    "HistorySettings",
    "HistorySettingsError",
    "load_history_settings",
    "resolve_constants",
    "ModelSeries",
    "run_model",
    "unscaled_accumulators",
    "MethodologyChoice",
    "MethodologyProblem",
    "MethodologyRecord",
    "partition_pages",
    "select_methodology",
    "HistoryReport",
    "MethodologyConfigurationError",
    "run_history",
}

#: Which submodule defines each published name -- the object the identity
#: check below compares against.
_HISTORY_SURFACE_OWNERS = {
    "HISTORY_FRONTMATTER_KEYS": fitdocs.history.page,
    "HISTORY_TITLE": fitdocs.history.page,
    "HISTORY_TYPE": fitdocs.history.page,
    "HISTORY_VERSION": fitdocs.history.page,
    "HISTORY_VERSION_KEY": fitdocs.history.page,
    "DEFAULT_HISTORY_SETTINGS": fitdocs.history.settings,
    "HistorySettings": fitdocs.history.settings,
    "HistorySettingsError": fitdocs.history.settings,
    "load_history_settings": fitdocs.history.settings,
    "resolve_constants": fitdocs.history.settings,
    "ModelSeries": fitdocs.history.model,
    "run_model": fitdocs.history.model,
    "unscaled_accumulators": fitdocs.history.model,
    "MethodologyChoice": fitdocs.history.series,
    "MethodologyProblem": fitdocs.history.series,
    "MethodologyRecord": fitdocs.history.series,
    "partition_pages": fitdocs.history.series,
    "select_methodology": fitdocs.history.series,
    "HistoryReport": fitdocs.history.engine,
    "MethodologyConfigurationError": fitdocs.history.engine,
    "run_history": fitdocs.history.engine,
}


def test_history_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.history.__all__) == _HISTORY_SURFACE
    # __all__ has no duplicates.
    assert len(fitdocs.history.__all__) == len(set(fitdocs.history.__all__))


def test_history_surface_owners_cover_exactly_the_published_surface() -> None:
    """``_HISTORY_SURFACE_OWNERS`` must name exactly the published names --
    a name published with no owner entry would leave the identity check
    below silently skipping it, the same failure mode
    ``test_every_converted_module_declares_its_contract_bindings`` (in
    ``tests/test_contract_consumers.py``) guards against for that registry.
    """
    assert set(_HISTORY_SURFACE_OWNERS) == _HISTORY_SURFACE


def test_every_history_name_is_the_same_object_as_its_defining_module() -> None:
    """Each published name is its defining submodule's own object, not a
    same-named local re-export bound directly in ``__init__.py``.

    Mutation caught (measured, round 2): adding
    ``run_history = lambda *args, **kwargs: None`` to
    ``src/fitdocs/history/__init__.py`` immediately below the real
    ``from fitdocs.history.engine import (... run_history)`` line reds this
    identity assertion at ``getattr(fitdocs.history, "run_history") is
    getattr(fitdocs.history.engine, "run_history")`` -- but not *only* this
    one: the shadow, still callable with the same signature and still
    listed in ``__all__``, is exercised by the confinement suite's history
    entry point, so
    ``tests/test_confinement.py::test_entry_point_writes_only_inside_the_permitted_locations[history]``
    and
    ``tests/test_confinement.py::test_history_entry_point_writes_no_workout_doc_asset_source_profile_or_settings``
    also go red (measured: 3 failed total) because the shadow writes
    nothing. The package's own ``__all__`` list and every ``hasattr``
    check do stay green, because the name is still listed and bound.
    """
    for name, owner in _HISTORY_SURFACE_OWNERS.items():
        assert hasattr(fitdocs.history, name), f"fitdocs.history is missing {name}"
        assert hasattr(owner, name), f"{owner.__name__} does not define {name}"
        assert getattr(fitdocs.history, name) is getattr(owner, name), (
            f"fitdocs.history.{name} is not the same object as {owner.__name__}.{name}"
        )


def test_history_is_not_re_exported_from_the_package_root() -> None:
    """The history package is a module-level surface, not a package-root name."""
    assert not set(fitdocs.__all__) & _HISTORY_SURFACE


# --- fitdocs.performance: the derivation pass' published surface -----------
#
# (performance-benchmarks task 4.5, design: PerformanceTypes / Guards
# "Public surface", Req 9.4, 9.5, 10.8) Every name `fitdocs.performance`
# publishes: the five names 1.1 shipped (the derivation-method and
# decline-reason vocabularies, the two frozen outcome values, and their
# sealed union) plus `derive_benchmarks`, appended last by 4.3 once the pass
# existed. Pinned the same way as `fitdocs.contract`/`fitdocs.audit`/
# `fitdocs.docio` above -- an equality pin on `__all__` plus an identity
# check against each name's *defining* module, `is` rather than `==`, so a
# same-named local re-implementation (e.g. a second `derive_benchmarks` that
# merely matches by name) is rejected exactly as a renamed or dropped export
# is.
_PERFORMANCE_EXPECTED = {
    "DeclineReason": fitdocs.performance.types.DeclineReason,
    "DerivationDeclined": fitdocs.performance.types.DerivationDeclined,
    "DerivationMethod": fitdocs.performance.types.DerivationMethod,
    "DerivationOutcome": fitdocs.performance.types.DerivationOutcome,
    "DerivedBenchmark": fitdocs.performance.types.DerivedBenchmark,
    "derive_benchmarks": fitdocs.performance.engine.derive_benchmarks,
}


def test_performance_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.performance.__all__) == set(_PERFORMANCE_EXPECTED)
    # __all__ has no duplicates.
    assert len(fitdocs.performance.__all__) == len(set(fitdocs.performance.__all__))


def test_every_performance_name_is_importable_and_correct() -> None:
    for name, expected in _PERFORMANCE_EXPECTED.items():
        assert hasattr(fitdocs.performance, name), (
            f"fitdocs.performance is missing {name}"
        )
        assert getattr(fitdocs.performance, name) is expected, (
            f"fitdocs.performance.{name} is not {expected!r}"
        )


def test_performance_direct_from_import_binds_the_public_names() -> None:
    from fitdocs.performance import (  # noqa: F401
        DeclineReason,
        DerivationDeclined,
        DerivationMethod,
        DerivationOutcome,
        DerivedBenchmark,
        derive_benchmarks,
    )

    assert DeclineReason is fitdocs.performance.types.DeclineReason
    assert DerivationDeclined is fitdocs.performance.types.DerivationDeclined
    assert DerivationMethod is fitdocs.performance.types.DerivationMethod
    assert DerivationOutcome is fitdocs.performance.types.DerivationOutcome
    assert DerivedBenchmark is fitdocs.performance.types.DerivedBenchmark
    assert derive_benchmarks is fitdocs.performance.engine.derive_benchmarks


def test_performance_is_not_re_exported_from_the_package_root() -> None:
    """The performance package is a module-level surface, not a package-root
    name -- ``fitdocs.__all__`` stays the narrow parse/compute API."""
    assert not set(fitdocs.__all__) & set(_PERFORMANCE_EXPECTED)


# --- fitdocs.plans: the training-block package's published surface --------
#
# (training-blocks task 4.4, design: "PackageBoundary and SurfacePins", Req
# 3.9, 6.4, 7.7, 8.4) ``fitdocs.plans.__init__`` is **append-only** across
# this plan's tasks (2.1, 2.2, 2.3, 3.1, 4.1, 4.2) -- this pin, like
# ``_HISTORY_SURFACE`` above, is a package-root surface gathered from eight
# submodules, so it also asserts identity against each name's own *defining*
# module, not merely ``fitdocs.contract`` -- a local shadow bound directly
# in ``__init__.py`` would satisfy every ``hasattr``/``__all__`` check here
# and still be a different object from its defining submodule's own.
#
# ``GENERATOR`` is the one name with two identities asserted, though the
# second is **not** the stronger check it might look like: CPython interns
# short, identifier-shaped string literals process-wide, so a re-spelled
# ``GENERATOR: Final[str] = "fitdocs"`` written a second time in ``page.py``
# is still ``is`` its own contract counterpart (measured directly: both
# ``fitdocs.plans.GENERATOR is fitdocs.plans.page.GENERATOR`` and
# ``fitdocs.plans.GENERATOR is fitdocs.contract.GENERATOR`` stay ``True``
# under that mutation) -- neither assertion below rules out a re-spelled
# *identical* literal. What the ``is`` checks rule out is everything an
# ``==`` check would also miss but a same-*value* re-implementation would
# not always share: a runtime-constructed string (``"".join(["f", "i", ...])``
# or an f-string), a value bound from a different source entirely, or
# simply a different value -- the ordinary "renamed or removed export"
# class of regression these owner-identity pins exist to catch across this
# whole file, GENERATOR included, is unaffected by the interning quirk.
# ``tests/plans/test_boundary.py``'s own ``TestNoBareRegionIdLiteral``-style
# AST scan is what actually rules out a local re-spelling of this specific
# name (see ``tests/plans/test_boundary.py::TestNoLocalContractNameRebinding``).
_PLANS_SURFACE = {
    # -- plans.model (2.1, 2.2) --
    "IDENTIFIER",
    "RESERVED_BLOCK_IDS",
    "is_reserved_block_id",
    "PlannedWorkout",
    "MesocycleTarget",
    "PlanState",
    "Mesocycle",
    "PlanProblem",
    "mesocycle_windows",
    "mesocycle_number",
    "check_rows",
    "check_targets",
    "MUTABLE_FIELDS",
    "UpdateOp",
    "AddOp",
    "RemoveOp",
    "TargetOp",
    "AmendmentOp",
    "AmendmentSpec",
    "RowChanged",
    "RowAdded",
    "RowRemoved",
    "TargetChanged",
    "Change",
    "Amendment",
    "Override",
    "Block",
    "apply_amendments",
    "check_overrides",
    "build_block",
    # -- plans.source (2.3) --
    "PlanValidationError",
    "parse_block",
    "load_block",
    # -- plans.resolution (3.1) --
    "RowResolution",
    "MesocycleResolution",
    "Resolution",
    "UNRESOLVED_ROW",
    "unresolved",
    # -- plans.page (3.1) --
    "BLOCK_TYPE",
    "BLOCK_VERSION",
    "BLOCK_VERSION_KEY",
    "BLOCK_FRONTMATTER_KEYS",
    "PLANNED_TYPE",
    "PLANNED_VERSION",
    "PLANNED_VERSION_KEY",
    "PLANNED_FRONTMATTER_KEYS",
    "WEEKDAYS",
    "INDOOR_WORD",
    "GENERATOR",
    "yaml_string",
    "frontmatter",
    "banner",
    "notes_region",
    "check_resolution",
    "is_fence_line",
    "sport_phrase",
    "cell",
    "link_text",
    "format_day",
    "format_load",
    # -- plans.settings (4.1) --
    "PLANS_TABLE",
    "PlanSettings",
    "DEFAULT_PLAN_SETTINGS",
    "PlanSettingsError",
    "load_plan_settings",
    "resolve_plans_dir",
    # -- plans.block_page, plans.planned_page, plans.engine (4.2) --
    "render_block_page",
    "render_planned_page",
    "BlockStatus",
    "BlockOutcome",
    "PlanReport",
    "Resolver",
    "run_plan",
    # -- plans.corpus (plan-resolution 2.1) --
    "LoggedWorkout",
    "Corpus",
    "scan_corpus",
}

#: Which submodule defines each published name -- the object the identity
#: check below compares against (mirrors ``_HISTORY_SURFACE_OWNERS``).
_PLANS_SURFACE_OWNERS = {
    "IDENTIFIER": fitdocs.plans.model,
    "RESERVED_BLOCK_IDS": fitdocs.plans.model,
    "is_reserved_block_id": fitdocs.plans.model,
    "PlannedWorkout": fitdocs.plans.model,
    "MesocycleTarget": fitdocs.plans.model,
    "PlanState": fitdocs.plans.model,
    "Mesocycle": fitdocs.plans.model,
    "PlanProblem": fitdocs.plans.model,
    "mesocycle_windows": fitdocs.plans.model,
    "mesocycle_number": fitdocs.plans.model,
    "check_rows": fitdocs.plans.model,
    "check_targets": fitdocs.plans.model,
    "MUTABLE_FIELDS": fitdocs.plans.model,
    "UpdateOp": fitdocs.plans.model,
    "AddOp": fitdocs.plans.model,
    "RemoveOp": fitdocs.plans.model,
    "TargetOp": fitdocs.plans.model,
    "AmendmentOp": fitdocs.plans.model,
    "AmendmentSpec": fitdocs.plans.model,
    "RowChanged": fitdocs.plans.model,
    "RowAdded": fitdocs.plans.model,
    "RowRemoved": fitdocs.plans.model,
    "TargetChanged": fitdocs.plans.model,
    "Change": fitdocs.plans.model,
    "Amendment": fitdocs.plans.model,
    "Override": fitdocs.plans.model,
    "Block": fitdocs.plans.model,
    "apply_amendments": fitdocs.plans.model,
    "check_overrides": fitdocs.plans.model,
    "build_block": fitdocs.plans.model,
    "PlanValidationError": fitdocs.plans.source,
    "parse_block": fitdocs.plans.source,
    "load_block": fitdocs.plans.source,
    "RowResolution": fitdocs.plans.resolution,
    "MesocycleResolution": fitdocs.plans.resolution,
    "Resolution": fitdocs.plans.resolution,
    "UNRESOLVED_ROW": fitdocs.plans.resolution,
    "unresolved": fitdocs.plans.resolution,
    "BLOCK_TYPE": fitdocs.plans.page,
    "BLOCK_VERSION": fitdocs.plans.page,
    "BLOCK_VERSION_KEY": fitdocs.plans.page,
    "BLOCK_FRONTMATTER_KEYS": fitdocs.plans.page,
    "PLANNED_TYPE": fitdocs.plans.page,
    "PLANNED_VERSION": fitdocs.plans.page,
    "PLANNED_VERSION_KEY": fitdocs.plans.page,
    "PLANNED_FRONTMATTER_KEYS": fitdocs.plans.page,
    "WEEKDAYS": fitdocs.plans.page,
    "INDOOR_WORD": fitdocs.plans.page,
    "GENERATOR": fitdocs.plans.page,
    "yaml_string": fitdocs.plans.page,
    "frontmatter": fitdocs.plans.page,
    "banner": fitdocs.plans.page,
    "notes_region": fitdocs.plans.page,
    "check_resolution": fitdocs.plans.page,
    "is_fence_line": fitdocs.plans.page,
    "sport_phrase": fitdocs.plans.page,
    "cell": fitdocs.plans.page,
    "link_text": fitdocs.plans.page,
    "format_day": fitdocs.plans.page,
    "format_load": fitdocs.plans.page,
    "PLANS_TABLE": fitdocs.plans.settings,
    "PlanSettings": fitdocs.plans.settings,
    "DEFAULT_PLAN_SETTINGS": fitdocs.plans.settings,
    "PlanSettingsError": fitdocs.plans.settings,
    "load_plan_settings": fitdocs.plans.settings,
    "resolve_plans_dir": fitdocs.plans.settings,
    "render_block_page": fitdocs.plans.block_page,
    "render_planned_page": fitdocs.plans.planned_page,
    "BlockStatus": fitdocs.plans.engine,
    "BlockOutcome": fitdocs.plans.engine,
    "PlanReport": fitdocs.plans.engine,
    "Resolver": fitdocs.plans.engine,
    "run_plan": fitdocs.plans.engine,
    "LoggedWorkout": fitdocs.plans.corpus,
    "Corpus": fitdocs.plans.corpus,
    "scan_corpus": fitdocs.plans.corpus,
}


def test_plans_all_lists_exactly_its_published_surface() -> None:
    assert set(fitdocs.plans.__all__) == _PLANS_SURFACE
    # __all__ has no duplicates.
    assert len(fitdocs.plans.__all__) == len(set(fitdocs.plans.__all__))


def test_plans_surface_owners_cover_exactly_the_published_surface() -> None:
    """``_PLANS_SURFACE_OWNERS`` must name exactly the published names --
    a name published with no owner entry would leave the identity check
    below silently skipping it (mirrors
    ``test_history_surface_owners_cover_exactly_the_published_surface``)."""
    assert set(_PLANS_SURFACE_OWNERS) == _PLANS_SURFACE


def test_every_plans_name_is_the_same_object_as_its_defining_module() -> None:
    """Each published name is its defining submodule's own object, not a
    same-named local re-export bound directly in ``__init__.py``."""
    for name, owner in _PLANS_SURFACE_OWNERS.items():
        assert hasattr(fitdocs.plans, name), f"fitdocs.plans is missing {name}"
        assert hasattr(owner, name), f"{owner.__name__} does not define {name}"
        assert getattr(fitdocs.plans, name) is getattr(owner, name), (
            f"fitdocs.plans.{name} is not the same object as {owner.__name__}.{name}"
        )


def test_generator_is_also_the_same_object_as_the_contract_publishes() -> None:
    """``GENERATOR`` is asserted against both its owner (``plans.page``,
    checked by the generic identity test above) and
    ``fitdocs.contract.GENERATOR`` directly. Measured, not assumed (see the
    ``_PLANS_SURFACE`` comment above): a re-spelled *identical* literal in
    ``page.py`` would still pass **both** checks, since CPython interns
    short identifier-shaped string literals -- this assertion, like the one
    above, rules out a renamed, removed, or differently-valued export, not
    a byte-identical local re-spelling; that narrower claim belongs to
    ``tests/plans/test_boundary.py``'s own AST scan for a local rebinding of
    a contract name.
    """
    assert fitdocs.plans.GENERATOR is fitdocs.contract.GENERATOR


def test_plans_is_not_re_exported_from_the_package_root() -> None:
    """The plans package is a module-level surface, not a package-root
    name -- ``fitdocs.__all__`` stays the narrow parse/compute API."""
    assert not set(fitdocs.__all__) & _PLANS_SURFACE

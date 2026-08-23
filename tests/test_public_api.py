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
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import fitdocs
import fitdocs.audit
import fitdocs.benchmarks
import fitdocs.contract
import fitdocs.declaration
import fitdocs.docio
import fitdocs.ingest
import fitdocs.ingest.errors
import fitdocs.load
import fitdocs.load.registry
import fitdocs.load.settings
import fitdocs.load.types
import fitdocs.metrics
import fitdocs.metrics.types
import fitdocs.model

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
# plugin authors never import directly). This spec ships no calculator (Req
# 13.2), so no bundled calculator name is expected here either. This test
# asserts every ENUMERATED name is importable and identical to its defining
# object, and never asserts or forbids names beyond that enumeration --
# deleting any one of them fails the test below; adding ``registry`` to it
# would be a test bug, not a regression, so it is deliberately absent from
# ``_LOAD_EXPECTED``.
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
}


def test_every_load_plugin_surface_name_is_importable_and_correct() -> None:
    for name, expected in _LOAD_EXPECTED.items():
        assert hasattr(fitdocs.load, name), f"fitdocs.load is missing {name}"
        assert getattr(fitdocs.load, name) is expected, f"{name} is the wrong object"


def test_load_plugin_surface_direct_from_import_binds_the_public_names() -> None:
    from fitdocs.load import (  # noqa: F401
        DEFAULT_LOAD_SETTINGS,
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


# Every name the document contract publishes: the vocabulary, the versions, the
# region-ownership policy, the fresh-region texts, the pure readers, and the
# marker helpers it re-exports from ``docmerge`` so a consumer needs one import.
_CONTRACT_SURFACE = {
    # versions
    "CONTRACT_VERSION",
    "DOC_VERSION",
    # document vocabulary
    "DOC_VERSION_KEY",
    "FRONTMATTER_FENCE",
    "GENERATOR",
    "GENERATOR_KEY",
    "LOAD_KEYS",
    "MANAGED_KEYS",
    "SOURCES_KEY",
    "TYPE_KEY",
    "UUID_KEY",
    "WORKOUT_TYPE",
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
    "document_uuid",
    "document_version",
    "format_session_uuid",
    "frontmatter_close_index",
    "is_workout_document",
    "parse_frontmatter",
    "sha_of_ref",
    "source_refs",
    "unmanaged_keys",
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

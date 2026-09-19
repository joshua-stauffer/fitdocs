# Vendored baseline for tests/test_preserved_guarantees.py.
#
# Provenance: these constants are the literal values read from
# `pyproject.toml`'s `[project]` table and `src/fitdocs/__init__.py`'s
# `__all__` at commit e74af37 -- the pre-feature revision this distribution
# plan's worktree branched from -- extracted with:
#
#     git show e74af37:pyproject.toml
#     git show e74af37:src/fitdocs/__init__.py
#
# Vendored here rather than read from git history at test time, because a
# depth-limited clone (GitHub Actions' default `actions/checkout` at
# `fetch-depth: 1`, or any shallow/partial clone -- the workflow does not and
# must not change this) does not carry the e74af37 object, and a test that
# shells out to `git show e74af37:...` fails with a missing-object error
# instead of reporting the drift it exists to catch. Vendoring this data
# makes the preserved-guarantee comparisons independent of what history
# happens to be present in the checkout, following the precedent set by
# `tests/fixtures/report_baseline_faa6d09.py`.
#
# Do not regenerate these constants against a moving target (e.g. "whatever
# HEAD currently has"): they exist to catch a regression relative to the
# *fixed* pre-feature point. If a future, deliberate change to the pre-1.0
# dependency set or the public surface is approved, re-vendor from the new
# baseline commit explicitly -- do not silently edit these to match HEAD.

from __future__ import annotations

#: `git show e74af37:pyproject.toml`'s `[project].dependencies`, in the
#: exact order they were declared.
DEPENDENCIES: tuple[str, ...] = (
    "garmin-fit-sdk>=21.208.0",
    "typer>=0.12",
    "rich>=13",
    "pyyaml>=6.0",
    "tomli-w>=1.0",
)

#: `git show e74af37:pyproject.toml`'s `[project].optional-dependencies` --
#: empty at the pre-feature revision.
OPTIONAL_DEPENDENCIES: dict[str, list[str]] = {}

#: `git show e74af37:src/fitdocs/__init__.py`'s `__all__`, in the exact
#: order it was declared (alphabetical, matching the source).
PUBLIC_ALL: tuple[str, ...] = (
    "SCHEMA_VERSION",
    "Activity",
    "AthleteInputs",
    "DerivedMetrics",
    "DeviceInfo",
    "FitDecodeError",
    "FitIntegrityError",
    "Lap",
    "Modality",
    "NotFitFileError",
    "Provenance",
    "Samples",
    "SessionSummary",
    "Sport",
    "StrengthSet",
    "TrimpWeighting",
    "ZoneSpec",
    "compute_metrics",
    "fit_datetime",
    "parse_fit",
)

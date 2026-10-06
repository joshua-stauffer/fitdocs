"""Re-derive one page's computed values from its listed FIT archives."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from fitdocs import AthleteInputs, compute_metrics, parse_fit
from fitdocs.compose.archive import compose_listed
from fitdocs.compose.types import Composition
from fitdocs.contract import sha_of_ref
from fitdocs.index.bookkeeping import ComputedState
from fitdocs.ingest.errors import FitDecodeError
from fitdocs.layout import archive_path
from fitdocs.metrics.types import DerivedMetrics


@dataclass(frozen=True)
class Derived:
    """A page's composed activity and metrics computed from that activity."""

    composition: Composition
    metrics: DerivedMetrics


def base_archive(data_root: Path, sources: Sequence[str]) -> Path | None:
    """Return the existing archive path named by the last source, if valid."""
    if not sources:
        return None
    sha = sha_of_ref(sources[-1])
    if sha is None:
        return None
    path = archive_path(data_root, sha)
    return path if path.is_file() else None


def derive_page(
    data_root: Path, sources: Sequence[str], athlete: AthleteInputs | None
) -> Derived | ComputedState:
    """Compose and score listed sources, or return their computed state."""
    base_path = base_archive(data_root, sources)
    if base_path is None:
        return ComputedState.SOURCE_MISSING
    try:
        base_bytes = base_path.read_bytes()
    except OSError:
        return ComputedState.SOURCE_UNREADABLE
    try:
        base = parse_fit(base_bytes)
    except FitDecodeError:
        return ComputedState.SOURCE_UNDECODABLE
    try:
        composition = compose_listed(data_root, sources, base)
    except OSError:
        return ComputedState.SOURCE_UNREADABLE
    except FitDecodeError:
        return ComputedState.SOURCE_UNDECODABLE
    return Derived(composition, compute_metrics(composition.activity, athlete))

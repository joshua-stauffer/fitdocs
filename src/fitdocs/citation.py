"""The shared citation vocabulary (Amendment 1).

This module is the second dependency-free leaf, alongside :mod:`fitdocs.model`,
at the bottom of the fitdocs dependency stack: it imports nothing internal and
never imports the ``garmin-fit-sdk``. It holds no arithmetic and defines no
constant record -- shapes only -- so that both ``fitdocs.metrics`` (below
``fitdocs.load``) and ``fitdocs.load.channels`` (above ``fitdocs.metrics``) can
depend on it without either importing the other (Req 15.2, 15.8, 15.9, 16.1,
16.4-16.7; design.md "citation layer (Amendment 1)").

Before Amendment 1, :class:`VerificationStatus` and a citation record lived
only in ``fitdocs.load.channels.sources``, one layer above ``fitdocs.metrics``,
so fit-ingest's own constants could not reference them without an upward
import. They move here; task 8.2 re-points ``fitdocs.load.channels.sources``
to import and re-export them instead of declaring its own, keeping its
citation records byte-identical (see design.md's "Constant Provenance
(Amendment 1)" Decision D2). That re-point has landed: as of task 8.2,
``fitdocs.load.channels.sources`` imports and re-exports both names from here
rather than declaring its own.

**The sealed union is what makes 16.4 structural, not reviewed.**
:data:`SourceRecord` is exactly :class:`Citation` or :class:`FitdocsChoice` --
never a third shape and never one masquerading as the other. Req 16.4 forbids
recording a value as read from a published work's primary text where only a
fitdocs choice holds; :class:`FitdocsChoice` enforces this by construction
rather than by convention: it has no field that can be set to
``VerificationStatus.PRIMARY_TEXT``. Its own ``verification`` field is typed
``Literal[VerificationStatus.FITDOCS_MEASURED]``, so it is not merely
*undocumented* to widen it -- doing so is a type error under strict checking.

**Corroboration is not a second governing source.** :class:`CitedConstant`
binds a value to exactly one governing :data:`SourceRecord` (Req 16.2, enforced
in ``fitdocs.metrics.sources``, one layer above this module) plus any number of
:class:`Corroboration` tuples -- further works that *speak to* the value
without fixing it. This is how Req 15.2 (a training-impulse weighting term
records both Banister (1991) and Morton (1990), each with its own locator) is
satisfied without contradicting Req 16.2's "exactly one record": the second
work is a corroborator, not a second governing source. See design.md's
"``corroborators`` is how 15.2 is satisfied without breaking 16.2."

**What this module does not do.** It carries no invariant-checking logic --
"a ``Corroboration`` whose ``agreement`` is not ``AGREES`` has a non-``None``
``note``", "no ``Corroboration`` names the same work as its constant's
governing source", and similar rules named in design.md are meant to be
asserted by a guard one layer up (``fitdocs.metrics.sources`` /
``ConstantGuard``), not by ``__post_init__`` here, so that a failure names the
offending constant rather than a construction site. That guard is tasks
9.x/10.x; at this commit ``fitdocs.metrics`` has no ``sources.py`` and no
``ConstantGuard`` exists yet. This module states shapes only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Literal, TypeVar


class VerificationStatus(StrEnum):
    """How well a cited constant's value was verified against its source.

    Task 8.2 re-points ``fitdocs.load.channels.sources`` to import and
    re-export this enum verbatim rather than declaring its own (design.md
    Decision D2); that module now imports it from here.
    ``SECONDARY_ATTESTATION`` is kept here for that shared use even
    though fit-ingest's own guard (``fitdocs.metrics.sources``,
    ``ConstantGuard``, tasks 9.x/10.x -- not yet built) will forbid it for
    any fit-ingest constant (Req 15.4) -- the vocabulary is shared; the
    policy over it is per-layer.
    """

    PRIMARY_TEXT = "primary_text"
    """The value was read from the cited work's own primary text."""

    SECONDARY_ATTESTATION = "secondary_attestation"
    """Consistently attested by independent secondary sources; the primary
    text was not obtainable. Not permitted for a fit-ingest constant
    (Req 15.4) -- ``fitdocs.load.channels.sources`` is this status's only
    permitted consumer, under its own named-exception policy."""

    FITDOCS_MEASURED = "fitdocs_measured"
    """No published work defines this value; fitdocs states it as its own
    choice (Req 15.8). Never present this as ``PRIMARY_TEXT``."""


@dataclass(frozen=True)
class Citation:
    """A published work's authors, year, work, locator and verification
    status (Req 15.1, 16.1)."""

    key: str
    authors: str
    year: int
    work: str
    locator: str | None
    verification: VerificationStatus
    note: str | None = None


@dataclass(frozen=True)
class FitdocsChoice:
    """A value no published work defines, recorded as fitdocs' own choice
    (Req 15.8, 15.9, 16.7).

    Carries ``justification`` (why this value) and ``search_basis`` (what was
    searched and what was found) in place of the authors, year, work and
    locator a :class:`Citation` supplies -- there is no published work to
    name. ``verification`` is pinned to ``FITDOCS_MEASURED``: this record has
    no field that can hold ``PRIMARY_TEXT``, which is what makes conflating a
    chosen value with a sourced one (Req 16.4) a type error rather than a
    reviewed convention.
    """

    key: str
    justification: str
    search_basis: str
    measurement: str | None = None
    verification: Literal[VerificationStatus.FITDOCS_MEASURED] = (
        VerificationStatus.FITDOCS_MEASURED
    )


SourceRecord = Citation | FitdocsChoice
"""The sealed union of a constant's governing source (Req 16.4): either a
published work's :class:`Citation`, or fitdocs' own :class:`FitdocsChoice`
where no published work defines the value. No third shape exists."""


class Agreement(StrEnum):
    """How a corroborating work relates to the value it speaks to (Req 15.2)."""

    AGREES = "agrees"
    """The corroborating work states the same value."""

    OMITS = "omits"
    """The corroborating work states the surrounding formula without this
    term."""

    DIFFERS = "differs"
    """The corroborating work states a different value."""


@dataclass(frozen=True)
class Corroboration:
    """A further published work that speaks to a constant's value without
    governing it (Req 15.2).

    ``citation`` carries its own verification status, independent of the
    constant's governing source. The guard one layer up (``ConstantGuard``,
    tasks 9.x/10.x -- not yet built) will require ``note`` whenever
    ``agreement`` is not ``AGREES`` -- a work that omits or contradicts the
    value must say so in words, not only in the enum.
    """

    citation: Citation
    locator: str
    agreement: Agreement
    note: str | None = None


@dataclass(frozen=True)
class Departure:
    """A deliberate departure from what a cited work specifies (Req 16.5).

    ``subject`` names the constant or behavior departing and is asserted
    unique within a consuming layer's ``DEPARTURES`` collection, one layer up.
    """

    subject: str
    source_specifies: str
    fitdocs_does: str
    reason: str


_N = TypeVar("_N", int, float)


@dataclass(frozen=True)
class CitedConstant(Generic[_N]):
    """Binds a value to its governing source, its corroborators, any
    deliberate departure, and the value it replaced (Req 16.2, 15.2, 16.5,
    15.3).

    Carries exactly one governing ``source`` -- the work whose text fixes the
    value -- so a constant with two governing sources or none cannot be
    constructed. ``corroborators`` names further works that speak to the value
    without governing it (Req 15.2), which is how the training-impulse
    weighting terms record both Banister (1991) and Morton (1990) while still
    keeping exactly one governing record. ``previous_value`` is the value a
    primary-text re-sourcing replaced (Req 15.3), and is ``None`` when
    re-sourcing confirmed the shipped value unchanged.
    """

    name: str
    value: _N
    source: SourceRecord
    corroborators: tuple[Corroboration, ...] = ()
    departure: Departure | None = None
    previous_value: _N | None = None

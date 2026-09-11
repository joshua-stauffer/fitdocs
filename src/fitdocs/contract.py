"""The fitdocs document contract: one policy every command reads (design:
DocumentContract).

A fitdocs workout document is written by one command and read by several
others -- sync, regeneration, the training-load pass, and the contract audit all
open the same file and must understand it identically (Req 1.1, 1.4). This
module is where that shared understanding lives: a pure leaf that states *what a
fitdocs document is* -- its frontmatter vocabulary, how its identity, format
version, and source history are read, *which* regions it reserves, *who owns*
each one, and what a freshly rendered region carries. It performs no I/O, reads
no clock, and imports nothing from the render, sync, load, CLI, layout, or model
layers, so any module in the package may depend on it.

Policy versus mechanism
-----------------------
:mod:`fitdocs.docmerge` owns the region *grammar* -- how a marker is spelled,
how a region is composed, extracted, and merged -- and is deliberately generic
over region ids: it is one algorithm, not three. This module owns the *policy*
those functions are pointed at: the three region ids, which of them a human
owns and which the tool fills, the preserved set, and the exact text a fresh
region carries. Grammar changes are a merge-module concern; ownership changes
are a contract concern, and a contract change is user-visible. The three marker
helpers are re-exported here so a consumer that needs both policy and grammar
imports one module; no new syntax is added.

Readers degrade, never raise
----------------------------
Every reader below accepts arbitrary input and answers with an *absent* value --
``None``, ``()``, or ``False`` -- for anything it does not recognize. That is
what lets each command keep its "skip what I cannot read" behavior while sharing
one interpretation (Req 1.2): a hand-authored page, a half-written file, a
foreign ``.md``, or a document a user edited into invalid YAML is simply not a
fitdocs document, and the run continues.

Absent is never a fabricated value. :func:`document_version` returns a version
only for a genuine integer -- in Python ``bool`` subclasses ``int``, so ``True``
is rejected explicitly rather than read as version 1 -- and a missing or
unusable version is ``None``, not ``0`` (Req 5.7). :func:`sha_of_ref` resolves
only a bare hex digest, so a hand-edited or traversal-shaped ``sources`` entry
is unresolvable rather than a lookup outside the archive (Req 1.3).

Versions
--------
Two version numbers live here and never mix. :data:`DOC_VERSION` is an integer
stamped into every generated document and compared arithmetically: lower means
out of date, higher means written by a newer fitdocs (Req 5.1-5.3, 5.5).
:data:`CONTRACT_VERSION` is a string identifier for the *published ownership
contract* -- the guarantees, not the file format -- quoted in the documentation
and in every in-tree declaration (Req 2.8).

Three classes of frontmatter key
---------------------------------
Every frontmatter key a fitdocs document may carry falls into exactly one of
three classes. **Managed** (:data:`MANAGED_KEYS`) keys are written by the
render layer or the training-load pass and rewritten in full on every
regeneration. **User-owned** (:data:`USER_KEYS`) keys -- currently the effort
tag's four keys -- are never written by fitdocs and are carried forward
verbatim on every rewrite, the same "yours to keep" guarantee
:data:`USER_REGIONS` gives a region rather than a key; this module states the
vocabulary, the ownership class and the line-level carry
(:func:`user_owned_lines`), which the sync engine applies to every rewrite.
Everything else is **unmanaged**: a key fitdocs neither writes nor
preserves, dropped with a warning on the next rewrite (:func:`unmanaged_keys`).
The three classes partition every key a document can carry; ``MANAGED_KEYS``
and ``USER_KEYS`` are disjoint, and held disjoint by test.

Region ownership
----------------
Three regions survive regeneration verbatim:

- ``notes`` and ``workout`` are **user-owned** (:data:`USER_REGIONS`). Their
  content is hand-authored; fitdocs writes an instructive placeholder into a
  brand-new document and never touches the region again.
- ``load`` is **tool-filled** (:data:`TOOL_REGIONS`). The training-load pass
  writes into it, but regeneration must still carry its content over rather
  than overwrite it, so it is preserved on the same footing.

:data:`PRESERVED_REGIONS` is the union in document order -- ``("notes",
"workout", "load")``. The order is part of the contract, not an accident: it is
the order regions appear in a rendered document and the order every published
enumeration of them uses.

Fresh-region content
--------------------
:data:`NOTES_PLACEHOLDER`, :data:`WORKOUT_PLACEHOLDER`, and
:data:`LOAD_NOT_COMPUTED` are the exact inner content of the corresponding
region in a freshly rendered document. Each states a guarantee in words and
contains no number: an unfilled region is an honest "nothing here yet", never a
fabricated zero. :data:`LOAD_NOT_COMPUTED` is additionally a *classifier* --
the training-load editor decides a ``load`` region is an untouched placeholder
by comparing against it, so the constant having exactly one definition is what
makes that comparison trustworthy.
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Final

import yaml

from fitdocs.docmerge import begin_marker, end_marker, region_block

__all__ = [
    "CONTRACT_VERSION",
    "DOC_BANNER",
    "DOC_VERSION",
    "DOC_VERSION_KEY",
    "EFFORT_DISTANCE_KEY",
    "EFFORT_EVENT_KEY",
    "EFFORT_KEY",
    "EFFORT_KEYS",
    "EFFORT_TIME_KEY",
    "EffortKind",
    "EffortTag",
    "EffortTagProblem",
    "FRONTMATTER_FENCE",
    "GENERATED_PREFIX",
    "GENERATOR",
    "GENERATOR_KEY",
    "InvalidEffortTag",
    "LOAD_KEYS",
    "LOAD_NOT_COMPUTED",
    "LOAD_REGION",
    "MANAGED_KEYS",
    "NOTES_PLACEHOLDER",
    "NOTES_REGION",
    "PRESERVED_REGIONS",
    "SOURCES_KEY",
    "TOOL_REGIONS",
    "TYPE_KEY",
    "USER_KEYS",
    "USER_REGIONS",
    "UUID_KEY",
    "WORKOUT_PLACEHOLDER",
    "WORKOUT_REGION",
    "WORKOUT_TYPE",
    "begin_marker",
    "document_date",
    "document_uuid",
    "document_version",
    "effort_tag",
    "end_marker",
    "format_session_uuid",
    "frontmatter_close_index",
    "is_generated",
    "is_workout_document",
    "parse_frontmatter",
    "region_block",
    "sha_of_ref",
    "source_refs",
    "unmanaged_keys",
    "user_owned_lines",
]

# --- versions ----------------------------------------------------------------

DOC_VERSION: Final[int] = 5
"""The document-format version stamped on every generated workout document.

Compared arithmetically against the version a document records (Req 5.1-5.3,
5.5): *lower* means the document predates the current format and regeneration
brings it current; *higher* means it was written by a newer fitdocs and this
installation must leave it alone rather than downgrade it. Raising it is a
user-visible format change and must land in the same change that regenerates
every committed golden document.

Raised from ``1`` to ``2`` in the same change that adds the ``generator`` key
and the provenance banner (Req 5.1, 5.2): the two frontmatter/body additions
are the entire format delta, so the version bump gives drift detection a real
signal to key on.

Raised from ``2`` to ``3`` in the same change that renames the managed load
keys to ``load_value``/``load_methodology``/``load_basis`` (Req 11.5): the
result format changed, so a document stamped with the prior version is
detectable as needing regeneration without opening its ``load`` region at all.

Raised from ``3`` to ``4`` by fit-ingest's Amendment 1 re-sourcing of its
metric constants (fit-ingest task 13.2, Req 18.1). No cited constant's value
actually moved -- all seven of the primary-text-sourced constants (four
training-impulse weighting terms plus ``TSS_SCALE``, ``NP_ROLLING_WINDOW_S``
and ``NP_AVERAGING_EXPONENT``) were confirmed unchanged (Req 15.1, 15.3,
18.4) -- but bringing normalized power into conformance with the cited
rolling-window step (only complete windows are averaged, dropping the
leading partial-window points) changes the value NP reports for most
activities whose power stream spans at least one window width, and with it
intensity factor, variability index, training-stress score and cycling
efficiency factor, for every already-documented activity with power data
whose NP moves. It is not a universal change: on a constant-power stream the
pre-13.1 partial-window average (dividing by ``min(i + 1, window)`` rather
than dropping the partial windows) already equals that same constant, so old
and new NP coincide there and nothing downstream moves either. That is a
metric-*value* change, not a change to the load result's own shape (Req 11.5
does not fire here; Req 18.1 does), and where it does change, whether it
raises or lowers a given activity's NP depends on whether its dropped
leading windows sat below or above the retained series -- higher is the
common case (a cold start ramping up to a steady power), but not the only
one possible. This bump is a one-line edit in a module fit-ingest does not
own, landing here only because Req 18.1 makes the advance a completion
condition of that amendment; no other behavior of this module changed, and
fit-ingest's own ``tests/metrics/test_power.py`` pins both the exact NP
value and the direction of the change on a fixture built to exercise it.

Raised from ``4`` to ``5`` by the maintainer's 2026-07-30 ruling on
``.kiro/queue/2026-07-30-absent-power-sample-filled-with-zero.md`` (chore/
power-absent-sample-fill), which changed
:func:`fitdocs.metrics.power._resample_power_1hz`'s 1 Hz resample in two
related ways, both removing a fabricated ``0.0`` from the fourth-power mean
normalized power takes:

1. An unrecorded (``None``) power sample *after* at least one power sample
   has already been recorded no longer fills as a fabricated ``0.0`` -- it
   forward-fills as the most recently RECORDED power value instead
   (matching that function's own docstring, which already claimed a
   forward-fill before this ruling made the fill value actually forward-fill
   anything), scanning every intervening raw sample rather than only the one
   a given grid second happens to land on, so a recorded reading is never
   skipped either. This changes normalized power, and with it intensity
   factor, variability index, training-stress score and cycling efficiency
   factor, for an already-documented activity whose power stream records at
   least one genuine device dropout after its first recorded sample; an
   activity whose power channel never drops out there computes identically
   before and after, because forward-fill and the old fabricated-zero fill
   only diverge where such a dropout actually occurs.
2. A leading dropout -- before the very first power sample is recorded at
   all -- no longer fills with anything either: the resample grid itself now
   starts at the first RECORDED sample, truncating the dead air before it
   rather than fabricating a value for it (this removed the one remaining
   site the first fix's own record, ``POWER_ABSENT_SAMPLE_CHOICE`` /
   ``POWER_ABSENT_SAMPLE_FILL``, still governed; neither record exists any
   more -- see ``sources.py``). This changes normalized power (and the same
   downstream metrics) for an already-documented activity whose power stream
   opens with a genuine device dropout before its first recorded sample; an
   activity with no leading dropout computes identically before and after,
   because truncation and the old fabricated-zero fill only diverge over the
   samples truncation actually removes.

Neither fix is universal, and both apply independently: an activity with
neither an opening nor a mid-stream/trailing power dropout computes
identically before and after this bump. None of Req 15.6's ten registered
constants moved, so this bump is the same *behavior*-trigger shape
fit-ingest task 13.2 introduced for the ``3 -> 4`` bump above: a
metric-value change with no moved registry entry behind it (Req 18.1 fires;
Req 11.5 does not, since the load result's own shape is unchanged).
``tests/metrics/test_power.py`` pins both fixes directly -- the forward-fill
rule on a fixture with distinguishing values on either side of a mid-stream
dropout, and the leading-truncation rule on a fixture with a leading
dropout before a steady plateau -- and ``tests/metrics/test_sources.py``
ties this specific bump to the mid-stream-dropout fixture the same way the
prior bump's behavior trigger did, with the same acknowledged limitation:
the forward assertion (``contract.DOC_VERSION`` past its pre-this-amendment
value) is a one-time, self-relative discrimination for this event and goes
quiet, by construction, once any later change advances the version for an
unrelated reason -- see ``_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE``'s
own docstring in that test module for why that is an accepted property of
this trigger shape, not a defect to route around a second time.
"""

CONTRACT_VERSION: Final[str] = "2"
"""The published ownership contract's version identifier (Req 2.8).

A *string*, and deliberately not comparable with :data:`DOC_VERSION`: it
versions the stated guarantees -- what fitdocs owns, what the user owns, what
regeneration replaces -- not the document format. It is quoted in the published
contract and restated in every in-tree ownership declaration, and changes
whenever a stated guarantee changes.

Bumped ``1`` -> ``2`` (Req 6.3) because a stated guarantee about what
regeneration preserves in the frontmatter block changed: :data:`USER_KEYS`
(the effort tag's four frontmatter keys) is a new class of key fitdocs never
writes and carries unchanged through every rewrite, alongside the pre-existing
managed keys and user-owned regions.
"""

# --- document vocabulary -----------------------------------------------------

WORKOUT_TYPE: Final[str] = "workout"
"""The frontmatter ``type`` value identifying a fitdocs workout document."""

GENERATOR: Final[str] = "fitdocs"
"""The tool name recorded as a generated document's generator (Req 4.1)."""

FRONTMATTER_FENCE: Final[str] = "---"
"""The line (ignoring surrounding whitespace) that opens and closes frontmatter."""

TYPE_KEY: Final[str] = "type"
"""Frontmatter key carrying the document type -- the fitdocs-document marker."""

GENERATOR_KEY: Final[str] = "generator"
"""Frontmatter key carrying the machine-readable generator name (Req 4.1)."""

DOC_VERSION_KEY: Final[str] = "doc_version"
"""Frontmatter key carrying the document-format version (Req 5.1)."""

UUID_KEY: Final[str] = "uuid"
"""Frontmatter key carrying the recorded session identity (Req 1.1, 1.3)."""

SOURCES_KEY: Final[str] = "sources"
"""Frontmatter key carrying the append-ordered archive-ref history (Req 1.3)."""

LOAD_KEYS: Final[tuple[str, ...]] = (
    "load_value",
    "load_methodology",
    "load_basis",
)
"""The three frontmatter keys the training-load pass writes, in emission order.

Named here rather than only in the load layer because the *ownership* question
they answer -- are these keys fitdocs' or the user's? -- is a contract question
(Req 6.2). They are a subset of :data:`MANAGED_KEYS`, so a document that has had
a load pass never reports an unmanaged key.

``load_value`` carries :attr:`~fitdocs.load.types.LoadResult.value` and
``load_basis`` carries :attr:`~fitdocs.load.types.LoadResult.basis`, which is
always present, so unlike the ``load_zone`` key these replace, the third key is
never conditionally omitted (Req 7.2). ``load_methodology`` carries
:attr:`~fitdocs.load.types.LoadResult.calculator_id` -- the origin record (Req
10.6). No diagnostic (``non_selected``, ``flags``) has a frontmatter projection
at all: restore re-derives frontmatter from the payload, so nothing is lost by
that omission.
"""

MANAGED_KEYS: Final[frozenset[str]] = frozenset(
    {
        # Written by the render layer's frontmatter builder, in emission order.
        "title",
        TYPE_KEY,
        GENERATOR_KEY,
        DOC_VERSION_KEY,
        UUID_KEY,
        "date",
        "start_time",
        "sport",
        "modality",
        "indoor",
        "distance_km",
        "moving_time",
        "avg_hr_bpm",
        "avg_power_w",
        "elevation_gain_m",
        "calories_kcal",
        SOURCES_KEY,
        # Written by the training-load pass.
        *LOAD_KEYS,
    }
)
"""Every frontmatter key fitdocs writes -- the published managed set (Req 6.2).

The frontmatter block of a generated document is tool-owned and rewritten in
full on every regeneration (Req 6.1), so this set is exactly the boundary
between "fitdocs will restore this" and "fitdocs will drop this": a key outside
it is *unmanaged*, is not preserved, and is named in a warning before it goes
(Req 6.3, :func:`unmanaged_keys`). It equals exactly the keys
:func:`fitdocs.render.frontmatter.build_frontmatter` can emit, union
:data:`LOAD_KEYS`; an anti-drift test pins the two together, failing the moment
a key is added to either side alone.
"""

# --- user-owned frontmatter keys: the effort tag (Req 1.1, 2.1) -------------

EFFORT_KEY: Final[str] = "effort"
"""Frontmatter key carrying the effort tag's kind (Req 2.1, 2.2)."""

EFFORT_DISTANCE_KEY: Final[str] = "effort_distance_m"
"""Frontmatter key carrying the official/certified course distance, metres."""

EFFORT_TIME_KEY: Final[str] = "effort_time_s"
"""Frontmatter key carrying the official/chip time, seconds."""

EFFORT_EVENT_KEY: Final[str] = "effort_event"
"""Frontmatter key carrying the event's name, ideally a quoted wikilink."""

EFFORT_KEYS: Final[tuple[str, ...]] = (
    EFFORT_KEY,
    EFFORT_DISTANCE_KEY,
    EFFORT_TIME_KEY,
    EFFORT_EVENT_KEY,
)
"""The effort tag's keys in documentation order; also problem-report order
(Req 2.1, 5.6)."""

USER_KEYS: Final[frozenset[str]] = frozenset(EFFORT_KEYS)
"""Every frontmatter key fitdocs preserves verbatim but never writes (Req 1.1,
1.2) -- the user-owned class, parallel to :data:`USER_REGIONS` for a region.
Disjoint with :data:`MANAGED_KEYS` (Req 1.1, 1.5): one test pins this set to
the exact frozenset of :data:`EFFORT_KEYS`, a second pins that it is disjoint
with :data:`MANAGED_KEYS` directly, and a third, the render-layer anti-drift
test, additionally pins that no key :func:`fitdocs.render.frontmatter.build_frontmatter`
can emit is in this set.
"""


class EffortKind(StrEnum):
    """The effort tag's closed kind vocabulary (Req 2.2).

    Matched exactly and case-sensitively against the ``effort`` frontmatter
    value; any other string is a malformed tag, never a fourth kind.
    """

    RACE = "race"
    TEST = "test"
    HARD = "hard"


@dataclass(frozen=True)
class EffortTag:
    """A well-formed effort tag (Req 2.1, 5.3).

    ``distance_m``, ``time_s``, and ``event`` are ``None`` when the page does
    not carry the corresponding key -- never a fabricated default (Req 5.3).
    """

    kind: EffortKind
    distance_m: float | None
    time_s: float | None
    event: str | None


@dataclass(frozen=True)
class EffortTagProblem:
    """One named defect in a malformed effort tag: which key, and why (Req 3.3)."""

    key: str
    detail: str


@dataclass(frozen=True)
class InvalidEffortTag:
    """A malformed effort tag (Req 3.1, 5.6).

    This type places no lower bound on ``problems`` itself: a hand-built
    empty instance constructs, and :meth:`describe` returns ``""`` for it.
    The reader that produces every real instance, :func:`effort_tag`, emits
    at least one problem whenever any rule fails, so an empty one does not
    arise in practice -- but nothing here enforces that (see
    ``.kiro/queue/2026-09-10-invalid-effort-tag-non-empty-unenforced.md``).
    """

    problems: tuple[EffortTagProblem, ...]

    def describe(self) -> str:
        """Render every problem as ``"key: detail"``, joined by ``"; "`` (Req 5.6).

        The one renderer every consumer of a malformed tag -- the ``check``
        finding, the ``sync``/``regen`` warning, and any downstream report --
        shares, so the same defect is described identically everywhere.
        """
        return "; ".join(
            f"{problem.key}: {problem.detail}" for problem in self.problems
        )


def _positive_finite_float(value: object) -> float | None:
    """Return ``value`` as a ``float`` when it is a positive finite real
    number, else ``None`` (Req 2.3, 5.2).

    Shared by D1 and T1 so the guard decision and the stored value can never
    disagree. Rejects ``bool`` (an ``int`` subclass), any non-numeric type,
    non-finite values, and non-positive values. An arbitrary-precision
    ``int`` too large to convert to ``float`` raises ``OverflowError`` from
    :func:`float`; that is caught here rather than propagated. Only
    ``OverflowError`` is caught, which covers every value the frontmatter
    parser can produce.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    if not math.isfinite(number) or not number > 0:
        return None
    return number


def effort_tag(
    frontmatter: Mapping[str, object] | None,
) -> EffortTag | InvalidEffortTag | None:
    """Read the effort tag from a document's parsed frontmatter (Req 1.3, 5.1).

    The one reader every consumer -- ``sync``, ``regen``, ``check``, and any
    downstream feature -- calls instead of parsing :data:`EFFORT_KEYS` itself
    (Req 5.4). Never raises (Req 5.2): ``frontmatter`` may be ``None`` (the
    absent value :func:`parse_frontmatter` returns for an unreadable
    document) or hold values of any shape.

    Returns exactly one of three outcomes:

    - ``None`` -- ``frontmatter`` is ``None``, or it is a mapping holding
      none of :data:`EFFORT_KEYS`. Untagged, not malformed (Req 1.3).
    - :class:`EffortTag` -- every effort key present passes its rule.
    - :class:`InvalidEffortTag` -- at least one key fails its rule.

    Six rules are applied in :data:`EFFORT_KEYS` order, at most one problem
    per key (the first failing rule for that key), so ``describe()`` and
    every reporter built on it name each offending key exactly once, in the
    same order (Req 5.6):

    - K1: ``effort`` must be present whenever any other effort key is
      present -- an orphan field is malformed, never read as untagged
      (Req 2.5).
    - K2: ``effort``'s value must be exactly one of ``race``, ``test``,
      ``hard``, matched case-sensitively (Req 2.2).
    - D1/T1: ``effort_distance_m`` and ``effort_time_s`` must each be an
      ``int`` or ``float`` that is not a ``bool``, finite, and strictly
      positive (Req 2.3). Python's ``bool`` is an ``int`` subclass, so it is
      rejected explicitly rather than read as ``0``/``1``. A string is never
      parsed into a number, however numeric it looks (Req 3.2).
    - D2: ``effort_distance_m`` requires ``effort_time_s`` to also be
      present; ``effort_time_s`` may stand alone (Req 2.4).
    - E1: ``effort_event`` must be a ``str`` whose stripped form is
      non-empty; stored exactly as written, never stripped (Req 2.6). An
      unquoted wikilink is read by YAML as a nested list rather than text,
      so that shape is reported here too, with a quoting hint (Req 3.7).

    Numeric fields are stored as ``float``; ``event`` is stored as written.
    Nothing is coerced, rounded, or defaulted (Req 3.2).
    """
    if frontmatter is None:
        return None
    if not any(key in frontmatter for key in EFFORT_KEYS):
        return None

    problems: list[EffortTagProblem] = []
    kind: EffortKind | None = None
    distance_m: float | None = None
    time_s: float | None = None
    event: str | None = None

    has_other_effort_key = any(
        key in frontmatter
        for key in (EFFORT_DISTANCE_KEY, EFFORT_TIME_KEY, EFFORT_EVENT_KEY)
    )
    if EFFORT_KEY not in frontmatter:
        if has_other_effort_key:
            problems.append(
                EffortTagProblem(
                    EFFORT_KEY,
                    "required whenever any other effort key is present; "
                    "expected one of race, test, hard",
                )
            )
    else:
        kind_value = frontmatter[EFFORT_KEY]
        if not isinstance(kind_value, str) or kind_value not in (
            EffortKind.RACE,
            EffortKind.TEST,
            EffortKind.HARD,
        ):
            problems.append(
                EffortTagProblem(
                    EFFORT_KEY,
                    "must be one of race, test, hard (exact, lowercase); "
                    f"got {kind_value!r}",
                )
            )
        else:
            kind = EffortKind(kind_value)

    if EFFORT_DISTANCE_KEY in frontmatter:
        distance_value = frontmatter[EFFORT_DISTANCE_KEY]
        distance_number = _positive_finite_float(distance_value)
        if distance_number is None:
            problems.append(
                EffortTagProblem(
                    EFFORT_DISTANCE_KEY,
                    f"must be a positive number of metres; got {distance_value!r}",
                )
            )
        elif EFFORT_TIME_KEY not in frontmatter:
            problems.append(
                EffortTagProblem(
                    EFFORT_DISTANCE_KEY,
                    "requires effort_time_s: a course distance is an "
                    "official result only together with its time",
                )
            )
        else:
            distance_m = distance_number

    if EFFORT_TIME_KEY in frontmatter:
        time_value = frontmatter[EFFORT_TIME_KEY]
        time_number = _positive_finite_float(time_value)
        if time_number is None:
            problems.append(
                EffortTagProblem(
                    EFFORT_TIME_KEY,
                    f"must be a positive number of seconds; got {time_value!r}",
                )
            )
        else:
            time_s = time_number

    if EFFORT_EVENT_KEY in frontmatter:
        event_value = frontmatter[EFFORT_EVENT_KEY]
        if not isinstance(event_value, str) or not event_value.strip():
            problems.append(
                EffortTagProblem(
                    EFFORT_EVENT_KEY,
                    "must be non-empty text; quote a wikilink, e.g. "
                    f'effort_event: "[[Boston Marathon 2024]]"; got {event_value!r}',
                )
            )
        else:
            event = event_value

    if problems:
        return InvalidEffortTag(problems=tuple(problems))
    if kind is None:
        # Structurally unreachable in the rules above: reaching here with no
        # problems recorded means EFFORT_KEY was absent while no other effort
        # key was present either, which the early absence check above already
        # returns None for. Kept as a guard against ever raising rather than
        # constructing an EffortTag with no kind, in keeping with Req 5.2.
        return None
    return EffortTag(kind=kind, distance_m=distance_m, time_s=time_s, event=event)


# --- provenance --------------------------------------------------------------

GENERATED_PREFIX: Final[str] = "<!-- fitdocs:generated"
"""The opening text of the HTML comment marking a file as fitdocs-written.

Both the per-document provenance stamp and the in-tree ownership declaration
start a line with this, so :func:`is_generated` answers "did fitdocs write
this?" for either (Req 3.6, 4.1). It is deliberately *not* a region marker:
:mod:`fitdocs.docmerge`'s grammar accepts only ``begin`` and ``end`` for a
marker's kind, so a ``generated`` comment reads as no region at all rather than
as a damaged one.
"""

DOC_BANNER: Final[str] = (
    f"{GENERATED_PREFIX}: everything outside the notes/workout/load regions is "
    "replaced on regeneration -- see this directory's AGENTS.md -->"
)
"""The one-line HTML-comment provenance banner every generated document carries.

Names the tool (via :data:`GENERATED_PREFIX`), states the regeneration
boundary, and points at the in-tree ownership declaration (Req 4.2). A single
constant, module-level string: it contains no tool version, no timestamp, no
uuid, and no machine-specific path, so it is identical between runs and between
releases (Req 4.5) and its equality with :data:`GENERATED_PREFIX`'s prefix is
what lets :func:`is_generated` recognize it. Placement -- outside every
preserved region, between the frontmatter block and the title -- is
:mod:`fitdocs.render.views`'s job, not this leaf's.
"""

# --- region ownership policy -------------------------------------------------

NOTES_REGION: Final[str] = "notes"
"""The user-owned region for free-form notes about the workout."""

WORKOUT_REGION: Final[str] = "workout"
"""The user-owned region recording the workout as actually performed."""

LOAD_REGION: Final[str] = "load"
"""The region the training-load pass fills; preserved across regeneration."""

USER_REGIONS: Final[tuple[str, ...]] = (NOTES_REGION, WORKOUT_REGION)
"""The regions a human authors; fitdocs writes only their initial placeholder."""

TOOL_REGIONS: Final[tuple[str, ...]] = (LOAD_REGION,)
"""The regions fitdocs itself fills after the document is first written."""

PRESERVED_REGIONS: Final[tuple[str, ...]] = USER_REGIONS + TOOL_REGIONS
"""Every region carried over verbatim on regeneration, in document order (1.4).

``("notes", "workout", "load")`` -- the order is contractual: it is the order
these regions appear in a rendered document and the order every enumeration of
them, published or internal, uses.
"""

# --- fresh-region content ----------------------------------------------------

NOTES_PLACEHOLDER: Final[str] = (
    "_Your notes go here. This section is preserved when the document is regenerated._"
)
"""The instructive placeholder a freshly rendered ``notes`` region carries."""

WORKOUT_PLACEHOLDER: Final[str] = (
    "_Record the workout you performed here -- exercises, sets, reps, and load. "
    "This section is preserved when the document is regenerated._"
)
"""The instructive placeholder a freshly rendered ``workout`` region carries."""

LOAD_NOT_COMPUTED: Final[str] = "_Training load not computed._"
"""The exact inner content of a freshly rendered ``load`` region.

Also the classifier the training-load editor compares against to recognize an
untouched placeholder: content equal to this string is fitdocs' own, anything
else is the user's. Having exactly one definition is what makes that comparison
safe, so both the renderer that emits it and the editor that recognizes it
import it from here.
"""

# --- pure readers ------------------------------------------------------------

_ARCHIVE_REF_PREFIX: Final[str] = "fit-archive/"
"""The data-root-relative directory every archive ref starts with.

Spelled here rather than imported from :mod:`fitdocs.layout`, which sits *above*
this leaf and would invert the dependency. ``sha_of_ref`` is the exact inverse
of ``layout.source_ref``, and a round-trip test pins the two together.
"""

_ARCHIVE_REF_SUFFIX: Final[str] = ".fit"
"""The extension every archive ref ends with."""

_HEX_DIGITS: Final[frozenset[str]] = frozenset("0123456789abcdefABCDEF")
"""The only characters a resolvable archive sha may contain."""

_SESSION_UUID_BYTE_COUNT: Final[int] = 16
"""A canonical UUID is exactly 16 bytes; any other length is malformed."""


def parse_frontmatter(text: str) -> dict[str, object] | None:
    """Parse a document's leading ``---``-fenced YAML frontmatter, or ``None``.

    Returns the parsed mapping only when ``text``'s *first* line is the fence
    (ignoring surrounding whitespace), a later line closes it, and the block
    between them parses to a YAML mapping. Everything else -- no leading fence,
    an unterminated block, YAML that fails to parse, or a block that parses to a
    sequence, a scalar, or nothing -- yields ``None``, which is every command's
    signal that this file is not a fitdocs document (Req 1.2). Never raises.

    Only the *first* closing fence terminates the block, so a ``---`` horizontal
    rule later in the body is body text, not a second frontmatter delimiter.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            block = "\n".join(lines[1:index])
            try:
                parsed = yaml.safe_load(block)
            except yaml.YAMLError:
                return None
            return parsed if isinstance(parsed, dict) else None
    return None


def frontmatter_close_index(lines: list[str]) -> int | None:
    """Index of the closing ``---`` fence, or ``None`` if there is no leading block.

    The line-level counterpart to :func:`parse_frontmatter`, for the editor that
    rewrites individual frontmatter lines rather than re-serializing the block.
    ``lines`` must be ``markdown.split("\\n")`` -- a *lossless* decomposition, so
    slicing around the returned index and re-joining with ``"\\n"`` reproduces
    the original bytes exactly. (``str.splitlines`` is not lossless and must not
    be used here: it would swallow a trailing newline and split on characters
    YAML treats as content.) Never raises.
    """
    if not lines or lines[0].strip() != FRONTMATTER_FENCE:
        return None
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_FENCE:
            return index
    return None


def user_owned_lines(lines: list[str]) -> tuple[str, ...]:
    """Every frontmatter line belonging to a user-owned entry, verbatim (Req
    2.6, 3.2, 4.4, 4.5, 5.5).

    ``lines`` must be ``markdown.split("\\n")`` -- the same lossless
    precondition as :func:`frontmatter_close_index`, which this function uses
    to find the block. A *top-level entry* starts at a line inside the fences
    whose first character is not whitespace, ``#`` or ``-`` and that contains
    ``:``; its key is the text before the first ``:``, stripped of whitespace
    and of one pair of matching surrounding quotes (``'`` or ``"``). Every
    following line up to the next entry start or the closing fence --
    indented lines, column-zero ``- `` list items, blank lines, comment lines
    -- belongs to that entry and is carried with it when the key is in
    :data:`USER_KEYS`.

    Returns ``()`` when there is no leading fence, the block is unterminated,
    or no user-owned entry exists. Never raises, parses no YAML, and
    validates nothing: a malformed tag's lines are carried exactly like a
    valid one's (Req 3.2, 4.4).
    """
    close_index = frontmatter_close_index(lines)
    if close_index is None:
        return ()
    carried: list[str] = []
    carrying = False
    for line in lines[1:close_index]:
        if line and line[0] not in (" ", "\t", "#", "-") and ":" in line:
            key = line.split(":", 1)[0].strip()
            if len(key) >= 2 and key[0] == key[-1] and key[0] in "'\"":
                key = key[1:-1]
            carrying = key in USER_KEYS
        if carrying:
            carried.append(line)
    return tuple(carried)


def is_workout_document(frontmatter: Mapping[str, object] | None) -> bool:
    """Whether parsed frontmatter identifies a fitdocs workout document (Req 1.1).

    ``None`` -- the absent value :func:`parse_frontmatter` returns for anything
    unreadable -- is accepted and answers ``False``, so a caller can compose the
    two without a separate guard. A page with no ``type``, or a ``type`` that is
    not exactly :data:`WORKOUT_TYPE`, is somebody else's file: it is skipped by
    every scan, identity match, regeneration, and training-load pass (Req 1.2,
    3.7).
    """
    return frontmatter is not None and frontmatter.get(TYPE_KEY) == WORKOUT_TYPE


def is_generated(text: str) -> bool:
    """Whether ``text`` carries fitdocs' provenance stamp (Req 3.6, 4.1).

    True when any line *starts* with :data:`GENERATED_PREFIX`. A line-scan rather
    than a first-line test because the stamp sits at the top of an in-tree
    ownership declaration but below the frontmatter block on a workout document,
    and one predicate answers for both. The match is anchored at column zero, so
    an indented lookalike -- inside a code block or a list item -- is content,
    not a claim of authorship.

    This is the guard that stops fitdocs overwriting a file it did not write: a
    declaration path occupied by an unstamped file is left alone and reported.
    """
    return any(line.startswith(GENERATED_PREFIX) for line in text.splitlines())


def document_uuid(frontmatter: Mapping[str, object]) -> str | None:
    """The document's recorded session identity, or ``None`` (Req 1.1, 1.3).

    The canonical UUID string under :data:`UUID_KEY`, present only for an
    activity that recorded a session identifier -- it is what converges every
    re-export of one activity onto one document, and it takes precedence over
    the source history when matching. A missing key, a non-string value, or an
    empty string is honest absence: the caller falls through to the source-history
    match rather than treating an empty value as an identity that could collide.
    """
    value = frontmatter.get(UUID_KEY)
    if isinstance(value, str) and value:
        return value
    return None


def document_version(frontmatter: Mapping[str, object]) -> int | None:
    """The document's recorded format version, or ``None`` if unusable (Req 5.7).

    Returns the value under :data:`DOC_VERSION_KEY` only when it is a *genuine*
    integer. ``bool`` subclasses ``int`` in Python, so ``True`` is rejected
    explicitly rather than silently read as version 1; a string, a float, or any
    other type is rejected too, because coercing one would invent a version the
    document does not state.

    The absent answer is ``None``, never ``0``: a document with no usable version
    is *out of date* (it predates versioning, or a user damaged the key) and is
    brought current by regeneration -- it must never read as newer (Req 5.7). A
    negative integer needs no special case: it is a genuine integer that compares
    below :data:`DOC_VERSION` and so reaches the same outcome.
    """
    value = frontmatter.get(DOC_VERSION_KEY)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def document_date(frontmatter: Mapping[str, object] | None) -> date | None:
    """The document's own recorded local calendar date, or ``None``.

    A cross-spec accessor (Amendment 3 of ``training-load``, consumed unchanged
    by ``athlete-benchmarks``): a calculator's per-activity context reaches the
    activity's own recorded date only through this function, never through an
    inline ``frontmatter.get("date")`` -- the same "every frontmatter read goes
    through the contract" invariant every other reader in this module holds.

    ``frontmatter`` accepts the *absent* value :func:`parse_frontmatter` returns
    for anything unreadable -- like :func:`is_workout_document`, ``None``
    composes directly rather than requiring a separate guard at every call site.

    :func:`~fitdocs.render.frontmatter.build_frontmatter` always emits ``date``
    as a *quoted* ISO ``YYYY-MM-DD`` string precisely so PyYAML never coerces it
    on read, so the ordinary case here parses a ``str`` with
    :meth:`date.fromisoformat`. A hand-edited document that leaves the value
    unquoted is read by PyYAML as a genuine :class:`datetime.date`, and that
    shape is accepted too -- it is exactly the value this function promises.
    A ``datetime`` is rejected explicitly even though it subclasses ``date``:
    it carries a time-of-day and a time zone this function never reads, the
    same discipline :func:`document_version` applies to ``bool`` subclassing
    ``int``. Anything else -- a missing key, an int, a float, a list, a
    malformed or empty string -- is honest absence, never a fabricated
    today (Req 9.1's "absent is never consent" discipline, applied to dates).
    """
    if frontmatter is None:
        return None
    value = frontmatter.get("date")
    if isinstance(value, datetime):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def source_refs(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
    """The document's ``sources`` history, in append order (Req 1.3).

    Each entry is a data-root-relative archive ref and the **last** entry is the
    current render source -- the one regeneration and the training-load pass
    resolve. A missing key, a non-list value, or an empty list yields ``()``;
    non-string entries in an otherwise usable list are dropped individually, so
    one hand-edited line degrades that entry rather than the whole history.
    """
    raw = frontmatter.get(SOURCES_KEY)
    if isinstance(raw, list):
        return tuple(item for item in raw if isinstance(item, str))
    return ()


def sha_of_ref(ref: str) -> str | None:
    """The sha256 embedded in a ``fit-archive/<sha>.fit`` ref, or ``None`` (1.3).

    The exact inverse of ``fitdocs.layout.source_ref``. The sha must be a
    non-empty run of hex digits and nothing else, so a ref that is foreign
    (another directory, another extension), empty, or traversal-shaped
    (``fit-archive/../secrets.fit``) resolves to ``None`` instead of to a path
    component. That matters because the caller joins the result onto the data
    root: an unvalidated ref from a hand-edited ``sources`` list would otherwise
    reach outside the archive. An unresolvable ref is not an error here -- the
    caller reports the document as having no regenerable source.
    """
    if not ref.startswith(_ARCHIVE_REF_PREFIX) or not ref.endswith(_ARCHIVE_REF_SUFFIX):
        return None
    sha = ref[len(_ARCHIVE_REF_PREFIX) : -len(_ARCHIVE_REF_SUFFIX)]
    if not sha or not all(char in _HEX_DIGITS for char in sha):
        return None
    return sha


def unmanaged_keys(frontmatter: Mapping[str, object]) -> tuple[str, ...]:
    """Frontmatter keys fitdocs neither manages nor a user owns (6.2, 6.3, 1.4).

    The frontmatter block of a generated document is tool-owned and rewritten in
    full, so any key outside :data:`MANAGED_KEYS` and :data:`USER_KEYS` is
    dropped by the next regeneration. Naming them is what turns that from
    silent data loss into a warning the user can act on (Req 6.3) and into an
    audit finding (Req 8.4). A user-owned key -- the effort tag's keys -- is
    never reported here (Req 1.4, 4.7): only a key in neither class is
    unmanaged. The verbatim carry that makes that exemption safe is
    :func:`user_owned_lines`, which the sync engine applies on every rewrite, so
    a user-owned key survives rather than being dropped.

    Non-string keys -- YAML permits them -- are ignored: fitdocs cannot name one
    in a warning, and it has never written one. Returns ``()`` for a fully
    managed document, including one that has had a training-load pass.
    """
    return tuple(
        sorted(
            {
                key
                for key in frontmatter
                if isinstance(key, str) and key not in MANAGED_KEYS | USER_KEYS
            }
        )
    )


def format_session_uuid(value: object) -> str | None:
    """Format a recorded ``SESSION UUID`` value as a canonical UUID string.

    Returns the lowercase ``8-4-4-4-12`` form (Req 1.1) only when ``value`` is
    exactly a 16-element tuple of ``int`` bytes in ``0..255`` -- the shape the
    ingest layer produces for the recorded identifier. Any other shape (wrong
    length, wrong element type, out-of-range byte, or a list, ``bytes``, or
    string rather than a tuple) is malformed and yields ``None`` so the caller
    omits the key. There is deliberately **no** sha256 fallback: the content-hash
    identity lives in ``sources``, and mixing the two would let a hash masquerade
    as a recorded session identifier.

    The checks fully guarantee that ``bytes(value)`` and the 16-byte
    ``uuid.UUID`` construction below cannot raise, so the never-raises contract
    holds without a try/except.
    """
    if not isinstance(value, tuple) or len(value) != _SESSION_UUID_BYTE_COUNT:
        return None
    for element in value:
        if not isinstance(element, int) or not 0 <= element <= 255:
            return None
    return str(uuid.UUID(bytes=bytes(value)))

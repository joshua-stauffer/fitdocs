"""The athlete profile store: the full lifecycle of ``athlete.toml`` (Req 2).

This module is authoritative for ``<data_root>/athlete.toml`` -- the single
profile file that holds tested max HR and the zone/threshold dividers a
methodology declares. workout-docs consumes the very same file *read-only*
for its zone and threshold rendering, so this store is bound by that read
contract: shared top-level keys keep their names and types, and every key or
table the store does not manage survives a rewrite verbatim (Req 2.5).

Three invariants shape the contract:

* **Absent is empty, never an error.** :func:`load_profile` of a missing file
  yields an empty :class:`AthleteProfile`, and reading never creates the file
  (Req 2.3). Lifecycle -- creation on the first persisted answer, reads, and
  validated updates -- is owned here (Req 2.1).

* **Loud, never lossy.** A file that exists but is not parseable TOML, or a
  value that is present but not a real number at an accessed key, raises
  :class:`ProfileError` naming the file and key (Req 2.4). Nothing is coerced,
  guessed, or silently dropped.

* **Only user-provided, validated values persist.** :meth:`AthleteProfile.with_value`
  validates against the declaring :class:`AthleteField`'s range and kind before
  storing, returns an updated *copy* (never mutating the original), and every
  :func:`save_profile` stamps :data:`fitdocs.athlete.ATHLETE_SCHEMA_VERSION` and
  writes atomically (Req 2.2, 2.6).

The critical serialization seam (Req 2.5): an ``int``-kind field is stored as a
Python ``int`` so ``tomli_w`` emits a bare TOML integer (``max_hr_bpm = 200``,
never ``200.0``). Because Python's ``bool`` is a subclass of ``int`` it is
rejected everywhere a number is required -- mirroring
:mod:`fitdocs.athlete`, the read-only reader whose strictness this store must
not break. Methodology-specific fields live in a table named after the
calculator id (``[mycalc] custom_threshold = 42``), addressed by the dotted
key ``"mycalc.custom_threshold"`` so fields from different calculators never
collide (Req 2.7).

A hand-edited TOML comment is lost on rewrite (tomllib parse -> mutate ->
``tomli_w`` dump preserves values, not comments) -- an accepted, documented
trade-off. Data values are never lost.
"""

from __future__ import annotations

import copy
import math
import os
import tempfile
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import date
from pathlib import Path
from typing import Final, cast

import tomli_w

from fitdocs import Sport
from fitdocs.athlete import (
    ATHLETE_SCHEMA_VERSION,
    VERSION_KEY,
    AthleteFileError,
    check_schema_version,
)
from fitdocs.benchmarks import (
    ATHLETE_SCOPE,
    ATHLETE_SCOPED,
    DISCIPLINE_SCOPED,
    INTEGRAL_KINDS,
    Benchmark,
    BenchmarkError,
    BenchmarkKind,
    BenchmarkSet,
    benchmarks_to_document,
    parse_benchmarks,
)
from fitdocs.load.types import AthleteField

__all__ = [
    "PROFILE_FILENAME",
    "AthleteProfile",
    "ProfileError",
    "load_profile",
    "save_profile",
]

PROFILE_FILENAME: Final[str] = "athlete.toml"
"""The profile file name in the data root -- the same file workout-docs reads."""


class ProfileError(AthleteFileError):
    """The ``athlete.toml`` file is unparseable or an accessed value is invalid.

    A subclass of :class:`fitdocs.athlete.AthleteFileError` so one file has one
    catchable voice: code that catches the athlete-inputs reader's error type
    also catches every profile-store failure, without knowing this module
    exists (Req 2.10).

    Raised for malformed TOML on load, for a present-but-non-numeric value at
    an accessed key (a boolean or a non-``int``/``float``), for a refused
    schema version, or for a malformed ``[benchmarks]`` region -- the last two
    are checked *eagerly*, at construction, so a broken store fails before
    anything else in a load pass is touched (Req 2.9, 2.10, 3.7). The message
    names the file and the offending key so the user can correct the
    configuration. An *absent* file is never an error -- it yields an empty
    profile instead (Req 2.3, 2.4).
    """


@dataclass(frozen=True)
class AthleteProfile:
    """An immutable, read-only view of a parsed ``athlete.toml`` document.

    Structurally implements :class:`fitdocs.load.types.ProfileView`. Numeric
    values are read by dotted key via :meth:`get_number`; updates go through
    :meth:`with_value`, which validates and returns a fresh copy without ever
    mutating this instance.

    Construction is eager (Req 1.1, 2.9, 2.10): ``__post_init__`` runs the
    schema-version guard and then parses the ``[benchmarks]`` region, so the
    raw ``data`` and the parsed :attr:`benchmarks` can never disagree --
    every mutation (:meth:`with_value`) builds a fresh document and hands it
    to a fresh instance, which re-parses on its own construction rather than
    inheriting a stale parse. A parser domain error is re-raised as
    :class:`ProfileError` naming the file, so a malformed store fails at
    construction time -- before a caller can query or persist anything.
    """

    data: Mapping[str, object]
    """The parsed TOML document. Treated as read-only; never mutated in place."""

    benchmarks: BenchmarkSet = dataclass_field(init=False, compare=False)
    """The ``[benchmarks]`` region of :attr:`data`, parsed eagerly at
    construction (Req 1.1, 2.9). Never set directly; always derived from
    ``data`` in :meth:`__post_init__` so the two can never disagree."""

    def __post_init__(self) -> None:
        path = Path(PROFILE_FILENAME)
        check_schema_version(self.data, path)
        try:
            benchmarks = parse_benchmarks(self.data)
        except BenchmarkError as exc:
            raise ProfileError(f"{path}: {exc}") from exc
        object.__setattr__(self, "benchmarks", benchmarks)

    def benchmark(
        self, kind: BenchmarkKind, *, discipline: Sport | None, on: date | None
    ) -> Benchmark | None:
        """Return the benchmark applicable to an activity dated ``on`` (Req 7.1).

        ``on`` is the *activity's own* date, an explicit argument -- the store
        holds no bound date and never assumes today's. When ``on`` is ``None``
        (an undated activity -- e.g. a document with no parseable date) this
        returns ``None`` unconditionally: an undated activity has no
        applicable benchmark, regardless of what is on file (Req 3.7, 9.5).
        Otherwise delegates to
        :meth:`fitdocs.benchmarks.BenchmarkSet.applicable`, which -- absent an
        athlete-declared exception -- never returns an entry measured after
        ``on``; the one exception (*Amendment 1*, athlete-benchmarks 3.10)
        is an entry whose own ``applies_from`` reaches back to or before
        ``on``, which the athlete recorded explicitly via
        :meth:`AthleteProfile.with_benchmark`'s ``applies_from`` -- this
        method itself never applies a later measurement on its own.
        """
        if on is None:
            return None
        return self.benchmarks.applicable(kind, discipline=discipline, on=on)

    def has_benchmark(self, kind: BenchmarkKind, *, discipline: Sport | None) -> bool:
        """Report whether any benchmark of ``kind``/``discipline`` is on file at
        all, ignoring dates entirely (Req 7.2) -- so a caller can separate "none
        on file" from "none applicable yet" (the latter is :meth:`benchmark`
        returning ``None`` while this returns ``True``).
        """
        return self.benchmarks.has(kind, discipline=discipline)

    def get_number(self, key: str) -> float | None:
        """Return the numeric value at ``key`` (dotted for scoped tables), or ``None``.

        ``key`` is split on ``"."`` and the mapping is traversed
        (``"mycalc.custom_threshold"`` -> ``data["mycalc"]["custom_threshold"]``;
        ``"max_hr_bpm"`` ->
        top-level). An absent key or an un-traversable path yields ``None`` --
        never an error, never a fabricated default (Req 2.4, 2.7).

        If the addressed value *is* present but is not a real number -- a
        ``bool`` (rejected even though ``bool`` subclasses ``int``) or any
        non-``int``/``float`` -- a :class:`ProfileError` naming the key is
        raised. This is the loud config-error path of Req 2.4.
        """
        node: object = self.data
        for part in key.split("."):
            if not isinstance(node, Mapping) or part not in node:
                return None
            node = node[part]
        if isinstance(node, bool) or not isinstance(node, (int, float)):
            raise ProfileError(
                f"{PROFILE_FILENAME}: {key!r} must be a number, "
                f"got {node!r} ({type(node).__name__})"
            )
        return float(node)

    def with_value(self, field: AthleteField, value: float) -> AthleteProfile:
        """Return a new profile with ``field`` set to a validated ``value``.

        ``value`` is validated against ``field`` before anything is stored:
        inclusive ``minimum``/``maximum`` bounds when set, and -- for
        ``kind == "int"`` -- an integral value stored as a Python ``int`` (so it
        serializes as a bare TOML integer); ``kind == "float"`` stores a
        ``float``. A ``bool`` is rejected outright. On any violation a
        :class:`ValueError` is raised and nothing is stored (Req 2.6).

        The returned profile's ``data`` is a deep copy of this one's with the
        value set at ``field.key``'s dotted path -- creating the methodology
        sub-table if absent -- and every other key and table preserved verbatim
        (Req 2.5, 2.7). This instance is never mutated.
        """
        stored = _validate(field, value)
        document = copy.deepcopy(dict(self.data))
        _set_dotted(document, field.key, stored)
        return AthleteProfile(data=document)

    def with_benchmark(
        self,
        kind: BenchmarkKind,
        *,
        discipline: Sport | None,
        value: float,
        measured_on: date,
        note: str | None = None,
        applies_from: date | None = None,
    ) -> AthleteProfile:
        """Return a new profile with one dated benchmark measurement recorded.

        ``discipline`` must agree with ``kind``'s scope -- ``None`` exactly for
        an athlete-wide quantity, an explicit :class:`~fitdocs.Sport` for a
        discipline-scoped one; a mismatch raises :class:`ValueError` and
        stores nothing (Req 6.9). ``value`` is validated before anything is
        stored -- finite, positive, and (for a beats-per-minute quantity) a
        whole number -- and any violation likewise raises :class:`ValueError`
        with nothing stored (Req 6.9). ``applies_from`` (*Amendment 1*, Req
        6.10) is the athlete's own declaration that this measurement also
        stands in for activities dated on or after ``applies_from`` that no
        earlier-measured entry covers; a value falling *after* ``measured_on``
        is refused with :class:`ValueError`, in the same voice as the scope
        and value refusals above, and nothing is stored (Req 6.10).
        ``applies_from == measured_on`` is accepted and behaves as if omitted.

        The entry is keyed by ``(discipline, kind, measured_on)`` (Req 1.5):
        an existing entry with the same key is *replaced*, never duplicated
        (Req 6.3). Every other key and table -- including any other
        benchmark history and the flat athlete-input keys -- survives on the
        returned profile's ``data``, a deep copy of this instance's (Req
        6.4); this instance is never mutated. Content :func:`parse_benchmarks`
        deliberately ignores for forward compatibility (Req 1.10) -- an
        unrecognized quantity table under a recognized discipline, and an
        unrecognized key inside a recognized entry table -- also survives:
        the newly built entries are *merged* into the existing region via
        :func:`_merge_benchmarks_document`, per ``(scope, kind, measured_on)``,
        never substituted wholesale for it. The new entries are built by
        :func:`fitdocs.benchmarks.benchmarks_to_document` (never hand-assembled
        here) and land date-sorted (Req 6.6). The merge base is keyed by the
        parser's canonical scope identity, never the raw on-disk spelling
        (:func:`_canonicalize_benchmarks_region`), and :func:`save_profile`
        additionally re-parses the assembled document before writing it --
        together these are what make "the writer cannot emit a shape the
        reader would reject" true, not merely asserted; the guarantee is
        enforced there, not by this method alone. No flat threshold key is
        written by this method (Req 6.8). Omitting ``applies_from`` on a
        same-date rewrite (leaving it ``None``) never erases an
        ``applies_from`` already on file for that ``measured_on`` -- overlaid,
        not replaced, exactly as ``note`` (Req 6.4, 6.10); see
        :func:`_merge_benchmarks_document`.
        """
        _check_benchmark_scope(kind, discipline)
        stored_value = _validate_benchmark_value(kind, value)
        _check_benchmark_applies_from(applies_from, measured_on)

        key = (discipline, kind, measured_on)
        entries = [
            entry
            for entry in self.benchmarks.entries
            if (entry.discipline, entry.kind, entry.measured_on) != key
        ]
        entries.append(
            Benchmark(
                kind=kind,
                discipline=discipline,
                value=stored_value,
                measured_on=measured_on,
                note=note,
                applies_from=applies_from,
            )
        )

        document = copy.deepcopy(dict(self.data))
        document["benchmarks"] = _merge_benchmarks_document(
            _existing_benchmarks_region(self.data), entries
        )
        return AthleteProfile(data=document)


def load_profile(data_root: Path) -> AthleteProfile:
    """Read ``<data_root>/athlete.toml`` into an :class:`AthleteProfile`.

    An absent file yields an empty profile and creates nothing (Req 2.3). A file
    that exists but is not valid TOML raises :class:`ProfileError` naming the
    file (Req 2.4). Individual values are *not* eagerly validated here -- the
    per-accessed-key numeric check lives in :meth:`AthleteProfile.get_number`.
    """
    path = data_root / PROFILE_FILENAME
    if not path.is_file():
        return AthleteProfile(data={})

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ProfileError(f"{path} is not valid TOML: {exc}") from exc

    return AthleteProfile(data=data)


def save_profile(data_root: Path, profile: AthleteProfile) -> None:
    """Persist ``profile`` to ``<data_root>/athlete.toml`` atomically.

    ``profile_version`` is stamped/overwritten to
    :data:`fitdocs.athlete.ATHLETE_SCHEMA_VERSION` in the written document (Req
    2.2, 6.5); every other key and table is written verbatim, so unmanaged
    data -- including the flat athlete-input keys -- survives (Req 2.5, 6.4).
    The file is created if absent -- the first persisted answer (Req 2.1).

    Any recorded benchmarks are re-emitted through
    :func:`fitdocs.benchmarks.benchmarks_to_document`, which groups by scope
    and quantity and orders each group by ascending measurement date (Req
    6.6) -- so the written file is canonical even when ``profile.data`` was
    assembled by hand, bypassing :meth:`AthleteProfile.with_benchmark`
    entirely; this save path re-sorts independently of that method, and is
    tested directly rather than only through it. The freshly emitted groups
    are *merged* into the existing ``benchmarks`` region via
    :func:`_merge_benchmarks_document`, not substituted for it wholesale, so
    content :func:`parse_benchmarks` deliberately ignores for forward
    compatibility (Req 1.10) survives too (Req 6.4). A profile with no
    benchmarks at all leaves the document without a ``benchmarks`` table,
    rather than writing an empty one no caller asked for.

    Before anything is touched on disk, the assembled ``document`` is run
    back through :func:`fitdocs.benchmarks.parse_benchmarks`: this is a
    structural check backing the "the writer cannot emit a shape the reader
    would reject" property, not merely an assertion of it. No caller in this
    codebase can reach this function with ``profile.data`` and
    ``profile.benchmarks`` already disagreeing -- every production
    :class:`AthleteProfile` is built via ``AthleteProfile(data=...)``, whose
    ``__post_init__`` derives ``benchmarks`` from that same ``data`` (see the
    class docstring and :func:`AthleteProfile.__post_init__`), so the two
    fields are equal by construction for anything this module itself
    assembles. What this re-parse actually guards is the divergence
    :func:`_canonicalize_benchmarks_region` names in its own docstring: that
    function reimplements :func:`fitdocs.benchmarks._resolve_scope`'s
    case-insensitive scope rule in a second module, so if ``benchmarks.py``
    ever adds a scope alias this module would not know it, and the
    canonicaliser would leave the aliased spelling unfolded -- an assembled
    document this re-parse is what turns into a loud, pre-write failure
    rather than a silent one. It does **not** backstop a same-date
    collision inside an unrecognized-kind fold in
    :func:`_canonicalize_benchmarks_region`: that fold's output is never
    re-inspected by this re-parse for content under a quantity name
    :func:`fitdocs.benchmarks.parse_benchmarks` does not recognize, because
    the parser itself skips entries under an unrecognized quantity name
    entirely rather than validating them (Req 1.10) -- see
    :func:`_canonicalize_benchmarks_region` for that accepted gap. A
    rejection this check does catch raises :class:`ProfileError` naming the
    target and the underlying :class:`~fitdocs.benchmarks.BenchmarkError`
    *before* ``mkstemp`` runs, so a refused save leaves the target file
    exactly as it was (Req 6.7, 6.9) -- strictly stronger than atomicity,
    which only promises no partial write once one has started.

    The write is atomic: the document is written to a temporary file in the
    *same* directory as the target, then :func:`os.replace` renames it over the
    target (a same-filesystem atomic rename). The temporary file is removed if
    anything fails, so no partial or ``.tmp`` file is ever left behind.
    """
    target = data_root / PROFILE_FILENAME
    document = copy.deepcopy(dict(profile.data))
    if profile.benchmarks.entries:
        document["benchmarks"] = _merge_benchmarks_document(
            _existing_benchmarks_region(profile.data), profile.benchmarks.entries
        )
    document[VERSION_KEY] = ATHLETE_SCHEMA_VERSION

    try:
        parse_benchmarks(document)
    except BenchmarkError as exc:
        raise ProfileError(
            f"refusing to write {target}: the assembled document would not "
            f"be readable back: {exc}"
        ) from exc

    data_root.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=data_root, prefix=".athlete-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            tomli_w.dump(document, handle)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _existing_benchmarks_region(data: Mapping[str, object]) -> Mapping[str, object]:
    """Return ``data["benchmarks"]`` narrowed to a ``Mapping``, or ``{}`` if absent.

    ``AthleteProfile.__post_init__`` already ran :func:`parse_benchmarks`
    against ``data``, which raises unless an existing ``benchmarks`` key is
    itself a table -- so this narrowing cannot fail for a value that reached
    this point; it exists purely to give the type checker a concrete
    ``Mapping`` rather than ``object``.
    """
    region = data.get("benchmarks", {})
    return region if isinstance(region, Mapping) else {}


def _canonicalize_benchmarks_region(
    existing: Mapping[str, object],
) -> dict[str, object]:
    """Rebuild ``existing`` keyed by each scope's canonical spelling.

    The merge base for :func:`_merge_benchmarks_document` must be keyed by
    the parser's canonical identity at every level of the key path where the
    parser's resolution is non-injective -- never by the raw on-disk
    spelling. Today that is the scope level only:
    :func:`fitdocs.benchmarks._resolve_scope` maps a scope name to a
    :class:`~fitdocs.Sport` (or the reserved athlete-wide token)
    case-insensitively, so ``"Run"`` and ``"run"`` are the same identity to
    the reader even though they are different keys on disk. Building the
    merge base as a bare deep copy of ``existing`` -- keyed by whatever
    spelling happens to be on disk -- let a fresh write under the parser's
    one canonical spelling (:func:`fitdocs.benchmarks.benchmarks_to_document`
    always emits the lowercase form) sit *alongside* an old entry under a
    different-cased spelling that resolves to the same identity, so every
    entry the fresh write covers was silently emitted twice under two scope
    tables :func:`fitdocs.benchmarks.parse_benchmarks` treats as one --
    which then rejects the result as a duplicate ``(discipline, kind,
    measured_on)``. This function closes that at the source: each existing
    scope key is lowercased and treated as canonical only when the lowercase
    form is a recognized scope spelling (a :class:`~fitdocs.Sport` value or
    the reserved ``athlete`` token); an unrecognized key is left alone
    (:func:`fitdocs.benchmarks.parse_benchmarks` would reject it either way,
    so there is nothing to fold).

    This *renames* a table inside the region this store manages -- the same
    normalisation Req 6.6 already mandates for entry order, not the "key the
    store does not manage" Req 6.4 protects. When two folded spellings carry
    different values for the *same* quantity (``kind``) key this function
    never silently picks one: it either merges the two automatically (the
    one case that can be merged without loss) or refuses loudly with
    :class:`ProfileError`, naming both raw spellings and the key, so the
    values a caller must reconcile by hand are never lost by an arbitrary
    last-spelling-wins pick.

    The one mergeable case is two raw ``[[..]]`` entry arrays: they are
    concatenated rather than one replacing the other. For a *recognized*
    kind this is harmless regardless of any date overlap, because the
    caller's fresh entries (built from the full, already-deduplicated
    :class:`~fitdocs.benchmarks.BenchmarkSet`) are what
    :func:`_merge_benchmarks_document` actually overlays onto the result, one
    entry per date; for an *unrecognized* kind -- content
    :func:`fitdocs.benchmarks.parse_benchmarks` deliberately never
    inspects (1.10) -- nothing rebuilds it, so dropping either spelling's
    list here would silently lose data, and concatenating is the only choice
    that keeps both. Concatenation does not itself deduplicate by date: a
    same-date collision inside an unrecognized kind's folded lists (both
    spellings having independently recorded an entry on the same day) is
    real forward-compatible data neither this function nor
    :func:`_merge_benchmarks_document` can arbitrate -- and, because
    :func:`fitdocs.benchmarks.parse_benchmarks` skips entries under an
    unrecognized quantity name entirely rather than validating them, that
    collision reaches disk and reloads cleanly; :func:`save_profile`'s
    re-parse does **not** catch it, and nothing in this module does. This is
    an accepted gap for content this store cannot interpret, not a silent
    loss of a value the store itself manages -- unlike the non-list case
    above, which this function does refuse.

    Any other collision -- a scalar or a table value on either side -- is
    not something this function can arbitrate at all, and raises rather
    than losing one side (see above).

    Divergence risk: this reimplements
    :func:`fitdocs.benchmarks._resolve_scope`'s case rule in a second
    module. If ``benchmarks.py`` ever adds an alias (e.g. ``bike`` ->
    ``Ride``) this function would not know it, and would leave such a key
    unfolded; :func:`save_profile`'s re-parse (not this function) is what
    turns that mismatch into a loud failure rather than a silent one. A
    public helper on :mod:`fitdocs.benchmarks` would remove the duplication
    entirely; adding one is out of this module's boundary.
    """
    canonical_scopes = {ATHLETE_SCOPE, *(sport.value.lower() for sport in Sport)}
    canonicalized: dict[str, dict[str, object]] = {}
    origin_scope: dict[tuple[str, str], object] = {}
    for scope_key, scope_table in copy.deepcopy(dict(existing)).items():
        lowered = str(scope_key).lower()
        canonical_key = lowered if lowered in canonical_scopes else str(scope_key)
        target = canonicalized.setdefault(canonical_key, {})
        if not isinstance(scope_table, Mapping):
            continue
        for kind_key, kind_entries in scope_table.items():
            if kind_key not in target:
                target[kind_key] = kind_entries
                origin_scope[(canonical_key, kind_key)] = scope_key
                continue
            prior = target[kind_key]
            if _is_entry_list(prior) and _is_entry_list(kind_entries):
                target[kind_key] = [
                    *cast("Sequence[object]", prior),
                    *cast("Sequence[object]", kind_entries),
                ]
                continue
            first_spelling = origin_scope[(canonical_key, kind_key)]
            raise ProfileError(
                f"{PROFILE_FILENAME}: benchmarks.{first_spelling}.{kind_key} and "
                f"benchmarks.{scope_key}.{kind_key} both define a value for "
                f"{kind_key!r} that this store cannot merge automatically "
                "(at least one side is not a raw entry array) -- merge the "
                "two tables by hand in the file"
            )
    return cast("dict[str, object]", canonicalized)


def _is_entry_list(value: object) -> bool:
    """Report whether ``value`` is a raw ``[[..]]`` entry-array shape."""
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes))


def _merge_benchmarks_document(
    existing: Mapping[str, object], entries: Sequence[Benchmark]
) -> dict[str, object]:
    """Merge freshly emitted benchmark entries into ``existing`` verbatim (Req 6.4).

    :func:`fitdocs.benchmarks.benchmarks_to_document` rebuilds every
    ``(scope, kind)`` group that ``entries`` covers -- everything
    :func:`fitdocs.benchmarks.parse_benchmarks` *recognizes*. Assigning that
    output as the whole ``benchmarks`` region (as this module once did)
    silently deletes anything the parser deliberately left alone for forward
    compatibility (1.10): an unrecognized quantity table under a recognized
    discipline, and any unrecognized key inside an entry table. This
    function instead starts from :func:`_canonicalize_benchmarks_region` of
    ``existing`` -- never a bare deep copy keyed by the raw on-disk spelling,
    which would let a scope resolve many-to-one at read time while this
    module wrote it one-to-many -- and, within each ``(scope, kind)`` group
    the fresh entries cover, merges *per entry* keyed by ``measured_on``: an
    existing raw entry table at that date is preserved and only its
    recognized fields (``value``, ``measured_on``, ``note``, and -- *Amendment
    1* -- ``applies_from``) are overlaid with the freshly validated ones, so
    an unrecognized key on that entry (e.g. a ``source`` a future feature
    wrote) survives even when the entry's value is the one being replaced. A
    ``measured_on`` with no prior raw entry (a genuinely new date) has
    nothing to inherit and is emitted as freshly built. Every scope key and
    every unrecognized kind key the fresh groups do not cover is left
    untouched entirely (Req 6.4, 1.10).

    One accepted consequence of overlay-not-replace: if a later
    :meth:`AthleteProfile.with_benchmark` call omits ``note`` (leaving it
    ``None``) for a ``measured_on`` that already carries a ``note``, the old
    ``note`` is *not* cleared -- ``None`` here means "not supplied", not
    "erase", consistent with this store never deleting data a caller did
    not explicitly ask to remove. ``applies_from`` behaves identically (Req
    6.10): :func:`fitdocs.benchmarks.benchmarks_to_document` omits the
    ``applies_from`` key from a fresh entry's record entirely when the
    ``Benchmark`` it was built from carries ``None``, so ``combined.update``
    below leaves an existing raw ``applies_from`` at that ``measured_on``
    untouched rather than overwriting it with an absence; a fresh entry that
    *does* carry one overlays it exactly as a fresh ``note`` would.
    """
    merged: dict[str, object] = _canonicalize_benchmarks_region(existing)
    new_region = cast(
        "Mapping[str, Mapping[str, Sequence[Mapping[str, object]]]]",
        benchmarks_to_document(entries)["benchmarks"],
    )
    for scope_key, kind_table in new_region.items():
        existing_scope_raw = merged.get(scope_key)
        existing_scope: dict[str, object] = (
            dict(existing_scope_raw) if isinstance(existing_scope_raw, Mapping) else {}
        )
        for kind_key, fresh_entries in kind_table.items():
            existing_kind_raw = existing_scope.get(kind_key)
            existing_by_date: dict[object, Mapping[str, object]] = {}
            if isinstance(existing_kind_raw, Sequence) and not isinstance(
                existing_kind_raw, (str, bytes)
            ):
                for raw_entry in existing_kind_raw:
                    if isinstance(raw_entry, Mapping):
                        existing_by_date[raw_entry.get("measured_on")] = raw_entry

            merged_entries: list[dict[str, object]] = []
            for fresh_entry in fresh_entries:
                original = existing_by_date.get(fresh_entry.get("measured_on"))
                combined: dict[str, object] = (
                    dict(original) if original is not None else {}
                )
                combined.update(fresh_entry)
                merged_entries.append(combined)
            existing_scope[kind_key] = merged_entries

        merged[scope_key] = existing_scope
    return merged


def _check_benchmark_scope(kind: BenchmarkKind, discipline: Sport | None) -> None:
    """Enforce :meth:`AthleteProfile.with_benchmark`'s scope precondition (Req 6.9).

    Mirrors the athlete-scoped/discipline-scoped distinction
    :mod:`fitdocs.benchmarks` enforces on a parsed *file* entry, but here the
    mismatch is the mutation *caller's* error, not malformed data on disk --
    so this raises the plain :class:`ValueError` this module's ``with_value``
    already uses for a caller-supplied violation, never
    :class:`~fitdocs.benchmarks.BenchmarkError`, and nothing is stored.
    """
    if kind in ATHLETE_SCOPED and discipline is not None:
        raise ValueError(
            f"{kind.value} is an athlete-wide quantity; record it with "
            f"discipline=None, not discipline={discipline!r}"
        )
    if kind in DISCIPLINE_SCOPED and discipline is None:
        raise ValueError(
            f"{kind.value} is a discipline-scoped quantity; record it with an "
            f"explicit discipline, not discipline=None"
        )


def _check_benchmark_applies_from(applies_from: date | None, measured_on: date) -> None:
    """Enforce :meth:`AthleteProfile.with_benchmark`'s ``applies_from`` precondition
    (*Amendment 1*, Req 6.10).

    Mirrors the bare-date-order rule
    :func:`fitdocs.benchmarks._validate_applies_from` enforces on a parsed
    *file* entry, but here a value falling after ``measured_on`` is the
    mutation *caller's* error, not malformed data on disk -- so this raises
    the plain :class:`ValueError` this module already uses for a
    caller-supplied violation (mirroring :func:`_check_benchmark_scope` and
    :func:`_validate_benchmark_value`), never
    :class:`~fitdocs.benchmarks.BenchmarkError`, and nothing is stored.
    ``applies_from is None`` (not supplied) and ``applies_from ==
    measured_on`` are both accepted.
    """
    if applies_from is not None and applies_from > measured_on:
        raise ValueError(
            f"applies_from ({applies_from.isoformat()}) must not fall after "
            f"measured_on ({measured_on.isoformat()})"
        )


def _validate_benchmark_value(kind: BenchmarkKind, value: float) -> int | float:
    """Validate a benchmark ``value`` before it is stored (Req 6.9).

    Rejects a ``bool`` (never a number), a non-finite or non-positive value,
    and -- for an :data:`~fitdocs.benchmarks.INTEGRAL_KINDS` quantity -- a
    fractional value, returning a Python ``int`` for those so the entry
    round-trips through :func:`~fitdocs.benchmarks.benchmarks_to_document` and
    ``tomli_w`` as a bare TOML integer rather than a synthetic float. For
    every other kind ``value`` is returned unchanged (never coerced through
    ``float()``), mirroring
    :func:`fitdocs.benchmarks._validate_value`'s own contract of
    round-tripping whatever numeric type the caller supplied -- ``260``
    stored as ``260``, never a synthetic ``260.0`` -- so this write path and
    the parser agree on identical input (Req 9.3).

    Raises :class:`ValueError` -- deliberately, not :class:`ProfileError` --
    mirroring this module's own ``with_value``/``_validate`` convention for a
    caller-supplied violation: the caller of ``with_benchmark`` gets the same
    error type at the point it supplies a bad value, before anything is
    written, rather than learning of it only from the eager re-parse
    ``AthleteProfile.__post_init__`` performs on construction. That re-parse
    still runs as a second net -- it does not become the primary check.
    """
    if isinstance(value, bool):
        raise ValueError(f"{kind.value}: a boolean is not a valid benchmark value")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{kind.value} value must be a finite number, got {value!r}")
    if numeric <= 0:
        raise ValueError(f"{kind.value} value must be a positive number, got {value!r}")
    if kind in INTEGRAL_KINDS:
        if not numeric.is_integer():
            raise ValueError(
                f"{kind.value} value must be a whole number of beats per "
                f"minute, got {value!r}"
            )
        return int(numeric)
    return value


def _validate(field: AthleteField, value: float) -> int | float:
    """Validate ``value`` against ``field`` and return the value to store.

    Rejects a ``bool`` (never a number), enforces the inclusive range bounds,
    and for an ``int``-kind field requires an integral value and returns a
    Python ``int`` so it serializes as a bare TOML integer. Any violation raises
    :class:`ValueError` and nothing is stored (Req 2.6).
    """
    if isinstance(value, bool):
        raise ValueError(
            f"{field.label} ({field.key}): a boolean is not a valid number"
        )
    if field.minimum is not None and value < field.minimum:
        raise ValueError(
            f"{field.label} ({field.key}) must be >= {field.minimum}, got {value}"
        )
    if field.maximum is not None and value > field.maximum:
        raise ValueError(
            f"{field.label} ({field.key}) must be <= {field.maximum}, got {value}"
        )
    if field.kind == "int":
        if not float(value).is_integer():
            raise ValueError(
                f"{field.label} ({field.key}) must be a whole number, got {value}"
            )
        return int(value)
    return float(value)


def _set_dotted(document: dict[str, object], key: str, value: int | float) -> None:
    """Set ``value`` at ``key``'s dotted path in ``document``, creating tables.

    Intermediate segments that are missing (or not a table) are replaced with a
    fresh table, so ``"mycalc.custom_threshold"`` lands under ``[mycalc]`` as
    ``custom_threshold`` (Req 2.7). Existing sibling keys and tables are left
    untouched.
    """
    parts = key.split(".")
    node = document
    for part in parts[:-1]:
        child = node.get(part)
        if isinstance(child, dict):
            node = child
        else:
            fresh: dict[str, object] = {}
            node[part] = fresh
            node = fresh
    node[parts[-1]] = value

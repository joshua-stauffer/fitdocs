"""The load pass: scan, resolve, orchestrate, write, report (design: LoadEngine).

This module is the one place that owns document I/O for the load layer. A single
entry point, :func:`apply_load`, walks the workout documents in a data root and,
per document in isolation, either **restores** the load frontmatter from a
preserved payload (no recomputation, no prompting), **computes** a fresh result
(resolve the archived source, parse it, compute metrics, select a supporting
calculator, collect declared fields, apply the outcome), writes the honest
**unsupported** state when no calculator supports the sport, records a
**skip** with a reason (missing inputs / declined / non-interactive), or records
a **failure** (missing/unparseable archive, damaged markers) -- and it never
aborts the pass on a per-document error (Req 8.5, 9.3).

Three properties make the pass trustworthy:

* **Configuration vs per-document errors.** The athlete file, the profile, the
  resolved ``[load]`` table, and a requested ``--calculator`` id (forced or
  configured as ``default_calculator``) are all validated up front, before the
  document scan; a malformed profile, a malformed ``[load]`` table, or an
  unknown calculator id (``AthleteFileError`` / ``ProfileError`` /
  ``SettingsError`` / ``LoadSettingsError`` / ``UnknownCalculatorError``)
  propagates and aborts the pass (exit 2 at the CLI, matching ``fitdocs
  sync``). Everything else that can go wrong for one document is isolated into
  a ``failures`` entry, that document left byte-identical.

* **Atomic, whole-document writes.** Every write is a temp-file-then-``os.replace``
  swap in the document's own directory, so a document is either its old bytes or
  its new bytes -- never a partial write. A repeated identical pass performs no
  writes at all: restore finds no drift, a computed region is never re-entered
  without ``--recompute``, and an already-unsupported region is a no-op.

* **Fully offline.** The pass reads only the documents, their archived sources,
  the athlete profile, and its own resolved ``[load]`` configuration (Req 8.7)
  -- no network, no other I/O. This feature registers no built-in calculator of
  its own (Req 13.2): the registry is populated only by a plugin author or a
  downstream methodology spec calling :func:`fitdocs.load.registry.register`.
  The engine addresses calculators only through the registry and
  :mod:`fitdocs.load.arbitrate`, so it stays calculator-agnostic (it reads the
  additive ``athlete_field_hints`` seam generically via ``getattr``).

**One document interpretation (design: DocumentContract).** Every read of a
document's frontmatter -- the fence, the ``type`` marker, the parse, and the
``sources`` history -- goes through :mod:`fitdocs.contract`, which holds the only
definition of each. The load pass therefore recognizes exactly the documents the
sync engine and the audit recognize, and resolves exactly the same archived
source for each (wiki-contract Req 1.1, 1.3). The contract is a pure leaf that
never touches the filesystem, so *interpreting* a document is the contract's
job; the actual filesystem read -- including the symlink refusal every scanner
shares -- is :mod:`fitdocs.docio`'s (wiki-contract task 7.2), not this
module's: :func:`_discover_workout_docs` below just calls it.

**Document-format version gate (wiki-contract Req 5.5, 5.8).** ``sync`` and
``regen`` refuse to rewrite a document whose recorded ``doc_version`` is
strictly newer than :data:`fitdocs.contract.DOC_VERSION` (task 5.1) -- but
that refusal alone does not protect the document end-to-end, because both CLI
commands run this pass immediately afterward over *every* workout document in
the data root, not only the ones they just wrote. Before doing anything else
with a document, :func:`_process_document` here reads the same
:func:`fitdocs.contract.document_version` and, when it is strictly newer,
leaves the document completely untouched -- restoring nothing, computing
nothing, writing no honest-unsupported state into its ``load`` region -- and
reports it *skipped* with a reason naming the version, exactly mirroring the
sync engine's own gate and its "skipped is not a completion signal" rule (Req
5.9). Without this, a version-gated document's frontmatter/body/regions would
be left alone by the document rewrite while its ``load`` region and three
load keys were rewritten anyway by this pass -- Req 5.5's "left unchanged"
guarantee held only for half of the document.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, assert_never

from fitdocs import AthleteInputs, compute_metrics, parse_fit
from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.contract import (
    DOC_VERSION,
    document_date,
    document_version,
    is_workout_document,
    parse_frontmatter,
    sha_of_ref,
    source_refs,
)
from fitdocs.docio import read_frontmatter as _read_frontmatter
from fitdocs.layout import WORKOUTS_DIR, archive_path, settings_path
from fitdocs.load.arbitrate import (
    Ambiguous,
    NoCalculator,
    Selected,
    arbitrate,
    validate_configured,
)
from fitdocs.load.docedit import (
    RegionState,
    apply_frontmatter_load,
    classify_load_region,
    replace_load_region,
    strip_frontmatter_load,
)
from fitdocs.load.profile import (
    AthleteProfile,
    ProfileError,
    load_profile,
    save_profile,
)
from fitdocs.load.prompts import collect_missing_fields
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.render import PayloadStamp, render_computed, render_unsupported
from fitdocs.load.settings import LoadSettings, load_load_settings
from fitdocs.load.types import (
    Computed,
    InteractionSession,
    LoadContext,
    MissingInputs,
    NotComputed,
    Unsupported,
    supports_activity,
)
from fitdocs.settings import SettingsError, load_settings_document

__all__ = [
    "DocLoadEntry",
    "LoadReport",
    "apply_load",
]

# Config-error classes propagate out of the pass (they abort it, exit 2 at the
# CLI); every other per-document exception is isolated into a failure entry.
# ``SettingsError`` is the parent of ``LoadSettingsError`` (a malformed
# ``[load]`` table), so this one entry covers both.
_CONFIG_ERRORS: Final = (
    AthleteFileError,
    ProfileError,
    UnknownCalculatorError,
    SettingsError,
)


@dataclass(frozen=True)
class DocLoadEntry:
    """One document's outcome line in a :class:`LoadReport`.

    ``doc`` is the data-root-relative POSIX path of the document; ``detail`` is a
    calculator id (for a computed/restored result) or a human-readable reason
    (for a skip or failure).
    """

    doc: str
    detail: str


@dataclass(frozen=True)
class LoadReport:
    """The outcome of a load pass: every processed document, classified.

    Each tuple is in document (sorted-scan) order. A workout document lands in
    exactly one tuple per pass -- ``computed`` (a fresh result written),
    ``restored`` (frontmatter re-synced from a preserved payload after a regen),
    ``unsupported`` (the honest no-calculator state written), ``skipped`` (missing
    inputs, a declined confirmation, a non-interactive pass, protected foreign
    content, or a ``doc_version`` newer than this fitdocs produces -- the document
    left unchanged in every case, wiki-contract Req 5.5, 5.8), or ``failures`` (a
    missing/unparseable archive or damaged markers -- the document left
    byte-identical).
    """

    computed: tuple[DocLoadEntry, ...]
    restored: tuple[DocLoadEntry, ...]
    unsupported: tuple[DocLoadEntry, ...]
    skipped: tuple[DocLoadEntry, ...]
    failures: tuple[DocLoadEntry, ...]


@dataclass
class _Buckets:
    """Mutable accumulators for the five report categories during a pass."""

    computed: list[DocLoadEntry]
    restored: list[DocLoadEntry]
    unsupported: list[DocLoadEntry]
    skipped: list[DocLoadEntry]
    failures: list[DocLoadEntry]


def apply_load(
    data_root: Path,
    *,
    session: InteractionSession,
    calculator_id: str | None = None,
    recompute: bool = False,
    today: date | None = None,
) -> LoadReport:
    """Run the load pass over every workout document in ``data_root``.

    Up front (configuration errors propagate and abort the pass, before any
    document is read or written): the athlete inputs are loaded via
    :func:`~fitdocs.athlete.load_athlete_inputs` (``AthleteFileError``), the
    profile via :func:`~fitdocs.load.profile.load_profile` (``ProfileError``),
    and the ``[load]`` table is read *exactly once* for this invocation
    (Amendment 3, Req 14.4) via :func:`~fitdocs.settings.load_settings_document`
    and projected through :func:`~fitdocs.load.settings.load_load_settings`
    (``SettingsError`` / ``LoadSettingsError``). The resolved
    :class:`~fitdocs.load.settings.LoadSettings` is held for the whole pass --
    there is deliberately **no** ``default_calculator`` parameter here; the
    value is a member of those settings, and threading both would read the file
    twice and give the pass two sources for one setting. Whichever identifier
    is actually in play -- ``calculator_id`` (the ``--calculator`` flag) or the
    configured default -- is then validated against the registry via
    :func:`~fitdocs.load.arbitrate.validate_configured`
    (``UnknownCalculatorError``). Then ``workouts/*.md`` is scanned for fitdocs
    workout documents (leading ``---`` frontmatter with ``type: workout``),
    sorted for determinism; non-workout ``.md`` files are skipped silently.

    Per document, isolated (the pass never aborts on a per-doc error, Req 8.5):

    * **Version gate** -- a ``doc_version`` strictly newer than
      :data:`fitdocs.contract.DOC_VERSION`: the document is left completely
      untouched (no restore, no compute, no honest-unsupported write) and
      reported skipped, naming the recorded version (wiki-contract Req 5.5,
      5.8) -- checked before any of the branches below, on every document.
    * **Restore** -- not ``recompute`` and the region is a recognized computed
      payload: the frontmatter load keys are re-derived from the payload without
      recomputation or prompting; a write happens only if they had drifted (7.4).
    * **Superseded** -- not ``recompute`` and the region holds a result recorded
      under a prior result-format version: the document is left untouched and
      reported skipped, the reason naming the recorded version and, when the
      stamp carries one, the methodology (Req 11.2, 11.3, 13.4).
    * **Foreign** -- not ``recompute`` and the region holds unrecognized content:
      the document is left untouched and reported skipped (7.6).
    * **Compute** -- ``recompute`` (any state; the frontmatter keys are stripped
      first so a fresh compute re-confirms from scratch, 8.3), or a placeholder /
      previously-unsupported region (a supporting calculator may exist now,
      7.7): resolve the last ``sources`` archive (9.3), ``parse_fit`` +
      ``compute_metrics``, :func:`~fitdocs.load.arbitrate.arbitrate` exactly one
      calculator for the activity (Req 1.6, 10.1-10.4) -- no candidate loop --
      then, for a ``Selected`` calculator, ask
      :func:`~fitdocs.load.types.supports_activity` **before** collecting any
      athlete input (Req 1.14, 3.1); a ``False`` answer writes the honest
      unsupported state immediately. Otherwise collect declared fields
      (prompting + immediate persistence, 3.1-3.4), build a
      :class:`~fitdocs.load.types.LoadContext` carrying the resolved settings
      and the document's own recorded date (Req 1.12), then apply the
      calculator outcome -- computed (region + frontmatter written atomically),
      unsupported (honest state written -- whether from arbitration finding no
      candidate, an ambiguity, the support check, or the calculator's own
      ``compute`` declining), or a typed skip with a reason, the document
      unchanged (9.1).

    ``today`` is resolved once, right here, and threaded down to the generic
    prompt flow's ``on`` parameter, which stamps it onto any accepted
    benchmark answer as its measurement date (Req 6.2, 8.7); a caller-supplied
    value makes the date injectable for tests, and this is the pass's only
    clock read -- no module below this function reads one.

    Returns a :class:`LoadReport` whose tuples are in scan order.
    """
    today = today or date.today()
    athlete_inputs = load_athlete_inputs(data_root)  # AthleteFileError propagates
    profile = load_profile(data_root)  # ProfileError propagates
    load_settings_file = settings_path(data_root)
    settings_document = load_settings_document(data_root)  # SettingsError propagates
    settings = load_load_settings(
        settings_document, load_settings_file
    )  # LoadSettingsError propagates
    validate_configured(
        calculator_id,
        settings.default_calculator,
        settings_file=load_settings_file,
    )  # UnknownCalculatorError propagates

    buckets = _Buckets([], [], [], [], [])
    for doc in _discover_workout_docs(data_root):
        rel = doc.relative_to(data_root).as_posix()
        try:
            profile = _process_document(
                doc,
                rel,
                data_root,
                athlete_inputs=athlete_inputs,
                profile=profile,
                session=session,
                calculator_id=calculator_id,
                recompute=recompute,
                settings=settings,
                today=today,
                buckets=buckets,
            )
        except _CONFIG_ERRORS:
            raise  # configuration error -> abort the pass (Req 2.4)
        except Exception as exc:  # noqa: BLE001 -- isolate every per-doc failure
            buckets.failures.append(DocLoadEntry(doc=rel, detail=_reason(exc)))

    return LoadReport(
        computed=tuple(buckets.computed),
        restored=tuple(buckets.restored),
        unsupported=tuple(buckets.unsupported),
        skipped=tuple(buckets.skipped),
        failures=tuple(buckets.failures),
    )


def _process_document(
    doc: Path,
    rel: str,
    data_root: Path,
    *,
    athlete_inputs: AthleteInputs | None,
    profile: AthleteProfile,
    session: InteractionSession,
    calculator_id: str | None,
    recompute: bool,
    settings: LoadSettings,
    today: date,
    buckets: _Buckets,
) -> AthleteProfile:
    """Process one document; append its outcome and return the threaded profile.

    The (possibly updated) profile is threaded back so a field answered once for
    an earlier document is never re-asked for a later one. Damaged markers raise
    :class:`~fitdocs.docmerge.RegionError` and a missing ``load`` region raises
    :class:`~fitdocs.load.docedit.LoadDocError`; both are caught by the caller as
    per-document failures.

    **Version gate first (wiki-contract Req 5.5, 5.8).** Before any of the
    restore/superseded/foreign/compute branches below, a ``doc_version``
    strictly newer than :data:`fitdocs.contract.DOC_VERSION` leaves the
    document completely untouched and reports it skipped -- this pass must
    never rewrite the ``load`` region or the three load frontmatter keys of a
    document that ``sync``/``regen`` themselves already refused to rewrite. A
    missing, unusable, or lower/equal version proceeds to the normal branches
    unaffected.
    """
    markdown = doc.read_text(encoding="utf-8")

    frontmatter = parse_frontmatter(markdown)
    version = document_version(frontmatter) if frontmatter is not None else None
    if version is not None and version > DOC_VERSION:
        buckets.skipped.append(
            DocLoadEntry(
                doc=rel,
                detail=(
                    f"doc_version {version} is newer than the installed "
                    f"fitdocs (version {DOC_VERSION}); left unchanged"
                ),
            )
        )
        return profile

    classification = classify_load_region(markdown)
    state, payload, stamp = (
        classification.state,
        classification.payload,
        classification.stamp,
    )

    if not recompute and state is RegionState.COMPUTED:
        # Restore: re-derive the frontmatter keys from the payload, no compute.
        assert payload is not None and payload.result is not None
        new = apply_frontmatter_load(markdown, payload.result)
        if new != markdown:
            _atomic_write(doc, new)
            buckets.restored.append(
                DocLoadEntry(doc=rel, detail=payload.result.calculator_id)
            )
        return profile

    if not recompute and state is RegionState.SUPERSEDED:
        # A result to protect (Req 11.2, 11.3, 13.4): left byte-identical and
        # skipped, never fed into computed/restored/unsupported. `stamp` is
        # always populated for SUPERSEDED (see classify_load_region's table).
        assert stamp is not None
        buckets.skipped.append(DocLoadEntry(doc=rel, detail=_superseded_reason(stamp)))
        return profile

    if not recompute and state is RegionState.FOREIGN:
        buckets.skipped.append(
            DocLoadEntry(
                doc=rel,
                detail=(
                    "load region has unrecognized content; left untouched "
                    "(use --recompute to overwrite)"
                ),
            )
        )
        return profile

    # Compute path: placeholder / previously-unsupported, or any state under
    # --recompute. A recompute strips the managed frontmatter keys first so the
    # confirmation truly happens from scratch (Req 8.3). The activity's own
    # recorded date is read from the frontmatter this function already parsed
    # -- through the contract's single date accessor, never an inline key read
    # -- before that markdown is possibly rewritten below (`strip_frontmatter_load`
    # never touches the ``date`` key, so this stays the same value either way).
    activity_date = document_date(frontmatter)
    if recompute:
        markdown = strip_frontmatter_load(markdown)
    return _compute_document(
        doc,
        rel,
        data_root,
        markdown,
        athlete_inputs=athlete_inputs,
        profile=profile,
        session=session,
        calculator_id=calculator_id,
        settings=settings,
        activity_date=activity_date,
        today=today,
        buckets=buckets,
    )


def _compute_document(
    doc: Path,
    rel: str,
    data_root: Path,
    markdown: str,
    *,
    athlete_inputs: AthleteInputs | None,
    profile: AthleteProfile,
    session: InteractionSession,
    calculator_id: str | None,
    settings: LoadSettings,
    activity_date: date | None,
    today: date,
    buckets: _Buckets,
) -> AthleteProfile:
    """Resolve, parse, arbitrate, and score one fillable document.

    Arbitrates exactly one calculator per document -- no candidate loop (Req
    10.5): :func:`~fitdocs.load.arbitrate.arbitrate` folds ``NoCalculator``,
    ``Ambiguous``, and ``Selected`` exhaustively. A ``Selected`` calculator is
    then asked :func:`~fitdocs.load.types.supports_activity` -- unconditionally,
    regardless of which arbitration branch selected it -- *before* any athlete
    input is collected (Req 1.14, 3.1, 7.7, 10.5): selection (arbitration) and
    enforcement (this check) are different requirements, so this check runs
    even though arbitration's own no-default branch already asked the same
    question to narrow its candidates.
    """
    archive = _resolve_archive(data_root, markdown)
    if archive is None:
        buckets.failures.append(
            DocLoadEntry(
                doc=rel,
                detail=(
                    "no archived source: the document's 'sources' history is "
                    "empty or its current source is missing from the archive"
                ),
            )
        )
        return profile

    data = archive.read_bytes()
    activity = parse_fit(data)  # FitDecodeError -> per-doc failure
    metrics = compute_metrics(activity, athlete_inputs)

    outcome = arbitrate(
        activity,
        forced_id=calculator_id,
        default_calculator=settings.default_calculator,
    )
    match outcome:
        case NoCalculator():
            _write_unsupported(doc, rel, markdown, activity.sport.value, buckets)
            return profile
        case Ambiguous(candidates=candidates):
            buckets.skipped.append(
                DocLoadEntry(doc=rel, detail=_ambiguous_reason(candidates))
            )
            return profile
        case Selected(calculator=calc):
            pass
        case _:  # pragma: no cover - exhaustive over the closed outcome union
            assert_never(outcome)

    # The support check between selection and field collection (Req 1.14, 3.1,
    # 7.7, 10.5). A forced or configured selection reaches here un-narrowed by
    # sport (arbitration's forced/default branches are deliberately sport-blind
    # per Req 10.5), so this question -- and only this question -- decides
    # whether the interactive prompt flow is ever entered for this document.
    if not supports_activity(calc, activity):
        _write_unsupported(doc, rel, markdown, activity.sport.value, buckets)
        return profile

    hints: Mapping[str, Callable[[float], str]] = getattr(
        calc, "athlete_field_hints", {}
    )
    profile, _still_missing = collect_missing_fields(
        calc.required_athlete_fields(),
        profile,
        session,
        persist=lambda updated: save_profile(data_root, updated),
        hints=hints,
        on=today,
    )
    context = LoadContext(activity_date=activity_date, settings=settings)
    calc_outcome = calc.compute(activity, metrics, profile, session, context)
    match calc_outcome:
        case Computed(result=result):
            content = render_computed(result)
            new = replace_load_region(markdown, content)
            new = apply_frontmatter_load(new, result)
            _atomic_write(doc, new)
            buckets.computed.append(DocLoadEntry(doc=rel, detail=calc.calculator_id))
            return profile
        case MissingInputs(fields=fields):
            labels = ", ".join(field.label for field in fields)
            buckets.skipped.append(
                DocLoadEntry(doc=rel, detail=f"missing required inputs: {labels}")
            )
            return profile
        case NotComputed(reason=reason):
            buckets.skipped.append(DocLoadEntry(doc=rel, detail=reason))
            return profile
        case Unsupported():
            # The check above narrows but never replaces this outcome: an
            # arbitrated calculator that answered `supports_activity` truthfully
            # may still decline the specific activity from `compute` itself
            # (Req 1.3), and that reaches the same honest unsupported state.
            _write_unsupported(doc, rel, markdown, activity.sport.value, buckets)
            return profile
        case _:  # pragma: no cover - exhaustive over the closed outcome union
            assert_never(calc_outcome)


def _ambiguous_reason(candidates: tuple[str, ...]) -> str:
    """The skip reason for an :class:`~fitdocs.load.arbitrate.Ambiguous`
    arbitration -- names the candidates and the setting to configure (Req 10.2).
    """
    joined = ", ".join(candidates)
    return (
        f"more than one registered calculator supports this activity ({joined}); "
        "configure [load] default_calculator in fitdocs.toml to choose one"
    )


def _superseded_reason(stamp: PayloadStamp) -> str:
    """The skip reason for a :data:`~fitdocs.load.docedit.RegionState.SUPERSEDED`
    region -- names the recorded result-format version and, when the stamp
    carries one, the methodology (Req 11.2, 13.4). Needs no methodology-specific
    code path and no hardcoded calculator name: everything named here comes from
    the stamp itself.
    """
    methodology = (
        f", recorded by the {stamp.calculator_id!r} methodology,"
        if stamp.calculator_id is not None
        else ""
    )
    return (
        f"load region holds a result written under result-format version "
        f"{stamp.version}{methodology} which this installed fitdocs cannot "
        "read; left untouched (use --recompute to overwrite)"
    )


def _write_unsupported(
    doc: Path,
    rel: str,
    markdown: str,
    sport: str,
    buckets: _Buckets,
) -> None:
    """Write the honest unsupported state, unless the region already is one.

    Idempotent: an already-unsupported region re-renders byte-identically, so no
    write happens and no report entry is added (Req 7.7). No frontmatter keys are
    written -- honest absence.
    """
    new = replace_load_region(markdown, render_unsupported(sport))
    if new != markdown:
        _atomic_write(doc, new)
        buckets.unsupported.append(
            DocLoadEntry(doc=rel, detail=f"no registered calculator supports {sport}")
        )


# --- document discovery & frontmatter helpers -------------------------------


def _discover_workout_docs(data_root: Path) -> list[Path]:
    """Every fitdocs workout document under ``workouts/`` (top level), sorted.

    Qualification is the contract's :func:`~fitdocs.contract.is_workout_document`
    -- the same predicate the sync scan and the audit apply -- so a document this
    pass processes is exactly a document those recognize (Req 1.1). Non-fitdocs
    pages, garbled ``.md`` files, and ``workouts/*.md`` symlinks (never
    followed, wiki-contract Req 7.5, 7.6 -- see :mod:`fitdocs.docio`) are all
    skipped silently (not reported): this pass has no warnings channel of its
    own to report one on (unlike :class:`fitdocs.sync.SyncReport.warnings`),
    and a missing ``workouts/`` directory yields an empty list. This is
    read-only.
    """
    workouts = data_root / WORKOUTS_DIR
    if not workouts.is_dir():
        return []
    return [
        path
        for path in sorted(workouts.glob("*.md"))
        if is_workout_document(_read_frontmatter(path))
    ]


def _resolve_archive(data_root: Path, markdown: str) -> Path | None:
    """Resolve the document's current (last) ``sources`` archive, or ``None``.

    Reads the leading frontmatter's ``sources`` history through the contract,
    takes the last ref (the current render source), and resolves it back to
    ``fit-archive/<sha>.fit``. Returns ``None`` when the history is empty, its
    last entry is not a resolvable archive ref, or the referenced archive file is
    absent -- in each case the document cannot be filled and the caller records a
    failure (Req 9.3).

    The contract's :func:`~fitdocs.contract.sha_of_ref` *validates* the embedded
    sha rather than trusting it, so a hand-edited or traversal-shaped entry
    (``fit-archive/../secrets.fit``) is unresolvable here instead of becoming a
    path component joined onto the data root (wiki-contract Req 1.3). The load
    pass and regeneration therefore resolve the identical archive for any given
    document, and neither can be steered outside the archive by an edited
    history.
    """
    frontmatter = parse_frontmatter(markdown)
    if frontmatter is None:
        return None
    sources = source_refs(frontmatter)
    if not sources:
        return None
    sha = sha_of_ref(sources[-1])
    if sha is None:
        return None
    archive = archive_path(data_root, sha)
    return archive if archive.is_file() else None


# --- atomic write -----------------------------------------------------------


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` as a whole-document atomic replace.

    The content is written to a temporary file in the *same* directory, then
    :func:`os.replace` renames it over the target (a same-filesystem atomic
    swap), so a document is only ever its old bytes or its new bytes -- never a
    partial write. ``newline=""`` disables newline translation so the exact
    string bytes are preserved. The temporary file is removed on any failure.
    """
    directory = path.parent
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".load-", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _reason(exc: Exception) -> str:
    """A concise, non-empty failure reason naming the error kind and its message."""
    message = str(exc).strip()
    kind = type(exc).__name__
    return f"{kind}: {message}" if message else kind

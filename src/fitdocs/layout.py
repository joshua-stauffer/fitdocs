"""Data-root layout, activity identity, and document naming (design: DataRootLayout).

This leaf module is the single home for the fitdocs output-location contract
(workout-docs Req 2.4-2.7, 3.1, 3.6, 5.6; load-history Req 5.1, 5.9). It
defines the data-root layout constants
(``workouts/``, ``workouts/assets/``, ``history/``, ``history/assets/``,
``fit-archive/``, ``.cache/``, ``.fitdocs/``) and the pure helpers the sync
engine uses to place documents, name assets, archive sources, and derive a
stable activity identity. Because it names
every location fitdocs writes into, it is also where the *ownership* boundary is
stated: :data:`OWNED_PATHS` is the set the published contract and the
write-confinement guard both read (wiki-contract Req 7.5, 7.6), and
:data:`DECLARED_DIRS` the subset that receives an in-tree ownership declaration
(Req 3.1). Two ideas govern every helper here:

* **Honest naming.** A document is named from the activity's *local* start time
  (``YYYY-MM-DD-<slug>-HHMM``). When the activity recorded no start time, the
  stem carries an identity prefix (``undated-<slug>-<uid[:12]>``) rather than a
  fabricated date -- the hard no-fabrication rule (Req 2.5).
* **Stable identity.** ``activity_uid`` prefers the recorded ``SESSION UUID``
  developer field (a 16-byte value, formatted as a canonical UUID string) so
  re-exports of one activity converge onto one document; absent or malformed, it
  degrades to the source content hash and never raises (Req 3.6, 5.6). The
  formatting is :func:`fitdocs.contract.format_session_uuid` -- the package's one
  implementation, shared with the renderer that stamps the identity into
  frontmatter (wiki-contract Req 1.1).

The module performs **no file I/O**. The collision predicate (``taken``) is
injected by the caller, and the "relative" helpers (``asset_rel_path``,
``history_asset_rel_path``, ``source_ref``) return POSIX forward-slash strings
built by plain string joins -- never ``os.path.join`` -- so links stay portable
across operating systems and a whole-data-root move never breaks a document
(workout-docs Req 2.7; load-history Req 5.9).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import tzinfo
from pathlib import Path
from typing import Final

from fitdocs import Activity, Modality
from fitdocs.contract import format_session_uuid

WORKOUTS_DIR: Final[str] = "workouts"
"""Documents directory under the data root: ``<data-root>/workouts/``."""

ASSETS_SUBDIR: Final[str] = "assets"
"""Chart-assets directory under ``workouts/``: ``<data-root>/workouts/assets/``.

Also the history assets subdirectory name -- :data:`HISTORY_ASSETS_SUBDIR` is
defined *as* this constant, not as a second ``"assets"`` literal."""

ARCHIVE_DIR: Final[str] = "fit-archive"
"""Immutable source archive under the data root: ``<data-root>/fit-archive/``."""

SETTINGS_FILE: Final[str] = "fitdocs.toml"
"""User-owned settings file under the data root: ``<data-root>/fitdocs.toml``.

One file, one name, one definition. Every table that lives in it -- ``[tiles]``
today, ``[inbox]`` and ``[plugins]`` next -- resolves the file through
:func:`settings_path` rather than spelling the name again, so a reader can never
drift onto a different file than the one the others read.
"""

CACHE_DIR: Final[str] = ".cache"
"""Tool-managed cache root under the data root: ``<data-root>/.cache/``.

Dot-prefixed because nobody browses it: everything under it is re-fetchable or
re-derivable, so deleting the whole tree costs only work, never data. The tile
cache is its one tenant today (:data:`TILE_CACHE_DIR` is composed from this
constant, so the owned prefix and the real cache location cannot diverge)."""

TILE_CACHE_DIR: Final[str] = f"{CACHE_DIR}/tiles"
"""Basemap tile cache under the data root: ``<data-root>/.cache/tiles/`` (Req 3.3).

The tile cache lives under the data root -- never inside a code repository or the
package installation -- and is keyed by provider name so switching providers
never mixes basemap skins. Append-only and never part of the re-derivable
document state (deleting it only means re-fetching on the next render)."""

TOOL_STATE_DIR: Final[str] = ".fitdocs"
"""Tool-owned state under the data root: ``<data-root>/.fitdocs/``.

Where run state that is neither a document, an asset, an archived source, nor a
cache entry lands -- the sibling ingestion spec's quarantine record is the first
tenant. It is tool-owned (it is in :data:`OWNED_PATHS`) but carries **no**
ownership declaration: it is dot-prefixed machine state that no human or agent
browses, and a declaration there would only be noise.

Not to be confused with the ``.fitdocs/data-root`` *pointer* file
(:data:`~fitdocs.config.POINTER_RELPATH`). That one lives in a **source tree**,
found by walking upward from the working directory, and is read-only to fitdocs;
this one is a directory *inside* the data root the pointer points at. They share
a name and nothing else."""

HISTORY_DIR: Final[str] = "history"
"""Longitudinal history document directory: ``<data-root>/history/``."""

HISTORY_ASSETS_SUBDIR: Final[str] = ASSETS_SUBDIR
"""Chart-assets directory under ``history/``: ``<data-root>/history/assets/``.

Reuses :data:`ASSETS_SUBDIR` rather than spelling ``"assets"`` again, so the
workouts and history assets subdirectory names can never diverge."""

HISTORY_DOC_STEM: Final[str] = "training-load-history"
"""The history document's filename stem (without the ``.md`` extension).

There is exactly one history document per data root (Req 5.1), so unlike
:func:`doc_stem` this name is a fixed constant, never derived from an
activity."""

HISTORY_CHART: Final[str] = "fitness"
"""The history chart's name component, used to compose its filename."""

OWNED_PATHS: Final[tuple[str, ...]] = (
    f"{WORKOUTS_DIR}/",
    f"{WORKOUTS_DIR}/{ASSETS_SUBDIR}/",
    f"{HISTORY_DIR}/",
    f"{HISTORY_DIR}/{HISTORY_ASSETS_SUBDIR}/",
    f"{ARCHIVE_DIR}/",
    f"{CACHE_DIR}/",
    f"{TOOL_STATE_DIR}/",
)
"""Every path under the data root the ownership contract calls fitdocs-owned.

Data-root-relative POSIX **directory prefixes** (each ends in ``/``), which is
what makes the set complete without enumerating files: everything beneath an
entry is owned too, including files fitdocs does not write yet -- the
per-directory ``AGENTS.md`` ownership declarations among them. The published
contract (Req 2.1) is generated from this tuple, and the confinement guard (Req
7.5, 7.6) asserts that no run creates, modifies, or deletes anything outside it.

Two exclusions are deliberate. The user-owned files at the data root --
``fitdocs.toml`` (:data:`SETTINGS_FILE`) and ``athlete.toml`` -- are *not* owned:
fitdocs reads them and writes only its own keys into the profile, preserving the
rest (Req 2.7, 6.4). And a location the user's settings configure fitdocs to
write into is not listed here either (Req 2.10): the permitted set for any given
run is this tuple **union** the configured locations, so a configured intake
directory grants its own permission without widening the contract's fixed owned
set."""

DECLARED_DIRS: Final[tuple[str, ...]] = (
    f"{WORKOUTS_DIR}/",
    f"{HISTORY_DIR}/",
    f"{ARCHIVE_DIR}/",
)
"""The owned top-level directories that receive an ownership declaration (Req 3.1).

A subset of :data:`OWNED_PATHS` -- a declaration can never be placed anywhere
fitdocs does not own. These are the directories a human or an LLM agent
actually browses; ``workouts/assets/`` and ``history/assets/`` are excluded
because they are not top level (the declaration in each parent already covers
what is beneath it), and ``.cache/`` and ``.fitdocs/`` are excluded because
they are dot-prefixed machine state nobody reads. Writing the files is task
4.2's (and the history package's) job; this constant only names their
directories."""

_SESSION_UUID_FIELD: Final[str] = "SESSION UUID"
"""Developer-field key carrying the recorded 16-byte session identifier."""


def sport_slug(activity: Activity) -> str:
    """The document name's sport component (Req 2.4).

    ``"strength"`` when the activity's modality is strength (real strength files
    often carry a generic ``"Workout"`` sport label, so the slug is driven by the
    modality, not the sport). Otherwise the normalized sport label lowercased --
    ``Sport.RUN`` -> ``"run"``, ``Sport.RIDE`` -> ``"ride"``.
    """
    if activity.modality is Modality.STRENGTH:
        return "strength"
    return activity.sport.value.lower()


def activity_uid(activity: Activity, sha256: str) -> str:
    """The stable activity identity: recorded session UUID, else the content hash.

    Returns the ``SESSION UUID`` developer field formatted as a canonical,
    lowercase ``8-4-4-4-12`` UUID string when it is present and well-formed -- a
    value of exactly 16 elements, each an ``int`` in ``0..255`` (Req 3.6, 5.6).
    This is the identity that converges re-exports of one activity onto one
    document (the sync engine matches it in frontmatter) and that seeds naming
    fallbacks. A missing or malformed value -- wrong length, non-integer element,
    out-of-range byte, or the wrong type entirely -- degrades to ``sha256`` and
    never raises.

    The formatting itself is :func:`fitdocs.contract.format_session_uuid`, not a
    copy of it: the identity this function derives is the identity the renderer
    stamps into frontmatter and the sync engine matches on, so all three must
    agree on every edge -- and a same-named local copy would satisfy every
    behavioral test while quietly disagreeing on one (wiki-contract Req 1.1).
    """
    formatted = format_session_uuid(activity.developer_fields.get(_SESSION_UUID_FIELD))
    return formatted if formatted is not None else sha256


def doc_stem(
    activity: Activity,
    uid: str,
    tz: tzinfo,
    taken: Callable[[str], bool],
) -> str:
    """The document's filename stem (without the ``.md`` extension) (Req 2.5, 2.6).

    With a recorded start time, the activity's UTC ``start_time`` is converted to
    local time in ``tz`` and formatted ``f"{local:%Y-%m-%d}-{slug}-{local:%H%M}"``
    (e.g. ``2026-07-12-run-0730``) -- the *local* date and time name the document.
    Without a start time the stem is ``f"undated-{slug}-{uid[:12]}"``: an identity
    prefix, never a fabricated date.

    Collision policy: ``taken`` reports whether an existing document for a
    *different* activity already uses a stem. When the base stem is taken, this
    appends ``f"-{uid[:8]}"``. The suffix depends only on this activity's recorded
    identity, so it is deterministic across runs and can never reuse another
    activity's name.
    """
    slug = sport_slug(activity)
    start = activity.start_time
    if start is None:
        base = f"undated-{slug}-{uid[:12]}"
    else:
        local = start.astimezone(tz)
        base = f"{local:%Y-%m-%d}-{slug}-{local:%H%M}"
    if taken(base):
        return f"{base}-{uid[:8]}"
    return base


def doc_path(data_root: Path, stem: str) -> Path:
    """The document's filesystem path: ``<data_root>/workouts/<stem>.md``."""
    return data_root / WORKOUTS_DIR / f"{stem}.md"


def asset_rel_path(stem: str, chart: str) -> str:
    """A chart asset's link, POSIX and *relative to the document's directory*.

    Returns ``assets/<stem>-<chart>.svg``. Because the document lives in
    ``<data-root>/workouts/`` and assets live in ``<data-root>/workouts/assets/``,
    this doc-relative link resolves correctly and survives a whole-data-root move
    (Req 2.7). Built by plain string joins so the separators stay forward slashes
    on every operating system.
    """
    return f"{ASSETS_SUBDIR}/{stem}-{chart}.svg"


def history_doc_path(data_root: Path) -> Path:
    """The history document's filesystem path.

    ``<data_root>/history/training-load-history.md``.
    """
    return data_root / HISTORY_DIR / f"{HISTORY_DOC_STEM}.md"


def history_asset_path(data_root: Path, chart: str) -> Path:
    """A history chart's filesystem path.

    ``<data_root>/history/assets/training-load-history-<chart>.svg``.
    """
    return (
        data_root
        / HISTORY_DIR
        / HISTORY_ASSETS_SUBDIR
        / f"{HISTORY_DOC_STEM}-{chart}.svg"
    )


def history_asset_rel_path(chart: str) -> str:
    """A history chart's link, POSIX and *relative to the history document's directory*.

    Returns ``assets/training-load-history-<chart>.svg``. Because the history
    document lives in ``<data-root>/history/`` and its charts live in
    ``<data-root>/history/assets/``, this doc-relative link resolves correctly
    and survives a whole-data-root move (Req 5.9). Built by a plain string join
    so the separators stay forward slashes on every operating system.
    """
    return f"{HISTORY_ASSETS_SUBDIR}/{HISTORY_DOC_STEM}-{chart}.svg"


def archive_path(data_root: Path, sha256: str) -> Path:
    """The archived source path: ``<data_root>/fit-archive/<sha256>.fit``."""
    return data_root / ARCHIVE_DIR / f"{sha256}.fit"


def settings_path(data_root: Path) -> Path:
    """The user-owned settings file: ``<data_root>/fitdocs.toml``.

    The single way to locate the settings file. Readers call this instead of
    composing the path from the filename constant, so every table in the file is
    guaranteed to be read from the same place.
    """
    return data_root / SETTINGS_FILE


def tile_cache_path(data_root: Path, provider: str, z: int, x: int, y: int) -> Path:
    """A basemap tile's cache path under the data root's tile cache (Req 3.3).

    Maps to ``<data_root>/.cache/tiles/<provider>/<z>/<x>/<y>.png``. The
    per-provider ``z/x/y`` layout keys tiles under the data root's cache area --
    never inside a code repository or the package installation.
    ``provider`` is the tile-settings ``name`` slug, already validated path-safe
    upstream (this leaf does not re-validate); ``z``/``x``/``y`` are plain slippy-map
    tile coordinates. Like every helper here this stays a pure leaf: it performs no
    I/O (the caller creates directories) and only prepends path components onto the
    supplied ``data_root``.
    """
    return data_root / TILE_CACHE_DIR / provider / str(z) / str(x) / f"{y}.png"


DEFAULT_INBOX_DIR: Final[str] = "inbox"
"""Default inbox location under the data root: ``<data-root>/inbox/`` (Req 1.2).

Used when the settings file or its ``[inbox]`` table is absent, or when the
table is present but does not override ``path``. The inbox itself is a
user-configured location fitdocs may create at drain time -- it is not part
of :data:`OWNED_PATHS`, the same treatment the optional processed-files
destination receives (Req 8.5)."""


def quarantine_path(data_root: Path) -> Path:
    """The quarantine record's path: ``<data_root>/.fitdocs/quarantine.toml``.

    Lives under :data:`TOOL_STATE_DIR`, the tool-owned state directory the
    published ownership contract already names (Req 5.1, 8.5). Pure path
    composition only -- creating the directory belongs to the store that
    writes into it (``quarantine.py``), not to this I/O-free leaf.
    """
    return data_root / TOOL_STATE_DIR / "quarantine.toml"


def source_ref(sha256: str) -> str:
    """The frontmatter source reference: the archive path *relative to the data root*.

    Returns ``fit-archive/<sha256>.fit`` as a POSIX forward-slash string (Req 3.1,
    3.4). Data-root-relative and portable so the ``sources`` provenance entry
    never bakes in an absolute or OS-specific path.
    """
    return f"{ARCHIVE_DIR}/{sha256}.fit"

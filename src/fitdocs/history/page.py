"""The training-history document's own vocabulary, and its frontmatter block
(load-history spec, task 4.2; Req 5.8, 6.4).

This module declares the document's identity once, in one place: its
``type`` value, its title, its format version and the frontmatter key that
carries it, and the ordered tuple of every key the frontmatter block emits.
Nothing here re-spells the vocabulary :mod:`fitdocs.contract` already owns --
the ``---`` fence, the ``type``/``generator`` key names, the generator name
itself -- every one of those is imported from ``contract`` and used as-is. A
test asserts :data:`HISTORY_TYPE` differs from ``contract.WORKOUT_TYPE``, so a
history page and a workout page are never mistaken for one another by any
scan that reads ``type`` (Req 5.8).

**The frontmatter block is emitted as ordered plain text lines, never through
a YAML library.** Every value the block carries is machine-generated and
drawn from a closed set -- fixed strings, integers, and ISO dates -- except
one: the methodology identifier, a calculator id an athlete's settings (or a
plugin) may supply. That one free value is emitted bare when it is a plain
token (``[A-Za-z0-9_.-]+``) and double-quoted, with ``\\`` and ``"`` escaped,
otherwise; a control character or a newline anywhere in it is a hard failure
rather than a block quietly broken past the point a YAML parser can still
read it back. :mod:`fitdocs.render.frontmatter` -- the package's one YAML
*emission* touchpoint, and workout-docs' file -- is neither imported nor
touched by this module.

**Every number is formatted by one explicit rule** (four decimal places, via
Python's own ``f"{value:.4f}"`` format spec) so no platform's default float
representation -- scientific notation, a trailing ``.0`` some readers drop,
a locale-specific separator -- can leak into the bytes. **A value that is
genuinely unknown is omitted from the block entirely, never emitted as a
fabricated zero**: every constant this module accepts is ``| None``-typed for
exactly this reason, and the emitter skips a ``None`` field's key and value
outright rather than writing a placeholder a later reader could mistake for a
real, computed number.

``pages_read``, ``pages_with_load`` and ``criterion_points`` (Req 6.1, 6.4)
are the three counts this module always writes: unlike a constant that may be
genuinely absent, a real archive always has these counts -- zero is itself a
meaningful, real answer, never a stand-in for "unknown" -- so each is a
required ``int`` parameter, not an optional one, and the frontmatter round
trip always reads each one back as an ``int``.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Final

from fitdocs import contract

# --- document vocabulary (Req 5.8) -------------------------------------------

HISTORY_TYPE: Final[str] = "training-history"
"""The frontmatter ``type`` value identifying the training-history document.

Distinct from :data:`fitdocs.contract.WORKOUT_TYPE` by construction -- a test
pins the inequality directly, so no future edit to either constant can quietly
make the two document kinds indistinguishable to a scan that reads ``type``.
"""

HISTORY_TITLE: Final[str] = "Training Load History"
"""The document's fixed title -- both the frontmatter ``title`` value and (task
4.3) the page's own heading text."""

HISTORY_VERSION: Final[int] = 1
"""The training-history document format's own version number -- independent of
:data:`fitdocs.contract.DOC_VERSION`, which versions the *workout* document
format instead."""

HISTORY_VERSION_KEY: Final[str] = "history_version"
"""The frontmatter key carrying :data:`HISTORY_VERSION`."""

HISTORY_FRONTMATTER_KEYS: Final[tuple[str, ...]] = (
    "title",
    contract.TYPE_KEY,
    contract.GENERATOR_KEY,
    HISTORY_VERSION_KEY,
    "methodology",
    "methodology_source",
    "constants_provenance",
    "tau_fitness_days",
    "tau_fatigue_days",
    "k_fitness",
    "k_fatigue",
    "coverage_threshold",
    "series_start",
    "series_end",
    "pages_read",
    "pages_with_load",
    "criterion_points",
)
"""Every frontmatter key this document emits, in emission order (Req 5.8).

Declared once, here, as the single source of truth for the key order; the
order :func:`render_frontmatter` actually writes is spelled independently in
that function's body (matching the design's key list, design.md:1224-1228) so
a test comparing the two catches either one drifting from the other."""

# --- emission rules -----------------------------------------------------------

_IDENTIFIER_PATTERN: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.-]+")
"""The plain-token shape a methodology identifier may be emitted bare in."""


def _reject_control_characters(value: str, *, field: str) -> None:
    """Raise if ``value`` carries a control character or newline anywhere.

    ``str.isprintable()`` is false for exactly this class of character (and
    true for an ordinary space, which a plain identifier may legitimately
    contain) -- the ASCII/Unicode "control or separator other than space"
    definition Python's own stdlib already carries, so this function spells no
    numeric code-point literal of its own.
    """
    if not value.isprintable():
        raise ValueError(
            f"{field} contains a control character or newline -- this would "
            "either break the frontmatter block's YAML syntax outright or "
            "silently embed an unreadable byte in it, so it is a hard "
            "failure rather than best-effort quoting"
        )


def _quote(value: str, *, field: str) -> str:
    """Double-quote ``value`` for the frontmatter block, escaping ``\\`` and
    ``"``. Used for every plain (non-identifier) string value the block
    carries."""
    _reject_control_characters(value, field=field)
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_identifier(value: str, *, field: str) -> str:
    """Format the one free value -- a methodology/calculator id -- per the
    design's quoting rule: bare when it is a plain token, double-quoted and
    escaped otherwise. A control character or newline is a hard failure
    regardless of which branch would otherwise apply."""
    _reject_control_characters(value, field=field)
    if _IDENTIFIER_PATTERN.fullmatch(value):
        return value
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _format_float(value: float) -> str:
    """Format a frontmatter float to a fixed four decimal places -- an
    explicit rule so no platform's default ``repr``/``str`` (scientific
    notation, a dropped trailing ``.0``) can leak into the bytes."""
    return f"{value:.4f}"


def render_frontmatter(
    *,
    methodology: str | None,
    methodology_source: str | None,
    constants_provenance: str | None,
    tau_fitness_days: float | None,
    tau_fatigue_days: float | None,
    k_fitness: float | None,
    k_fatigue: float | None,
    coverage_threshold: float | None,
    series_start: date | None,
    series_end: date | None,
    pages_read: int,
    pages_with_load: int,
    criterion_points: int,
) -> str:
    """Render the training-history document's frontmatter block, as ordered
    plain text lines fenced by :data:`fitdocs.contract.FRONTMATTER_FENCE`
    (Req 5.8, 6.4).

    Every ``| None``-typed parameter is a value that may genuinely be unknown
    -- no methodology could be selected, no constant set resolved, no page in
    the series at all -- and is omitted from the block entirely when ``None``,
    never emitted as a fabricated zero or empty string. ``pages_read``,
    ``pages_with_load`` and ``criterion_points`` are real counts that are
    always known (zero is itself a real, meaningful answer for each), so they
    are required and always written.

    Returns the block including its opening and closing fence lines and a
    trailing newline; the result parses through
    :func:`fitdocs.contract.parse_frontmatter` directly.
    """
    lines: list[str] = [contract.FRONTMATTER_FENCE]
    lines.append(f"title: {_quote(HISTORY_TITLE, field='title')}")
    lines.append(
        f"{contract.TYPE_KEY}: {_quote(HISTORY_TYPE, field=contract.TYPE_KEY)}"
    )
    lines.append(
        f"{contract.GENERATOR_KEY}: "
        f"{_quote(contract.GENERATOR, field=contract.GENERATOR_KEY)}"
    )
    lines.append(f"{HISTORY_VERSION_KEY}: {HISTORY_VERSION}")
    if methodology is not None:
        lines.append(
            f"methodology: {_format_identifier(methodology, field='methodology')}"
        )
    if methodology_source is not None:
        lines.append(
            f"methodology_source: "
            f"{_quote(methodology_source, field='methodology_source')}"
        )
    if constants_provenance is not None:
        lines.append(
            f"constants_provenance: "
            f"{_quote(constants_provenance, field='constants_provenance')}"
        )
    if tau_fitness_days is not None:
        lines.append(f"tau_fitness_days: {_format_float(tau_fitness_days)}")
    if tau_fatigue_days is not None:
        lines.append(f"tau_fatigue_days: {_format_float(tau_fatigue_days)}")
    if k_fitness is not None:
        lines.append(f"k_fitness: {_format_float(k_fitness)}")
    if k_fatigue is not None:
        lines.append(f"k_fatigue: {_format_float(k_fatigue)}")
    if coverage_threshold is not None:
        lines.append(f"coverage_threshold: {_format_float(coverage_threshold)}")
    if series_start is not None:
        lines.append(
            f"series_start: {_quote(series_start.isoformat(), field='series_start')}"
        )
    if series_end is not None:
        lines.append(
            f"series_end: {_quote(series_end.isoformat(), field='series_end')}"
        )
    lines.append(f"pages_read: {pages_read}")
    lines.append(f"pages_with_load: {pages_with_load}")
    lines.append(f"criterion_points: {criterion_points}")
    lines.append(contract.FRONTMATTER_FENCE)
    return "\n".join(lines) + "\n"

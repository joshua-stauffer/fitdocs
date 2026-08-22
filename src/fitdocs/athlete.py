"""Read-only athlete-inputs reader (Req 8.3).

This module maps an *optional* ``<data_root>/athlete.toml`` onto the fit-ingest
:class:`~fitdocs.AthleteInputs` / :class:`~fitdocs.ZoneSpec` contract (design:
AthleteInputsReader). The athlete-inputs source is what unlocks the zone strip
(Req 8.1) and the threshold-dependent metrics -- intensity factor, training
stress, TRIMP (Req 8.4) -- downstream; this layer only *reads* it.

Two invariants shape the contract:

* **Optional.** An absent file yields ``None`` -- not an error. The whole
  feature set that depends on athlete inputs simply degrades to omission.
* **Loud, never lossy.** A file that exists but is malformed -- invalid TOML, a
  wrong value type, a boolean where a number is expected, or non-ascending /
  empty zone dividers -- raises :class:`AthleteFileError`. Silently dropping a
  bad zone would change the rendered document invisibly, so nothing is swallowed.

The reader is read-only *by construction* (Req 8.3): it never creates the file,
never prompts, and writes nothing on any path. Profile creation, prompting, and
the file's lifecycle belong to the downstream training-load feature, which may
add keys -- so **unknown keys are ignored** for forward compatibility.

Types are validated strictly. Because Python's ``bool`` is a subclass of
``int``, a TOML boolean would otherwise sneak through as ``0``/``1``; it is
rejected everywhere a number is required. Integer thresholds (``resting_hr_bpm``,
``max_hr_bpm``) require a TOML integer; ``ftp_watts`` accepts a TOML integer or
float and is normalized to ``float``.
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from fitdocs import AthleteInputs, ZoneSpec

ATHLETE_FILE: Final[str] = "athlete.toml"

ATHLETE_SCHEMA_VERSION: Final[int] = 2
"""Schema version stamped into and required of ``athlete.toml``.

1 = flat athlete-input keys only (the shipped shape); 2 adds ``[benchmarks]``.
"""

VERSION_KEY: Final[str] = "profile_version"
"""The existing on-disk key name, kept unchanged for file compatibility."""


class AthleteFileError(Exception):
    """The ``athlete.toml`` file exists but cannot be read as valid inputs.

    Raised for malformed TOML, a wrong value type (including a boolean where a
    number is required), non-ascending / empty zone dividers, or a declared
    schema version this fitdocs does not recognize. An *absent* file is never
    an error -- it yields ``None`` instead. The message names the file and the
    offending key so a user can correct the configuration.
    """


def check_schema_version(document: Mapping[str, object], path: Path) -> int:
    """Read and validate the declared schema version of a decoded ``athlete.toml``.

    An absent :data:`VERSION_KEY` is treated as version 1, the earliest schema
    (Req 1.8), and any benchmarks present are still read regardless of the
    declared version, so long as it is one this fitdocs supports (Req 1.6) --
    the version gates *forward* only.

    Raises :class:`AthleteFileError` naming *path*, the declared version and
    the supported version when the value is not a plain integer (a TOML
    boolean is rejected even though ``bool`` subclasses ``int``), is below 1,
    or is greater than :data:`ATHLETE_SCHEMA_VERSION` (Req 1.7).
    """
    if VERSION_KEY not in document:
        return 1

    value = document[VERSION_KEY]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise AthleteFileError(
            f"{path}: {VERSION_KEY} must be an integer between 1 and "
            f"{ATHLETE_SCHEMA_VERSION} (the version this fitdocs supports), "
            f"got {value!r} ({type(value).__name__})"
        )
    if value > ATHLETE_SCHEMA_VERSION:
        raise AthleteFileError(
            f"{path} declares {VERSION_KEY} = {value}, which is newer than "
            f"the schema version this fitdocs supports "
            f"({ATHLETE_SCHEMA_VERSION}); install a newer fitdocs to read it"
        )
    return value


def load_athlete_inputs(data_root: Path) -> AthleteInputs | None:
    """Read ``<data_root>/athlete.toml`` into :class:`AthleteInputs`, or ``None``.

    Returns ``None`` when the file is absent -- the inputs are optional (Req
    8.3). Otherwise every recognized key is mapped onto the corresponding
    :class:`AthleteInputs` field (present keys only; the rest stay ``None``), and
    unknown keys are ignored for forward compatibility with training-load.

    Raises :class:`AthleteFileError` when the file exists but is malformed:
    invalid TOML, a wrong value type, a boolean where a number is expected, or
    zone dividers that are empty or not strictly ascending (the last surfaced by
    :class:`~fitdocs.ZoneSpec` and re-raised here). The function only ever reads;
    it never writes, creates, or prompts.
    """
    path = data_root / ATHLETE_FILE
    if not path.is_file():
        return None

    try:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise AthleteFileError(f"{path} is not valid TOML: {exc}") from exc

    check_schema_version(data, path)

    return AthleteInputs(
        ftp_watts=_optional_number(data, "ftp_watts", path),
        resting_hr_bpm=_optional_int(data, "resting_hr_bpm", path),
        max_hr_bpm=_optional_int(data, "max_hr_bpm", path),
        hr_zones=_optional_zone(data, "hr_zones", path),
        power_zones=_optional_zone(data, "power_zones", path),
        pace_zones=_optional_zone(data, "pace_zones", path),
    )


def _optional_number(data: dict[str, Any], key: str, path: Path) -> float | None:
    """Map an optional numeric threshold to ``float``; reject non-numbers/bools."""
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AthleteFileError(
            f"{path}: {key} must be a number, got {value!r} ({type(value).__name__})"
        )
    return float(value)


def _optional_int(data: dict[str, Any], key: str, path: Path) -> int | None:
    """Map an optional integer threshold; reject floats and bools strictly."""
    if key not in data:
        return None
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AthleteFileError(
            f"{path}: {key} must be an integer, got {value!r} ({type(value).__name__})"
        )
    return value


def _optional_zone(data: dict[str, Any], key: str, path: Path) -> ZoneSpec | None:
    """Map an optional list of ascending dividers to a :class:`ZoneSpec`.

    Every element must be a number (a boolean is rejected, never coerced to
    ``0``/``1``); the ascending / non-empty guarantee is delegated to
    :class:`ZoneSpec`, whose :class:`ValueError` is re-raised as
    :class:`AthleteFileError` so a bad list fails loudly instead of vanishing.
    """
    if key not in data:
        return None
    value = data[key]
    if not isinstance(value, list):
        raise AthleteFileError(
            f"{path}: {key} must be a list of ascending numbers, "
            f"got {value!r} ({type(value).__name__})"
        )
    dividers: list[float] = []
    for element in value:
        if isinstance(element, bool) or not isinstance(element, (int, float)):
            raise AthleteFileError(
                f"{path}: every {key} divider must be a number, "
                f"got {element!r} ({type(element).__name__})"
            )
        dividers.append(float(element))
    try:
        return ZoneSpec(dividers=tuple(dividers))
    except ValueError as exc:
        raise AthleteFileError(
            f"{path}: {key} must be non-empty and strictly ascending ({exc})"
        ) from exc

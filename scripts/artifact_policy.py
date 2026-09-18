"""Reader for `release/artifact-policy.toml` (design: ArtifactPolicy).

This module holds the one judgement about release-artifact contents that is
reviewable data rather than script internals: which members a wheel and a
source distribution must contain, which member-name patterns they must
never contain, and which distribution-metadata fields a release must
declare. It reads that data; it defines none of it.

Two rules shape the reader, mirroring `fitdocs.settings`:

* **Loud, never lossy.** A missing policy file, unparsable TOML, a missing
  required table or key, or a wrongly-typed value (anything other than a
  list of non-empty strings for `wheel.required`, `sdist.required`,
  `forbidden.members`, or `metadata.required_fields`) raises
  :class:`PolicyError` naming the offending key.
* **Unknown is tolerated.** An unrecognized top-level table or an
  unrecognized key inside a known table is ignored, exactly as the shared
  settings reader tolerates unknown keys in the user's settings file --
  this file is meant to grow across tasks without every addition needing a
  reader change.

This module is a pure leaf: standard library only (`tomllib`, `dataclasses`,
`pathlib`, `typing`), nothing imported from `fitdocs`. It is invoked as
`python -m scripts.<name>` from the repository root and never ships in a
built artifact.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_POLICY_PATH: Path = Path("release/artifact-policy.toml")
"""The policy file's location, relative to the repository root."""


class PolicyError(ValueError):
    """The policy file is missing, unparsable, or declares malformed data.

    The message names the offending table, key, or file path so a person
    editing the policy by hand knows exactly what to fix.
    """


@dataclass(frozen=True)
class ArtifactPolicy:
    """Validated contents of `release/artifact-policy.toml`.

    Every field is a non-empty tuple of non-empty strings; :func:`load_policy`
    never returns a partially-populated instance -- a malformed or absent
    input raises :class:`PolicyError` instead.
    """

    wheel_required: tuple[str, ...]
    sdist_required: tuple[str, ...]
    forbidden_members: tuple[str, ...]
    required_metadata_fields: tuple[str, ...]


def _read_required_list(
    document: dict[str, Any], table: str, key: str
) -> tuple[str, ...]:
    """Read `document[table][key]` as a non-empty list of non-empty strings.

    Raises :class:`PolicyError` naming `table.key` for a missing table, a
    missing key, or any value that is not a list of non-empty strings.
    """
    table_value = document.get(table)
    if not isinstance(table_value, dict):
        raise PolicyError(
            f"release policy is missing required table '[{table}]' (not a table)"
        )
    if key not in table_value:
        raise PolicyError(f"release policy is missing required key '{table}.{key}'")

    raw = table_value[key]
    if not isinstance(raw, list) or not raw:
        raise PolicyError(
            f"release policy key '{table}.{key}' must be a non-empty list of strings"
        )
    for item in raw:
        if not isinstance(item, str) or not item:
            raise PolicyError(
                f"release policy key '{table}.{key}' must be non-empty strings"
            )
    return tuple(raw)


def load_policy(path: Path) -> ArtifactPolicy:
    """Read and validate the artifact policy at `path`.

    Raises :class:`PolicyError` when the file does not exist, is not valid
    TOML, or is missing any of the four required table/key pairs
    (`wheel.required`, `sdist.required`, `forbidden.members`,
    `metadata.required_fields`) or gives one of them a wrongly-typed value.
    Unknown tables and unknown keys within a known table are tolerated.
    """
    if not path.is_file():
        raise PolicyError(f"release policy file {path} does not exist")

    try:
        with path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(
            f"release policy file {path} is not valid TOML: {exc}"
        ) from exc

    return ArtifactPolicy(
        wheel_required=_read_required_list(document, "wheel", "required"),
        sdist_required=_read_required_list(document, "sdist", "required"),
        forbidden_members=_read_required_list(document, "forbidden", "members"),
        required_metadata_fields=_read_required_list(
            document, "metadata", "required_fields"
        ),
    )

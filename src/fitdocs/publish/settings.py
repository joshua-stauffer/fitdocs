"""The ``[publish]`` settings table and the built-in default templates
(publish-core Req 4.1, 4.2, 4.3, 4.6, 4.8).

``fitdocs.toml`` is shared: the caller reads it once and hands this reader the
already-parsed mapping, the settings file's path (used only to name it in
errors) and the names of the configured publish targets.  Nothing here opens a
file.

Per target and per field (title, description) the template is the target's own
``[publish.targets.<name>]`` value, else the table-wide ``[publish]`` value,
else the built-in default.  Every problem raises :class:`PublishSettingsError`
naming the settings file, the table and the key, and for a template the
position and reason.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from fitdocs.publish.template import (
    TargetTemplates,
    Template,
    TemplateSyntaxError,
    parse_template,
)
from fitdocs.publish.values import PLACEHOLDERS, has_control_character
from fitdocs.settings import SettingsError

PUBLISH_TABLE: Final[str] = "publish"
DEFAULT_TITLE: Final[str] = "{title}"
DEFAULT_DESCRIPTION: Final[str] = (
    "{?Distance: {distance_km} km\n}"
    "{?Time: {moving_time}\n}"
    "{?Pace: {pace_per_km} /km\n}"
    "{?Speed: {speed_kmh} km/h\n}"
    "{?Average heart rate: {avg_hr_bpm} bpm\n}"
    "{?Average power: {avg_power_w} W\n}"
    "{?Elevation gain: {elevation_gain_m} m\n}"
)

_TITLE_KEY: Final[str] = "title"
_DESCRIPTION_KEY: Final[str] = "description"
_TARGETS_KEY: Final[str] = "targets"
_TEMPLATE_KEYS: Final[tuple[str, ...]] = (_TITLE_KEY, _DESCRIPTION_KEY)


class PublishSettingsError(SettingsError):
    """The ``[publish]`` table is malformed (a configuration error, exit 2)."""


#: Parsed at import: a default that names an unknown placeholder or is
#: malformed fails the import, not a user's run.
DEFAULT_TEMPLATES: Final[TargetTemplates] = TargetTemplates(
    title=parse_template(DEFAULT_TITLE, names=PLACEHOLDERS),
    description=parse_template(DEFAULT_DESCRIPTION, names=PLACEHOLDERS),
)


@dataclass(frozen=True)
class PublishSettings:
    """The resolved templates of every configured publish target."""

    per_target: Mapping[str, TargetTemplates]

    def for_target(self, name: str) -> TargetTemplates:
        return self.per_target[name]


def _template_field(
    table: Mapping[str, object], key: str, where: str, settings_file: Path
) -> Template | None:
    """Parse ``table[key]`` if present; ``None`` when the key is absent."""
    if key not in table:
        return None
    value = table[key]
    if not isinstance(value, str):
        raise PublishSettingsError(
            f"{settings_file}: [{where}] {key} must be text, "
            f"got {value!r} ({type(value).__name__})"
        )
    if key == _TITLE_KEY and has_control_character(value):
        raise PublishSettingsError(
            f"{settings_file}: [{where}] {key} must be a single line, got {value!r}"
        )
    try:
        return parse_template(value, names=PLACEHOLDERS)
    except TemplateSyntaxError as exc:
        raise PublishSettingsError(
            f"{settings_file}: [{where}] {key}: invalid template, {exc}"
        ) from exc


def _read_fields(
    table: Mapping[str, object],
    where: str,
    allowed: tuple[str, ...],
    settings_file: Path,
) -> dict[str, Template | None]:
    for key in table:
        if key not in allowed:
            raise PublishSettingsError(
                f"{settings_file}: [{where}] has unknown key {key!r} "
                f"(expected one of {', '.join(allowed)})"
            )
    return {
        key: _template_field(table, key, where, settings_file) for key in _TEMPLATE_KEYS
    }


def load_publish_settings(
    document: Mapping[str, object], *, settings_file: Path, targets: Collection[str]
) -> PublishSettings:
    """Project ``[publish]`` of an already-parsed settings document.

    ``targets`` names the configured publish targets; every one gets an entry
    in the result, and a ``[publish.targets.<name>]`` table naming anything
    else is refused.  An absent ``[publish]`` yields the built-in default for
    every target.
    """
    table: Mapping[str, object] = {}
    if PUBLISH_TABLE in document:
        raw = document[PUBLISH_TABLE]
        if not isinstance(raw, dict):
            raise PublishSettingsError(
                f"{settings_file}: [{PUBLISH_TABLE}] must be a table, "
                f"got {raw!r} ({type(raw).__name__})"
            )
        table = raw
    wide = _read_fields(
        table, PUBLISH_TABLE, (*_TEMPLATE_KEYS, _TARGETS_KEY), settings_file
    )
    own: dict[str, dict[str, Template | None]] = {}
    if _TARGETS_KEY in table:
        where_targets = f"{PUBLISH_TABLE}.{_TARGETS_KEY}"
        raw_targets = table[_TARGETS_KEY]
        if not isinstance(raw_targets, dict):
            raise PublishSettingsError(
                f"{settings_file}: [{where_targets}] must be a table, "
                f"got {raw_targets!r} ({type(raw_targets).__name__})"
            )
        for name, entry in raw_targets.items():
            where = f"{where_targets}.{name}"
            if not isinstance(entry, dict):
                raise PublishSettingsError(
                    f"{settings_file}: [{where}] must be a table, "
                    f"got {entry!r} ({type(entry).__name__})"
                )
            if name not in targets:
                known = ", ".join(sorted(targets)) or "none configured"
                raise PublishSettingsError(
                    f"{settings_file}: [{where}] names {name!r}, which is "
                    f"not a configured publish target (configured: {known})"
                )
            own[name] = _read_fields(entry, where, _TEMPLATE_KEYS, settings_file)

    def pick(name: str, key: str, default: Template) -> Template:
        for layer in (own.get(name, {}), wide):
            found = layer.get(key)
            if found is not None:
                return found
        return default

    return PublishSettings(
        per_target={
            name: TargetTemplates(
                title=pick(name, _TITLE_KEY, DEFAULT_TEMPLATES.title),
                description=pick(name, _DESCRIPTION_KEY, DEFAULT_TEMPLATES.description),
            )
            for name in targets
        }
    )

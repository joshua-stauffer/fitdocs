"""Read and validate ``post-template.toml`` (post-templates Req 1, 5.5).

Pure apart from the one read in :func:`load_post_template`: it opens no index
(Req 1.15). Validation collects every problem across keys, so one run can
report them all; each problem names the file and the key, and for a grammar
problem the line and column within that key's text.
"""

from __future__ import annotations

import hashlib
import json
import os
import tomllib
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final

from fitdocs.layout import POST_TEMPLATE_FILE, post_template_path
from fitdocs.publish.template import (
    TargetTemplates,
    Template,
    TemplateSyntaxError,
    is_placeholder_name,
    parse_template,
    template_names,
)
from fitdocs.publish.values import PLACEHOLDERS, has_control_character
from fitdocs.settings import SettingsError

__all__ = [
    "POST_TEMPLATE_FILE",
    "PostTemplate",
    "PostTemplateError",
    "Variable",
    "load_post_template",
    "parse_post_template",
]

_ALLOWED_KEYS: Final = ("since", "title", "description", "vars")
_REQUIRED_KEYS: Final = ("since", "title")
_COMMENT_MARKERS: Final = ("<!--", "-->", "--!>")


@dataclass(frozen=True)
class Variable:
    name: str
    sql: str


@dataclass(frozen=True)
class PostTemplate:
    path: Path
    since: date
    templates: TargetTemplates
    variables: tuple[Variable, ...]  # sorted by name
    digest: str


class PostTemplateError(SettingsError):
    """A post template that cannot be used, with every problem found."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("\n".join(problems))
        self.problems = problems


def _digest(title: str, description: str, variables: tuple[Variable, ...]) -> str:
    payload = json.dumps(
        [title, description, [[v.name, v.sql.rstrip("\r\n")] for v in variables]],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_text(
    key: str,
    value: object,
    *,
    where: str,
    names: Collection[str],
    problems: list[str],
    single_line: bool,
) -> Template | None:
    """Check one text key; the parsed template, or None when it did not parse."""
    if not isinstance(value, str):
        problems.append(f"{where}: {key}: must be text")
        return None
    if single_line and has_control_character(value):
        problems.append(
            f"{where}: {key}: must be one line, with no control character "
            "or line or paragraph separator"
        )
    for marker in _COMMENT_MARKERS:
        if marker in value:
            problems.append(
                f"{where}: {key}: must not contain {marker!r}, "
                "which can damage the page's region markers"
            )
    try:
        return parse_template(value, names=names)
    except TemplateSyntaxError as exc:
        problems.append(
            f"{where}: {key}: line {exc.line}, column {exc.column} "
            f"of the value: {exc.reason}"
        )
        return None


def parse_post_template(data: bytes, *, path: Path) -> PostTemplate:
    """Validate ``data``; raise :class:`PostTemplateError` listing every problem."""
    where = str(path)
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PostTemplateError((f"{where}: is not valid UTF-8: {exc}",)) from exc
    try:
        document = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise PostTemplateError((f"{where}: is not valid TOML: {exc}",)) from exc

    problems: list[str] = []

    for key in _REQUIRED_KEYS:
        if key not in document:
            problems.append(f"{where}: {key}: required key is missing")
    for key in document:
        if key not in _ALLOWED_KEYS:
            problems.append(f"{where}: {key}: not a recognized key")

    since = document.get("since")
    since_ok = type(since) is date
    if "since" in document and not since_ok:
        problems.append(
            f"{where}: since: must be a TOML date without a time, "
            "written like since = 2026-11-07"
        )

    raw_vars = document.get("vars", {})
    variables: dict[str, str] = {}
    shape: list[str] = []  # reported after title and description
    if not isinstance(raw_vars, dict):
        shape.append(f"{where}: vars: must be a table of tables, one per variable")
        raw_vars = {}
    for name, entry in raw_vars.items():
        key = f"vars.{name}"
        if not isinstance(entry, dict):
            shape.append(f"{where}: {key}: must be a table holding exactly `sql`")
            continue
        if "sql" not in entry:
            shape.append(f"{where}: {key}: lacks the key `sql`")
        for other in entry:
            if other != "sql":
                shape.append(f"{where}: {key}: holds the unknown key {other!r}")
        if "sql" in entry:
            if isinstance(entry["sql"], str):
                variables[name] = entry["sql"]
            else:
                shape.append(f"{where}: {key}.sql: must be text")

    names = (*PLACEHOLDERS, *raw_vars)
    title = (
        _parse_text(
            "title",
            document.get("title"),
            where=where,
            names=names,
            problems=problems,
            single_line=True,
        )
        if "title" in document
        else None
    )
    description = (
        _parse_text(
            "description",
            document["description"],
            where=where,
            names=names,
            problems=problems,
            single_line=False,
        )
        if "description" in document
        else parse_template("", names=names)
    )

    problems.extend(shape)
    used: frozenset[str] | None = None
    if title is not None and description is not None:
        used = template_names(title) | template_names(description)
    for name in raw_vars:
        key = f"vars.{name}"
        if not is_placeholder_name(name):
            problems.append(
                f"{where}: {key}: the name must be lowercase letters, digits and "
                "underscores, starting with a letter"
            )
        elif name in PLACEHOLDERS:
            problems.append(f"{where}: {key}: the name is a page placeholder")
        elif used is not None and name not in used:
            problems.append(
                f"{where}: {key}: the variable is not used by title or description"
            )

    if problems or not isinstance(since, date) or title is None or description is None:
        raise PostTemplateError(tuple(problems))

    ordered = tuple(Variable(n, variables[n]) for n in sorted(variables))
    return PostTemplate(
        path=path,
        since=since,
        templates=TargetTemplates(title, description),
        variables=ordered,
        digest=_digest(title.source, description.source, ordered),
    )


def load_post_template(data_root: Path) -> PostTemplate | None:
    """The data root's post template, or None when there is no file (Req 1.3)."""
    path = post_template_path(data_root)
    if not os.path.lexists(path):
        return None
    if path.is_symlink():
        raise PostTemplateError((f"{path}: is a symlink, not a file",))
    if not path.is_file():
        raise PostTemplateError((f"{path}: is not a regular file",))
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise PostTemplateError((f"{path}: could not be read: {exc}",)) from exc
    return parse_post_template(data, path=path)

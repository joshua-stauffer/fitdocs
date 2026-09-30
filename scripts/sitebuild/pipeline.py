"""Orchestrate one build into one root, with location and failure guarantees.

Requirements 2.9, 6.6 and 6.7.

``build`` clears the managed paths of the root first, so no earlier site survives
into a failed run. It then loads the content and the template, runs every
script-level check in memory, and reports all their problems in one outcome
(2.9). Only a clean plan is written and handed to the generator, and ``html/``
exists afterwards if and only if the build succeeded (6.6). ``guard_root`` keeps
every write inside ``website/build/`` when the root is in the repository (6.7).
Standard library plus ``scripts.sitebuild``.
"""

from __future__ import annotations

import os
import posixpath
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from scripts.sitebuild.config import (
    TEMPLATE_PATH,
    check_config,
    dump_config,
    load_template,
    referenced_assets,
    render_config,
)
from scripts.sitebuild.content import load_content
from scripts.sitebuild.generator import run_build
from scripts.sitebuild.links import check_links
from scripts.sitebuild.model import Problem
from scripts.sitebuild.outline import nav_structure, render_llms, render_llms_full
from scripts.sitebuild.stage import HTML, STAGED, plan_tree, write_tree

DEFAULT_BUILD_ROOT: Final = Path("website/build/site")
DEFAULT_PREVIEW_ROOT: Final = Path("website/build/preview")

_BUILD_DIR: Final = Path("website/build")
_LLMS_FIELDS: Final[tuple[str, ...]] = ("site_name", "site_description", "site_url")


class BuildRootRefused(Exception):
    """The build root is inside the repository but not under ``website/build/``."""


@dataclass(frozen=True)
class BuildOutcome:
    ok: bool
    problems: tuple[Problem, ...]
    generator_output: str  # "" when the generator did not run
    tree: Mapping[str, bytes] | None  # None when a script-level check failed
    page_count: int


def guard_root(root: Path, *, repo_root: Path) -> Path:
    """The resolved root, or ``BuildRootRefused`` for a repository path elsewhere.

    ``..`` and symbolic links are resolved first. Containment is then decided by
    file identity (``os.path.samefile``) and not by path text, because
    ``Path.resolve`` does not fold letter case on a case-insensitive filesystem
    or follow macOS firmlinks. A root that is the repository or one of its
    ancestors is refused, since clearing its managed paths would reach outside
    ``website/build/``. A root elsewhere outside the repository is allowed; one
    inside it must lie strictly under ``<repo_root>/website/build/``, where the
    ``build`` directory is named exactly as ``website/build`` names it.
    """
    resolved = root.resolve()
    chain = [resolved, *resolved.parents]
    website = repo_root / _BUILD_DIR.parent
    if (
        _index_of([repo_root.resolve(), *repo_root.resolve().parents], resolved)
        is not None
    ):
        raise BuildRootRefused(
            f"refusing to build into {resolved}: it is the repository or one of "
            "its parent directories"
        )
    if _index_of(chain, repo_root) is None:
        return resolved
    at = _index_of(chain, website)
    if at is None or at < 2 or chain[at - 1].name != _BUILD_DIR.name:
        raise BuildRootRefused(
            f"refusing to build into {resolved}: inside the repository, "
            f"a build root must be under {repo_root.resolve() / _BUILD_DIR}"
        )
    return resolved


def _index_of(chain: list[Path], target: Path) -> int | None:
    """The first position in ``chain`` that is the same file as ``target``."""
    for index, candidate in enumerate(chain):
        try:
            if os.path.samefile(candidate, target):
                return index
        except OSError:
            continue
    return None


def build(content_dir: Path, root: Path, *, repo_root: Path) -> BuildOutcome:
    """Build the site for ``content_dir`` into ``root`` and report every problem."""
    root = guard_root(root, repo_root=repo_root)
    if root.is_dir():
        write_tree({}, root)  # removes the managed paths, html/ included

    content, problems = load_content(content_dir)
    template, template_problems = load_template(repo_root / TEMPLATE_PATH)
    collected: list[Problem] = list(problems)
    collected += (
        Problem(TEMPLATE_PATH.as_posix(), p.where, p.message) for p in template_problems
    )

    tree: dict[str, bytes] | None = None
    if content is not None:
        collected += check_links(content, repo_root=repo_root)
        if template is not None:
            fields, field_problems = _llms_fields(template)
            collected += field_problems
            config = render_config(template, nav_structure(content))
            collected += check_config(config, template)
            if fields is not None:
                site_name, summary, site_url = fields
                tree = plan_tree(
                    content,
                    config_text=dump_config(config),
                    llms=render_llms(
                        content,
                        site_name=site_name,
                        summary=summary,
                        site_url=site_url,
                    ),
                    llms_full=render_llms_full(content, site_url=site_url),
                    assets_dir=repo_root / "website" / "assets",
                    overrides_dir=repo_root / "website" / "overrides",
                )
                collected += _missing_assets(config, tree)

    page_count = len(content.pages) if content is not None else 0
    if collected:
        return BuildOutcome(False, tuple(collected), "", None, page_count)

    assert tree is not None  # no problems means the content and template loaded
    write_tree(tree, root)
    try:
        result = run_build(root)
    except BaseException:
        _remove_html(root)
        raise
    if not result.ok:
        _remove_html(root)
    return BuildOutcome(result.ok, result.problems, result.output, tree, page_count)


def _llms_fields(
    template: Mapping[str, object],
) -> tuple[tuple[str, str, str] | None, tuple[Problem, ...]]:
    """The template's ``site_name``, ``site_description`` and ``site_url`` as text."""
    problems = tuple(
        Problem(
            TEMPLATE_PATH.as_posix(),
            key,
            f"{key} is required by the llms.txt files and must be text",
        )
        for key in _LLMS_FIELDS
        if not isinstance(template.get(key), str)
    )
    if problems:
        return None, problems
    name, summary, url = (str(template[key]) for key in _LLMS_FIELDS)
    return (name, summary, url), ()


def _missing_assets(
    config: Mapping[str, object], tree: Mapping[str, bytes]
) -> list[Problem]:
    """A problem for each referenced path that the planned ``staged/`` lacks."""
    problems: list[Problem] = []
    for ref in dict.fromkeys(referenced_assets(config)):
        if f"{STAGED}/{posixpath.normpath(ref)}" not in tree:
            problems.append(
                Problem(
                    TEMPLATE_PATH.as_posix(),
                    "",
                    f"{ref} is referenced by the template but is not in the built "
                    f"site (looked for {STAGED}/{ref})",
                )
            )
    return problems


def _remove_html(root: Path) -> None:
    """Delete the generator's output; ``root`` is a guarded build root."""
    html = root / HTML
    if html.is_symlink() or html.is_file():
        html.unlink()
    elif html.is_dir():
        shutil.rmtree(html)


__all__ = [
    "DEFAULT_BUILD_ROOT",
    "DEFAULT_PREVIEW_ROOT",
    "BuildOutcome",
    "BuildRootRefused",
    "build",
    "guard_root",
]

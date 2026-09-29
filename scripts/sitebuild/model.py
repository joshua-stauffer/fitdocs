"""The content contract and the value types every build module shares.

This module is the single definition of the section list, the frontmatter keys
and the reserved names (2.1, 2.2, 2.3). It is pure data: standard library only,
no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

SECTIONS: Final[tuple[str, ...]] = (
    "Home",
    "Why",
    "Get started",
    "Guides",
    "Working with LLMs",
    "Reference",
    "Extend",
    "Project",
)
REQUIRED_KEYS: Final[tuple[str, ...]] = ("title", "description", "section", "order")
OPTIONAL_KEYS: Final[tuple[str, ...]] = ("draft",)
HERO_KEYS: Final[tuple[str, ...]] = ("hero_title", "hero_tagline", "hero_actions")
# label and href are required; primary is optional.
HERO_ACTION_KEYS: Final[tuple[str, ...]] = ("label", "href", "primary")
HOME_PAGE: Final = "index.md"
HOME_TEMPLATE: Final = "home.html"
RESERVED_ROOT_NAMES: Final[tuple[str, ...]] = ("llms.txt", "llms-full.txt")
# Build-owned staged directory, unreachable by content (1.4).
BRAND_DIR: Final = "_brand"
CONTENT_ENV_VAR: Final = "FITDOCS_SITE_CONTENT"
ANNOTATION_MARKER: Final = "\n\n---\nAnnotations:"


class ContentSource(StrEnum):
    """Where the content directory path came from (named in 1.2 messages)."""

    OPTION = "--content"
    ENVIRONMENT = "FITDOCS_SITE_CONTENT"
    DEFAULT = "default website/content/"


@dataclass(frozen=True)
class ResolvedContent:
    path: Path
    source: ContentSource


@dataclass(frozen=True)
class Problem:
    """One violation. ``render`` is the one line format (2.9, 6.5, 7.3)."""

    path: str  # content-relative POSIX path; "" when none applies;
    # "site generator" for path-less generator errors
    where: str  # frontmatter key, "line:col", or ""
    message: str

    def render(self) -> str:
        """Render the problem as one line.

        Each field becomes ``" ".join(field.splitlines())``, so no line break
        survives and a trailing one leaves nothing behind. A field that is empty
        after that is dropped, and the rest are joined with ``": "``. Other
        whitespace is kept as written.
        """
        fields = (
            " ".join(f.splitlines()) for f in (self.path, self.where, self.message)
        )
        return ": ".join(f for f in fields if f)


@dataclass(frozen=True)
class HeroAction:
    label: str
    href: str  # absolute https:// URL, or a non-empty trailing-slash site path
    primary: bool


@dataclass(frozen=True)
class Page:
    path: str  # content-relative POSIX path ending ".md"
    title: str
    description: str
    section: str  # a member of SECTIONS
    order: int
    staged_text: (
        str  # file text with the annotation block removed (frontmatter included)
    )
    body: str  # staged_text without its frontmatter
    hero_title: str | None
    hero_tagline: str | None
    hero_actions: tuple[HeroAction, ...] | None


@dataclass(frozen=True)
class Asset:
    path: str  # content-relative POSIX path
    source: Path


@dataclass(frozen=True)
class SiteContent:
    root: Path
    pages: tuple[Page, ...]  # included, non-draft pages; sorted by path
    assets: tuple[Asset, ...]  # included non-markdown files; sorted by path

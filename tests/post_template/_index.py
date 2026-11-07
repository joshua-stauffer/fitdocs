"""A synthetic data root with a built index, shared by the post-template tests.

The pages are written by hand and indexed by the real `fitdocs index` command,
so the index rows are the ones production reads. Start times, loads and page
keys are pairwise distinct, so a lookup by any one of them names one page.

Calendar (2021, Monday 6 September starts the first week):

| page | start (naive local)  | load | week |
|------|----------------------|------|------|
| MON  | 2021-09-06 07:10:00  | 35   | threshold |
| AM   | 2021-09-08 06:05:00  | 45   | threshold, same day as PM |
| PM   | 2021-09-08 17:40:00  | 25   | threshold, same day as AM |
| REST | 2021-09-15 08:20:00  | 0    | the next week, zero load |

The design's example share (a page's load over the week's load up to its own
start, as a rounded percentage) gives 100 for MON, 56 for AM, 24 for PM and
NULL for REST.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Timer

from typer.testing import CliRunner

from fitdocs import contract
from fitdocs.cli import app
from fitdocs.docmerge import region_block
from fitdocs.index.location import resolve_index_location
from fitdocs.query.command import QueryEnvironment
from tests.query._helpers import FIXTURE_TODAY, copy_indexed_root

#: The recorded offset of every fixture page. The index drops it.
OFFSET = timezone(timedelta(hours=2))

#: The design's example (brief, "The template").
EXAMPLE_SQL = """SELECT round(100 * max(load_value) FILTER (page_key = $page_key)
             / NULLIF(sum(load_value), 0))::INT
FROM pages
WHERE date >= date_trunc('week', $as_of)
  AND start_time_local <= $as_of
"""


@dataclass(frozen=True)
class FixturePage:
    name: str
    path: str  # data-root-relative POSIX
    key: str  # the base archive digest
    start: datetime  # naive local, as the index records it
    load: float

    @property
    def aware_start(self) -> datetime:
        return self.start.replace(tzinfo=OFFSET)


def _page(name: str, start: datetime, load: float) -> FixturePage:
    # Distinct 64-hex keys with no shared prefix or suffix, so a truncated key
    # cannot stand for another page's.
    key = hashlib.sha256(name.encode()).hexdigest()
    stamp = start.strftime("%Y-%m-%d-%H%M")
    return FixturePage(name, f"workouts/{stamp}-run.md", key, start, load)


MON = _page("MON", datetime(2021, 9, 6, 7, 10, 0), 35.0)
AM = _page("AM", datetime(2021, 9, 8, 6, 5, 0), 45.0)
PM = _page("PM", datetime(2021, 9, 8, 17, 40, 0), 25.0)
REST = _page("REST", datetime(2021, 9, 15, 8, 20, 0), 0.0)
PAGES: tuple[FixturePage, ...] = (MON, AM, PM, REST)

#: The share the example gives for each page.
EXAMPLE_SHARE: Mapping[str, int | None] = {"MON": 100, "AM": 56, "PM": 24, "REST": None}


def page_text(page: FixturePage, *, post: str = contract.POST_PLACEHOLDER) -> str:
    """The text of a page: frontmatter, a notes region and the `post` region."""
    start = page.aware_start.isoformat()
    return (
        "---\n"
        f"title: Run {page.name}\n"
        f"type: {contract.WORKOUT_TYPE}\n"
        "generator: fitdocs\n"
        f"doc_version: {contract.DOC_VERSION}\n"
        f"date: {page.start.date().isoformat()}\n"
        f"start_time: '{start}'\n"
        "sport: Run\n"
        "modality: run\n"
        f"sources: [fit-archive/{page.key}.fit]\n"
        f"load_value: {page.load}\n"
        "load_methodology: threshold\n"
        "load_basis: pace\n"
        "---\n\n"
        f"# Run {page.name}\n\n"
        + region_block("notes", "")
        + "\n"
        + region_block("load", contract.LOAD_NOT_COMPUTED)
        + "\n"
        + region_block("post", post)
    )


@dataclass(frozen=True)
class IndexedPostRoot:
    """A data root with a built index, and the environment that finds it."""

    root: Path
    index_dir: Path
    home: Path
    environ: Mapping[str, str]
    pages: tuple[FixturePage, ...]

    def query_environment(
        self,
        *,
        pid: int = 74123,
        on_wait: Callable[[int | None], None] | None = None,
    ) -> QueryEnvironment:
        return QueryEnvironment(
            environ=dict(self.environ),
            home=self.home,
            pid=pid,
            monotonic=lambda: 0.0,
            sleep=lambda _delay: None,
            on_wait=on_wait if on_wait is not None else (lambda _pid: None),
            is_running=lambda _pid: False,
            timer=Timer,
        )


def build_indexed_post_root(base: Path) -> IndexedPostRoot:
    """Write the fixture pages under `base/data` and build the index.

    The caller must have set HOME and FITDOCS_INDEX_DIR for the current process
    (the real command resolves the index location from them), and patched the
    command's `_today` if it matters; `base` is a fresh empty directory.
    """
    root = base / "data"
    (root / "workouts").mkdir(parents=True)
    home = base / "home"
    home.mkdir(exist_ok=True)
    (root / "fitdocs.toml").write_text("[tiles]\nenabled = false\n", encoding="utf-8")
    for page in PAGES:
        (root / page.path).write_text(page_text(page), encoding="utf-8")
    indexed = CliRunner().invoke(app, ["index", "--out", str(root)])
    assert indexed.exit_code == 0, indexed.output
    location = resolve_index_location(root, os.environ, home)
    return IndexedPostRoot(
        root=root,
        index_dir=location.directory,
        home=home,
        environ={"HOME": str(home), "FITDOCS_INDEX_DIR": str(base / "index-cache")},
        pages=PAGES,
    )


def copy_post_root(fixture: IndexedPostRoot, dst: Path) -> IndexedPostRoot:
    """A writable copy with its own data root, index and environment."""
    root, index_dir = copy_indexed_root(fixture.root, fixture.index_dir, dst)
    home = dst / "home"
    return IndexedPostRoot(
        root=root,
        index_dir=index_dir,
        home=home,
        environ={"HOME": str(home), "FITDOCS_INDEX_DIR": str(dst / "index-cache")},
        pages=fixture.pages,
    )


__all__ = [
    "AM",
    "EXAMPLE_SHARE",
    "EXAMPLE_SQL",
    "FIXTURE_TODAY",
    "MON",
    "OFFSET",
    "PAGES",
    "PM",
    "REST",
    "FixturePage",
    "IndexedPostRoot",
    "build_indexed_post_root",
    "copy_post_root",
    "page_text",
]

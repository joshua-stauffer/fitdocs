"""The shared indexed data root for the post-template tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.post_template._index import (
    FIXTURE_TODAY,
    IndexedPostRoot,
    build_indexed_post_root,
    copy_post_root,
)


@pytest.fixture(scope="module")
def indexed_post_root(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[IndexedPostRoot]:
    """Read-only: four pages, indexed once per test module. Copy to mutate."""
    base = tmp_path_factory.mktemp("post-template-indexed")
    with pytest.MonkeyPatch.context() as isolated:
        isolated.setenv("HOME", str(base / "home"))
        isolated.setenv("FITDOCS_INDEX_DIR", str(base / "index-cache"))
        isolated.delenv("XDG_CACHE_HOME", raising=False)
        import fitdocs.cli as cli_module

        isolated.setattr(cli_module, "_today", lambda: FIXTURE_TODAY)
        (base / "home").mkdir()
        yield build_indexed_post_root(base)


@pytest.fixture
def post_root_copy(
    indexed_post_root: IndexedPostRoot, per_test_directory: Callable[[str], Path]
) -> IndexedPostRoot:
    """A private writable copy of the indexed root."""
    return copy_post_root(indexed_post_root, per_test_directory("post-root"))

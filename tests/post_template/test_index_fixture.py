"""The shared indexed data root holds what its docstring says it holds.

2.4 and the engine's integration cases rely on these facts, so they are pinned
here rather than rediscovered through a failing resolver test.
"""

from __future__ import annotations

from datetime import date

from fitdocs.query.command import QuerySession, open_session
from tests.post_template._index import (
    AM,
    EXAMPLE_SHARE,
    EXAMPLE_SQL,
    MON,
    PAGES,
    PM,
    REST,
    IndexedPostRoot,
    page_text,
)


def _session(fixture: IndexedPostRoot) -> QuerySession:
    session = open_session(fixture.root, fixture.query_environment())
    assert isinstance(session, QuerySession)
    return session


def test_starts_loads_and_keys_are_pairwise_distinct() -> None:
    assert len({page.start for page in PAGES}) == len(PAGES)
    assert len({page.load for page in PAGES}) == len(PAGES)
    assert len({page.key for page in PAGES}) == len(PAGES)
    assert len({page.path for page in PAGES}) == len(PAGES)
    assert all(len(page.key) == 64 for page in PAGES)


def test_the_weeks_and_the_shared_day_are_as_documented() -> None:
    week = {page.name: page.start.isocalendar()[:2] for page in PAGES}
    assert week["MON"] == week["AM"] == week["PM"] != week["REST"]
    assert AM.start.date() == PM.start.date() and AM.start < PM.start
    assert MON.start.date() < AM.start.date()
    assert REST.load == 0.0 and all(p.load > 0 for p in (MON, AM, PM))
    assert REST.start.date() > date(2021, 9, 12)  # the next Monday-based week


def test_the_index_holds_each_page_as_the_fixture_describes_it(
    indexed_post_root: IndexedPostRoot,
) -> None:
    session = _session(indexed_post_root)
    try:
        result = session.run(
            "SELECT page_key, path, start_time_local, load_value FROM pages "
            "ORDER BY start_time_local",
            params={},
            max_rows=10,
            timeout_s=10.0,
        )
        assert result.rows == tuple(
            (page.key, page.path, page.start, page.load) for page in PAGES
        )
        for page in PAGES:
            data = (indexed_post_root.root / page.path).read_bytes()
            assert data == page_text(page).encode("utf-8")
            assert session.page_is_current(page.key, page.path, data) is True
    finally:
        session.close()


def test_the_design_example_gives_each_page_its_documented_share(
    indexed_post_root: IndexedPostRoot,
) -> None:
    session = _session(indexed_post_root)
    try:
        shares = {}
        for page in PAGES:
            result = session.run(
                EXAMPLE_SQL,
                params={"as_of": page.start, "page_key": page.key},
                max_rows=2,
                timeout_s=10.0,
            )
            assert len(result.rows) == 1
            shares[page.name] = result.rows[0][0]
        assert shares == EXAMPLE_SHARE
    finally:
        session.close()


def test_every_page_is_current_and_in_the_post_waiting_state(
    indexed_post_root: IndexedPostRoot,
) -> None:
    from datetime import date

    from fitdocs.post_template.engine import PageRead, read_for_fill
    from fitdocs.post_template.model import RegionState
    from fitdocs.publish.pages import select_pages

    pages = select_pages(indexed_post_root.root, (), cwd=indexed_post_root.root)
    assert len(pages) == len(PAGES)
    for selected in pages:
        read = read_for_fill(selected, since=date(2021, 1, 1), ledgers=[])
        assert isinstance(read, PageRead), read
        assert read.state is RegionState.WAITING

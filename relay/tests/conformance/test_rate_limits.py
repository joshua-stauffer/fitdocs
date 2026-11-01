"""Fixed-window request counting on both backends."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw
from tests.conftest import StateStore

from fitdocs_relay.storage.interface import RateDecision, StorageUnreachable

WINDOW = 60
START = 1_700_000_040  # a multiple of WINDOW
KEY = "token:alpha"


def rows(target: Target) -> list[tuple[str, int, int, int]]:
    return [
        (str(k), int(s), int(c), int(e))
        for k, s, c, e in raw(
            target,
            "SELECT key, window_start, count, window_end FROM rate_counts "
            "ORDER BY key, window_start",
        )
    ]


def test_the_fixture_start_is_a_window_boundary() -> None:
    assert START % WINDOW == 0


@pytest.mark.covers("RateLimitStore.count_request")
def test_counts_up_to_the_limit_are_allowed_and_the_next_is_not(
    state_store: StateStore,
) -> None:
    def count(now: int) -> RateDecision:
        return state_store.count_request(key=KEY, window_s=WINDOW, limit=3, now=now)

    # never 0 and never a number when allowed: retry_after_s is None
    assert count(START + 1) == RateDecision(True, 1, None)
    assert count(START + 2) == RateDecision(True, 2, None)
    assert count(START + 3) == RateDecision(True, 3, None)  # exactly at the limit
    # over the limit: the count keeps rising; the wait is to the window's end
    assert count(START + 25) == RateDecision(False, 4, 35)
    assert count(START + 58) == RateDecision(False, 5, 2)


@pytest.mark.covers("RateLimitStore.count_request")
def test_a_limit_of_one_allows_exactly_the_first_request(
    state_store: StateStore,
) -> None:
    first = state_store.count_request(key=KEY, window_s=WINDOW, limit=1, now=START)
    second = state_store.count_request(key=KEY, window_s=WINDOW, limit=1, now=START)
    assert first == RateDecision(True, 1, None)
    # a request at the window's first second waits the whole window
    assert second == RateDecision(False, 2, WINDOW)


@pytest.mark.covers("RateLimitStore.count_request")
def test_the_window_starts_at_now_minus_now_modulo_the_window(
    database_target: Target, state_store: StateStore
) -> None:
    window = 45
    now = 1_700_000_003
    offset = now % window
    assert offset not in (
        0,
        window - 1,
    )  # now is neither a boundary nor the last second
    assert rows(database_target) == []  # nothing counted yet
    state_store.count_request(key=KEY, window_s=window, limit=9, now=now)
    start = now - offset
    assert rows(database_target) == [(KEY, start, 1, start + window)]


@pytest.mark.covers("RateLimitStore.count_request")
def test_a_new_window_starts_exactly_at_the_old_windows_end_and_the_old_row_goes(
    database_target: Target, state_store: StateStore
) -> None:
    for offset in (1, 2, 59):
        state_store.count_request(key=KEY, window_s=WINDOW, limit=1, now=START + offset)
    assert rows(database_target) == [(KEY, START, 3, START + WINDOW)]

    # now == the old window_end belongs to the next window: counted from 1
    decision = state_store.count_request(
        key=KEY, window_s=WINDOW, limit=1, now=START + WINDOW
    )

    assert decision == RateDecision(True, 1, None)
    assert rows(database_target) == [
        (KEY, START + WINDOW, 1, START + 2 * WINDOW)
    ]  # the ended window's row is gone from storage


@pytest.mark.covers("RateLimitStore.count_request")
def test_ended_windows_of_every_key_are_deleted_and_a_live_one_is_kept(
    database_target: Target, state_store: StateStore
) -> None:
    other = "client:beta"
    state_store.count_request(key=other, window_s=WINDOW, limit=5, now=START + 10)
    assert rows(database_target) == [(other, START, 1, START + WINDOW)]

    # one second before the other key's window ends: its row stays
    state_store.count_request(key=KEY, window_s=WINDOW, limit=5, now=START + 59)
    assert rows(database_target) == [
        (other, START, 1, START + WINDOW),
        (KEY, START, 1, START + WINDOW),
    ]

    # at its window_end: the other key's row is deleted by this key's count
    state_store.count_request(key=KEY, window_s=WINDOW, limit=5, now=START + WINDOW)
    assert rows(database_target) == [(KEY, START + WINDOW, 1, START + 2 * WINDOW)]


@pytest.mark.covers("RateLimitStore.count_request")
def test_keys_are_counted_separately(state_store: StateStore) -> None:
    for expected in (1, 2):
        decision = state_store.count_request(
            key="a", window_s=WINDOW, limit=2, now=START + expected
        )
        assert decision.count == expected
    assert state_store.count_request(
        key="b", window_s=WINDOW, limit=2, now=START + 3
    ) == RateDecision(True, 1, None)
    assert state_store.count_request(
        key="a", window_s=WINDOW, limit=2, now=START + 4
    ) == RateDecision(False, 3, 56)


@pytest.mark.covers("RateLimitStore.count_request", "StorageBase.close")
def test_counts_survive_a_restart_of_the_storage_object(
    open_state_store: Callable[[Target | None], StateStore],
) -> None:
    first = open_state_store(None)
    for offset in (1, 2):
        first.count_request(key=KEY, window_s=WINDOW, limit=2, now=START + offset)
    first.close()

    second = open_state_store(None)

    assert second.count_request(
        key=KEY, window_s=WINDOW, limit=2, now=START + 3
    ) == RateDecision(False, 3, 57)


@pytest.mark.covers("RateLimitStore.count_request")
def test_counting_on_a_closed_store_is_unreachable(state_store: StateStore) -> None:
    state_store.close()
    with pytest.raises(StorageUnreachable):
        state_store.count_request(key=KEY, window_s=WINDOW, limit=1, now=START)


HOUR = 3600
HOUR_START = 1_700_000_000 - 1_700_000_000 % HOUR


@pytest.mark.covers("RateLimitStore.count_request")
def test_a_window_ends_by_its_own_length_not_the_requests_window_length(
    database_target: Target, state_store: StateStore
) -> None:
    assert HOUR_START % WINDOW == 0
    base = HOUR_START

    def count(key: str, window_s: int, now: int) -> None:
        state_store.count_request(key=key, window_s=window_s, limit=9, now=now)

    count("a", HOUR, base + 5)
    count("c", WINDOW, base + 10)
    assert rows(database_target) == [
        ("a", base, 1, base + HOUR),
        ("c", base, 1, base + WINDOW),
    ]

    # a 60 s request two minutes in: the ended 60 s row goes, the hour row stays
    count("b", WINDOW, base + 120)
    assert rows(database_target) == [
        ("a", base, 1, base + HOUR),
        ("b", base + 120, 1, base + 180),
    ]

    # an hour-window request at b's window_end deletes b's ended 60 s row
    count("d", HOUR, base + 180)
    assert rows(database_target) == [
        ("a", base, 1, base + HOUR),
        ("d", base, 1, base + HOUR),
    ]

    # at the hour's end both hour rows go
    count("e", WINDOW, base + HOUR)
    assert rows(database_target) == [("e", base + HOUR, 1, base + HOUR + WINDOW)]

"""Both backends under contention: 20 threads, started together by a barrier."""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw

from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    RateDecision,
    RevokeResult,
    Storage,
    TokenRecord,
)

THREADS = 20
WINDOW = 60
START = 1_700_000_040  # a multiple of WINDOW
T1, T2, T3 = 1_700_000_001, 1_700_000_002, 1_700_000_003

OpenFull = Callable[[], Storage]


@pytest.fixture(params=["one-shared-object", "an-object-per-thread"])
def storages(
    request: pytest.FixtureRequest, open_full_storage: OpenFull
) -> list[Storage]:
    """`THREADS` entries: the same object for each thread, or one object each."""
    if request.param == "one-shared-object":
        shared = open_full_storage()
        return [shared] * THREADS
    return [open_full_storage() for _ in range(THREADS)]


def race(count: int, work: Callable[[int], object]) -> list[object]:
    """Run `work(i)` on `count` threads released together; results by index.

    A raised exception is the result for its index.
    """
    results: list[object] = [None] * count
    barrier = threading.Barrier(count)

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = work(index)
        except BaseException as error:  # noqa: BLE001 - reported to the test
            results[index] = error

    threads = [
        threading.Thread(target=run, args=(i,), daemon=True) for i in range(count)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a thread hung"
    return results


@pytest.mark.covers("RateLimitStore.count_request")
def test_twenty_threads_counting_one_key_count_each_request_once(
    database_target: Target, storages: list[Storage]
) -> None:
    assert len(storages) == THREADS
    assert raw(database_target, "SELECT count(*) FROM rate_counts") == [(0,)]
    limit = 7
    results = race(
        THREADS,
        lambda i: storages[i].count_request(
            key="token:race", window_s=WINDOW, limit=limit, now=START + 1
        ),
    )
    decisions = [r for r in results if isinstance(r, RateDecision)]
    assert len(decisions) == THREADS, f"a count failed: {results}"
    # each thread saw a different count: 1..20 once each, none lost, none doubled
    assert sorted(d.count for d in decisions) == list(range(1, THREADS + 1))
    assert sorted(d.count for d in decisions if d.allowed) == list(range(1, limit + 1))
    assert raw(database_target, "SELECT key, count FROM rate_counts") == [
        ("token:race", THREADS)
    ]


@pytest.mark.covers("RecordStore.put_record", "RecordStore.take_record")
def test_exactly_one_of_twenty_racing_takes_wins(
    database_target: Target, storages: list[Storage]
) -> None:
    assert raw(database_target, "SELECT count(*) FROM records") == [(0,)]
    for round_number in range(5):
        key = f"once-{round_number}"
        storages[0].put_record(
            namespace="state",
            key=key,
            value=f"payload-{round_number}".encode(),
            expires_at=START + 100,
            now=START,
        )
        assert raw(database_target, "SELECT count(*) FROM records") == [(1,)]

        def take(i: int, key: str = key) -> bytes | None:
            return storages[i].take_record(namespace="state", key=key, now=START + 1)

        results = race(THREADS, take)
        assert [r for r in results if isinstance(r, BaseException)] == []
        assert sorted(r is None for r in results) == [False] + [True] * (THREADS - 1)
        assert [r for r in results if r is not None] == [
            f"payload-{round_number}".encode()
        ]
        assert raw(database_target, "SELECT count(*) FROM records") == [(0,)]


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.create_principal")
@pytest.mark.parametrize("contenders", [2, THREADS])
@pytest.mark.parametrize("owners", ["one-shared-principal", "a-principal-each"])
def test_racing_mints_of_one_token_id_give_one_success_and_the_rest_duplicates(
    contenders: int, owners: str, storages: list[Storage]
) -> None:
    # With one shared principal the mints queue on the principal's row lock
    # before the token insert; a principal each lets them reach the insert together.
    principals = (
        ["quin"] * contenders
        if owners == "one-shared-principal"
        else [f"p{i:02d}" for i in range(contenders)]
    )
    for principal in sorted(set(principals)):
        storages[0].create_principal(NewPrincipal(principal, None), now=T1)
    for round_number in range(5):
        token_id = f"tok-{round_number}"

        def mint(i: int, token_id: str = token_id) -> TokenRecord:
            return storages[i].mint_token(
                NewToken(token_id, f"verifier-{i}", None),
                principal_id=principals[i],
                new_principal=None,
                now=T2,
            )

        results = race(contenders, mint)
        wins = [r for r in results if isinstance(r, TokenRecord)]
        duplicates = [r for r in results if isinstance(r, DuplicateIdentifier)]
        assert len(wins) == 1, results
        assert len(duplicates) == contenders - 1, results
        stored = storages[0].find_token(token_id)
        assert stored is not None
        # the stored token is the winner's, not a blend
        assert stored.verifier == wins[0].verifier


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.create_principal")
def test_racing_mints_with_one_new_principal_give_one_success(
    storages: list[Storage],
) -> None:
    results = race(
        THREADS,
        lambda i: storages[i].mint_token(
            NewToken(f"tok-{i}", f"verifier-{i}", None),
            principal_id=None,
            new_principal=NewPrincipal("pat", None),
            now=T1,
        ),
    )
    assert len([r for r in results if isinstance(r, TokenRecord)]) == 1, results
    assert len([r for r in results if isinstance(r, DuplicateIdentifier)]) == (
        THREADS - 1
    ), results
    assert [p.principal_id for p in storages[0].list_principals()] == ["pat"]
    assert len(storages[0].list_tokens("pat")) == 1


@pytest.mark.covers("TokenStore.revoke_token", "TokenStore.find_token")
def test_a_lookup_that_starts_after_a_revocation_returned_never_sees_an_active_token(
    storages: list[Storage],
) -> None:
    lookups = 5
    looked = threading.Semaphore(0)  # released by each looker's first lookup
    revoked = threading.Event()
    seen: list[list[tuple[bool, TokenRecord | None]]] = [[] for _ in range(lookups)]
    storages[0].create_principal(NewPrincipal("rae", None), now=T1)
    storages[0].mint_token(
        NewToken("tok-rev", "verifier", None),
        principal_id="rae",
        new_principal=None,
        now=T1,
    )

    def work(index: int) -> object:
        if index == 0:
            for _ in range(lookups):
                # every looker has seen the active token
                if not looked.acquire(timeout=30):
                    raise AssertionError("a looker never completed a lookup")
            result = storages[0].revoke_token("tok-rev", now=T2)
            revoked.set()
            return result
        mine = seen[index - 1]
        try:
            while True:
                after = revoked.is_set()  # read before the lookup starts
                record = storages[index].find_token("tok-rev")
                mine.append((after, record))
                if len(mine) == 1:
                    looked.release()
                if after:
                    return None
                if len(mine) > 100_000:
                    raise AssertionError("the revocation never returned")
        finally:
            if not mine:
                looked.release()  # a failed first lookup must not strand the revoker

    results = race(lookups + 1, work)
    assert results[0] is RevokeResult.REVOKED, results
    assert [r for r in results[1:] if r is not None] == []
    flat = [pair for mine in seen for pair in mine]
    # precondition: some lookup began before the revoke and saw the token active
    assert any(
        not after and r is not None and r.revoked_at is None for after, r in flat
    )
    assert all(mine[-1][0] for mine in seen), "a looker stopped before the revoke"
    for after, record in flat:
        assert record is not None
        if after:
            assert record.revoked_at == T2, "an active token after the revoke"

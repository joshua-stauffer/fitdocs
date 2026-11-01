"""Tokens on both backends: mint, find, list, revoke, and the races among them."""

from __future__ import annotations

import dataclasses
import threading
from collections.abc import Callable

import pytest
from tests.conftest import BYTE_ORDER, TIED_IDS, AccountStore

from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    RevokeResult,
    StorageUnreachable,
    TokenRecord,
    TokenSummary,
    UnknownPrincipal,
)

T1, T2, T3, T4, T5 = (
    1_700_000_001,
    1_700_000_002,
    1_700_000_003,
    1_700_000_004,
    1_700_000_005,
)
T6, T7, T8 = 1_700_000_006, 1_700_000_007, 1_700_000_008


def new_token(token_id: str, label: str | None = None) -> NewToken:
    return NewToken(token_id=token_id, verifier=f"verifier-of-{token_id}", label=label)


@pytest.mark.covers("TokenStore.mint_token", "TokenStore.find_token")
def test_minting_for_an_existing_principal_stores_and_returns_the_record(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("amy", None), now=T1)
    minted = account_store.mint_token(
        new_token("tok-1", "laptop"), principal_id="amy", new_principal=None, now=T2
    )
    assert minted == TokenRecord(
        token_id="tok-1",
        principal_id="amy",
        verifier="verifier-of-tok-1",
        label="laptop",
        created_at=T2,
        revoked_at=None,
    )
    assert account_store.find_token("tok-1") == minted
    assert account_store.find_token("tok-2") is None
    assert account_store.get_principal("amy") is not None


@pytest.mark.covers("TokenStore.mint_token", "TokenStore.find_token")
def test_a_token_without_a_label_has_label_none(account_store: AccountStore) -> None:
    account_store.create_principal(NewPrincipal("ben", None), now=T1)
    minted = account_store.mint_token(
        new_token("tok-n"), principal_id="ben", new_principal=None, now=T2
    )
    found = account_store.find_token("tok-n")
    assert minted.label is None
    assert found is not None
    assert found.label is None


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.get_principal")
def test_minting_for_an_unknown_principal_is_refused_and_stores_nothing(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("cat", None), now=T1)
    with pytest.raises(UnknownPrincipal):
        account_store.mint_token(
            new_token("tok-x"), principal_id="ghost", new_principal=None, now=T2
        )
    assert account_store.find_token("tok-x") is None
    assert account_store.get_principal("ghost") is None
    assert [p.principal_id for p in account_store.list_principals()] == ["cat"]


@pytest.mark.covers("TokenStore.mint_token", "TokenStore.find_token")
def test_a_duplicate_token_id_is_refused_even_for_another_principal(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("dan", None), now=T1)
    account_store.create_principal(NewPrincipal("eve", None), now=T2)
    first = account_store.mint_token(
        new_token("tok-d", "first"), principal_id="dan", new_principal=None, now=T3
    )
    with pytest.raises(DuplicateIdentifier):
        account_store.mint_token(
            NewToken("tok-d", "other-verifier", "second"),
            principal_id="eve",
            new_principal=None,
            now=T4,
        )
    assert account_store.find_token("tok-d") == first
    assert account_store.list_tokens("eve") == ()


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.get_principal")
def test_minting_with_a_new_principal_creates_both_together(
    account_store: AccountStore,
) -> None:
    minted = account_store.mint_token(
        new_token("tok-f"),
        principal_id=None,
        new_principal=NewPrincipal("fred", "Fred's club"),
        now=T2,
    )
    assert minted.principal_id == "fred"
    assert minted.created_at == T2
    principal = account_store.get_principal("fred")
    assert principal is not None
    assert (principal.label, principal.created_at) == ("Fred's club", T2)
    assert account_store.find_token("tok-f") == minted


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.get_principal")
def test_a_new_principal_that_already_exists_is_a_duplicate_and_adds_no_token(
    account_store: AccountStore,
) -> None:
    existing = account_store.create_principal(NewPrincipal("gia", "kept"), now=T1)
    with pytest.raises(DuplicateIdentifier):
        account_store.mint_token(
            new_token("tok-g"),
            principal_id=None,
            new_principal=NewPrincipal("gia", "replaced"),
            now=T2,
        )
    assert account_store.find_token("tok-g") is None
    assert account_store.get_principal("gia") == existing


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.get_principal")
def test_a_mint_with_a_new_principal_is_rolled_back_when_the_token_insert_fails(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("hal", None), now=T1)
    original = account_store.mint_token(
        new_token("tok-h"), principal_id="hal", new_principal=None, now=T2
    )
    # Preconditions: the new principal is absent, the token id is taken.
    assert account_store.get_principal("ivy") is None
    assert account_store.find_token("tok-h") is not None

    with pytest.raises(DuplicateIdentifier):
        account_store.mint_token(
            new_token("tok-h"),
            principal_id=None,
            new_principal=NewPrincipal("ivy", None),
            now=T3,
        )

    assert account_store.get_principal("ivy") is None
    assert [p.principal_id for p in account_store.list_principals()] == ["hal"]
    assert account_store.find_token("tok-h") == original


@pytest.mark.parametrize(
    ("principal_id", "new_principal"),
    [("jo", NewPrincipal("jo2", None)), (None, None)],
    ids=["both", "neither"],
)
@pytest.mark.covers("TokenStore.mint_token")
def test_a_mint_must_name_exactly_one_of_the_principal_and_a_new_one(
    account_store: AccountStore,
    principal_id: str | None,
    new_principal: NewPrincipal | None,
) -> None:
    account_store.create_principal(NewPrincipal("jo", None), now=T1)
    with pytest.raises(ValueError, match="exactly one"):
        account_store.mint_token(
            new_token("tok-j"),
            principal_id=principal_id,
            new_principal=new_principal,
            now=T2,
        )
    assert account_store.find_token("tok-j") is None
    assert account_store.get_principal("jo2") is None


@pytest.mark.covers("TokenStore.list_tokens")
def test_listing_tokens_filters_by_principal_and_never_carries_a_verifier(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("kim", None), now=T1)
    account_store.create_principal(NewPrincipal("lou", None), now=T1)
    account_store.mint_token(
        new_token("kim-a", "k1"), principal_id="kim", new_principal=None, now=T2
    )
    account_store.mint_token(
        new_token("lou-a", "l1"), principal_id="lou", new_principal=None, now=T3
    )
    account_store.mint_token(
        new_token("kim-b"), principal_id="kim", new_principal=None, now=T4
    )
    account_store.revoke_token("kim-b", now=T5)
    assert account_store.list_tokens("kim") == (
        TokenSummary("kim-a", "kim", "k1", T2, None),
        TokenSummary("kim-b", "kim", None, T4, T5),
    )
    assert account_store.list_tokens("lou") == (
        TokenSummary("lou-a", "lou", "l1", T3, None),
    )
    assert [t.token_id for t in account_store.list_tokens(None)] == [
        "kim-a",
        "lou-a",
        "kim-b",
    ]
    assert account_store.list_tokens("nobody") == ()
    assert "verifier" not in {f.name for f in dataclasses.fields(TokenSummary)}
    assert all(type(t) is TokenSummary for t in account_store.list_tokens(None)), (
        "a listed token is a summary"
    )


@pytest.mark.covers("TokenStore.list_tokens")
def test_listing_tokens_orders_by_creation_time_then_id_by_bytes_on_both_backends(
    account_store: AccountStore, ids_sort_by_locale_here: None
) -> None:
    assert sorted(TIED_IDS) == BYTE_ORDER
    account_store.create_principal(NewPrincipal("mia", None), now=T1)
    account_store.mint_token(
        new_token("zzz_early"), principal_id="mia", new_principal=None, now=T2
    )
    for token_id in TIED_IDS:
        account_store.mint_token(
            new_token(token_id), principal_id="mia", new_principal=None, now=T4
        )
    account_store.mint_token(
        new_token("0_late"), principal_id="mia", new_principal=None, now=T6
    )
    expected = ["zzz_early", *BYTE_ORDER, "0_late"]
    assert [t.token_id for t in account_store.list_tokens("mia")] == expected
    assert [t.token_id for t in account_store.list_tokens(None)] == expected


@pytest.mark.covers("TokenStore.revoke_token", "TokenStore.find_token")
def test_revoking_sets_the_time_and_touches_no_other_token(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("ned", None), now=T1)
    minted = account_store.mint_token(
        new_token("ned-a"), principal_id="ned", new_principal=None, now=T2
    )
    account_store.mint_token(
        new_token("ned-b"), principal_id="ned", new_principal=None, now=T3
    )
    assert minted.revoked_at is None
    assert account_store.revoke_token("ned-a", now=T5) is RevokeResult.REVOKED
    revoked = account_store.find_token("ned-a")
    assert revoked == dataclasses.replace(minted, revoked_at=T5)
    untouched = account_store.find_token("ned-b")
    assert untouched is not None
    assert untouched.revoked_at is None


@pytest.mark.covers("TokenStore.revoke_token", "TokenStore.find_token")
def test_a_second_revoke_is_reported_and_keeps_the_first_time(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("ola", None), now=T1)
    account_store.mint_token(
        new_token("ola-a"), principal_id="ola", new_principal=None, now=T2
    )
    assert account_store.revoke_token("ola-a", now=T3) is RevokeResult.REVOKED
    assert account_store.revoke_token("ola-a", now=T6) is RevokeResult.ALREADY_REVOKED
    assert account_store.revoke_token("ola-a", now=T7) is RevokeResult.ALREADY_REVOKED
    found = account_store.find_token("ola-a")
    assert found is not None
    assert found.revoked_at == T3
    # The token is still revoked after a later mint for the same principal.
    account_store.mint_token(
        new_token("ola-b"), principal_id="ola", new_principal=None, now=T8
    )
    again = account_store.find_token("ola-a")
    assert again is not None
    assert again.revoked_at == T3


@pytest.mark.covers("TokenStore.revoke_token", "TokenStore.list_tokens")
def test_revoking_an_unknown_token_is_reported_and_stores_nothing(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("pam", None), now=T1)
    account_store.mint_token(
        new_token("pam-a"), principal_id="pam", new_principal=None, now=T2
    )
    assert account_store.revoke_token("pam-zzz", now=T3) is RevokeResult.UNKNOWN
    assert account_store.find_token("pam-zzz") is None
    assert [t.revoked_at for t in account_store.list_tokens(None)] == [None]


def _race(count: int, work: Callable[[int], object]) -> list[object]:
    """Run `work(i)` on `count` threads released together; results by index."""
    results: list[object] = [None] * count
    barrier = threading.Barrier(count)

    def run(index: int) -> None:
        barrier.wait()
        try:
            results[index] = work(index)
        except BaseException as error:  # noqa: BLE001 - reported to the test
            results[index] = error

    threads = [threading.Thread(target=run, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads)
    return results


@pytest.mark.covers("TokenStore.mint_token", "TokenStore.find_token")
def test_concurrent_mints_of_one_token_id_give_exactly_one_success(
    open_account_store: Callable[[], AccountStore],
) -> None:
    stores = [open_account_store() for _ in range(6)]
    stores[0].create_principal(NewPrincipal("quin", None), now=T1)
    results = _race(
        6,
        lambda i: stores[i].mint_token(
            NewToken("tok-race", f"verifier-{i}", None),
            principal_id="quin",
            new_principal=None,
            now=T2 + i,
        ),
    )
    wins = [r for r in results if isinstance(r, TokenRecord)]
    losses = [r for r in results if isinstance(r, DuplicateIdentifier)]
    assert len(wins) == 1
    assert len(losses) == 5
    assert stores[0].find_token("tok-race") == wins[0]
    assert len(stores[0].list_tokens("quin")) == 1


@pytest.mark.covers("TokenStore.revoke_token", "TokenStore.find_token")
def test_concurrent_revokes_give_exactly_one_revoked_and_keep_its_time(
    open_account_store: Callable[[], AccountStore],
) -> None:
    stores = [open_account_store() for _ in range(6)]
    stores[0].create_principal(NewPrincipal("rex", None), now=T1)
    stores[0].mint_token(
        new_token("rex-a"), principal_id="rex", new_principal=None, now=T2
    )
    results = _race(6, lambda i: stores[i].revoke_token("rex-a", now=T3 + i))
    assert results.count(RevokeResult.REVOKED) == 1
    assert results.count(RevokeResult.ALREADY_REVOKED) == 5
    winner = results.index(RevokeResult.REVOKED)
    found = stores[0].find_token("rex-a")
    assert found is not None
    assert found.revoked_at == T3 + winner


@pytest.mark.covers("TokenStore.mint_token", "PrincipalStore.delete_principal")
def test_a_mint_racing_a_delete_never_leaves_a_token_without_its_principal(
    open_account_store: Callable[[], AccountStore],
) -> None:
    for round_number in range(8):
        _mint_races_delete(
            open_account_store(),
            open_account_store(),
            principal_id=f"sue-{round_number}",
            token_id=f"sue-tok-{round_number}",
        )


def _mint_races_delete(
    miner: AccountStore, deleter: AccountStore, *, principal_id: str, token_id: str
) -> None:
    miner.create_principal(NewPrincipal(principal_id, None), now=T1)

    def work(index: int) -> object:
        if index == 0:
            return miner.mint_token(
                new_token(token_id),
                principal_id=principal_id,
                new_principal=None,
                now=T2,
            )
        return deleter.delete_principal(principal_id)

    results = _race(2, work)
    assert results[1] is True
    assert isinstance(results[0], (TokenRecord, UnknownPrincipal))
    assert miner.get_principal(principal_id) is None
    assert miner.find_token(token_id) is None


@pytest.mark.parametrize("operation", range(8))
@pytest.mark.covers(
    "PrincipalStore.create_principal",
    "PrincipalStore.get_principal",
    "PrincipalStore.list_principals",
    "PrincipalStore.delete_principal",
    "TokenStore.mint_token",
    "TokenStore.find_token",
    "TokenStore.list_tokens",
    "TokenStore.revoke_token",
)
def test_every_operation_on_a_closed_store_is_unreachable(
    account_store: AccountStore, operation: int
) -> None:
    calls: list[Callable[[], object]] = [
        lambda: account_store.create_principal(NewPrincipal("x", None), now=T1),
        lambda: account_store.get_principal("x"),
        lambda: account_store.list_principals(),
        lambda: account_store.delete_principal("x"),
        lambda: account_store.mint_token(
            new_token("t"), principal_id="x", new_principal=None, now=T1
        ),
        lambda: account_store.find_token("t"),
        lambda: account_store.list_tokens(None),
        lambda: account_store.revoke_token("t", now=T1),
    ]
    assert len(calls) == 8
    account_store.close()
    with pytest.raises(StorageUnreachable):
        calls[operation]()

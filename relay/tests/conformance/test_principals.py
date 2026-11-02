"""Principals on both backends: create, get, list order, delete with its cascade."""

from __future__ import annotations

import pytest
from tests.conftest import BYTE_ORDER, TIED_IDS, AccountStore

from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    Principal,
)

T1, T2, T3, T4, T5 = (
    1_700_000_001,
    1_700_000_002,
    1_700_000_003,
    1_700_000_004,
    1_700_000_005,
)


def mint(store: AccountStore, token_id: str, principal_id: str, now: int) -> None:
    store.mint_token(
        NewToken(token_id=token_id, verifier=f"verifier-{token_id}", label=None),
        principal_id=principal_id,
        new_principal=None,
        now=now,
    )


@pytest.mark.covers("PrincipalStore.create_principal", "PrincipalStore.get_principal")
def test_a_created_principal_is_returned_and_found_with_its_label_and_time(
    account_store: AccountStore,
) -> None:
    assert account_store.get_principal("alice") is None
    created = account_store.create_principal(
        NewPrincipal(principal_id="alice", label="Alice's club"), now=T1
    )
    assert created == Principal(
        principal_id="alice", label="Alice's club", created_at=T1
    )
    assert account_store.get_principal("alice") == created
    assert account_store.get_principal("alicf") is None


@pytest.mark.covers("PrincipalStore.create_principal", "PrincipalStore.get_principal")
def test_a_principal_without_a_label_has_label_none(
    account_store: AccountStore,
) -> None:
    created = account_store.create_principal(
        NewPrincipal(principal_id="bob", label=None), now=T2
    )
    assert created.label is None
    found = account_store.get_principal("bob")
    assert found is not None
    assert found.label is None


@pytest.mark.covers("PrincipalStore.create_principal", "PrincipalStore.get_principal")
def test_a_duplicate_principal_is_refused_and_the_first_is_unchanged(
    account_store: AccountStore,
) -> None:
    first = account_store.create_principal(
        NewPrincipal(principal_id="carol", label="first"), now=T1
    )
    with pytest.raises(DuplicateIdentifier):
        account_store.create_principal(
            NewPrincipal(principal_id="carol", label="second"), now=T2
        )
    assert account_store.get_principal("carol") == first
    assert len(account_store.list_principals()) == 1


@pytest.mark.covers("PrincipalStore.list_principals")
def test_listing_an_empty_store_gives_an_empty_tuple(
    account_store: AccountStore,
) -> None:
    assert account_store.list_principals() == ()


@pytest.mark.covers("PrincipalStore.list_principals", "PrincipalStore.create_principal")
def test_listing_orders_by_creation_time_then_id_by_bytes_on_both_backends(
    account_store: AccountStore, ids_sort_by_locale_here: None
) -> None:
    assert sorted(TIED_IDS) == BYTE_ORDER
    # "Late" has the smallest id of all but the latest time; "Early" the
    # largest-sorting id but the earliest. Neither id alone gives the order.
    account_store.create_principal(NewPrincipal("zzz_early", None), now=T1)
    for principal_id in TIED_IDS:  # created out of order, all at one time
        account_store.create_principal(NewPrincipal(principal_id, None), now=T3)
    account_store.create_principal(NewPrincipal("0_late", None), now=T5)
    listed = account_store.list_principals()
    assert [p.principal_id for p in listed] == ["zzz_early", *BYTE_ORDER, "0_late"]
    assert [p.created_at for p in listed] == [T1] + [T3] * 7 + [T5]


@pytest.mark.covers("PrincipalStore.delete_principal")
def test_deleting_reports_whether_the_principal_existed(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("dora", None), now=T1)
    account_store.create_principal(NewPrincipal("eli", None), now=T2)
    assert account_store.delete_principal("dora") is True
    assert account_store.get_principal("dora") is None
    assert account_store.delete_principal("dora") is False
    assert account_store.delete_principal("never-there") is False
    assert [p.principal_id for p in account_store.list_principals()] == ["eli"]


@pytest.mark.covers(
    "PrincipalStore.delete_principal",
    "TokenStore.find_token",
    "TokenStore.list_tokens",
)
def test_deleting_a_principal_cascades_its_tokens_and_only_its_tokens(
    account_store: AccountStore,
) -> None:
    account_store.create_principal(NewPrincipal("fay", None), now=T1)
    account_store.create_principal(NewPrincipal("gus", None), now=T1 + 10)
    mint(account_store, "fay-live", "fay", T2)
    mint(account_store, "fay-revoked", "fay", T3)
    account_store.revoke_token("fay-revoked", now=T4)
    mint(account_store, "gus-live", "gus", T3 + 10)
    # Precondition: all three tokens exist before the delete.
    assert account_store.find_token("fay-live") is not None
    assert account_store.find_token("fay-revoked") is not None
    assert len(account_store.list_tokens(None)) == 3

    assert account_store.delete_principal("fay") is True

    assert account_store.find_token("fay-live") is None
    assert account_store.find_token("fay-revoked") is None
    assert account_store.list_tokens("fay") == ()
    remaining = account_store.list_tokens(None)
    assert [t.token_id for t in remaining] == ["gus-live"]
    assert account_store.get_principal("gus") is not None

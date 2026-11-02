"""IdentityService: minting, authenticating and revoking relay tokens (2.1-2.4, 2.6)."""

from __future__ import annotations

import ast
import dataclasses
import hashlib
import hmac
import inspect
import re
import secrets
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, cast

import pytest

from fitdocs_relay import identity
from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.identity import Authenticated, MintedToken, TokenService
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import split_relay_token
from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    Principal,
    RevokeResult,
    Storage,
    TokenRecord,
    UnknownPrincipal,
)

PEPPER = b"identity-test-pepper-0123456789abcdefghijklmnopqrstuvwxyz"
OTHER_PEPPER = b"another-pepper-entirely-0123456789abcdefghijklmnopqrstuvw"
NOW = 1_700_000_000
ALPHABET = re.compile(r"^[a-z2-7]+$")
PRINCIPAL_ID = re.compile(r"^prn_[a-z2-7]{16}$")

# The design's interface block (design.md, IdentityService), verbatim.
DESIGNED = """
@dataclass(frozen=True)
class MintedToken: token_id: str; principal_id: str; token: str = field(repr=False)
@dataclass(frozen=True)
class Authenticated: principal_id: str; token_id: str
class TokenService:
    def __init__(self, storage: Storage, *, pepper: bytes, clock: Callable[[], int]) -> None: ...
    def create_principal(self, label: str | None) -> Principal: ...
    def mint(self, *, principal_id: str | None, label: str | None, principal_label: str | None = None) -> MintedToken: ...
    def authenticate(self, presented: str | None) -> Authenticated | RelayCode: ...
    def revoke(self, token_id: str) -> RevokeResult: ...
    def delete_principal(self, principal_id: str) -> bool: ...
"""  # noqa: E501


def _expected_verifier(pepper: bytes, token_id: str, secret: str) -> str:
    message = b"fitdocs-relay-token-v1\0" + token_id.encode() + b"\0" + secret.encode()
    return hmac.new(pepper, message, hashlib.sha256).hexdigest()


def _parts(minted: MintedToken) -> tuple[str, str]:
    parts = split_relay_token(minted.token)
    assert parts is not None
    return parts


@pytest.fixture
def storage(open_full_storage: Callable[[], Storage]) -> Storage:
    return open_full_storage()


@pytest.fixture
def service(storage: Storage) -> TokenService:
    return TokenService(storage, pepper=PEPPER, clock=lambda: NOW)


def _flip_last(value: str) -> str:
    return value[:-1] + ("b" if value[-1] == "a" else "a")


# --- the designed interface --------------------------------------------------


def _designed_classes() -> dict[str, ast.ClassDef]:
    return {
        node.name: node
        for node in ast.parse(DESIGNED).body
        if isinstance(node, ast.ClassDef)
    }


def _actual_classes() -> dict[str, ast.ClassDef]:
    tree = ast.parse(Path(inspect.getfile(identity)).read_text(encoding="utf-8"))
    return {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}


def test_designed_interface_is_pinned_whole() -> None:
    designed = _designed_classes()
    actual = _actual_classes()
    assert set(designed) == {"MintedToken", "Authenticated", "TokenService"}
    for name in ("MintedToken", "Authenticated"):
        want, got = designed[name], actual[name]
        assert [ast.dump(d) for d in got.decorator_list] == [
            ast.dump(d) for d in want.decorator_list
        ]
        assert [ast.dump(n) for n in got.body if isinstance(n, ast.AnnAssign)] == [
            ast.dump(n) for n in want.body if isinstance(n, ast.AnnAssign)
        ]
    want_methods = {
        n.name: n
        for n in designed["TokenService"].body
        if isinstance(n, ast.FunctionDef)
    }
    got_methods = {
        n.name: n
        for n in actual["TokenService"].body
        if isinstance(n, ast.FunctionDef)
        and (n.name == "__init__" or not n.name.startswith("_"))
    }
    assert set(want_methods) == set(got_methods) and len(want_methods) == 6
    for name, want_fn in want_methods.items():
        got_fn = got_methods[name]
        assert want_fn.returns is not None and got_fn.returns is not None
        assert ast.dump(got_fn.args) == ast.dump(want_fn.args), name
        assert ast.dump(got_fn.returns) == ast.dump(want_fn.returns), name
        assert [ast.dump(d) for d in got_fn.decorator_list] == [
            ast.dump(d) for d in want_fn.decorator_list
        ]


# --- format and generation (2.2) --------------------------------------------


def test_minted_token_has_the_documented_format(service: TokenService) -> None:
    minted = service.mint(principal_id=None, label="phone", principal_label="me")
    parts = split_relay_token(minted.token)
    assert parts is not None
    token_id, secret = parts
    assert minted.token == f"fdr1_{token_id}_{secret}"
    assert minted.token_id == token_id
    assert len(token_id) == 16 and ALPHABET.match(token_id)
    assert len(secret) == 52 and ALPHABET.match(secret)
    assert PRINCIPAL_ID.match(minted.principal_id)
    assert token_id != secret[:16]


def test_ids_and_secrets_differ_across_mints(service: TokenService) -> None:
    minted = [service.mint(principal_id=None, label=None) for _ in range(40)]
    assert len({m.token_id for m in minted}) == 40
    assert len({_parts(m)[1] for m in minted}) == 40
    assert len({m.principal_id for m in minted}) == 40


def test_every_random_part_is_drawn_from_secrets(
    service: TokenService, monkeypatch: pytest.MonkeyPatch
) -> None:
    drawn: list[str] = []

    def fixed(alphabet: str) -> str:
        drawn.append(alphabet)
        return "q"

    monkeypatch.setattr(secrets, "choice", fixed)
    minted = service.mint(principal_id=None, label=None)
    assert minted.token == "fdr1_" + "q" * 16 + "_" + "q" * 52
    assert minted.principal_id == "prn_" + "q" * 16
    assert len(drawn) == 16 + 52 + 16
    assert set(drawn) == {"abcdefghijklmnopqrstuvwxyz234567"}


# --- the stored record (2.2, 2.6) -------------------------------------------


def test_the_store_holds_only_the_verifier(
    service: TokenService, storage: Storage, database_target: object
) -> None:
    minted = service.mint(principal_id=None, label="laptop")
    token_id, secret = _parts(minted)
    record = storage.find_token(token_id)
    assert record is not None
    assert record.verifier == _expected_verifier(PEPPER, token_id, secret)
    assert re.fullmatch(r"[0-9a-f]{64}", record.verifier)
    values = [str(v) for v in dataclasses.astuple(record)]
    assert not any(secret in v or minted.token in v for v in values)
    assert secret not in repr(record)
    assert [s.token_id for s in storage.list_tokens(None)] == [token_id]
    assert not any(
        secret in str(v)
        for s in storage.list_tokens(None)
        for v in dataclasses.astuple(s)
    )
    if isinstance(database_target, SqliteTarget):
        storage.close()
        raw = b"".join(
            p.read_bytes() for p in database_target.path.parent.iterdir() if p.is_file()
        )
        assert token_id.encode() in raw
        assert secret.encode() not in raw


def test_the_verifier_depends_on_the_id_the_secret_and_the_pepper(
    service: TokenService, storage: Storage
) -> None:
    first = service.mint(principal_id=None, label=None)
    second = service.mint(principal_id=None, label=None)
    stored = {}
    for minted in (first, second):
        record = storage.find_token(minted.token_id)
        assert record is not None
        stored[minted.token_id] = record.verifier
    assert len(set(stored.values())) == 2
    first_id, first_secret = _parts(first)
    second_id, second_secret = _parts(second)
    assert stored[first_id] != _expected_verifier(PEPPER, first_id, second_secret)
    assert stored[first_id] != _expected_verifier(PEPPER, second_id, first_secret)
    assert stored[first_id] != _expected_verifier(OTHER_PEPPER, first_id, first_secret)


def test_a_database_copy_and_a_wrong_pepper_authenticate_nothing(
    service: TokenService, storage: Storage
) -> None:
    minted = service.mint(principal_id=None, label=None)
    assert service.authenticate(minted.token) == Authenticated(
        minted.principal_id, minted.token_id
    )
    stranger = TokenService(storage, pepper=OTHER_PEPPER, clock=lambda: NOW)
    assert stranger.authenticate(minted.token) is RelayCode.TOKEN_UNKNOWN
    record = storage.find_token(minted.token_id)
    assert record is not None
    # What a database copy yields: the id, and the verifier. Neither is a token.
    token_id, secret = _parts(minted)
    stolen = f"fdr1_{token_id}_{record.verifier[:52]}"
    assert split_relay_token(stolen) is None
    assert service.authenticate(stolen) is RelayCode.TOKEN_UNKNOWN
    assert stranger.authenticate(f"fdr1_{token_id}_{secret}") is RelayCode.TOKEN_UNKNOWN


# --- authentication answers (2.3, 2.4) --------------------------------------


def test_missing_token(service: TokenService) -> None:
    assert service.authenticate(None) is RelayCode.TOKEN_MISSING


def test_empty_and_malformed_values_are_unknown_not_missing(
    service: TokenService,
) -> None:
    minted = service.mint(principal_id=None, label=None)
    token_id, secret = _parts(minted)
    for bad in (
        "",
        "garbage",
        minted.token.upper(),
        minted.token + "a",
        f"fdr2_{token_id}_{secret}",
        f"fdr1_{token_id}_{secret[:-1]}",
        f"fdr1_{token_id[:-1]}_{secret}",
        " " + minted.token,
    ):
        assert service.authenticate(bad) is RelayCode.TOKEN_UNKNOWN, bad


def test_a_valid_token_authenticates_as_its_principal(
    service: TokenService, storage: Storage
) -> None:
    owner = service.create_principal("owner")
    other = service.create_principal("other")
    minted = service.mint(principal_id=owner.principal_id, label=None)
    answer = service.authenticate(minted.token)
    assert answer == Authenticated(owner.principal_id, minted.token_id)
    assert isinstance(answer, Authenticated)
    assert answer.principal_id != other.principal_id


def test_unknown_id_and_mismatched_secret_are_unknown(service: TokenService) -> None:
    minted = service.mint(principal_id=None, label=None)
    token_id, secret = _parts(minted)
    wrong_secret = f"fdr1_{token_id}_{_flip_last(secret)}"
    wrong_id = f"fdr1_{_flip_last(token_id)}_{secret}"
    assert service.authenticate(wrong_secret) is RelayCode.TOKEN_UNKNOWN
    assert service.authenticate(wrong_id) is RelayCode.TOKEN_UNKNOWN
    assert service.authenticate(minted.token) is not RelayCode.TOKEN_UNKNOWN


def test_revoked_token_answers_revoked(service: TokenService) -> None:
    minted = service.mint(principal_id=None, label=None)
    assert isinstance(service.authenticate(minted.token), Authenticated)
    assert service.revoke(minted.token_id) is RevokeResult.REVOKED
    assert service.authenticate(minted.token) is RelayCode.TOKEN_REVOKED
    assert service.revoke(minted.token_id) is RevokeResult.ALREADY_REVOKED
    assert service.authenticate(minted.token) is RelayCode.TOKEN_REVOKED


def test_revocation_is_per_token_and_unknown_ids_are_reported(
    service: TokenService,
) -> None:
    owner = service.create_principal(None)
    first = service.mint(principal_id=owner.principal_id, label=None)
    second = service.mint(principal_id=owner.principal_id, label=None)
    service.revoke(first.token_id)
    assert service.authenticate(first.token) is RelayCode.TOKEN_REVOKED
    assert isinstance(service.authenticate(second.token), Authenticated)
    assert service.revoke("a" * 16) is RevokeResult.UNKNOWN


def test_a_revoked_token_with_a_wrong_secret_stays_unknown(
    service: TokenService,
) -> None:
    minted = service.mint(principal_id=None, label=None)
    token_id, secret = _parts(minted)
    service.revoke(token_id)
    forged = f"fdr1_{token_id}_{_flip_last(secret)}"
    assert service.authenticate(forged) is RelayCode.TOKEN_UNKNOWN


def test_deleting_a_principal_makes_its_tokens_unknown(
    service: TokenService, storage: Storage
) -> None:
    owner = service.create_principal(None)
    kept = service.create_principal(None)
    live = service.mint(principal_id=owner.principal_id, label=None)
    dead = service.mint(principal_id=owner.principal_id, label=None)
    survivor = service.mint(principal_id=kept.principal_id, label=None)
    service.revoke(dead.token_id)
    assert service.authenticate(live.token) == Authenticated(
        owner.principal_id, live.token_id
    )
    assert service.delete_principal(owner.principal_id) is True
    assert service.authenticate(live.token) is RelayCode.TOKEN_UNKNOWN
    assert service.authenticate(dead.token) is RelayCode.TOKEN_UNKNOWN
    assert isinstance(service.authenticate(survivor.token), Authenticated)
    assert storage.find_token(live.token_id) is None
    assert service.delete_principal(owner.principal_id) is False


# --- constant-time comparison and the dummy verifier (2.3) ------------------


class _Spies:
    def __init__(self) -> None:
        self.compares: list[tuple[Any, Any]] = []
        self.keyed: list[bytes] = []


@pytest.fixture
def spies(monkeypatch: pytest.MonkeyPatch) -> _Spies:
    spy = _Spies()
    real_compare = hmac.compare_digest
    real_new = hmac.new

    def compare(a: Any, b: Any) -> bool:
        spy.compares.append((a, b))
        return real_compare(a, b)

    def new(key: bytes, msg: bytes | None = None, digestmod: Any = "") -> Any:
        spy.keyed.append(key)
        return real_new(key, msg, digestmod)

    monkeypatch.setattr(hmac, "compare_digest", compare)
    monkeypatch.setattr(hmac, "new", new)
    return spy


def test_a_matching_token_is_compared_once_in_constant_time(
    service: TokenService, storage: Storage, spies: _Spies
) -> None:
    minted = service.mint(principal_id=None, label=None)
    record = storage.find_token(minted.token_id)
    assert record is not None
    spies.compares.clear()
    spies.keyed.clear()
    assert isinstance(service.authenticate(minted.token), Authenticated)
    assert len(spies.compares) == 1
    assert set(spies.compares[0]) == {record.verifier}
    assert spies.keyed == [PEPPER]


def test_a_mismatched_secret_is_compared_once_in_constant_time(
    service: TokenService, storage: Storage, spies: _Spies
) -> None:
    minted = service.mint(principal_id=None, label=None)
    token_id, secret = _parts(minted)
    record = storage.find_token(token_id)
    assert record is not None
    spies.compares.clear()
    spies.keyed.clear()
    forged = f"fdr1_{token_id}_{_flip_last(secret)}"
    assert service.authenticate(forged) is RelayCode.TOKEN_UNKNOWN
    assert len(spies.compares) == 1
    assert record.verifier in spies.compares[0]
    assert len(set(spies.compares[0])) == 2
    assert spies.keyed == [PEPPER]


def test_an_unknown_id_still_computes_one_verifier_and_one_comparison(
    service: TokenService, spies: _Spies
) -> None:
    unknown = "fdr1_" + "a" * 16 + "_" + "b" * 52
    assert service.authenticate(unknown) is RelayCode.TOKEN_UNKNOWN
    assert spies.keyed == [PEPPER]
    assert len(spies.compares) == 1
    computed, dummy = spies.compares[0]
    assert computed == _expected_verifier(PEPPER, "a" * 16, "b" * 52)
    assert dummy != computed
    assert re.fullmatch(r"[0-9a-f]{64}", str(dummy))


def test_missing_and_malformed_values_compute_nothing(
    service: TokenService, spies: _Spies
) -> None:
    service.authenticate(None)
    service.authenticate("not-a-token")
    assert spies.keyed == [] and spies.compares == []


# --- mint (2.1, 2.2, 2.6) ----------------------------------------------------


def test_mint_for_a_new_principal_creates_it_with_both_labels(
    service: TokenService, storage: Storage
) -> None:
    minted = service.mint(principal_id=None, label="phone", principal_label="Ann")
    principal = storage.get_principal(minted.principal_id)
    assert principal == Principal(minted.principal_id, "Ann", NOW)
    record = storage.find_token(minted.token_id)
    assert record is not None
    assert record.label == "phone" and record.principal_id == minted.principal_id
    assert record.created_at == NOW and record.revoked_at is None


def test_mint_for_an_existing_principal_adds_a_token_only(
    service: TokenService, storage: Storage
) -> None:
    owner = service.create_principal("owner")
    before = storage.list_principals()
    minted = service.mint(principal_id=owner.principal_id, label=None)
    assert minted.principal_id == owner.principal_id
    assert storage.list_principals() == before
    assert [t.token_id for t in storage.list_tokens(owner.principal_id)] == [
        minted.token_id
    ]


def test_mint_for_an_unknown_principal_raises_and_stores_nothing(
    service: TokenService, storage: Storage
) -> None:
    with pytest.raises(UnknownPrincipal):
        service.mint(principal_id="prn_" + "a" * 16, label=None)
    assert storage.list_tokens(None) == ()
    assert storage.list_principals() == ()


def test_create_principal(service: TokenService, storage: Storage) -> None:
    labelled = service.create_principal("Ann")
    bare = service.create_principal(None)
    assert PRINCIPAL_ID.match(labelled.principal_id)
    assert labelled.label == "Ann" and bare.label is None
    assert labelled.created_at == NOW
    assert labelled.principal_id != bare.principal_id
    assert storage.get_principal(labelled.principal_id) == labelled


def test_the_clock_is_read_for_each_operation(storage: Storage) -> None:
    ticks = iter(range(1000, 2000))
    clocked = TokenService(storage, pepper=PEPPER, clock=lambda: next(ticks))
    minted = clocked.mint(principal_id=None, label=None)
    record = storage.find_token(minted.token_id)
    assert record is not None and record.created_at == 1000
    clocked.revoke(minted.token_id)
    revoked = storage.find_token(minted.token_id)
    assert revoked is not None and revoked.revoked_at == 1001


def test_the_minted_value_is_hidden_from_repr_and_str(service: TokenService) -> None:
    minted = service.mint(principal_id=None, label=None)
    _, secret = _parts(minted)
    assert minted.token_id in repr(minted) and minted.principal_id in repr(minted)
    for text in (repr(minted), str(minted), f"{minted}", f"{minted!r}"):
        assert minted.token not in text
        assert secret not in text
    assert "token=" not in repr(minted)
    with pytest.raises(FrozenInstanceError):
        minted.token = "x"  # type: ignore[misc]


def test_returned_values_expose_no_verifier_or_secret(service: TokenService) -> None:
    minted = service.mint(principal_id=None, label=None)
    answer = service.authenticate(minted.token)
    assert isinstance(answer, Authenticated)
    assert [f.name for f in dataclasses.fields(MintedToken)] == [
        "token_id",
        "principal_id",
        "token",
    ]
    assert [f.name for f in dataclasses.fields(Authenticated)] == [
        "principal_id",
        "token_id",
    ]
    _, secret = _parts(minted)
    assert secret not in repr(answer) and minted.token not in repr(answer)
    with pytest.raises(FrozenInstanceError):
        answer.token_id = "x"  # type: ignore[misc]


# --- the retry on a duplicate identifier -------------------------------------


class _FlakyStore:
    """Delegates to a real store, but fails the first `failures` mints."""

    def __init__(self, inner: Storage, failures: int) -> None:
        self._inner = inner
        self.failures = failures
        self.attempts: list[tuple[NewToken, NewPrincipal | None]] = []

    def mint_token(self, token: NewToken, **kwargs: Any) -> TokenRecord:
        self.attempts.append((token, kwargs.get("new_principal")))
        if len(self.attempts) <= self.failures:
            raise DuplicateIdentifier("taken")
        return self._inner.mint_token(token, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_mint_retries_generation_once_on_a_duplicate(storage: Storage) -> None:
    flaky = _FlakyStore(storage, failures=1)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    minted = service.mint(principal_id=None, label=None)
    assert len(flaky.attempts) == 2
    (first, first_principal), (second, second_principal) = flaky.attempts
    assert first.token_id != second.token_id
    assert first_principal is not None and second_principal is not None
    assert first_principal.principal_id != second_principal.principal_id
    assert minted.token_id == second.token_id
    assert minted.principal_id == second_principal.principal_id
    assert isinstance(service.authenticate(minted.token), Authenticated)
    assert storage.find_token(first.token_id) is None


def test_the_retry_regenerates_the_secret_too(storage: Storage) -> None:
    flaky = _FlakyStore(storage, failures=1)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    service.mint(principal_id=None, label=None)
    (first, _), (second, _) = flaky.attempts
    assert first.verifier != second.verifier


def test_mint_raises_after_a_second_duplicate(storage: Storage) -> None:
    flaky = _FlakyStore(storage, failures=2)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    with pytest.raises(DuplicateIdentifier):
        service.mint(principal_id=None, label=None)
    assert len(flaky.attempts) == 2
    assert storage.list_tokens(None) == ()


def test_mint_for_an_existing_principal_also_retries_once(storage: Storage) -> None:
    owner = TokenService(storage, pepper=PEPPER, clock=lambda: NOW).create_principal(
        None
    )
    flaky = _FlakyStore(storage, failures=1)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    minted = service.mint(principal_id=owner.principal_id, label=None)
    assert len(flaky.attempts) == 2
    assert minted.principal_id == owner.principal_id


class _FlakyPrincipals:
    """Delegates to a real store, but fails the first `failures` principal creations."""

    def __init__(self, inner: Storage, failures: int) -> None:
        self._inner = inner
        self.failures = failures
        self.attempts: list[NewPrincipal] = []

    def create_principal(self, principal: NewPrincipal, *, now: int) -> Principal:
        self.attempts.append(principal)
        if len(self.attempts) <= self.failures:
            raise DuplicateIdentifier("taken")
        return self._inner.create_principal(principal, now=now)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


def test_create_principal_retries_generation_once(storage: Storage) -> None:
    flaky = _FlakyPrincipals(storage, failures=1)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    created = service.create_principal("Ann")
    first, second = flaky.attempts
    assert first.principal_id != second.principal_id
    assert created.principal_id == second.principal_id
    assert storage.get_principal(first.principal_id) is None
    assert storage.get_principal(created.principal_id) == created


def test_create_principal_raises_after_a_second_duplicate(storage: Storage) -> None:
    flaky = _FlakyPrincipals(storage, failures=2)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    with pytest.raises(DuplicateIdentifier):
        service.create_principal(None)
    assert len(flaky.attempts) == 2
    assert storage.list_principals() == ()


# --- later requests after revocation (2.4) ----------------------------------


def test_a_revoked_token_stays_revoked_at_every_later_tick(storage: Storage) -> None:
    now = [1000]
    clocked = TokenService(storage, pepper=PEPPER, clock=lambda: now[0])
    minted = clocked.mint(principal_id=None, label=None)
    assert isinstance(clocked.authenticate(minted.token), Authenticated)
    now[0] = 1500
    assert clocked.revoke(minted.token_id) is RevokeResult.REVOKED
    record = storage.find_token(minted.token_id)
    assert record is not None and record.revoked_at == 1500
    # Mutations: `revoked_at >= clock()` and `revoked_at > clock()` as the
    # revoked condition both answer Authenticated at the later ticks.
    for later in (1501, 1502, 1510, 99_999):
        now[0] = later
        assert clocked.authenticate(minted.token) is RelayCode.TOKEN_REVOKED


# --- the secret is stored nowhere, on every mint shape (2.6) ------------------


# (mint call, expected token label, expected principal label)
_Shape = tuple[Callable[[TokenService], MintedToken], str | None, str | None]


def _existing(service: TokenService, label: str | None) -> MintedToken:
    owner = service.create_principal(None)
    return service.mint(principal_id=owner.principal_id, label=label)


def _mint_shapes() -> dict[str, _Shape]:
    return {
        "new-principal-no-label": (
            lambda s: s.mint(principal_id=None, label=None),
            None,
            None,
        ),
        "new-principal-labelled": (
            lambda s: s.mint(principal_id=None, label="phone", principal_label="Ann"),
            "phone",
            "Ann",
        ),
        "new-principal-no-token-label-with-principal-label": (
            lambda s: s.mint(principal_id=None, label=None, principal_label="Ann"),
            None,
            "Ann",
        ),
        "existing-no-label": (lambda s: _existing(s, None), None, None),
        "existing-labelled": (lambda s: _existing(s, "laptop"), "laptop", None),
    }


def _assert_secret_nowhere(
    storage: Storage,
    minted: MintedToken,
    target: object,
    *,
    token_label: str | None,
    principal_label: str | None,
) -> None:
    token_id, secret = _parts(minted)
    record = storage.find_token(token_id)
    assert record == TokenRecord(
        token_id,
        minted.principal_id,
        _expected_verifier(PEPPER, token_id, secret),
        token_label,
        NOW,
        None,
    )
    principal = storage.get_principal(minted.principal_id)
    assert principal is not None and principal.label == principal_label
    stored = [str(v) for v in dataclasses.astuple(record)]
    stored += [
        str(v) for s in storage.list_tokens(None) for v in dataclasses.astuple(s)
    ]
    stored += [str(v) for v in dataclasses.astuple(principal)]
    stored += [
        str(v) for p in storage.list_principals() for v in dataclasses.astuple(p)
    ]
    assert len(stored) > 10
    assert not any(secret in v or minted.token in v for v in stored)
    if isinstance(target, SqliteTarget):
        storage.close()
        files = [p for p in target.path.parent.iterdir() if p.is_file()]
        assert files
        raw = b"".join(p.read_bytes() for p in files)
        assert minted.token_id.encode() in raw
        assert secret.encode() not in raw


@pytest.mark.parametrize("shape", list(_mint_shapes()))
def test_the_secret_is_stored_nowhere_for_every_mint_shape(
    shape: str, storage: Storage, service: TokenService, database_target: object
) -> None:
    # Mutations: `label if label is not None else secret` (and `secret[:26]`,
    # `secret.upper()`) as the stored label fail the record equality here.
    mint, token_label, principal_label = _mint_shapes()[shape]
    minted = mint(service)
    _assert_secret_nowhere(
        storage,
        minted,
        database_target,
        token_label=token_label,
        principal_label=principal_label,
    )


def test_the_secret_is_stored_nowhere_after_a_retry(
    storage: Storage, database_target: object
) -> None:
    flaky = _FlakyStore(storage, failures=1)
    service = TokenService(cast(Storage, flaky), pepper=PEPPER, clock=lambda: NOW)
    minted = service.mint(principal_id=None, label=None)
    assert len(flaky.attempts) == 2
    _assert_secret_nowhere(
        storage, minted, database_target, token_label=None, principal_label=None
    )

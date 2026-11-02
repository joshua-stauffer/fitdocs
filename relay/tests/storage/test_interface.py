"""The storage interface: value types, errors, members, `now` as an argument."""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path
from typing import Protocol

import pytest

from fitdocs_relay.storage import interface
from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewConnection,
    NewPrincipal,
    NewToken,
    Principal,
    PrincipalStore,
    RateDecision,
    RateLimitStore,
    RecordStore,
    RevokeResult,
    SchemaAhead,
    SchemaChange,
    SchemaState,
    SchemaStore,
    SealedTokens,
    ServingStore,
    Storage,
    StorageBase,
    StorageError,
    StorageUnreachable,
    StoredConnection,
    TargetConnectionStore,
    TokenRecord,
    TokenStore,
    TokenSummary,
    UnknownPrincipal,
)

INTERFACE_SOURCE = Path(interface.__file__)

# Every member of Storage, by the protocol that declares it (design.md,
# StorageInterface). Literal, so adding or dropping a member reds here.
EXPECTED_MEMBERS: dict[str, set[str]] = {
    "StorageBase": {"backend", "ping", "close"},
    "PrincipalStore": {
        "create_principal",
        "get_principal",
        "list_principals",
        "delete_principal",
    },
    "TokenStore": {"mint_token", "find_token", "list_tokens", "revoke_token"},
    "RateLimitStore": {"count_request"},
    "RecordStore": {"put_record", "get_record", "take_record", "delete_record"},
    "SchemaStore": {"schema_state", "apply_schema_change"},
    "ServingStore": {"claim_serving"},
    "TargetConnectionStore": {
        "put_connection",
        "get_connection",
        "list_connections",
        "delete_connection",
        "delete_connection_by_account",
    },
}

AREAS = {
    "PrincipalStore": PrincipalStore,
    "TokenStore": TokenStore,
    "RateLimitStore": RateLimitStore,
    "RecordStore": RecordStore,
    "SchemaStore": SchemaStore,
    "ServingStore": ServingStore,
    "TargetConnectionStore": TargetConnectionStore,
}


def _declared(protocol: type) -> set[str]:
    return {
        name
        for name, value in vars(protocol).items()
        if not name.startswith("_") and (callable(value) or isinstance(value, property))
    }


def test_each_protocol_declares_exactly_its_members() -> None:
    declared = {"StorageBase": _declared(StorageBase)} | {
        name: _declared(proto) for name, proto in AREAS.items()
    }
    assert declared == EXPECTED_MEMBERS
    assert all(declared.values()), "an area declared nothing"


def test_every_area_is_based_on_storage_base_and_composed_into_storage() -> None:
    for name, proto in AREAS.items():
        assert StorageBase in proto.__bases__, name
        assert Protocol in proto.__bases__, name
    assert Storage.__bases__ == (
        PrincipalStore,
        TokenStore,
        RateLimitStore,
        RecordStore,
        SchemaStore,
        ServingStore,
        TargetConnectionStore,
        Protocol,
    )
    assert _declared(Storage) == set()


# The class statements of design.md, StorageInterface (its python block),
# rendered as: decorators, bases, then one string per body statement. A method
# is "[@decorator ]def name(args) -> returns"; a docstring is not a statement
# and the `...` bodies are not rendered.
DESIGNED: dict[str, dict[str, list[str]]] = {
    "Principal": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["principal_id: str", "label: str | None", "created_at: int"],
    },
    "NewPrincipal": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["principal_id: str", "label: str | None"],
    },
    "NewToken": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["token_id: str", "verifier: str", "label: str | None"],
    },
    "TokenRecord": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": [
            "token_id: str",
            "principal_id: str",
            "verifier: str = field(repr=False)",
            "label: str | None",
            "created_at: int",
            "revoked_at: int | None",
        ],
    },
    "TokenSummary": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": [
            "token_id: str",
            "principal_id: str",
            "label: str | None",
            "created_at: int",
            "revoked_at: int | None",
        ],
    },
    "RevokeResult": {
        "decorators": [],
        "bases": ["StrEnum"],
        "body": [
            "REVOKED = 'revoked'",
            "ALREADY_REVOKED = 'already-revoked'",
            "UNKNOWN = 'unknown'",
        ],
    },
    "RateDecision": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["allowed: bool", "count: int", "retry_after_s: int | None"],
    },
    "SchemaState": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["current: int", "expected: int"],
    },
    "SchemaChange": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": ["version: int", "name: str", "sql: str"],
    },
    "ServingClaim": {
        "decorators": [],
        "bases": ["Protocol"],
        "body": ["def release(self) -> None"],
    },
    "StorageError": {"decorators": [], "bases": ["Exception"], "body": []},
    "StorageUnreachable": {"decorators": [], "bases": ["StorageError"], "body": []},
    "DuplicateIdentifier": {"decorators": [], "bases": ["StorageError"], "body": []},
    "UnknownPrincipal": {"decorators": [], "bases": ["StorageError"], "body": []},
    "SchemaAhead": {"decorators": [], "bases": ["StorageError"], "body": []},
    "StorageBase": {
        "decorators": [],
        "bases": ["Protocol"],
        "body": [
            "@property def backend(self) -> Literal['sqlite', 'postgres']",
            "def ping(self) -> None",
            "def close(self) -> None",
        ],
    },
    "PrincipalStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def create_principal(self, principal: NewPrincipal, *, now: int) -> "
            "Principal",
            "def get_principal(self, principal_id: str) -> Principal | None",
            "def list_principals(self) -> tuple[Principal, ...]",
            "def delete_principal(self, principal_id: str) -> bool",
        ],
    },
    "TokenStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def mint_token(self, token: NewToken, *, principal_id: str | None, "
            "new_principal: NewPrincipal | None, now: int) -> TokenRecord",
            "def find_token(self, token_id: str) -> TokenRecord | None",
            "def list_tokens(self, principal_id: str | None) -> tuple[TokenSummary, "
            "...]",
            "def revoke_token(self, token_id: str, *, now: int) -> RevokeResult",
        ],
    },
    "RateLimitStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def count_request(self, *, key: str, window_s: int, limit: int, now: "
            "int) -> RateDecision"
        ],
    },
    "RecordStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def put_record(self, *, namespace: str, key: str, value: bytes, "
            "expires_at: int, now: int) -> None",
            "def get_record(self, *, namespace: str, key: str, now: int) -> bytes | "
            "None",
            "def take_record(self, *, namespace: str, key: str, now: int) -> bytes | "
            "None",
            "def delete_record(self, *, namespace: str, key: str) -> bool",
        ],
    },
    "SchemaStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def schema_state(self) -> SchemaState",
            "def apply_schema_change(self, change: SchemaChange, *, now: int) -> bool",
        ],
    },
    "ServingStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": ["def claim_serving(self) -> ServingClaim | None"],
    },
    "SealedTokens": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": [
            "access: str = field(repr=False)",
            "refresh: str | None = field(repr=False)",
            "access_expires_at: int | None",
        ],
    },
    "NewConnection": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": [
            "principal_id: str",
            "target: str",
            "account_key: str",
            "tokens: SealedTokens",
        ],
    },
    "StoredConnection": {
        "decorators": ["dataclass(frozen=True)"],
        "bases": [],
        "body": [
            "principal_id: str",
            "target: str",
            "account_key: str",
            "tokens: SealedTokens",
            "generation: int",
            "lease_id: str | None",
            "lease_until: int | None",
            "token_id: str | None",
            "created_at: int",
            "updated_at: int",
        ],
    },
    "TargetConnectionStore": {
        "decorators": [],
        "bases": ["StorageBase", "Protocol"],
        "body": [
            "def put_connection(self, connection: NewConnection, *, now: int) -> None",
            "def get_connection(self, principal_id: str, target: str) -> "
            "StoredConnection | None",
            "def list_connections(self, target: str | None) -> "
            "tuple[StoredConnection, ...]",
            "def delete_connection(self, principal_id: str, target: str, *, "
            "generation: int | None, now: int) -> bool",
            "def delete_connection_by_account(self, target: str, account_key: str, "
            "*, now: int) -> bool",
        ],
    },
    "Storage": {
        "decorators": [],
        "bases": [
            "PrincipalStore",
            "TokenStore",
            "RateLimitStore",
            "RecordStore",
            "SchemaStore",
            "ServingStore",
            "TargetConnectionStore",
            "Protocol",
        ],
        "body": [],
    },
}


def _render_classes(source: str) -> dict[str, dict[str, list[str]]]:
    rendered: dict[str, dict[str, list[str]]] = {}
    for node in ast.parse(source).body:
        if not isinstance(node, ast.ClassDef):
            continue
        body: list[str] = []
        for stmt in node.body:
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                continue
            if isinstance(stmt, ast.FunctionDef):
                decorators = "".join(f"@{ast.unparse(d)} " for d in stmt.decorator_list)
                returns = f" -> {ast.unparse(stmt.returns)}" if stmt.returns else ""
                body.append(
                    f"{decorators}def {stmt.name}({ast.unparse(stmt.args)}){returns}"
                )
            else:
                body.append(ast.unparse(stmt))
        rendered[node.name] = {
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "bases": [ast.unparse(b) for b in node.bases],
            "body": body,
        }
    return rendered


def test_every_class_in_the_interface_module_is_the_designed_one() -> None:
    live = _render_classes(INTERFACE_SOURCE.read_text(encoding="utf-8"))
    assert live, "no classes were rendered"
    assert list(live) == list(DESIGNED)
    assert live == DESIGNED


# Operations that take `now`, keyword-only (the caller supplies the time).
TAKES_NOW = {
    PrincipalStore: {"create_principal"},
    TokenStore: {"mint_token", "revoke_token"},
    RateLimitStore: {"count_request"},
    RecordStore: {"put_record", "get_record", "take_record"},
    SchemaStore: {"apply_schema_change"},
    TargetConnectionStore: {
        "put_connection",
        "delete_connection",
        "delete_connection_by_account",
    },
}


def test_now_is_a_keyword_only_argument_of_exactly_the_time_dependent_operations() -> (
    None
):
    seen_with_now: set[str] = set()
    for proto in AREAS.values():
        for name in _declared(proto):
            member = vars(proto)[name]
            if isinstance(member, property):
                continue
            param = inspect.signature(member).parameters.get("now")
            if param is not None:
                assert param.kind is inspect.Parameter.KEYWORD_ONLY, name
                assert param.default is inspect.Parameter.empty, name
                seen_with_now.add(name)
    expected = {name for names in TAKES_NOW.values() for name in names}
    assert expected  # the table is not empty
    assert seen_with_now == expected


def test_the_interface_module_imports_no_clock() -> None:
    tree = ast.parse(INTERFACE_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported, "the walk found no imports in the interface module"
    assert not imported & {"time", "datetime", "sched", "asyncio"}


# --- value types ------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "fields"),
    [
        (Principal, ["principal_id", "label", "created_at"]),
        (NewPrincipal, ["principal_id", "label"]),
        (NewToken, ["token_id", "verifier", "label"]),
        (
            TokenRecord,
            [
                "token_id",
                "principal_id",
                "verifier",
                "label",
                "created_at",
                "revoked_at",
            ],
        ),
        (
            TokenSummary,
            ["token_id", "principal_id", "label", "created_at", "revoked_at"],
        ),
        (RateDecision, ["allowed", "count", "retry_after_s"]),
        (SchemaState, ["current", "expected"]),
        (SchemaChange, ["version", "name", "sql"]),
        (SealedTokens, ["access", "refresh", "access_expires_at"]),
        (NewConnection, ["principal_id", "target", "account_key", "tokens"]),
        (
            StoredConnection,
            [
                "principal_id",
                "target",
                "account_key",
                "tokens",
                "generation",
                "lease_id",
                "lease_until",
                "token_id",
                "created_at",
                "updated_at",
            ],
        ),
    ],
)
def test_value_types_are_frozen_with_the_designed_fields(
    cls: type, fields: list[str]
) -> None:
    assert [f.name for f in dataclasses.fields(cls)] == fields
    params = cls.__dataclass_params__  # type: ignore[attr-defined]
    assert params.frozen is True


def test_a_value_type_cannot_be_mutated() -> None:
    principal = Principal(principal_id="p1", label=None, created_at=5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        principal.label = "x"  # type: ignore[misc]


def test_the_verifier_never_appears_in_a_token_record_repr() -> None:
    secret = "verifier-secret-0123"
    record = TokenRecord(
        token_id="t1",
        principal_id="p1",
        verifier=secret,
        label=None,
        created_at=1,
        revoked_at=None,
    )
    assert secret not in repr(record)
    assert record.verifier == secret  # excluded from repr only


def test_revoke_result_values() -> None:
    assert [(r.name, r.value) for r in RevokeResult] == [
        ("REVOKED", "revoked"),
        ("ALREADY_REVOKED", "already-revoked"),
        ("UNKNOWN", "unknown"),
    ]
    assert isinstance(RevokeResult.REVOKED, str)


def test_error_hierarchy() -> None:
    assert issubclass(StorageError, Exception)
    for sub in (StorageUnreachable, DuplicateIdentifier, UnknownPrincipal, SchemaAhead):
        assert issubclass(sub, StorageError)
        assert sub.__mro__[1] is StorageError
    assert not issubclass(StorageUnreachable, DuplicateIdentifier)


def test_the_backend_classes_exist_and_stub_nothing_with_not_implemented() -> None:
    from fitdocs_relay.storage import postgres, sqlite

    for module, name in ((sqlite, "SqliteBackend"), (postgres, "PostgresBackend")):
        assert inspect.isclass(getattr(module, name))
        tree = ast.parse(Path(module.__file__ or "").read_text(encoding="utf-8"))
        raised = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id == "NotImplementedError"
        ]
        assert raised == [], f"{name}: a backend never stubs a member"

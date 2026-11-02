"""The coverage marker: every `covers(...)` argument names a real Storage member."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

import pytest

Collected = Sequence[tuple[str, Sequence[object]]]
ProblemsFn = Callable[[Collected], list[str]]

# Every member of Storage, "<declaring protocol>.<member>" (design.md,
# StorageInterface). Literal, so the enumeration cannot drift unseen.
EXPECTED = {
    "StorageBase.backend",
    "StorageBase.ping",
    "StorageBase.close",
    "PrincipalStore.create_principal",
    "PrincipalStore.get_principal",
    "PrincipalStore.list_principals",
    "PrincipalStore.delete_principal",
    "TokenStore.mint_token",
    "TokenStore.find_token",
    "TokenStore.list_tokens",
    "TokenStore.revoke_token",
    "RateLimitStore.count_request",
    "RecordStore.put_record",
    "RecordStore.get_record",
    "RecordStore.take_record",
    "RecordStore.delete_record",
    "SchemaStore.schema_state",
    "SchemaStore.apply_schema_change",
    "ServingStore.claim_serving",
    "TargetConnectionStore.put_connection",
    "TargetConnectionStore.get_connection",
    "TargetConnectionStore.list_connections",
    "TargetConnectionStore.delete_connection",
    "TargetConnectionStore.delete_connection_by_account",
}


def test_the_member_enumeration_is_the_designed_set(storage_members: set[str]) -> None:
    assert len(EXPECTED) == 24
    assert storage_members == EXPECTED


class _Base(Protocol):
    @property
    def declared_property(self) -> int: ...

    def declared_method(self) -> None: ...

    annotated_only: int


class _Derived(_Base, Protocol):
    def derived_method(self) -> None: ...

    _private: int


def test_the_enumeration_reads_methods_properties_and_annotations_by_declarer(
    members_of: Callable[[type], set[str]],
) -> None:
    assert members_of(_Derived) == {
        "_Base.declared_property",
        "_Base.declared_method",
        "_Base.annotated_only",
        "_Derived.derived_method",
    }


def test_a_marker_naming_a_real_member_is_accepted(
    marker_problems: ProblemsFn,
) -> None:
    collected: Collected = [
        ("t::a", ("TokenStore.find_token", "StorageBase.ping")),
        ("t::b", ("ServingStore.claim_serving",)),
    ]
    assert marker_problems(collected) == []


@pytest.mark.parametrize(
    "name",
    [
        "TokenStore.find_tokens",  # a near miss
        "find_token",  # the area is required
        "Storage.find_token",  # composed, not declaring
        "TokenStore.",
        "",
        "StorageBase.__init__",
    ],
)
def test_a_marker_naming_a_non_member_is_a_problem(
    marker_problems: ProblemsFn, name: str
) -> None:
    problems = marker_problems([("t::a", ("TokenStore.find_token", name))])
    assert len(problems) == 1
    assert "t::a" in problems[0]
    assert repr(name) in problems[0]


@pytest.mark.parametrize("bad", [(), (3,), (None,), (("TokenStore.find_token",),)])
def test_a_marker_without_a_string_name_is_a_problem(
    marker_problems: ProblemsFn, bad: tuple[object, ...]
) -> None:
    problems = marker_problems([("t::a", bad)])
    assert len(problems) == 1
    assert "t::a" in problems[0]
    assert ("names nothing" if not bad else "is not a string") in problems[0]


def test_every_marker_in_the_suite_names_a_real_member(
    collected_covers: Collected,
    marker_problems: ProblemsFn,
    request: pytest.FixtureRequest,
) -> None:
    assert request.session.items, "the session collected nothing"
    assert marker_problems(collected_covers) == []


def uncovered(collected: Collected, members: set[str]) -> list[str]:
    named = {name for _, names in collected for name in names}
    return sorted(members - named)


def test_a_member_no_marker_names_is_uncovered(storage_members: set[str]) -> None:
    only_one = [("t::a", ("TokenStore.find_token",))]
    assert uncovered(only_one, storage_members) == sorted(
        storage_members - {"TokenStore.find_token"}
    )
    assert uncovered([("t::a", tuple(storage_members))], storage_members) == []


def test_every_storage_member_is_named_by_at_least_one_marker(
    collected_covers: Collected,
    storage_members: set[str],
    request: pytest.FixtureRequest,
) -> None:
    suite = Path(__file__).parent
    modules = sorted(suite.glob("test_*.py"))
    assert modules, "the walk is looking at the wrong directory"
    collected_ids = {item.nodeid for item in request.session.items}
    missing = [
        m.name
        for m in modules
        if not any(
            i.endswith(f"/{m.name}") or f"{m.name}::" in i for i in collected_ids
        )
    ]
    if missing or request.config.option.keyword or request.config.option.markexpr:
        pytest.skip(
            "completeness needs the whole conformance suite collected "
            f"(not collected, or filtered: {missing or 'a -k/-m filter'})"
        )
    assert uncovered(collected_covers, storage_members) == []

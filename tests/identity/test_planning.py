"""Tests for the run planner and duplicate sets.

Requirements 3.7, 3.9, 3.10, 4.1-4.6, 4.8, 4.9, 5.7, 8.3.

The decision scenarios (pinned, fresh group, one claim, bridge, double claim,
matched-by-a-bridge, pinned re-export) are asserted against explicit expected
decisions, tasks and holds for EVERY permutation of their input files
(``itertools.permutations``). Decisions and holds are compared as values; tasks
as ``(page, member set)`` pairs, because member order and task order follow
input order and are asserted separately against the permuted input (the tasks
test and the holds-order test). ``duplicate_sets`` is checked over a seeded
random sample of record orders, not every order.

Where the value picked is the point of a scenario (which page, which group,
which evidence, which start order), its fixture values differ pairwise for that
comparison; other keys are shared where sharing is harmless.
"""

from __future__ import annotations

import itertools
import random
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.matching import Evidence, SessionKey
from fitdocs.identity.planning import (
    DuplicateSet,
    Fresh,
    Hold,
    Join,
    PageIndex,
    PageRecord,
    RunFile,
    RunPlan,
    duplicate_sets,
    plan_run,
)

_T0 = datetime(2024, 5, 1, 12, 0, 0, tzinfo=UTC)
_DEVICE = "0123456789abcdef"


def _key(
    *,
    start: datetime | None = _T0,
    elapsed_s: float | None = 3000.0,
    distance_m: float | None = 10_000.0,
    device: str | None = None,
    kind: SourceKind | None = SourceKind.ORIGINAL,
    sport: str = "Run",
) -> SessionKey:
    return SessionKey(
        sport=sport,
        start=start,
        elapsed_s=elapsed_s,
        distance_m=distance_m,
        device=device,
        kind=kind,
    )


def _page(
    path: str,
    key: SessionKey,
    *,
    sources: tuple[str, ...] = (),
    session_uuid: str | None = None,
) -> PageRecord:
    return PageRecord(path=path, sources=sources, session_uuid=session_uuid, key=key)


def _file(
    file_id: str,
    key: SessionKey,
    *,
    ref: str | None = None,
    session_uuid: str | None = None,
) -> RunFile:
    return RunFile(
        id=file_id,
        ref=ref if ref is not None else f"archive/{file_id}.fit",
        session_uuid=session_uuid,
        key=key,
    )


def _shape(plan: RunPlan) -> tuple[object, object, object]:
    """Order-free view: decisions, tasks as (page, member set), holds as a set."""
    return (
        dict(plan.decisions),
        frozenset((t.page, frozenset(t.members)) for t in plan.tasks),
        frozenset(plan.holds),
    )


def _assert_every_permutation(
    files: Sequence[RunFile],
    index: PageIndex,
    *,
    decisions: dict[str, object],
    tasks: set[tuple[str | None, frozenset[str]]],
    holds: set[str],
) -> None:
    count = 0
    for perm in itertools.permutations(files):
        plan = plan_run(perm, index)
        got = _shape(plan)
        assert got == (decisions, frozenset(tasks), frozenset(holds)), [
            f.id for f in perm
        ]
        # invariants (design "Invariants")
        assert set(plan.decisions) == {f.id for f in files}
        in_tasks = {m for t in plan.tasks for m in t.members}
        assert not in_tasks & set(plan.holds)
        count += 1
    assert count >= 2


# --- PageIndex.exact_match ---------------------------------------------------


def test_exact_match_prefers_session_uuid_then_sources_each_first_in_path_order() -> (
    None
):
    k = _key()
    index = PageIndex(
        [
            _page("w/c.md", k, session_uuid="u-1"),
            _page("w/e.md", k, sources=("r-x",)),
            _page("w/b.md", k, session_uuid="u-1", sources=("r-y",)),
            _page("w/d.md", k, sources=("r-x", "r-z")),
            _page("w/f.md", k),
        ]
    )
    assert [r.path for r in index.records] == [f"w/{c}.md" for c in "bcdef"]
    match = index.exact_match("u-1", "r-x")
    assert match is not None and match.path == "w/b.md"  # uuid beats sources
    match = index.exact_match("u-none", "r-x")
    assert match is not None and match.path == "w/d.md"  # first sources in path order
    match = index.exact_match(None, "r-z")
    assert match is not None and match.path == "w/d.md"
    assert index.exact_match("u-none", "r-none") is None


def test_exact_match_never_matches_an_absent_session_uuid() -> None:
    index = PageIndex([_page("w/a.md", _key(), session_uuid=None)])
    assert index.exact_match(None, "r-none") is None


# --- plan_run ----------------------------------------------------------------


def test_pinned_files_always_join_and_ignore_key_evidence() -> None:
    pinned_page = _page("w/pinned.md", _key(elapsed_s=1000.0), sources=("r-old",))
    uuid_page = _page("w/z-uuid.md", _key(elapsed_s=1500.0), session_uuid="u-77")
    other = _page("w/a-other.md", _key(elapsed_s=3001.0))
    index = PageIndex([other, uuid_page, pinned_page])
    # both files' own keys strictly match ``other``, yet each joins its exact page
    by_ref = _file("f-ref", _key(elapsed_s=3002.0), ref="r-old")
    by_uuid = _file("f-uuid", _key(elapsed_s=3003.0), session_uuid="u-77")
    _assert_every_permutation(
        [by_ref, by_uuid],
        index,
        decisions={
            "f-ref": Join("w/pinned.md", Evidence.SOURCE),
            "f-uuid": Join("w/z-uuid.md", Evidence.UUID),
        },
        tasks={
            ("w/pinned.md", frozenset({"f-ref"})),
            ("w/z-uuid.md", frozenset({"f-uuid"})),
        },
        holds=set(),
    )


def test_a_fresh_group_of_three_linked_files_is_one_task() -> None:
    # k1~k3 strict; k3~k7 only by an equal session UUID (keys 50 min apart)
    k1 = _file("k1", _key(elapsed_s=3000.0))
    k3 = _file("k3", _key(elapsed_s=3004.0), session_uuid="u-shared")
    k7 = _file(
        "k7",
        _key(start=_T0 + timedelta(minutes=50), elapsed_s=2222.0),
        session_uuid="u-shared",
    )
    lone = _file("k2", _key(start=_T0 + timedelta(days=3), elapsed_s=1800.0))
    index = PageIndex([_page("w/unrelated.md", _key(start=_T0 + timedelta(days=9)))])
    _assert_every_permutation(
        [k7, lone, k1, k3],
        index,
        decisions={
            "k1": Fresh(0),
            "k3": Fresh(0),
            "k7": Fresh(0),
            "k2": Fresh(1),
        },
        tasks={(None, frozenset({"k1", "k3", "k7"})), (None, frozenset({"k2"}))},
        holds=set(),
    )


def test_one_claim_joins_with_the_strongest_evidence() -> None:
    page = _page("w/p.md", _key(elapsed_s=3006.0, device=_DEVICE))
    a = _file("a", _key(elapsed_s=3001.0, device=_DEVICE))  # DEVICE with the page
    b = _file("b", _key(elapsed_s=3009.0))  # STRICT with the page and a
    index = PageIndex([page, _page("w/far.md", _key(start=_T0 + timedelta(days=4)))])
    _assert_every_permutation(
        [b, a],
        index,
        decisions={
            "a": Join("w/p.md", Evidence.DEVICE),
            "b": Join("w/p.md", Evidence.DEVICE),
        },
        tasks={("w/p.md", frozenset({"a", "b"}))},
        holds=set(),
    )


def test_a_group_bridging_two_pages_is_held_with_both_candidates() -> None:
    p1 = _page("w/m-first.md", _key(elapsed_s=2990.0))
    p2 = _page("w/n-second.md", _key(elapsed_s=3020.0))
    # g1 (3000) strict with p1 only; g2 (3010) strict with p2 only and with g1
    g1 = _file("g1", _key(elapsed_s=3000.0))
    g2 = _file("g2", _key(elapsed_s=3010.0))
    index = PageIndex([p2, p1])
    held = Hold(("w/m-first.md", "w/n-second.md"), (Evidence.STRICT, Evidence.STRICT))
    _assert_every_permutation(
        [g2, g1],
        index,
        decisions={"g1": held, "g2": held},
        tasks=set(),
        holds={"g1", "g2"},
    )


def test_two_unlinked_groups_claiming_one_page_are_both_held() -> None:
    page = _page("w/only.md", _key(elapsed_s=3007.0))
    a = _file("a", _key(elapsed_s=3000.0))
    b = _file("b", _key(elapsed_s=3014.0))  # 14 s from a: unlinked; 7 s from the page
    other = _file("c", _key(start=_T0 + timedelta(days=2), elapsed_s=1700.0))
    index = PageIndex([page])
    held = Hold(("w/only.md",), (Evidence.STRICT,))
    _assert_every_permutation(
        [b, other, a],
        index,
        decisions={"a": held, "b": held, "c": Fresh(2)},
        tasks={(None, frozenset({"c"}))},
        holds={"a", "b"},
    )


def test_a_pinned_re_export_and_a_strict_original_share_a_task() -> None:
    # the page's own key is 30 minutes away: the original has no evidence with it
    page = _page(
        "w/page.md",
        _key(start=_T0 + timedelta(minutes=30), elapsed_s=2500.0),
        sources=("r-re-export",),
    )
    re_export = _file("re", _key(elapsed_s=3000.0), ref="r-re-export")
    original = _file("orig", _key(elapsed_s=3005.0))
    index = PageIndex([page])
    _assert_every_permutation(
        [original, re_export],
        index,
        decisions={
            "re": Join("w/page.md", Evidence.SOURCE),
            "orig": Join("w/page.md", Evidence.STRICT),
        },
        tasks={("w/page.md", frozenset({"re", "orig"}))},
        holds=set(),
    )


def test_tasks_follow_the_first_member_and_members_keep_input_order() -> None:
    pa = _page("w/a.md", _key(start=_T0 + timedelta(days=1)), sources=("r-a",))
    pb = _page("w/b.md", _key(start=_T0 + timedelta(days=2)), sources=("r-b",))
    index = PageIndex([pb, pa])
    fa1 = _file("fa1", _key(start=_T0 + timedelta(days=1)), ref="r-a")
    fa2 = _file("fa2", _key(start=_T0 + timedelta(days=1)), ref="r-a")
    fb = _file("fb", _key(start=_T0 + timedelta(days=2)), ref="r-b")
    fresh = _file("fx", _key(start=_T0 + timedelta(days=5), elapsed_s=999.0))
    target = {"fa1": "w/a.md", "fa2": "w/a.md", "fb": "w/b.md", "fx": None}
    seen_orders = set()
    for perm in itertools.permutations([fa1, fa2, fb, fresh]):
        plan = plan_run(perm, index)
        expected: list[tuple[str | None, tuple[str, ...]]] = []
        for f in perm:
            if not any(page == target[f.id] for page, _ in expected):
                expected.append(
                    (
                        target[f.id],
                        tuple(g.id for g in perm if target[g.id] == target[f.id]),
                    )
                )
        assert [(t.page, t.members) for t in plan.tasks] == expected
        seen_orders.add(tuple(p for p, _ in expected))
    # the scenario does exercise path order and reverse-path order
    assert ("w/a.md", "w/b.md", None) in seen_orders
    assert ("w/b.md", "w/a.md", None) in seen_orders


# --- duplicate_sets ----------------------------------------------------------


def _day(n: int) -> datetime:
    return _T0 + timedelta(days=n)


def test_duplicate_sets_by_each_of_the_three_links() -> None:
    records = [
        # shared source ref, keys far apart
        _page("w/s1.md", _key(start=_day(1), elapsed_s=1111.0), sources=("r-1", "r-s")),
        _page("w/s2.md", _key(start=_day(2), elapsed_s=1222.0), sources=("r-s",)),
        # shared session UUID, across sports
        _page("w/u1.md", _key(start=_day(3), elapsed_s=1333.0), session_uuid="u-d"),
        _page(
            "w/u2.md",
            _key(start=_day(4), elapsed_s=1444.0, sport="Ride"),
            session_uuid="u-d",
        ),
        # pair evidence only
        _page("w/e1.md", _key(start=_day(5), elapsed_s=1555.0)),
        _page("w/e2.md", _key(start=_day(5), elapsed_s=1560.0)),
        # a chain: ref link then pair evidence; three pages, both links reported
        _page("w/c1.md", _key(start=_day(6), elapsed_s=1666.0), sources=("r-c",)),
        _page("w/c2.md", _key(start=_day(7), elapsed_s=1777.0), sources=("r-c",)),
        _page("w/c3.md", _key(start=_day(7), elapsed_s=1781.0)),
        # non-members: same start as e1 but another sport; and a lone page
        _page("w/x1.md", _key(start=_day(5), elapsed_s=1555.0, sport="Ride")),
        _page("w/x2.md", _key(start=_day(8), elapsed_s=1888.0)),
    ]
    expected = (
        DuplicateSet(
            ("w/c1.md", "w/c2.md", "w/c3.md"), (Evidence.SOURCE, Evidence.STRICT)
        ),
        DuplicateSet(("w/e1.md", "w/e2.md"), (Evidence.STRICT,)),
        DuplicateSet(("w/s1.md", "w/s2.md"), (Evidence.SOURCE,)),
        DuplicateSet(("w/u1.md", "w/u2.md"), (Evidence.UUID,)),
    )
    rng = random.Random(24)
    shuffled_differently = False
    for _ in range(60):
        order = list(records)
        rng.shuffle(order)
        shuffled_differently |= order != records
        assert duplicate_sets(PageIndex(order)) == expected
    assert shuffled_differently


def test_duplicate_sets_finds_a_shifted_pair_past_unrelated_pages() -> None:
    phone = _key(
        start=_T0 + timedelta(hours=5),
        elapsed_s=3002.0,
        distance_m=10_001.0,
        kind=SourceKind.PHONE_COPY,
    )
    records = [
        _page("w/2-shifted.md", phone),
        _page("w/1-base.md", _key()),
        _page("w/3-between.md", _key(start=_T0 + timedelta(hours=2), elapsed_s=900.0)),
        _page(
            "w/4-too-far.md", _key(start=_T0 + timedelta(hours=100), elapsed_s=3002.0)
        ),
        _page("w/5-no-start.md", _key(start=None)),
    ]
    assert duplicate_sets(PageIndex(records)) == (
        DuplicateSet(("w/1-base.md", "w/2-shifted.md"), (Evidence.SHIFTED,)),
    )


def test_no_duplicate_sets_when_no_pages_link() -> None:
    assert duplicate_sets(PageIndex([])) == ()
    records = [
        _page("w/a.md", _key(start=_day(1))),
        _page("w/b.md", _key(start=_day(2))),
    ]
    assert duplicate_sets(PageIndex(records)) == ()


def test_duplicate_sets_window_covers_a_shift_of_exactly_the_maximum() -> None:
    base = _page("w/base.md", _key())
    edge = _page(
        "w/edge.md",
        _key(
            start=_T0 + timedelta(hours=36, seconds=0.5),
            elapsed_s=3002.0,
            distance_m=10_001.0,
            kind=SourceKind.PHONE_COPY,
        ),
    )
    assert duplicate_sets(PageIndex([edge, base])) == (
        DuplicateSet(("w/base.md", "w/edge.md"), (Evidence.SHIFTED,)),
    )


def test_duplicate_sets_scans_in_start_order_not_path_order() -> None:
    # path order x, y, z; start order x, z, y with y far away between them by path
    x = _page("w/a-x.md", _key(elapsed_s=3000.0))
    y = _page("w/b-y.md", _key(start=_T0 + timedelta(hours=100), elapsed_s=1234.0))
    z = _page(
        "w/c-z.md", _key(start=_T0 + timedelta(milliseconds=400), elapsed_s=3004.0)
    )
    assert duplicate_sets(PageIndex([y, z, x])) == (
        DuplicateSet(("w/a-x.md", "w/c-z.md"), (Evidence.STRICT,)),
    )


# --- ruling: a bridge matches each of its candidates (Req 4.2, 4.6) ---------


def test_a_page_matched_by_a_bridge_is_held_for_every_group_matching_it() -> None:
    # P 3000 and Q 3016 are candidates of B (3008); A (2995) matches P only,
    # C (3021) matches Q only; A, B and C are pairwise unlinked (13, 13, 26 s).
    p = _page("w/p.md", _key(elapsed_s=3000.0))
    q = _page("w/q.md", _key(elapsed_s=3016.0))
    a = _file("a", _key(elapsed_s=2995.0))
    b = _file("b", _key(elapsed_s=3008.0))
    c = _file("c", _key(elapsed_s=3021.0))
    strict = Evidence.STRICT
    _assert_every_permutation(
        [c, a, b],
        PageIndex([q, p]),
        decisions={
            "a": Hold(("w/p.md",), (strict,)),
            "b": Hold(("w/p.md", "w/q.md"), (strict, strict)),
            "c": Hold(("w/q.md",), (strict,)),
        },
        tasks=set(),
        holds={"a", "b", "c"},
    )


def test_a_bridge_hold_carries_each_candidates_own_evidence() -> None:
    # m matches by STRICT (elapsed), n by DEVICE only; path order m, n differs
    # from strength order.
    m = _page("w/m.md", _key(elapsed_s=3004.0))
    n = _page("w/n.md", _key(elapsed_s=3500.0, device=_DEVICE))
    f = _file("f", _key(elapsed_s=3000.0, device=_DEVICE))
    g = _file("g", _key(elapsed_s=3002.0))
    held = Hold(("w/m.md", "w/n.md"), (Evidence.STRICT, Evidence.DEVICE))
    _assert_every_permutation(
        [g, f],
        PageIndex([n, m]),
        decisions={"f": held, "g": held},
        tasks=set(),
        holds={"f", "g"},
    )


def test_a_free_file_linked_to_a_pinned_file_only_by_session_uuid_joins_its_page() -> (
    None
):
    page = _page("w/pin.md", _key(start=_T0 + timedelta(days=20)), sources=("r-pin",))
    pinned = _file(
        "p", _key(start=_T0 + timedelta(days=21)), ref="r-pin", session_uuid="u-link"
    )
    free = _file(
        "q",
        _key(start=_T0 + timedelta(days=30), elapsed_s=999.0),
        session_uuid="u-link",
    )
    _assert_every_permutation(
        [free, pinned],
        PageIndex([page]),
        decisions={
            "p": Join("w/pin.md", Evidence.SOURCE),
            "q": Join("w/pin.md", Evidence.UUID),
        },
        tasks={("w/pin.md", frozenset({"p", "q"}))},
        holds=set(),
    )


def test_candidate_pages_are_looked_up_in_the_files_own_sport() -> None:
    ride = "Ride"
    run_page = _page("w/a-run.md", _key(elapsed_s=3001.0))
    ride_page = _page("w/b-ride.md", _key(elapsed_s=3001.0, sport=ride))
    r1 = _file("r1", _key(elapsed_s=3000.0, sport=ride))
    r2 = _file("r2", _key(elapsed_s=3003.0, sport=ride))
    _assert_every_permutation(
        [r2, r1],
        PageIndex([run_page, ride_page]),
        decisions={
            "r1": Join("w/b-ride.md", Evidence.STRICT),
            "r2": Join("w/b-ride.md", Evidence.STRICT),
        },
        tasks={("w/b-ride.md", frozenset({"r1", "r2"}))},
        holds=set(),
    )


def test_holds_are_listed_in_input_order() -> None:
    page = _page("w/only.md", _key(elapsed_s=3007.0))
    a = _file("a", _key(elapsed_s=3000.0))
    b = _file("b", _key(elapsed_s=3014.0))
    fresh = _file("c", _key(start=_T0 + timedelta(days=2), elapsed_s=1700.0))
    for perm in itertools.permutations([a, b, fresh]):
        plan = plan_run(perm, PageIndex([page]))
        assert plan.holds == tuple(f.id for f in perm if f.id != "c")


def test_decisions_iterate_in_input_order() -> None:
    page = _page("w/a.md", _key(elapsed_s=3000.0), sources=("archive/a.fit",))
    pinned = _file("a", _key(elapsed_s=3000.0), ref="archive/a.fit")
    fresh_1 = _file("f1", _key(start=_T0 + timedelta(days=5), elapsed_s=1100.0))
    fresh_2 = _file("f2", _key(start=_T0 + timedelta(days=9), elapsed_s=1300.0))
    for perm in itertools.permutations([pinned, fresh_1, fresh_2]):
        plan = plan_run(perm, PageIndex([page]))
        assert list(plan.decisions) == [f.id for f in perm]

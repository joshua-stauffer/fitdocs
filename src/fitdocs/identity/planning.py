"""Assign every file of a run to a page, a new page, or a hold; find duplicate pages.

Pure: no I/O, no clock. Every decision's value, every task's membership and the
set of held files are functions of the *set* of run files and the page index;
every order the plan carries (tasks, task members, holds, and the iteration
order of its decisions) follows input order (Req 4.8, 5.7). Nothing here merges
two pages or removes a source ref (Req 4.9). Pages are compared through
:class:`PageRecord` values only (Req 3.10).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from fitdocs.identity.matching import (
    SHIFT_MAX_HOURS,
    SHIFT_STEP_S,
    START_TOLERANCE_S,
    Evidence,
    SessionKey,
    pair_evidence,
)

__all__ = [
    "Decision",
    "DuplicateSet",
    "Fresh",
    "Hold",
    "Join",
    "PageIndex",
    "PageRecord",
    "PageTaskPlan",
    "RunFile",
    "RunPlan",
    "duplicate_sets",
    "plan_run",
]

# Strongest first: the declaration order of the enum.
_STRENGTH: dict[Evidence, int] = {e: i for i, e in enumerate(Evidence)}
# The widest start difference any tier accepts.
_START_WINDOW_S = SHIFT_MAX_HOURS * SHIFT_STEP_S + START_TOLERANCE_S


@dataclass(frozen=True)
class PageRecord:
    """What the planner knows of one existing page."""

    path: str
    sources: tuple[str, ...]
    session_uuid: str | None
    key: SessionKey


class PageIndex:
    """Page records sorted by path, with the exact match."""

    def __init__(self, records: Sequence[PageRecord]) -> None:
        self.records: tuple[PageRecord, ...] = tuple(
            sorted(records, key=lambda r: r.path)
        )
        self._by_uuid: dict[str, PageRecord] = {}
        self._by_ref: dict[str, PageRecord] = {}
        for record in self.records:
            if record.session_uuid is not None:
                self._by_uuid.setdefault(record.session_uuid, record)
            for ref in record.sources:
                self._by_ref.setdefault(ref, record)

    def exact_match(self, session_uuid: str | None, ref: str) -> PageRecord | None:
        """The first record (path order) with this session UUID, else the first
        whose ``sources`` contains ``ref``."""
        if session_uuid is not None:
            found = self._by_uuid.get(session_uuid)
            if found is not None:
                return found
        return self._by_ref.get(ref)


@dataclass(frozen=True)
class RunFile:
    """One file of the run: a run-unique label, its ref, its UUID and its key."""

    id: str
    ref: str
    session_uuid: str | None
    key: SessionKey


@dataclass(frozen=True)
class Join:
    page: str
    evidence: Evidence


@dataclass(frozen=True)
class Fresh:
    group: int


@dataclass(frozen=True)
class Hold:
    candidates: tuple[str, ...]
    evidence: tuple[Evidence, ...]


Decision = Join | Fresh | Hold


@dataclass(frozen=True)
class PageTaskPlan:
    page: str | None  # None for a fresh group
    members: tuple[str, ...]  # RunFile ids, input order


@dataclass(frozen=True)
class RunPlan:
    decisions: Mapping[str, Decision]
    tasks: tuple[PageTaskPlan, ...]
    holds: tuple[str, ...]


@dataclass(frozen=True)
class DuplicateSet:
    """Two or more pages that are one session: paths ascending, and the distinct
    evidence of the links that connect them, strongest first."""

    pages: tuple[str, ...]
    evidence: tuple[Evidence, ...]


def _stronger(a: Evidence | None, b: Evidence | None) -> Evidence | None:
    if a is None:
        return b
    if b is None:
        return a
    return a if _STRENGTH[a] <= _STRENGTH[b] else b


def _link(
    a_key: SessionKey,
    a_uuid: str | None,
    b_key: SessionKey,
    b_uuid: str | None,
) -> Evidence | None:
    """The strongest link between two files: an equal UUID, or pair evidence."""
    evidence = pair_evidence(a_key, b_key)
    if a_uuid is not None and a_uuid == b_uuid:
        evidence = _stronger(evidence, Evidence.UUID)
    return evidence


class _Sets:
    """Union-find over hashable items."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[max(ra, rb)] = min(ra, rb)


def plan_run(files: Sequence[RunFile], index: PageIndex) -> RunPlan:
    """Decide every file of the run (Req 4.1-4.6, 4.8)."""
    position = {f.id: i for i, f in enumerate(files)}
    by_id = {f.id: f for f in files}

    # 1. Pinned files always join their exact page.
    decisions: dict[str, Decision] = {}
    pinned_page: dict[str, str] = {}
    for f in files:
        match = index.exact_match(f.session_uuid, f.ref)
        if match is None:
            continue
        by_uuid = f.session_uuid is not None and match.session_uuid == f.session_uuid
        decisions[f.id] = Join(
            match.path, Evidence.UUID if by_uuid else Evidence.SOURCE
        )
        pinned_page[f.id] = match.path
    pinned = [by_id[i] for i in pinned_page]
    free = [f for f in files if f.id not in pinned_page]

    # 2-3. Groups: connected components of free files under linkage.
    sets = _Sets()
    for f in free:
        sets.add(f.id)
    for n, a in enumerate(free):
        for b in free[n + 1 :]:
            if _link(a.key, a.session_uuid, b.key, b.session_uuid) is not None:
                sets.union(a.id, b.id)
    members_of: dict[str, list[str]] = defaultdict(list)
    for f in free:
        members_of[sets.find(f.id)].append(f.id)
    groups = sorted(members_of.values(), key=lambda ids: min(ids))
    group_number = {min(ids): n for n, ids in enumerate(groups)}

    by_sport: dict[str, list[PageRecord]] = defaultdict(list)
    for record in index.records:
        by_sport[record.key.sport].append(record)

    # 4. Candidate pages of each group, with the strongest evidence per page.
    candidates_of: dict[int, dict[str, Evidence]] = {}
    for ids in groups:
        found: dict[str, Evidence] = {}
        for member_id in ids:
            member = by_id[member_id]
            for record in by_sport.get(member.key.sport, ()):
                ev = pair_evidence(member.key, record.key)
                if ev is not None:
                    found[record.path] = _stronger(found.get(record.path), ev) or ev
            for other in pinned:
                ev = _link(
                    member.key, member.session_uuid, other.key, other.session_uuid
                )
                if ev is not None:
                    page = pinned_page[other.id]
                    found[page] = _stronger(found.get(page), ev) or ev
        candidates_of[group_number[min(ids)]] = found

    # 5-6. Fresh, hold or claim. A bridging group matches each of its candidates
    # (Req 4.2), so a page matched by two or more groups holds all of them.
    matched_by: dict[str, list[int]] = defaultdict(list)
    for number, found in candidates_of.items():
        for page in found:
            matched_by[page].append(number)

    holds: list[str] = []
    for ids in groups:
        number = group_number[min(ids)]
        found = candidates_of[number]
        if not found:
            for member_id in ids:
                decisions[member_id] = Fresh(number)
            continue
        paths = sorted(found)
        if len(found) == 1 and len(matched_by[paths[0]]) == 1:
            for member_id in ids:
                decisions[member_id] = Join(paths[0], found[paths[0]])
            continue
        hold = Hold(tuple(paths), tuple(found[p] for p in paths))
        for member_id in ids:
            decisions[member_id] = hold
            holds.append(member_id)

    # 7. Tasks: one per target page and per fresh group, ordered by first member.
    members_by_target: dict[tuple[str | None, int | None], list[str]] = defaultdict(
        list
    )
    for f in files:
        decision = decisions[f.id]
        if isinstance(decision, Join):
            members_by_target[(decision.page, None)].append(f.id)
        elif isinstance(decision, Fresh):
            members_by_target[(None, decision.group)].append(f.id)
    tasks = sorted(
        (
            PageTaskPlan(page, tuple(ids))
            for (page, _), ids in members_by_target.items()
        ),
        key=lambda t: position[t.members[0]],
    )
    return RunPlan(
        decisions=MappingProxyType({f.id: decisions[f.id] for f in files}),
        tasks=tuple(tasks),
        holds=tuple(sorted(holds, key=lambda i: position[i])),
    )


def duplicate_sets(index: PageIndex) -> tuple[DuplicateSet, ...]:
    """Every maximal set of two or more pages linked by a shared source ref, an
    equal session UUID, or pair evidence (Req 8.3); ordered by first path."""
    records = index.records
    sets = _Sets()
    links: list[tuple[str, str, Evidence]] = []
    for r in records:
        sets.add(r.path)

    def connect(a: str, b: str, ev: Evidence) -> None:
        if a != b:
            sets.union(a, b)
            links.append((a, b, ev))

    first_ref: dict[str, str] = {}
    first_uuid: dict[str, str] = {}
    for r in records:
        for ref in r.sources:
            if ref in first_ref:
                connect(first_ref[ref], r.path, Evidence.SOURCE)
            else:
                first_ref[ref] = r.path
        if r.session_uuid is not None:
            if r.session_uuid in first_uuid:
                connect(first_uuid[r.session_uuid], r.path, Evidence.UUID)
            else:
                first_uuid[r.session_uuid] = r.path

    by_sport: dict[str, list[PageRecord]] = defaultdict(list)
    for r in records:
        if r.key.start is not None:
            by_sport[r.key.sport].append(r)
    for bucket in by_sport.values():
        bucket.sort(key=lambda r: (r.key.start, r.path))
        for n, a in enumerate(bucket):
            for b in bucket[n + 1 :]:
                assert a.key.start is not None and b.key.start is not None
                if (b.key.start - a.key.start).total_seconds() > _START_WINDOW_S:
                    break
                ev = pair_evidence(a.key, b.key)
                if ev is not None:
                    connect(a.path, b.path, ev)

    pages: dict[str, list[str]] = defaultdict(list)
    for r in records:
        pages[sets.find(r.path)].append(r.path)
    found: dict[str, set[Evidence]] = defaultdict(set)
    for path_a, _path_b, link_ev in links:
        found[sets.find(path_a)].add(link_ev)
    out = [
        DuplicateSet(
            tuple(paths), tuple(sorted(found[root], key=_STRENGTH.__getitem__))
        )
        for root, paths in pages.items()
        if len(paths) > 1
    ]
    return tuple(sorted(out, key=lambda d: d.pages[0]))

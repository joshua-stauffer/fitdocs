"""Tests for the precedence, the rank order and the page roles (Req 2.5, 2.6, 2.8,
5.1-5.3, 5.5, 7.7).

Two kinds of input:

* members parsed from the synthetic species of :mod:`tests.fixtures.identity`
  (a Garmin original, a HealthFit copy, a Stryd file) plus an unknown file made
  with ``dataclasses.replace`` (its ``file_id`` manufacturer removed), for the
  default and configured precedence;
* hand-built :class:`SourceMember` values, for the tie-break keys, where each
  key is made to point against the others.
"""

from __future__ import annotations

import itertools
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from fitdocs.identity.kinds import SourceKind, source_identity
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PageRoles,
    PrecedenceEntry,
    SourceMember,
    page_session_uuid,
    rank_key,
    rank_members,
    resolve_precedence,
    source_member,
)
from fitdocs.ingest import parse_fit
from tests.fixtures import identity

_T0 = datetime(2024, 1, 2, 3, 0, 0, tzinfo=UTC)

ORIGINAL = PrecedenceEntry(SourceKind.ORIGINAL)
PHONE = PrecedenceEntry(SourceKind.PHONE_COPY)
UNKNOWN = PrecedenceEntry(SourceKind.UNKNOWN)
GARMIN = PrecedenceEntry(SourceKind.ORIGINAL, "garmin")
STRYD = PrecedenceEntry(SourceKind.ORIGINAL, "stryd")


def _member(
    ref: str,
    *,
    kind: SourceKind = SourceKind.ORIGINAL,
    manufacturer: str | None = "acme",
    count: int | None = 0,
    created: datetime | None = _T0,
    sha: str | None = None,
    session_uuid: str | None = None,
) -> SourceMember:
    return SourceMember(
        ref=ref,
        sha=sha if sha is not None else f"sha-{ref}",
        kind=kind,
        manufacturer=manufacturer,
        undocumented_messages=count,
        time_created=created,
        session_uuid=session_uuid,
    )


def _species_members() -> dict[str, SourceMember]:
    """Garmin original, HealthFit copy, Stryd file and an unknown file."""
    unknown_activity = parse_fit(identity.stryd_file().data)
    unknown_activity = replace(
        unknown_activity,
        file_identity=replace(unknown_activity.file_identity, manufacturer=None),
    )
    return {
        "garmin": source_member(
            "garmin.fit", "sha-garmin", parse_fit(identity.garmin_original().data)
        ),
        "copy": source_member(
            "copy.fit", "sha-copy", parse_fit(identity.healthfit_copy().data)
        ),
        "stryd": source_member(
            "stryd.fit", "sha-stryd", parse_fit(identity.stryd_file().data)
        ),
        "unknown": source_member("unknown.fit", "sha-unknown", unknown_activity),
    }


def _order(
    members: dict[str, SourceMember], precedence: tuple[PrecedenceEntry, ...]
) -> list[str]:
    roles = rank_members(list(members.values()), (), precedence)
    by_ref = {member.ref: name for name, member in members.items()}
    return [by_ref[m.ref] for m in (roles.base, *roles.extras)]


class TestSourceMember:
    def test_built_from_the_parsed_files_own_identity(self) -> None:
        members = _species_members()
        garmin_species = identity.garmin_original()
        member = members["garmin"]
        assert member.ref == "garmin.fit"
        assert member.sha == "sha-garmin"
        assert member.kind is SourceKind.ORIGINAL
        assert member.manufacturer == "garmin"
        assert member.undocumented_messages == garmin_species.undocumented == 3
        assert (
            member.time_created
            == parse_fit(garmin_species.data).file_identity.time_created
        )
        assert member.time_created is not None
        assert member.session_uuid is None

    def test_a_healthfit_copy_is_a_phone_copy_with_its_session_uuid(self) -> None:
        member = _species_members()["copy"]
        assert member.kind is SourceKind.PHONE_COPY
        assert member.manufacturer == "development"
        assert (
            member.session_uuid
            == source_identity(parse_fit(identity.healthfit_copy().data)).session_uuid
        )
        assert member.session_uuid == "c8c9cacb-cccd-cecf-d0d1-d2d3d4d5d6d7"

    def test_the_unknown_file_has_no_manufacturer(self) -> None:
        member = _species_members()["unknown"]
        assert member.kind is SourceKind.UNKNOWN
        assert member.manufacturer is None


class TestResolvePrecedence:
    def test_the_default_entries_and_order(self) -> None:
        assert DEFAULT_PRECEDENCE == (GARMIN, PHONE, ORIGINAL, UNKNOWN)

    def test_a_configured_list_replaces_the_default_and_names_its_kinds(self) -> None:
        assert resolve_precedence([ORIGINAL, PHONE, UNKNOWN]) == (
            ORIGINAL,
            PHONE,
            UNKNOWN,
        )

    def test_unnamed_kinds_are_appended_and_the_defaults_garmin_entry_is_not(
        self,
    ) -> None:
        resolved = resolve_precedence([STRYD, PHONE])
        assert resolved == (STRYD, PHONE, ORIGINAL, UNKNOWN)
        assert GARMIN not in resolved

    def test_only_a_bare_kind_entry_names_a_kind(self) -> None:
        assert resolve_precedence([GARMIN]) == (GARMIN, ORIGINAL, PHONE, UNKNOWN)

    def test_appended_kinds_follow_the_order_original_phone_copy_unknown(self) -> None:
        assert resolve_precedence([]) == (ORIGINAL, PHONE, UNKNOWN)
        assert resolve_precedence([UNKNOWN]) == (UNKNOWN, ORIGINAL, PHONE)

    def test_a_manufacturer_belongs_only_to_an_original_entry(self) -> None:
        with pytest.raises(ValueError, match="original"):
            PrecedenceEntry(SourceKind.PHONE_COPY, "garmin")


class TestDefaultPrecedence:
    def test_garmin_above_healthfit_copy_above_stryd_above_unknown(self) -> None:
        members = _species_members()
        assert _order(members, DEFAULT_PRECEDENCE) == [
            "garmin",
            "copy",
            "stryd",
            "unknown",
        ]

    def test_the_positions_are_read_directly(self) -> None:
        members = _species_members()
        positions = {
            name: rank_key(member, DEFAULT_PRECEDENCE)[0]
            for name, member in members.items()
        }
        assert positions == {"garmin": 0, "copy": 1, "stryd": 2, "unknown": 3}


class TestConfiguredPrecedence:
    def test_bare_kinds_put_stryd_above_the_healthfit_copy(self) -> None:
        precedence = resolve_precedence([ORIGINAL, PHONE, UNKNOWN])
        assert precedence == (ORIGINAL, PHONE, UNKNOWN)
        members = _species_members()
        # Garmin and Stryd share the original position; the Garmin file's
        # undocumented messages (3 against 0) break the tie.
        assert _order(members, precedence) == ["garmin", "stryd", "copy", "unknown"]

    def test_a_manufacturer_entry_ranks_its_files_and_originals_fall_to_original(
        self,
    ) -> None:
        precedence = resolve_precedence([STRYD, PHONE])
        assert precedence == (STRYD, PHONE, ORIGINAL, UNKNOWN)
        members = _species_members()
        assert _order(members, precedence) == ["stryd", "copy", "garmin", "unknown"]

    def test_a_manufacturer_entry_beats_its_kinds_entry_wherever_it_sits(self) -> None:
        members = _species_members()
        after = resolve_precedence([ORIGINAL, PHONE, UNKNOWN, STRYD])
        assert _order(members, after) == ["garmin", "copy", "unknown", "stryd"]
        before = resolve_precedence([STRYD, ORIGINAL, PHONE, UNKNOWN])
        assert _order(members, before) == ["stryd", "garmin", "copy", "unknown"]

    def test_a_manufacturer_entry_does_not_rank_a_phone_copy_of_that_maker(
        self,
    ) -> None:
        # The HealthFit copy lists Garmin as its device but is a phone copy.
        members = _species_members()
        precedence = resolve_precedence([UNKNOWN, GARMIN, PHONE])
        assert _order(members, precedence) == ["unknown", "garmin", "copy", "stryd"]

    def test_a_precedence_without_the_members_kind_is_refused(self) -> None:
        with pytest.raises(ValueError):
            rank_key(_member("a", kind=SourceKind.UNKNOWN), (ORIGINAL, PHONE))


class TestRankKey:
    def test_the_four_keys_in_order(self) -> None:
        member = _member("a", count=4, created=_T0, sha="abc")
        position, count, created, sha = rank_key(member, DEFAULT_PRECEDENCE)
        assert position == 2
        assert count == -4
        assert created == -_T0.timestamp()
        assert sha == "abc"

    def test_an_absent_count_and_time_rank_after_every_present_value(self) -> None:
        present = rank_key(_member("a", count=0, created=_T0), DEFAULT_PRECEDENCE)
        absent = rank_key(_member("b", count=None, created=None), DEFAULT_PRECEDENCE)
        assert absent[1] > present[1]
        assert absent[2] > present[2]


class TestTieBreaks:
    """Six originals at one position, each key pointing against the others."""

    @staticmethod
    def _six() -> dict[str, SourceMember]:
        return {
            # most undocumented messages, but oldest and highest hash
            "m1": _member("m1", count=9, created=_T0, sha="f"),
            # fewer, newest of the count-4 files, hash after m3's
            "m2": _member("m2", count=4, created=_T0 + timedelta(hours=5), sha="e"),
            "m3": _member("m3", count=4, created=_T0 + timedelta(hours=3), sha="a"),
            # same count and time as m3, decided by hash alone
            "m4": _member("m4", count=4, created=_T0 + timedelta(hours=3), sha="c"),
            # same count, no creation time
            "m6": _member("m6", count=4, created=None, sha="0"),
            # no count, but the newest and lowest hash of all
            "m5": _member("m5", count=None, created=_T0 + timedelta(hours=9), sha="00"),
        }

    def test_the_order_is_count_then_time_then_hash_with_absent_last(self) -> None:
        members = self._six()
        expected = ["m1", "m2", "m3", "m4", "m6", "m5"]
        assert _order(members, DEFAULT_PRECEDENCE) == expected

    def test_every_permutation_of_the_six_yields_the_same_roles(self) -> None:
        members = list(self._six().values())
        reference = rank_members(members, ("u",), DEFAULT_PRECEDENCE)
        assert reference.base.ref == "m1"
        checked = 0
        for permutation in itertools.permutations(members):
            assert rank_members(permutation, ("u",), DEFAULT_PRECEDENCE) == reference
            checked += 1
        assert checked == 720


class TestKindAgainstOtherKeys:
    def test_every_permutation_of_four_members_yields_the_same_roles(self) -> None:
        # Each better-ranked kind is worse on count, time and hash.
        members = [
            _member(
                "garmin",
                manufacturer="garmin",
                count=0,
                created=None,
                sha="z",
            ),
            _member(
                "copy",
                kind=SourceKind.PHONE_COPY,
                manufacturer="development",
                count=1,
                created=_T0,
                sha="y",
            ),
            _member(
                "stryd",
                manufacturer="stryd",
                count=5,
                created=_T0 + timedelta(hours=1),
                sha="b",
            ),
            _member(
                "unknown",
                kind=SourceKind.UNKNOWN,
                manufacturer=None,
                count=99,
                created=_T0 + timedelta(hours=2),
                sha="a",
            ),
        ]
        reference = rank_members(members, (), DEFAULT_PRECEDENCE)
        assert [m.ref for m in (reference.base, *reference.extras)] == [
            "garmin",
            "copy",
            "stryd",
            "unknown",
        ]
        for permutation in itertools.permutations(members):
            assert rank_members(permutation, (), DEFAULT_PRECEDENCE) == reference


class TestPageRoles:
    def _roles(self) -> PageRoles:
        members = [
            _member("b", count=2, sha="b"),
            _member("c", count=1, sha="c"),
            _member("a", count=3, sha="a"),
        ]
        return rank_members(members, ("u2", "u1"), DEFAULT_PRECEDENCE)

    def test_base_extras_best_first_and_unresolved_in_the_order_given(self) -> None:
        roles = self._roles()
        assert roles.base.ref == "a"
        assert [m.ref for m in roles.extras] == ["b", "c"]
        assert roles.unresolved == ("u2", "u1")

    def test_sources_ascend_in_rank_with_the_base_last(self) -> None:
        assert self._roles().sources == ("u2", "u1", "c", "b", "a")

    def test_unresolved_refs_are_never_the_base(self) -> None:
        roles = rank_members([_member("only")], ("gone",), DEFAULT_PRECEDENCE)
        assert roles.base.ref == "only"
        assert roles.extras == ()
        assert roles.sources == ("gone", "only")

    def test_no_resolved_member_is_refused(self) -> None:
        with pytest.raises(ValueError):
            rank_members([], ("gone",), DEFAULT_PRECEDENCE)


class TestPageSessionUuid:
    _UUID_BASE = "11111111-1111-1111-1111-111111111111"
    _UUID_FIRST = "22222222-2222-2222-2222-222222222222"
    _UUID_SECOND = "33333333-3333-3333-3333-333333333333"
    _RECORDED = "44444444-4444-4444-4444-444444444444"

    def test_the_base_carries_it(self) -> None:
        roles = rank_members(
            [
                _member("a", count=2, session_uuid=self._UUID_BASE),
                _member("b", count=1, session_uuid=self._UUID_FIRST),
            ],
            (),
            DEFAULT_PRECEDENCE,
        )
        assert page_session_uuid(roles, self._RECORDED) == self._UUID_BASE

    def test_retained_through_the_first_extra_that_carries_one(self) -> None:
        roles = rank_members(
            [
                _member("a", count=4),
                _member("b", count=3),
                _member("c", count=2, session_uuid=self._UUID_FIRST),
                _member("d", count=1, session_uuid=self._UUID_SECOND),
            ],
            (),
            DEFAULT_PRECEDENCE,
        )
        assert page_session_uuid(roles, self._RECORDED) == self._UUID_FIRST

    def test_retained_through_the_recorded_value_when_no_member_has_one(self) -> None:
        roles = rank_members(
            [_member("a", count=2), _member("b", count=1)], ("u",), DEFAULT_PRECEDENCE
        )
        assert page_session_uuid(roles, self._RECORDED) == self._RECORDED

    def test_absent_everywhere_is_none(self) -> None:
        roles = rank_members([_member("a")], (), DEFAULT_PRECEDENCE)
        assert page_session_uuid(roles, None) is None

"""The document contract: region-ownership policy, vocabulary, pure readers.

These pin :mod:`fitdocs.contract` -- the pure policy leaf that says *which*
regions a fitdocs document reserves, *who owns* each one, what a freshly
rendered region carries, and how a document's frontmatter, identity, format
version, and source history are read -- against the approved DocumentContract
interface (design §DocumentContract) and Req 1.1-1.4, 5.7, 6.2: one
interpretation of a document, applied identically by every command.

The policy moved here from :mod:`fitdocs.docmerge` (task 1.1), which keeps only
the region *grammar* (marker composition, extraction, merging) and is generic
over region ids. Two assertions therefore matter as much as the values
themselves: the preserved tuple keeps its historical order (``notes``,
``workout``, ``load``), because merge order and every published enumeration
depend on it; and the merge module exports no policy constant any more, so
there is exactly one place a region id or placeholder can be defined.

Task 1.2 added the schema vocabulary and the readers. Two properties are tested
for every reader, because they are what let a consumer delete its own copy:

* **the success path** -- the value a well-formed document yields; and
* **the degradation path** -- an absent value (``None``, ``()``, ``False``)
  rather than an exception, for absent, malformed, wrong-typed, and adversarial
  input. Absent is never a fabricated ``0`` (steering: ``tech.md``).

The reader cases are the union of the cases the implementations this module
replaces already satisfy -- the sync engine's and load engine's frontmatter
parsers, the load doc editor's fence scan, the sync engine's archive-ref
resolver, and the two session-UUID formatters (``layout`` and
``render.frontmatter``) -- so parity is proven by construction rather than by
reaching into those modules' privates.

Everything here is pure, so the tests are direct value assertions.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

import pytest

from fitdocs import contract, docmerge

# --------------------------------------------------------------------------- #
# Region ids and ownership groupings (Req 1.4)
# --------------------------------------------------------------------------- #


def test_region_ids_are_the_exact_marker_tokens() -> None:
    assert contract.NOTES_REGION == "notes"
    assert contract.WORKOUT_REGION == "workout"
    assert contract.LOAD_REGION == "load"


def test_user_regions_are_the_two_hand_authored_ones() -> None:
    assert contract.USER_REGIONS == ("notes", "workout")


def test_tool_regions_are_the_machine_filled_ones() -> None:
    assert contract.TOOL_REGIONS == ("load",)


def test_preserved_regions_is_user_then_tool_in_historical_order() -> None:
    assert contract.PRESERVED_REGIONS == ("notes", "workout", "load")
    assert contract.PRESERVED_REGIONS == contract.USER_REGIONS + contract.TOOL_REGIONS


def test_every_preserved_region_is_owned_exactly_once() -> None:
    """No id is both user-owned and tool-filled, and none is unowned."""
    assert set(contract.USER_REGIONS).isdisjoint(contract.TOOL_REGIONS)
    assert len(set(contract.PRESERVED_REGIONS)) == len(contract.PRESERVED_REGIONS)


# --------------------------------------------------------------------------- #
# Fresh-region content (Req 1.4)
# --------------------------------------------------------------------------- #


def test_load_not_computed_is_the_exact_placeholder_line() -> None:
    assert contract.LOAD_NOT_COMPUTED == "_Training load not computed._"


def test_notes_placeholder_is_instructive_and_names_the_guarantee() -> None:
    assert contract.NOTES_PLACEHOLDER == (
        "_Your notes go here. This section is preserved when the document is "
        "regenerated._"
    )


def test_workout_placeholder_is_instructive_and_names_the_guarantee() -> None:
    assert contract.WORKOUT_PLACEHOLDER == (
        "_Record the workout you performed here -- exercises, sets, reps, and "
        "load. This section is preserved when the document is regenerated._"
    )


def test_fresh_region_contents_carry_no_digits() -> None:
    """A freshly rendered region states a guarantee, never a fabricated value."""
    for text in (
        contract.LOAD_NOT_COMPUTED,
        contract.NOTES_PLACEHOLDER,
        contract.WORKOUT_PLACEHOLDER,
    ):
        assert not any(char.isdigit() for char in text)


# --------------------------------------------------------------------------- #
# The merge module is pure mechanism (Req 1.4)
# --------------------------------------------------------------------------- #


def test_merge_module_exports_no_policy_constant() -> None:
    """``docmerge`` keeps grammar only -- policy has exactly one home."""
    for name in (
        "PRESERVED_REGIONS",
        "LOAD_NOT_COMPUTED",
        "NOTES_PLACEHOLDER",
        "WORKOUT_PLACEHOLDER",
        "USER_REGIONS",
        "TOOL_REGIONS",
    ):
        assert not hasattr(docmerge, name), f"docmerge still exports {name}"


def test_region_ids_compose_with_the_merge_grammar() -> None:
    """The policy's ids are exactly what the grammar round-trips."""
    document = "".join(
        docmerge.region_block(region_id, f"content for {region_id}")
        for region_id in contract.PRESERVED_REGIONS
    )
    assert docmerge.extract_regions(document) == {
        region_id: f"content for {region_id}"
        for region_id in contract.PRESERVED_REGIONS
    }


def test_marker_helpers_are_re_exported_from_the_merge_module() -> None:
    """One import for a consumer: the contract re-exports the grammar helpers.

    Identity (``is``), not equality -- a re-export must be the merge module's own
    function object, never a second implementation that could drift from it.
    """
    assert contract.begin_marker is docmerge.begin_marker
    assert contract.end_marker is docmerge.end_marker
    assert contract.region_block is docmerge.region_block


# --------------------------------------------------------------------------- #
# Document vocabulary (Req 1.1, 6.2)
# --------------------------------------------------------------------------- #


def test_document_vocabulary_is_the_literal_text_documents_carry() -> None:
    """Every constant is the exact token a written document already holds."""
    assert contract.WORKOUT_TYPE == "workout"
    assert contract.GENERATOR == "fitdocs"
    assert contract.FRONTMATTER_FENCE == "---"


def test_frontmatter_key_names_are_the_emitted_spellings() -> None:
    assert contract.TYPE_KEY == "type"
    assert contract.GENERATOR_KEY == "generator"
    assert contract.DOC_VERSION_KEY == "doc_version"
    assert contract.UUID_KEY == "uuid"
    assert contract.SOURCES_KEY == "sources"


def test_load_keys_are_the_three_training_load_keys_in_emission_order() -> None:
    assert contract.LOAD_KEYS == ("load_value", "load_methodology", "load_basis")


def test_load_keys_are_a_subset_of_the_managed_keys() -> None:
    """Policy invariant (6.2): the load pass writes keys fitdocs manages.

    If a load key fell outside ``MANAGED_KEYS`` the unmanaged-key warning would
    fire on every document the load pass has touched.
    """
    assert set(contract.LOAD_KEYS) <= contract.MANAGED_KEYS


# The published frontmatter schema, spelled out independently of the module so a
# key can never be added on one side alone (design §Logical Data Model).
_PUBLISHED_KEYS = {
    "title",
    "type",
    "generator",
    "doc_version",
    "uuid",
    "date",
    "start_time",
    "sport",
    "modality",
    "indoor",
    "distance_km",
    "moving_time",
    "avg_hr_bpm",
    "avg_power_w",
    "elevation_gain_m",
    "calories_kcal",
    "sources",
    "load_value",
    "load_methodology",
    "load_basis",
}


def test_managed_keys_is_the_published_frontmatter_schema() -> None:
    """6.2: the complete published set, including the training-load keys."""
    assert set(contract.MANAGED_KEYS) == _PUBLISHED_KEYS


def test_managed_keys_contains_every_named_key_constant() -> None:
    """A key the contract names by constant is, by definition, one it manages."""
    for key in (
        contract.TYPE_KEY,
        contract.GENERATOR_KEY,
        contract.DOC_VERSION_KEY,
        contract.UUID_KEY,
        contract.SOURCES_KEY,
    ):
        assert key in contract.MANAGED_KEYS


def test_managed_keys_is_an_immutable_frozenset() -> None:
    assert isinstance(contract.MANAGED_KEYS, frozenset)


def test_managed_keys_equals_the_builders_emittable_keys_plus_load_keys() -> None:
    """Anti-drift (design §DocumentContract Implementation Notes; task 3.1): the
    published managed set is EXACTLY the keys
    :func:`fitdocs.render.frontmatter.build_frontmatter` can emit, union
    :data:`~fitdocs.contract.LOAD_KEYS` -- failing the moment a key is added to
    either side alone.

    Reads the emittable set from ``build_frontmatter``'s own AST -- every
    ``data[<key>] = ...`` assignment -- rather than re-typing it by hand: a
    literal string key is used directly, and a bare name (an imported contract
    constant such as ``GENERATOR_KEY``) is resolved by looking it up in the
    frontmatter module's own namespace, so the two can never merely agree by
    coincidence.
    """
    from fitdocs.render import frontmatter as frontmatter_module

    tree = ast.parse(inspect.getsource(frontmatter_module.build_frontmatter))
    emittable: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (
                isinstance(target, ast.Subscript)
                and isinstance(target.value, ast.Name)
                and target.value.id == "data"
            ):
                continue
            key_node = target.slice
            if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                emittable.add(key_node.value)
            elif isinstance(key_node, ast.Name):
                emittable.add(getattr(frontmatter_module, key_node.id))
            else:
                raise AssertionError(f"unrecognized frontmatter key node: {key_node!r}")

    assert emittable, "no emittable keys found -- the AST walk found nothing"
    assert emittable | set(contract.LOAD_KEYS) == set(contract.MANAGED_KEYS)
    # Sibling assertion (task 1.1, Req 1.1, 1.5): the keys the render layer can
    # actually emit never collide with the user-owned effort-tag keys either --
    # the same anti-drift discipline, applied to the second boundary.
    assert emittable.isdisjoint(contract.USER_KEYS)


# --------------------------------------------------------------------------- #
# The effort-tag vocabulary: keys, USER_KEYS, EffortKind, and the three value
# types (task 1.1, design §EffortVocabulary, Req 1.1, 1.4, 1.5, 2.1, 2.2, 5.3,
# 5.5)
# --------------------------------------------------------------------------- #


def test_effort_key_constants_are_the_four_spellings_in_documentation_order() -> None:
    """2.1: the exact spellings, and EFFORT_KEYS carries them in that order."""
    assert contract.EFFORT_KEY == "effort"
    assert contract.EFFORT_DISTANCE_KEY == "effort_distance_m"
    assert contract.EFFORT_TIME_KEY == "effort_time_s"
    assert contract.EFFORT_EVENT_KEY == "effort_event"
    assert contract.EFFORT_KEYS == (
        contract.EFFORT_KEY,
        contract.EFFORT_DISTANCE_KEY,
        contract.EFFORT_TIME_KEY,
        contract.EFFORT_EVENT_KEY,
    )


def test_user_keys_equals_the_exact_frozenset_of_effort_keys() -> None:
    """1.1: USER_KEYS is exactly the frozenset of EFFORT_KEYS, and is a frozenset."""
    assert frozenset(contract.EFFORT_KEYS) == contract.USER_KEYS
    assert isinstance(contract.USER_KEYS, frozenset)
    # The literal spelling pinned by the task's own Observable line -- defeats a
    # USER_KEYS built from the wrong constants that still happens to equal
    # frozenset(EFFORT_KEYS) by construction.
    assert (
        frozenset({"effort", "effort_distance_m", "effort_time_s", "effort_event"})
        == contract.USER_KEYS
    )


def test_user_keys_is_disjoint_with_managed_keys() -> None:
    """1.1, 1.5: no key is both fitdocs-written and user-owned.

    Named mutation (task 1.1): adding ``"effort"`` to ``MANAGED_KEYS`` reddens
    this assertion (and the anti-drift equality above) together.
    """
    assert contract.USER_KEYS.isdisjoint(contract.MANAGED_KEYS)


def test_effort_kind_is_the_closed_three_value_enumeration() -> None:
    """2.2: exactly race/test/hard -- a fourth value is rejected, not accepted."""
    assert {member.value for member in contract.EffortKind} == {"race", "test", "hard"}
    assert contract.EffortKind.RACE == "race"
    assert contract.EffortKind.TEST == "test"
    assert contract.EffortKind.HARD == "hard"
    with pytest.raises(ValueError):
        contract.EffortKind("marathon")


def test_effort_tag_is_a_frozen_dataclass_with_kind_and_three_optional_fields() -> None:
    """5.3: kind plus three fields typed to accept None -- no fabricated default.

    Reading back a ``None`` passed by this same test would be true before any
    production change (post-condition-true-beforehand), so the "optional"
    half of the claim is pinned on the *annotation* instead: each of the three
    fields' type hint includes ``NoneType``, via ``typing.get_type_hints`` so a
    ``from __future__ import annotations`` string annotation is resolved to the
    real type before inspection.
    """
    import typing

    field_names = {field.name for field in dataclasses.fields(contract.EffortTag)}
    assert field_names == {"kind", "distance_m", "time_s", "event"}

    hints = typing.get_type_hints(contract.EffortTag)
    assert hints["kind"] is contract.EffortKind
    for optional_field in ("distance_m", "time_s", "event"):
        assert type(None) in typing.get_args(hints[optional_field]), optional_field

    # No default is fabricated: dataclasses reports MISSING, not a real value,
    # for every field -- constructing without all four arguments is a TypeError.
    assert all(
        field.default is dataclasses.MISSING
        for field in dataclasses.fields(contract.EffortTag)
    )
    with pytest.raises(TypeError):
        contract.EffortTag(kind=contract.EffortKind.RACE, distance_m=None, time_s=None)  # type: ignore[call-arg]

    tag = contract.EffortTag(
        kind=contract.EffortKind.RACE, distance_m=None, time_s=None, event=None
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        tag.kind = contract.EffortKind.TEST  # type: ignore[misc]


def test_effort_tag_problem_is_a_frozen_dataclass_of_key_and_detail() -> None:
    """3.3: both fields are ``str`` (not e.g. an ``int`` key or a ``list`` of
    details), and neither has a fabricated default -- the same discrimination
    applied to ``EffortTag`` in the sibling test above, carried across.
    """
    import typing

    field_names = {
        field.name for field in dataclasses.fields(contract.EffortTagProblem)
    }
    assert field_names == {"key", "detail"}

    hints = typing.get_type_hints(contract.EffortTagProblem)
    assert hints["key"] is str
    assert hints["detail"] is str

    assert all(
        field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
        for field in dataclasses.fields(contract.EffortTagProblem)
    )
    with pytest.raises(TypeError):
        contract.EffortTagProblem(key=contract.EFFORT_KEY)  # type: ignore[call-arg]

    problem = contract.EffortTagProblem(key=contract.EFFORT_KEY, detail="bad kind")
    with pytest.raises(dataclasses.FrozenInstanceError):
        problem.detail = "other"  # type: ignore[misc]


def test_invalid_effort_tag_is_a_frozen_dataclass_of_problems() -> None:
    """5.3: the third value type -- ``problems`` -- is frozen like the other two,
    and ``problems`` is annotated as a ``tuple[EffortTagProblem, ...]`` -- not a
    ``list`` (which would make the frozen instance's contents mutable in place
    and the instance itself unhashable) and not a fabricated ``()`` default.
    """
    import typing

    field_names = {
        field.name for field in dataclasses.fields(contract.InvalidEffortTag)
    }
    assert field_names == {"problems"}

    hints = typing.get_type_hints(contract.InvalidEffortTag)
    assert typing.get_origin(hints["problems"]) is tuple
    assert typing.get_args(hints["problems"]) == (contract.EffortTagProblem, Ellipsis)

    assert all(
        field.default is dataclasses.MISSING
        and field.default_factory is dataclasses.MISSING
        for field in dataclasses.fields(contract.InvalidEffortTag)
    )
    with pytest.raises(TypeError):
        contract.InvalidEffortTag()  # type: ignore[call-arg]

    invalid = contract.InvalidEffortTag(
        problems=(contract.EffortTagProblem(key=contract.EFFORT_KEY, detail="x"),)
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        invalid.problems = ()  # type: ignore[misc]


def test_invalid_effort_tag_describe_joins_key_detail_pairs_in_given_order() -> None:
    """5.6: ``describe()`` renders ``"key: detail"`` pairs joined by ``"; "``.

    Two distinct, non-alphabetically-sorted problems: this defeats a joiner
    that uses ``", "`` instead of ``"; "``, a separator other than ``": "``
    between key and detail, and an implementation that sorts the problems
    rather than preserving the order given.
    """
    invalid = contract.InvalidEffortTag(
        problems=(
            contract.EffortTagProblem(
                key=contract.EFFORT_TIME_KEY, detail="must be a positive number"
            ),
            contract.EffortTagProblem(
                key=contract.EFFORT_KEY, detail="must be one of race, test, hard"
            ),
        )
    )
    assert invalid.describe() == (
        "effort_time_s: must be a positive number; "
        "effort: must be one of race, test, hard"
    )


# --------------------------------------------------------------------------- #
# Version numbers (Req 5.1, 2.8)
# --------------------------------------------------------------------------- #


def test_doc_version_is_a_plain_positive_integer() -> None:
    assert isinstance(contract.DOC_VERSION, int)
    assert not isinstance(contract.DOC_VERSION, bool)
    assert contract.DOC_VERSION >= 1


def test_doc_version_equals_the_version_stamped_on_the_committed_goldens() -> None:
    """Byte-neutrality guard for tasks 1 and 2 (design §Migration Strategy).

    The constant is *moved* at its existing value here; raising it is task 3.1's
    job, and it may only be raised in the same change that regenerates the
    goldens. Reading the version back out of a committed golden through the
    contract's own parser proves both halves at once: the constant still matches
    what the renderer wrote, and ``parse_frontmatter`` reads a real document.
    """
    golden = Path(__file__).parent / "render" / "golden_docs" / "minimal.md"
    frontmatter = contract.parse_frontmatter(golden.read_text(encoding="utf-8"))
    assert frontmatter is not None
    assert frontmatter[contract.DOC_VERSION_KEY] == contract.DOC_VERSION


def test_contract_version_is_a_non_empty_string_identifier() -> None:
    """2.8: the published contract's version is an identifier, not a number.

    It is stated in prose (the published contract, every in-tree declaration),
    so it is a string and is never compared arithmetically with ``DOC_VERSION``.
    """
    assert isinstance(contract.CONTRACT_VERSION, str)
    assert contract.CONTRACT_VERSION.strip() == contract.CONTRACT_VERSION
    assert contract.CONTRACT_VERSION


# --------------------------------------------------------------------------- #
# parse_frontmatter (Req 1.1, 1.2)
# --------------------------------------------------------------------------- #

_DOC = (
    "---\n"
    "title: Run 2021-09-07 19:46\n"
    "type: workout\n"
    "doc_version: 1\n"
    "uuid: 00010203-0405-0607-0809-0a0b0c0d0e0f\n"
    "sources:\n"
    "- fit-archive/aaaa.fit\n"
    "- fit-archive/bbbb.fit\n"
    "---\n"
    "\n"
    "# Run 2021-09-07 19:46\n"
)


def test_parse_frontmatter_returns_the_fenced_mapping() -> None:
    parsed = contract.parse_frontmatter(_DOC)
    assert parsed is not None
    assert parsed["type"] == "workout"
    assert parsed["doc_version"] == 1
    assert parsed["sources"] == ["fit-archive/aaaa.fit", "fit-archive/bbbb.fit"]


def test_parse_frontmatter_stops_at_the_first_closing_fence() -> None:
    """A later ``---`` in the body is a horizontal rule, not a second fence."""
    text = "---\ntype: workout\n---\n\nbody\n\n---\n\nmore body\n"
    assert contract.parse_frontmatter(text) == {"type": "workout"}


def test_parse_frontmatter_tolerates_whitespace_around_the_fences() -> None:
    assert contract.parse_frontmatter("---  \ntype: workout\n  ---\n") == {
        "type": "workout"
    }


def test_parse_frontmatter_yields_none_without_a_leading_fence() -> None:
    assert contract.parse_frontmatter("# Just a heading\n\ntype: workout\n") is None


def test_parse_frontmatter_yields_none_for_an_unterminated_block() -> None:
    assert contract.parse_frontmatter("---\ntype: workout\n\nbody\n") is None


def test_parse_frontmatter_yields_none_for_unparseable_yaml() -> None:
    """A YAML error degrades to absent -- the caller skips the file (1.2)."""
    assert contract.parse_frontmatter("---\ntype: [unclosed\n---\n") is None


def test_parse_frontmatter_yields_none_for_a_non_mapping_block() -> None:
    """A sequence or a scalar is well-formed YAML but is not frontmatter (1.2)."""
    assert contract.parse_frontmatter("---\n- one\n- two\n---\n") is None
    assert contract.parse_frontmatter("---\njust a scalar\n---\n") is None


def test_parse_frontmatter_yields_none_for_an_empty_block() -> None:
    assert contract.parse_frontmatter("---\n---\n") is None


def test_parse_frontmatter_yields_none_for_empty_text() -> None:
    assert contract.parse_frontmatter("") is None


# --------------------------------------------------------------------------- #
# frontmatter_close_index (Req 1.1)
# --------------------------------------------------------------------------- #


def test_frontmatter_close_index_locates_the_closing_fence() -> None:
    lines = _DOC.split("\n")
    close = contract.frontmatter_close_index(lines)
    assert close is not None
    assert lines[close].strip() == contract.FRONTMATTER_FENCE
    assert close == 8


def test_frontmatter_close_index_keeps_the_lossless_split_contract() -> None:
    """The index is an offset into ``split("\\n")``, so slicing is byte-exact.

    This is what lets the load doc editor rewrite frontmatter lines without ever
    re-serializing the renderer's YAML.
    """
    lines = _DOC.split("\n")
    close = contract.frontmatter_close_index(lines)
    assert close is not None
    rebuilt = "\n".join([lines[0], *lines[1:close], *lines[close:]])
    assert rebuilt == _DOC


def test_frontmatter_close_index_yields_none_without_a_leading_fence() -> None:
    assert contract.frontmatter_close_index(["# Heading", "body"]) is None


def test_frontmatter_close_index_yields_none_for_an_unterminated_block() -> None:
    assert contract.frontmatter_close_index(["---", "type: workout"]) is None


def test_frontmatter_close_index_yields_none_for_no_lines() -> None:
    assert contract.frontmatter_close_index([]) is None


# --------------------------------------------------------------------------- #
# is_workout_document (Req 1.1, 1.2)
# --------------------------------------------------------------------------- #


def test_is_workout_document_recognizes_the_type_marker() -> None:
    assert contract.is_workout_document({"type": "workout"}) is True


def test_is_workout_document_rejects_an_absent_frontmatter() -> None:
    """1.2: an unparseable document is not a fitdocs document, in every command."""
    assert contract.is_workout_document(None) is False


def test_is_workout_document_rejects_a_foreign_or_missing_type() -> None:
    assert contract.is_workout_document({}) is False
    assert contract.is_workout_document({"type": "recipe"}) is False
    assert contract.is_workout_document({"type": None}) is False
    assert contract.is_workout_document({"type": 1}) is False


def test_is_workout_document_ignores_an_in_tree_declaration() -> None:
    """3.7: the ownership declaration carries no frontmatter, so it never scans."""
    declaration = f"{contract.GENERATED_PREFIX} -->\n\n# This directory\n"
    assert (
        contract.is_workout_document(contract.parse_frontmatter(declaration)) is False
    )


# --------------------------------------------------------------------------- #
# is_generated (Req 3.6, 4.1)
# --------------------------------------------------------------------------- #


def test_is_generated_recognizes_the_provenance_prefix() -> None:
    stamp = f"{contract.GENERATED_PREFIX} by fitdocs -->\n"
    assert contract.is_generated(stamp) is True


def test_is_generated_finds_the_stamp_below_a_frontmatter_block() -> None:
    """On a workout document the stamp sits between the fence and the title."""
    text = f"---\ntype: workout\n---\n\n{contract.GENERATED_PREFIX} -->\n\n# Run\n"
    assert contract.is_generated(text) is True


def test_is_generated_rejects_a_hand_authored_file() -> None:
    assert contract.is_generated("# My own notes\n\nfitdocs is great.\n") is False
    assert contract.is_generated("") is False


def test_is_generated_rejects_an_indented_lookalike() -> None:
    """A marker inside a code block or a list is not a column-zero stamp."""
    assert contract.is_generated(f"    {contract.GENERATED_PREFIX} -->\n") is False


def test_doc_banner_starts_with_the_generated_prefix() -> None:
    """4.1: the banner is recognized by :func:`is_generated` like any other
    provenance stamp."""
    assert contract.DOC_BANNER.startswith(contract.GENERATED_PREFIX)
    assert contract.is_generated(contract.DOC_BANNER + "\n")


def test_doc_banner_is_one_line_and_a_well_formed_html_comment() -> None:
    assert "\n" not in contract.DOC_BANNER
    assert contract.DOC_BANNER.startswith("<!--")
    assert contract.DOC_BANNER.endswith("-->")


def test_doc_banner_names_the_tool_and_the_declaration() -> None:
    """4.2: names fitdocs, states the regeneration boundary, points at the
    in-tree declaration."""
    assert contract.GENERATOR in contract.DOC_BANNER
    assert "regenerat" in contract.DOC_BANNER
    assert "AGENTS.md" in contract.DOC_BANNER


def test_doc_banner_carries_no_run_or_release_varying_value() -> None:
    """4.5: no tool version, no timestamp -- nothing that varies between runs or
    between releases."""
    assert not any(char.isdigit() for char in contract.DOC_BANNER)


def test_generated_prefix_can_never_be_read_as_a_region_marker() -> None:
    """Data contract: the stamp must not collide with the merge grammar.

    ``docmerge``'s marker regex accepts only ``begin``/``end`` for its kind, so a
    ``generated`` comment extracts as no region at all rather than as a damaged
    one (which would raise and fail the document).
    """
    stamp = f"{contract.GENERATED_PREFIX} by fitdocs -->\n"
    assert docmerge.extract_regions(stamp) == {}


# --------------------------------------------------------------------------- #
# document_uuid -- recorded activity identity (Req 1.1, 1.3)
# --------------------------------------------------------------------------- #


def test_document_uuid_returns_the_recorded_session_identifier() -> None:
    parsed = contract.parse_frontmatter(_DOC)
    assert parsed is not None
    assert contract.document_uuid(parsed) == "00010203-0405-0607-0809-0a0b0c0d0e0f"


def test_document_uuid_yields_none_when_the_key_is_absent() -> None:
    """Absent is honest: not every activity records a session UUID (5.6)."""
    assert contract.document_uuid({"type": "workout"}) is None


def test_document_uuid_yields_none_for_a_non_string_or_empty_value() -> None:
    assert contract.document_uuid({"uuid": 12345}) is None
    assert contract.document_uuid({"uuid": None}) is None
    assert contract.document_uuid({"uuid": ["a"]}) is None
    assert contract.document_uuid({"uuid": ""}) is None


# --------------------------------------------------------------------------- #
# document_version (Req 5.7)
# --------------------------------------------------------------------------- #


def test_document_version_returns_a_genuine_integer() -> None:
    assert contract.document_version({"doc_version": 1}) == 1
    assert contract.document_version({"doc_version": 7}) == 7


def test_document_version_rejects_a_boolean() -> None:
    """``bool`` subclasses ``int`` in Python -- ``True`` is not version 1 (5.7)."""
    assert contract.document_version({"doc_version": True}) is None
    assert contract.document_version({"doc_version": False}) is None


def test_document_version_rejects_non_integer_values() -> None:
    """5.7: an unusable value is absent, never coerced and never a fabricated 0."""
    for value in ("1", 1.0, 1.5, None, [1], {"v": 1}):
        assert contract.document_version({"doc_version": value}) is None


def test_document_version_yields_none_when_the_key_is_absent() -> None:
    assert contract.document_version({}) is None
    assert contract.document_version({"type": "workout"}) is None


def test_document_version_passes_a_negative_integer_through() -> None:
    """A negative version is a genuine integer, so it classifies as out of date.

    5.7 asks only that a missing or unusable version never read as *newer*; a
    negative value compares below :data:`~fitdocs.contract.DOC_VERSION` and so
    reaches the same outcome without a special case.
    """
    assert contract.document_version({"doc_version": -3}) == -3
    assert contract.document_version({"doc_version": -3}) < contract.DOC_VERSION


# --------------------------------------------------------------------------- #
# document_date -- the document's own recorded local calendar date
# (Amendment 3, cross-spec training-load/athlete-benchmarks incursion)
# --------------------------------------------------------------------------- #


def test_document_date_parses_the_quoted_iso_string_fitdocs_emits() -> None:
    """The ordinary case: ``render.frontmatter`` always quotes the ``date``
    value, so ``parse_frontmatter`` hands this accessor a plain ``str``."""
    from datetime import date

    assert contract.document_date({"date": "2024-01-15"}) == date(2024, 1, 15)


def test_document_date_accepts_a_genuine_date_object() -> None:
    """A hand-edited document that leaves ``date`` unquoted is read by PyYAML
    as a genuine :class:`datetime.date` -- accepted, not rejected, since it is
    exactly the value this accessor promises to return."""
    from datetime import date

    assert contract.document_date({"date": date(2024, 1, 15)}) == date(2024, 1, 15)


def test_document_date_rejects_a_datetime() -> None:
    """A ``datetime`` carries a time-of-day and time zone this accessor never
    reads -- ``bool`` subclasses ``int`` is the precedent (``document_version``);
    here a ``datetime`` subclasses ``date`` and is rejected explicitly."""
    from datetime import datetime

    assert contract.document_date({"date": datetime(2024, 1, 15, 12, 0)}) is None


def test_document_date_yields_none_for_absent_frontmatter() -> None:
    """``frontmatter`` may itself be the absent value :func:`parse_frontmatter`
    returns -- the accessor is composable with it, like ``is_workout_document``."""
    assert contract.document_date(None) is None


def test_document_date_yields_none_when_the_key_is_absent() -> None:
    assert contract.document_date({}) is None
    assert contract.document_date({"type": "workout"}) is None


def test_document_date_yields_none_for_an_unparseable_string() -> None:
    assert contract.document_date({"date": "not-a-date"}) is None
    assert contract.document_date({"date": "2024-13-99"}) is None
    assert contract.document_date({"date": ""}) is None


def test_document_date_yields_none_for_wrong_shaped_values() -> None:
    for value in (2024, 1.5, ["2024-01-15"], {"y": 2024}, None):
        assert contract.document_date({"date": value}) is None


# --------------------------------------------------------------------------- #
# source_refs -- the source history (Req 1.3)
# --------------------------------------------------------------------------- #


def test_source_refs_returns_the_history_in_append_order() -> None:
    parsed = contract.parse_frontmatter(_DOC)
    assert parsed is not None
    refs = contract.source_refs(parsed)
    assert refs == ("fit-archive/aaaa.fit", "fit-archive/bbbb.fit")
    # The last entry is the current render source (Req 1.3).
    assert refs[-1] == "fit-archive/bbbb.fit"


def test_source_refs_yields_an_empty_tuple_when_absent() -> None:
    assert contract.source_refs({"type": "workout"}) == ()


def test_source_refs_yields_an_empty_tuple_for_a_non_list_value() -> None:
    assert contract.source_refs({"sources": "fit-archive/aaaa.fit"}) == ()
    assert contract.source_refs({"sources": None}) == ()
    assert contract.source_refs({"sources": {"a": 1}}) == ()


def test_source_refs_drops_non_string_entries() -> None:
    """A hand-edited history degrades entry-wise rather than failing the doc."""
    assert contract.source_refs({"sources": ["fit-archive/aaaa.fit", 7, None]}) == (
        "fit-archive/aaaa.fit",
    )
    assert contract.source_refs({"sources": []}) == ()


# --------------------------------------------------------------------------- #
# sha_of_ref -- archive-ref resolution (Req 1.3)
# --------------------------------------------------------------------------- #

_SHA = "a" * 64


def test_sha_of_ref_extracts_the_sha_from_a_well_formed_ref() -> None:
    assert contract.sha_of_ref(f"fit-archive/{_SHA}.fit") == _SHA


def test_sha_of_ref_is_the_inverse_of_the_layout_ref_builder() -> None:
    """Anti-drift: the reader and the writer of a ref must agree on its shape.

    The contract cannot import :mod:`fitdocs.layout` (it is a leaf below it), so
    the two spell the archive directory separately; this round trip is what keeps
    them from diverging.
    """
    from fitdocs.layout import source_ref

    assert contract.sha_of_ref(source_ref(_SHA)) == _SHA


def test_sha_of_ref_yields_none_for_a_foreign_ref() -> None:
    for ref in (
        f"somewhere-else/{_SHA}.fit",
        f"{_SHA}.fit",
        f"fit-archive/{_SHA}.md",
        f"/fit-archive/{_SHA}.fit",
        "",
    ):
        assert contract.sha_of_ref(ref) is None, ref


def test_sha_of_ref_yields_none_for_an_empty_sha() -> None:
    assert contract.sha_of_ref("fit-archive/.fit") is None


def test_sha_of_ref_yields_none_for_a_traversal_shaped_ref() -> None:
    """A hand-edited ref must never resolve into a path component (1.3).

    The sha is joined onto the data root by the caller, so anything that is not
    a bare hex digest -- a traversal, a nested path, an absolute component -- is
    unresolvable rather than a lookup outside the archive.
    """
    for ref in (
        "fit-archive/../../etc/passwd.fit",
        "fit-archive/../secrets.fit",
        "fit-archive/nested/dir.fit",
        "fit-archive/~.fit",
        f"fit-archive/{_SHA}/../x.fit",
    ):
        assert contract.sha_of_ref(ref) is None, ref


# --------------------------------------------------------------------------- #
# unmanaged_keys (Req 6.2, 6.3)
# --------------------------------------------------------------------------- #


def test_unmanaged_keys_is_empty_for_a_fully_managed_document() -> None:
    parsed = contract.parse_frontmatter(_DOC)
    assert parsed is not None
    assert contract.unmanaged_keys(parsed) == ()


def test_unmanaged_keys_is_empty_after_a_training_load_pass() -> None:
    """6.2: the three load keys are managed, so they never warn."""
    frontmatter = {key: "x" for key in contract.LOAD_KEYS}
    frontmatter["type"] = "workout"
    assert contract.unmanaged_keys(frontmatter) == ()


def test_unmanaged_keys_names_hand_added_keys_sorted() -> None:
    assert contract.unmanaged_keys(
        {"type": "workout", "tags": ["a"], "aliases": ["b"], "rating": 5}
    ) == ("aliases", "rating", "tags")


def test_unmanaged_keys_ignores_non_string_keys() -> None:
    """YAML admits non-string keys; fitdocs cannot name one in a warning."""
    assert contract.unmanaged_keys({1: "x", "tags": ["a"]}) == ("tags",)


def test_unmanaged_keys_is_empty_for_an_empty_mapping() -> None:
    assert contract.unmanaged_keys({}) == ()


def test_unmanaged_keys_excludes_the_user_owned_effort_key() -> None:
    """Task 1.1's exact pin: a user-owned key is not unmanaged; a stray one is.

    Named mutation (task 1.1): reverting :func:`contract.unmanaged_keys` to
    subtract only :data:`MANAGED_KEYS` brings ``"effort"`` back into the
    result, i.e. ``("effort", "tags")``.
    """
    assert contract.unmanaged_keys({"effort": "race", "tags": ["a"]}) == ("tags",)


# --------------------------------------------------------------------------- #
# format_session_uuid (Req 1.1)
# --------------------------------------------------------------------------- #

# The shape the ingest layer produces for a recorded ``SESSION UUID``.
_UUID_BYTES: tuple[int, ...] = tuple(range(16))


def test_format_session_uuid_formats_the_recorded_sixteen_bytes() -> None:
    assert (
        contract.format_session_uuid(_UUID_BYTES)
        == "00010203-0405-0607-0809-0a0b0c0d0e0f"
    )


def test_format_session_uuid_yields_none_for_a_wrong_length() -> None:
    assert contract.format_session_uuid(tuple(range(15))) is None
    assert contract.format_session_uuid(tuple(range(17))) is None
    assert contract.format_session_uuid(()) is None


def test_format_session_uuid_yields_none_for_a_non_tuple() -> None:
    """Only the tuple shape ingest produces is accepted -- never coerced."""
    assert contract.format_session_uuid(list(range(16))) is None
    assert contract.format_session_uuid(bytes(range(16))) is None
    assert contract.format_session_uuid("00010203-0405-0607-0809-0a0b0c0d0e0f") is None
    assert contract.format_session_uuid(None) is None


def test_format_session_uuid_yields_none_for_a_malformed_element() -> None:
    assert contract.format_session_uuid(("a",) * 16) is None
    assert contract.format_session_uuid((None,) * 16) is None
    assert contract.format_session_uuid((0,) * 15 + (256,)) is None
    assert contract.format_session_uuid((0,) * 15 + (-1,)) is None


def test_format_session_uuid_has_no_sha_fallback() -> None:
    """5.6: the sha identity lives in ``sources``, never in ``uuid``."""
    assert contract.format_session_uuid(_SHA) is None


# --------------------------------------------------------------------------- #
# Purity: the contract is a leaf (design §DocumentContract, Allowed Dependencies)
# --------------------------------------------------------------------------- #


def test_contract_imports_nothing_from_the_layers_above_it() -> None:
    """Structural guard: every layer must be free to depend on the contract.

    Checked via the AST import nodes, not the source text, so the docstring may
    name ``render``/``sync``/``load`` to explain the boundary while the
    executable code imports none of them. ``docmerge`` is the one internal
    dependency the design allows (the marker-helper re-export).
    """
    tree = ast.parse(inspect.getsource(contract))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    internal = {name for name in imported if name.startswith("fitdocs")}
    assert internal == {"fitdocs.docmerge"}
    for banned in (
        "fitdocs.render",
        "fitdocs.sync",
        "fitdocs.load",
        "fitdocs.cli",
        "fitdocs.layout",
        "fitdocs.model",
    ):
        assert not any(
            name == banned or name.startswith(f"{banned}.") for name in imported
        ), f"contract imports {banned}"


def test_contract_performs_no_io_and_reads_no_clock() -> None:
    """Pure: no file I/O, no clock read, no randomness, no network (design).

    ``datetime`` is now imported for :func:`contract.document_date`'s ``date``
    return type (Amendment 3, cross-spec incursion): that accessor decodes a
    document's own *recorded* date, never the system clock. So the guard here
    narrows from "the module never imports ``datetime``" to "the module never
    references the clock-reading members of it" -- no ``.now``, ``.today``, or
    ``.utcnow`` attribute access anywhere in the module, called or not, which
    is what every clock read through ``datetime``/``date`` looks like at the
    access site regardless of which name the type is imported under. Matching
    the bare :class:`ast.Attribute` (not only when it is the ``func`` of an
    :class:`ast.Call`) also catches an aliased reference such as
    ``_CLOCK = date.today`` invoked elsewhere in the module -- a call whose
    ``func`` is a bare :class:`ast.Name`, not an :class:`ast.Attribute`, so a
    call-site-only check would miss it.
    """
    tree = ast.parse(inspect.getsource(contract))
    imported: set[str] = set()
    clock_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
        elif isinstance(node, ast.Attribute) and node.attr in (
            "now",
            "today",
            "utcnow",
        ):
            clock_calls.add(node.attr)
    for banned in ("pathlib", "os", "io", "time", "random", "urllib"):
        assert banned not in imported
    assert clock_calls == set()

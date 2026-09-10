"""Tests for :mod:`fitdocs.load.docedit` (task 3.2, Req 7.1, 7.2, 7.4-7.6).

The load doc editor performs safe surgery on an already-generated workout
document: it classifies the reserved ``load`` region (placeholder / computed /
unsupported / foreign / damaged), replaces *only* that region's inner content,
and upserts the three managed frontmatter keys by line-level edit -- never
re-serializing the workout-docs-emitted YAML. These tests pin the invariants
that make that surgery trustworthy:

* **Faithful classification** -- the imported placeholder constant is
  PLACEHOLDER, a recognized payload is COMPUTED/UNSUPPORTED, and anything else
  (user-owned text) is FOREIGN and therefore never overwritten silently (7.6).
* **Byte-exact region replacement** -- replacing the load content touches no
  other byte of the document (frontmatter, other regions, generated body);
  ``extract_regions(replace(...))["load"]`` round-trips the new content (7.1).
* **Non-destructive frontmatter upsert** -- the three managed keys are added
  inside the existing fence, read back correctly, idempotent, and cleanly
  strippable, with all other frontmatter and body bytes preserved (7.2, 7.4).
* **Damage is loud** -- damaged region markers surface as a propagating
  ``RegionError`` (a per-document conflict), never a silent misread (7.5).
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs import docmerge
from fitdocs.contract import LOAD_KEYS, LOAD_NOT_COMPUTED
from fitdocs.contract import parse_frontmatter as _contract_parse_frontmatter
from fitdocs.docmerge import (
    RegionError,
    extract_regions,
)
from fitdocs.load.docedit import (
    FRONTMATTER_LOAD_KEYS,
    LoadDocError,
    RegionClassification,
    RegionState,
    apply_frontmatter_load,
    classify_load_region,
    read_frontmatter_load,
    replace_load_region,
    strip_frontmatter_load,
)
from fitdocs.load.render import (
    LoadPayload,
    parse_payload,
    render_computed,
    render_unsupported,
)
from fitdocs.load.types import LoadResult, NonSelectedValue, QualityFlag
from tests.load.test_render import (
    _V1_UNSUPPORTED_LINE,
    _V1_WITHDRAWN_COMPUTED_LINE,
)

# --- fixtures ---------------------------------------------------------------


def _computed_result() -> LoadResult:
    """A stub interval-structured result exercising the full rendered shape."""
    return LoadResult(
        calculator_id="stub-methodology",
        display_name="Stub Methodology",
        value=2473.2,
        basis="HR channel, 88% of tested max",
        non_selected=(),
        flags=(),
        inputs_used=(("Tested max HR", "200 bpm"), ("Threshold", "42")),
        notes=("zone estimated from avg HR (basis: 88% of tested max)",),
    )


def _continuous_result() -> LoadResult:
    """A stub continuous-structured result exercising the full rendered shape."""
    return LoadResult(
        calculator_id="stub-methodology",
        display_name="Stub Methodology",
        value=1700.0,
        basis="HR channel",
        non_selected=(),
        flags=(),
        inputs_used=(("Tested max HR", "200 bpm"),),
        notes=(),
    )


# The frontmatter carries a couple of scalar keys and a multi-line ``sources``
# list -- exactly the kind of golden-guarded, workout-docs-emitted block whose
# bytes the upsert must never reflow.
_FRONTMATTER = (
    "---\n"
    "type: workout\n"
    "date: 2026-07-16\n"
    "distance_km: 10.0\n"
    "sources:\n"
    "  - fit-archive/abc123def456.fit\n"
    "---\n"
)

_BODY = "\n# Morning Run\n\nGenerated prose the tool owns and rewrites.\n\n"

_NOTES = docmerge.region_block("notes", "My private notes — keep me verbatim.")

_TRAILER = "\n_End of document._\n"


def _document(load_content: str) -> str:
    """A realistic fitdocs document with the ``load`` region mid-document.

    Placing the load region between the body and the notes region gives both a
    non-trivial prefix (frontmatter + body) and suffix (notes region + trailer),
    so byte-preservation assertions actually bite on both sides.
    """
    load = docmerge.region_block("load", load_content)
    return f"{_FRONTMATTER}{_BODY}{load}\n{_NOTES}{_TRAILER}"


def _body_after_frontmatter(markdown: str) -> str:
    """Everything after the closing ``---`` fence (frontmatter-independent)."""
    lines = markdown.split("\n")
    assert lines[0] == "---"
    close = next(i for i in range(1, len(lines)) if lines[i] == "---")
    return "\n".join(lines[close + 1 :])


# --- classification (Req 7.5, 7.6) ------------------------------------------


def test_classify_placeholder() -> None:
    """The imported not-computed constant classifies as PLACEHOLDER, no payload."""
    doc = _document(LOAD_NOT_COMPUTED)

    classification = classify_load_region(doc)
    state, payload = classification.state, classification.payload

    assert state is RegionState.PLACEHOLDER
    assert payload is None


def test_classify_computed_returns_matching_payload() -> None:
    """A rendered computed region classifies COMPUTED with the exact payload."""
    result = _computed_result()
    doc = _document(render_computed(result))

    classification = classify_load_region(doc)
    state, payload = classification.state, classification.payload

    assert state is RegionState.COMPUTED
    assert payload is not None
    assert payload.status == "computed"
    assert payload.result == result


def test_classify_unsupported_returns_payload() -> None:
    """A rendered unsupported region classifies UNSUPPORTED naming the sport."""
    doc = _document(render_unsupported("Ride"))

    classification = classify_load_region(doc)
    state, payload = classification.state, classification.payload

    assert state is RegionState.UNSUPPORTED
    assert payload is not None
    assert payload.status == "unsupported"
    assert payload.sport == "Ride"


def test_classify_current_format_invalid_body_stays_foreign() -> None:
    """A current-version marker whose body parse_payload rejects stays FOREIGN,
    not SUPERSEDED -- corrupted own-format content is never silently
    overwritten (7.6). ``never both populated`` for this case: neither payload
    nor stamp is populated even though the classifier consulted the stamp."""
    doc = _document('<!-- fitdocs-load:v2 {"not":"a valid payload"} -->')

    classification = classify_load_region(doc)

    assert classification.state is RegionState.FOREIGN
    assert classification.payload is None
    assert classification.stamp is None


def test_classify_superseded_computed_payload() -> None:
    """A non-current payload stamped 'computed' is SUPERSEDED -- a result this
    tool can no longer read, protected from automatic recomputation (11.2,
    11.3, 13.4). Uses the synthetic v1 withdrawn-calculator fixture."""
    doc = _document(_V1_WITHDRAWN_COMPUTED_LINE)

    classification = classify_load_region(doc)

    assert classification.state is RegionState.SUPERSEDED
    assert classification.payload is None
    assert classification.stamp is not None
    assert classification.stamp.version == 1
    assert classification.stamp.status == "computed"


def test_classify_non_current_unsupported_is_unsupported_not_superseded() -> None:
    """The 24-document branch: a non-current payload stamped 'unsupported'
    classifies UNSUPPORTED, not SUPERSEDED. It records no result -- only that
    nothing supported the sport when it was written -- so it rejoins the
    compute path and is re-rendered in the current format on the next pass
    (7.7). Uses the synthetic v1 unsupported fixture. Its payload is
    never populated: the old body is never decoded, only the stamp is kept."""
    doc = _document(_V1_UNSUPPORTED_LINE)

    classification = classify_load_region(doc)

    assert classification.state is RegionState.UNSUPPORTED
    assert classification.payload is None
    assert classification.stamp is not None
    assert classification.stamp.version == 1
    assert classification.stamp.status == "unsupported"


def test_classify_non_current_undeterminable_status_is_superseded() -> None:
    """A non-current payload whose status cannot be determined classifies
    SUPERSEDED -- the protective default (11.2)."""
    doc = _document('<!-- fitdocs-load:v1 {"not valid json at all -->')

    classification = classify_load_region(doc)

    assert classification.state is RegionState.SUPERSEDED
    assert classification.payload is None
    assert classification.stamp is not None
    assert classification.stamp.version == 1
    assert classification.stamp.status is None


def test_classify_never_both_payload_and_stamp_populated() -> None:
    """Across every classification case, payload and stamp are never both set
    -- a discriminating check on the actual object each case returns, not a
    structural property that would pass under sabotage that always leaves one
    field None (e.g. always returning stamp=None)."""
    cases: list[tuple[str, RegionState]] = [
        (LOAD_NOT_COMPUTED, RegionState.PLACEHOLDER),
        (render_computed(_computed_result()), RegionState.COMPUTED),
        (render_unsupported("Ride"), RegionState.UNSUPPORTED),
        ("hand-authored foreign text", RegionState.FOREIGN),
        (_V1_WITHDRAWN_COMPUTED_LINE, RegionState.SUPERSEDED),
        (_V1_UNSUPPORTED_LINE, RegionState.UNSUPPORTED),
        ('<!-- fitdocs-load:v1 {"not valid json at all -->', RegionState.SUPERSEDED),
    ]
    for content, expected_state in cases:
        classification = classify_load_region(_document(content))
        assert isinstance(classification, RegionClassification)
        assert classification.state is expected_state, content
        payload_set = classification.payload is not None
        stamp_set = classification.stamp is not None
        assert not (payload_set and stamp_set), content


def test_classify_foreign_content() -> None:
    """User-authored text that is neither placeholder nor payload is FOREIGN."""
    doc = _document("I hand-wrote my own load notes here.\n\nDo not clobber this.")

    classification = classify_load_region(doc)
    state, payload = classification.state, classification.payload

    assert state is RegionState.FOREIGN
    assert payload is None


def test_classify_foreign_is_not_the_placeholder() -> None:
    """Foreign content that merely resembles-but-differs from the placeholder."""
    doc = _document(LOAD_NOT_COMPUTED + " (edited)")

    classification = classify_load_region(doc)
    state, payload = classification.state, classification.payload

    assert state is RegionState.FOREIGN
    assert payload is None


def test_classify_damaged_markers_propagate_region_error() -> None:
    """A begin marker with no matching end surfaces as a RegionError (7.5)."""
    damaged = (
        f"{_FRONTMATTER}{_BODY}"
        "<!-- fitdocs:begin:load -->\n"
        "content with no closing marker\n"
    )

    with pytest.raises(RegionError):
        classify_load_region(damaged)


def test_classify_no_load_region_raises_load_doc_error() -> None:
    """A document lacking a load region is a structural docedit failure."""
    doc = f"{_FRONTMATTER}{_BODY}{_NOTES}{_TRAILER}"

    with pytest.raises(LoadDocError):
        classify_load_region(doc)


# --- region replacement (Req 7.1) -------------------------------------------


def test_replace_load_region_swaps_only_inner_content() -> None:
    """Replacement changes only the load inner bytes; everything else verbatim."""
    old = LOAD_NOT_COMPUTED
    new = render_computed(_computed_result())
    doc = _document(old)
    old_block = docmerge.region_block("load", old)
    prefix, _, suffix = doc.partition(old_block)

    result = replace_load_region(doc, new)

    # The document is byte-identical except the load region's inner content: the
    # prefix (frontmatter + body) and suffix (notes region + trailer) are exactly
    # the surrounding bytes, and the replaced region is the new content spliced in.
    assert result == prefix + docmerge.region_block("load", new) + suffix


def test_replace_load_region_round_trips_new_content() -> None:
    """extract_regions(replace(md, c))["load"] == c for multi-line content."""
    new = render_computed(_continuous_result())
    doc = _document(LOAD_NOT_COMPUTED)

    result = replace_load_region(doc, new)

    assert extract_regions(result)["load"] == new


def test_replace_load_region_preserves_other_regions_and_frontmatter() -> None:
    """The notes region and the frontmatter survive a load replacement."""
    doc = _document(LOAD_NOT_COMPUTED)
    before = extract_regions(doc)

    result = replace_load_region(doc, "replaced inner content")
    after = extract_regions(result)

    assert after["notes"] == before["notes"]
    assert after["load"] == "replaced inner content"
    assert read_frontmatter_load(result) == {}  # frontmatter still intact/managed-free


def test_replace_load_region_no_region_raises() -> None:
    """Replacing when there is no load region is a docedit failure."""
    doc = f"{_FRONTMATTER}{_BODY}{_NOTES}{_TRAILER}"

    with pytest.raises(LoadDocError):
        replace_load_region(doc, "whatever")


def test_replace_load_region_damaged_markers_propagate() -> None:
    """Damaged markers make replacement raise RegionError, not a silent edit."""
    damaged = (
        f"{_FRONTMATTER}{_BODY}<!-- fitdocs:begin:load -->\nno closing marker here\n"
    )

    with pytest.raises(RegionError):
        replace_load_region(damaged, "new")


# --- frontmatter upsert (Req 7.2, 7.4) --------------------------------------


def test_apply_frontmatter_load_adds_and_reads_back_keys() -> None:
    """load_value/methodology/basis are added and read back with correct types."""
    result = _computed_result()
    doc = _document(render_computed(result))

    applied = apply_frontmatter_load(doc, result)
    read = read_frontmatter_load(applied)

    # value is a NUMBER, methodology and basis are STRINGS -- queryable by tools.
    assert read == {
        "load_value": 2473.2,
        "load_methodology": "stub-methodology",
        "load_basis": "HR channel, 88% of tested max",
    }


def test_apply_frontmatter_load_value_drops_trailing_zero() -> None:
    """A whole-number result renders load_value as an int scalar (1700)."""
    result = _continuous_result()  # 1700.0
    doc = _document(render_computed(result))

    read = read_frontmatter_load(apply_frontmatter_load(doc, result))

    assert read["load_value"] == 1700
    assert isinstance(read["load_value"], int)


def test_apply_frontmatter_load_keys_live_inside_the_fence() -> None:
    """Managed keys are appended before the closing --- and the body is intact."""
    result = _computed_result()
    doc = _document(render_computed(result))

    applied = apply_frontmatter_load(doc, result)

    # read_frontmatter_load only parses the block *between* the fences, so keys
    # being read back proves they were inserted before the closing '---'. All
    # three managed keys are emitted today (task 2.4): load_basis is
    # unconditional, unlike the retired load_zone it replaces.
    assert set(read_frontmatter_load(applied)) == {
        "load_value",
        "load_methodology",
        "load_basis",
    }
    assert set(read_frontmatter_load(applied)) == set(FRONTMATTER_LOAD_KEYS)
    # The whole body (everything after the closing fence) is byte-identical.
    assert _body_after_frontmatter(applied) == _body_after_frontmatter(doc)


def test_apply_frontmatter_load_projects_no_diagnostics() -> None:
    """7.2's negative half: diagnostics never reach frontmatter.

    A result carrying ``non_selected`` entries and ``flags`` upserts a
    frontmatter block whose *complete* key set (read via the contract's own
    parser, not the filtered ``read_frontmatter_load``) is exactly the
    original document's keys plus the three managed load keys -- nothing
    projected from either diagnostic field.
    """
    result = dataclasses.replace(
        _computed_result(),
        non_selected=(
            NonSelectedValue(
                key="hr", label="HR channel", value=180.0, reason="not selected"
            ),
        ),
        flags=(
            QualityFlag(
                key="cadence-lock",
                label="Cadence lock",
                verdict="detected",
                detail="cadence pinned",
            ),
        ),
    )
    doc = _document(render_computed(result))
    original_keys = set(_contract_parse_frontmatter(doc) or {})

    applied = apply_frontmatter_load(doc, result)
    applied_keys = set(_contract_parse_frontmatter(applied) or {})

    assert applied_keys == original_keys | set(LOAD_KEYS)


def test_apply_frontmatter_load_preserves_all_other_bytes_via_strip() -> None:
    """apply-then-strip returns the exact original document (only keys added)."""
    result = _computed_result()
    doc = _document(render_computed(result))

    applied = apply_frontmatter_load(doc, result)

    assert applied != doc  # something was added
    assert strip_frontmatter_load(applied) == doc  # ...and only the managed keys


def test_apply_frontmatter_load_is_idempotent() -> None:
    """Applying the same result twice equals applying it once (7.4 restore)."""
    result = _computed_result()
    doc = _document(render_computed(result))

    once = apply_frontmatter_load(doc, result)
    twice = apply_frontmatter_load(once, result)

    assert twice == once


def test_apply_frontmatter_load_basis_is_always_emitted() -> None:
    """``load_basis`` is unconditional: ``result.basis`` is always present, so
    unlike the retired ``load_zone`` key, it is never conditionally omitted."""
    result = _continuous_result()
    doc = _document(render_computed(result))

    applied = apply_frontmatter_load(doc, result)
    read = read_frontmatter_load(applied)

    assert "load_zone" not in read
    assert "load_zone" not in applied
    assert read == {
        "load_value": 1700,
        "load_methodology": "stub-methodology",
        "load_basis": "HR channel",
    }


def test_apply_frontmatter_load_replaces_stale_keys() -> None:
    """Re-applying with a different result overwrites, never duplicates, keys.

    The input document also carries a pre-existing stale ``load_zone:`` line --
    the retired key this rename replaces -- which ``_is_managed_line`` must no
    longer recognize as managed (it was dropped from ``FRONTMATTER_LOAD_KEYS``
    in task 2.4), so a document carrying it from before the rename keeps that
    line as ordinary, unmanaged frontmatter."""
    doc = _document(render_computed(_computed_result())).replace(
        "distance_km: 10.0\n", "distance_km: 10.0\nload_zone: Z3\n"
    )
    assert "load_zone:" in doc

    first = apply_frontmatter_load(doc, _computed_result())
    assert "load_zone: Z3" in first  # no longer a managed key -- left alone

    second = apply_frontmatter_load(first, _continuous_result())

    read = read_frontmatter_load(second)
    assert read == {
        "load_value": 1700,
        "load_methodology": "stub-methodology",
        "load_basis": "HR channel",
    }
    # exactly one occurrence of each key -- no accumulation.
    assert second.count("load_value:") == 1
    assert "load_zone: Z3" in second  # still untouched, unmanaged


def test_apply_frontmatter_load_no_frontmatter_raises() -> None:
    """A document with no leading frontmatter fence is a docedit failure."""
    no_fm = _BODY + docmerge.region_block("load", LOAD_NOT_COMPUTED)

    with pytest.raises(LoadDocError):
        apply_frontmatter_load(no_fm, _computed_result())


# --- frontmatter read (drift detection, Req 7.4) ----------------------------


def test_read_frontmatter_load_empty_when_no_managed_keys() -> None:
    """A document without managed keys reads back an empty mapping."""
    doc = _document(LOAD_NOT_COMPUTED)

    assert read_frontmatter_load(doc) == {}


def test_read_frontmatter_load_empty_when_no_frontmatter() -> None:
    """Absence of a frontmatter block is not an error for the read path."""
    assert read_frontmatter_load("no frontmatter at all\n") == {}


def test_read_frontmatter_load_never_writes() -> None:
    """Reading is pure: the input document is unchanged (defensive check)."""
    doc = apply_frontmatter_load(_document(LOAD_NOT_COMPUTED), _computed_result())
    snapshot = doc

    read_frontmatter_load(doc)

    assert doc == snapshot


# --- frontmatter strip (recompute cleanup, Req 7.5/8.3) ---------------------


def test_strip_frontmatter_load_removes_only_managed_keys() -> None:
    """Strip after apply restores the original frontmatter and body exactly."""
    doc = _document(LOAD_NOT_COMPUTED)
    applied = apply_frontmatter_load(doc, _computed_result())

    stripped = strip_frontmatter_load(applied)

    assert stripped == doc
    assert read_frontmatter_load(stripped) == {}


def test_strip_frontmatter_load_no_managed_keys_is_noop() -> None:
    """Stripping a document with no managed keys returns it unchanged."""
    doc = _document(LOAD_NOT_COMPUTED)

    assert strip_frontmatter_load(doc) == doc


def test_strip_frontmatter_load_is_idempotent() -> None:
    """Stripping twice equals stripping once."""
    applied = apply_frontmatter_load(_document(LOAD_NOT_COMPUTED), _computed_result())

    once = strip_frontmatter_load(applied)
    twice = strip_frontmatter_load(once)

    assert twice == once


# --- classification x parse_payload seam ------------------------------------


def test_classify_uses_parse_payload_contract() -> None:
    """Classification agrees with render.parse_payload on the same content."""
    content = render_computed(_computed_result())
    doc = _document(content)

    payload = classify_load_region(doc).payload
    direct = parse_payload(content)

    assert isinstance(direct, LoadPayload)
    assert payload == direct


# --- Req 11.2's behavioral invariant -----------------------------------------
#
# classify_load_region is now the first real caller of inspect_payload /
# PayloadStamp (training-load task 2.3). Req 11.2's full guarantee -- that
# stamp output never reaches apply_frontmatter_load in a running pass -- is a
# call-site (engine) property, not something this module's unit tests can
# establish on their own; it is proven end-to-end in
# tests/load/test_engine.py's SUPERSEDED byte-identity tests (task 2.3
# remediation) and is otherwise carried forward as an open obligation for
# task 4.1. The two tests below are narrower and say so: one is a static-
# typing note, the other a structural change detector. Neither exercises
# classify_load_region's actual call behavior, so neither can catch a
# classifier that itself starts calling apply_frontmatter_load.


def test_stamp_cannot_be_fed_to_apply_frontmatter_load_silently() -> None:
    """Static-typing note, not a behavioral proof: PayloadStamp and LoadResult
    do not share a ``value`` attribute, so passing a stamp to the real
    apply_frontmatter_load raises AttributeError immediately rather than
    silently producing frontmatter. This is a structural accident of the two
    types' current field sets, not evidence that classify_load_region never
    calls apply_frontmatter_load -- it does not exercise the classifier's call
    behavior at all. It reddens if and only if _managed_lines is changed to
    read `.calculator_id` only (the one field the two types share) instead of
    `.value`; mypy already rejects the call statically (see the
    ``# type: ignore[arg-type]`` below), so this is a runtime backstop for
    that same fact, not an independent behavioral guarantee."""
    doc = _document(_V1_WITHDRAWN_COMPUTED_LINE)
    classification = classify_load_region(doc)
    assert classification.state is RegionState.SUPERSEDED
    stamp = classification.stamp
    assert stamp is not None
    assert classification.payload is None  # no LoadResult was ever built

    with pytest.raises(AttributeError, match="value"):
        apply_frontmatter_load(doc, stamp)  # type: ignore[arg-type]


def test_stamp_cannot_construct_a_load_result() -> None:
    """Structural field-disjointness check, not a behavioral proof: PayloadStamp
    is missing every field a LoadResult requires (value, basis, non_selected,
    flags, inputs_used, notes, display_name), so no code path can construct a
    LoadResult from a stamp's fields alone. This does not show that no code
    path *does* construct a LoadResult from a stamp by other means (e.g. from
    literal/default values) and feed it to apply_frontmatter_load -- tasks.md
    identifies this as insufficient on its own for that reason. The
    behavioral obligation is carried forward to task 4.1."""
    stamp = classify_load_region(_document(_V1_WITHDRAWN_COMPUTED_LINE)).stamp
    assert stamp is not None

    result_fields = {f.name for f in dataclasses.fields(LoadResult)}
    stamp_fields = {f.name for f in dataclasses.fields(stamp)}
    assert result_fields - stamp_fields == {
        "value",
        "basis",
        "non_selected",
        "flags",
        "inputs_used",
        "notes",
        "display_name",
    }


# --- task 2.4: LoadPassPreservation -- user-owned lines through the load
# editor's three primitives (Req 4.3) ----------------------------------------
#
# The editor never parses or re-serializes YAML (module docstring); a
# user-owned (effort-tag) frontmatter line is simply an "other" line that
# `_is_managed_line` does not claim, so it survives whatever the upsert, the
# strip, and the region replacement each do. These tests build a frontmatter
# block carrying the four effort-tag user lines -- `effort`,
# `effort_distance_m`, `effort_time_s`, and a block-scalar `effort_event`
# spanning two indented continuation lines -- interleaved with stale managed
# load keys, and prove each primitive leaves every user line byte-identical
# and in the same relative order, with the fresh load keys landing after them.

_USER_LINE_EFFORT = "effort: race"
_USER_LINE_DISTANCE = "effort_distance_m: 42195"
# Trailing whitespace, deliberately: a byte-identity assertion that only
# checks a line's stripped/semantic value would not notice it silently
# dropped -- proven against a `line.rstrip()` mutation applied to `kept` in
# both `apply_frontmatter_load` and `strip_frontmatter_load`.
_USER_LINE_TIME = "effort_time_s: 10800  "
_USER_LINE_EVENT_KEY = "effort_event: >-"
_USER_LINE_EVENT_CONT_1 = "  Boston"
_USER_LINE_EVENT_CONT_2 = "  Marathon"

# The four user-owned lines in their fixture-authored relative order -- the
# block scalar's key line stands for the whole entry; its continuation lines
# are checked separately (immediately following, byte-identical).
_USER_KEY_LINES_IN_ORDER = (
    _USER_LINE_EFFORT,
    _USER_LINE_DISTANCE,
    _USER_LINE_TIME,
    _USER_LINE_EVENT_KEY,
)

_STALE_LOAD_LINE_VALUE = "load_value: 999"
_STALE_LOAD_LINE_METHODOLOGY = 'load_methodology: "old-methodology"'
_STALE_LOAD_LINE_BASIS = 'load_basis: "old basis"'


def _document_with_user_lines_and_stale_load_keys() -> str:
    """A realistic document whose frontmatter interleaves the four user-owned
    effort-tag lines (one a block scalar) with stale managed load keys left
    over from a prior pass, on top of the same body/region/notes shape the
    rest of this module uses."""
    frontmatter = (
        "\n".join(
            [
                "---",
                "type: workout",
                "date: 2026-07-16",
                _USER_LINE_EFFORT,
                _STALE_LOAD_LINE_VALUE,
                "distance_km: 10.0",
                _USER_LINE_DISTANCE,
                _STALE_LOAD_LINE_METHODOLOGY,
                _USER_LINE_TIME,
                _STALE_LOAD_LINE_BASIS,
                _USER_LINE_EVENT_KEY,
                _USER_LINE_EVENT_CONT_1,
                _USER_LINE_EVENT_CONT_2,
                "sources:",
                "  - fit-archive/abc123def456.fit",
                "---",
            ]
        )
        + "\n"
    )
    load = docmerge.region_block("load", LOAD_NOT_COMPUTED)
    return f"{frontmatter}{_BODY}{load}\n{_NOTES}{_TRAILER}"


def _assert_user_lines_preserved_and_ordered(markdown: str) -> None:
    """Every user-owned line is present verbatim, in the fixture's relative
    order, with the block scalar's continuation lines immediately following
    its key line, byte-identical."""
    lines = markdown.split("\n")
    indices = [lines.index(line) for line in _USER_KEY_LINES_IN_ORDER]
    assert indices == sorted(indices), f"user lines out of relative order: {indices}"
    event_key_idx = indices[-1]
    assert lines[event_key_idx + 1] == _USER_LINE_EVENT_CONT_1
    assert lines[event_key_idx + 2] == _USER_LINE_EVENT_CONT_2


def _fresh_load_key_indices(markdown: str) -> list[int]:
    """Indices of the (post-upsert) fresh managed load key lines."""
    lines = markdown.split("\n")
    prefixes = ("load_value:", "load_methodology:", "load_basis:")
    return [i for i, line in enumerate(lines) if line.startswith(prefixes)]


def _frontmatter_prefix(markdown: str) -> str:
    """Everything up to and including the closing ``---`` fence."""
    suffix = _body_after_frontmatter(markdown)
    assert markdown.endswith(suffix)
    return markdown[: len(markdown) - len(suffix)]


def test_load_key_upsert_preserves_user_lines_and_orders_fresh_keys_after() -> None:
    """apply_frontmatter_load (the upsert) keeps every user-owned line
    byte-identical and in the same relative order, and lands the fresh
    managed keys after them -- a placement claim, not mere presence (Req 4.3).
    """
    doc = _document_with_user_lines_and_stale_load_keys()

    applied = apply_frontmatter_load(doc, _computed_result())

    _assert_user_lines_preserved_and_ordered(applied)
    # exactly one fresh occurrence of each managed key -- the stale ones were
    # removed, not merely appended alongside.
    fresh_indices = _fresh_load_key_indices(applied)
    assert len(fresh_indices) == 3
    lines = applied.split("\n")
    event_cont2_idx = lines.index(_USER_LINE_EVENT_CONT_2)
    assert min(fresh_indices) > event_cont2_idx
    assert _body_after_frontmatter(applied) == _body_after_frontmatter(doc)


def test_load_key_strip_preserves_user_lines_and_removes_only_stale_keys() -> None:
    """strip_frontmatter_load keeps every user-owned line byte-identical and
    in the same relative order while removing the stale managed lines (Req
    4.3)."""
    doc = _document_with_user_lines_and_stale_load_keys()

    stripped = strip_frontmatter_load(doc)

    _assert_user_lines_preserved_and_ordered(stripped)
    assert _STALE_LOAD_LINE_VALUE not in stripped
    assert _STALE_LOAD_LINE_METHODOLOGY not in stripped
    assert _STALE_LOAD_LINE_BASIS not in stripped
    assert _body_after_frontmatter(stripped) == _body_after_frontmatter(doc)


def test_region_replacement_preserves_user_lines_after_an_upsert() -> None:
    """replace_load_region never inspects the frontmatter at all, so the four
    user-owned lines already upserted alongside fresh managed keys survive a
    region swap byte-identically, in the same relative order (Req 4.3).

    Built on the *upserted* document (rather than a bare fresh fixture) so
    that a defect in the upsert's own line-classification is not masked by
    testing region replacement in isolation: if the upsert corrupted the user
    lines before this test ever calls ``replace_load_region``, this
    assertion sees the corruption too.
    """
    doc = _document_with_user_lines_and_stale_load_keys()
    upserted = apply_frontmatter_load(doc, _computed_result())

    replaced = replace_load_region(upserted, render_computed(_continuous_result()))

    assert _frontmatter_prefix(replaced) == _frontmatter_prefix(upserted)
    _assert_user_lines_preserved_and_ordered(replaced)

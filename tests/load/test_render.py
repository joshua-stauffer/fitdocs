"""Tests for :mod:`fitdocs.load.render` (task 2.1, Req 1.2, 1.8-1.11, 7.1, 7.3,
9.2, 11.1).

The load-section renderer produces the content of a document's reserved
training-load region: a deterministic block of human-readable markdown plus a
single machine-readable v2 payload comment that lets the tool recognize and
recover its own previously computed results -- now carrying the redefined
multi-channel result vocabulary: the selected value, its basis, any values
computed but not selected (with the reason each was not), and any quality
flags raised about the data behind the result. These tests pin:

* **Byte-determinism** -- the same ``LoadResult`` renders identically every
  time (no timestamps, no randomness), so regeneration is a no-op diff.
* **Lossless payload round-trip** -- parsing a rendered region reconstructs the
  exact ``LoadResult``, because the payload is the durable record from which
  markdown and frontmatter are derived (7.3, 11.1).
* **Conditional diagnostic blocks** -- the non-selected and flags blocks are
  omitted entirely when empty (no heading, no table, no placeholder row), and
  rendered visibly subordinate to the headline value when present (1.10, 1.11).
* **Honest absence** -- a non-selected entry with no computed number renders
  with no number, never a fabricated ``0`` (1.11, 9.1).
* **Number-free unsupported content** -- the honest "no methodology supports
  this sport" state names the sport and contains no digits (7.7).
* **Tolerant, versioned parsing** -- absent, malformed, or unknown-version
  payloads parse as *unrecognized* (``None``) so foreign content is never
  silently misread or overwritten; a v2 payload missing ``non_selected``/
  ``flags`` decodes those as empty tuples (11.1).
"""

from __future__ import annotations

import json
import re

import pytest

from fitdocs import contract
from fitdocs.load.render import (
    LOAD_PAYLOAD_VERSION,
    LoadPayload,
    PayloadStamp,
    encode_payload,
    inspect_payload,
    parse_payload,
    render_computed,
    render_unsupported,
)
from fitdocs.load.types import LoadResult, NonSelectedValue, QualityFlag

# --- fixtures ---------------------------------------------------------------


def _full_result() -> LoadResult:
    """A result exercising the full rendered shape: non-selected values
    (including a ``value is None`` entry) and all three flag verdicts."""
    return LoadResult(
        calculator_id="stub-threshold",
        display_name="Stub Threshold Methodology",
        value=2473.2,
        basis="HR channel, 88% of tested max",
        non_selected=(
            NonSelectedValue(
                key="pace", label="Pace channel", value=2100.0, reason="lower priority"
            ),
            NonSelectedValue(
                key="power",
                label="Power channel",
                value=None,
                reason="no power meter recorded",
            ),
        ),
        flags=(
            QualityFlag(
                key="cadence-lock",
                label="Cadence lock",
                verdict="detected",
                detail="cadence variance below threshold for 12 minutes",
            ),
            QualityFlag(
                key="gps-drift",
                label="GPS drift",
                verdict="not-detected",
                detail="distance matches recorded track within tolerance",
            ),
            QualityFlag(
                key="hr-strap-contact",
                label="HR strap contact",
                verdict="not-assessed",
                detail="no contact-quality field in this device's records",
            ),
        ),
        inputs_used=(("Tested max HR", "200 bpm"), ("Threshold", "42")),
        notes=("estimated from avg HR (basis: 88% of tested max)",),
    )


def _continuous_result() -> LoadResult:
    """A stub continuous result with inputs and no diagnostics."""
    return LoadResult(
        calculator_id="stub-continuous",
        display_name="Stub Continuous Methodology",
        value=1700.0,
        basis="HR channel",
        non_selected=(),
        flags=(),
        inputs_used=(("Tested max HR", "200 bpm"),),
        notes=(),
    )


def _single_value_result() -> LoadResult:
    """The single-value case (Req 1.11): no alternatives, no flags, no inputs,
    no notes -- nothing fabricated for any of them."""
    return LoadResult(
        calculator_id="stub",
        display_name="Stub Methodology",
        value=42.0,
        basis="HR channel",
        non_selected=(),
        flags=(),
        inputs_used=(),
        notes=(),
    )


def _human_lines(region: str) -> str:
    """The region with its HTML-comment payload line(s) removed."""
    return "\n".join(
        line for line in region.splitlines() if not line.strip().startswith("<!--")
    )


# --- version constant -------------------------------------------------------


def test_payload_version_paired_with_doc_version() -> None:
    """Req 11.5: when the result format changes, the CLI shall change the
    document-format version. Pinning the two constants as a single tuple
    means a sibling spec that bumps one without the other reddens here,
    with a message that names the constant they forgot.

    **Maintainer ruling (fit-ingest task 13.2, escalated by that task and
    resolved there): the pair became ``(2, 4)`` -- ``DOC_VERSION`` alone
    advances.** fit-ingest's Amendment 1 changed a metric *value* (normalized
    power's rolling-window conformance), not the load result's own format --
    ``LoadPayload``/``LoadResult`` are byte-identical before and after -- so
    Req 11.5 never fires for this change; Req 18.1 (a changed reported value
    advances the document-format version) is what fires, and it is
    one-directional: it says nothing about ``LOAD_PAYLOAD_VERSION``. Bumping
    ``LOAD_PAYLOAD_VERSION`` here would also have been actively harmful:
    ``parse_payload`` (this module, see the version check a few lines above)
    treats an unrecognized payload version as foreign content and refuses to
    read it, so bumping the constant would orphan every existing document's
    already-computed load payload for no format change at all. Filed as
    ``.kiro/queue/2026-07-30-version-pair-tripwire-asserts-a-biconditional.md``:
    this assertion's "(and vice versa)" wording still states a biconditional
    Req 11.5 does not -- left as-is here since fixing that reading is that
    spec's call, not this task's.

    **The pair became ``(2, 5)`` (chore/power-absent-sample-fill,
    2026-07-30): the same reasoning applies a second time.** The absent-
    power-sample forward-fill ruling
    (``.kiro/queue/2026-07-30-absent-power-sample-filled-with-zero.md``) is
    again a metric *value* change (normalized power's fill rule for a
    device dropout), not a load-result format change, so ``DOC_VERSION``
    advances alone once more and ``LOAD_PAYLOAD_VERSION`` stays untouched
    for the same orphaning reason stated above.
    """
    assert (LOAD_PAYLOAD_VERSION, contract.DOC_VERSION) == (2, 5), (
        f"LOAD_PAYLOAD_VERSION={LOAD_PAYLOAD_VERSION} and "
        f"contract.DOC_VERSION={contract.DOC_VERSION} drifted apart. "
        "Req 11.5 requires that a result-format change also change the "
        "document-format version: if you bumped LOAD_PAYLOAD_VERSION, you "
        "must also bump contract.DOC_VERSION (and vice versa), then update "
        "the expected pair in this assertion."
    )


# --- round-trip (7.3, 11.1) --------------------------------------------------


@pytest.mark.parametrize(
    "result",
    [_full_result(), _continuous_result(), _single_value_result()],
)
def test_computed_round_trip(result: LoadResult) -> None:
    parsed = parse_payload(render_computed(result))
    assert parsed is not None
    assert parsed.status == "computed"
    assert parsed.sport is None
    assert parsed.result == result


def test_unsupported_round_trip() -> None:
    parsed = parse_payload(render_unsupported("Ride"))
    assert parsed == LoadPayload("unsupported", None, "Ride")


def test_encode_parse_round_trip_direct() -> None:
    payload = LoadPayload("computed", _full_result(), None)
    parsed = parse_payload(encode_payload(payload))
    assert parsed == payload


def test_full_result_round_trip_re_encodes_byte_identically() -> None:
    """The task's own observable: a full result -- non-selected entries
    including a ``value is None`` one, and every flag verdict -- round-trips
    through encode/parse to an *equal* value, and re-encoding is byte-
    identical, not merely field-equal."""
    result = _full_result()
    first_line = encode_payload(LoadPayload("computed", result, None))

    parsed = parse_payload(first_line)
    assert parsed is not None
    assert parsed.result == result

    re_encoded = encode_payload(LoadPayload("computed", parsed.result, None))
    assert re_encoded == first_line  # byte-identical, not just field-equal


# --- None is never a zero (Req 1.11, 9.1) ------------------------------------


def test_non_selected_none_value_survives_round_trip_as_none() -> None:
    result = _full_result()
    power_entry = next(e for e in result.non_selected if e.key == "power")
    assert power_entry.value is None

    parsed = parse_payload(render_computed(result))
    assert parsed is not None
    assert parsed.result is not None
    round_tripped = next(e for e in parsed.result.non_selected if e.key == "power")
    assert round_tripped.value is None
    assert round_tripped.value != 0
    assert round_tripped.value != 0.0


def test_non_selected_none_value_renders_no_number() -> None:
    """A ``value is None`` entry renders its label and reason with no number --
    absent data is never a fabricated ``0`` (1.11)."""
    result = _full_result()
    human = _human_lines(render_computed(result))
    # The power entry's line carries no digits anywhere on it.
    power_line = next(line for line in human.splitlines() if "Power channel" in line)
    assert not any(ch.isdigit() for ch in power_line)
    assert "no power meter recorded" in power_line


def test_non_selected_json_null_is_never_coerced_to_zero() -> None:
    """Direct payload-JSON assertion: the encoded ``value`` for a ``None``
    non-selected entry is the JSON literal ``null``, never ``0``."""
    line = encode_payload(LoadPayload("computed", _full_result(), None))
    match = re.match(r"^<!-- fitdocs-load:v2 (.+) -->$", line)
    assert match is not None
    data = json.loads(match.group(1))
    power_entries = [e for e in data["non_selected"] if e["key"] == "power"]
    assert len(power_entries) == 1
    assert power_entries[0]["value"] is None


# --- determinism --------------------------------------------------------------


def test_render_computed_is_byte_deterministic() -> None:
    result = _full_result()
    assert render_computed(result) == render_computed(result)


def test_render_unsupported_is_byte_deterministic() -> None:
    assert render_unsupported("Ride") == render_unsupported("Ride")


def test_payload_json_is_compact_and_sorted() -> None:
    line = render_computed(_full_result()).splitlines()[0]
    match = re.match(r"^<!-- fitdocs-load:v2 (.+) -->$", line)
    assert match is not None
    json_text = match.group(1)
    data = json.loads(json_text)
    # Compact separators + sorted keys => identical bytes for identical results.
    assert json_text == json.dumps(
        data, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )


def test_payload_arrays_preserve_producer_order() -> None:
    """Array-valued fields are never sorted at the value level (11.1)."""
    line = render_computed(_full_result()).splitlines()[0]
    match = re.match(r"^<!-- fitdocs-load:v2 (.+) -->$", line)
    assert match is not None
    data = json.loads(match.group(1))
    assert [e["key"] for e in data["non_selected"]] == ["pace", "power"]
    assert [f["key"] for f in data["flags"]] == [
        "cadence-lock",
        "gps-drift",
        "hr-strap-contact",
    ]


# --- value formatting (one decimal, trailing .0 dropped) --------------------


def test_value_formatting_drops_trailing_zero() -> None:
    human = _human_lines(render_computed(_continuous_result()))
    assert "**1700** — Stub Continuous Methodology" in human
    assert "1700.0" not in human


def test_value_formatting_keeps_one_decimal() -> None:
    human = _human_lines(render_computed(_full_result()))
    assert "2473.2" in human


# --- payload is the first line ----------------------------------------------


def test_computed_payload_is_first_line() -> None:
    region = render_computed(_full_result())
    first = region.splitlines()[0]
    assert first == encode_payload(LoadPayload("computed", _full_result(), None))
    assert first.startswith("<!-- fitdocs-load:v2 ")
    assert first.endswith(" -->")


def test_unsupported_payload_is_first_line() -> None:
    region = render_unsupported("Ride")
    first = region.splitlines()[0]
    assert first == encode_payload(LoadPayload("unsupported", None, "Ride"))


# --- human content presence -------------------------------------------------


def test_computed_human_content_carries_the_elements() -> None:
    human = _human_lines(render_computed(_full_result()))
    assert "Stub Threshold Methodology" in human  # methodology name
    assert "HR channel, 88% of tested max" in human  # basis
    assert "| Input | Value |" in human  # inputs table header
    assert "Tested max HR" in human and "200 bpm" in human  # inputs table rows
    assert "Threshold" in human and "42" in human
    assert "estimated from avg HR (basis: 88% of tested max)" in human  # note


# --- conditional diagnostic blocks (Req 1.10, 1.11, 7.1) --------------------


def test_single_value_case_renders_neither_diagnostic_block() -> None:
    """The task's own observable: the single-value case renders no diagnostic
    block -- no headings, no empty tables, no placeholder rows."""
    human = _human_lines(render_computed(_single_value_result()))
    assert "Not selected" not in human
    assert "Quality flags" not in human
    assert "| Input | Value |" not in human  # empty inputs table also omitted
    assert "| --- |" not in human  # no headingless table of any shape either


def test_result_with_diagnostics_renders_both_blocks() -> None:
    human = _human_lines(render_computed(_full_result()))
    assert "**Not selected:**" in human
    assert "**Quality flags:**" in human
    assert "Pace channel" in human
    assert "Cadence lock" in human
    assert "detected" in human
    assert "not-detected" in human
    assert "not-assessed" in human


def test_diagnostic_blocks_render_after_the_headline_value() -> None:
    """Diagnostics are visibly subordinate to the headline value (1.10): the
    headline appears before either diagnostic block's heading."""
    human = _human_lines(render_computed(_full_result()))
    headline_index = human.index("Stub Threshold Methodology")
    not_selected_index = human.index("**Not selected:**")
    flags_index = human.index("**Quality flags:**")
    assert headline_index < not_selected_index
    assert headline_index < flags_index


# --- unsupported: names the sport, contains no numbers (7.7) ---------------


def test_unsupported_names_the_sport() -> None:
    human = _human_lines(render_unsupported("Ride"))
    assert "Ride" in human


def test_unsupported_human_content_is_number_free() -> None:
    human = _human_lines(render_unsupported("Ride"))
    assert human.strip()  # there IS a human line
    assert not any(ch.isdigit() for ch in human)


# --- tolerant, versioned parsing -> None on anything unrecognized -----------


def test_parse_returns_none_when_no_payload_line() -> None:
    assert parse_payload("no payload here") is None
    assert parse_payload("") is None


def test_parse_returns_none_on_malformed_json() -> None:
    assert parse_payload("<!-- fitdocs-load:v2 {bad json -->") is None


def test_parse_returns_none_on_unknown_version() -> None:
    assert parse_payload('<!-- fitdocs-load:v1 {"v":1,"status":"computed"} -->') is None
    assert parse_payload('<!-- fitdocs-load:v3 {"v":3,"status":"computed"} -->') is None


def test_parse_returns_none_on_missing_required_field() -> None:
    # Valid v2 marker + JSON, but no status field.
    assert parse_payload('<!-- fitdocs-load:v2 {"v":2} -->') is None
    # computed status but missing calculator_id, value, basis, and the rest.
    assert parse_payload('<!-- fitdocs-load:v2 {"v":2,"status":"computed"} -->') is None


def test_parse_tolerates_unknown_extra_fields() -> None:
    line = encode_payload(LoadPayload("unsupported", None, "Ride"))
    # Splice an unknown field into the JSON; it must still parse.
    tampered = line.replace('"sport":"Ride"', '"sport":"Ride","future_field":123')
    assert tampered != line
    assert parse_payload(tampered) == LoadPayload("unsupported", None, "Ride")


def test_parse_finds_payload_within_a_larger_region() -> None:
    result = _full_result()
    region = (
        "## Training Load\n\n"
        + render_computed(result)
        + "\n\nsome trailing user prose\n"
    )
    parsed = parse_payload(region)
    assert parsed is not None
    assert parsed.result == result


# --- forward tolerance: absent non_selected/flags decode as empty (11.1) ----


def test_absent_non_selected_and_flags_decode_as_empty_tuples() -> None:
    """A v2 payload with ``non_selected``/``flags`` absent decodes those as
    empty tuples -- a later additive field must not invalidate the format."""
    body = {
        "v": 2,
        "status": "computed",
        "calculator_id": "stub",
        "display_name": "Stub",
        "value": 10.0,
        "basis": "a basis",
        "inputs_used": [],
        "notes": [],
    }
    line = f"<!-- fitdocs-load:v2 {json.dumps(body, separators=(',', ':'))} -->"
    parsed = parse_payload(line)
    assert parsed is not None
    assert parsed.result is not None
    assert parsed.result.non_selected == ()
    assert parsed.result.flags == ()


def test_missing_required_field_still_yields_none_even_with_diagnostics_absent() -> (
    None
):
    """Forward tolerance applies only to the diagnostic collections: a v2
    payload missing a genuinely required field (``basis``) still decodes as
    ``None`` -- all-or-nothing for required fields (11.1)."""
    body = {
        "v": 2,
        "status": "computed",
        "calculator_id": "stub",
        "display_name": "Stub",
        "value": 10.0,
        # "basis" deliberately omitted
        "inputs_used": [],
        "notes": [],
    }
    line = f"<!-- fitdocs-load:v2 {json.dumps(body, separators=(',', ':'))} -->"
    assert parse_payload(line) is None


def _complete_v2_body() -> dict[str, object]:
    """An otherwise-complete v2 ``computed`` body carrying all six required
    fields, for the per-field strictness tests below."""
    return {
        "v": 2,
        "status": "computed",
        "calculator_id": "stub",
        "display_name": "Stub",
        "value": 10.0,
        "basis": "a basis",
        "inputs_used": [],
        "notes": [],
    }


def _encode_body(body: dict[str, object]) -> str:
    return f"<!-- fitdocs-load:v2 {json.dumps(body, separators=(',', ':'))} -->"


@pytest.mark.parametrize(
    "field",
    ["calculator_id", "display_name", "value", "basis", "inputs_used", "notes"],
)
def test_each_required_field_absent_individually_yields_none(field: str) -> None:
    """Decoding is all-or-nothing per required field (design.md 1305, 11.1): an
    otherwise-complete payload missing exactly one required field -- proven for
    each of the six fields individually, not generalised from one -- decodes as
    ``None``. Catches, e.g., a field silently defaulting to a fabricated ``0.0``
    or ``""`` instead of invalidating the whole decode (Req 9.1, 10.6)."""
    body = _complete_v2_body()
    del body[field]
    assert parse_payload(_encode_body(body)) is None


def test_value_wrong_type_yields_none() -> None:
    """A ``value`` field holding a string, not a number, invalidates the
    decode -- it must never be silently coerced (Req 9.1)."""
    body = _complete_v2_body()
    body["value"] = "not-a-number"
    assert parse_payload(_encode_body(body)) is None


def test_inputs_used_wrong_type_yields_none() -> None:
    """A non-list ``inputs_used`` invalidates the decode.

    Uses a JSON object with two-character keys rather than a bare string: a
    string is caught incidentally by the downstream pair-unpacking (each
    single-char pair[1] lookup raises ``IndexError``), which would mask a
    missing ``isinstance`` check. A dict of two-char keys iterates as pairs
    that unpack *without* error, so this only fails if the type is actually
    checked."""
    body = _complete_v2_body()
    body["inputs_used"] = {"ab": "unused", "cd": "unused"}
    assert parse_payload(_encode_body(body)) is None


def test_notes_wrong_type_yields_none() -> None:
    """A non-list ``notes`` invalidates the decode."""
    body = _complete_v2_body()
    body["notes"] = "not-a-list"
    assert parse_payload(_encode_body(body)) is None


def test_malformed_present_non_selected_fails_the_whole_decode() -> None:
    """A *present* but malformed ``non_selected`` array is not silently
    ignored -- it invalidates the decode, distinct from an absent array."""
    body = {
        "v": 2,
        "status": "computed",
        "calculator_id": "stub",
        "display_name": "Stub",
        "value": 10.0,
        "basis": "a basis",
        "non_selected": "not-a-list",
        "flags": [],
        "inputs_used": [],
        "notes": [],
    }
    line = f"<!-- fitdocs-load:v2 {json.dumps(body, separators=(',', ':'))} -->"
    assert parse_payload(line) is None


def test_flag_with_unknown_verdict_fails_the_decode() -> None:
    """An unrecognized flag verdict is rejected, not silently coerced."""
    body = {
        "v": 2,
        "status": "computed",
        "calculator_id": "stub",
        "display_name": "Stub",
        "value": 10.0,
        "basis": "a basis",
        "non_selected": [],
        "flags": [
            {
                "key": "k",
                "label": "l",
                "verdict": "totally-unknown-verdict",
                "detail": "d",
            }
        ],
        "inputs_used": [],
        "notes": [],
    }
    line = f"<!-- fitdocs-load:v2 {json.dumps(body, separators=(',', ':'))} -->"
    assert parse_payload(line) is None


# --- payload stamp inspection (task 2.2, Req 7.7, 11.1, 11.2, 13.4) ---------
#
# `inspect_payload` learns what it can from a payload marker without decoding
# a result. It is the read path task 2.3's classifier will use to distinguish
# a superseded *result* worth protecting (Req 11.2, 11.3, 13.4) from a
# superseded record of nothing having been computed (Req 7.7). `status` is
# the one field that may ever reach routing; `calculator_id` may only ever
# reach a human-readable message.
#
# Retained v1 (pre-format-bump) payload bodies, shaped to match the byte
# layout the v1 encoder used just before the commit that withdrew the
# methodology (task 1.3), specifically that commit's parent's pre-withdrawal
# state. The values below are the test data itself -- nothing here is fetched
# from git history at test/import time, so no historical commit needs to
# resolve for this module to run:
#
# * The v1 encoder's field set and byte shape carried
#   `{v, status, calculator_id, display_name, points, zone, zone_label,
#   structure, inputs_used, notes}` for a computed payload and
#   `{v, status: "unsupported", sport}` for an unsupported one.
#
# SYNTHETIC FROM THIS COMMIT FORWARD (encumbered-content-purge Req 11.11):
# this body is no longer a transcription of the withdrawn calculator's real
# identity or real output. Every value below other than `v` and `status` --
# `calculator_id`, `display_name`, `points`, `zone`, `zone_label`,
# `structure`, `inputs_used`, `notes` -- is invented. None of them is
# transcribed from any real record.
#
# These are retained as test data only, to prove `parse_payload` refuses a
# recorded prior-format result and `inspect_payload` names its methodology,
# and to prove the routing distinction between it and a recorded prior-format
# unsupported state is made by stamped *status*, never by calculator name.

_V1_WITHDRAWN_COMPUTED_BODY: dict[str, object] = {
    "v": 1,
    "status": "computed",
    "calculator_id": "withdrawn-v1",
    "display_name": "Withdrawn V1 Calculator",
    "points": 1614.7,
    "zone": 4,
    "zone_label": "Zone 4 (Tempo)",
    "structure": "5 × 12:00 in Zone 4",
    "inputs_used": [["Fixture max HR", "171 bpm"], ["Fixture threshold", "19"]],
    "notes": ["fixture note: values invented, not sourced from any real record"],
}

_V1_UNSUPPORTED_BODY: dict[str, object] = {
    "v": 1,
    "status": "unsupported",
    "sport": "Ride",
}


def _v1_line(body: dict[str, object]) -> str:
    """Encode ``body`` as a v1 payload comment line, mirroring the shape of
    the real (now-deleted) v1 :func:`encode_payload`."""
    json_text = json.dumps(
        body, separators=(",", ":"), sort_keys=True, ensure_ascii=False
    )
    return f"<!-- fitdocs-load:v1 {json_text} -->"


_V1_WITHDRAWN_COMPUTED_LINE = _v1_line(_V1_WITHDRAWN_COMPUTED_BODY)
_V1_UNSUPPORTED_LINE = _v1_line(_V1_UNSUPPORTED_BODY)


def test_retained_v1_withdrawn_payload_is_refused_by_parse_payload() -> None:
    """`parse_payload` still refuses a non-current-version payload (11.2):
    a recorded v1 result from the withdrawn calculator parses as
    unrecognized, never partially."""
    assert parse_payload(_V1_WITHDRAWN_COMPUTED_LINE) is None


def test_retained_v1_unsupported_payload_is_also_refused_by_parse_payload() -> None:
    assert parse_payload(_V1_UNSUPPORTED_LINE) is None


def test_adding_inspect_payload_does_not_loosen_parse_payload() -> None:
    """Calling `inspect_payload` first must not have any side effect that
    changes `parse_payload`'s refusal of a retained v1 payload."""
    inspect_payload(_V1_WITHDRAWN_COMPUTED_LINE)
    assert parse_payload(_V1_WITHDRAWN_COMPUTED_LINE) is None


def test_inspect_reports_version_status_and_methodology_for_well_formed_v1() -> None:
    """The task's own observable, half one: a well-formed prior-format
    payload's version, status and methodology are all reported."""
    stamp = inspect_payload(_V1_WITHDRAWN_COMPUTED_LINE)
    assert stamp == PayloadStamp(
        version=1, status="computed", calculator_id="withdrawn-v1"
    )


def test_inspect_reports_version_alone_for_a_corrupted_body() -> None:
    """The task's own observable, half two: a corrupted body yields the
    version alone, with both other fields absent."""
    stamp = inspect_payload("<!-- fitdocs-load:v1 {not valid json at all -->")
    assert stamp == PayloadStamp(version=1, status=None, calculator_id=None)


def test_inspect_returns_none_when_no_payload_line_exists() -> None:
    assert inspect_payload("no payload marker here at all") is None
    assert inspect_payload("") is None


def test_inspect_status_decodes_but_calculator_id_does_not() -> None:
    """Independence of the best-effort fields: a body whose `status` decodes
    but whose `calculator_id` is wrongly typed resolves `status` on its own,
    without requiring `calculator_id` to also succeed."""
    body = {"v": 1, "status": "computed", "calculator_id": 12345}
    line = _v1_line(body)
    stamp = inspect_payload(line)
    assert stamp == PayloadStamp(version=1, status="computed", calculator_id=None)


def test_inspect_calculator_id_decodes_but_status_does_not() -> None:
    """Independence of the best-effort fields, the reverse case: a body whose
    `calculator_id` decodes but whose `status` is an unrecognized string
    resolves `calculator_id` on its own, without `status` also succeeding."""
    body = {"v": 1, "status": "not-a-real-status", "calculator_id": "withdrawn-v1"}
    line = _v1_line(body)
    stamp = inspect_payload(line)
    assert stamp == PayloadStamp(version=1, status=None, calculator_id="withdrawn-v1")


def test_inspect_version_present_when_body_is_not_even_a_mapping() -> None:
    """The version reports whenever a payload comment line exists at all --
    even when the JSON body decodes but is not a mapping."""
    line = "<!-- fitdocs-load:v1 [1,2,3] -->"
    assert inspect_payload(line) == PayloadStamp(
        version=1, status=None, calculator_id=None
    )


def test_routing_distinguishes_v1_computed_from_v1_unsupported_by_status() -> None:
    """The routing distinction (Req 7.7 vs 11.2/11.3/13.4) is made by
    *stamped status*, never by calculator name. Both retained v1 bodies
    carry no recognizable calculator identity signal in the unsupported
    case (it has no `calculator_id` field at all), so a router keyed on
    `status` correctly separates a result worth protecting from a record of
    nothing having been computed -- while a router keyed on calculator name
    could not, because the unsupported payload never names one."""
    computed_stamp = inspect_payload(_V1_WITHDRAWN_COMPUTED_LINE)
    unsupported_stamp = inspect_payload(_V1_UNSUPPORTED_LINE)
    assert computed_stamp is not None
    assert unsupported_stamp is not None

    # The two exact values ARE the separation the router keys on; an explicit
    # `computed_stamp.status != unsupported_stamp.status` line used to follow and
    # was removed once this module entered mypy's scope, which reported it as a
    # non-overlapping comparison: after the two assertions above, both operands
    # are narrowed to distinct literals, so it could not have failed under any
    # implementation. Asserting each value is strictly stronger than asserting
    # they differ.
    assert computed_stamp.status == "computed"
    assert unsupported_stamp.status == "unsupported"
    assert unsupported_stamp.calculator_id is None


def test_stamp_is_not_convertible_into_a_load_result() -> None:
    """A structural change detector, not a behavioral proof: pins that
    `PayloadStamp`'s field set stays disjoint from `LoadResult`'s
    data-bearing fields (no value, basis, display name, non_selected or
    flags), so a later change that adds one of those fields to
    `PayloadStamp` breaks this test. Requirement 11.2's *behavioral*
    invariant -- that a stamp never feeds `restore` or a frontmatter
    projection -- has no callers to exercise at task 2.2 (`inspect_payload`/
    `PayloadStamp` are referenced only within this module); that half is the
    obligation of tasks 2.3 and 4.1, once callers exist."""
    import dataclasses

    stamp = inspect_payload(_V1_WITHDRAWN_COMPUTED_LINE)
    assert stamp is not None
    stamp_fields = {f.name for f in dataclasses.fields(stamp)}
    assert stamp_fields == {"version", "status", "calculator_id"}
    # PayloadStamp carries none of the fields that determine a load *value*
    # -- value, display_name, basis, non_selected, flags, inputs_used, notes
    # -- so no code path can build a LoadResult from a PayloadStamp alone.
    # `calculator_id` is present on both dataclasses by name, but that alone
    # cannot construct a result: LoadResult still requires the six other
    # fields PayloadStamp never carries.
    result_data_fields = {f.name for f in dataclasses.fields(LoadResult)} - {
        "calculator_id"
    }
    assert not (stamp_fields & result_data_fields)


def test_inspect_reports_the_markers_version_even_when_the_body_disagrees() -> None:
    """The marker's version digit is the version of record (design.md 920),
    never the body's own `v` field, so a stray/incorrect `v` inside the JSON
    body cannot masquerade as a different marker version. Verified to kill
    the mutant that prefers the body's `v` (falling back to the marker's
    only when the body's is absent/malformed): with that mutation applied,
    this test asserts `version=1` but observes `version=2`, and reddens."""
    line = '<!-- fitdocs-load:v1 {"v":2,"status":"computed","calculator_id":"x"} -->'
    assert inspect_payload(line) == PayloadStamp(
        version=1, status="computed", calculator_id="x"
    )


def test_inspect_reports_a_current_format_computed_payload() -> None:
    """`inspect_payload` correctly reports the *current* (v2) format's own
    encoder output for a computed result -- the exact input task 2.3's
    classifier will hand it on every region. Round-trips through the real
    `encode_payload`, not a hand-built fixture."""
    line = encode_payload(LoadPayload("computed", _continuous_result(), None))
    assert inspect_payload(line) == PayloadStamp(
        version=LOAD_PAYLOAD_VERSION,
        status="computed",
        calculator_id="stub-continuous",
    )


def test_inspect_reports_a_current_format_unsupported_payload() -> None:
    """The current-format unsupported case: `status` resolves and
    `calculator_id` correctly stays `None` -- an unsupported payload never
    names a methodology."""
    line = encode_payload(LoadPayload("unsupported", None, "swimming"))
    assert inspect_payload(line) == PayloadStamp(
        version=LOAD_PAYLOAD_VERSION, status="unsupported", calculator_id=None
    )

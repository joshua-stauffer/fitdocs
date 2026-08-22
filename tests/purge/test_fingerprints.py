"""`scripts/purge/fingerprints.py`: the one-shot generator for `ContentOracle`
(task 2.4, Req 3.2, 3.7).

Every fixture here is synthetic -- invented digit sequences with no relation
to any removed material -- because the generator's *mechanism* (salt
generation, windowing/digesting a corpus, rendering the sibling data module,
running an evasion probe and recording pass/fail) is what this file pins.
The one-shot run against the real files happens exactly once, outside the
test suite (task 2.4's status report records its result); no test here reads
the withdrawn writeup or either withdrawn CSV by path, so this suite stays
meaningful after task 3.1 deletes them.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import typer
from scripts.purge.fingerprints import (
    EvasionResult,
    as_python_literal,
    collect_fingerprints,
    generate_and_verify,
    generate_salt,
    reformatted_copy,
    render_data_module,
    run,
    run_probe,
    write_data_module,
    write_results,
)
from typer.testing import CliRunner

from tests._content_oracle import ENTROPY_FLOOR_BITS, scan

runner = CliRunner()

# A synthetic "table" with enough digit density to clear the 96-bit floor
# across a handful of tokens, standing in for a real withdrawn table without
# reproducing one.
_SYNTHETIC_CORPUS = (
    "Zone factors: 118.42837, 204.99123, 337.55019, 441.20876, 552.68231\n"
    "Pace ranges: 07:14 to 07:29, 09:02 to 09:18, 11:47 to 12:03\n"
)

_CONTROL_TEXT = (
    "Invented workout: easy run, 5.2 km in 32:10 at 145 bpm average heart "
    "rate, elevation gain 210 m. None of this is drawn from any real table."
)


# --- generate_salt() --------------------------------------------------------


def test_generate_salt_returns_the_requested_length() -> None:
    assert len(generate_salt(32)) == 32


def test_generate_salt_is_random_across_calls() -> None:
    # Positive control against a stub that returns a fixed value: two calls
    # must not collide.
    assert generate_salt(32) != generate_salt(32)


# --- collect_fingerprints() --------------------------------------------------


def test_collect_fingerprints_is_nonempty_for_a_realistic_corpus() -> None:
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    assert fps, "a corpus dense enough to clear the floor must yield digests"
    assert lengths, "a corpus dense enough to clear the floor must yield window lengths"


def test_collect_fingerprints_over_no_texts_is_empty() -> None:
    # Positive control for the walk: an empty source list must not vacuously
    # produce fingerprints.
    fps, lengths = collect_fingerprints([], salt=b"fixed-salt")

    assert fps == frozenset()
    assert lengths == frozenset()


def test_collect_fingerprints_over_low_entropy_text_is_empty() -> None:
    # Five one-digit tokens (~16.6 bits total) never clear the 96-bit floor --
    # mirrors windows()'s own "tail dropped" behaviour, exercised through the
    # collector rather than windows() directly.
    fps, lengths = collect_fingerprints(["1 2 3 4 5"], salt=b"fixed-salt")

    assert fps == frozenset()
    assert lengths == frozenset()


def test_collect_fingerprints_lets_a_stored_digest_be_found_by_scan() -> None:
    # The digest set this produces must actually be consumable by the shared
    # oracle's scan() -- not merely be non-empty.
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    assert scan(_SYNTHETIC_CORPUS, fps, lengths, b"fixed-salt") is True


def test_collect_fingerprints_does_not_flag_unrelated_text() -> None:
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    assert scan(_CONTROL_TEXT, fps, lengths, b"fixed-salt") is False


def test_collect_fingerprints_digests_the_full_window_not_just_its_offset() -> None:
    # The correct formula is digest(toks[offset:offset + length], salt). A
    # mutant that computes digest(toks[offset:length], salt) instead produces
    # an identical (and therefore still-passing) digest for the very first
    # window (offset 0, where the two slices coincide) but a wrong digest for
    # every window after it. _SYNTHETIC_CORPUS yields exactly two windows, so
    # this exercises the second, non-zero-offset one. The text scanned below
    # omits the first window's own tokens entirely and is prefixed with
    # unrelated high-entropy padding, so a match can only be found via the
    # second window's digest at a non-zero offset -- not via the first
    # window's own, bug-immune digest supplying a vacuous pass. (Verified by
    # execution against exactly that mutant -- see DISCRIMINATION in the
    # status report.)
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    assert len(fps) == 2, "this corpus yields exactly two windows -- one digest each"

    padding = "913.44827, 205.99981, 811.30274, 442.87105\n"
    second_window_text = "552.68231, 07:14 to 07:29, 09:02 to 09:18, 11:47 to 12:03\n"
    scanned_text = padding + second_window_text

    assert scan(scanned_text, fps, lengths, b"fixed-salt") is True


def test_collect_fingerprints_does_not_window_across_a_text_boundary() -> None:
    # Each text has 3 three-digit tokens (~9.96 bits each, ~29.9 bits total)
    # -- individually well short of floor=50.0 -- but 6 tokens combined
    # (~59.8 bits) would clear it. A mutant that concatenates every text's
    # tokens before windowing (rather than windowing each text on its own)
    # would emit a window here; the correct, per-text behaviour must not.
    # (Verified by execution against exactly that mutant -- see
    # DISCRIMINATION in the status report.)
    fps, lengths = collect_fingerprints(
        ["111 222 333", "444 555 666"], salt=b"fixed-salt", floor=50.0
    )

    assert fps == frozenset()
    assert lengths == frozenset()


def test_collect_fingerprints_does_window_when_the_same_tokens_share_one_text() -> None:
    # The positive half of the boundary test above: the same six tokens
    # (~59.8 bits combined), when they share ONE text instead of being split
    # across two, do clear floor=50.0 and must yield exactly one digest of
    # length 6. Without this, the emptiness asserted above would hold both
    # under correct per-text windowing and under a `collect_fingerprints`
    # that ignores its `floor` parameter and windows against some other
    # floor entirely -- this makes that mutant discriminable.
    fps, lengths = collect_fingerprints(
        ["111 222 333 444 555 666"], salt=b"fixed-salt", floor=50.0
    )

    assert lengths == frozenset({6})
    assert len(fps) == 1


# --- render_data_module() / write_data_module() -----------------------------


def test_render_data_module_records_every_declared_field() -> None:
    rendered = render_data_module(
        salt=b"\x01\x02",
        entropy_floor_bits=96.0,
        digest_hex_length=32,
        fingerprints=frozenset({"abc123"}),
        window_lengths=frozenset({3, 7}),
        source_count=1,
        generated_at="2026-08-01T00:00:00+00:00",
    )

    assert "0102" in rendered  # the salt, hex-encoded
    assert "96.0" in rendered
    assert "32" in rendered
    assert '"abc123"' in rendered
    assert "SOURCE_COUNT" in rendered
    assert "FINGERPRINTS" in rendered
    assert "WINDOW_LENGTHS" in rendered
    assert "GENERATED_AT" in rendered
    assert "2026-08-01T00:00:00+00:00" in rendered

    # Anchored on the rendered WINDOW_LENGTHS block itself, not on "3"/"7"
    # appearing anywhere in the output -- the digest fixture "abc123" already
    # contains a "3", which would let this pass even if window lengths were
    # dropped from the render entirely.
    window_lengths_block = rendered.split("WINDOW_LENGTHS")[1].split("FINGERPRINTS")[0]
    assert "3" in window_lengths_block
    assert "7" in window_lengths_block


def test_render_data_module_output_is_importable_python(tmp_path: Path) -> None:
    # The strongest form of "well-formed": write it out and import it as a
    # real module, then use its contents through scan() -- a stray quote or
    # a bad frozenset literal would fail this, not merely a string-contains
    # assertion.
    salt = b"\x9a\xbc"
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=salt)
    rendered = render_data_module(
        salt=salt,
        entropy_floor_bits=ENTROPY_FLOOR_BITS,
        digest_hex_length=32,
        fingerprints=fps,
        window_lengths=lengths,
        source_count=1,
        generated_at="2026-08-01T00:00:00+00:00",
    )
    out_path = tmp_path / "_generated.py"
    write_data_module(out_path, rendered)

    import importlib.util

    spec = importlib.util.spec_from_file_location("_generated_fixture", out_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert salt == module.SALT
    assert fps == module.FINGERPRINTS
    assert lengths == module.WINDOW_LENGTHS
    assert module.SOURCE_COUNT == 1
    assert (
        scan(_SYNTHETIC_CORPUS, module.FINGERPRINTS, module.WINDOW_LENGTHS, module.SALT)
        is True
    )
    assert (
        scan(_CONTROL_TEXT, module.FINGERPRINTS, module.WINDOW_LENGTHS, module.SALT)
        is False
    )


def test_render_data_module_output_carries_no_source_path_field(
    tmp_path: Path,
) -> None:
    # Req 3.7: the rendered module must carry no path-bearing field -- only
    # an opaque count of how many sources were measured.
    rendered = render_data_module(
        salt=b"\x01\x02",
        entropy_floor_bits=96.0,
        digest_hex_length=32,
        fingerprints=frozenset({"abc123"}),
        window_lengths=frozenset({3, 7}),
        source_count=3,
        generated_at="2026-08-01T00:00:00+00:00",
    )

    assert "SOURCE_PATHS" not in rendered
    assert "SOURCE_COUNT: int = 3" in rendered


# --- reformatted_copy() / as_python_literal() -------------------------------


def test_reformatted_copy_changes_the_surrounding_formatting() -> None:
    reformatted = reformatted_copy(_SYNTHETIC_CORPUS)

    assert reformatted != _SYNTHETIC_CORPUS


def test_reformatted_copy_preserves_every_digit_run_in_order() -> None:
    # The transformation must not touch numeric content or reorder it -- only
    # the surrounding punctuation/structure -- or a stored digest could never
    # match the reformatted text again.
    from tests._content_oracle import tokens

    assert tokens(reformatted_copy(_SYNTHETIC_CORPUS)) == tokens(_SYNTHETIC_CORPUS)


def test_reformatted_copy_still_matches_the_original_fingerprints() -> None:
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")
    reformatted = reformatted_copy(_SYNTHETIC_CORPUS)

    assert scan(reformatted, fps, lengths, b"fixed-salt") is True


def test_reformatted_copy_preserves_a_thousands_grouped_integer() -> None:
    # `_THOUSANDS_COMMA` protects a comma that groups thousands (e.g.
    # "12,345") from the field-delimiter reformatting below it, so that
    # digit run is not fragmented into two smaller tokens. No source this
    # generator has actually been run against contains one (task 2.4's own
    # status report), so this fixture is invented rather than drawn from
    # what is actually there -- it pins the defensive branch directly.
    from tests._content_oracle import tokens

    text = "Total distance: 12,345 km over the season.\n"

    assert tokens(reformatted_copy(text)) == tokens(text)


def test_as_python_literal_wraps_every_line_as_a_quoted_string() -> None:
    literal = as_python_literal(_SYNTHETIC_CORPUS, constant_name="_PASTED")

    assert "_PASTED" in literal
    assert literal.count('"') >= 2 or literal.count("'") >= 2


def test_as_python_literal_still_matches_the_original_fingerprints() -> None:
    # This is evasion 3 from the withdrawal-evasions queue item, at unit
    # scale: a table pasted verbatim as Python string literals into an
    # allowlisted module must still digest-match, because tokens() only
    # looks at digit runs and ignores surrounding quotes/commas/parens.
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")
    literal = as_python_literal(_SYNTHETIC_CORPUS)

    assert scan(literal, fps, lengths, b"fixed-salt") is True


# --- run_probe() / EvasionResult --------------------------------------------


def test_run_probe_records_a_pass_when_a_positive_detection_is_found() -> None:
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    result = run_probe(
        "verbatim re-add",
        _SYNTHETIC_CORPUS,
        expected_detected=True,
        fps=fps,
        lengths=lengths,
        salt=b"fixed-salt",
    )

    assert result == EvasionResult(
        name="verbatim re-add", expected_detected=True, detected=True
    )
    assert result.passed is True


def test_run_probe_records_a_pass_when_absence_is_expected_and_found() -> None:
    # The single-constant-paste probe: a lone low-entropy value is NOT
    # expected to be caught (the declared limit, Req 3.7) -- "passed" here
    # means the probe correctly demonstrates non-detection, not that
    # something was found.
    fps, lengths = collect_fingerprints([_SYNTHETIC_CORPUS], salt=b"fixed-salt")

    result = run_probe(
        "single-constant paste",
        "an isolated value: 118",
        expected_detected=False,
        fps=fps,
        lengths=lengths,
        salt=b"fixed-salt",
    )

    assert result.detected is False
    assert result.passed is True


def test_run_probe_records_a_failure_when_expectation_and_reality_disagree() -> None:
    # Negative control on `passed` itself: an unrelated fingerprint set/salt
    # means the "positive" probe finds nothing, so `passed` must read False.
    result = run_probe(
        "mismatched expectation",
        _SYNTHETIC_CORPUS,
        expected_detected=True,
        fps=frozenset({"deadbeef"}),
        lengths=frozenset({3}),
        salt=b"unrelated-salt",
    )

    assert result.detected is False
    assert result.passed is False


# --- write_results() ---------------------------------------------------------


def test_write_results_records_every_probe_pass_fail_and_no_probe_text(
    tmp_path: Path,
) -> None:
    results = (
        EvasionResult(name="source-1 flagged", expected_detected=True, detected=True),
        EvasionResult(
            name="control not flagged", expected_detected=False, detected=False
        ),
        # A disagreeing probe -- expected and actual detection differ -- so
        # this test's own name (asserting every probe's pass/fail is
        # recorded) actually exercises a `passed=False` case rather than
        # only ever-passing ones.
        EvasionResult(
            name="mismatched expectation", expected_detected=True, detected=False
        ),
    )
    out_path = tmp_path / "evasion-acceptance.json"

    write_results(
        results,
        out_path,
        source_count=1,
        fingerprint_count=12,
        window_length_count=3,
    )

    payload = json.loads(out_path.read_text())
    assert payload["probes"] == [
        {
            "name": "source-1 flagged",
            "expected_detected": True,
            "detected": True,
            "passed": True,
        },
        {
            "name": "control not flagged",
            "expected_detected": False,
            "detected": False,
            "passed": True,
        },
        {
            "name": "mismatched expectation",
            "expected_detected": True,
            "detected": False,
            "passed": False,
        },
    ]
    assert payload["fingerprint_count"] == 12
    assert payload["window_length_count"] == 3
    assert payload["source_count"] == 1
    # The record is pass/fail and shape only -- never a value: `write_results`
    # never receives a text argument at all (only names, counts and
    # booleans), which the payload keys below (and
    # test_evasion_result_holds_no_text_field below) are what actually pins.
    assert set(payload.keys()) == {
        "generated_at",
        "source_count",
        "fingerprint_count",
        "window_length_count",
        "probes",
    }
    for probe in payload["probes"]:
        assert set(probe.keys()) == {
            "name",
            "expected_detected",
            "detected",
            "passed",
        }


def test_write_results_with_no_probes_is_a_visible_shape_not_a_silent_pass(
    tmp_path: Path,
) -> None:
    # Positive control for the walk: an empty probe list must not be hidden
    # inside a payload that otherwise looks complete.
    out_path = tmp_path / "evasion-acceptance.json"

    write_results(
        (), out_path, source_count=0, fingerprint_count=0, window_length_count=0
    )

    payload = json.loads(out_path.read_text())
    assert payload["probes"] == []


def test_evasion_result_holds_no_text_field() -> None:
    # Pins the no-raw-text property directly on the dataclass: adding a
    # `text` field (even a defaulted one) to `EvasionResult` must be
    # detected here, since nothing else in this suite inspects its field set.
    import dataclasses

    assert {field.name for field in dataclasses.fields(EvasionResult)} == {
        "name",
        "expected_detected",
        "detected",
    }


# --- generate_and_verify() ----------------------------------------------------


def _write_synthetic_sources(tmp_path: Path) -> tuple[Path, ...]:
    first = tmp_path / "writeup.md"
    second = tmp_path / "table-one.csv"
    first.write_text(_SYNTHETIC_CORPUS)
    second.write_text(
        "804.11239,913.66502,027.94810,158.33267,466.72015\n"
        "run pace,12:41 to 12:58,14:03 to 14:22\n"
    )
    return (first, second)


def test_generate_and_verify_writes_a_nonvacuous_data_module_and_results(
    tmp_path: Path,
) -> None:
    real_sources = _write_synthetic_sources(tmp_path)
    # A third source with no digit or clock token at all: `tokens()` returns
    # an empty list for it, so it contributes no window to the combined
    # fingerprint set and can never itself be found by `scan` (there is no
    # offset to try). Its own "source-N flagged" probe therefore records
    # `expected_detected=True` / `detected=False` -- a genuine, deterministic
    # failure among otherwise-passing probes. Needed so the read-back
    # assertion below can actually distinguish "the record matches the run"
    # from "the record was silently filtered to passing probes only": with
    # every probe passing, a filter that drops failures is invisible.
    # Placed between the two real sources (never last): `generate_and_verify`
    # indexes `texts[0]` and `texts[-1]` by position for two of the
    # catalogued-evasion probes, and both must stay real sources with digit
    # content for those probes to pass.
    no_digit_source = tmp_path / "no-digits.md"
    no_digit_source.write_text(
        "An aside with no numeric or clock tokens at all: none, whatsoever.\n"
    )
    sources = (real_sources[0], no_digit_source, real_sources[1])
    data_module_out = tmp_path / "_content_fingerprints.py"
    results_out = tmp_path / "scratch" / "evasion-acceptance.json"

    fps, lengths, results = generate_and_verify(
        sources, data_module_out=data_module_out, results_out=results_out
    )

    assert fps, "the generated fingerprint set must not be empty"
    assert lengths, "the generated window-length set must not be empty"
    assert results, "the acceptance run must record at least one probe"
    assert data_module_out.exists()
    assert results_out.exists()

    # Every probe must match its own expectation, EXCEPT the deliberately
    # unfindable third source above -- a mismatch anywhere else means the
    # generator's own probes disagree with the oracle they exercise.
    failing_name = "source-2 flagged"
    for result in results:
        if result.name == failing_name:
            assert not result.passed, (
                f"{failing_name} was expected to fail by fixture construction"
            )
            continue
        assert result.passed, (
            f"{result.name}: expected {result.expected_detected}, got {result.detected}"
        )

    names = {result.name for result in results}
    assert "control file not flagged" in names
    assert "verbatim re-add" in names
    assert "renamed and reformatted re-add" in names
    assert "table pasted as a language literal into an allowlisted module" in names
    assert "copy under a different extension" in names

    # The task's own primary observable: each source passed in gets its own
    # per-source flagged probe, and every one of them expects detection.
    # Probe names are opaque, index-based labels -- never a source's
    # filename (Req 3.7) -- so this asserts on position, not on the sources'
    # own names.
    by_name = {result.name: result for result in results}
    for index in range(1, len(sources) + 1):
        flagged_name = f"source-{index} flagged"
        assert flagged_name in by_name, (
            f"no per-source flagged probe recorded for index {index}"
        )
        assert by_name[flagged_name].expected_detected is True

    # The above only asserts the acceptance run's own probes agree with
    # themselves -- it never reads back the module `generate_and_verify`
    # actually wrote to disk, so a mutation that renders a stale salt or a
    # truncated fingerprint set into `data_module_out` while the in-memory
    # `fps`/`lengths` (and every probe above) stay correct would ship a dead
    # module at exit 0. Import the written module directly, the same way
    # `test_render_data_module_output_is_importable_python` already does,
    # and assert it actually matches what the probes were run against.
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_generate_and_verify_written_module", data_module_out
    )
    assert spec is not None and spec.loader is not None
    written_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(written_module)

    assert fps == written_module.FINGERPRINTS
    assert lengths == written_module.WINDOW_LENGTHS

    for source in real_sources:
        assert (
            scan(
                source.read_text(encoding="utf-8"),
                written_module.FINGERPRINTS,
                written_module.WINDOW_LENGTHS,
                written_module.SALT,
            )
            is True
        ), f"the written module must still detect {source.name}"

    assert (
        scan(
            _CONTROL_TEXT,
            written_module.FINGERPRINTS,
            written_module.WINDOW_LENGTHS,
            written_module.SALT,
        )
        is False
    )

    # The above only reads back the generated data module -- it never reads
    # back the durable evasion-acceptance record `write_results` writes, so a
    # mutation at that call site (dropping every result, filtering out the
    # failing ones, or zeroing a recorded count) can leave every assertion
    # above green while the record itself is fabricated. Compare it against
    # the run that actually produced it: order and pass/fail lines must
    # match exactly, not just the count (a filter that drops only the
    # deliberately-failing probe above changes the count by exactly one, so
    # a bare length check would still catch that one case, but a filter on
    # some other predicate need not -- comparing the full ordered tuple list
    # is what pins both).
    payload = json.loads(results_out.read_text())
    recorded = [
        (probe["name"], probe["expected_detected"], probe["detected"], probe["passed"])
        for probe in payload["probes"]
    ]
    produced = [
        (result.name, result.expected_detected, result.detected, result.passed)
        for result in results
    ]
    assert recorded == produced
    assert payload["fingerprint_count"] == len(fps)
    assert payload["window_length_count"] == len(lengths)
    assert payload["source_count"] == len(sources)


def test_generate_and_verify_raises_rather_than_write_a_vacuous_module(
    tmp_path: Path,
) -> None:
    low_entropy = tmp_path / "low-entropy.md"
    low_entropy.write_text("1 2 3 4 5\n")
    data_module_out = tmp_path / "_content_fingerprints.py"
    results_out = tmp_path / "scratch" / "evasion-acceptance.json"

    import pytest

    with pytest.raises(ValueError, match="empty"):
        generate_and_verify(
            (low_entropy,), data_module_out=data_module_out, results_out=results_out
        )

    assert not data_module_out.exists(), (
        "a vacuous fingerprint set must never reach a written data module"
    )


def test_generate_and_verify_raises_for_zero_sources(tmp_path: Path) -> None:
    # The empty-`sources` path is a degenerate case of the same vacuous-set
    # guard above, but is never exercised by it (an empty `texts` list is a
    # distinct control-flow path from "one low-entropy text") -- pin it
    # directly, alongside the no-module-written guarantee.
    data_module_out = tmp_path / "_content_fingerprints.py"
    results_out = tmp_path / "scratch" / "evasion-acceptance.json"

    with pytest.raises(ValueError, match="empty"):
        generate_and_verify(
            (), data_module_out=data_module_out, results_out=results_out
        )

    assert not data_module_out.exists(), (
        "a zero-source run must never reach a written data module"
    )
    assert not results_out.exists(), (
        "a zero-source run must never reach a written results record"
    )


# NOTE (encumbered-content-purge, 4.1, elective boundary exception): a
# `_single_known_positive_control_value()` helper and a conditional
# "single-constant paste" probe branch in `generate_and_verify` used to be
# exercised by two tests here (`test_single_known_positive_control_value_is_
# available_by_default` and `test_generate_and_verify_emits_the_single_
# constant_probe_when_available`, plus a third,
# `..._is_none_when_the_constant_is_absent`, that monkeypatched a stub
# module to simulate absence). Task 4.1 deleted the value-tuple constant
# that helper read, from `tests/load/test_packaging.py`, rather than
# renaming it, which made the helper permanently return `None` and the
# conditional branch it fed permanently unreachable. Both the helper and
# the branch are deleted from `scripts/purge/fingerprints.py` as of this
# task rather than left as dead code (see that module's own NOTE at the
# same site), so all three tests are deleted here rather than repointed at
# a mechanism that no longer exists. This deletion is outside task 4.1's
# declared boundary (`ReintroductionGuards`, `IdentityErasure`) -- this
# module belongs to `ContentOracle` (task 2.4) -- but is forced by the same
# upstream deletion: reverting `scripts/purge/fingerprints.py` alone (the
# non-elective fix) would restore a `mypy attr-defined` error against an
# attribute that no longer exists, since that module is in
# `[tool.mypy].files`.


# --- CLI: run() ----------------------------------------------------------------


def _build_app() -> typer.Typer:
    app = typer.Typer(no_args_is_help=True, add_completion=False)
    app.command("fingerprints")(run)
    return app


def test_cli_run_writes_output_and_exits_zero_on_a_realistic_synthetic_corpus(
    tmp_path: Path,
) -> None:
    sources = _write_synthetic_sources(tmp_path)
    data_module_out = tmp_path / "_content_fingerprints.py"
    results_out = tmp_path / "scratch" / "evasion-acceptance.json"

    args: list[str] = []
    for source in sources:
        args += ["--source", str(source)]
    args += [
        "--data-module-out",
        str(data_module_out),
        "--results-out",
        str(results_out),
    ]

    result = runner.invoke(_build_app(), args)

    assert result.exit_code == 0, result.output
    assert data_module_out.exists()
    assert results_out.exists()
    assert "PASS" in result.output


def test_cli_run_exits_nonzero_when_a_source_file_is_missing(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.md"
    result = runner.invoke(
        _build_app(),
        [
            "--source",
            str(missing),
            "--results-out",
            str(tmp_path / "out.json"),
        ],
    )

    assert result.exit_code == 1
    assert "not found" in result.output


def test_cli_run_exits_nonzero_when_a_probe_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Drives a real probe to disagree with its own expectation (rather than
    # a missing-source short-circuit) -- the "do not proceed to the
    # irreversible deletion" signal this task's one-shot tool depends on.
    # Forcing `scan` to always report "not found" makes every
    # `expected_detected=True` probe (every per-source flagged probe, every
    # catalogued evasion) fail, without touching any other code path.
    import scripts.purge.fingerprints as fingerprints_module

    monkeypatch.setattr(fingerprints_module, "scan", lambda *args, **kwargs: False)

    sources = _write_synthetic_sources(tmp_path)
    data_module_out = tmp_path / "_content_fingerprints.py"
    results_out = tmp_path / "scratch" / "evasion-acceptance.json"

    args: list[str] = []
    for source in sources:
        args += ["--source", str(source)]
    args += [
        "--data-module-out",
        str(data_module_out),
        "--results-out",
        str(results_out),
    ]

    result = runner.invoke(_build_app(), args)

    assert result.exit_code == 1, result.output
    assert "FAIL" in result.output
    assert "did not match their expected outcome" in result.output

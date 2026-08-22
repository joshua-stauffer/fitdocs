"""`scripts/purge/pins.py`: `ReferenceRepair`, the epoch-convention
`pinned_at:` repair and the unrepaired-token report (task 7.5, design.md
`#### ReferenceRepair`, Req 9.4, 9.5, 9.8).

Every fixture builds synthetic files under `tmp_path` and a synthetic
`epoch` string; the real replacement root's short commit id does not exist
until task 8.2 forges it, so nothing here touches this repository's own
history or its real `.kiro/queue/` tree.

`EPOCH` is the one recurring "post-replacement" value shared across most
fixtures below -- deliberately, since the whole point of the convention is
that *every* open item's pin becomes this single literal value, so re-using
it (rather than inventing a fresh one per fixture) is itself the behaviour
under test. Where a fixture needs to distinguish "already holds the epoch
value" from "does not", it says so explicitly and uses a visibly different
original value.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.purge.pins import (
    PinOutcome,
    PinRepairVerificationError,
    apply_repair,
    count_other_identifier_tokens,
    repair_files,
    repair_text,
    resolve_pin,
    verify_rewrite,
)

EPOCH = "9f00aaa1112223334445"

# ---------------------------------------------------------------------------
# resolve_pin
# ---------------------------------------------------------------------------


def test_resolve_pin_reports_a_non_matching_value_as_repaired_to_the_epoch() -> None:
    outcome = resolve_pin("cafe123", EPOCH)

    assert outcome == PinOutcome(status="repaired", original="cafe123", resolved=EPOCH)


def test_resolve_pin_reports_an_exact_match_as_already_current() -> None:
    outcome = resolve_pin(EPOCH, EPOCH)

    assert outcome == PinOutcome(
        status="already_current", original=EPOCH, resolved=None
    )


def test_resolve_pin_repairs_a_branch_name_pin_the_same_as_a_commit_shaped_one() -> (
    None
):
    # No per-item judgement: the retired module treated a non-commit-shaped
    # value (a branch name) as a distinct "unresolvable" outcome. Under the
    # epoch convention there is no such distinction -- ANY value that is not
    # already exactly the epoch gets uniformly repaired to it.
    outcome = resolve_pin("spec/fit-ingest-primary-sourcing", EPOCH)

    assert outcome == PinOutcome(
        status="repaired", original="spec/fit-ingest-primary-sourcing", resolved=EPOCH
    )


def test_resolve_pin_never_substitutes_a_plausible_alternative_for_the_epoch() -> None:
    # Req 9.8: no plausible commit is ever substituted for a pre-replacement
    # reference. Pin the strongest form of this at resolve_pin's own level --
    # regardless of how close, how commit-shaped, or how unrelated `original`
    # is, `resolved` for a repaired outcome is always exactly the literal
    # `epoch` string, never something derived from `original` (e.g. a
    # "smart" merge of the two, or a value that merely shares a prefix).
    originals = [
        "cafe123",  # short, commit-shaped, shares no prefix with EPOCH
        "9f00aaa",  # a genuine PREFIX of EPOCH, still not equal to it
        EPOCH + "9",  # the reverse: EPOCH is a strict prefix of THIS one
        "spec/fit-ingest-primary-sourcing",  # not commit-shaped at all
        "0000000000000000000000000000000000000",  # commit-shaped, all zeros
    ]

    resolved_values = {resolve_pin(original, EPOCH).resolved for original in originals}

    assert resolved_values == {EPOCH}


# ---------------------------------------------------------------------------
# repair_text
# ---------------------------------------------------------------------------


def test_repair_text_rewrites_a_pinned_at_line_to_the_epoch_value() -> None:
    text = "---\nid: example\npinned_at: 7777777\ncontext: []\n---\n"

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == f"---\nid: example\npinned_at: {EPOCH}\ncontext: []\n---\n"
    assert outcomes == (
        PinOutcome(status="repaired", original="7777777", resolved=EPOCH),
    )


def test_repair_text_leaves_a_pinned_at_line_already_at_epoch_byte_identical() -> None:
    text = f"pinned_at: {EPOCH}\n"

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == text
    assert outcomes == (
        PinOutcome(status="already_current", original=EPOCH, resolved=None),
    )


def test_repair_text_repairs_a_branch_name_pin_uniformly_with_no_judgement() -> None:
    text = "pinned_at: spec/fit-ingest-primary-sourcing\n"

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == f"pinned_at: {EPOCH}\n"
    assert outcomes == (
        PinOutcome(
            status="repaired",
            original="spec/fit-ingest-primary-sourcing",
            resolved=EPOCH,
        ),
    )


def test_repair_text_leaves_every_other_commit_reference_exactly_as_written() -> None:
    # A "prose" hex token in an evidence line, and a resume-command hex
    # token, both distinct from the epoch value and from each other -- none
    # of these three may be rewritten, only the pinned_at line's own value.
    text = (
        "pinned_at: aaa1111\n"
        "## Evidence\n"
        "Broken at commit bbb2222 -- see also ccc3333 in the resume command.\n"
    )

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == (
        f"pinned_at: {EPOCH}\n"
        "## Evidence\n"
        "Broken at commit bbb2222 -- see also ccc3333 in the resume command.\n"
    )
    assert outcomes == (
        PinOutcome(status="repaired", original="aaa1111", resolved=EPOCH),
    )


def test_repair_text_rewrites_the_queue_readmes_schema_example_the_same_way() -> None:
    # Mirrors the queue README's own fenced-code-block schema example: the
    # pinned_at line sits inside prose and a code fence, not real YAML
    # frontmatter -- design.md's ReferenceRepair states the README's own
    # example pin is updated to the convention value (Req 9.5), so it is
    # repaired identically to a real queue item.
    text = (
        "## Item format\n\n"
        "```markdown\n"
        "---\n"
        "id: 2026-07-25-trimp-coefficients\n"
        "pinned_at: 2a01dfd\n"
        "---\n"
        "```\n"
    )

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == (
        "## Item format\n\n"
        "```markdown\n"
        "---\n"
        "id: 2026-07-25-trimp-coefficients\n"
        f"pinned_at: {EPOCH}\n"
        "---\n"
        "```\n"
    )
    assert outcomes == (
        PinOutcome(status="repaired", original="2a01dfd", resolved=EPOCH),
    )


def test_repair_text_matches_only_the_exact_pinned_at_line_shape() -> None:
    # The module docstring's exact claim: the regex "matches only a line of
    # the exact shape `pinned_at: <value>`, nothing else on the line and
    # nothing elsewhere in the file." Three distinct decoys in one text, none
    # of which is the real pin: a suffixed key (`last_pinned_at:`), a real
    # key with a trailing comment on the same line, and a mid-line prose
    # occurrence. A regex that drops its `^` anchor would match into
    # `last_pinned_at:`'s value; one whose trailing `[ \t]*$` is loosened to
    # `.*$` would swallow the trailing-comment line's value too.
    text = (
        "pinned_at: cafe123\n"
        "last_pinned_at: 9999999\n"
        "pinned_at: deadbee  # trailing comment\n"
        "the field pinned_at: 1234567 was set\n"
    )

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == (
        f"pinned_at: {EPOCH}\n"
        "last_pinned_at: 9999999\n"
        "pinned_at: deadbee  # trailing comment\n"
        "the field pinned_at: 1234567 was set\n"
    )
    assert len(outcomes) == 1
    assert outcomes[0] == PinOutcome(
        status="repaired", original="cafe123", resolved=EPOCH
    )


def test_repair_text_resolves_every_pinned_at_line_not_only_the_first() -> None:
    # `_PIN_LINE_RE.sub(_sub, text)` (every match) vs. `sub(_sub, text,
    # count=1)` (first match only) are indistinguishable when every fixture
    # carries at most one pin. Two pinned_at lines with DIFFERENT values --
    # one needing repair, one already at the epoch -- force both to be
    # visited.
    text = f"pinned_at: cafe123\n---\npinned_at: {EPOCH}\n"

    new_text, outcomes = repair_text(text, EPOCH)

    assert new_text == f"pinned_at: {EPOCH}\n---\npinned_at: {EPOCH}\n"
    assert outcomes == (
        PinOutcome(status="repaired", original="cafe123", resolved=EPOCH),
        PinOutcome(status="already_current", original=EPOCH, resolved=None),
    )


# ---------------------------------------------------------------------------
# count_other_identifier_tokens
# ---------------------------------------------------------------------------


def test_count_other_identifier_tokens_counts_tokens_outside_pinned_at_lines() -> None:
    # Four pairwise-distinct hex tokens: one inside pinned_at (must be
    # excluded) and three elsewhere (must all be counted). A mutation that
    # forgets to strip the pinned_at line first would count 4, not 3; a
    # mutation that under-counts (e.g. `findall(...)[:1]`) would report 1.
    text = (
        "pinned_at: aaa1111\n"
        "surfaced_by commit bbb2222\n"
        "resume_command references ccc3333\n"
        "context also cites ddd4444 in prose\n"
    )

    assert count_other_identifier_tokens(text) == 3


def test_count_other_identifier_tokens_is_zero_over_a_file_with_no_other_tokens() -> (
    None
):
    # Positive control: a file whose ONLY identifier-shaped token is the
    # pinned_at value itself must count zero, not silently pass by never
    # having stripped anything.
    text = "pinned_at: aaa1111\nno other commit references here at all\n"

    assert count_other_identifier_tokens(text) == 0


def test_count_other_identifier_tokens_counts_occurrences_not_distinct_tokens() -> None:
    # `len(_IDENTIFIER_TOKEN_RE.findall(stripped))` (occurrences) vs.
    # `len(set(...))` (distinct tokens) are indistinguishable when every
    # fixture uses pairwise-distinct tokens. Repeat the SAME token twice.
    text = "see fff7777 and fff7777 again\n"

    assert count_other_identifier_tokens(text) == 2


def test_count_other_identifier_tokens_excludes_words_below_the_seven_char_floor() -> (
    None
):
    # `\b[0-9a-f]{7,40}\b` (7-char floor) vs. `{4,40}` are indistinguishable
    # unless a fixture places a genuinely hex-shaped word SHORTER than seven
    # characters next to one that clears the floor. "beef" is 4 hex
    # characters and must not count; "fff7777" is 7 and must.
    text = "see beef and fff7777 nearby\n"

    assert count_other_identifier_tokens(text) == 1


def test_count_other_identifier_tokens_with_no_pinned_at_line_still_counts() -> None:
    # A file with zero pinned_at lines (the .sub over pinned_at is a no-op)
    # must still find tokens elsewhere -- proves the strip step does not
    # accidentally depend on a pinned_at line being present.
    text = "commit eee5555 fixed this; see fff6666 too.\n"

    assert count_other_identifier_tokens(text) == 2


# ---------------------------------------------------------------------------
# verify_rewrite
# ---------------------------------------------------------------------------


def test_verify_rewrite_raises_when_the_line_on_disk_does_not_match_the_outcome() -> (
    None
):
    outcomes = (PinOutcome(status="repaired", original="aaa1111", resolved=EPOCH),)
    # Simulates a write that silently failed to change the file: the
    # "rewritten" text still shows the OLD value.
    stale_text = "pinned_at: aaa1111\n"

    with pytest.raises(PinRepairVerificationError):
        verify_rewrite(stale_text, outcomes)


def test_verify_rewrite_passes_when_the_line_on_disk_matches_the_outcome() -> None:
    outcomes = (PinOutcome(status="repaired", original="aaa1111", resolved=EPOCH),)
    correct_text = f"pinned_at: {EPOCH}\n"

    verify_rewrite(correct_text, outcomes)  # must not raise


def test_verify_rewrite_catches_a_stale_value_that_is_not_the_first_line() -> None:
    # The module exists because a prior session's in-place edit performed two
    # of the queue contract's three acts and the third silently did not
    # happen. A check that reads back only the FIRST pinned_at: value would
    # have reported that same partial write as complete, so the first stale
    # line here is deliberately NOT the first line: the file's opening pin is
    # already correct and only the second is stale.
    outcomes = (
        PinOutcome(status="repaired", original="aaa1111", resolved=EPOCH),
        PinOutcome(status="repaired", original="bbb2222", resolved=EPOCH),
    )
    partially_written = f"pinned_at: {EPOCH}\npinned_at: bbb2222\n"

    with pytest.raises(PinRepairVerificationError):
        verify_rewrite(partially_written, outcomes)


def test_verify_rewrite_catches_a_pin_on_disk_the_outcomes_do_not_account_for() -> None:
    # The read-back must compare EVERY pin on disk, not merely as many as it
    # expected to find. The extra pin here carries the SAME value as the
    # expected one, so what discriminates is the COUNT, not the value: a
    # read-back that stopped after the values it had outcomes for, or that
    # collapsed duplicates, would see (EPOCH,) against (EPOCH,) and report a
    # file with an unaccounted-for second pin as complete. The differing-value
    # case is covered by the test above.
    outcomes = (PinOutcome(status="repaired", original="aaa1111", resolved=EPOCH),)
    extra_pin = f"pinned_at: {EPOCH}\npinned_at: {EPOCH}\n"

    with pytest.raises(PinRepairVerificationError):
        verify_rewrite(extra_pin, outcomes)


def test_apply_repair_verifies_every_pin_through_its_real_write_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The two tests above pin the "every line" property on the PURE
    # verify_rewrite. This one pins it one frame up, through apply_repair's
    # actual read-back, because that is where the defect the module exists
    # for lives: a write that lands part of its work and returns normally.
    #
    # The write here drops the second pin line entirely rather than leaving
    # it stale, which is the shape that defeats a truncating comparison: with
    # only one value on disk, a read-back that compared just the first pin,
    # just the last pin, or only as many values as it had outcomes for would
    # see (EPOCH,) against (EPOCH,) and call a half-written file complete.
    item = tmp_path / "two-pin-item.md"
    item.write_text("pinned_at: aaa1111\npinned_at: bbb2222\n", encoding="utf-8")

    real_write_text = Path.write_text
    truncated = f"pinned_at: {EPOCH}\n"

    def _dropping_write_text(
        self: Path, data: str, *args: object, **kwargs: object
    ) -> int:
        return real_write_text(self, truncated, *args, **kwargs)  # type: ignore[arg-type]

    # The starting content is not `truncated`, so an on-disk `truncated`
    # afterwards can only have come from the double.
    assert item.read_text(encoding="utf-8") != truncated

    monkeypatch.setattr(Path, "write_text", _dropping_write_text)

    with pytest.raises(PinRepairVerificationError):
        apply_repair(item, EPOCH)

    # Assert the double's EFFECT, not merely its precondition. Without this,
    # a double that silently did nothing would leave the original two stale
    # pins on disk, verify_rewrite would still raise on them, and the test
    # would pass having exercised none of the drop-shape it is named for --
    # measured: with the double's body replaced by `return 0`, this test and
    # the whole module stay green, and the `outcomes[:1]` mutation it exists
    # to kill goes green with them.
    assert item.read_text(encoding="utf-8") == truncated


def test_apply_repair_actually_calls_verify_rewrite_against_the_real_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Proves verify_rewrite is reachable from apply_repair's own write path,
    # not only unit-testable in isolation: forces the write to silently
    # write STALE content (the pre-repair text) while still returning
    # normally, mimicking a write that "succeeds" without producing the
    # field it was supposed to produce. Only a real read-back check inside
    # apply_repair can catch this -- a version that merely trusted
    # `write_text` not raising would return a `changed=True` result over a
    # file that, read back, still names the old value.
    item = tmp_path / "open-item.md"
    stale_content = "pinned_at: cafe123\n"
    item.write_text(stale_content, encoding="utf-8")

    real_write_text = Path.write_text

    def _lying_write_text(
        self: Path, data: str, *args: object, **kwargs: object
    ) -> int:
        # Ignore the caller's `data` and write the stale content instead --
        # simulates a write that did not actually take effect.
        return real_write_text(self, stale_content, *args, **kwargs)  # type: ignore[arg-type]

    # Confirm the double is actually installed and would be exercised: an
    # ordinary write through the unpatched method changes content, so if the
    # monkeypatch silently failed to install, this test would instead see
    # apply_repair succeed (no raise) rather than the verification error it
    # asserts below.
    control_path = tmp_path / "control.md"
    control_path.write_text("before\n", encoding="utf-8")
    control_path.write_text("after\n", encoding="utf-8")
    assert control_path.read_text(encoding="utf-8") == "after\n"

    monkeypatch.setattr(Path, "write_text", _lying_write_text)

    with pytest.raises(PinRepairVerificationError):
        apply_repair(item, EPOCH)


# ---------------------------------------------------------------------------
# apply_repair (real files under tmp_path)
# ---------------------------------------------------------------------------


def test_apply_repair_rewrites_a_pin_on_disk_and_reports_changed_true(
    tmp_path: Path,
) -> None:
    item = tmp_path / "open-item.md"
    item.write_text("---\npinned_at: cafe123\n---\n", encoding="utf-8")

    result = apply_repair(item, EPOCH)

    assert result.changed is True
    assert item.read_text(encoding="utf-8") == f"---\npinned_at: {EPOCH}\n---\n"
    assert result.pins == (
        PinOutcome(status="repaired", original="cafe123", resolved=EPOCH),
    )


def test_apply_repair_leaves_a_pin_already_at_epoch_byte_identical(
    tmp_path: Path,
) -> None:
    item = tmp_path / "already-repaired-item.md"
    original_bytes = f"---\npinned_at: {EPOCH}\n---\n".encode()
    item.write_bytes(original_bytes)
    before_mtime_ns = item.stat().st_mtime_ns

    result = apply_repair(item, EPOCH)

    assert result.changed is False
    assert item.read_bytes() == original_bytes
    # A real re-write, even of identical bytes, would still be a write --
    # the mtime must be untouched, proving apply_repair skipped write_text
    # entirely rather than writing back the same content.
    assert item.stat().st_mtime_ns == before_mtime_ns
    assert result.pins == (
        PinOutcome(status="already_current", original=EPOCH, resolved=None),
    )


def test_apply_repair_repairs_a_pin_the_same_regardless_of_directory_name(
    tmp_path: Path,
) -> None:
    # design.md #### ReferenceRepair: this module performs no open/closed
    # judgement of its own -- a path under a directory literally named
    # "closed" is repaired identically to any other path apply_repair is
    # handed. Distinguishing open from closed queue items is the caller's
    # job (task 9.1's), enforced by which paths it passes in, not by
    # anything inside this module inspecting the path or file content.
    closed_dir = tmp_path / "closed"
    closed_dir.mkdir()
    item = closed_dir / "2026-07-26-something.md"
    item.write_text("---\npinned_at: cafe123\n---\n", encoding="utf-8")

    result = apply_repair(item, EPOCH)

    assert result.changed is True
    assert item.read_text(encoding="utf-8") == f"---\npinned_at: {EPOCH}\n---\n"


def test_apply_repair_is_idempotent_on_a_genuine_second_run(tmp_path: Path) -> None:
    item = tmp_path / "open-item.md"
    item.write_text("---\npinned_at: cafe123\n---\n", encoding="utf-8")

    first = apply_repair(item, EPOCH)
    assert first.changed is True, (
        "the first run must actually change the file, or the second run's "
        "no-op assertion below would be trivially satisfied by a repair "
        "that never does anything"
    )
    content_after_first_run = item.read_bytes()

    second = apply_repair(item, EPOCH)

    assert second.changed is False
    assert item.read_bytes() == content_after_first_run
    assert second.pins == (
        PinOutcome(status="already_current", original=EPOCH, resolved=None),
    )


def test_apply_repair_returns_the_other_identifier_token_count_for_the_file(
    tmp_path: Path,
) -> None:
    item = tmp_path / "open-item.md"
    item.write_text(
        "---\npinned_at: cafe123\n---\n## Evidence\nsee also fff7777 and ggg8888\n",
        encoding="utf-8",
    )

    result = apply_repair(item, EPOCH)

    assert result.other_identifier_token_count == 1  # only "fff7777" is hex-shaped


# ---------------------------------------------------------------------------
# repair_files
# ---------------------------------------------------------------------------


def test_repair_files_raises_on_an_empty_path_sequence() -> None:
    with pytest.raises(ValueError):
        repair_files((), EPOCH)


def test_repair_files_repaired_count_is_an_independent_anchor_on_every_open_item(
    tmp_path: Path,
) -> None:
    # Three open items: the already-current one sits FIRST and two items
    # needing repair sit second and last. repaired_count must equal 2 -- an
    # independent anchor beside any per-file assertion, so a repair_files
    # implementation that silently drops one open path from its own
    # iteration (e.g. `paths[:-1]`, which would drop the LAST item here --
    # one of the two that must be repaired) is caught by this count even
    # though the per-file assertions on the remaining paths would still be
    # individually correct.
    first_already_current = tmp_path / "first.md"
    first_already_current.write_text(f"pinned_at: {EPOCH}\n", encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("pinned_at: dada789\n", encoding="utf-8")
    third = tmp_path / "third.md"
    third.write_text("pinned_at: cafe123\n", encoding="utf-8")

    report = repair_files((first_already_current, second, third), EPOCH)

    assert report.repaired_count == 2
    assert first_already_current.read_text(encoding="utf-8") == f"pinned_at: {EPOCH}\n"
    assert second.read_text(encoding="utf-8") == f"pinned_at: {EPOCH}\n"
    assert third.read_text(encoding="utf-8") == f"pinned_at: {EPOCH}\n"


def test_repair_files_repaired_count_stays_flat_across_a_genuine_second_run(
    tmp_path: Path,
) -> None:
    # Idempotence pinned at the RepairReport level, not only per-file: the
    # first run must genuinely repair something (repaired_count > 0), or the
    # second run's zero would be trivially satisfied by a repair that never
    # does anything.
    item = tmp_path / "open-item.md"
    item.write_text("pinned_at: cafe123\n", encoding="utf-8")

    first_report = repair_files((item,), EPOCH)
    assert first_report.repaired_count == 1, (
        "the first run must genuinely repair the pin, or the second run's "
        "zero-repaired assertion below would be trivially satisfied by a "
        "repair that never touches anything"
    )

    second_report = repair_files((item,), EPOCH)

    assert second_report.repaired_count == 0
    assert second_report.results[0].pins[0].status == "already_current"


def test_repair_files_sums_the_unrepaired_token_count_across_every_file(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.md"
    first.write_text("pinned_at: cafe123\nsee commit 1112223 too\n", encoding="utf-8")
    second = tmp_path / "second.md"
    second.write_text("pinned_at: dada789\nsee 4445556 and 7778889\n", encoding="utf-8")

    report = repair_files((first, second), EPOCH)

    assert report.total_other_identifier_tokens == 3


def test_repair_files_over_a_synthetic_queue_leaves_untouched_paths_byte_identical(
    tmp_path: Path,
) -> None:
    # design.md #### ReferenceRepair / Req 9.5: closed items are untouched.
    # This module enforces that only by construction -- a path never handed
    # to repair_files is never read or written. Build a synthetic queue with
    # an "open" and a "closed" directory, call repair_files ONLY over the
    # open item's path (as task 9.1's caller is specified to do), and prove
    # the closed item's bytes -- including its own pre-replacement pin -- are
    # completely unchanged, and its content plays no part in the report at
    # all (repaired_count and total_other_identifier_tokens only reflect the
    # one file actually handed in).
    open_dir = tmp_path / "queue"
    open_dir.mkdir()
    open_item = open_dir / "2026-07-25-trimp-coefficients.md"
    open_item.write_text("---\npinned_at: 2a01dfd\n---\n", encoding="utf-8")

    closed_dir = tmp_path / "queue" / "closed"
    closed_dir.mkdir()
    closed_item = closed_dir / "2026-07-10-something-closed.md"
    closed_original_bytes = (
        b"---\npinned_at: spec/fit-ingest-primary-sourcing\nstatus: done\n---\n"
        b"see also bbb2222 in the evidence\n"
    )
    closed_item.write_bytes(closed_original_bytes)
    closed_before_mtime_ns = closed_item.stat().st_mtime_ns

    report = repair_files((open_item,), EPOCH)

    assert open_item.read_text(encoding="utf-8") == f"---\npinned_at: {EPOCH}\n---\n"
    assert report.repaired_count == 1
    assert closed_item.read_bytes() == closed_original_bytes
    assert closed_item.stat().st_mtime_ns == closed_before_mtime_ns

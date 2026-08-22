"""`ReferenceRepair`: the epoch-convention `pinned_at:` repair + the
unrepaired-token report (task 7.5, design.md `#### ReferenceRepair`, Req 9.4,
9.5, 9.8).

**Amendment 1 (2026-08-17) retired the commit map.** A fresh-root replacement
has no post-replacement counterpart for any pre-replacement commit, so
per-item resolution against a `commit_map` is impossible by construction (Req
9.3). This module now applies **one value, uniformly, with no per-item
judgement**: every open queue item's `pinned_at:` field is set to the
replacement root's short commit id (the "epoch" value), whatever the field
previously held. `resolve_pin`, `repair_text`, `apply_repair` and
`repair_files` all take that single `epoch: str` in place of the retired
`commit_map: Mapping[str, str]` parameter; there is no map-driven path left
anywhere in this module.

**The line, and the one invariant it draws.** `pinned_at:` is machine-
consumed -- `/kiro-queue` runs `git log --oneline <pinned_at>..HEAD` against
it, so a dead value breaks a skill -- and it is repaired mechanically,
wherever it is handed a path, open items and the queue schema's own README
example alike -- design.md `#### ReferenceRepair` makes the README's example
pin carry the convention value, and gives this module no open/closed
judgement of its own. Every other commit reference in a tracked file (spec prose,
`roadmap.md`, a hook, a queue item's own evidence section or resume command)
is left exactly as written, because it is prose recording what was true at a
moment and rewriting it would falsify the record. This module never touches
those references; `repair_text`'s regex matches only a line of the exact
shape `pinned_at: <value>`, nothing else on the line and nothing elsewhere in
the file.

**Closed items are untouched by construction, not by a check inside this
module** (Req 9.5): declared stale rather than rewritten, because their pins
recorded what was true when the evidence was gathered and `/kiro-queue` ranks
open items only. This module performs no open/closed judgement of its own --
`apply_repair` and `repair_files` operate only on the paths they are handed,
so a closed item is untouched exactly because task 9.1's caller never passes
its path in. `count_other_identifier_tokens` still runs against whatever
content it is given.

**This is not a substitution, and Req 9.8 is why the distinction is written
down.** `resolve_pin` never computes, guesses or derives a value -- the
`resolved` field of every non-`already_current` outcome is always exactly the
literal `epoch` string the caller supplied, regardless of what shape the
original value had (a real short commit id, a stale full-length id, a branch
name, or anything else). No plausible commit is substituted for a
pre-replacement reference; the epoch value is a documented marker recording
that the item's evidence predates the replacement and its original pin is
permanently unresolvable, never a claim that the epoch is the pin's
post-replacement counterpart.

**Every write is verified by reading the line back, not merely by the file
having moved.** `apply_repair` writes only when `repair_text` actually
changed something, then re-reads the file from disk and calls
`verify_rewrite`, which re-parses the `pinned_at:` line(s) out of what is now
on disk and compares them, in order, against what the resolution outcomes say
they should be -- not merely that `Path.write_text` did not raise and the
path still exists. This is the same "read back what was written" discipline
`scripts/purge/rewrite_map.py` already applies to its own artifacts, here
applied to a status field a defect recorded at task 3.12 once left stale
while every other symptom of success (the file existing, the write
returning) looked fine.

**The unrepaired-token count is a distinct report, not a rename of any pin
outcome.** `count_other_identifier_tokens` scans a file's content *outside*
every `pinned_at:` line for anything shaped like a git commit identifier
(Req 9's blast-radius measurement: spec prose, `roadmap.md`, queue bodies'
evidence sections and resume commands) and returns how many it found --
deliberately not rewritten, and reported so silent non-repair of that surface
would not read as completeness. `repair_files` raises rather than silently
reporting zero when handed an empty file list, for the same reason
`scripts/purge/adopt.py::assert_carry_over` raises on an empty checklist: a
walk over nothing that reports "0 unrepaired tokens" is indistinguishable, in
the report alone, from a walk that found nothing to report.

**`RepairReport.repaired_count` is an independent count anchor, not a
derivative of iterating the file list.** The population `repair_files`
covers is discovered at call time from whatever `paths` it is handed; a
dropped path leaves every remaining iteration green on its own terms. Any
"every open item was repaired" claim is checked against this count, not by
inspecting individual files one at a time.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import typer

_PIN_LINE_RE = re.compile(
    r"^(?P<prefix>[ \t]*pinned_at:[ \t]*)(?P<value>\S+)[ \t]*$", re.MULTILINE
)
_IDENTIFIER_TOKEN_RE = re.compile(r"\b[0-9a-f]{7,40}\b")

PinStatus = Literal["repaired", "already_current"]


class PinRepairVerificationError(RuntimeError):
    """Raised by `apply_repair` when the `pinned_at:` value(s) read back from
    disk after a write do not match what the resolution outcomes said they
    should be -- the write happened, but the status line it was supposed to
    produce is not actually there."""


@dataclass(frozen=True)
class PinOutcome:
    """The result of resolving one `pinned_at:` value against the epoch
    value. `status` is `"already_current"` when the field already holds
    exactly `epoch` (nothing rewritten), otherwise `"repaired"` (the field
    is rewritten to exactly `epoch`, whatever shape it previously held --
    there is no per-item judgement)."""

    status: PinStatus
    original: str
    resolved: str | None


@dataclass(frozen=True)
class FileRepairResult:
    """One file's repair outcome: every `pinned_at:` line found (`pins`, in
    file order), the count of identifier-shaped tokens found elsewhere in the
    file (`other_identifier_token_count`), and whether the file's content on
    disk actually changed (`changed`)."""

    path: Path
    pins: tuple[PinOutcome, ...]
    other_identifier_token_count: int
    changed: bool


@dataclass(frozen=True)
class RepairReport:
    """The aggregate result of `repair_files` over a sequence of paths."""

    results: tuple[FileRepairResult, ...]

    @property
    def repaired_count(self) -> int:
        """The independent count anchor: how many individual `pinned_at`
        fields were actually rewritten (`status == "repaired"`) across every
        file this report covers. Kept distinct from simply iterating
        `results`, because the population `repair_files` covers is
        discovered at call time -- a repair that silently drops one open
        item from its own input leaves every remaining per-file assertion
        green; this count is the anchor a caller checks against the number
        of open items it expected to hand in."""
        return sum(
            1
            for result in self.results
            for outcome in result.pins
            if outcome.status == "repaired"
        )

    @property
    def total_other_identifier_tokens(self) -> int:
        """The unrepaired-token count: the sum, across every file this
        report covers, of identifier-shaped tokens found outside any
        `pinned_at:` line."""
        return sum(result.other_identifier_token_count for result in self.results)


def resolve_pin(original: str, epoch: str) -> PinOutcome:
    """Resolve one `pinned_at:` value against the single `epoch` value (the
    replacement root's short commit id). There is no per-item judgement: if
    `original` already equals `epoch` exactly, the outcome is
    `already_current` and nothing is rewritten; otherwise the outcome is
    `repaired` and `resolved` is always exactly `epoch`, whatever shape
    `original` had -- a real short commit id, a stale full-length id, a
    branch name, or anything else. Comparison is whole-value equality, not a
    prefix match in either direction: a value that merely happens to be a
    prefix of `epoch` (or vice versa) is a different value and must still be
    rewritten, or a later run could misreport an unrepaired field as already
    current."""
    if original == epoch:
        return PinOutcome(status="already_current", original=original, resolved=None)
    return PinOutcome(status="repaired", original=original, resolved=epoch)


def repair_text(text: str, epoch: str) -> tuple[str, tuple[PinOutcome, ...]]:
    """Rewrite every `pinned_at:` line in `text` to `epoch`, leaving every
    other line -- including a line whose value already equals `epoch`, and
    every other identifier-shaped token anywhere else in `text` -- exactly
    as written. Returns the (possibly unchanged) new text and every
    `PinOutcome` found, in file order."""
    outcomes: list[PinOutcome] = []

    def _sub(match: re.Match[str]) -> str:
        outcome = resolve_pin(match.group("value"), epoch)
        outcomes.append(outcome)
        if outcome.status == "repaired":
            return f"{match.group('prefix')}{outcome.resolved}"
        return match.group(0)

    new_text = _PIN_LINE_RE.sub(_sub, text)
    return new_text, tuple(outcomes)


def count_other_identifier_tokens(text: str) -> int:
    """Count identifier-shaped tokens (Req 9.4/9.8's blast radius: spec
    prose, `roadmap.md`, a hook, and queue bodies' evidence sections and
    resume commands) found in `text` *outside* every `pinned_at:` line. Every
    `pinned_at:` line is stripped from `text` before scanning, regardless of
    the pin's own resolution outcome, so the field this module does repair is
    never double-counted as a field it left alone."""
    stripped = _PIN_LINE_RE.sub("", text)
    return len(_IDENTIFIER_TOKEN_RE.findall(stripped))


def _pin_values(text: str) -> tuple[str, ...]:
    """Every `pinned_at:` value present in `text`, in file order -- used by
    `verify_rewrite` to read a rewrite back rather than trust that a write
    call not raising means the field it was supposed to produce exists."""
    return tuple(match.group("value") for match in _PIN_LINE_RE.finditer(text))


def verify_rewrite(rewritten_text: str, outcomes: Sequence[PinOutcome]) -> None:
    """Raise `PinRepairVerificationError` unless every `pinned_at:` value
    found in `rewritten_text` matches, in order, what `outcomes` says it
    should be (`epoch` for a `repaired` outcome, the unchanged `original`
    value otherwise). This is the read-back check itself -- pure and
    independent of any file I/O, so it can be exercised directly against a
    hand-built mismatch without touching a filesystem."""
    expected = tuple(
        outcome.resolved if outcome.status == "repaired" else outcome.original
        for outcome in outcomes
    )
    actual = _pin_values(rewritten_text)
    if actual != expected:
        raise PinRepairVerificationError(
            f"pinned_at read-back mismatch after rewrite: expected {expected!r}, "
            f"found {actual!r} on disk"
        )


def apply_repair(path: Path, epoch: str) -> FileRepairResult:
    """Repair every `pinned_at:` line in the file at `path` to `epoch`, in
    place. Writes only when `repair_text` actually produced different
    content (a file whose every `pinned_at:` value already equals `epoch` is
    never written to, so a second run over an already-repaired tree is a
    genuine no-op rather than a rewrite that happens to reproduce the same
    bytes); when it does write, reads the file back and calls
    `verify_rewrite` against what is now on disk before returning."""
    original = path.read_text(encoding="utf-8")
    new_text, outcomes = repair_text(original, epoch)
    changed = new_text != original
    if changed:
        path.write_text(new_text, encoding="utf-8")
        rewritten = path.read_text(encoding="utf-8")
        verify_rewrite(rewritten, outcomes)
    other_count = count_other_identifier_tokens(original)
    return FileRepairResult(
        path=path,
        pins=outcomes,
        other_identifier_token_count=other_count,
        changed=changed,
    )


def repair_files(paths: Sequence[Path], epoch: str) -> RepairReport:
    """Run `apply_repair` over every path in `paths` and aggregate the
    results. `paths` is the caller's own selection of which files to touch --
    this module performs no open/closed judgement of its own, so a closed
    queue item is untouched exactly because its path is never passed in, not
    because anything here inspects its status. Raises `ValueError` on an
    empty `paths` sequence rather than silently returning a report claiming
    zero unrepaired tokens and zero repairs -- a report built from no files
    would be indistinguishable, in the report alone, from a report proving
    nothing was found."""
    if not paths:
        raise ValueError(
            "repair_files called with zero paths; a report built from no "
            "files would claim completeness ('0 repaired, 0 unrepaired "
            "tokens') without having checked anything"
        )
    return RepairReport(results=tuple(apply_repair(path, epoch) for path in paths))


def run() -> None:
    """`purge pins` -- CLI wiring not yet implemented. `resolve_pin`,
    `repair_text`, `count_other_identifier_tokens`, `verify_rewrite`,
    `apply_repair` and `repair_files` above are implemented and tested (task
    7.5, `ReferenceRepair`, re-scoped to the epoch convention); wiring the
    CLI to the real replacement root's short commit id, the real open queue
    paths and the real `.kiro/queue/README.md` path is task 9.1's
    responsibility, run after the history replacement has produced a root to
    repair against -- the same posture `scripts/purge/preflight.py::run`,
    `scripts/purge/plan.py::run`, `scripts/purge/rewrite.py::run`,
    `scripts/purge/verify.py::verify_local` and `scripts/purge/adopt.py::run`
    state for their own CLI wiring.
    """
    typer.echo(
        "purge pins: ReferenceRepair CLI wiring not yet implemented (task "
        "9.1 supplies the real epoch value, open queue paths and README "
        "path at the call site)",
        err=True,
    )
    raise typer.Exit(code=1)

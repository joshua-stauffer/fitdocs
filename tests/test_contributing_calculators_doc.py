"""Verifies the worked example in ``docs/contributing-calculators.md`` against
the shipped ``LoadCalculator`` contract (Req 1.7, 13.3; design: ContributorGuide).

The guide is plugin-author-facing documentation living under ``docs/``, not a
module under ``src/`` -- ``uv run mypy`` (``files = ["src"]`` in
``pyproject.toml``) never sees it, so "the guide's example type-checks
against the shipped contract" is otherwise an unverifiable narrative claim.
This module is the mechanism that makes it a checked one: it extracts the
single worked example bracketed by the ``<!-- doctest: worked-example ... -->``
HTML comments in the guide, writes it to a real ``.py`` file outside
``src/``, and runs ``mypy --strict`` against it directly (mypy still resolves
the installed ``fitdocs`` package for an out-of-tree file). A future
contract change the guide's prose was not updated for -- a renamed outcome, a
changed ``compute`` signature, a moved import -- fails this test with mypy's
own diagnostic, not just a stale narrative.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_DOC = Path(__file__).resolve().parent.parent / "docs" / "contributing-calculators.md"
_START = "<!-- doctest: worked-example start -->"
_END = "<!-- doctest: worked-example end -->"
_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _read_doc() -> str:
    assert _DOC.is_file(), f"expected {_DOC} to exist"
    return _DOC.read_text(encoding="utf-8")


def _extract_worked_example() -> str:
    """The fenced Python source between the doctest markers, verbatim."""
    text = _read_doc()
    start = text.index(_START)
    end = text.index(_END, start)
    block = text[start:end]
    match = _FENCE.search(block)
    assert match is not None, (
        "no fenced ```python block found between the worked-example doctest "
        "markers in docs/contributing-calculators.md"
    )
    return match.group(1)


def test_worked_example_markers_are_present_and_wrap_a_calculator() -> None:
    """The extraction contract itself: markers exist and bracket real code.

    Guards the guard -- if a future edit removes or reorders the markers,
    this fails loudly instead of the type-check test silently extracting an
    empty string and reporting a false pass.
    """
    source = _extract_worked_example()
    assert "class ExampleCalculator" in source
    assert "def compute(" in source
    assert "def supports(" in source
    # `supports` may only ever narrow `supported_modalities`, never widen it
    # (Req 1.14) -- no type checker can catch this rule's absence, so it is
    # asserted textually here rather than left to rely on the guide's prose.
    assert "activity.modality not in self.supported_modalities" in source


def test_worked_example_type_checks_against_the_shipped_contract(
    tmp_path: Path,
) -> None:
    """The observable: the guide's worked example type-checks under mypy
    --strict against the real, installed ``fitdocs.load`` contract."""
    source = _extract_worked_example()
    example_file = tmp_path / "contributing_calculators_worked_example.py"
    example_file.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(example_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "docs/contributing-calculators.md's worked example does not "
        "type-check against the shipped LoadCalculator contract:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


# RETIRED here (encumbered-content-purge, task 4.4), not re-based:
# `test_guide_names_no_shipped_methodology`, which looped over the withdrawn
# methodology's identifying tokens and asserted neither appeared in
# `docs/contributing-calculators.md`. Req 11.7 requires a guard that detects
# re-introduction by matching an identifying token literally to be re-based
# or retired so that no token is retained in any form from which it can be
# read back; the loop's needles WERE the token, matched literally, so
# re-basing was not available the way it was for the steering pairing check
# in `tests/test_docs_guarantees.py` -- there is no neutral form of "assert
# this literal token is absent". The standing guard (task 4.3,
# `tests/test_forbidden_strings.py`) covers the same corpus for the file the
# retired loop actually scanned -- confirmed directly by planting a
# token-category value in `docs/contributing-calculators.md` (not in this
# module) and observing the standing guard's tracked-content and sdist-member
# scans both go red as the sole failures, then reverting to green.
#
# What retirement gives up, stated rather than left implicit (Req 11.9,
# recorded in `docs/reference/history-rewrites.md` Section 5, written at task
# 3.4): the guide's absence of the withdrawn calculator's name is no longer
# checked by an unconditional test, only by the opt-in standing guard, which
# skips rather than runs when `FITDOCS_FORBIDDEN_STRINGS` is unset.
#
# A second, narrower gap existed briefly during this repair and was closed
# in the same task: `tests/test_forbidden_strings.py`'s
# `_CONTENT_EXEMPT_VALUES` table had kept listing this module for the
# retired loop's own two reviewed token indices after the loop itself was
# deleted, which measured directly as a real hole -- planting exactly those
# two indices' values back into this file left the standing guard's scans
# fully green (5 passed, 0 failed). That table is owned by the
# `ForbiddenStrings` component (task 4.3), outside this task's
# `ReintroductionGuards` boundary, but the staleness was caused by this
# task's own deletions, so the repair removed the three stale entries and
# re-based the one test that pinned them
# (`test_reviewed_exemption_rejects_a_different_value_in_the_same_file`,
# now keyed to a still-live pair). Re-measured after the fix: planting the
# same two needles back into this file now reds the standing guard's
# tracked-content and sdist-member scans as the sole failures, matching
# `docs/contributing-calculators.md`'s own behaviour above -- see the task
# 4.4 status report for the full before/after reproduction.


def test_guide_uses_the_renamed_not_computed_outcome() -> None:
    """Amendment 3: the pre-rename ``NotConfirmed`` name resolves nowhere."""
    text = _read_doc()
    assert "NotConfirmed" not in text
    assert "NotComputed" in text


def test_guide_states_the_recorded_sample_aggregate_rule() -> None:
    """Req 9.2: a value derived from a recorded sample stream must be an
    aggregate over the samples *actually recorded*, never a missing sample
    treated as a zero.

    This obligation previously existed only as a docstring on
    ``LoadCalculator.compute`` in ``src/fitdocs/load/types.py`` -- absent
    from the guide that calculator authors actually read, and unpinned by
    any test, so a future edit could delete it silently. No type checker
    catches the absence of a documented postcondition, so it is asserted
    textually here, the same mechanism this file already uses for the
    ``supports`` narrowing rule.
    """
    text = _read_doc()
    start = text.index("## 5. Aggregating over recorded samples")
    end = text.index("## 6. Reading configuration and the activity's date", start)
    section = text[start:end]
    # Vacuous-walk control: the section itself must be non-empty before its
    # content is asserted, or a future heading rename would make this test
    # pass by extracting nothing.
    assert section.strip(), "expected a non-empty '## 5.' section in the guide"
    assert "never treat a missing sample as a zero" in section


def test_guide_shows_compute_taking_the_five_argument_context_signature() -> None:
    """Amendment 3: ``compute`` takes ``context: LoadContext`` as its 5th arg."""
    source = _extract_worked_example()
    assert re.search(r"def compute\(\s*self,", source) is not None
    assert "context: LoadContext" in source

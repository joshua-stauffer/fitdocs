"""Task 5.4: prove the load-channels feature did not move any shipped output.

Covers Requirement 9.8 -- "The fitdocs load-channel layer shall not change
the shipped derived-metric definitions it consumes, so that no already-
rendered metric value changes as a result of this feature." See
``.kiro/specs/load-channels/tasks.md`` task 5.4.

**Provenance (established once, by reading, not asserted here as a runtime
git-history check).** The pre-feature base for this repository's linear
history is ``c3d2201`` ("Initial commit of the published history"), the
first commit reachable on this branch -- an earlier, unsquashed history is
not available (see ``docs/reference/history-rewrites.md`` and the
encumbered-content-purge spec). Measured directly against that commit's
blobs:

* ``src/fitdocs/metrics/stress.py`` (``trimp``, ``power_tss``) is
  byte-identical between ``c3d2201`` and this branch's ``HEAD``.
* ``src/fitdocs/metrics/power.py`` (``normalized_power``, the NP rolling
  window) is likewise byte-identical.
* ``src/fitdocs/metrics/sources.py`` differs by exactly one hunk, entirely
  outside the training-impulse and normalized-power records: commit
  ``b4ccfa4`` (``fix(metrics): correct the moving-threshold record``, not a
  ``feat(load-channels)`` commit) rewrote only
  ``MOVING_THRESHOLD_CHOICE.justification``'s prose, stated in that
  commit's own message to move no computed value. Every ``feat(load-
  channels)``-tagged commit between ``c3d2201`` and ``HEAD`` was checked
  individually (``git show --stat``) and none touches
  ``src/fitdocs/metrics/sources.py``, ``stress.py`` or ``power.py`` at all.

A git-diff-based assertion inside the suite would be fragile against this
repository's own history-rewrite machinery (a rebase or a future purge
changes commit hashes without changing file content), so that provenance
finding is not re-derived here. What *is* asserted here, and kept honest
going forward, is the payload itself: the exact values and exact function
bodies this task found unchanged, pinned so that any *future* edit --
whether from this feature or a regression -- reds immediately.
"""

from __future__ import annotations

import hashlib
import inspect

from fitdocs.metrics import power, sources, stress
from fitdocs.metrics.types import TrimpWeighting

# --- training-impulse coefficients (Banister 1991 p. 408) -------------------


def test_banister_male_pair_value_pin() -> None:
    """The male curve fitdocs applies by default: y = 0.64e^1.92x.

    Mutation: change either literal below (or the shipped constant) and this
    reds -- proved by editing ``BANISTER_MALE_COEFFICIENT``'s ``value`` to
    ``0.65`` and observing the failure, then reverting.
    """
    assert sources.BANISTER_MALE_COEFFICIENT.value == 0.64
    assert sources.BANISTER_MALE_EXPONENT.value == 1.92


def test_banister_female_pair_value_pin() -> None:
    """The female curve: y = 0.86e^1.67x."""
    assert sources.BANISTER_FEMALE_COEFFICIENT.value == 0.86
    assert sources.BANISTER_FEMALE_EXPONENT.value == 1.67


def test_weighting_for_resolves_to_the_pinned_male_pair_by_default() -> None:
    """``weighting_for(None)`` -- what the heart-rate channel calls -- returns
    the exact pair pinned above, by object identity on both fields, not a
    coincidentally-equal recomputation.

    Mutation: point ``DEFAULT_TRIMP_WEIGHTING`` at
    ``TrimpWeighting.BANISTER_FEMALE`` and this reds (proved; reverted).
    """
    resolved = sources.weighting_for(None)
    assert resolved.coefficient is sources.BANISTER_MALE_COEFFICIENT
    assert resolved.exponent is sources.BANISTER_MALE_EXPONENT
    assert resolved.selection == TrimpWeighting.BANISTER_MALE


# --- normalized-power window (Coggan 2003 step 1, p. 10) -------------------


def test_np_rolling_window_value_pin() -> None:
    """30 *samples* wide at power.py's 1 Hz resample.

    Mutation: change ``NP_ROLLING_WINDOW_S.value`` to ``29`` and this reds
    (proved; reverted).
    """
    assert sources.NP_ROLLING_WINDOW_S.value == 30
    assert type(sources.NP_ROLLING_WINDOW_S.value) is int


def test_np_averaging_exponent_and_min_span_value_pin() -> None:
    assert sources.NP_AVERAGING_EXPONENT.value == 4
    assert sources.NP_MIN_SPAN_S.value == 30.0


def test_power_module_constants_equal_the_pinned_record_values() -> None:
    """``power.py``'s private window/exponent/span names carry the same
    *values* as the records pinned above, at the time this task measured
    them.

    This is a value-equality pin only: it compares ``.value`` to the private
    module-level name's current value, so it cannot distinguish "reads the
    record's ``.value`` at import time" from "restates the same number as an
    independent literal" -- both produce equal values and both leave this
    test green. The derivation itself (that ``power.py`` reads the record
    rather than re-declaring the literal) is pinned separately, by AST walk
    over the module source, in
    :func:`tests.metrics.test_power.test_module_source_has_no_bare_np_window_exponent_or_span_literal`.

    Mutation: restate any of the three private names in ``power.py`` with a
    literal that does not match the pinned value above (e.g. ``29`` instead
    of ``30``, ``5`` instead of ``4``, ``31.0`` instead of ``30.0``) and this
    reds (proved; reverted). Restating the *same* value as a literal --
    which is the derivation change this test's old name and docstring
    incorrectly claimed it caught -- does not red it, by construction of a
    value-equality assertion.
    """
    assert sources.NP_ROLLING_WINDOW_S.value == power._NP_ROLLING_WINDOW_S
    assert sources.NP_AVERAGING_EXPONENT.value == power._NP_AVERAGING_EXPONENT
    assert sources.NP_MIN_SPAN_S.value == power._NP_MIN_SPAN_S


# --- function-body content pins ---------------------------------------------
#
# Value pins alone would not catch a control-flow change that preserves every
# named constant -- e.g. loosening :func:`fitdocs.metrics.stress.trimp`'s
# ``if dt <= 0`` skip to ``if dt < 0`` (measured: this alone reds
# ``test_trimp_source_matches_pre_feature_content`` below, with no named
# constant touched). These hash the exact source text this task measured
# byte-identical against the pre-feature commit ``c3d2201`` (see the module
# docstring), so any later edit to these four functions -- from this feature
# or any other -- reds here regardless of whether it touches a named
# constant.

_EXPECTED_SOURCE_SHA256 = {
    "trimp": "a673a893c5ef4cbf6063bf696b7e567eb85685a3068ddb2bc4a47a792d41a7b2",
    "power_tss": "e2da85ab4175b208dca8ff6bad00a28affaa144cb42dc16830b919d8ca0cc654",
    "normalized_power": (
        "d36233de363f1cdeff61d3c1307ce7c42a74ea5945850e933d817174a2bbc511"
    ),
    "weighting_for": "1e48d6619f6c3a38314608a6b7bec7664001624b80e823dc70e69103a15b3aa9",
}


def _source_digest(fn: object) -> str:
    return hashlib.sha256(inspect.getsource(fn).encode()).hexdigest()  # type: ignore[arg-type]


_DIGEST_MISMATCH_MSG = (
    "source digest changed for {name} -- this pin reds on ANY source edit, "
    "including a semantically neutral one (a comment, a docstring wording "
    "change, a ruff-format reflow). If the function's behavior genuinely "
    "changed on purpose, recompute the digest and update "
    "_EXPECTED_SOURCE_SHA256['{name}'] deliberately, as a reviewed line in "
    "the diff -- do not paste in whatever a failing run prints without "
    "reading the source diff first."
)


def test_trimp_source_matches_pre_feature_content() -> None:
    """Mutation: change the clamp bounds, the ``exp`` argument order, or the
    accumulation line inside :func:`fitdocs.metrics.stress.trimp` and this
    reds -- proved by swapping ``hrr`` and ``coefficient`` in the
    accumulation expression (numerically different for non-trivial inputs)
    and observing the failure, then reverting.
    """
    assert _source_digest(stress.trimp) == _EXPECTED_SOURCE_SHA256["trimp"], (
        _DIGEST_MISMATCH_MSG.format(name="trimp")
    )


def test_power_tss_source_matches_pre_feature_content() -> None:
    assert _source_digest(stress.power_tss) == _EXPECTED_SOURCE_SHA256["power_tss"], (
        _DIGEST_MISMATCH_MSG.format(name="power_tss")
    )


def test_normalized_power_source_matches_pre_feature_content() -> None:
    assert (
        _source_digest(power.normalized_power)
        == _EXPECTED_SOURCE_SHA256["normalized_power"]
    ), _DIGEST_MISMATCH_MSG.format(name="normalized_power")


def test_weighting_for_source_matches_pre_feature_content() -> None:
    assert (
        _source_digest(sources.weighting_for)
        == _EXPECTED_SOURCE_SHA256["weighting_for"]
    ), _DIGEST_MISMATCH_MSG.format(name="weighting_for")


def test_source_digests_are_pairwise_distinct() -> None:
    """Sanity check on the digest table's literals, not a positive control.

    A copy-paste error that gave two entries the same expected hash is
    *not* invisible to the four tests above: since the digests are
    hard-coded (never recomputed and compared to each other) and the four
    hashed functions necessarily have different source text, any such
    collision means at least one of ``test_*_source_matches_pre_feature_
    content`` already has the wrong expected value baked in, and reds on
    its own. Measured: setting all four table entries to ``trimp``'s digest
    produces ``4 failed`` (the ``power_tss``, ``normalized_power`` and
    ``weighting_for`` per-function tests plus this one;
    ``test_trimp_source_matches_pre_feature_content`` stays green, since the
    value it expects is trimp's own true digest); setting only one entry
    (``power_tss``) to ``trimp``'s digest produces
    ``2 failed`` -- ``test_power_tss_source_matches_pre_feature_content``
    among them. This test cannot red without at least one per-function test
    reddening first; it only additionally documents, for a human reading the
    table, that the four literals were not meant to collide.
    """
    assert len(set(_EXPECTED_SOURCE_SHA256.values())) == len(_EXPECTED_SOURCE_SHA256)

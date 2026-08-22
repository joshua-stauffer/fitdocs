"""The numeric-literal half of ``ConstantGuard`` (task 12.2; Req 15.5, 15.7,
16.3) -- design.md's "Literal scan" bullet at ``ConstantGuard``
(``tests/metrics/test_sources.py``, ``tests/metrics/test_constant_guard.py``).

Task 12.1 shipped the *registry* half in ``test_sources.py``: assertions that
walk ``CONSTANT_SOURCES`` and ``WEIGHTING_PAIRS`` and can only confirm what is
already registered there. Req 16.3 ("an uncited covered constant fails the
library's own checks") needs a check that can fail when a constant is *not*
registered at all -- a bare number sitting in a metric module's own source,
never routed through ``fitdocs.metrics.sources``. A registry walk cannot see
that by construction (it only ever sees what somebody already added), so this
module is a second, independent test module with no shared state: it parses
``aggregates.py``, ``power.py`` and ``stress.py`` as source text and collects
every numeric literal their syntax trees actually contain, rather than
trusting any docstring's claim about what those modules do or do not declare.

Every literal found must be present in ``_EXEMPTIONS`` below, each entry
naming the exact site (module, line, column, value) and the Req 15.7 reason
it carries no methodological choice -- a unit conversion, an arithmetic
identity, or a percentage scaling that follows from a definition already
cited. A value read from a ``CitedConstant`` (``sources.FOO.value``) is an
``ast.Attribute`` access, not an ``ast.Constant`` literal, so none of the ten
values ``test_sources.py`` already pins ever reaches this scan at all --
that is what "either read from a cited constant or exempted" means in
practice, and is exercised directly by
``test_a_cited_constant_access_does_not_appear_as_a_literal`` below.

The exemption list is this guard's own weak point (design.md: "an over-broad
entry silently re-opens the hole"), so ``test_no_exemption_entry_is_unused``
asserts every entry is actually matched by a literal the scan finds --
covering the *other* direction task 12.1's WARN about vacuous walks names:
an exemption that matches nothing is exactly as dangerous as a walk that
finds nothing, because it lets `_EXEMPTIONS` grow without anyone confirming
each new entry excuses a real site.

A third, independent assertion carries Req 15.5 directly:
``test_reference_directory_is_named_nowhere_under_the_metrics_package`` scans
every ``.py`` file under ``src/fitdocs/metrics/`` (not only the three literal-
scanned modules) for the literal string ``docs/reference`` -- in code, in a
comment, in a docstring -- since Req 15.5 forbids naming that tree as a
constant's source anywhere in this package, not only where a numeric literal
also happens to sit.
"""

from __future__ import annotations

import ast
import enum
import pathlib
from dataclasses import dataclass
from types import ModuleType

from fitdocs.metrics import aggregates, power, stress

_METRIC_MODULES: tuple[ModuleType, ...] = (aggregates, power, stress)


class ExemptionCategory(enum.Enum):
    """The three, and only three, reasons Req 15.7 lets a numeric literal in
    the metrics package go uncited. Restricting this to an enum (rather than
    a free-text ``reason`` field alone) is what keeps a future entry from
    inventing a fourth category by accident."""

    UNIT_CONVERSION = "unit_conversion"
    ARITHMETIC_IDENTITY = "arithmetic_identity"
    PERCENTAGE_SCALING = "percentage_scaling"


@dataclass(frozen=True)
class LiteralExemption:
    """One numeric literal this scan is told to pass over, and why.

    ``module`` is the metric module's own filename (``"aggregates.py"``,
    ``"power.py"``, ``"stress.py"``) -- not an import path -- so it matches
    ``pathlib.Path(module.__file__).name`` directly. ``line``, ``col_offset``
    and ``value`` together identify the exact AST ``Constant`` node the
    exemption excuses. ``col_offset`` is load-bearing, not decorative: the
    key used to be ``(line, value)`` alone, which let a literal newly
    inserted on an already-exempted line silently hide behind a sibling
    exemption for the same value on that line (e.g. a genuine
    ``CitedConstant`` read replaced by a bare ``1`` on a line that already
    carries an exemption for the value ``1`` from an unrelated ``[-1]`` or
    ``[0]`` index) -- two distinct AST nodes with the same ``(line, value)``
    but different ``col_offset`` are two distinct sites, and each needs its
    own entry (``power.py``'s line with ``time_s[0]`` used twice has two
    entries below, one per column, for exactly this reason). A future edit
    that moves the literal to a different line or column, or changes its
    value, stops matching this entry and reddens the coverage test below
    until the entry (or the site) is corrected -- deliberately, not a
    weakness to route around.
    """

    module: str
    line: int
    col_offset: int
    value: int | float
    category: ExemptionCategory
    reason: str


# --- exemption list (Req 15.7) -----------------------------------------------
#
# Every entry below was checked against the exact source line (and, since
# task 12.2's remediation, column) it names -- each ``reason`` states what
# that literal, at that site, actually does, not a generic description of
# its value. None of the fifty sites is a constant Req 15.6 enumerates
# (those ten are all ``sources.FOO.value`` attribute accesses, never bare
# literals in these three modules); every one here is either an arithmetic
# bookkeeping literal (a first/last index, an additive identity, a divisor
# guard, a slice or range boundary, a window's own arithmetic) or one of
# four named unit conversions / one named percentage scaling
# (`aggregates.py`'s `1000`, `stress.py`'s `60`/`3600`, `power.py`'s `60`
# and `100`). Three of those four unit conversions are worked examples
# design.md itself calls out; the fourth, `power.py`'s `60` (m/s to m/min
# for the run-modality efficiency factor), is inferable from design.md's
# "m/min" wording but is not itself presented there as a worked example.

_EXEMPTIONS: tuple[LiteralExemption, ...] = (
    # --- aggregates.py -------------------------------------------------------
    LiteralExemption(
        "aggregates.py",
        120,
        56,
        2,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "_derive_moving_time_s requires at least two samples to have a "
        "consecutive pair to sum a duration over; below two there is no "
        "pair at all.",
    ),
    LiteralExemption(
        "aggregates.py",
        122,
        12,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total` starts at the additive identity before summing each "
        "moving pair's duration.",
    ),
    LiteralExemption(
        "aggregates.py",
        123,
        33,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "the number of consecutive sample pairs among len(time_s) samples "
        "is one fewer than the sample count.",
    ),
    LiteralExemption(
        "aggregates.py",
        128,
        30,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "distance[i + 1] indexes the later half of the consecutive pair "
        "(i, i + 1) being tested for movement.",
    ),
    LiteralExemption(
        "aggregates.py",
        131,
        32,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[i + 1] indexes the same consecutive pair's later sample, "
        "for the duration added to the moving-time sum.",
    ),
    LiteralExemption(
        "aggregates.py",
        150,
        31,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[0] is the first recorded sample's offset -- index 0 by the "
        "definition of 'first'.",
    ),
    LiteralExemption(
        "aggregates.py",
        150,
        19,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[-1] is Python's own index-from-the-end convention for "
        "'last'; the elapsed span is the last offset minus the first.",
    ),
    LiteralExemption(
        "aggregates.py",
        195,
        57,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "distance <= 0 guards the pace division below; a non-positive "
        "distance cannot be a divisor for a rate.",
    ),
    LiteralExemption(
        "aggregates.py",
        197,
        32,
        1000.0,
        ExemptionCategory.UNIT_CONVERSION,
        "converts distance from metres to kilometres before dividing "
        "moving time by it, to report pace per kilometre.",
    ),
    LiteralExemption(
        "aggregates.py",
        289,
        17,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "max(0, ...) clamps the trailing altitude window's start index to "
        "the first valid index; a window cannot start before the series "
        "begins.",
    ),
    LiteralExemption(
        "aggregates.py",
        289,
        33,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "a trailing window of width `window` ending at i starts at "
        "i - window + 1 -- the arithmetic definition of a window's first "
        "index given its own width and end.",
    ),
    LiteralExemption(
        "aggregates.py",
        290,
        48,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "altitude[lo : i + 1] slices up to and including i; Python slice "
        "upper bounds are exclusive, so +1 is required to include index i "
        "itself.",
    ),
    LiteralExemption(
        "aggregates.py",
        307,
        23,
        2,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "differencing consecutive smoothed altitude points needs at least "
        "two of them; below two there is nothing to difference.",
    ),
    LiteralExemption(
        "aggregates.py",
        309,
        11,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`gain` starts at the additive identity before summing positive deltas.",
    ),
    LiteralExemption(
        "aggregates.py",
        310,
        11,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`loss` starts at the additive identity before summing the "
        "magnitudes of negative deltas.",
    ),
    LiteralExemption(
        "aggregates.py",
        311,
        49,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "smoothed[1:] pairs each smoothed point with its successor by "
        "offsetting the second list by one position -- the definition of "
        "'consecutive' used to difference them.",
    ),
    LiteralExemption(
        "aggregates.py",
        313,
        19,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "delta > 0 is the sign test distinguishing a gain from a loss.",
    ),
    LiteralExemption(
        "aggregates.py",
        315,
        21,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "delta < 0 is the mirrored sign test for a loss.",
    ),
    LiteralExemption(
        "aggregates.py",
        323,
        18,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "result[0] is the first element of the (gain, loss) pair "
        "_altitude_gain_loss returns.",
    ),
    LiteralExemption(
        "aggregates.py",
        330,
        18,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "result[1] is the second element of the same (gain, loss) pair.",
    ),
    # --- power.py --------------------------------------------------------
    LiteralExemption(
        "power.py",
        168,
        16,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "rel[-1] is the last offset in the series shifted to zero at the "
        "first recorded sample, via Python's own -1 last-index convention.",
    ),
    LiteralExemption(
        "power.py",
        172,
        33,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "range(int(span) + 1) needs +1 because range's own upper bound is "
        "exclusive, but the resample grid must include the final whole "
        "second.",
    ),
    LiteralExemption(
        "power.py",
        174,
        53,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "bisect_right(...) - 1 converts bisect's own insertion point into "
        "the index of the most recent sample at or before the target "
        "second, per bisect's documented convention.",
    ),
    LiteralExemption(
        "power.py",
        178,
        41,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "scanned_through + 1 starts the fold-in scan one past the last raw "
        "index already folded into last_recorded -- Python's own "
        "next-index-after convention, not an independent choice of where "
        "to resume.",
    ),
    LiteralExemption(
        "power.py",
        178,
        50,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "idx + 1 makes range's own exclusive upper bound include idx "
        "itself, so the fold-in scan reaches the sample the bisect just "
        "picked, not only the ones strictly before it.",
    ),
    LiteralExemption(
        "power.py",
        231,
        21,
        2,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "normalized_power requires at least two samples before there is "
        "any span at all to measure against _NP_MIN_SPAN_S.",
    ),
    LiteralExemption(
        "power.py",
        233,
        27,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[0] is the first sample's offset, used for the overall span "
        "check against _NP_MIN_SPAN_S (this guard runs before any "
        "truncation to the first RECORDED sample).",
    ),
    LiteralExemption(
        "power.py",
        233,
        15,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[-1] is the last sample's offset via Python's -1 "
        "convention, the other end of the same span check.",
    ),
    LiteralExemption(
        "power.py",
        243,
        36,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "1 / exponent takes the root as the averaging exponent's own "
        "multiplicative inverse -- the module's stated technique (see "
        "_NP_AVERAGING_EXPONENT's own docstring) for keeping the power "
        "and its root from drifting apart, not an independent literal.",
    ),
    LiteralExemption(
        "power.py",
        255,
        45,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "ftp <= 0 guards the intensity-factor division; a non-positive "
        "FTP cannot be a divisor.",
    ),
    LiteralExemption(
        "power.py",
        266,
        57,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "avg_power <= 0 guards the variability-index division; a "
        "non-positive average power cannot be a divisor.",
    ),
    LiteralExemption(
        "power.py",
        286,
        35,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "avg_hr <= 0 guards the efficiency-factor division; a "
        "non-positive heart rate cannot be a divisor.",
    ),
    LiteralExemption(
        "power.py",
        292,
        29,
        60.0,
        ExemptionCategory.UNIT_CONVERSION,
        "converts running speed from m/s to m/min -- the efficiency "
        "factor's output unit for the run modality -- by multiplying by "
        "60 seconds per minute.",
    ),
    LiteralExemption(
        "power.py",
        328,
        18,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "mean_hr == 0 guards the per-half efficiency division; zero is "
        "the boundary value that makes the ratio undefined.",
    ),
    LiteralExemption(
        "power.py",
        359,
        17,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "the first (leftmost) time_s[0] on this line is the first sample's "
        "offset -- the start of the span being halved to find the "
        "decoupling midpoint.",
    ),
    LiteralExemption(
        "power.py",
        359,
        31,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[-1] is the last sample's offset via Python's -1 "
        "convention, the other end of the span being halved.",
    ),
    LiteralExemption(
        "power.py",
        359,
        43,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "the second (rightmost) time_s[0] on the same line is the same "
        "first sample's offset, subtracted from time_s[-1] to compute the "
        "span before halving it -- the same index-0-is-first identity as "
        "the first occurrence, at a distinct AST site (different column).",
    ),
    LiteralExemption(
        "power.py",
        359,
        49,
        2.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "dividing the elapsed span by 2.0 is the arithmetic definition of "
        "a midpoint, not a methodological choice about where to split.",
    ),
    LiteralExemption(
        "power.py",
        362,
        60,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "ef_first == 0 guards the decoupling-percentage division; zero is "
        "the boundary value that makes the ratio undefined.",
    ),
    LiteralExemption(
        "power.py",
        364,
        47,
        100.0,
        ExemptionCategory.PERCENTAGE_SCALING,
        "expresses the (EF_first - EF_second) / EF_first ratio as a "
        "percentage; that ratio is the decoupling definition already "
        "pinned in research.md's 'Decision: pin the formulas the "
        "reference leaves undocumented' and restated in this module's "
        "own docstring -- scaling an already-defined ratio by 100 adds "
        "no further methodological choice.",
    ),
    # --- stress.py -------------------------------------------------------
    LiteralExemption(
        "stress.py",
        90,
        36,
        60.0,
        ExemptionCategory.UNIT_CONVERSION,
        "_SECONDS_PER_MINUTE converts seconds to minutes for dt_min in the TRIMP sum.",
    ),
    LiteralExemption(
        "stress.py",
        91,
        34,
        3600.0,
        ExemptionCategory.UNIT_CONVERSION,
        "_SECONDS_PER_HOUR converts seconds to hours in the TSS 'per hour "
        "at threshold power' denominator (Coggan (2003) step 8).",
    ),
    LiteralExemption(
        "stress.py",
        96,
        15,
        1.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "clamps the heart-rate-reserve fraction to the unit interval's "
        "upper bound; a fraction of reserve cannot exceed 1 by the "
        "ratio's own definition (HRr = clamp(fraction, 0, 1), per this "
        "module's own docstring).",
    ),
    LiteralExemption(
        "stress.py",
        96,
        24,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "clamps the same fraction to the unit interval's lower bound; a "
        "fraction of reserve cannot be negative by the same ratio "
        "definition.",
    ),
    LiteralExemption(
        "stress.py",
        151,
        18,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "reserve <= 0 guards the HRr division; a non-positive "
        "heart-rate reserve cannot be a divisor.",
    ),
    LiteralExemption(
        "stress.py",
        161,
        12,
        0.0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "`total` starts at the additive identity before summing each "
        "pair's TRIMP contribution.",
    ),
    LiteralExemption(
        "stress.py",
        163,
        23,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "range(n - 1) is one fewer than the paired-sample count n -- the "
        "number of consecutive sample pairs.",
    ),
    LiteralExemption(
        "stress.py",
        167,
        24,
        1,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "time_s[i + 1] indexes the consecutive pair's later sample.",
    ),
    LiteralExemption(
        "stress.py",
        168,
        17,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "dt <= 0 excludes a non-positive duration from the sum; only a "
        "positive elapsed interval between samples contributes.",
    ),
    LiteralExemption(
        "stress.py",
        198,
        70,
        0,
        ExemptionCategory.ARITHMETIC_IDENTITY,
        "ftp <= 0 guards the TSS division; a non-positive FTP cannot be a divisor.",
    ),
)


def _numeric_literals(module: ModuleType) -> list[tuple[int, int, int | float]]:
    """Every ``(line, col_offset, value)`` triple for a numeric (non-``bool``)
    ``Constant`` node anywhere in ``module``'s own source -- the whole tree,
    not only top-level statements, so a literal nested inside an ``if`` or a
    call argument is caught too. ``bool`` is excluded deliberately: ``True`` /
    ``False`` are ``int`` subclasses in Python but carry no numeric
    methodological choice, and none of the three modules' own control-flow
    booleans (e.g. ``strict=False`` in a ``zip`` call) is a constant this
    guard is meant to police."""
    path = pathlib.Path(module.__file__ or "").resolve()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    literals: list[tuple[int, int, int | float]] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, (int, float))
            and not isinstance(node.value, bool)
        ):
            literals.append((node.lineno, node.col_offset, node.value))
    return literals


def _exemptions_by_module() -> dict[str, set[tuple[int, int, int | float]]]:
    by_module: dict[str, set[tuple[int, int, int | float]]] = {}
    for exemption in _EXEMPTIONS:
        by_module.setdefault(exemption.module, set()).add(
            (exemption.line, exemption.col_offset, exemption.value)
        )
    return by_module


def test_every_numeric_literal_in_the_three_metric_modules_is_exempted() -> None:
    """Req 16.3's own "fails rather than the constant shipping uncited":
    every numeric literal the scan finds in ``aggregates.py``, ``power.py``
    and ``stress.py`` must be named in ``_EXEMPTIONS`` at its exact line,
    column and value. A bare number added to any of the three modules that
    is not already covered by name, line, column and value reddens this
    test. Keying on ``col_offset`` in addition
    to ``(line, value)`` is itself load-bearing: a new literal landing on an
    already-exempted line, with a value some *other* literal on that same
    line already carries (e.g. a genuine ``CitedConstant`` read replaced by
    a bare ``1`` on a line that already has an unrelated ``[-1]`` or ``[0]``
    index exempted), sits at a different column and so is not silently
    absorbed by the sibling entry."""
    exemptions_by_module = _exemptions_by_module()
    scanned_modules = 0
    scanned_literals = 0
    for module in _METRIC_MODULES:
        module_name = pathlib.Path(module.__file__ or "").name
        literals = _numeric_literals(module)
        assert literals, f"the walk found no numeric literals in {module_name}"
        scanned_modules += 1
        allowed = exemptions_by_module.get(module_name, set())
        for line, col_offset, value in literals:
            scanned_literals += 1
            assert (line, col_offset, value) in allowed, (
                f"{module_name}:{line}:{col_offset} literal {value!r} is "
                "neither read from a CitedConstant nor present in _EXEMPTIONS"
            )
    assert scanned_modules == len(_METRIC_MODULES), (
        "the walk did not reach all three metric modules"
    )
    assert scanned_literals, "the walk found no numeric literals to check at all"


def test_no_exemption_entry_is_unused() -> None:
    """design.md's own stated weak point: "an over-broad entry silently
    re-opens the hole" -- so every entry in ``_EXEMPTIONS`` must actually
    match a numeric literal the scan finds in its named module, at its
    named line, column and value. An entry that matches nothing (a stale
    site, a typo'd line or column number, or a speculative entry added for a
    literal that was never there) reddens this test rather than sitting
    unused forever."""
    found_by_module: dict[str, set[tuple[int, int, int | float]]] = {}
    for module in _METRIC_MODULES:
        module_name = pathlib.Path(module.__file__ or "").name
        found_by_module[module_name] = set(_numeric_literals(module))

    assert _EXEMPTIONS, "the exemption list is empty -- nothing to check for use"
    for exemption in _EXEMPTIONS:
        found = found_by_module.get(exemption.module, set())
        assert (exemption.line, exemption.col_offset, exemption.value) in found, (
            f"{exemption.module}:{exemption.line}:{exemption.col_offset} "
            f"value {exemption.value!r} is an unused exemption entry -- no "
            "such literal was found in the scan"
        )


def test_a_cited_constant_access_does_not_appear_as_a_literal() -> None:
    """The claim the module docstring above makes explicit: reading a value
    through its ``CitedConstant`` (e.g. ``sources.TSS_SCALE.value``) is an
    ``ast.Attribute`` access, never an ``ast.Constant`` literal, so none of
    the ten values ``test_sources.py`` already pins ever needs an
    ``_EXEMPTIONS`` entry of its own. Checked directly against the actual
    source rather than only asserted in prose: every module-level ``Final``
    that reads ``sources.<NAME>.value`` is an ``ast.Attribute`` whose value
    is itself an ``ast.Attribute`` on a ``Name`` -- never a bare numeric
    literal -- and this test fails if that ever stops being true for any of
    the six sourced module-level constants. (Task 12.2 briefly added a
    seventh, ``_POWER_ABSENT_SAMPLE_FILL``; the 2026-07-30 absent-power-
    sample ruling removed it again -- the resample grid now starts at the
    first RECORDED sample instead of fabricating a fill value for the dead
    air before it, so there is no fourth fill-value constant left to read.)"""
    sourced_names = (
        (aggregates, "_MOVING_SPEED_THRESHOLD_MPS"),
        (aggregates, "_ALTITUDE_SMOOTHING_WINDOW"),
        (power, "_NP_MIN_SPAN_S"),
        (power, "_NP_ROLLING_WINDOW_S"),
        (power, "_NP_AVERAGING_EXPONENT"),
        (stress, "_TSS_SCALE"),
    )
    checked = 0
    for module, name in sourced_names:
        module_name = pathlib.Path(module.__file__ or "").name
        path = pathlib.Path(module.__file__ or "").resolve()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == name
            ) or (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == name
            ):
                checked += 1
                assert isinstance(node.value, ast.Attribute), (
                    f"{module_name}:{name} is not read through an attribute access"
                )
                assert isinstance(node.value.value, ast.Attribute), (
                    f"{module_name}:{name} does not read a CitedConstant's "
                    "own .value attribute"
                )
    assert checked == len(sourced_names), (
        f"the walk found only {checked} of {len(sourced_names)} sourced "
        "module-level constants"
    )


def test_reference_directory_is_named_nowhere_under_the_metrics_package() -> None:
    """Req 15.5, carried directly rather than through the literal scan
    above (a string is not a numeric literal): the substring
    ``docs/reference`` must not appear anywhere under
    ``src/fitdocs/metrics/`` -- in code, in a comment, or in a docstring --
    since Req 15.5 forbids naming that tree as a constant's source, and
    ``fitdocs.metrics.sources``'s own module docstring states plainly that
    every locator here was verified against the named work's own primary
    text, "never against any working document". Scans every ``.py`` file in
    the package, not only the three literal-scanned modules, so ``sources.py``,
    ``types.py``, ``zones.py`` and ``__init__.py`` are covered too."""
    package_dir = pathlib.Path(aggregates.__file__ or "").resolve().parent
    python_files = sorted(package_dir.glob("*.py"))
    assert python_files, "the walk found no .py files under the metrics package"
    assert package_dir.name == "metrics", (
        f"the walk is looking at the wrong directory -- resolved to "
        f"{package_dir} instead of a directory named 'metrics'"
    )
    expected_names = {
        "aggregates.py",
        "power.py",
        "stress.py",
        "sources.py",
        "types.py",
        "zones.py",
        "__init__.py",
    }
    found_names = {p.name for p in python_files}
    assert expected_names <= found_names, (
        f"the walk did not reach every known metrics module -- found only "
        f"{sorted(found_names)}, missing {sorted(expected_names - found_names)}"
    )
    for path in python_files:
        text = path.read_text(encoding="utf-8")
        assert "docs/reference" not in text, path.name

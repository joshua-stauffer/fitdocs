"""Tests for the published-work and fitdocs-choice citation records
(Amendment 1, tasks 9.1-9.4).

Covers Requirements 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.8, 15.9, 16.1, 16.2,
16.4, 16.5, 16.6, 16.7, 17.1, 17.2, 17.4 -- see
``.kiro/specs/fit-ingest/requirements.md`` and the "MetricsSources
(`src/fitdocs/metrics/sources.py`)" component in design.md. Every locator
assertion below was independently re-verified against the primary text it
names (the Banister (1991) page scans, the Morton et al. (1990) publisher
PDF, and Coggan's (2003) manuscript) rather than against design.md's table or
any working document -- see the implementer's status report for what was
opened and read.

This module tests the three :class:`~fitdocs.citation.Citation` records task
9.1 adds, the three :class:`~fitdocs.citation.FitdocsChoice` records task 9.2
adds -- three in all today; task 12.2 briefly added a fourth
(``POWER_ABSENT_SAMPLE_CHOICE``), which the 2026-07-30 absent-power-sample
ruling removed again once the resample grid's own leading-truncation fix
left it with no remaining fill value to govern (see ``sources.py``) -- the
ten :class:`~fitdocs.citation.CitedConstant` bindings and
``CONSTANT_SOURCES`` registry task 9.3 adds (under "CitedConstant bindings"),
and (under "Weighting resolver (task 9.4)" below) the ``WeightingPair`` type,
``WEIGHTING_PAIRS``, ``DEFAULT_TRIMP_WEIGHTING``, ``weighting_for`` and
``DEPARTURES`` task 9.4 adds.

**15.1's scope in this task.** 15.1 requires every constant to record
authors, year, work, locator and verification status -- 9.1 pins that shape,
and pins it fully, for the three published works themselves (the
``Citation`` records below). 9.1 does **not** itself pin any numeric
*value* -- it adds no ``CitedConstant`` to bind a value to a source, so
nothing in 9.1's own tests asserts, e.g., that fitdocs' own TRIMP exponent
equals 1.92. Task 9.3's ``CitedConstant`` bindings below (see "CitedConstant
bindings") now pin exactly that -- ``BANISTER_MALE_EXPONENT.value == 1.92``
among them. The *systematic* guard over every constant -- including the
two the module-sync tests below do not reach (the female curve's two
terms) -- is 12.1/12.2, which do not exist yet. The three module-sync
tests at the end of this file pin the other eight today: seven against
named constants in ``stress.py``, ``power.py`` and ``aggregates.py``
directly -- including, as of task 10.2, the NP averaging exponent against
``power._NP_AVERAGING_EXPONENT``, previously two inline literals
(``**4``/``**0.25``) with no module constant to compare against -- and the
moving-time threshold against ``aggregates._MOVING_SPEED_THRESHOLD_MPS`` --
task 10.1 promoted the former bare ``0.5`` to that module constant -- so all
eight now catch a drift in their respective module. The note-content
assertions below (curve text, step text, coefficient-absence text) pin what
the *record* claims the source text says, verified by this session's own
re-opening of the source -- not whether fitdocs' own arithmetic uses that
value correctly, which remains unpinned until 12.1/12.2 exist.

**9.2's scope.** The three ``FitdocsChoice`` records below (``NP_MIN_SPAN_
CHOICE``, ``MOVING_THRESHOLD_CHOICE``, ``ALTITUDE_WINDOW_CHOICE``) carry
``justification`` and ``search_basis`` prose in place of a published work's
authors/year/work/locator (15.8, 15.9, 16.7) -- prose whose falsification is
just as invisible to a substring check as the ``Citation`` notes above, so
the same whole-value equality backstop is applied to ``justification``,
``search_basis`` and ``measurement`` for each of the three records, plus
full equality on every other identity field (``key``, ``verification``).
This module does not itself assert that the fitdocs-choice classification is
correct for these three values (that no published work anywhere defines
them) -- it pins what the record *claims* was searched and found, which is
the only thing a test in this module can mechanically check.
"""

from __future__ import annotations

import ast
import dataclasses
import pathlib
import re
import subprocess
import sys
from typing import Final

import pytest

import fitdocs.metrics.sources as sources
from fitdocs import contract
from fitdocs.citation import (
    Agreement,
    Citation,
    CitedConstant,
    Departure,
    FitdocsChoice,
    VerificationStatus,
)
from fitdocs.metrics import power
from fitdocs.metrics.types import TrimpWeighting
from fitdocs.model import Samples

# Whole-note backstop pins (see the three ``test_*_note_matches_the_full_pinned_text``
# tests below). Each constant is the note's full text, copied from this session's own
# re-opening of the source and re-verified character-for-character against
# ``sources.py`` at review time -- not derived from the module under test, so a
# mutation to the module cannot silently drag its own backstop along with it.
BACKSTOP_BANISTER_1991_NOTE: Final[str] = (
    "The training-impulse weighting's governing source for both the coefficient "
    "and the exponent, for both sexes. Opened in this session at the chapter's "
    "own page scan (page footer reads '408'): under 'the following equations', "
    "the printed page states 'y = 0.64e^1.92x (male)' and 'y = 0.86e^1.67x "
    "(female)', both coefficient and exponent present together on this page for "
    "each sex. The same page defines 'e' as 'the Napierian logarithm having a "
    "value of 2.712' -- a misstatement of e (which is 2.71828...); that 2.712 "
    "figure is not recorded anywhere in this layer as a constant. The year, "
    "1991, is the one element on this record that rests on the OCLC / Internet "
    "Archive catalogue entry rather than on the book's own pages -- the chapter "
    "carries no copyright-page year itself."
)

BACKSTOP_MORTON_1990_NOTE: Final[str] = (
    "A corroborator of the training-impulse weighting's exponent, not a "
    "governing source -- Banister (1991) p. 408 governs both weighting terms. "
    "Opened in this session (publisher PDF, printed p. 1172): labeled equation "
    "(2) reads 'Y = e^bx', with the surrounding text giving 'b values for men "
    "(1.92) and women (1.67)'. No multiplicative coefficient appears anywhere "
    "in that equation or in the paragraph introducing it -- confirmed by "
    "reading the page, not merely its absence from a summary. This is why the "
    "coefficient's corroboration is OMITS while the exponent's is AGREES: the "
    "exponents (1.92, 1.67) match Banister (1991) p. 408 exactly; the "
    "coefficient this work simply does not state."
)

BACKSTOP_BANISTER_1991_WORK: Final[str] = (
    "Modeling Elite Athletic Performance, in: Physiological Testing of the "
    "High-Performance Athlete (2nd ed.), Human Kinetics"
)

BACKSTOP_MORTON_1990_WORK: Final[str] = (
    "Modeling human performance in running, Journal of Applied Physiology "
    "69(3):1171-1177"
)

BACKSTOP_COGGAN_2003_WORK: Final[str] = (
    "Training and racing using a power meter: an introduction (USA "
    "Cycling coaching-education chapter; the basis for, and later folded "
    'into, Allen & Coggan\'s "Training and Racing with a Power Meter")'
)

BACKSTOP_COGGAN_2003_LOCATOR: Final[str] = (
    '§3 "Analysis of power meter data" -> "Intensity factor '
    '(IF) and training stress score (TSS)", pp. 8-11 of the revised 25 '
    "March 2003 edition"
)

BACKSTOP_COGGAN_2003_NOTE: Final[str] = (
    "The governing source for the normalized-power rolling-window width, the "
    "normalized-power averaging exponent, and the training-stress-score scale "
    "-- the same work already shipping as COGGAN_TSS in "
    "fitdocs.load.channels.sources; this record reuses that identification "
    "rather than re-deriving it, since it is Coggan's own primary text rather "
    "than the Allen & Coggan book, which was never obtained. Opened in this "
    "session (printed pp. 8-11 of the revised 25 March 2003 edition): printed "
    "p. 8 carries the 'Intensity factor (IF) and training stress score (TSS)' "
    "heading and the TRIMPS equation 'TRIMPS = exercise duration x average HR "
    "x a HR-dependent intensity weighting factor'; printed p. 9 proposes TSS "
    "'by analogy' as 'TSS = exercise duration x average power x a "
    "power-dependent intensity weighting factor' and states the averaging "
    "exponent 'was rounded from 3.90 to 4.00 for simplicity's sake'; printed "
    "p. 10 lists the eight computation steps verbatim, including step 1 "
    "('starting at 30 s, calculate a 30 second rolling average for power' -- "
    "the rolling-window width), steps 2-4 ('raise the values obtained in step "
    "1 to the 4th power' / 'take the average of all the values obtained in "
    "step 2' / 'take the 4th root of the number obtained in step 3' -- the "
    'averaging exponent), and step 8 (\'divide the "raw" TSS by the amount of '
    "work that could be performed in one hour at threshold power ... and "
    "multiply by 100 to obtain the final TSS' -- the TSS scale, 100)."
)


def _normalized(text: str) -> str:
    """Collapse runs of whitespace to a single space, for the backstop
    comparisons below -- the module source wraps each note across many
    adjacent string literals, and this normalization must never do more than
    fold that wrapping back together. It must not, e.g., strip punctuation or
    case-fold, either of which could hide a falsification inside whitespace
    that looks identical either way."""
    return re.sub(r"\s+", " ", text).strip()


def test_module_does_not_import_the_fit_sdk_in_subprocess() -> None:
    """16.6 / the task's own observable: importing this module in a fresh
    interpreter reads records without needing the ``garmin-fit-sdk`` --
    reading a citation record requires no ingest machinery. (Importing
    ``fitdocs.metrics.sources`` necessarily first runs
    ``fitdocs.metrics.__init__``, which -- outside this task's boundary --
    already imports the arithmetic-bearing sibling modules; that parent
    package behavior is not this module's own doing and is not what this
    test pins.)"""
    code = (
        "import sys\n"
        "import fitdocs.metrics.sources\n"
        "assert 'garmin_fit_sdk' not in sys.modules, sorted(sys.modules)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_module_source_imports_only_fitdocs_citation_internally() -> None:
    """The only internal ``fitdocs`` imports the module source contains are
    the shared citation vocabulary and (as of task 9.4) the ``TrimpWeighting``
    selection vocabulary -- a static check alongside the subprocess check
    above, pinned to the source text rather than to whatever happens to
    already be imported by the test process. Absolute ``from fitdocs.x import
    y``, plain ``import fitdocs.x`` and *relative* ``from ..x import y``
    (resolved against this module's own package, ``fitdocs.metrics``) are all
    collected, so an upward import into ``fitdocs.load`` (a layer this module
    must never depend on) cannot slip past this guard merely by spelling it
    relatively -- a collector that only handled absolute ``ImportFrom`` would
    give ``node.module == "load.channels"`` for ``from ..load.channels import
    sources as _up``, which does not start with ``"fitdocs"`` and would
    silently pass. The subprocess check above cannot catch any of this
    either, since ``fitdocs.load.channels.sources`` pulls no SDK."""
    source_path = pathlib.Path(sources.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    own_package_parts = ["fitdocs", "metrics"]
    internal_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if (node.module or "").startswith("fitdocs"):
                    internal_imports.add(node.module or "")
            else:
                trim = len(own_package_parts) - (node.level - 1)
                base_parts = own_package_parts[:trim]
                extra = [node.module] if node.module else []
                resolved = ".".join(base_parts + extra)
                if resolved.startswith("fitdocs"):
                    internal_imports.add(resolved)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("fitdocs"):
                    internal_imports.add(alias.name)
    assert internal_imports == {"fitdocs.citation", "fitdocs.metrics.types"}, (
        internal_imports
    )


def test_module_holds_no_arithmetic() -> None:
    """The module holds no arithmetic (task 9.1's own observable, and
    design's "Holds no arithmetic" constraint) -- no ``ast.BinOp``,
    ``ast.AugAssign`` or ``ast.UnaryOp`` carrying an arithmetic operator
    anywhere in the source, and no call to a builtin that itself performs
    arithmetic over its arguments (``sum``, ``pow``, ``abs``, ``round``,
    ``divmod``, ``min``, ``max``) -- a bare operator check alone would miss
    ``_SCRATCH: Final[int] = sum((1, 2, 3))``, which computes an arithmetic
    reduction without any ``BinOp`` node at all. This is checked over the
    whole tree (not only top-level statements), so arithmetic nested inside
    an ``if`` or a call argument is caught too.

    This is a syntactic guard, not a semantic one: it cannot see arithmetic
    performed inside a function this module calls (e.g. a hypothetical
    third-party helper), only arithmetic spelled out in this module's own
    source as an operator or a call to one of the specific builtins above.
    """
    source_path = pathlib.Path(sources.__file__).resolve()
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    arithmetic_ops = (
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.FloorDiv,
        ast.Mod,
        ast.Pow,
        ast.MatMult,
    )
    unary_arithmetic_ops = (ast.UAdd, ast.USub)
    arithmetic_builtins = {"sum", "pow", "abs", "round", "divmod", "min", "max"}
    nodes = list(ast.walk(tree))
    assert nodes, "the walk collected nothing"
    for node in nodes:
        assert not (
            isinstance(node, ast.BinOp) and isinstance(node.op, arithmetic_ops)
        ), ast.dump(node)
        assert not (
            isinstance(node, ast.AugAssign) and isinstance(node.op, arithmetic_ops)
        ), ast.dump(node)
        assert not (
            isinstance(node, ast.UnaryOp) and isinstance(node.op, unary_arithmetic_ops)
        ), ast.dump(node)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in arithmetic_builtins
        ):
            raise AssertionError(ast.dump(node))


def test_exactly_three_citation_records_are_module_level_finals() -> None:
    """Task 9.1 adds exactly the three publishing-work records design.md's
    Service Interface names -- not more, not fewer (9.3's ten
    ``CitedConstant`` bindings and ``CONSTANT_SOURCES`` are counted
    separately below; 9.2's ``FitdocsChoice`` records are also counted
    separately and explicitly excluded from this count; 9.4's
    ``WeightingPair``/``WEIGHTING_PAIRS``/``weighting_for``/``DEPARTURES``
    now exist too and are covered in their own section below). Counted
    directly over the module's namespace (every module-level ``Citation``
    instance), so a fourth record added under a new name cannot slip past
    this guard the way a fixed list of forbidden future names can."""
    assert sources.BANISTER_1991.key == "banister_1991"
    assert sources.MORTON_1990.key == "morton_1990"
    assert sources.COGGAN_2003.key == "coggan_2003"
    from fitdocs.citation import Citation

    citation_instances = [
        value for value in vars(sources).values() if isinstance(value, Citation)
    ]
    assert len(citation_instances) == 3, citation_instances


def test_exactly_three_fitdocschoice_records_are_module_level_finals() -> None:
    """Task 9.2 adds exactly the three fitdocs-choice records design.md's
    Service Interface names under the 15.8 rows (``NP_MIN_SPAN_CHOICE``,
    ``MOVING_THRESHOLD_CHOICE``, ``ALTITUDE_WINDOW_CHOICE``) -- three in all,
    not more, not fewer. (Task 12.2 briefly added a fourth,
    ``POWER_ABSENT_SAMPLE_CHOICE``, for the power-resample absent-sample fill
    value that ``ConstantGuard``'s literal scan found could not honestly be
    classified as carrying no methodological choice; the 2026-07-30
    absent-power-sample ruling removed it again once the resample grid's own
    leading-truncation fix left no fill value for it to govern -- see
    ``sources.py``.) Counted directly over the module's namespace (every
    module-level ``FitdocsChoice`` instance) rather than via a fixed name
    list, for the same reason as the ``Citation`` count above: a fourth
    record under a new name cannot slip past a count."""
    choice_instances = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert len(choice_instances) == 3, choice_instances
    assert sources.NP_MIN_SPAN_CHOICE.key == "np_min_span_choice"
    assert sources.MOVING_THRESHOLD_CHOICE.key == "moving_threshold_choice"
    assert sources.ALTITUDE_WINDOW_CHOICE.key == "altitude_window_choice"


def test_all_three_records_carry_primary_text_verification() -> None:
    """15.4: none of the three constants a published work defines may be
    recorded as anything less than a value read from that work's own
    primary text -- no ``SECONDARY_ATTESTATION`` for any of the three."""
    for record in (sources.BANISTER_1991, sources.MORTON_1990, sources.COGGAN_2003):
        assert record.verification == VerificationStatus.PRIMARY_TEXT, record.key


def test_no_record_field_names_a_working_document_under_docs_reference() -> None:
    """15.5: no record, note, docstring or comment in this module names
    ``docs/reference/`` or any file under it as the source of a constant.
    Checked first across every string field (a locator or ``work`` field
    could carry it just as easily as ``note``), then over the whole module
    source text -- 15.5 says "no record, note or comment", and the module
    docstring itself is exactly the kind of place a stray reference could
    hide without any record-field check ever seeing it. The whole-source
    check also covers the bare filename (e.g. ``fitdocs-ai-reference.md``)
    without the ``docs/reference`` path prefix -- a reference laundered as
    "(per fitdocs-ai-reference.md)" names a working document just as much as
    the full path does, and the path-only check would not catch it.

    The ``FitdocsChoice`` half of this check below walks every module-level
    ``FitdocsChoice`` instance directly (task 12.2's remediation) rather than
    the fixed three-record tuple it used before -- the fixed tuple silently
    missed ``POWER_ABSENT_SAMPLE_CHOICE`` (task 12.2) when it was added
    outside ``CONSTANT_SOURCES``, so a fourth or fifth record added the same
    way cannot slip past this guard either."""
    for record in (sources.BANISTER_1991, sources.MORTON_1990, sources.COGGAN_2003):
        for field in ("authors", "work", "locator", "note"):
            value = getattr(record, field)
            if value is not None:
                assert "docs/reference" not in value, (record.key, field)
    choice_records = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert choice_records, "the walk found no fitdocs-choice records"
    for choice in choice_records:
        for field in ("justification", "search_basis", "measurement"):
            value = getattr(choice, field)
            if value is not None:
                assert "docs/reference" not in value, (choice.key, field)
    source_path = pathlib.Path(sources.__file__).resolve()
    module_text = source_path.read_text(encoding="utf-8")
    assert "docs/reference" not in module_text
    assert "fitdocs-ai-reference" not in module_text


def test_banister_1991_identifies_the_1991_chapter_at_page_408() -> None:
    """15.1, 16.1: authors, year, work and locator identify Banister's own
    chapter, at the page this session opened and read. ``authors``, ``year``
    and ``locator`` are pinned by full equality already; ``work`` is now
    pinned twice -- first by full equality against
    :data:`BACKSTOP_BANISTER_1991_WORK` (closing the whole field, the way
    ``locator`` already was), then by the three independent substrings kept
    below as a diagnostic, so a red equality pin still names which clause of
    ``work`` moved without the reader eyeballing a string diff. A check on
    the book title and edition/publisher alone would survive dropping
    "Modeling Elite Athletic Performance", leaving the record identifying
    the book rather than Banister's own chapter."""
    record = sources.BANISTER_1991
    assert record.authors == "Banister, E.W."
    assert record.year == 1991
    assert record.work == BACKSTOP_BANISTER_1991_WORK
    assert "Modeling Elite Athletic Performance" in record.work
    assert "Physiological Testing of the High-Performance Athlete" in record.work
    assert "(2nd ed.), Human Kinetics" in record.work
    assert record.locator == "p. 408"


def test_banister_1991_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (deliberate exact-match pin). Every targeted
    assertion below this one in the module pins a clause or a quoted
    substring; none of them, individually or together, bounds the space of
    single-word or single-number substitutions elsewhere in the note. This
    test closes that space by requiring the *entire* note to equal a
    character-for-character copy of the text this session read from
    Banister's own p. 408 (whitespace-normalized only to absorb how the
    module source wraps the string across adjacent literals -- no other
    normalization is applied, so no substitution of one word or number for
    another can hide inside it). It is deliberately brittle: any change to
    this provenance record other than whitespace re-wrapping must fail this
    test and force a human to read the diff, because the record makes a claim about a
    copyrighted primary text that no other mechanism here verifies word for
    word. This does not, by itself, verify that the note is *true* -- only
    that it has not silently drifted from the text an earlier session
    confirmed was true; truth rests on a human (or a future session) actually
    reading Banister's p. 408 again.

    The targeted assertions elsewhere in this module are not redundant with
    this one: when this backstop reds, they tell the reader *which* claim
    moved, without having to eyeball a large text diff."""
    note = sources.BANISTER_1991.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_BANISTER_1991_NOTE)


def test_banister_1991_note_flags_the_year_as_catalogue_sourced() -> None:
    """design.md: 'BANISTER_1991.year is the one non-primary element' -- the
    book's copyright page carries no year, so the note must say so rather
    than presenting 1991 as read from the chapter's own pages. Pinned to the
    two clauses that carry the meaning, not to tokens present under both the
    true and a factually inverted version of the claim: "catalogue" and
    "copyright" alone would both survive rewriting the note to claim the
    chapter's own copyright page prints 1991 -- a claim the copyright-page
    scan this session opened disproves (it carries a printing line and
    addresses, no year)."""
    note = sources.BANISTER_1991.note or ""
    assert "catalogue entry rather than on the book's own pages" in note
    assert "carries no copyright-page year" in note


def test_banister_1991_note_states_it_governs_both_terms_for_both_sexes() -> None:
    """The record's governance claim -- Banister (1991) p. 408 is the
    *governing* source for both the coefficient and the exponent, for both
    sexes -- was previously unasserted anywhere in this module. Without a
    pin here, inverting the claim ("not a governing source ... corroborated
    elsewhere") left every other assertion in this module green: the curve
    text, the footer text and the 2.712 trap are all unaffected by whether
    the opening sentence frames Banister as governing or merely
    corroborating."""
    note = sources.BANISTER_1991.note or ""
    assert (
        "governing source for both the coefficient and the exponent, for "
        "both sexes" in note
    )


def test_banister_1991_note_states_both_curves_confirmed_on_the_cited_page() -> None:
    """Independent re-verification, not transcription: the note must record
    what was actually read on p. 408 -- both fitted curves, coefficient and
    exponent together, each pinned to its own sex -- not merely assert the
    page number, and not merely assert that both coefficients and both sex
    labels appear somewhere in the note. Each assertion requires the full
    "coefficient e^exponent (sex)" string together, so swapping which
    coefficient goes with which sex (e.g. attributing 0.86 to "male") fails
    this test even though every individual token -- "0.64e", "male",
    "0.86e", "female" -- would still be present in the note."""
    note = sources.BANISTER_1991.note or ""
    assert "0.64e^1.92x (male)" in note
    assert "0.86e^1.67x (female)" in note


def test_banister_1991_note_states_the_page_footer_read() -> None:
    """The note claims a specific page-footer reading ('408') as part of
    identifying which physical page was opened and read -- distinct from
    ``locator``, which is the citation's own structured page field. Without
    this assertion, a note that silently retargeted the footer claim to a
    different page number (while ``locator`` still read "p. 408") would
    ship green: nothing else in this module checks the footer text itself."""
    note = sources.BANISTER_1991.note or ""
    assert "page footer reads '408'" in note


def test_banister_1991_note_does_not_launder_the_misstated_e_as_a_constant() -> None:
    """The B91-misstates-e trap: the page defines 'e' as 2.712 (a
    misstatement of the true value, 2.71828...), and the note must say so
    plainly and state that fitdocs does not record that 2.712 figure as a
    constant. The bare disjunct ``"2.712" not in note or "not recorded" in
    note.lower()`` is satisfied by any occurrence of "not recorded"
    anywhere in the note, whether or not it is actually bound to 2.712 --
    it would equally pass a note claiming the page prints 2.71828
    correctly (no 2.712 at all, so the left disjunct alone is true) or a
    note that disclaims some *other* number as "not recorded" while
    quietly turning 2.712 into a real constant. Pinning the full quoted
    definition and the full disclaiming sentence -- both anchored to
    "2.712" itself -- closes both gaps."""
    note = sources.BANISTER_1991.note or ""
    assert "the Napierian logarithm having a value of 2.712" in note
    assert "a misstatement of e (which is 2.71828" in note
    assert (
        "that 2.712 figure is not recorded anywhere in this layer as a constant" in note
    )


def test_morton_1990_identifies_the_1990_paper_at_equation_2_page_1172() -> None:
    """15.1, 16.1: authors, year, work and locator identify Morton's own
    paper. ``authors``, ``year`` and ``locator`` are pinned by full equality
    already; ``work`` is now pinned twice -- first by full equality against
    :data:`BACKSTOP_MORTON_1990_WORK` (closing the whole field, the way
    ``locator`` already was), then by the three independent substrings kept
    below as a diagnostic, so a red equality pin still names which clause of
    ``work`` moved. A mutation retitling the paper (while leaving the
    journal citation intact) cannot slip past either check."""
    record = sources.MORTON_1990
    assert record.authors == "Morton, R.H., Fitz-Clarke, J.R., Banister, E.W."
    assert record.year == 1990
    assert record.work == BACKSTOP_MORTON_1990_WORK
    assert "Modeling human performance in running" in record.work
    assert "Journal of Applied Physiology" in record.work
    assert "69(3):1171-1177" in record.work
    assert record.locator == "Eq. 2, p. 1172"


def test_morton_1990_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (deliberate exact-match pin), same rationale as
    :func:`test_banister_1991_note_matches_the_full_pinned_text`: the
    targeted assertions below pin clauses and quoted substrings, but the
    space of possible single-word or single-number substitutions elsewhere in
    the note is not bounded by any of them individually. Requiring the
    *entire* note to equal a character-for-character copy of the text this
    session read from Morton's own Eq. 2, p. 1172 closes that space -- e.g.
    it catches swapping which corroboration verdict (AGREES / OMITS) attaches
    to which term, a swap none of the targeted assertions below would catch
    on its own. Whitespace-normalized only to absorb the module source's line
    wrapping; no other normalization is applied. Brittleness is deliberate,
    for the same reason given on the Banister backstop: this is a claim about
    a copyrighted primary text, not fitdocs' own arithmetic, so no character
    of it should be able to change without a human reading the diff. This
    does not itself verify the note is true, only that it has not drifted."""
    note = sources.MORTON_1990.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_MORTON_1990_NOTE)


def test_morton_1990_note_confirms_the_coefficient_is_absent() -> None:
    """The corroboration-omission trap: the note must state that the
    coefficient's *absence* was confirmed by reading the equation and its
    surrounding text, not merely that Morton's paper is not being quoted for
    it. Pinned to the exact phrase rather than a weaker disjunction, so a
    mutation that keeps some coefficient-adjacent words but drops the
    absence claim itself is caught."""
    note = sources.MORTON_1990.note or ""
    assert "no multiplicative coefficient" in note.lower()
    assert "1.92" in note
    assert "1.67" in note


def test_morton_1990_note_binds_each_value_to_its_own_sex() -> None:
    """ "1.92" and "1.67" each appear twice in the note -- once in the
    quotation attributed to the paper's own text, once in the summary
    sentence comparing the exponents to Banister (1991) p. 408. A bare
    substring check on either number is satisfied by the summary occurrence
    alone regardless of what the quotation says, so a sex swap, a
    fabricated pair of values, or a single-token falsification inside the
    quotation would all still leave "1.92" and "1.67" present somewhere in
    the note. Pinning the full quoted phrase -- both values bound to their
    sexes together -- closes that gap."""
    note = sources.MORTON_1990.note or ""
    assert "b values for men (1.92) and women (1.67)" in note


def test_morton_1990_note_quotes_equation_2_without_a_coefficient() -> None:
    """The equation-2 quotation itself must read as a bare exponential with
    no multiplicative coefficient -- this is the primary-text evidence the
    rest of the note's coefficient-absence claim rests on. Pinning the
    quoted form directly means it cannot be silently rewritten to include
    the coefficient ("Y = A x e^bx") while the surrounding prose still
    claims none is present."""
    note = sources.MORTON_1990.note or ""
    assert "equation (2) reads 'Y = e^bx'" in note


def test_morton_1990_note_states_the_exponents_match_banister_exactly() -> None:
    """The record's whole reason for existing as a corroborator (Req 15.2)
    is this cross-work agreement claim -- Morton's exponents *match*
    Banister (1991) p. 408 exactly, which is what makes the exponent's
    corroboration status AGREES rather than OMITS or CONTRADICTS. Without
    this pin, negating the claim ("do not match Banister (1991) p. 408")
    left every other assertion in this module green: the sex-bound
    quotation and the coefficient-absence text are both unaffected by
    whether the note then claims the values agree or disagree."""
    note = sources.MORTON_1990.note or ""
    assert "the exponents (1.92, 1.67) match Banister (1991) p. 408 exactly" in note


def test_morton_1990_note_states_it_governs_nothing() -> None:
    """design.md: Morton is a corroborator only. The note must not present
    Morton as a governing source for either weighting term. Pinned to the
    exact "not a governing source" phrase rather than the weaker
    "corroborat" disjunct -- that bare stem survives elsewhere in the note
    (e.g. "corroborator of the training-impulse weighting's exponent") even
    after the "not a governing source" framing is deleted entirely, so a
    disjunction admitting it would not actually pin the framing."""
    note = sources.MORTON_1990.note or ""
    assert "not a governing source" in note.lower()


def test_coggan_2003_identifies_the_same_work_as_the_load_channel_citation() -> None:
    """15.1, 16.1: authors, year, work and locator identify the same Coggan
    (2003) manuscript already shipping as ``COGGAN_TSS`` in
    ``fitdocs.load.channels.sources``. ``authors`` and ``year`` are pinned
    by full equality. ``work`` and ``locator`` were previously pinned only
    by substrings ("in" checks), unlike Banister's and Morton's fully
    equality-pinned ``locator`` fields -- an asymmetry that left, e.g., the
    section/subsection titles and the "Analysis of power meter data" /
    "Interpretation of heart rate data" wording, and the "coaching-education
    chapter" / "peer-reviewed journal article" kind-of-publication wording,
    unfalsifiable. Both fields are now pinned twice -- first by full
    equality against :data:`BACKSTOP_COGGAN_2003_WORK` and
    :data:`BACKSTOP_COGGAN_2003_LOCATOR` (closing the whole field), then by
    the substrings kept below as a diagnostic, so a red equality pin still
    names which clause moved. After this change, every one of ``Citation``'s
    six fields (``key``, ``authors``, ``year``, ``work``, ``locator``,
    ``verification``) is pinned by full equality somewhere in this module
    for all three records (``note`` by the whole-note backstops above), so
    there is nothing left on a ``Citation`` record that only a substring
    check bounds."""
    record = sources.COGGAN_2003
    assert record.authors == "Coggan, A.R."
    assert record.year == 2003
    assert record.work == BACKSTOP_COGGAN_2003_WORK
    assert record.locator == BACKSTOP_COGGAN_2003_LOCATOR
    assert "Training and racing using a power meter: an introduction" in record.work
    assert "USA Cycling" in record.work
    assert record.locator is not None and "pp. 8-11" in record.locator
    assert (
        record.locator is not None and "revised 25 March 2003 edition" in record.locator
    )


def test_coggan_2003_note_matches_the_full_pinned_text() -> None:
    """Whole-note backstop (deliberate exact-match pin), same rationale as
    :func:`test_banister_1991_note_matches_the_full_pinned_text`. This is the
    longest and densest of the three notes, and the targeted assertions
    below it individually pin only clauses or quoted substrings -- several of
    them bare tokens ("4th power", "4th root", "multiply by 100") that are
    prefixes of a falsified reading rather than the whole word ("14th power",
    "24th root", "multiply by 1000") and so do not, on their own, discriminate
    that falsification; a substring check reds on "100 -> 95" but not on
    "100 -> 1000", because "100" remains a substring of "1000". Requiring the
    *entire* note to equal a character-for-character copy of the text this
    session read from Coggan's own pp. 8-11 closes that gap along with every
    other single-word or single-number substitution the targeted assertions
    do not individually bound -- including relocating a quoted equation to
    the wrong printed page, since the targeted page-attribution assertions
    below pin the page-number clause and the claim clause as separate
    substrings rather than requiring them adjacent. Whitespace-normalized
    only to absorb the module source's line wrapping; no other normalization
    is applied. Brittleness is deliberate, for the same reason given on the
    Banister backstop: this is a claim about a copyrighted primary text, not
    fitdocs' own arithmetic, so no character of it should be able to change
    without a human reading the diff. This does not itself verify the note is
    true, only that it has not drifted."""
    note = sources.COGGAN_2003.note or ""
    assert _normalized(note) == _normalized(BACKSTOP_COGGAN_2003_NOTE)


def test_coggan_2003_note_confirms_rolling_window_averaging_exponent_and_scale() -> (
    None
):
    """15.1: the record must confirm, from the text itself, the three
    distinct constants this work governs -- the rolling-window width (30 s),
    the averaging exponent (4th power / 4th root), and the TSS scale (100)
    -- not merely restate the design's classification table. The
    rolling-window assertion is pinned to the full quoted phrase; the
    averaging-exponent and TSS-scale assertions below are bare substrings
    ("4th power", "4th root", "multiply by 100") and are not, on their own,
    fully discriminating -- "4th power" also matches inside "14th power" and
    "multiply by 100" also matches inside "multiply by 1000", so a
    prefix-preserving falsification of either can ship green against this
    test alone. The whole-note backstop
    (:func:`test_coggan_2003_note_matches_the_full_pinned_text`) is what
    actually closes that gap; this test remains useful as a diagnostic that
    names which of the three constants moved when the backstop reds."""
    note = sources.COGGAN_2003.note or ""
    assert "starting at 30 s, calculate a 30 second rolling average for power" in note
    assert "4th power" in note
    assert "4th root" in note
    assert "multiply by 100" in note


def test_coggan_2003_note_states_it_is_the_governing_source() -> None:
    """The record's own governance claim -- Coggan (2003) *governs* all
    three constants (rolling-window width, averaging exponent, TSS scale),
    not merely corroborates them -- was previously unasserted anywhere in
    this module. Inverting the opening sentence to "not a governing
    source ... merely a corroborator" left every other assertion in this
    module green, since the quoted step text and numbers later in the note
    are unaffected by that framing sentence."""
    note = sources.COGGAN_2003.note or ""
    assert "The governing source for the normalized-power rolling-window" in note


def test_coggan_2003_note_quotes_the_trimps_equation_and_its_tss_analogy() -> None:
    """The note's governance claim rests on two quoted equations -- the
    HR-based TRIMPS formula p. 8 actually prints, and the power-based TSS
    formula p. 9 proposes "by analogy" to it. Neither equation's own text
    was previously asserted, so a mutation swapping "average HR" for
    "average power" inside the TRIMPS quotation (misattributing the
    power-based formula to p. 8) shipped green. Pinning both quotations by
    their full text closes that."""
    note = sources.COGGAN_2003.note or ""
    assert (
        "'TRIMPS = exercise duration x average HR x a HR-dependent intensity "
        "weighting factor'" in note
    )
    assert (
        "'TSS = exercise duration x average power x a power-dependent "
        "intensity weighting factor'" in note
    )


def test_coggan_2003_note_states_the_averaging_exponent_was_rounded_from_3_90() -> None:
    """The averaging exponent's rounding -- from 3.90, not some other
    figure, to 4.00 -- was previously unasserted; only the resulting "4th
    power" / "4th root" steps were pinned. A mutation changing "rounded
    from 3.90 to 4.00" to "rounded from 4.20 to 4.00" left every existing
    assertion in this module green, since the 4th-power/4th-root step text
    is unaffected by what the note claims the rounding started from."""
    note = sources.COGGAN_2003.note or ""
    assert "rounded from 3.90 to 4.00 for simplicity's sake" in note


def test_coggan_2003_note_attributes_each_claim_to_its_own_printed_page() -> None:
    """The steps and formulas the note quotes are attributed to the printed
    page each one actually appears on -- the TRIMPS analogy and TSS formula
    are on printed p. 9 (not p. 8, which carries only the section heading
    and the HR-based TRIMPS equation), and the eight computation steps are on
    printed p. 10. Each assertion below pins a page-number clause as its own
    substring, independent of the claim it introduces -- it does not require
    the page number and the claim to be adjacent in the note, so a mutation
    that relocates, e.g., the TRIMPS equation to printed p. 11 while leaving
    all three page-number clauses and all three claim clauses individually
    present ships green against this test. The whole-note backstop
    (:func:`test_coggan_2003_note_matches_the_full_pinned_text`) is what
    actually catches that relocation; this test remains useful as a
    diagnostic that names which page attribution moved when the backstop
    reds."""
    note = sources.COGGAN_2003.note or ""
    assert "printed p. 8 carries the 'Intensity factor (IF) and training " in note
    assert "printed p. 9 proposes TSS 'by analogy'" in note
    assert "printed p. 10 lists the eight computation steps" in note


def test_coggan_2003_note_reuses_coggan_tss_by_symbol_not_by_stale_line_number() -> (
    None
):
    """The note identifies the same work already shipping as ``COGGAN_TSS``
    in ``fitdocs.load.channels.sources`` by module path and symbol name, not
    by a line number -- a line number inside a citation note goes stale on
    every edit above it in that file (this is what happened before this
    fix: the note named line 137, which had drifted to line 122)."""
    note = sources.COGGAN_2003.note or ""
    assert "fitdocs.load.channels.sources" in note
    assert "COGGAN_TSS" in note
    assert ".py:" not in note


def test_all_three_keys_are_distinct() -> None:
    keys = {sources.BANISTER_1991.key, sources.MORTON_1990.key, sources.COGGAN_2003.key}
    assert len(keys) == 3


# --- FitdocsChoice records (task 9.2; Req 15.8, 15.9, 16.4, 16.7) -----------

# Whole-value backstop pins, same rationale as the ``Citation`` backstops
# above: each constant is the record's full text, copied from ``sources.py``
# and re-verified character-for-character against it at review time -- not
# derived from the module under test, so a mutation to the module cannot
# silently drag its own backstop along with it.
BACKSTOP_NP_MIN_SPAN_JUSTIFICATION: Final[str] = (
    "The minimum span is set equal to the width of the rolling-mean window "
    "Coggan (2003) itself specifies (30 s; COGGAN_2003 governs that width, "
    "not this record) -- but that window is 30 *samples* wide, and at "
    "this module's 1 Hz resample a 30-sample window spans only 29 s of "
    "elapsed offset (samples at offset 0 s through offset 29 s), not 30 "
    "s. A 29.0 s power-stream span already resamples to 30 one-second "
    "points and so already yields one complete windowed value from the "
    "cited procedure's own rolling-mean step (step 1); 29.0 s, not 30.0 "
    "s, is the smallest span for which that step produces even a single "
    "complete value. This record nonetheless sets the threshold at 30.0 "
    "s -- one second above that smallest span -- because the threshold "
    "is stated in the same units the cited text itself uses for the "
    "window (seconds: '30 s' / '30 second', COGGAN_2003 step 1), rather "
    "than as a figure derived from this module's own sampling grid; "
    "reading the minimum span directly off the window width Coggan's "
    "text states, in the units that text states it, is the choice this "
    "record makes and states over the samples-vs-seconds arithmetic "
    "instead. No measurement was taken to arrive at 30.0 s; it is read "
    "directly off the window width Coggan's own text fixes elsewhere in "
    "this layer, in the seconds that text uses to state it."
)

BACKSTOP_NP_MIN_SPAN_SEARCH_BASIS: Final[str] = (
    "This session has no live literature-search tool available, so the "
    "search was a review of the three primary texts already obtained for "
    "this layer -- Banister (1991) p. 408, Morton (1990) Eq. 2 p. 1172, "
    "and Coggan (2003) pp. 8-11, all re-opened and quoted above at "
    "BANISTER_1991, MORTON_1990 and COGGAN_2003 -- for any stated minimum "
    "power-stream duration below which the procedure should be withheld. "
    "Coggan's own eight steps define the rolling-window width, the "
    "averaging exponent and the final scale but never state a minimum "
    "span; Banister's and Morton's texts concern the heart-rate-based "
    "training-impulse weighting only and do not address a power stream at "
    "all. The Allen & Coggan book this manuscript was folded into was "
    "never obtained (noted already on COGGAN_2003) and is not treated "
    "here as a substitute search target. No published work located in "
    "this review states a minimum span; the figure recorded here is "
    "derived from the window width these same texts do govern, not read "
    "from an independent published minimum."
)

BACKSTOP_MOVING_THRESHOLD_JUSTIFICATION: Final[str] = (
    "0.5 m/s is a value fitdocs inherits from fitdocs.ai, the reference "
    "application this project's parsing pipeline and metric formulas "
    "otherwise borrow directly (see aggregates.py); fitdocs took no "
    "measurement of its own to arrive at it, and states here its own "
    "reasoning for retaining the inherited value rather than presenting "
    "the number as originated in this layer. It is a slow-walking-pace "
    "floor below which a single instantaneous speed sample cannot be "
    "reliably distinguished from GPS noise at a "
    "standstill; treating a sample above it (or a cumulative-distance "
    "increase across the pair, for a speed-less channel) as 'moving' "
    "keeps brief stationary noise from being counted as movement without "
    "also discarding genuine slow walking. That reasoning is why fitdocs "
    "keeps the inherited value rather than replacing it: it is a "
    "judgment call about where that noise floor sits, not a value either "
    "fitdocs.ai or this layer read off measured data."
)

BACKSTOP_MOVING_THRESHOLD_SEARCH_BASIS: Final[str] = (
    "A web literature search was run for a published GPS- or "
    "accelerometry-based moving/stopped speed threshold, using the "
    "queries 'GPS moving time speed threshold stationary detection "
    "published method m/s fitness tracking', '\"moving time\" algorithm "
    'speed threshold "0.5 m/s" OR "1 m/s" cycling running published '
    "standard', and 'accelerometry GPS speed cut-point classifying "
    "stationary versus ambulatory sports science threshold m/s "
    "validation'. The physical-activity/accelerometry cut-point "
    "literature defines intensity cut-points and walking-speed bands, "
    "not a moving/stopped floor for workout timing: a post-stroke ROC "
    "study sets ambulation bands of 0.41-0.8, 0.81-1.2 and >1.2 m/s; a "
    "chest-patch validation gives a sedentary-vs-ambulatory Mean "
    "Amplitude Deviation cut-point of 47.73 mG, an acceleration "
    "magnitude rather than a speed. GPS-based activity classification "
    "(the Personal Activity Location Measurement System) defines "
    "stationary time as under 25 m of displacement in a minute, a "
    "distance-over-interval rule rather than a per-sample speed "
    "comparison. Patent literature sets a moving-speed threshold near "
    "7.0 km/h (~1.94 m/s) for detecting running specifically, and "
    "elsewhere detects movement by consecutive GPS fixes over 5 m apart "
    "across 5 s; neither is a general moving-time floor, and both sit "
    "two to four times above 0.5 m/s. Consumer "
    "platforms (Strava's help centre, and similarly Garmin and "
    "TrainingPeaks) document that moving time uses a speed threshold "
    "without publishing the threshold or algorithm -- an unpublished "
    "implementation detail in a commercial product is not a published "
    "work under criterion 15.1, so none of them was treated as a "
    "candidate governing source. The value 0.5 m/s itself is inherited "
    "from fitdocs.ai, the reference application this project borrows its "
    "parsing pipeline and metric formulas from (see aggregates.py); "
    "fitdocs.ai is an application whose source this project read (linked "
    "from README.md), not a published work under criterion 15.1, so it is "
    "not treated as a citable source here either -- fitdocs states its "
    "own reasoning above for retaining the inherited value rather than "
    "crediting fitdocs.ai as the value's origin. No published work "
    "defining a per-sample moving/stopped speed threshold was located in "
    "this search. This was a web literature search, not an exhaustive "
    "survey of the sports-science and geodesy literature -- it did not "
    "reach paywalled full texts beyond abstracts and open-access "
    "articles, so it establishes that no such work is readily locatable, "
    "not that none exists."
)

BACKSTOP_ALTITUDE_WINDOW_JUSTIFICATION: Final[str] = (
    "10 is a value fitdocs inherits from fitdocs.ai, the reference "
    "application this project's parsing pipeline and metric formulas "
    "otherwise borrow directly (see aggregates.py); fitdocs took no "
    "measurement of its own to arrive at it, and states here its own "
    "reasoning for retaining the inherited value rather than presenting "
    "the number as originated in this layer. A 10-sample trailing boxcar "
    "is wide enough to average out single-sample altimeter or barometric "
    "jitter before differencing for elevation gain and loss, while "
    "staying short enough, relative to a real sustained climb spanning "
    "many samples, that the climb itself is not smoothed away. That "
    "reasoning is why fitdocs keeps the inherited value rather than "
    "replacing it: it is a judgment call trading jitter suppression "
    "against climb fidelity, not a value either fitdocs.ai or this layer "
    "read off measured altitude data."
)

BACKSTOP_ALTITUDE_WINDOW_SEARCH_BASIS: Final[str] = (
    "A web literature search was run for a published altitude-smoothing "
    "window width, using the queries 'barometric altimetry filtering "
    "elevation gain computation moving average window samples validation "
    "study' and 'elevation gain calculation barometric altimeter "
    "smoothing window size algorithm published threshold'. The "
    "barometric-altimetry filtering literature characterises altimeter "
    "noise (Allan-variance style) and recommends simple exponential "
    "recursive filters rather than a fixed-width boxcar; window widths "
    "that do appear are incidental to other purposes and disagree with "
    "one another and with 10 -- a 21-point median/moving-average in one "
    "patent's filter chain, a 4-point moving average used before ARMA "
    "identification. Elevation-gain computation as shipped by a consumer "
    "platform (Strava) instead publishes an amplitude threshold -- a "
    "climb must be sustained over roughly 2 m (barometric) or 10 m "
    "(non-barometric) before it counts -- a different mechanism "
    "(thresholding accumulated amplitude) from smoothing the altitude "
    "series before differencing, not a window width. Patents describe "
    "smoothing/threshold schemes for altitude without fixing a "
    "sample-count window; several fuse barometric with GPS altitude, "
    "which fitdocs does not do. The value 10 itself is inherited from "
    "fitdocs.ai, the reference application this project borrows its "
    "parsing pipeline and metric formulas from (see aggregates.py); "
    "fitdocs.ai is an application whose source this project read (linked "
    "from README.md), not a published work under criterion 15.1, so it is "
    "not treated as a citable source here either -- fitdocs states its "
    "own reasoning above for retaining the inherited value rather than "
    "crediting fitdocs.ai as the value's origin. No published work "
    "defining an altitude-smoothing window width was located in this "
    "search. This was a web literature search, not an exhaustive survey "
    "of the barometric-altimetry and geodesy literature -- it did not "
    "reach paywalled full texts beyond abstracts and open-access "
    "articles, so it establishes that no such work is readily locatable, "
    "not that none exists."
)

# BACKSTOP_POWER_ABSENT_SAMPLE_JUSTIFICATION / _SEARCH_BASIS and their two
# whole-value pin tests are REMOVED (chore/power-absent-sample-fill,
# 2026-07-30 ruling), along with ``POWER_ABSENT_SAMPLE_CHOICE`` /
# ``POWER_ABSENT_SAMPLE_FILL`` themselves in ``sources.py`` -- the resample
# grid's leading-truncation fix left no fill value for that record to
# govern, so there is no longer a record here to pin a backstop against.


def test_all_fitdocschoice_records_carry_fitdocs_measured_verification() -> None:
    """16.4: none of the constants no published work defines may be recorded
    as anything other than ``FITDOCS_MEASURED`` -- in particular never
    ``PRIMARY_TEXT``, which would misrepresent a fitdocs choice as read from
    a published work's own text. The dataclass field is typed
    ``Literal[VerificationStatus.FITDOCS_MEASURED]`` (a static guard), but
    this asserts the runtime value directly too, since a runtime
    construction can still pass an explicit ``verification=`` kwarg past
    the type checker's back (e.g. under ``# type: ignore``). Derived over
    every module-level ``FitdocsChoice`` instance (``vars(sources)``)
    rather than a fixed three-name tuple: round 4 found the fixed tuple
    already missed ``POWER_ABSENT_SAMPLE_CHOICE`` (added by this same task),
    so a walk is what closes the class for a fifth record too."""
    choices = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert choices, "the walk found no fitdocs-choice records"
    for record in choices:
        assert record.verification == VerificationStatus.FITDOCS_MEASURED, record.key


def test_all_fitdocschoice_records_carry_no_measurement() -> None:
    """15.8: a fitdocs choice records a measurement only where the choice
    rests on one. None of these choices rests on a measurement taken in
    this session (each ``justification`` says so explicitly, pinned by the
    whole-value backstops above/below), so ``measurement`` must be ``None``
    on all of them rather than a fabricated supporting figure. Derived over
    every module-level ``FitdocsChoice`` instance, same rationale as the
    verification walk above -- a fixed tuple already went stale once."""
    choices = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert choices, "the walk found no fitdocs-choice records"
    for record in choices:
        assert record.measurement is None, record.key


def test_np_min_span_choice_justification_matches_the_full_pinned_text() -> None:
    """Whole-value backstop (deliberate exact-match pin), same rationale as
    the ``Citation`` note backstops above: the free-text ``justification``
    on a ``FitdocsChoice`` is just as falsifiable one substring at a time,
    and no targeted assertion below bounds that space on its own. Requiring
    the *entire* field to equal a character-for-character copy closes it --
    e.g. it catches silently changing "read directly off the window width"
    to a claim that a measurement was in fact taken, which no other
    assertion in this module would catch."""
    assert (
        sources.NP_MIN_SPAN_CHOICE.justification == BACKSTOP_NP_MIN_SPAN_JUSTIFICATION
    )


def test_np_min_span_choice_search_basis_matches_the_full_pinned_text() -> None:
    """Whole-value backstop on ``search_basis`` (Req 15.9's own field): this
    is the text distinguishing "no published work defines this" (a search
    performed and reported) from "the paper could not be obtained" (which
    Req 15.4/15.9 would instead require to block). A substring check on
    any one clause cannot bound a silent rewrite that, e.g., claims
    Coggan's text *does* state a minimum span, or claims a literature
    search tool was available and used when none was."""
    assert sources.NP_MIN_SPAN_CHOICE.search_basis == BACKSTOP_NP_MIN_SPAN_SEARCH_BASIS


def test_np_min_span_choice_justification_derives_the_value_from_the_cited_window() -> (
    None
):
    """Targeted diagnostic beneath the whole-value backstop above: the
    justification must state the derivation (minimum span == the cited
    rolling-window width) rather than merely asserting a bare number, so a
    reader can tell the 30 s figure is not an independent guess."""
    text = sources.NP_MIN_SPAN_CHOICE.justification
    assert "equal to the width of the rolling-mean window" in text
    assert "(30 s; COGGAN_2003" in text


def test_moving_threshold_choice_justification_matches_the_full_pinned_text() -> None:
    """Whole-value backstop on ``justification``, same rationale as above."""
    assert (
        sources.MOVING_THRESHOLD_CHOICE.justification
        == BACKSTOP_MOVING_THRESHOLD_JUSTIFICATION
    )


def test_moving_threshold_choice_search_basis_matches_the_full_pinned_text() -> None:
    """Whole-value backstop on ``search_basis``, same rationale as above."""
    assert (
        sources.MOVING_THRESHOLD_CHOICE.search_basis
        == BACKSTOP_MOVING_THRESHOLD_SEARCH_BASIS
    )


def test_moving_threshold_does_not_treat_a_platform_convention_as_published() -> None:
    """Targeted diagnostic: the record must say explicitly that an
    unpublished commercial-platform heuristic is not a published work
    under 15.1 -- without this, a rewrite claiming a specific fitness
    platform's internal threshold as this value's *governing published
    source* would still read as "searched", passing 15.9 in letter while
    smuggling an unverifiable secondary attestation past 15.4 in
    substance."""
    text = sources.MOVING_THRESHOLD_CHOICE.search_basis
    assert (
        "in a commercial product is not a published work under criterion 15.1" in text
    )


def test_altitude_window_choice_justification_matches_the_full_pinned_text() -> None:
    """Whole-value backstop on ``justification``, same rationale as above."""
    assert (
        sources.ALTITUDE_WINDOW_CHOICE.justification
        == BACKSTOP_ALTITUDE_WINDOW_JUSTIFICATION
    )


def test_altitude_window_choice_search_basis_matches_the_full_pinned_text() -> None:
    """Whole-value backstop on ``search_basis``, same rationale as above."""
    assert (
        sources.ALTITUDE_WINDOW_CHOICE.search_basis
        == BACKSTOP_ALTITUDE_WINDOW_SEARCH_BASIS
    )


def test_np_min_span_choice_search_basis_states_no_search_tool_was_available() -> None:
    """Honesty check (Req 15.9): ``NP_MIN_SPAN_CHOICE.search_basis`` must
    say plainly that no live literature-search tool was available when it
    was written, rather than narrating a literature search that did not
    happen. Unlike ``MOVING_THRESHOLD_CHOICE`` and ``ALTITUDE_WINDOW_CHOICE``
    (remediated later with a real web-search tool -- see the tests below),
    this one's search basis is unchanged from task 9.2 and still rests on
    re-reading the three primary texts already in hand. (Task 12.2's
    now-removed ``POWER_ABSENT_SAMPLE_CHOICE`` rested on the same
    re-reading and was likewise never web-search remediated before it was
    removed -- see ``sources.py``.)"""
    assert (
        "no live literature-search tool available"
        in sources.NP_MIN_SPAN_CHOICE.search_basis
    )


def test_moving_threshold_and_altitude_window_do_not_claim_no_search_tool() -> None:
    """Both records were remediated with a live web-search tool (unlike
    ``NP_MIN_SPAN_CHOICE``), so neither may carry over the "no live
    literature-search tool available" disclosure that would now be false
    for them -- a search *was* run and its queries are named instead. This
    would catch a careless copy-paste of the ``NP_MIN_SPAN_CHOICE`` search
    basis onto either record, which the whole-value backstops above also
    catch, but which the old blanket honesty check across all three would
    have wrongly demanded."""
    for record in (
        sources.MOVING_THRESHOLD_CHOICE,
        sources.ALTITUDE_WINDOW_CHOICE,
    ):
        assert "no live literature-search tool available" not in record.search_basis, (
            record.key
        )
        assert "web literature search was run" in record.search_basis, record.key


def test_moving_threshold_search_basis_names_its_actual_queries() -> None:
    """Targeted diagnostic: the record must name at least one of the
    verbatim queries actually run against a live search tool (per the
    session's search dossier), not merely assert in the abstract that a
    search happened."""
    text = sources.MOVING_THRESHOLD_CHOICE.search_basis
    assert (
        "GPS moving time speed threshold stationary detection published "
        "method m/s fitness tracking" in text
    )


def test_altitude_window_search_basis_names_its_actual_queries() -> None:
    """Targeted diagnostic, same rationale as the moving-threshold query
    check above."""
    text = sources.ALTITUDE_WINDOW_CHOICE.search_basis
    assert (
        "barometric altimetry filtering elevation gain computation moving "
        "average window samples validation study" in text
    )


def test_moving_threshold_and_altitude_window_disclose_fitdocs_ai_inheritance() -> None:
    """Req 15.9/16.6/16.7: both values were inherited from fitdocs.ai (see
    ``aggregates.py``'s own attributions), not originated in this layer.
    Each ``search_basis`` must disclose that origin and state explicitly
    that fitdocs.ai is not a published work under criterion 15.1 -- so it
    is not itself treated as this value's citable source, and so the
    record does not read as fresh fitdocs reasoning that happens to land
    on the same number fitdocs.ai already shipped."""
    for record in (
        sources.MOVING_THRESHOLD_CHOICE,
        sources.ALTITUDE_WINDOW_CHOICE,
    ):
        assert "inherited from fitdocs.ai" in record.search_basis, record.key
        assert (
            "fitdocs.ai is an application whose source this project read "
            "(linked from README.md), not a published work under "
            "criterion 15.1" in record.search_basis
        ), record.key


def test_moving_threshold_and_altitude_window_justifications_say_inherited() -> None:
    """The ``justification`` fields must themselves reconcile with that
    inheritance -- stating the value is retained from fitdocs.ai rather
    than implying it was freshly derived in this layer -- so the
    "judgment call" language that follows reads as fitdocs' reasoning for
    *keeping* an inherited number, not for having originated it."""
    for record in (
        sources.MOVING_THRESHOLD_CHOICE,
        sources.ALTITUDE_WINDOW_CHOICE,
    ):
        assert "inherits from fitdocs.ai" in record.justification, record.key
        assert (
            "rather than presenting the number as originated in this layer"
            in record.justification
        ), record.key


def test_all_citation_and_fitdocschoice_record_keys_are_distinct() -> None:
    """Every module-level ``Citation`` and ``FitdocsChoice`` record's
    ``.key`` must be unique across both types. Derived over
    ``vars(sources)`` rather than a fixed six-name tuple: that fixed tuple
    already went stale once (task 12.2 brought the true count to seven
    without this test noticing, since it is a consistency check rather than
    a hole any other test independently covers). Counting the size of the
    key set against the record count (rather than a hardcoded literal)
    catches a same-key collision between *any* two records -- new or old,
    same type or across types -- without this test itself needing an update
    every time a record is added."""
    records: list[Citation | FitdocsChoice] = [
        value
        for value in vars(sources).values()
        if isinstance(value, (Citation, FitdocsChoice))
    ]
    assert records, "the walk found no Citation or FitdocsChoice records"
    keys = {record.key for record in records}
    assert len(keys) == len(records), records


# --- CitedConstant bindings (task 9.3; Req 15.3, 15.6, 16.2) ----------------

# Whole-value backstop pins for the four weighting-term corroborators, same
# rationale as the ``Citation``/``FitdocsChoice`` backstops above: a bare
# non-emptiness check on ``locator`` or ``note`` cannot catch a substitution
# of one plausible-looking value for another (a wrong-but-real Morton page, a
# fabricated Banister page, an inverted OMITS/AGREES claim). Each constant
# below is retyped by hand from ``sources.py``, not derived from the module
# under test.
BACKSTOP_MORTON_CORROBORATOR_LOCATOR: Final[str] = "Eq. 2, p. 1172"

BACKSTOP_MORTON_MALE_COEFFICIENT_NOTE: Final[str] = (
    "Morton (1990) Eq. 2 p. 1172 gives 'Y = e^bx' for both sexes with no "
    "multiplicative coefficient anywhere in the equation or the paragraph "
    "introducing it -- confirmed by reading the page, not merely its "
    "absence from a summary. The coefficient 0.64 rests on Banister (1991) "
    "p. 408 alone; Morton (1990) simply does not state one, for either sex."
)

BACKSTOP_MORTON_FEMALE_COEFFICIENT_NOTE: Final[str] = (
    "Morton (1990) Eq. 2 p. 1172 gives 'Y = e^bx' for both sexes with no "
    "multiplicative coefficient anywhere in the equation or the paragraph "
    "introducing it -- confirmed by reading the page, not merely its "
    "absence from a summary. The coefficient 0.86 rests on Banister (1991) "
    "p. 408 alone; Morton (1990) simply does not state one, for either sex."
)

BACKSTOP_MORTON_MALE_EXPONENT_NOTE: Final[str] = (
    "Morton (1990) Eq. 2 p. 1172 states 'b values for men (1.92) and women "
    "(1.67)', matching Banister (1991) p. 408's male exponent exactly."
)

BACKSTOP_MORTON_FEMALE_EXPONENT_NOTE: Final[str] = (
    "Morton (1990) Eq. 2 p. 1172 states 'b values for men (1.92) and women "
    "(1.67)', matching Banister (1991) p. 408's female exponent exactly."
)


def test_constant_sources_has_exactly_ten_entries() -> None:
    """Req 15.6's enumeration names seven items / eight constants, and both
    training-impulse terms are instantiated once per fitted curve (four, not
    two) -- ten ``CitedConstant`` bindings in all (design.md's resolved
    classification table + the ``WeightingPair`` seam note). A registry
    missing even one of them is silently incomplete."""
    assert len(sources.CONSTANT_SOURCES) == 10


def test_constant_sources_is_exactly_the_module_level_cited_constants() -> None:
    """Completeness in both directions (the task's own observable): every
    module-level :class:`~fitdocs.citation.CitedConstant` instance must
    appear in ``CONSTANT_SOURCES``, and vice versa. (Task 12.2 briefly added
    a documented exception, ``POWER_ABSENT_SAMPLE_FILL``, which was not one
    of Req 15.6's seven enumerated items and so was deliberately kept out of
    ``CONSTANT_SOURCES``; the 2026-07-30 absent-power-sample ruling removed
    that constant entirely, so there is no exception to carve out any more --
    see ``sources.py``.) Compared by identity (``id``), not equality, so a
    *different* ``CitedConstant`` that happens to carry the same
    name/value/source cannot masquerade as the registered one. This single
    assertion still catches both directions the task's own observable names:
    dropping an entry from ``CONSTANT_SOURCES`` while its module-level
    binding still exists (the sets no longer match), and adding a brand-new
    module-level ``CitedConstant`` without registering it in
    ``CONSTANT_SOURCES`` (the module-level set grows past the registry's)."""
    module_level = [
        value for value in vars(sources).values() if isinstance(value, CitedConstant)
    ]
    assert len(module_level) == 10, module_level
    assert {id(value) for value in module_level} == {
        id(value) for value in sources.CONSTANT_SOURCES
    }


def test_constant_sources_names_are_unique() -> None:
    """The registry tuple names them all, with unique names (the task's own
    requirement, and design.md's 'Invariants: CONSTANT_SOURCES names are
    unique')."""
    names = [constant.name for constant in sources.CONSTANT_SOURCES]
    assert len(names) == len(set(names)) == 10, names


def test_each_bound_value_matches_its_recorded_literal() -> None:
    """Every ``CitedConstant.value`` below is asserted against a literal
    recorded directly in this test (not derived from another constant in the
    module, and not computed via any arithmetic expression here either), so a
    reviewer can confirm each by inspection without running any formula. This
    does not itself observe import-time computation -- that observable is
    carried by ``test_module_holds_no_arithmetic`` (the AST guard) and
    ``test_module_does_not_import_the_fit_sdk_in_subprocess`` (the subprocess
    import check) above."""
    assert sources.TSS_SCALE.value == 100.0
    assert sources.NP_ROLLING_WINDOW_S.value == 30
    assert sources.NP_AVERAGING_EXPONENT.value == 4
    assert sources.NP_MIN_SPAN_S.value == 30.0
    assert sources.MOVING_SPEED_THRESHOLD_MPS.value == 0.5
    assert sources.ALTITUDE_SMOOTHING_WINDOW.value == 10
    assert sources.BANISTER_MALE_COEFFICIENT.value == 0.64
    assert sources.BANISTER_MALE_EXPONENT.value == 1.92
    assert sources.BANISTER_FEMALE_COEFFICIENT.value == 0.86
    assert sources.BANISTER_FEMALE_EXPONENT.value == 1.67


def test_each_15_1_constant_is_bound_to_its_governing_citation_by_identity() -> None:
    """16.2: exactly one governing source per constant, checked by identity
    (``is``) rather than equality -- two ``Citation`` records could
    coincidentally compare equal (unlikely here, since every field differs),
    but identity is what actually proves the registry points at *the* shared
    module-level record rather than a freshly constructed look-alike, and is
    what a swap between ``BANISTER_1991`` and ``COGGAN_2003`` as a governing
    source would actually break."""
    assert sources.BANISTER_MALE_COEFFICIENT.source is sources.BANISTER_1991
    assert sources.BANISTER_MALE_EXPONENT.source is sources.BANISTER_1991
    assert sources.BANISTER_FEMALE_COEFFICIENT.source is sources.BANISTER_1991
    assert sources.BANISTER_FEMALE_EXPONENT.source is sources.BANISTER_1991
    assert sources.TSS_SCALE.source is sources.COGGAN_2003
    assert sources.NP_ROLLING_WINDOW_S.source is sources.COGGAN_2003
    assert sources.NP_AVERAGING_EXPONENT.source is sources.COGGAN_2003


def test_each_15_8_constant_is_bound_to_its_governing_fitdocschoice_by_identity() -> (
    None
):
    """16.2, applied to the three fitdocs-chosen values: ``SourceRecord`` is
    a union, and a ``FitdocsChoice`` is just as legal a ``source`` as a
    ``Citation`` -- but it must be the *right* one, checked by identity so a
    swap between the choice records (e.g. binding the altitude window to
    ``MOVING_THRESHOLD_CHOICE``) cannot hide behind two records that
    otherwise look similar. (Task 12.2 briefly added a fourth pairing here,
    ``POWER_ABSENT_SAMPLE_FILL``/``POWER_ABSENT_SAMPLE_CHOICE``, neither of
    which was in ``CONSTANT_SOURCES``; the 2026-07-30 absent-power-sample
    ruling removed both, so this test is back to the three pairings that
    are in the registry.) The three ``is`` pairings above are an enumerated
    list, not a registry walk, so a closing assert confirms the enumeration
    itself has not gone stale: the three listed choices must be exactly the
    module's ``FitdocsChoice`` records, so a fourth added without extending
    this list fails the closing assert rather than being silently skipped."""
    assert sources.NP_MIN_SPAN_S.source is sources.NP_MIN_SPAN_CHOICE
    assert sources.MOVING_SPEED_THRESHOLD_MPS.source is sources.MOVING_THRESHOLD_CHOICE
    assert sources.ALTITUDE_SMOOTHING_WINDOW.source is sources.ALTITUDE_WINDOW_CHOICE

    enumerated_choices = {
        id(choice)
        for choice in (
            sources.NP_MIN_SPAN_CHOICE,
            sources.MOVING_THRESHOLD_CHOICE,
            sources.ALTITUDE_WINDOW_CHOICE,
        )
    }
    module_choices = {
        id(value)
        for value in vars(sources).values()
        if isinstance(value, FitdocsChoice)
    }
    assert module_choices, "the walk found no fitdocs-choice records"
    assert enumerated_choices == module_choices, (
        "a module-level FitdocsChoice was added or removed without updating "
        "the enumerated pairing above"
    )


def test_tied_30_value_constants_are_distinguished_by_name_and_source_together() -> (
    None
):
    """Tied-value defense: ``NP_ROLLING_WINDOW_S`` (30, an ``int``, governed
    by ``COGGAN_2003``) and ``NP_MIN_SPAN_S`` (30.0, a ``float``, governed by
    ``NP_MIN_SPAN_CHOICE``) carry numerically equal values (``30 == 30.0`` in
    Python), so a pairwise swap of *only* their ``value`` fields would leave
    every bare ``== 30`` / ``== 30.0`` check in this module green. This test
    pins each constant's ``name`` and ``source`` identity, which a bare value
    swap does not touch -- but a ``30``/``30.0`` swap that moves *both*
    ``value`` fields together does not move ``name`` or ``source`` either,
    so the identity assertions below do not catch it: applying that swap with
    only the two ``type(...)`` assertions removed still leaves the suite
    green. The two ``type(...)`` assertions are the sole discriminator for
    that swap and must not be removed."""
    assert sources.NP_ROLLING_WINDOW_S.name == "np_rolling_window_s"
    assert sources.NP_ROLLING_WINDOW_S.source is sources.COGGAN_2003
    assert type(sources.NP_ROLLING_WINDOW_S.value) is int
    assert sources.NP_MIN_SPAN_S.name == "np_min_span_s"
    assert sources.NP_MIN_SPAN_S.source is sources.NP_MIN_SPAN_CHOICE
    assert type(sources.NP_MIN_SPAN_S.value) is float


def test_weighting_coefficients_omit_and_exponents_agree_with_morton() -> None:
    """15.2/16.5: the two-works corroboration relation the enumeration's
    weighting item requires -- the coefficient's single corroborator is
    ``MORTON_1990`` with relation ``OMITS`` (M90 Eq. 2 has no multiplicative
    coefficient at all), the exponent's is ``AGREES`` (M90's printed exponent
    values match Banister's exactly). Checked for both curves, and checked
    by identity on the corroborating citation so a swap of *which* citation
    corroborates (e.g. self-corroborating with ``BANISTER_1991``) is caught,
    not merely which enum value is recorded. The corroborator's ``note`` is
    pinned by full equality against a hand-retyped backstop for all four
    terms (including the two ``AGREES`` exponents, which previously had no
    note assertion at all) -- a bare non-emptiness check would survive an
    inverted claim ("Morton does print the coefficient explicitly") or a
    changed quoted b value just as easily as it survives the true text."""
    coefficient_notes = {
        sources.BANISTER_MALE_COEFFICIENT.name: BACKSTOP_MORTON_MALE_COEFFICIENT_NOTE,
        sources.BANISTER_FEMALE_COEFFICIENT.name: (
            BACKSTOP_MORTON_FEMALE_COEFFICIENT_NOTE
        ),
    }
    for coefficient in (
        sources.BANISTER_MALE_COEFFICIENT,
        sources.BANISTER_FEMALE_COEFFICIENT,
    ):
        assert len(coefficient.corroborators) == 1, coefficient.name
        corroboration = coefficient.corroborators[0]
        assert corroboration.citation is sources.MORTON_1990, coefficient.name
        assert corroboration.agreement == Agreement.OMITS, coefficient.name
        assert corroboration.note == coefficient_notes[coefficient.name], (
            coefficient.name
        )

    exponent_notes = {
        sources.BANISTER_MALE_EXPONENT.name: BACKSTOP_MORTON_MALE_EXPONENT_NOTE,
        sources.BANISTER_FEMALE_EXPONENT.name: BACKSTOP_MORTON_FEMALE_EXPONENT_NOTE,
    }
    for exponent in (
        sources.BANISTER_MALE_EXPONENT,
        sources.BANISTER_FEMALE_EXPONENT,
    ):
        assert len(exponent.corroborators) == 1, exponent.name
        corroboration = exponent.corroborators[0]
        assert corroboration.citation is sources.MORTON_1990, exponent.name
        assert corroboration.agreement == Agreement.AGREES, exponent.name
        assert corroboration.note == exponent_notes[exponent.name], exponent.name


def test_weighting_corroborators_locator_matches_the_full_pinned_text() -> None:
    """15.2: 'together with the locator within each work at which the value
    appears' -- the corroborator's own ``locator`` field, independent of
    ``MORTON_1990.locator`` itself, is pinned by full equality against
    :data:`BACKSTOP_MORTON_CORROBORATOR_LOCATOR` for all four weighting
    terms. A bare non-emptiness check previously here would survive a
    corroborator locator silently retargeted to a different Morton page, or
    even to Banister's own p. 408 (which is not a Morton locator at all)."""
    for constant in (
        sources.BANISTER_MALE_COEFFICIENT,
        sources.BANISTER_MALE_EXPONENT,
        sources.BANISTER_FEMALE_COEFFICIENT,
        sources.BANISTER_FEMALE_EXPONENT,
    ):
        assert len(constant.corroborators) == 1, constant.name
        locator = constant.corroborators[0].locator
        assert locator == BACKSTOP_MORTON_CORROBORATOR_LOCATOR, constant.name


def test_non_weighting_constants_carry_no_corroborators() -> None:
    """design.md's classification table records '--' in the Corroborator
    column for every value except the training-impulse weighting -- only the
    weighting terms carry a second work speaking to their value."""
    for constant in (
        sources.TSS_SCALE,
        sources.NP_ROLLING_WINDOW_S,
        sources.NP_AVERAGING_EXPONENT,
        sources.NP_MIN_SPAN_S,
        sources.MOVING_SPEED_THRESHOLD_MPS,
        sources.ALTITUDE_SMOOTHING_WINDOW,
    ):
        assert constant.corroborators == (), constant.name


def test_none_of_the_ten_constants_records_a_previous_value_or_departure() -> None:
    """15.3: 'the value it replaced recorded wherever a text moved one' --
    none of the ten values this task binds differs from what ``stress.py``,
    ``power.py`` and ``aggregates.py`` already ship (confirmed against those
    modules directly, not against this registry), so every
    ``previous_value`` must be ``None``. ``departure`` is also ``None`` on
    all ten -- ``DEPARTURES`` is task 9.4's, not this task's."""
    for constant in sources.CONSTANT_SOURCES:
        assert constant.previous_value is None, constant.name
        assert constant.departure is None, constant.name


def test_the_four_weighting_terms_bound_values_match_stress_py() -> None:
    """A registry whose values disagree with what the metric module actually
    uses is worse than none. As of task 11, ``stress.trimp`` no longer
    resolves or caches a default weighting of its own at all -- it reads
    ``weighting.coefficient.value`` / ``weighting.exponent.value`` straight
    off whichever :class:`~fitdocs.metrics.sources.WeightingPair` its caller
    supplies (resolving a selection, or the default for none, is the metrics
    facade's job through :func:`fitdocs.metrics.sources.weighting_for`, not
    this module's). This assertion therefore calls :func:`stress.trimp`
    directly with the registry's own male pair and confirms the accumulated
    value follows that pair's coefficient/exponent exactly -- a same-value
    consistency check (moving ``BANISTER_MALE_COEFFICIENT.value`` moves the
    expected result with it, so it cannot red on a value mismatch) rather
    than an independent pin. It guards against ``stress.trimp`` reading a
    *different* record than the one it was handed -- but not against its
    ignoring the argument in favour of the male pair specifically, which
    leaves this assertion green; that mutation is caught by
    ``tests/metrics/test_stress.py::test_trimp_uses_the_coefficient_and_exponent_of_the_supplied_pair``.
    It does not guard against a wrong *value* either -- the value itself is
    pinned by literal equality elsewhere:
    ``test_default_trimp_weighting_resolves_to_the_pre_amendment_stress_py_values``
    below (standalone ``== 0.64`` / ``== 1.92`` equalities) and by ``stress.py``'s own
    hand-computed formula tests in ``test_stress.py``."""
    import math

    import fitdocs.metrics.stress as stress
    from fitdocs.model import Samples

    none_floats: tuple[float | None, ...] = (None, None)
    samples = Samples(
        time_s=(0.0, 60.0),
        heart_rate_bpm=(130, 999),
        power_w=(None, None),
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )
    male_pair = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]
    result = stress.trimp(samples, resting_hr=60, max_hr=200, weighting=male_pair)
    assert result is not None
    # rest=60, max=200 -> HRr = (130-60)/140 = 0.5; dt_min = 1.0.
    hrr = 0.5
    expected = (
        1.0
        * hrr
        * sources.BANISTER_MALE_COEFFICIENT.value
        * math.exp(sources.BANISTER_MALE_EXPONENT.value * hrr)
    )
    assert result.value == pytest.approx(expected, rel=1e-12)


def test_tss_scale_and_np_constants_match_their_shipped_modules() -> None:
    """Same rationale as the weighting-term check above. For ``TSS_SCALE``,
    task 10.3 inverted the dependency the same way it did for the weighting
    terms: ``stress._TSS_SCALE`` is now bound *from*
    ``sources.TSS_SCALE.value`` at import time, so the equality below is a
    same-value-both-sides consistency check (it catches ``stress.py``
    binding from the wrong record, not a wrong value) rather than an
    independent pin -- the value ``100.0`` is pinned by literal equality at
    ``test_each_bound_value_matches_its_recorded_literal`` above and by
    ``stress.py``'s own hand-computed ``power_tss`` tests in
    ``test_stress.py``. The remaining fitdocs-chosen constants
    (``NP_ROLLING_WINDOW_S``, ``NP_AVERAGING_EXPONENT``, ``NP_MIN_SPAN_S``)
    are untouched by task 10.3 and read from ``power.py``'s own attributes as
    before -- ``power.py`` now also names the averaging exponent (task 10.2
    -- previously two inline literals, ``**4``/``**0.25``, with no named
    module attribute to compare against here)."""
    import fitdocs.metrics.power as power
    import fitdocs.metrics.stress as stress

    assert sources.TSS_SCALE.value == stress._TSS_SCALE
    assert sources.NP_ROLLING_WINDOW_S.value == power._NP_ROLLING_WINDOW_S
    assert sources.NP_AVERAGING_EXPONENT.value == power._NP_AVERAGING_EXPONENT
    assert sources.NP_MIN_SPAN_S.value == power._NP_MIN_SPAN_S


def test_moving_and_altitude_constants_match_aggregates_py() -> None:
    """Same rationale again, for the two ``aggregates.py``-sited values. Both
    now have a named module constant to read from -- task 10.1 promoted the
    moving-time threshold's former bare literal to
    ``aggregates._MOVING_SPEED_THRESHOLD_MPS`` -- so both are read live
    rather than transcribed."""
    import fitdocs.metrics.aggregates as aggregates

    moving_threshold = sources.MOVING_SPEED_THRESHOLD_MPS.value
    assert moving_threshold == aggregates._MOVING_SPEED_THRESHOLD_MPS
    assert (
        sources.ALTITUDE_SMOOTHING_WINDOW.value == aggregates._ALTITUDE_SMOOTHING_WINDOW
    )


# --- Weighting resolver (task 9.4; Req 16.5, 17.1, 17.2, 17.4) --------------
#
# ``WEIGHTING_PAIRS``, ``DEFAULT_TRIMP_WEIGHTING``, ``weighting_for`` and
# ``DEPARTURES``. This does NOT wire the resolver into ``stress.trimp`` --
# threading a caller's selection through to a computed metric is task 11, not
# this one; nothing below calls ``fitdocs.metrics.stress.trimp``.


def test_weighting_pair_is_frozen() -> None:
    """design.md's Service Interface declares ``WeightingPair`` frozen, and
    this repo pins frozenness for every comparable citation/metrics
    dataclass (see ``tests/test_citation.py``'s
    ``test_all_record_types_are_frozen`` and the ``ZoneSpec``/
    ``AthleteInputs``/``DerivedMetrics`` guards in ``test_types.py``) --
    nothing pinned it here before this test.

    Uses a throwaway ``WeightingPair`` rather than the registered
    ``WEIGHTING_PAIRS`` singleton: under a broken, mutable implementation,
    assigning to the registered module-level object would succeed and the
    mutation would leak into every later test that reads
    ``WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]``."""
    pair = sources.WeightingPair(
        selection=TrimpWeighting.BANISTER_MALE,
        coefficient=sources.BANISTER_MALE_COEFFICIENT,
        exponent=sources.BANISTER_MALE_EXPONENT,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        pair.coefficient = sources.BANISTER_FEMALE_COEFFICIENT  # type: ignore[misc]


def test_weighting_pairs_has_exactly_the_two_trimpweighting_members_as_keys() -> None:
    """``WEIGHTING_PAIRS`` keys are exactly the ``TrimpWeighting`` members --
    derived from the enum itself (``set(TrimpWeighting)``), so the keys
    assertion does not silently rot if a third curve is ever added. The
    ``len`` assertion below is a hardcoded pair count -- it is expected to
    red loudly the day a third curve is added, at which point it must be
    updated alongside the enum. Design's own invariant: 'WEIGHTING_PAIRS
    keys are exactly the TrimpWeighting members'."""
    assert set(sources.WEIGHTING_PAIRS.keys()) == set(TrimpWeighting)
    assert len(sources.WEIGHTING_PAIRS) == 2


def test_each_weighting_pair_carries_its_own_selection_and_registered_terms() -> None:
    """Each ``WeightingPair``'s own ``.selection`` matches the key it is
    stored under (not merely present in the mapping under any key), and its
    ``.coefficient``/``.exponent`` are, by identity, the exact
    ``CitedConstant`` objects task 9.3 registered in ``CONSTANT_SOURCES`` --
    not a fresh, equal-looking, unregistered pair. Checked by identity
    because that is what distinguishes a fresh, equal-content,
    unregistered ``CitedConstant`` from the registered object: a bare
    ``.coefficient.value`` check would still catch a male/female curve swap
    (0.64 vs 0.86 are distinct values), but it would not catch a
    ``WeightingPair`` built from an unregistered copy carrying the same
    numbers -- only identity against ``CONSTANT_SOURCES`` rules that out."""
    male = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]
    assert male.selection == TrimpWeighting.BANISTER_MALE
    assert male.coefficient is sources.BANISTER_MALE_COEFFICIENT
    assert male.exponent is sources.BANISTER_MALE_EXPONENT

    female = sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_FEMALE]
    assert female.selection == TrimpWeighting.BANISTER_FEMALE
    assert female.coefficient is sources.BANISTER_FEMALE_COEFFICIENT
    assert female.exponent is sources.BANISTER_FEMALE_EXPONENT

    for constant in (
        male.coefficient,
        male.exponent,
        female.coefficient,
        female.exponent,
    ):
        assert any(constant is registered for registered in sources.CONSTANT_SOURCES), (
            constant.name
        )


def test_default_trimp_weighting_resolves_to_the_pre_amendment_stress_py_values() -> (
    None
):
    """17.2: the no-selection default must be pinned by *value*, not merely
    by member name, so a later rename of ``BANISTER_MALE`` cannot silently
    weaken the guarantee (design.md's own instruction). The bare
    ``0.64``/``1.92`` literals below are the independent value check (a wrong
    default value reds here) -- this test's own registry-level reasoning is
    the ``DEFAULT_TRIMP_WEIGHTING == TrimpWeighting.BANISTER_MALE`` line
    (task 9.4's own decision, tracked and open at design.md:1120-1141 and
    ``.kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md``); the
    *behavioral* value-not-name pin, that this same default pair reproduces
    fitdocs' pre-Amendment-1 TRIMP output through
    :func:`fitdocs.metrics.stress.trimp`, is
    ``tests/metrics/test_facade.py::
    test_no_selection_reproduces_the_pre_amendment_value_pinned_by_value``
    (task 11) -- as of that task, ``stress.py`` no longer holds a coefficient
    or exponent of its own to compare against here at all."""
    assert sources.DEFAULT_TRIMP_WEIGHTING == TrimpWeighting.BANISTER_MALE
    pair = sources.weighting_for(None)
    assert pair.coefficient.value == 0.64
    assert pair.exponent.value == 1.92


def test_weighting_for_absent_selection_returns_the_default_pair_by_identity() -> None:
    """17.2: ``weighting_for(None)`` returns exactly the registered default
    pair object (identity), not merely an equal-looking one constructed
    fresh.

    This assertion is a self-referential compare -- both sides are indexed
    by ``DEFAULT_TRIMP_WEIGHTING``, so it stays green even under a default
    flip to the female pair; it survives here only as a cheap identity
    smoke check. The value-pinned test above,
    ``test_default_trimp_weighting_resolves_to_the_pre_amendment_stress_py_values``,
    is what actually pins 17.2's default to the pre-amendment (0.64, 1.92)
    values -- do not delete that test as redundant with this one."""
    assert (
        sources.weighting_for(None)
        is sources.WEIGHTING_PAIRS[sources.DEFAULT_TRIMP_WEIGHTING]
    )


def test_weighting_for_stated_selection_returns_the_matching_registered_pair() -> None:
    """17.1: for each defined selection, ``weighting_for`` returns exactly
    the registered pair for that selection (identity) -- not the default,
    and not the other curve's pair. Male and female values are
    pairwise-distinct (0.64/1.92 vs 0.86/1.67), so a resolver that silently
    always returned the default regardless of the stated selection reddens
    the female-branch assertion below without touching the male one."""
    assert (
        sources.weighting_for(TrimpWeighting.BANISTER_MALE)
        is sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_MALE]
    )
    assert (
        sources.weighting_for(TrimpWeighting.BANISTER_FEMALE)
        is sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_FEMALE]
    )
    assert (
        sources.weighting_for(TrimpWeighting.BANISTER_FEMALE).coefficient.value == 0.86
    )
    assert sources.weighting_for(TrimpWeighting.BANISTER_FEMALE).exponent.value == 1.67


def test_weighting_for_accepts_a_plain_string_matching_a_defined_member_value() -> None:
    """Because ``TrimpWeighting`` is a ``StrEnum``, a caller can genuinely
    hand ``weighting_for`` a plain ``str`` equal to a member's value (not
    only the enum member itself) -- this is a reachable path, not a
    hypothetical one. The resolver accepts it by coercing the input through
    ``TrimpWeighting(resolved)`` before the lookup, so this is an *observed
    consequence* of ``TrimpWeighting`` being a ``StrEnum`` and of the
    resolver's own coercion, not a promised contract of ``weighting_for``'s
    ``TrimpWeighting | None`` signature -- the signature does not commit to
    accepting a bare ``str``, and a caller relying on this path is relying
    on an implementation detail."""
    pair = sources.weighting_for("banister_female")  # type: ignore[arg-type]
    assert pair is sources.WEIGHTING_PAIRS[TrimpWeighting.BANISTER_FEMALE]


def test_weighting_for_rejects_an_unhashable_selection_with_value_error() -> None:
    """17.4: an unhashable selection (e.g. a ``set``) must be rejected with
    ``ValueError``, not escape as ``TypeError``. ``weighting_for`` coerces
    ``resolved`` through ``TrimpWeighting(resolved)`` before the mapping
    lookup specifically so that an unhashable input fails ``TrimpWeighting``
    construction (raising ``ValueError``, caught by the handler) rather than
    reaching ``WEIGHTING_PAIRS[resolved]`` directly, where subscripting a
    dict with an unhashable key raises ``TypeError`` -- a type the resolver's
    ``except (KeyError, ValueError)`` clause does not catch. A resolver that
    dropped the coercion and subscripted ``WEIGHTING_PAIRS`` with the raw
    input would let this ``TypeError`` escape uncaught instead of raising
    the documented ``ValueError``."""
    with pytest.raises(ValueError):
        sources.weighting_for({"banister_male"})  # type: ignore[arg-type]


def test_weighting_for_rejects_unrecognized_selection_names_defined_set() -> None:
    """17.4: an unrecognized selection is rejected -- named in the error --
    together with every selection the source defines, rather than silently
    substituting a pair. The expected message is built from
    ``TrimpWeighting`` itself (``[m.value for m in TrimpWeighting]``), not a
    hardcoded "two selections" list, so this does not silently stop
    discriminating if a third curve is ever added to the enum. Pinned by
    whole-message equality: a bare 'contains "bogus_selection"' check alone
    would not catch the defined-set half going missing or wrong, and a bare
    'names every defined value' check alone would not catch the selection
    itself going unnamed."""
    expected_defined = ", ".join(member.value for member in TrimpWeighting)
    with pytest.raises(ValueError) as exc_info:
        sources.weighting_for("bogus_selection")  # type: ignore[arg-type]
    message = str(exc_info.value)
    assert message == (
        "Unrecognized training-impulse weighting selection 'bogus_selection'; "
        f"the source defines: {expected_defined}"
    )


def test_weighting_for_rejection_does_not_substitute_a_pair() -> None:
    """17.4: an unrecognized selection must raise, never return a
    ``WeightingPair`` -- a resolver that caught the lookup failure and
    quietly fell back to the default would satisfy every message-content
    assertion above if it raised nothing, so this separately proves the call
    actually raises rather than returning a value at all."""
    with pytest.raises(ValueError):
        sources.weighting_for("not_a_real_selection")  # type: ignore[arg-type]


# Whole-value backstops for the three ``DEPARTURES`` entries. Each constant is
# retyped by hand, not derived from the module under test, so a mutation to
# ``sources.py`` cannot silently drag its own backstop along with it.
BACKSTOP_SEX_NEUTRAL_SUBJECT: Final[str] = "trimp-weighting-sex-neutral-default"
BACKSTOP_SEX_NEUTRAL_SOURCE_SPECIFIES: Final[str] = (
    "Banister (1991) p. 408 and Morton (1990) Eq. 2 p. 1172 both define the "
    "training-impulse weighting per sex -- Banister as a distinct coefficient "
    "and exponent pair per sex (0.64/1.92 male, 0.86/1.67 female), Morton as "
    "a distinct exponent per sex (b = 1.92 men, 1.67 women) with no "
    "coefficient in either."
)
BACKSTOP_SEX_NEUTRAL_FITDOCS_DOES: Final[str] = (
    "fitdocs applies the BANISTER_MALE weighting pair to every athlete who "
    "supplies no weighting selection (Req 17.2), regardless of that "
    "athlete's sex."
)
BACKSTOP_SEX_NEUTRAL_REASON: Final[str] = (
    "Req 17.2 pins the no-selection default to the exact pair fitdocs "
    "computed with before this amendment -- stress.py's coefficient (0.64) "
    "and exponent (1.92), which are Banister's male curve -- so that no "
    "athlete's TRIMP changes by default when Amendment 1 lands; "
    "sex-neutrality is a stability guarantee for existing callers, not a "
    "claim that the male curve fits every athlete."
)

BACKSTOP_INTEGRATION_SUBJECT: Final[str] = "trimp-per-sample-integration"
BACKSTOP_INTEGRATION_SOURCE_SPECIFIES: Final[str] = (
    "Both Banister (1991) p. 408 and Morton (1990) p. 1172 sum the "
    "training-impulse weighting over segments of near-constant heart rate, "
    "each segment contributing its own average heart rate to the sum."
)
BACKSTOP_INTEGRATION_FITDOCS_DOES: Final[str] = (
    "fitdocs integrates every consecutive sample pair in the heart-rate "
    "channel, applying the weighting to each pair's own duration and "
    "heart-rate reserve."
)
# Retyped by hand from the reviewer's own remediation text -- never derived
# from sources.py, so a mutation to the module's own reason string cannot
# silently drag its own backstop along with it.
BACKSTOP_INTEGRATION_REASON: Final[str] = (
    "Per-sample-pair integration is the segment sum of the cited texts in "
    "the limit of segment width shrinking to one sample interval. It is "
    "not numerically identical to the texts' segment form: x*e^(1.92x) is "
    "convex on [0, 1], so by Jensen's inequality the per-sample sum is "
    "systematically greater than or equal to the segment-mean form "
    "whenever heart rate varies within a segment, and equal only when it "
    "does not. fitdocs takes the sample series the file records rather "
    "than reconstructing the texts' steady-state segments."
)

BACKSTOP_COEFFICIENT_SUBJECT: Final[str] = "trimp-coefficient-over-morton"
BACKSTOP_COEFFICIENT_SOURCE_SPECIFIES: Final[str] = (
    "Morton (1990) Eq. 2 p. 1172 prints the training-impulse weighting as "
    "'Y = e^bx' -- a bare exponential with no multiplicative coefficient "
    "anywhere in the equation or the paragraph introducing it."
)
BACKSTOP_COEFFICIENT_FITDOCS_DOES: Final[str] = (
    "fitdocs ships Banister (1991) p. 408's multiplicative coefficient "
    "(0.64 for the male curve, 0.86 for the female curve) rather than "
    "Morton's uncoefficiented form, per the maintainer's 2026-07-27 ruling "
    "and Morton's own worked example."
)
# Retyped by hand from the reviewer's own remediation text -- never derived
# from sources.py.
BACKSTOP_COEFFICIENT_REASON: Final[str] = (
    "The maintainer ruled on 2026-07-27 to keep Banister's coefficient "
    "because Morton's own worked example in the same paper implies a "
    "coefficient its printed equation omits, so a bare 'Y = e^bx' with no "
    "coefficient at all would compute a training-impulse value inconsistent "
    "with the ~125-trimp figure Morton's own worked example illustrates -- "
    "an inference from that one example, whose HR_max and HR_rest the "
    "paper leaves unstated, rather than a statement in either text."
)


def test_departures_has_exactly_three_entries() -> None:
    """16.5: the design's ``DEPARTURES`` content table names exactly three
    entries -- not more, not fewer."""
    assert len(sources.DEPARTURES) == 3
    assert all(isinstance(entry, Departure) for entry in sources.DEPARTURES)


def test_departures_subjects_are_unique_and_match_the_design_table() -> None:
    """Subject values must be unique (the task's own requirement) and match
    the three subjects design.md's ``DEPARTURES`` table names, by full
    equality rather than substring -- a truncated or renamed subject
    (e.g. dropping the '-default' suffix) would otherwise still read as
    'present'."""
    subjects = [entry.subject for entry in sources.DEPARTURES]
    assert len(subjects) == len(set(subjects)) == 3
    assert set(subjects) == {
        BACKSTOP_SEX_NEUTRAL_SUBJECT,
        BACKSTOP_INTEGRATION_SUBJECT,
        BACKSTOP_COEFFICIENT_SUBJECT,
    }


def _departure_by_subject(subject: str) -> Departure:
    matches = [entry for entry in sources.DEPARTURES if entry.subject == subject]
    assert len(matches) == 1, subject
    return matches[0]


def test_sex_neutral_departure_matches_the_full_pinned_text() -> None:
    """Whole-value backstop over all three prose fields of the
    sex-neutral-default departure -- pinning ``source_specifies``,
    ``fitdocs_does`` and ``reason`` each by full equality, same rationale as
    the ``Citation``/``FitdocsChoice`` note backstops above: a bare
    non-emptiness check would survive a swap of ``source_specifies`` with
    ``fitdocs_does`` (the two are adjacent and near-symmetric prose), or the
    male curve silently becoming the female curve in ``fitdocs_does``."""
    entry = _departure_by_subject(BACKSTOP_SEX_NEUTRAL_SUBJECT)
    assert entry.source_specifies == BACKSTOP_SEX_NEUTRAL_SOURCE_SPECIFIES
    assert entry.fitdocs_does == BACKSTOP_SEX_NEUTRAL_FITDOCS_DOES
    assert entry.reason == BACKSTOP_SEX_NEUTRAL_REASON


def test_integration_departure_matches_the_full_pinned_text() -> None:
    """Whole-value backstop over the per-sample-integration departure, same
    rationale: a bare non-emptiness check would survive "near-constant"
    silently becoming "varying", or ``source_specifies``/``fitdocs_does``
    being swapped wholesale."""
    entry = _departure_by_subject(BACKSTOP_INTEGRATION_SUBJECT)
    assert entry.source_specifies == BACKSTOP_INTEGRATION_SOURCE_SPECIFIES
    assert entry.fitdocs_does == BACKSTOP_INTEGRATION_FITDOCS_DOES
    assert entry.reason == BACKSTOP_INTEGRATION_REASON


def test_coefficient_departure_matches_the_full_pinned_text() -> None:
    """Whole-value backstop over the coefficient-over-Morton departure, same
    rationale: a bare non-emptiness check would survive "with no
    multiplicative coefficient" being inverted to "with a multiplicative
    coefficient" in ``source_specifies``, or the coefficient values
    (0.64/0.86) being altered in ``fitdocs_does``."""
    entry = _departure_by_subject(BACKSTOP_COEFFICIENT_SUBJECT)
    assert entry.source_specifies == BACKSTOP_COEFFICIENT_SOURCE_SPECIFIES
    assert entry.fitdocs_does == BACKSTOP_COEFFICIENT_FITDOCS_DOES
    assert entry.reason == BACKSTOP_COEFFICIENT_REASON


def test_no_departure_field_is_empty() -> None:
    """tasks.md:190's Observable for this task: 'each departure states what
    the source specifies, what fitdocs does, and why' -- every field on
    every entry is
    non-empty. A weaker check than the whole-value backstops above; kept as
    a diagnostic that covers even a fourth, unpinned departure that is ever
    added without its own backstop."""
    for entry in sources.DEPARTURES:
        assert entry.subject
        assert entry.source_specifies
        assert entry.fitdocs_does
        assert entry.reason


def test_departures_is_not_where_the_np_rolling_window_start_condition_lands() -> None:
    """design.md:1211-1212 is explicit that ``DEPARTURES`` is not where the
    NP rolling-window start condition lands: 'that divergence is being
    removed rather than recorded; see PowerSeriesMetrics'. tasks.md 13.1 is
    the unit that removes it. No entry's subject may reference the rolling
    window or partial-window averaging."""
    for entry in sources.DEPARTURES:
        assert "rolling" not in entry.subject
        assert "partial-window" not in entry.subject
        assert "partial window" not in entry.subject


# --- ConstantGuard registry assertions (task 12.1; Req 15.2, 15.4, 15.6, ---
# --- 15.8, 15.9, 16.2, 16.5, 16.6) -------------------------------------------
#
# Every assertion in this section walks CONSTANT_SOURCES (and, for the
# weighting-specific ones, WEIGHTING_PAIRS) programmatically rather than
# naming the ten module-level constants individually the way the task
# 9.x/10.x tests above do. That is deliberate: this section is the
# *systematic* guard design.md's ConstantGuard component and this task's own
# "Registry assertions over the records" bullet ask for -- one that a future
# eleventh constant is covered by simply being added to the registry, not by
# a reviewer remembering to extend a hardcoded tuple. (No assertion in this
# section reads DEPARTURES; a future fourth departure is not covered by
# anything here.) It duplicates some already-pinned facts (e.g. that the
# weighting terms carry a MORTON_1990 corroborator) by construction, and
# adds one invariant no earlier task asserts at all: that no corroborator
# names its own constant's governing source.
#
# 15.6's "exactly once" is asserted here as *coverage* (every value the
# enumeration names appears at least once), not as "exactly one entry per
# enumerated item" -- the training-impulse coefficient and exponent are each
# instantiated once per fitted curve (task 9.3), a known seam between the
# design's stricter wording and Req 15.6 tracked open at
# ``.kiro/queue/2026-07-28-weighting-terms-appear-twice-in-registry.md``
# (checked at the start of this task: still ``status: open``, unruled). The
# name-uniqueness and full-registry-coverage assertions above
# (``test_constant_sources_names_are_unique``,
# ``test_constant_sources_is_exactly_the_module_level_cited_constants``)
# already carry that coverage reading; nothing here tightens it further.


def test_every_registry_citation_carries_a_non_empty_locator_when_primary_text() -> (
    None
):
    """design.md's own ``CitedConstant`` invariant -- 'a Citation carrying
    PRIMARY_TEXT has a non-None locator' -- asserted by walking every
    Citation the registry actually reaches: each constant's governing
    source (when it is a Citation rather than a FitdocsChoice) and every
    corroborator's citation. This is the generic form of the per-record
    ``locator == "p. 408"``-style pins above; it additionally reaches
    corroborator citations, which those pins never touch as a *governing*
    source."""
    citations: list[Citation] = []
    for constant in sources.CONSTANT_SOURCES:
        if isinstance(constant.source, Citation):
            citations.append(constant.source)
        for corroboration in constant.corroborators:
            citations.append(corroboration.citation)
    assert citations, "the walk found no citations in the registry"
    for citation in citations:
        if citation.verification == VerificationStatus.PRIMARY_TEXT:
            assert citation.locator, citation.key


def test_every_module_fitdocschoice_carries_non_empty_justification_and_basis() -> None:
    """15.8, 15.9 -- asserted by walking every module-level ``FitdocsChoice``
    instance directly, rather than deriving the set from
    ``sources.CONSTANT_SOURCES`` (task 12.2's remediation: walking the
    registry alone missed the now-removed ``POWER_ABSENT_SAMPLE_CHOICE``,
    which was deliberately kept out of ``CONSTANT_SOURCES`` while it
    existed -- see ``sources.py`` -- so a registry walk enforced 15.8/15.9
    on only the registered ``FitdocsChoice`` records and nothing on one kept
    out of it; the same hole would reopen for any future record kept out of
    the registry the same way). Walking ``vars(sources)`` instead closes the
    class for any future *module-level* ``FitdocsChoice`` binding -- it does
    not reach a ``FitdocsChoice`` constructed inline as an argument and never
    bound to a module name (the identity test above is what pins that
    case)."""
    choices = [
        value for value in vars(sources).values() if isinstance(value, FitdocsChoice)
    ]
    assert choices, "the walk found no fitdocs-choice records"
    for choice in choices:
        assert choice.justification, choice.key
        assert choice.search_basis, choice.key


def test_no_module_level_citation_carries_secondary_attestation_status() -> None:
    """15.4: no record this module reaches -- a constant's governing source
    or any corroborator -- may carry ``SECONDARY_ATTESTATION``. Walks every
    module-level ``CitedConstant`` instance directly, rather than only
    ``sources.CONSTANT_SOURCES`` (task 12.2's remediation, same class-level
    hole as the ``FitdocsChoice`` walk above: the now-removed
    ``POWER_ABSENT_SAMPLE_FILL`` was deliberately kept out of the registry
    while it existed, so a registry-only walk would silently skip it, and
    would still silently skip any future constant kept out of the registry
    the same way), rather than naming ``BANISTER_1991``/``MORTON_1990``/
    ``COGGAN_2003`` directly."""
    citations: list[Citation] = []
    constants = [
        value for value in vars(sources).values() if isinstance(value, CitedConstant)
    ]
    assert constants, "the walk found no CitedConstant records"
    for constant in constants:
        if isinstance(constant.source, Citation):
            citations.append(constant.source)
        for corroboration in constant.corroborators:
            citations.append(corroboration.citation)
    assert citations, "the walk found no citations in the registry"
    for citation in citations:
        assert citation.verification != VerificationStatus.SECONDARY_ATTESTATION, (
            citation.key
        )


def test_no_corroborator_names_its_own_constants_governing_source() -> None:
    """design.md's own ``CitedConstant`` invariant -- 'no Corroboration names
    the same work as its constant's governing source' -- asserted here for
    the first time in this module. Compared by the citation's ``key`` (a
    stable identifier independent of object identity), over every
    corroborator every registered constant carries."""
    checked = 0
    for constant in sources.CONSTANT_SOURCES:
        for corroboration in constant.corroborators:
            checked += 1
            if isinstance(constant.source, Citation):
                assert corroboration.citation.key != constant.source.key, constant.name
    assert checked, "the walk found no corroborators to check"


def test_every_registry_corroboration_has_a_locator_and_a_note_when_not_agreeing() -> (
    None
):
    """15.2 (locator) plus design.md's own invariant ('a non-None note
    whenever agreement is not AGREES') -- asserted generically over every
    ``Corroboration`` the registry holds, rather than the four weighting-term
    ones the full-text backstops above name directly."""
    checked = 0
    for constant in sources.CONSTANT_SOURCES:
        for corroboration in constant.corroborators:
            checked += 1
            assert corroboration.locator, constant.name
            if corroboration.agreement != Agreement.AGREES:
                assert corroboration.note, constant.name
    assert checked, "the walk found no corroborators to check"


def test_no_fitdocschoice_sourced_constant_carries_corroborators_by_type() -> None:
    """design.md: 'A FitdocsChoice constant takes no corroborators' --
    asserted here by the governing source's *type*
    (``isinstance(constant.source, FitdocsChoice)``), walked over every
    module-level ``CitedConstant`` instance rather than only
    ``sources.CONSTANT_SOURCES`` (task 12.2's remediation: ``constant.source
    for constant in sources.CONSTANT_SOURCES`` alone never reached the
    now-removed ``POWER_ABSENT_SAMPLE_FILL``, which was deliberately kept
    out of the registry while it existed -- see ``sources.py``), rather than
    by naming the six non-weighting constants the way
    ``test_non_weighting_constants_carry_no_corroborators`` above does. A
    future fitdocs-choice constant -- registered or not -- is covered by its
    classification alone, without being added to a hardcoded tuple."""
    constants = [
        value for value in vars(sources).values() if isinstance(value, CitedConstant)
    ]
    assert constants, "the walk found no CitedConstant records"
    choice_constants = [
        constant for constant in constants if isinstance(constant.source, FitdocsChoice)
    ]
    assert choice_constants, "the walk found no fitdocs-choice constants"
    for constant in choice_constants:
        assert constant.corroborators == (), constant.name


def test_every_registered_weighting_term_carries_a_morton_corroborator() -> None:
    """15.2, derived from ``WEIGHTING_PAIRS`` rather than the four
    module-level ``BANISTER_*`` names the full-text backstops above use --
    every coefficient and exponent any registered ``WeightingPair`` holds
    carries at least one corroborator naming ``MORTON_1990`` (by identity)
    with a non-empty locator. Covers a future third curve added to
    ``WEIGHTING_PAIRS`` without editing this test."""
    terms: list[CitedConstant[float]] = []
    for pair in sources.WEIGHTING_PAIRS.values():
        terms.append(pair.coefficient)
        terms.append(pair.exponent)
    assert terms, "the walk found no weighting terms"
    for term in terms:
        morton = [
            corroboration
            for corroboration in term.corroborators
            if corroboration.citation is sources.MORTON_1990
        ]
        assert morton, term.name
        assert all(corroboration.locator for corroboration in morton), term.name


def test_every_registered_weighting_pairs_coefficient_omits_and_exponent_agrees() -> (
    None
):
    """15.2's two-works criterion -- the coefficient's relation to Morton is
    ``OMITS`` and the exponent's is ``AGREES`` -- derived generically from
    ``WEIGHTING_PAIRS`` rather than the four hardcoded names above. Executed
    against ``BANISTER_MALE_COEFFICIENT``: dropping its Morton corroborator
    entirely reddens four tests -- this one, the Morton-corroborator guard
    above, and both task 9.x full-text backstops
    (``test_weighting_coefficients_omit_and_exponents_agree_with_morton``,
    ``test_weighting_corroborators_locator_matches_the_full_pinned_text``).
    Flipping only its relation from ``OMITS`` to ``AGREES`` reddens exactly
    two -- this assertion and
    ``test_weighting_coefficients_omit_and_exponents_agree_with_morton`` --
    leaving the Morton-corroborator guard (which checks that a corroborator
    exists and carries a non-empty locator, not its ``agreement``) and the
    locator backstop green."""
    pairs = list(sources.WEIGHTING_PAIRS.values())
    assert pairs, "the walk found no weighting pairs"
    for pair in pairs:
        coefficient_morton = [
            corroboration
            for corroboration in pair.coefficient.corroborators
            if corroboration.citation is sources.MORTON_1990
        ]
        assert coefficient_morton, pair.coefficient.name
        assert all(
            corroboration.agreement == Agreement.OMITS
            for corroboration in coefficient_morton
        ), pair.coefficient.name

        exponent_morton = [
            corroboration
            for corroboration in pair.exponent.corroborators
            if corroboration.citation is sources.MORTON_1990
        ]
        assert exponent_morton, pair.exponent.name
        assert all(
            corroboration.agreement == Agreement.AGREES
            for corroboration in exponent_morton
        ), pair.exponent.name


def test_registry_records_are_readable_from_a_fresh_interpreter_without_a_metric() -> (
    None
):
    """16.6: 'readable without computing a metric', asserted directly against
    the registry object itself (not merely the absence of the FIT SDK from
    ``sys.modules``, which ``test_module_does_not_import_the_fit_sdk_in_
    subprocess`` above already covers) -- a fresh subprocess can read every
    constant's ``name`` and non-``None`` ``source`` from ``CONSTANT_SOURCES``
    without calling any function in ``fitdocs.metrics``. The subprocess walks
    every record the registry holds, not just the first, and prints how many
    it read; the parent process compares that count against its own
    ``len(CONSTANT_SOURCES)``. The positive control below is what makes that
    walk non-vacuous: on an empty registry the subprocess reads nothing,
    prints ``0``, and the count comparison matches ``0`` -- so without it
    this test passes having asserted nothing about any record. An empty
    ``name`` or a ``None`` source on
    *any* record -- not only the first -- fails the subprocess's own
    ``assert``, which reddens this test via the non-zero exit status; the
    count comparison is a shape check on top of that, not what catches a
    bad record. This does not, on its own, prove the
    subprocess and the parent process are reading two independently
    populated registries: both import the same module from the same file,
    so a change that truncates or reorders ``CONSTANT_SOURCES`` is visible
    identically to both sides and this comparison cannot distinguish that
    from an unmutated run."""
    assert sources.CONSTANT_SOURCES, "the walk found no records in the registry"
    code = (
        "import fitdocs.metrics.sources as sources\n"
        "count = 0\n"
        "for constant in sources.CONSTANT_SOURCES:\n"
        "    assert constant.name\n"
        "    assert constant.source is not None\n"
        "    count += 1\n"
        "print(count)\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == str(len(sources.CONSTANT_SOURCES))


# --- MigrationGate (task 13.2; Req 15.3, 18.1, 18.4, 18.5) ------------------
#
# Ties a changed reported value to the document-format version advance
# (``contract.DOC_VERSION``). Lives here, in the test layer only, precisely
# so 18.5 holds in production: nothing under ``fitdocs.metrics`` imports
# ``fitdocs.contract`` (see ``test_module_source_imports_only_fitdocs_
# citation_internally`` above, which already pins ``sources.py``'s own
# import set and would catch a production import creeping in) -- the
# coupling exists only where a reviewer of this test file can see it.
#
# Two independent triggers, each with its own forward assertion and its own
# discrimination test that forces the exact "forgotten advance" shape and
# confirms that same forward assertion goes red -- so neither can go quiet
# by omission:
#
# 1. **Constant trigger** -- any ``CitedConstant`` in ``CONSTANT_SOURCES``
#    carrying a ``previous_value`` implies the advance. Vacuous against
#    today's real registry (see ``test_none_of_the_ten_constants_records_a_
#    previous_value_or_departure`` above: every one of the seven primary-
#    text-sourced constants was confirmed unchanged), so it is exercised
#    here against a synthetic moved constant, and separately against a
#    mutated copy of the real registry (matching today's actual
#    ``contract.DOC_VERSION``), instead.
# 2. **Behavior trigger** -- fit-ingest task 13.1's NP rolling-window
#    conformance change (only complete windows are averaged) moves NP, and
#    with it IF/VI/TSS/EF, for most activities with a long-enough power
#    stream (not universally -- a constant-power stream's old and new NP
#    coincide; see ``contract.DOC_VERSION``'s own docstring), independently
#    of whether any constant moved. Pinned by the same provably-differing
#    fixture ``tests/metrics/test_power.py`` uses for its own NP-value
#    assertion (29 s at 0 W, then 61 s at 300 W), reproduced here rather
#    than imported so this gate does not depend on that other test module's
#    internals to fail on its own.

_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE: Final[int] = 3
"""The document-format version this amendment (fit-ingest task 13.2) started
from -- ``contract.DOC_VERSION``'s own docstring records this as the version
raised in the *previous* bump (2 -> 3, Req 11.5's managed-load-key rename).

Task 13.2 remediation, round 3 finding: this used to be a module-level
``Final[int]`` named ``PRE_AMENDMENT_DOC_VERSION`` and treated as a live gate
input. It is **not** one, and naming it as though it were misled a reviewer:
the **behavior trigger**'s forward assertion, ``doc_version > this value``,
records one specific historical event (this amendment's own advance, 3 -> 4)
that already happened. Once ``contract.DOC_VERSION`` has advanced past ``3``
for any reason -- which it already has, in this very amendment -- the
comparison holds forever afterward regardless of any future registry or
behavior state, and no assertion in this file (or anywhere else) checks this
specific literal against any current, inspectable piece of reality; changing
it from ``3`` to ``2`` reddens nothing (verified). A ``Final`` constant with
a doc comment claiming maintenance significance would overstate that: it is
an inert historical annotation, kept as a leading-underscore module local
with this docstring explaining why, and not used outside this module -- the
leading underscore is what enforces that. The behavior trigger below reads it
as the value it monkeypatches ``contract.DOC_VERSION`` to, which is why
changing it reddens nothing: that discrimination is self-relative (patch the
version to this constant, then assert ``x > x`` fails), so any integer would
serve. The **constant trigger** below does NOT use this value -- see
:data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION` for why a frozen pre-amendment
baseline cannot serve as that trigger's comparison point, and why that
trigger's own baseline is instead tied to current reality where it can be."""

CONSTANT_REGISTRY_ASOF_DOC_VERSION: Final[int] = 5
"""The document-format version as of which every ``CONSTANT_SOURCES``
binding was last confirmed to carry no ``previous_value`` (this amendment:
Req 15.3, 18.4) -- today, ``contract.DOC_VERSION`` itself.

This is intentionally NOT the frozen historical value the previous
paragraph names. That value is frozen at ``3`` -- this amendment's
*starting* version -- and once ``contract.DOC_VERSION`` has advanced past it
for any reason (as it already has, via the behavior trigger, in this very
amendment), the comparison ``doc_version > 3`` holds forever afterward
regardless of the registry's own state: a future re-sourcing that moves a
value without advancing ``contract.DOC_VERSION`` at all would still pass.
Pinning the constant-trigger baseline to the *current* ``contract.DOC_VERSION``
instead closes that gap -- ``doc_version > CONSTANT_REGISTRY_ASOF_DOC_VERSION``
is false today (4 > 4), so it only holds once a future change both moves a
value AND advances ``contract.DOC_VERSION`` beyond this constant.

Tied to reality, but only while it is safe to (task 13.2 remediation, round
4 finding): asserting ``CONSTANT_REGISTRY_ASOF_DOC_VERSION ==
contract.DOC_VERSION`` unconditionally would be unfollowable the moment a
constant actually moves, because ``CitedConstant.previous_value`` is
PERMANENT (``src/fitdocs/citation.py``, Req 15.3) -- the re-sourcing edit
itself must leave this constant strictly BELOW the new
``contract.DOC_VERSION`` (see the forward gate above), never equal to it, so
an unconditional equality pin would contradict the forward gate in the same
edit that legitimately satisfies it. ``_assert_constant_registry_asof_matches_
reality`` below therefore only asserts the equality while the registry
itself is clean (no constant carries a ``previous_value``) -- exactly the
regime today's real ``CONSTANT_SOURCES`` is in, and the only regime in which
this constant's job description ("confirmed clean as of this doc version")
makes equality the correct claim rather than a stale one.

Maintenance obligation this creates (corrected in task 13.2 remediation,
Finding 2 -- the previous wording here was unfollowable): the change that
next moves a cited constant's value must advance ``contract.DOC_VERSION``
past this constant's CURRENT value, exactly as designed above -- but must
NOT, in that same edit, bump this constant to MATCH the new
``contract.DOC_VERSION``. Instead, bump this constant strictly BELOW
whatever ``contract.DOC_VERSION`` becomes in that edit (never equal to it)
-- a later, separate edit may then raise it further, so long as it still
stays below the ``contract.DOC_VERSION`` current at that time.

What "leaving this constant un-bumped after a move" actually costs (task
13.2 remediation, round 4 correction -- the previous wording here claimed
this was closable by "a periodic confirm still clean edit"; it is not, and
a reviewer's simulation proved it, so the claim is corrected here rather
than repeated): once ANY constant in ``CONSTANT_SOURCES`` carries a
``previous_value``, the registry is permanently "not clean" and
``_assert_constant_registry_asof_matches_reality``'s equality half goes
permanently quiet -- there is no future edit, periodic or otherwise, that
makes the registry clean again, because ``previous_value`` never clears.
The forward, inequality half of the constant trigger
(``_assert_constant_trigger_satisfied``) keeps working after that point --
demanding ``doc_version > CONSTANT_REGISTRY_ASOF_DOC_VERSION`` whenever a
constant is moved -- but it is single-use in a different sense, confirmed by
calling ``_assert_constant_trigger_satisfied`` twice against the same moved
registry: a legitimate move #1 that lands with ``contract.DOC_VERSION``
raised to ``5`` while this constant stays at ``4`` (no integer sits strictly
between them) satisfies the gate; calling it again for a subsequent move #2
that forgets to advance ``contract.DOC_VERSION`` any further -- still
``doc_version = 5``, still ``CONSTANT_REGISTRY_ASOF_DOC_VERSION = 4`` --
raises nothing, because ``5 > 4`` is still true. The constant trigger arms
once, on the first move after the registry was last clean, and is
permanently satisfied thereafter regardless of any later move that skips
its own advance -- this is a real, permanent residual of pinning a
monotonic counter against a value that can only ever be bumped forward by
at most one integer per edit, not a lag that closes itself."""


def _pre_amendment_partial_window_np(
    time_s: tuple[float, ...], watts: tuple[int | None, ...]
) -> float:
    """Independent reimplementation of the pre-13.1 partial-window ``ra30``
    rule -- every point averaged over ``count = min(i + 1, window)`` rather
    than dropping incomplete leading windows (see ``git show
    142fc90:src/fitdocs/metrics/power.py``) -- applied to whatever fixture
    the caller passes in.

    Deliberately reimplemented here, rather than pinned as a literal
    computed once against a fixture that has since been edited (task 13.2
    remediation Finding 1): a literal is bound to the fixture that existed
    when it was written, not to the fixture in this file, so it can go
    stale silently if the fixture below is ever changed. Reusing this
    function against the CURRENT fixture keeps ``new_np != old_np`` a
    statement about the fixture, not about history.

    Reuses the module's own (unchanged) 1 Hz resampling helper --
    fit-ingest task 13.1 changed only the rolling-window rule, not
    resampling -- so this is not a full duplicate of
    ``power.normalized_power``, only of the one rule that changed."""
    resampled = power._resample_power_1hz(time_s, watts)
    window = sources.NP_ROLLING_WINDOW_S.value
    exponent = sources.NP_AVERAGING_EXPONENT.value
    running = 0.0
    ra30: list[float] = []
    for i, value in enumerate(resampled):
        running += value
        if i >= window:
            running -= resampled[i - window]
        count = min(i + 1, window)
        ra30.append(running / count)
    averaging_mean = sum(v**exponent for v in ra30) / len(ra30)
    return float(averaging_mean ** (1 / exponent))


def test_pre_amendment_reimplementation_matches_the_hand_derived_value() -> None:
    """Additional, independent pin (kept per task 13.2 remediation Finding
    1's guidance): :func:`_pre_amendment_partial_window_np` reproduces, for
    this exact fixture, the value ``tests/metrics/test_power.py::test_
    normalized_power_complete_window_raises_np_over_partial_window`` derives
    by hand in full (closed-form arithmetic, worked there independently of
    any module under test). Guards against a mistake in the
    reimplementation itself -- something the fixture-vs-fixture comparison
    in ``_behavior_trigger_np_values`` alone would not catch, since both the
    new and the reimplemented-old values could be wrong together and still
    satisfy ``new_np != old_np``."""
    zeros_s = 29
    plateau_s = 61
    watts: tuple[int | None, ...] = tuple([0] * zeros_s + [300] * plateau_s)
    time_s = tuple(float(k) for k in range(len(watts)))
    old_np = _pre_amendment_partial_window_np(time_s, watts)
    assert old_np == pytest.approx(241.0463756814967, rel=1e-9)


def _behavior_trigger_np_values() -> tuple[float, float]:
    """The new (complete-window) and old (partial-window) normalized-power
    values for a 90-sample fixture -- 29 s at 0 W (a cold start below the
    eventual steady value) then 61 s at 300 W -- built to make the two
    algorithms provably differ. ``old_partial_window_np`` is computed by
    :func:`_pre_amendment_partial_window_np` against THIS SAME fixture (not
    a literal frozen from a fixture that may have since been edited -- task
    13.2 remediation Finding 1), so ``new_np != old_np`` is a live property
    of the fixture below rather than a claim about history. See
    ``test_pre_amendment_reimplementation_matches_the_hand_derived_value``
    above for confirmation this reimplementation matches the independent
    hand-derivation in ``tests/metrics/test_power.py``."""
    zeros_s = 29
    plateau_s = 61
    watts: tuple[int | None, ...] = tuple([0] * zeros_s + [300] * plateau_s)
    time_s = tuple(float(k) for k in range(len(watts)))
    n = len(watts)
    none_floats: tuple[float | None, ...] = (None,) * n
    samples = Samples(
        time_s=time_s,
        heart_rate_bpm=(None,) * n,
        power_w=watts,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )
    new_np = power.normalized_power(samples)
    assert new_np is not None, "fixture must yield a value, not None"
    old_partial_window_np = _pre_amendment_partial_window_np(time_s, watts)
    return new_np, old_partial_window_np


def _assert_constant_trigger_satisfied(
    constants: tuple[CitedConstant[int] | CitedConstant[float], ...],
    doc_version: int,
) -> None:
    """The constant-trigger half of the gate: if any constant in
    ``constants`` carries a ``previous_value``, ``doc_version`` must exceed
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION`."""
    moved = tuple(c for c in constants if c.previous_value is not None)
    if moved:
        assert doc_version > CONSTANT_REGISTRY_ASOF_DOC_VERSION, (
            f"{[c.name for c in moved]} carries a replaced value; "
            f"doc_version ({doc_version}) must exceed "
            f"CONSTANT_REGISTRY_ASOF_DOC_VERSION "
            f"({CONSTANT_REGISTRY_ASOF_DOC_VERSION})"
        )


def _assert_constant_registry_asof_matches_reality(
    constants: tuple[CitedConstant[int] | CitedConstant[float], ...],
    asof_doc_version: int,
    doc_version: int,
) -> None:
    """Task 13.2 remediation, round 4 fix: ties
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION` to the REAL
    ``contract.DOC_VERSION``, but only while ``constants`` is clean -- no
    binding carries a ``previous_value``. That guard is what makes this
    satisfiable forever rather than only once: round 2's unconditional
    ``contract.DOC_VERSION == CONSTANT_REGISTRY_ASOF_DOC_VERSION`` pin broke
    the very first legitimate future re-sourcing, because ``previous_value``
    is permanent and the forward gate then demands ``doc_version > ASOF``
    for every amendment after that, forever, which contradicts an
    unconditional equality pin for any single value of ASOF. Restricting the
    equality to the clean regime avoids that: once a constant moves, this
    half goes quiet and the forward inequality gate
    (:func:`_assert_constant_trigger_satisfied`) takes over instead."""
    registry_clean = not any(c.previous_value is not None for c in constants)
    if registry_clean:
        assert asof_doc_version == doc_version, (
            f"CONSTANT_REGISTRY_ASOF_DOC_VERSION ({asof_doc_version}) must "
            f"match contract.DOC_VERSION ({doc_version}) while the registry "
            "carries no previous_value"
        )


def test_constant_trigger_is_quiet_against_the_real_registry() -> None:
    """Today's real ``CONSTANT_SOURCES`` carries no ``previous_value`` on
    any of its ten bindings, so this half of the gate is vacuous by design
    against the actual registry -- asserted anyway (via the shared helper
    below, not a fresh code path). See
    ``test_constant_trigger_reddens_against_the_real_registry_without_the_
    advance`` below for proof that this same call, against a mutated copy of
    this same real registry, does go red rather than passing vacuously
    forever.

    Task 13.2 remediation, round 4 fix: also ties
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION` to the real
    ``contract.DOC_VERSION`` via
    :func:`_assert_constant_registry_asof_matches_reality` -- see
    ``test_constant_registry_asof_reddens_when_it_drifts_from_doc_version``
    below for proof this catches a one-character edit to the ASOF constant
    that the forward-only gate above cannot."""
    moved = tuple(c for c in sources.CONSTANT_SOURCES if c.previous_value is not None)
    assert moved == (), "no constant should carry a previous_value today"
    _assert_constant_trigger_satisfied(sources.CONSTANT_SOURCES, contract.DOC_VERSION)
    _assert_constant_registry_asof_matches_reality(
        sources.CONSTANT_SOURCES,
        CONSTANT_REGISTRY_ASOF_DOC_VERSION,
        contract.DOC_VERSION,
    )


def test_constant_registry_asof_reddens_when_it_drifts_from_doc_version() -> None:
    """Discrimination for the new reality pin (task 13.2 remediation, round
    4 acceptance case 1): with the real, clean ``CONSTANT_SOURCES`` and the
    real ``contract.DOC_VERSION`` (4), an ASOF value one below the real
    ``CONSTANT_REGISTRY_ASOF_DOC_VERSION`` (the exact shape of the
    one-character ``4 -> 3`` edit that survived green in round 3) must
    raise. Confirms this specific one-character edit -- previously
    undetectable -- is now caught."""
    drifted_asof = CONSTANT_REGISTRY_ASOF_DOC_VERSION - 1
    assert drifted_asof != contract.DOC_VERSION  # falsity in the starting state
    with pytest.raises(AssertionError, match="must match contract.DOC_VERSION"):
        _assert_constant_registry_asof_matches_reality(
            sources.CONSTANT_SOURCES, drifted_asof, contract.DOC_VERSION
        )


def test_constant_registry_asof_pin_is_quiet_once_a_constant_moves() -> None:
    """Positive-direction companion (task 13.2 remediation, round 4
    acceptance case 3, half B): once the registry carries a moved constant,
    the reality pin must NOT fire even though ``asof_doc_version`` and
    ``doc_version`` are no longer equal -- this is what keeps the pin from
    reproducing round 2's unsatisfiability the moment a legitimate
    re-sourcing lands. Built from a mutated copy of the real registry (same
    fixture as the forward-gate tests above), with ``doc_version`` advanced
    past ``CONSTANT_REGISTRY_ASOF_DOC_VERSION`` exactly as the forward gate
    requires."""
    moved_constant = dataclasses.replace(
        sources.TSS_SCALE, previous_value=sources.TSS_SCALE.value + 1.0
    )
    mutated_registry = tuple(
        moved_constant if c is sources.TSS_SCALE else c
        for c in sources.CONSTANT_SOURCES
    )
    moved = tuple(c for c in mutated_registry if c.previous_value is not None)
    assert moved, "fixture failed to construct a moved constant"  # reachability

    advanced_doc_version = CONSTANT_REGISTRY_ASOF_DOC_VERSION + 1
    assert advanced_doc_version != CONSTANT_REGISTRY_ASOF_DOC_VERSION  # not equal
    _assert_constant_registry_asof_matches_reality(
        mutated_registry, CONSTANT_REGISTRY_ASOF_DOC_VERSION, advanced_doc_version
    )
    _assert_constant_trigger_satisfied(mutated_registry, advanced_doc_version)


def test_constant_trigger_reddens_when_a_moved_constant_ships_without_the_advance() -> (
    None
):
    """Discrimination for the constant trigger: construct a synthetic
    registry where one constant carries a ``previous_value`` (a future
    re-sourcing that moved a value), pass ``doc_version`` equal to
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION` itself -- the exact shape a
    forgotten advance would take, since a re-sourcing that forgets to bump
    ``contract.DOC_VERSION`` leaves it sitting at whatever that constant
    already records -- and confirm the shared gate helper raises."""
    moved_constant = dataclasses.replace(
        sources.TSS_SCALE, previous_value=sources.TSS_SCALE.value + 1.0
    )
    fake_registry = tuple(
        moved_constant if c is sources.TSS_SCALE else c
        for c in sources.CONSTANT_SOURCES
    )
    moved = tuple(c for c in fake_registry if c.previous_value is not None)
    assert moved, "fixture failed to construct a moved constant"  # reachability

    with pytest.raises(AssertionError, match="carries a replaced value"):
        _assert_constant_trigger_satisfied(
            fake_registry, CONSTANT_REGISTRY_ASOF_DOC_VERSION
        )


def test_constant_trigger_reddens_against_the_real_registry_without_the_advance() -> (
    None
):
    """Direct reproduction of the forgotten-advance scenario against
    ``sources.CONSTANT_SOURCES`` itself (not a synthetic tuple): mutate the
    real ``TSS_SCALE`` binding in place to carry a ``previous_value``, pair
    it with a SYNTHETIC ``doc_version`` equal to
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION` -- the exact shape a
    forgotten advance would take -- and confirm the shared gate helper
    raises on that pairing.

    Task 13.2 remediation Finding 2: this used to assert the REAL
    ``contract.DOC_VERSION == CONSTANT_REGISTRY_ASOF_DOC_VERSION`` as a
    precondition. That is unsatisfiable forever after the first legitimate
    future re-sourcing: ``CitedConstant.previous_value`` is a PERMANENT
    provenance record (``src/fitdocs/citation.py``, Req 15.3), so once any
    constant carries one, the forward gate's ``moved`` is non-empty for
    every amendment after that, and the forward gate then demands
    ``doc_version > ASOF`` -- which contradicts a precondition demanding
    ``doc_version == ASOF`` for any single value of ASOF. A synthetic
    ``doc_version`` here decouples this test from that future collision
    while still proving the forward implication is not vacuously true
    forever just because ``contract.DOC_VERSION`` has already advanced past
    ``_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE`` for the (independent)
    behavior-trigger reason in this same amendment. See
    ``test_constant_trigger_satisfied_when_asof_is_bumped_alongside_the_
    advance`` below for the companion positive-direction proof that the
    corrected maintenance instruction is actually satisfiable."""
    moved_constant = dataclasses.replace(
        sources.TSS_SCALE, previous_value=sources.TSS_SCALE.value + 1.0
    )
    mutated_registry = tuple(
        moved_constant if c is sources.TSS_SCALE else c
        for c in sources.CONSTANT_SOURCES
    )
    moved = tuple(c for c in mutated_registry if c.previous_value is not None)
    assert moved, "fixture failed to construct a moved constant"  # reachability
    synthetic_doc_version = CONSTANT_REGISTRY_ASOF_DOC_VERSION

    with pytest.raises(AssertionError, match="carries a replaced value"):
        _assert_constant_trigger_satisfied(mutated_registry, synthetic_doc_version)


def test_constant_trigger_satisfied_when_asof_is_bumped_alongside_the_advance() -> None:
    """Positive-direction companion to the test above (task 13.2 remediation
    Finding 2): the legitimate future the corrected maintenance instruction
    describes -- a constant moves, and in that SAME edit both
    ``contract.DOC_VERSION`` and :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION`
    advance together -- must NOT raise. Both are monkeypatched one past
    their current real values (rather than asserting anything about the
    real, live constants) so this proves the gate is satisfiable, not merely
    that it can be made to fail."""
    moved_constant = dataclasses.replace(
        sources.TSS_SCALE, previous_value=sources.TSS_SCALE.value + 1.0
    )
    mutated_registry = tuple(
        moved_constant if c is sources.TSS_SCALE else c
        for c in sources.CONSTANT_SOURCES
    )
    moved = tuple(c for c in mutated_registry if c.previous_value is not None)
    assert moved, "fixture failed to construct a moved constant"  # reachability

    module = sys.modules[__name__]
    bumped_asof = CONSTANT_REGISTRY_ASOF_DOC_VERSION + 1
    bumped_doc_version = bumped_asof + 1
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(module, "CONSTANT_REGISTRY_ASOF_DOC_VERSION", bumped_asof)
        _assert_constant_trigger_satisfied(mutated_registry, bumped_doc_version)


def test_constant_trigger_is_permanently_quiet_after_the_first_satisfied_move() -> None:
    """Backs the permanent-residual claim in
    :data:`CONSTANT_REGISTRY_ASOF_DOC_VERSION`'s own docstring (task 13.2
    remediation, round 4 fix -- the previous wording there falsely called
    this closable by a periodic edit). Move #1 satisfies the forward gate
    (``doc_version`` raised to one past ``CONSTANT_REGISTRY_ASOF_DOC_VERSION``,
    exactly as the maintenance instruction requires). Move #2 then repeats
    the SAME ``doc_version``/ASOF pairing -- the shape a forgotten second
    advance would take -- and the same shared helper is called again rather
    than re-derived, so this cannot silently diverge from the gate actually
    in force. If the gate were closable by a later "confirm still clean"
    edit, this second call would need to raise; it does not."""
    moved_constant = dataclasses.replace(
        sources.TSS_SCALE, previous_value=sources.TSS_SCALE.value + 1.0
    )
    mutated_registry = tuple(
        moved_constant if c is sources.TSS_SCALE else c
        for c in sources.CONSTANT_SOURCES
    )
    moved = tuple(c for c in mutated_registry if c.previous_value is not None)
    assert moved, "fixture failed to construct a moved constant"  # reachability

    move_1_doc_version = CONSTANT_REGISTRY_ASOF_DOC_VERSION + 1
    _assert_constant_trigger_satisfied(mutated_registry, move_1_doc_version)  # move #1

    move_2_doc_version = move_1_doc_version  # move #2: no further advance
    _assert_constant_trigger_satisfied(mutated_registry, move_2_doc_version)


def test_behavior_trigger_fixture_provably_differs_between_old_and_new() -> None:
    """The behavior trigger's fixture must be a case where the two
    behaviors provably differ (task 13.2's own requirement), not merely
    asserted to. Confirms the falsity-in-the-starting-state: the two values
    are not equal, and the direction matches task 13.1's stated claim
    (dropping the low leading partial-window averages raises NP)."""
    new_np, old_np = _behavior_trigger_np_values()
    assert new_np != old_np
    assert new_np > old_np


def _assert_behavior_trigger_satisfied(doc_version: int) -> None:
    """The behavior trigger's forward assertion, shared between the "today's
    actual state" test and its discrimination test below so the
    discrimination test cannot silently re-write the comparison inline and
    stay green under a mutation the shared assertion would catch."""
    assert doc_version > _PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE, (
        "the NP rolling-mean conformance change (task 13.1) moves normalized "
        "power and its downstream metrics for this fixture; contract."
        f"DOC_VERSION must advance past {_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE}"
    )


def test_behavior_trigger_couples_the_np_conformance_change_to_the_advance() -> None:
    """Forward direction, and today's actual state: fit-ingest task 13.1's
    NP rolling-mean conformance change actually moved the value for this
    fixture in this amendment (not universally -- see
    ``contract.DOC_VERSION``'s own docstring on the constant-power
    exception), so ``contract.DOC_VERSION`` must exceed
    ``_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE`` regardless of whether any constant
    carries a ``previous_value`` -- this is the trigger that actually fires
    in this amendment, independently of the (currently vacuous) constant
    trigger above."""
    new_np, old_np = _behavior_trigger_np_values()
    assert new_np != old_np, "the behavior trigger must actually be firing"
    _assert_behavior_trigger_satisfied(contract.DOC_VERSION)


def test_behavior_trigger_reddens_if_the_advance_did_not_happen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discrimination for the behavior trigger: with the fixture still
    proving the two behaviors differ, force ``contract.DOC_VERSION`` back
    to its pre-amendment baseline -- the exact shape a forgotten advance
    would take -- and confirm the SAME shared forward assertion used in
    ``test_behavior_trigger_couples_the_np_conformance_change_to_the_advance``
    (called here, not re-written inline) goes red. Proves this trigger,
    independently of the constant trigger, is what would catch a forgotten
    advance in this actual amendment."""
    new_np, old_np = _behavior_trigger_np_values()
    assert new_np != old_np, "the behavior trigger must actually be firing"
    monkeypatch.setattr(
        contract, "DOC_VERSION", _PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE
    )
    with pytest.raises(AssertionError):
        _assert_behavior_trigger_satisfied(contract.DOC_VERSION)


def test_no_advance_required_only_when_both_triggers_are_quiet() -> None:
    """18.1, 18.4: 'no advance is required' is a conclusion only when BOTH
    triggers are quiet -- stated here explicitly rather than left to
    omission. Today the constant trigger is quiet (no ``CitedConstant``
    carries a ``previous_value``) but the behavior trigger is not (task
    13.1's NP conformance change), so the conjunction is false and the
    advance *is* required -- which is exactly why ``contract.DOC_VERSION``
    moved from ``_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE`` to its current value in
    this same change."""
    constant_trigger_quiet = not any(
        c.previous_value is not None for c in sources.CONSTANT_SOURCES
    )
    new_np, old_np = _behavior_trigger_np_values()
    behavior_trigger_quiet = new_np == old_np

    assert constant_trigger_quiet  # today's actual, vacuous-by-design state
    assert not behavior_trigger_quiet  # today's actual, firing state

    both_quiet = constant_trigger_quiet and behavior_trigger_quiet
    assert not both_quiet, "the conjunction must be false for the advance to be owed"
    assert contract.DOC_VERSION > _PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE


# --- MigrationGate, second instance (chore/power-absent-sample-fill; Req
#     15.3, 18.1, 18.4, 18.5) -----------------------------------------------
#
# A second behavior-trigger event, same shape as task 13.2's above and
# deliberately reusing it rather than inventing a new mechanism: the
# 2026-07-30 ruling on
# ``.kiro/queue/2026-07-30-absent-power-sample-filled-with-zero.md`` changes
# how an unrecorded (``None``) power sample forward-fills in the 1 Hz
# resample (forward-fills the last RECORDED value, rather than a fabricated
# ``0.0``; a leading dropout before the first recorded sample truncates the
# grid instead of fabricating anything for it either), which moves
# normalized power (and IF/VI/TSS/EF downstream) for any activity whose
# power stream carries a genuine device dropout -- independently of whether
# any ``CONSTANT_SOURCES`` entry moved (none did: the ``FitdocsChoice``
# this ruling was recorded against, ``POWER_ABSENT_SAMPLE_FILL``, was never
# registered there while it existed, and the ruling removed it entirely --
# see ``sources.py``). This section's own frozen historical
# marker is, like ``_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE`` above, an
# inert annotation of this one event once ``contract.DOC_VERSION`` has moved
# past it for any reason -- not a live, repeatable gate. That is a stated,
# accepted property of this trigger shape (see that constant's own docstring
# for the full argument), not a defect introduced here a second time.


_PRE_FILL_RULING_DOC_VERSION_HISTORICAL_VALUE: Final[int] = 4
"""The document-format version this event (chore/power-absent-sample-fill)
started from -- ``contract.DOC_VERSION``'s own docstring records this as the
version fit-ingest task 13.2 raised it to. Exactly as inert as
:data:`_PRE_AMENDMENT_DOC_VERSION_HISTORICAL_VALUE` above and for the same
reason: once ``contract.DOC_VERSION`` has advanced past ``4`` for any
reason -- which it already has, in this very event -- the forward assertion
``doc_version > this value`` holds forever afterward, so this is a
self-relative discrimination fixture (monkeypatch the version back to this
constant, then show the same forward assertion reds), not a check against
any future, independent piece of reality. A third event that changes a
metric value with no registered constant behind it needs its own similarly-
named marker at whatever ``contract.DOC_VERSION`` is by then -- this one
does not generalize forward, by design, the same way its predecessor does
not."""


def _fill_ruling_np_values() -> tuple[float, float]:
    """The new (forward-fill) and old (fabricated-``0.0``-fill) normalized-
    power values for a fixture with a genuine device dropout AFTER its first
    recorded sample: 300 W for 25 s, then a 10 s dropout (``None``), then
    100 W for 25 s (60 samples, span 59 s >= 30 s min span). Distinguishing
    values on either side of the gap (300 vs 100) are what make "forward-fill
    the preceding value" and "fabricate 0.0" provably differ on this fixture
    -- a same-value-both-sides fixture would not (see
    ``tests/metrics/test_power.py::
    test_normalized_power_none_gap_forward_fills_from_preceding_sample`` for
    the full argument). ``old_zero_fill_np`` is computed by reimplementing
    ONLY the (unchanged) fabricated-zero fill rule directly against this same
    fixture -- reusing :mod:`fitdocs.metrics.power`'s own (unchanged) rolling-
    mean and averaging-exponent machinery, so this is not a full duplicate of
    ``power.normalized_power``, only of the one rule this event changed."""
    zeros_before = 25
    gap = 10
    after = 25
    watts: tuple[int | None, ...] = (
        tuple([300] * zeros_before) + tuple([None] * gap) + tuple([100] * after)
    )
    time_s = tuple(float(k) for k in range(len(watts)))
    n = len(watts)
    none_floats: tuple[float | None, ...] = (None,) * n
    samples = Samples(
        time_s=time_s,
        heart_rate_bpm=(None,) * n,
        power_w=watts,
        cadence_rpm=none_floats,
        speed_mps=none_floats,
        distance_m=none_floats,
        altitude_m=none_floats,
        latitude_deg=none_floats,
        longitude_deg=none_floats,
        temperature_c=none_floats,
    )
    new_np = power.normalized_power(samples)
    assert new_np is not None, "fixture must yield a value, not None"

    # Independent reimplementation of the fabricated-``0.0`` fill this event
    # replaces -- a bare 0.0 substitution for every None sample, rather than
    # this module's own (changed) forward-fill.
    old_resampled = [0.0 if w is None else float(w) for w in watts]
    window = sources.NP_ROLLING_WINDOW_S.value
    exponent = sources.NP_AVERAGING_EXPONENT.value
    ra30 = power._trailing_rolling_mean(old_resampled, window)
    assert ra30, "fixture must clear the rolling-window guard"
    old_averaging_mean = sum(v**exponent for v in ra30) / len(ra30)
    old_zero_fill_np = float(old_averaging_mean ** (1 / exponent))
    return new_np, old_zero_fill_np


def _assert_fill_ruling_trigger_satisfied(doc_version: int) -> None:
    """The fill-ruling trigger's forward assertion, shared between the
    "today's actual state" test and its discrimination test below, same
    discipline as :func:`_assert_behavior_trigger_satisfied` above."""
    assert doc_version > _PRE_FILL_RULING_DOC_VERSION_HISTORICAL_VALUE, (
        "the absent-power-sample forward-fill ruling "
        "(chore/power-absent-sample-fill) moves normalized power and its "
        "downstream metrics for this fixture; contract.DOC_VERSION must "
        f"advance past {_PRE_FILL_RULING_DOC_VERSION_HISTORICAL_VALUE}"
    )


def test_fill_ruling_fixture_provably_differs_between_old_and_new() -> None:
    """The fill-ruling trigger's fixture must be a case where the two
    behaviors provably differ, not merely asserted to -- falsity in the
    starting state, same discipline as the rolling-window trigger's own
    test above."""
    new_np, old_np = _fill_ruling_np_values()
    assert new_np != old_np


def test_fill_ruling_trigger_couples_the_forward_fill_change_to_the_advance() -> None:
    """Forward direction, and today's actual state: the absent-power-sample
    forward-fill ruling actually moved the value for this fixture in this
    event, so ``contract.DOC_VERSION`` must exceed
    ``_PRE_FILL_RULING_DOC_VERSION_HISTORICAL_VALUE`` regardless of whether
    any constant carries a ``previous_value`` -- the ``FitdocsChoice`` this
    ruling was recorded against was never registered in
    ``CONSTANT_SOURCES``, and the ruling removed it entirely, so the
    constant trigger above cannot see this event either way."""
    new_np, old_np = _fill_ruling_np_values()
    assert new_np != old_np, "the fill-ruling trigger must actually be firing"
    _assert_fill_ruling_trigger_satisfied(contract.DOC_VERSION)


def test_fill_ruling_trigger_reddens_if_the_advance_did_not_happen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Discrimination for the fill-ruling trigger: with the fixture still
    proving the two behaviors differ, force ``contract.DOC_VERSION`` back to
    its pre-event baseline -- the exact shape a forgotten advance would take
    -- and confirm the SAME shared forward assertion used in
    ``test_fill_ruling_trigger_couples_the_forward_fill_change_to_the_advance``
    (called here, not re-written inline) goes red."""
    new_np, old_np = _fill_ruling_np_values()
    assert new_np != old_np, "the fill-ruling trigger must actually be firing"
    monkeypatch.setattr(
        contract, "DOC_VERSION", _PRE_FILL_RULING_DOC_VERSION_HISTORICAL_VALUE
    )
    with pytest.raises(AssertionError):
        _assert_fill_ruling_trigger_satisfied(contract.DOC_VERSION)

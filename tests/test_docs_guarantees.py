"""Preserved-guarantee assertions over the shipped documentation *set* (design:
inbox UserDocs, Req 8.4).

These are cross-cutting guarantee properties, in the same spirit as
``tests/test_determinism.py``'s preserved-guarantee section (network-free
plugin discovery, the frozen runtime-dependency baseline): each assertion here
pins a *statement*, not a file. Two of the inbox feature's user-facing
guarantees -- that no configuration ever deletes an inbox file (Req 6.6) and
that fitdocs performs no watching or scheduling of any kind (Req 8.2) -- are
guarantees rather than mere descriptions, and the `distribution` spec later
rewrites `README.md` wholesale and builds a documentation set whose entry
point does not yet mention the inbox at all. Asserting these phrases against
one named file (`README.md`) would pass today and then silently stop being
checked the moment that rewrite moves the text into a dedicated
`docs/inbox.md` page.

So each assertion below searches the *concatenation* of every markdown file in
the shipped documentation set -- the project README plus every top-level
`docs/*.md` file (task 5.7 scopes this to top-level `docs/` pages, excluding
`docs/reference/`, which is retained research/provenance material rather than
user documentation) -- rather than one named path. The phrasing survives the
text moving between files, being split across sections, or being indexed from
a new entry point, as long as the guarantee sentence itself keeps shipping
somewhere.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import fitdocs
import fitdocs.load
from fitdocs.config import DATA_ROOT_ENV, POINTER_RELPATH
from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL

_REPO_ROOT = Path(__file__).resolve().parent.parent
_PROJECT_URL_PREFIX = "https://github.com/joshua-stauffer/fitdocs/blob/main/"


def _shipped_documentation_text(root: Path = _REPO_ROOT) -> str:
    """The concatenated, whitespace-normalized text of every markdown file
    fitdocs ships to users as *user-facing* documentation, read from under
    ``root``.

    ``root / "README.md"`` plus every top-level ``*.md`` file directly inside
    ``root / "docs"`` -- **not** recursive, and in particular **not**
    ``root / "docs" / "reference"``, which is retained research material
    (task 5.7's docstring/README note), not user documentation. Task 5.7
    (5.2 review, mutation M10) found this corpus builder previously walked
    ``docs/**/*.md`` recursively, so the never-delete guarantee's guard test
    below was satisfied by a meta-mention of the guarantee's own wording
    inside ``docs/reference/history-rewrites.md`` -- a durable record
    *describing* the guard, not the guard's own subject matter -- regardless
    of whether the real inbox documentation still stated the guarantee at
    all. Scoping to top-level ``docs/*.md`` closes that: a subject-matter
    sentence that moves between the README and any top-level ``docs/`` page
    is still found here without this test changing, but a page under
    ``docs/reference/`` can no longer stand in for it.

    Runs of whitespace (including markdown's hard line wraps) are collapsed
    to a single space before matching, so a substring assertion is not
    sensitive to where in the prose a paragraph happens to wrap.

    ``root`` defaults to the real repository root and is a parameter (task
    4.2's corpus-builder collapse) so a positive control can point it at a
    synthetic tree under ``tmp_path`` -- the replacement for the deleted,
    writeup-dependent positive control that used to prove this walk finds
    real content rather than passing vacuously (Req 3.3, 3.4). Before task
    4.2 this module carried a second builder,
    ``_shipped_documentation_text_excluding_reference_writeup``, that
    additionally filtered out the retained research writeup; that
    exclusion's only caller was retired at the same task (Req 11.7), so the
    second builder is gone rather than kept as an unused variant. Task 5.7
    reintroduces the exclusion, generalized to the whole ``docs/reference/``
    tree rather than one named writeup file, directly inside the builder
    itself rather than as an opt-in second function.
    """
    paths = [root / "README.md", *sorted((root / "docs").glob("*.md"))]
    # Joined with a period sentinel, not a blank line: the whitespace collapse
    # below would turn "\n\n" into a single space, letting a bounded ``[^.]``
    # window in a guarantee regex straddle two documents and match a phrase
    # assembled from the tail of one file and the head of the next. ``[^.]``
    # cannot cross a period, so the sentinel confines every match to one file.
    joined = " . ".join(
        path.read_text(encoding="utf-8") for path in paths if path.is_file()
    )
    return re.sub(r"\s+", " ", joined)


def test_shipped_documentation_corpus_builder_reads_from_the_supplied_root(
    tmp_path: Path,
) -> None:
    """Req 3.3/3.4's replacement positive control for
    :func:`_shipped_documentation_text`. The predecessor control this
    replaces, the deleted writeup-mentions-the-methodology positive control,
    depended on the retained research writeup and was retired at task 3.1
    when that file was deleted from the working tree (Req 1.1). This control
    depends on no removed file: it plants markers under a fresh ``tmp_path``.

    Builds a synthetic tree with a README and a top-level docs file, each
    holding a distinct marker string that appears nowhere in the real
    repository, and asserts both markers are found when ``root`` points at
    the synthetic tree.

    Task 5.7 re-based this control's second marker from a *nested*
    ``docs/nested/guide.md`` to a *top-level* ``docs/guide.md``: the corpus
    builder is deliberately non-recursive now (5.7's corpus-scoping fix,
    below), so a marker one directory level below ``docs/`` would no longer
    be found and this control would wrongly report the builder broken. The
    sibling test below,
    ``test_shipped_documentation_corpus_builder_excludes_docs_reference``,
    is what now pins the exclusion of anything below ``docs/`` itself.

    Mutation caught (verified, then reverted byte-identically): ignoring
    ``root`` and hard-coding ``_REPO_ROOT`` inside
    ``_shipped_documentation_text`` (the exact mutation design.md names for
    this guard) reds both assertions below as the sole failure in this file,
    because the real repository's README and docs never contain either
    synthetic marker; reverting restores green.
    """
    (tmp_path / "docs").mkdir(parents=True)
    marker_readme = "zzqv-marker-readme-70142"
    marker_doc = "zzqv-marker-doc-58203"
    (tmp_path / "README.md").write_text(marker_readme, encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text(marker_doc, encoding="utf-8")

    synthetic_corpus = _shipped_documentation_text(root=tmp_path)
    assert marker_readme in synthetic_corpus
    assert marker_doc in synthetic_corpus


def test_shipped_documentation_corpus_builder_excludes_docs_reference(
    tmp_path: Path,
) -> None:
    """Task 5.7's corpus-scoping fix (5.2 review, mutation M10): a file under
    ``docs/reference/`` never enters :func:`_shipped_documentation_text`'s
    corpus, even though it sits inside ``docs/``.

    Extends the synthetic-tree pattern the sibling positive control above
    uses: plants a marker inside ``docs/reference/x.md`` -- one directory
    level below ``docs/``, exactly where the real
    ``docs/reference/history-rewrites.md`` meta-mention lived -- and asserts
    the marker is *absent* from the corpus, alongside a second, top-level
    marker asserted *present* so the same run also proves the builder is not
    simply reading nothing at all (the vacuous-exclusion failure mode: a
    builder that excludes everything would also make the reference marker
    "absent" without discriminating anything).

    Mutation caught (verified, then reverted byte-identically): reverting
    :func:`_shipped_documentation_text` to its pre-5.7 recursive walk
    (``(root / "docs").rglob("*.md")``) makes the reference marker assertion
    fail as the sole failure in this file -- the exact regression this test
    exists to close.
    """
    (tmp_path / "docs" / "reference").mkdir(parents=True)
    marker_top_level = "zzqv-marker-top-level-40917"
    marker_reference = "zzqv-marker-reference-83271"
    (tmp_path / "README.md").write_text("readme", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text(marker_top_level, encoding="utf-8")
    (tmp_path / "docs" / "reference" / "x.md").write_text(
        marker_reference, encoding="utf-8"
    )

    corpus = _shipped_documentation_text(root=tmp_path)
    assert marker_top_level in corpus, (
        "the builder excluded a top-level docs/*.md file too -- it should "
        "only exclude docs/reference/, not everything under docs/"
    )
    assert marker_reference not in corpus


def test_inbox_never_delete_guarantee_is_published_somewhere_in_the_docs() -> None:
    """No inbox configuration ever deletes a file (Req 6.6) -- stated as a
    guarantee, not merely implied by describing the leave-in-place default.

    The assertion is a single bounded-proximity regex, not two independent
    substring checks: "deletes an inbox file" already appears a second time
    in the leave-disposition sentence ("never writes, moves, renames, or
    deletes an inbox file"), so a two-substring check survives deleting the
    guarantee outright; and an *inverted* sentence -- "the `purge`
    disposition deletes an inbox file once archived; no configuration
    prevents that" -- would satisfy both substrings while asserting the
    opposite guarantee.
    Requiring "ever deletes an inbox file" to appear shortly *after* "no
    configuration", in that order, is what pins the actual statement rather
    than two keywords that happen to both be present in the corpus.

    Mutation caught: dropping this sentence, or replacing it with the
    inverted sentence above, fails this test regardless of which file in the
    shipped documentation set the sentence lives in.
    """
    lowered = _shipped_documentation_text().lower()
    assert re.search(r"no configuration[^.]{0,20}ever deletes an inbox file", lowered)


def test_inbox_no_watching_guarantee_is_published_somewhere_in_the_docs() -> None:
    """fitdocs performs no watching or scheduling of any kind (Req 8.2), and a
    drain happens only when ``fitdocs sync`` is invoked.

    Both are bounded-proximity regexes, not independent substring checks:
    "fitdocs sync" already appears in ``docs/ownership-contract.md`` and
    "only when" in both that file and
    ``docs/reference/fitdocs-ai-reference.md``, so an independent-substring
    assertion is satisfied by the pre-existing corpus regardless of what the
    inbox documentation says -- it would still pass if the "only when ...
    invoked" sentence were deleted entirely, or if the whole paragraph were
    replaced with a directly contradictory one (a background helper "may
    pick files up for you"). Requiring the actual guarantee's words in their
    actual order, within a small window, is what pins the statement.

    Mutation caught: dropping either sentence, or replacing the paragraph
    with a contradictory one that keeps the "no watching and no scheduling"
    clause but drops the "only when ... invoked" clause, fails this test
    regardless of which file in the shipped documentation set it lives in.
    """
    lowered = _shipped_documentation_text().lower()
    assert re.search(r"performs no watching and no scheduling", lowered)
    assert re.search(
        r"drain happens only when [^.]{0,40}fitdocs sync[^.]{0,40}invoked", lowered
    )


# --- withdrawal record: the shipped-documentation half (Req 11.7, 11.9) -----
#
# RETIRED here (encumbered-content-purge, task 4.2), not re-based: the
# deleted shipped-documentation token-absence guard (Req 13.3). It searched
# shipped documentation for the identifying token literally. Req 11.1 forbids
# retaining that token in any tracked file, including this module's own
# source and docstrings, so re-basing it onto a neutral needle was not
# available the way it was for the steering guard below -- there is no
# neutral form of "asserts this literal token is present" -- and Req 11.7
# requires retirement instead.
#
# Retired earlier, recorded here for completeness rather than left an
# unstated consequence: the two token-present positive controls that lived
# inside the deleted writeup-mentions-the-methodology positive control test
# died at task 3.1, when the writeup they read was deleted (Req 1.1) -- not
# a retirement this task performs, but one this task's own Req 11.7
# accounting would otherwise leave unnamed.
#
# Req 11.9, stated rather than left implicit: retiring the token-absence
# guard gives up detection this repository previously had. No test in this
# repository today asserts that no shipped document (README.md or
# docs/**/*.md) claims fitdocs ships the withdrawn methodology as an
# available option. No standing guard scans the repository for identifying
# tokens yet, either -- `tests/test_forbidden_strings.py` (run and confirmed:
# 24 passed, 0 skipped, identically with `FITDOCS_FORBIDDEN_STRINGS` set and
# unset) is a meta-test that pins `tests/_forbidden_strings.py`'s loader and
# matcher against synthetic fixtures; it never reads this repository's own
# documentation. Task 4.3 will add the standing guard that scans tracked
# content and path names for whatever strings the maintainer supplies via
# `FITDOCS_FORBIDDEN_STRINGS`, matched by substring. Even once that guard
# exists, it will catch only a paste that names the third party in a form
# matching a supplied string; a paste that describes the withdrawn
# methodology's evaluation in plain language, naming no one, matches no
# supplied string and is not caught by 4.3 or by anything else in this
# repository -- a residue this purge accepts rather than closes.


def _steering_pairing_violations(steering_root: Path) -> list[Path]:
    """Every ``*.md`` file under ``steering_root`` that mentions the neutral
    evaluation vocabulary ("third party" / "third-party") without also
    recording the withdrawal ("withdraw") in the same file.

    Factored out of the test below (task 4.2) so a synthetic tree that
    VIOLATES the pairing property can exercise this function directly. A
    fixture that already satisfies a property pins nothing -- the real
    ``.kiro/steering/`` tree currently has no violation, so a test that only
    ever runs this function against the real tree cannot demonstrate the
    function actually detects one.
    """
    violations: list[Path] = []
    for path in sorted(steering_root.rglob("*.md")):
        text = path.read_text(encoding="utf-8").lower()
        mentions_evaluation = "third party" in text or "third-party" in text
        if mentions_evaluation and "withdraw" not in text:
            violations.append(path)
    return violations


def test_every_steering_file_mentioning_the_withdrawn_methodology_also_records_its_withdrawal() -> (  # noqa: E501
    None
):
    """Req 13.3's steering-specific half (task 6.4 round 3, finding 2), re-based
    by task 3.10 from the prior guard that matched on the identity token
    itself, and re-based again by task 4.2 onto the pairing property below.
    Req 11.1 forbids retaining that token in any tracked file, including this
    one, so a needle built from it could only ever find nothing from task
    3.10 forward.

    This match instead fires on the neutral evaluation vocabulary Req 11.5
    requires retained -- "third party" / "third-party". The property this
    pins is the **pairing**: every steering file matching that needle also
    contains "withdraw" somewhere in the same file, checked by
    :func:`_steering_pairing_violations`.

    Today: ``roadmap.md`` and ``structure.md`` each mention both needles;
    every other steering file mentions neither, so this passes with zero
    further steering edits.

    Coverage limit, stated rather than left implicit (Req 11.9): the needle
    is confounded on the real tree. ``roadmap.md`` also matches
    "third-party" in two sentences unrelated to the withdrawn methodology (a
    plugin-api extension point, a plugin displacing a built-in calculator),
    so today's green result is not evidence that *those* mentions are paired
    with a withdrawal -- only that some mention in the file is.

    Second coverage limit, measured directly against this finished guard
    rather than assumed (Req 11.9): a steering paste that describes the
    withdrawn methodology's evaluation in plain language, without using the
    literal "third party" / "third-party" needle and naming no one, is not
    flagged. Confirmed by planting such a sentence in
    ``.kiro/steering/product.md`` and re-running the full suite: it stays
    green. Two distinct cases follow this guard's boundary, stated
    separately because they resolve differently once task 4.3 lands: a
    steering paste that names the third party in a form matching a string
    the maintainer supplies to ``ForbiddenStrings`` (task 4.3) will be caught
    there, once that guard exists and the data is supplied. A steering paste
    that describes the evaluation in plain language and names no one matches
    no supplied string; it is caught by this guard only when it happens to
    use the neutral vocabulary, and by nothing in this repository otherwise
    -- an accepted residue, not a deferral to a guard that will close it.

    Mutation caught: adding a line containing "third party" (and no
    "withdraw") to a steering file that has neither today -- confirmed
    directly against ``.kiro/steering/product.md`` -- reds this test as a
    sole failure naming that file; reverting restores it byte-identically.
    See the sibling test below for the synthetic-fixture pin of
    :func:`_steering_pairing_violations` itself, which is the positive
    control this test's own assertion depends on (Req 3.3, 3.4).

    Positive control: the loop body's assertion sits entirely inside the
    ``mentioning`` loop, and the file set it iterates was never asserted
    non-empty -- so a renamed or moved ``.kiro/steering/`` directory, or
    ``steering_root`` drifting relative to this file, leaves the loop body
    unreached and this test green having asserted nothing at all. Confirmed
    directly: pointing ``steering_root`` at a nonexistent path makes
    ``rglob`` yield no files, ``mentioning`` below empty, and -- absent the
    assertion added here -- the test would still pass. The ``mentioning``
    list is collected first and asserted non-empty before any per-file check
    runs, so that failure mode is now itself a failure.
    """
    steering_root = _REPO_ROOT / ".kiro" / "steering"
    mentioning = [
        path
        for path in sorted(steering_root.rglob("*.md"))
        if "third party" in path.read_text(encoding="utf-8").lower()
        or "third-party" in path.read_text(encoding="utf-8").lower()
    ]
    assert mentioning, (
        "no steering file mentions the third party -- the guard is scanning "
        "the wrong directory (steering_root may have drifted or been "
        "renamed)"
    )
    violations = _steering_pairing_violations(steering_root)
    assert not violations, (
        "steering file(s) mention the third party without also recording "
        "the withdrawal in the same file: "
        f"{[str(p.relative_to(_REPO_ROOT)) for p in violations]}"
    )


def test_synthetic_steering_tree_with_an_unpaired_evaluation_mention_reds_the_pairing_check(  # noqa: E501
    tmp_path: Path,
) -> None:
    """Req 3.3/3.4's positive control for :func:`_steering_pairing_violations`:
    a fixture that VIOLATES the pairing property, not one that already
    satisfies it. The real ``.kiro/steering/`` tree has no violation today, so
    a test that only ever runs the function against the real tree could not
    tell a genuinely discriminating function from one that always returns
    ``[]`` -- the pre-satisfied-fixture anti-pattern.

    Builds a synthetic steering tree with three files: one mentions the
    evaluation and also records the withdrawal in the same file (paired,
    compliant); the other two mention the evaluation without ever recording
    the withdrawal (unpaired, a violation each) -- one using each disjunct
    of the two-form needle Req 11.5 names, so both are exercised
    simultaneously rather than alternately. The function must flag exactly
    the two violating files.

    The files deliberately differ in more ways than the pairing property
    itself needs, each pinning a distinct clause the real steering tree
    cannot exercise (it never contains an unpaired mention, so a test that
    only ran the function against it could not tell these clauses were
    live):
    - ``paired.md`` uses the hyphenated, lower-case needle ("third-party").
      Dropping the ``.lower()`` call from the needle check would miss it
      remaining compliant in a way that changes nothing observable, but
      dropping the ``"third-party" in text`` disjunct removes the only
      thing that makes ``unpaired-hyphenated.md`` (below) a violation.
    - ``nested/unpaired.md`` uses the spaced needle in title case
      ("Third Party"). Dropping either the ``"third party" in text``
      disjunct or the ``.lower()`` call would miss it.
    - ``unpaired-hyphenated.md`` uses the hyphenated, lower-case needle
      ("third-party") with no withdrawal recorded. Dropping the
      ``"third-party" in text`` disjunct would miss it -- this is the
      clause ``paired.md`` alone cannot pin, because ``paired.md`` stays
      compliant (and so absent from ``violations``) whether or not that
      disjunct fires.
    - ``nested/unpaired.md`` sits one directory level below
      ``steering_root``, not directly inside it, so
      ``steering_root.glob("*.md")`` (dropping the ``r``) would never see
      it.

    Mutation caught (verified, then reverted byte-identically): dropping the
    ``not`` from ``"withdraw" not in text`` (so the condition becomes
    ``mentions_evaluation and "withdraw" in text``) reds this test -- it
    flags ``paired.md`` instead of the two unpaired files. The same mutation
    also reds ``test_every_steering_file_mentioning_the_withdrawn_
    methodology_also_records_its_withdrawal``, because the real tree's two
    mentioning files (``roadmap.md``, ``structure.md``) both already contain
    "withdraw" and the mutated condition flags both of them too -- this
    mutation is not a sole failure of this test alone, only of the pairing
    logic both tests share.
    """
    steering_root = tmp_path / "steering"
    (steering_root / "nested").mkdir(parents=True)
    (steering_root / "paired.md").write_text(
        "We evaluated a third-party methodology for load scoring and later "
        "withdrew it for licensing reasons -- see the withdrawal record.",
        encoding="utf-8",
    )
    (steering_root / "nested" / "unpaired.md").write_text(
        "We evaluated a Third Party methodology for load scoring.",
        encoding="utf-8",
    )
    (steering_root / "unpaired-hyphenated.md").write_text(
        "We evaluated a third-party methodology for load scoring.",
        encoding="utf-8",
    )

    violations = _steering_pairing_violations(steering_root)

    # `_steering_pairing_violations` iterates `sorted(steering_root.rglob(...))`;
    # this asserts that empirically-observed order rather than assuming one,
    # so a change to the helper's sort key is visible here too.
    assert violations == [
        steering_root / "nested" / "unpaired.md",
        steering_root / "unpaired-hyphenated.md",
    ]


# --- surface-list accuracy (task 6.4 note 4): a stale entry stays caught -----


def _code_block_after(marker: str, text: str) -> list[str]:
    """The comma-separated names inside the first fenced code block that
    follows ``marker`` in ``text`` (docs/plugins.md's ``From fitdocs:`` /
    ``From fitdocs.load:`` surface-list blocks)."""
    idx = text.index(marker)
    start = text.index("```", idx) + 3
    end = text.index("```", start)
    block = text[start:end]
    names = block.replace("\n", " ").split(",")
    return [name.strip() for name in names if name.strip()]


def test_every_name_in_the_plugins_doc_public_surface_list_actually_imports() -> None:
    """Every name ``docs/plugins.md`` publishes as importable from ``fitdocs``
    or ``fitdocs.load`` really does resolve on that module (task 6.4 note 4).

    This would have caught either defect task 5.2 fixed: a published name
    that no longer imports (a rename or removal), and is complementary to the
    name-absence guards above, which only catch a *withdrawn* name reappearing
    -- not a *surviving* published name silently going stale.

    Mutation caught: renaming ``docs/plugins.md``'s listed ``NotComputed`` to
    ``NotComputedResult`` (a name ``fitdocs.load`` does not export) reddens
    this test.
    """
    text = (_REPO_ROOT / "docs" / "plugins.md").read_text(encoding="utf-8")

    fitdocs_names = _code_block_after("From `fitdocs`:", text)
    assert fitdocs_names, "expected a non-empty `From fitdocs:` surface list"
    for name in fitdocs_names:
        assert hasattr(fitdocs, name), f"docs/plugins.md: fitdocs.{name} does not exist"

    load_names = _code_block_after("From `fitdocs.load`:", text)
    assert load_names, "expected a non-empty `From fitdocs.load:` surface list"
    for name in load_names:
        assert hasattr(fitdocs.load, name), (
            f"docs/plugins.md: fitdocs.load.{name} does not exist"
        )


def test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_list() -> None:
    """The reverse direction of the guard above (queue item
    ``2026-07-26-plugin-surface-list-stale-after-amendment-3``): every name
    ``fitdocs.load.__all__`` actually exports must appear in
    ``docs/plugins.md``'s ``From fitdocs.load:`` list, not merely the other
    way around.

    The guard above only ever catches a *listed* name going stale (a rename
    or removal); it is structurally blind to a *real* export the list never
    picked up in the first place -- which is exactly how ``LoadContext``,
    ``LoadSettings``, ``LoadSettingsError``, ``DEFAULT_LOAD_SETTINGS``,
    ``NonSelectedValue``, ``QualityFlag`` and ``supports_activity`` went
    undocumented for two amendments running (this item's own history: 6
    missing, then 7, then 8 measured today) with the existing test suite
    green throughout.

    Mutation caught: removing any single name (tried here with
    ``QualityFlag``) from ``docs/plugins.md``'s ``From fitdocs.load:`` block
    reddens this test as the sole failure; restoring the line byte-identically
    turns the suite green again.
    """
    text = (_REPO_ROOT / "docs" / "plugins.md").read_text(encoding="utf-8")
    load_names = set(_code_block_after("From `fitdocs.load`:", text))
    assert load_names, "expected a non-empty `From fitdocs.load:` surface list"

    # `registry` is `fitdocs.load`'s own re-exported submodule, not a
    # contract symbol a plugin author is meant to import directly --
    # docs/plugins.md deliberately teaches the module-level functions
    # (`register`/`get`/`available`/`for_modality`) instead, and says so in
    # the prose immediately following the surface-list block. This is the
    # one exported name this guard does not require to be listed.
    deliberately_undocumented = {"registry"}

    missing = set(fitdocs.load.__all__) - load_names - deliberately_undocumented
    assert not missing, (
        "docs/plugins.md's `From fitdocs.load:` surface list omits exported "
        f"name(s) {sorted(missing)} -- add them to the list, or, if the "
        "omission is deliberate, add the name to `deliberately_undocumented` "
        "above with a comment justifying why plugin authors should not "
        "depend on it directly"
    )

    # Guard the allowlist itself so it cannot silently grow to swallow a
    # future real omission: it must name exactly `{"registry"}`, and
    # `registry` must genuinely still be an export today. Widening the set
    # literal above without also widening this assertion goes red here,
    # which is deliberate -- an allowlist that can absorb any name without
    # this test noticing is exactly the vacuous-guard failure mode this test
    # exists to close off.
    assert deliberately_undocumented == {"registry"}
    assert "registry" in fitdocs.load.__all__


# --- design.md's public-surface enumeration accuracy (queue: design-md- -----
# --- enumeration-unguarded) -- mirrors the two docs/plugins.md guards above


_DESIGN_DOC = _REPO_ROOT / ".kiro" / "specs" / "plugin-api" / "design.md"


# A real inline-prose surface-list segment (~lines 800-812) is mostly
# backtick-quoted names, commas and spaces -- measured ~75% of its
# characters sit inside backtick-quoted names (root: 281 chars/207 name-chars
# = 73.7%; fitdocs.load: 499 chars/385 name-chars = 77.2%). A segment read
# from the wrong region of the document (prose, not a name list) measures
# around 1% instead, so the gap between "real list" and "wrong region" is
# enormous and this threshold is not delicate. Unlike a character-count cap,
# this check never needs bumping as the enumeration legitimately grows -- a
# longer real list stays just as dense, only a wrong-region read looks
# sparse. (A third, structural line of defence, not itself pinned by a test:
# an early-bound root marker necessarily recaptures the marker's own
# `` `fitdocs` `` token as a "name", and `hasattr(fitdocs, "fitdocs")` is
# always False -- so even a near-decoy segment dense enough to clear this
# threshold still fails the forward-import check. Note for whoever next
# touches the marker text or the name regex: changing either could silently
# remove this backstop.)
_MIN_SURFACE_LIST_NAME_DENSITY = 0.5


def _design_doc_public_surface_lists() -> tuple[list[str], list[str]]:
    """The (`fitdocs` names, `fitdocs.load` names) design.md's inline-prose
    public-surface enumeration (~lines 800-812) lists.

    Unlike ``docs/plugins.md``, which fences its surface lists in fenced code
    blocks parsed by ``_code_block_after``, design.md states the same
    enumeration as inline prose: `` `fitdocs` (`Name`, `Name`, ...) and
    `fitdocs.load` (`Name`, ...) (5.2)``. Whitespace (including markdown's
    hard line wraps inside the enumeration) is collapsed before searching, so
    the markers match regardless of where a line happens to wrap.

    The `fitdocs.load` half's open marker (`` ") and `fitdocs.load` ("``) is
    *not* distinctive on its own -- design.md's Allowed Dependencies section
    (~line 112) separately says "``and `fitdocs.load` (registry + contract
    types)``", one small style edit away from also matching it. Searching
    the whole document for that marker would silently prefer whichever
    occurrence comes first. Instead, this function anchors the search to
    start only *after* the `fitdocs` root marker's own match, which today
    sits immediately before the real enumeration (~line 800) with no other
    occurrence earlier in the document -- so, against *today's* text, an
    accidental match near line 112 (well before that anchor) is skipped.
    That anchor is a property of the current document, not a structural
    guarantee the algorithm enforces on its own: a future edit could in
    principle introduce this same root marker text earlier in the document
    too, making the anchor bind early and the segment balloon. The name-
    density check below is the independent backstop for exactly that case
    -- it reds loudly on a low-density (wrong-region) segment rather than
    silently swallowing hundreds of lines of unrelated prose, regardless of
    why the marker matched where it did.
    """
    text = re.sub(r"\s+", " ", _DESIGN_DOC.read_text(encoding="utf-8"))

    root_marker = "exactly: `fitdocs` ("
    load_open_marker = ") and `fitdocs.load` ("
    load_close_marker = ") (5.2)"
    name_pattern = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*)`")

    def _index(marker: str, from_pos: int, what: str) -> int:
        try:
            return text.index(marker, from_pos)
        except ValueError as exc:
            raise AssertionError(
                f"design.md: could not find {what} ({marker!r}) -- has the "
                "public-surface enumeration (~lines 800-812) been reworded?"
            ) from exc

    def _plausible_names(start: int, end: int, what: str) -> list[str]:
        segment = text[start:end]
        names = name_pattern.findall(segment)
        name_chars = sum(len(name) for name in names)
        density = name_chars / len(segment) if segment else 0.0
        assert density > _MIN_SURFACE_LIST_NAME_DENSITY, (
            f"design.md: the {what} surface-list segment looks implausible "
            f"-- only {density:.0%} of its {len(segment)} chars are inside "
            "backtick-quoted names, where a real surface list runs ~75%. "
            "The enumeration legitimately growing would NOT trip this (a "
            "longer real list stays just as dense); two more likely causes: "
            "(1) a marker matched the wrong occurrence in the document, "
            "reading unrelated prose instead of the real enumeration (~lines "
            "800-812) -- check for an earlier accidental match of the "
            "open/close marker used here; or (2) non-name prose (a "
            "parenthetical or a gloss, e.g. the 'decode errors' -> three-"
            "names precedent) was added inside the list itself, diluting "
            "its density"
        )
        return names

    root_start = _index(root_marker, 0, "the `fitdocs` surface-list marker") + len(
        root_marker
    )
    load_open = _index(load_open_marker, root_start, "the `fitdocs.load` open marker")
    fitdocs_names = _plausible_names(root_start, load_open, "`fitdocs`")

    load_start = load_open + len(load_open_marker)
    load_end = _index(load_close_marker, load_start, "the `fitdocs.load` close marker")
    load_names = _plausible_names(load_start, load_end, "`fitdocs.load`")

    return fitdocs_names, load_names


def test_design_doc_public_surface_list_names_actually_import() -> None:
    """Every name plugin-api's design.md publishes as importable from
    ``fitdocs`` or ``fitdocs.load`` really does resolve on that module,
    mirroring ``test_every_name_in_the_plugins_doc_public_surface_list_
    actually_imports`` for ``docs/plugins.md``.

    Mutation caught: renaming design.md's listed ``NotComputed`` to
    ``NotComputedResult`` (a name ``fitdocs.load`` does not export) reddens
    this test.
    """
    fitdocs_names, load_names = _design_doc_public_surface_lists()
    assert fitdocs_names, "expected a non-empty `fitdocs` surface list in design.md"
    for name in fitdocs_names:
        assert hasattr(fitdocs, name), f"design.md: fitdocs.{name} does not exist"

    assert load_names, "expected a non-empty `fitdocs.load` surface list in design.md"
    for name in load_names:
        assert hasattr(fitdocs.load, name), (
            f"design.md: fitdocs.load.{name} does not exist"
        )


def test_every_fitdocs_load_export_appears_in_the_design_doc_surface_list() -> None:
    """The reverse direction: every name ``fitdocs.load.__all__`` actually
    exports must appear in plugin-api design.md's public-surface enumeration,
    not merely the other way around -- mirroring
    ``test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_
    list``, which already guards ``docs/plugins.md``'s copy of the same list
    (queue: ``2026-07-27-design-md-enumeration-unguarded``).

    Nothing previously read this file at all. Five benchmark exports
    (``Benchmark``, ``BenchmarkKind``, ``BenchmarkRef``, ``BenchmarkAge``,
    ``benchmark_age``) were missing from this enumeration the day this guard
    was written (queue: ``2026-07-27-plugin-api-enumeration-restaled-by-
    benchmarks``); running this assertion before adding them reddened with
    exactly those five names in ``missing``.

    Mutation caught: removing any single name (tried here with
    ``QualityFlag``) from design.md's ``fitdocs.load`` surface list reddens
    this test as the sole failure; restoring the text byte-identically turns
    the suite green again.
    """
    _, load_names_list = _design_doc_public_surface_lists()
    load_names = set(load_names_list)
    assert load_names, "expected a non-empty `fitdocs.load` surface list in design.md"

    # Same exemption as docs/plugins.md's sibling guard, for the same reason:
    # `registry` is `fitdocs.load`'s own re-exported submodule, not a contract
    # symbol a plugin author is meant to import directly. design.md's own
    # prose immediately after the enumeration makes the same call
    # (matching `docs/plugins.md`'s stated decision on the same name).
    deliberately_undocumented = {"registry"}

    missing = set(fitdocs.load.__all__) - load_names - deliberately_undocumented
    assert not missing, (
        "plugin-api design.md's public-surface enumeration omits exported "
        f"name(s) {sorted(missing)} -- add them to the enumeration (~lines "
        "800-812), or, if the omission is deliberate, add the name to "
        "`deliberately_undocumented` above with a comment justifying why "
        "plugin authors should not depend on it directly"
    )

    # Guard the allowlist itself so it cannot silently grow to swallow a
    # future real omission: it must name exactly `{"registry"}`, and
    # `registry` must genuinely still be an export today.
    assert deliberately_undocumented == {"registry"}
    assert "registry" in fitdocs.load.__all__


# --- worked-example signature accuracy (queue: docs/plugins.md compute -----
# --- signature drift; sibling mechanism: test_contributing_calculators_doc.py)


_PLUGINS_DOC = _REPO_ROOT / "docs" / "plugins.md"
_WORKED_EXAMPLE_START = "<!-- doctest: worked-example start -->"
_WORKED_EXAMPLE_END = "<!-- doctest: worked-example end -->"
_PY_FENCE = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _extract_plugins_doc_worked_example() -> str:
    """The fenced Python source between the doctest markers in
    ``docs/plugins.md``'s packaged-calculator worked example, verbatim."""
    text = _PLUGINS_DOC.read_text(encoding="utf-8")
    start = text.index(_WORKED_EXAMPLE_START)
    end = text.index(_WORKED_EXAMPLE_END, start)
    block = text[start:end]
    match = _PY_FENCE.search(block)
    assert match is not None, (
        "no fenced ```python block found between the worked-example doctest "
        "markers in docs/plugins.md"
    )
    return match.group(1)


def test_plugins_doc_worked_example_markers_are_present_and_wrap_a_calculator() -> None:
    """The extraction contract itself: markers exist and bracket real code.

    Guards the guard -- if a future edit removes, renames, or reorders the
    ``<!-- doctest: worked-example ... -->`` markers, this fails loudly
    instead of the type-check test below silently extracting an empty string
    and reporting a false pass (the "vacuous walk" failure mode).

    Mutation caught: renaming the end marker to
    ``<!-- doctest: worked-example finish -->`` makes ``str.index`` raise
    ``ValueError`` here (a loud failure), rather than the type-check test
    silently checking nothing.
    """
    source = _extract_plugins_doc_worked_example()
    assert "class MyCalculator" in source
    assert "def compute(" in source
    assert "def required_athlete_fields(" in source
    # Pins the conformance anchor itself (queue sweep round 3, finding 1): the
    # type-check test below only proves anything about the *signature* because
    # this exact assignment exists inside the checked block. Without an
    # assertion naming it, deleting `_conformance_check` -- something
    # `docs/plugins.md`'s own prose invites the reader to do when they copy
    # the example ("delete it when you copy this example") -- leaves mypy
    # with nothing Protocol-shaped to check `MyCalculator` against, and the
    # type-check test passes regardless of what `compute`'s parameters are
    # annotated as.
    #
    # Mutation caught (verified, then reverted byte-identically): deleting
    # `_conformance_check` entirely from the worked example, both alone and
    # combined with changing `profile: object` to `profile: str` (a type the
    # engine never passes and the Protocol rejects), is GREEN across the
    # whole suite without this line; both mutations turn RED with it.
    assert "_c: LoadCalculator = MyCalculator()" in source


def test_plugins_doc_worked_example_type_checks_against_the_shipped_contract(
    tmp_path: Path,
) -> None:
    """The observable: ``docs/plugins.md``'s packaged-calculator worked
    example type-checks under ``mypy --strict`` against the real, installed
    ``fitdocs.load`` contract -- including an explicit
    ``_c: LoadCalculator = MyCalculator()`` assignment inside the checked
    block, which is what pins the *whole* ``compute`` signature (every
    parameter's presence and type, plus ``required_athlete_fields``'s return
    type) at once, rather than one hand-maintained name or parameter string.

    A prior version of this guide's example named ``context: LoadContext``
    only in prose, so deleting the parameter from the code sample itself left
    every existing test green -- the doc's promise that "these names carry
    inline type annotations your own mypy/pyright can check against" was
    otherwise unverified narrative for this specific example. Assigning the
    example class to the ``LoadCalculator`` Protocol type is what makes
    conformance an mypy diagnostic instead of a claim: mypy only accepts the
    assignment if ``MyCalculator``'s members structurally satisfy
    ``LoadCalculator``'s signatures target-type-first, so it also catches a
    covariance-violating return type (e.g. ``required_athlete_fields``
    returning ``tuple[object, ...]`` instead of ``tuple[AthleteField, ...]``)
    that a same-file mypy-with-no-Protocol-anchor pass would happily accept.

    Mutations caught (each verified, then reverted byte-identically). Two are
    the *sole* new failure in this file; the other two also fail the textual
    companion test below (``test_plugins_doc_worked_example_shows_the_
    five_argument_context_signature`` names ``context: LoadContext``
    literally, so any mutation touching that exact parameter fails both this
    test and that one -- not a false discrimination claim, just two guards
    with overlapping reach):
      - deleting a parameter this test alone pins (``metrics: DerivedMetrics``)
        -- sole failure here;
      - narrowing ``required_athlete_fields``'s return annotation back to
        ``tuple[object, ...]`` -- sole failure here;
      - deleting ``context: LoadContext`` from ``compute``'s parameter list
        -- fails here AND the textual companion test;
      - changing that parameter's type (``context: LoadContext`` ->
        ``context: int``) -- fails here AND the textual companion test.

    DECLARED UNPINNED, and structurally unfixable by this mechanism:
    *widening* any parameter annotation to ``object`` (e.g.
    ``metrics: DerivedMetrics`` -> ``metrics: object``). Protocol parameter
    types are matched **contravariantly**, so ``object`` -- which accepts
    everything the engine could pass -- always satisfies the signature. This
    was measured, not assumed: after ``profile``/``session`` were given their
    real annotations, widening any of them back to ``object`` still passes
    ``mypy --strict``. The anchor catches *incompatible* parameter types
    (``profile: ProfileView`` -> ``profile: str`` reds) and covariance
    violations in the return type; it cannot catch widening. ``context`` is
    the one parameter covered anyway, by the textual companion test's literal
    match. Closing this for the rest would need a textual assertion per
    parameter, which is the hand-maintained copy this test exists to replace.
    """
    source = _extract_plugins_doc_worked_example()
    example_file = tmp_path / "plugins_doc_worked_example.py"
    example_file.write_text(source, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "mypy", "--strict", str(example_file)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, (
        "docs/plugins.md's worked example does not type-check against the "
        "shipped LoadCalculator contract:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


def test_plugins_doc_worked_example_shows_the_five_argument_context_signature() -> None:
    """Textual companion to the mypy check above: pins the literal
    ``context: LoadContext`` spelling in the doc's own source, in addition to
    the structural mypy guarantee -- so a rewrite that keeps the parameter
    but drops the exact ``LoadContext`` annotation text is caught by name
    even in a hypothetical future where the parameter type checks against a
    wider alias."""
    source = _extract_plugins_doc_worked_example()
    assert re.search(r"def compute\(\s*self,", source) is not None
    assert "context: LoadContext" in source


# --- intra-documentation anchor links ---------------------------------------
#
# NUMBERING DECISION (2026-07-26), recorded so it is not rediscovered.
#
# `docs/contributing-calculators.md` uses numbered headings (`## 8. Register
# it`). GitHub derives an anchor slug from the *full* heading text, so the
# number is part of the anchor and **inserting any section renumbers every
# anchor below it**. Dropping the numbers would make anchors stable under
# insertion forever.
#
# The numbers stay. The guide is a step-by-step tutorial where the ordinals
# carry real meaning ("do step 2 only if..."), and the actual defect was never
# the renumbering -- it was that renumbering failed *silently*. A dead in-page
# anchor does not 404; the browser lands at the top of a 470-line document, so
# even a human clicking it may not notice. The guard below makes the breakage
# loud, turning silent corruption into ordinary, visible maintenance.
#
# The accepted cost: inserting a section into that guide reddens this test and
# the inbound links must be repointed in the same change. That is working as
# intended. Revisit if the toil outgrows the tutorial value -- four Phase 4
# specs are expected to add sections to these files.


def _heading_slugs(markdown: str) -> set[str]:
    """Every GitHub-flavoured anchor slug the ATX headings in ``markdown`` define.

    GitHub lowercases the full heading text, strips characters that are not
    alphanumerics, spaces or hyphens (so backticks, periods, colons and
    apostrophes vanish rather than becoming separators), and replaces spaces
    with hyphens. ``## 6. Reading configuration ... `LoadContext``` therefore
    becomes ``6-reading-configuration-...-loadcontext`` -- the leading number
    included, which is exactly why insertion breaks inbound links.
    """
    slugs: set[str] = set()
    for line in markdown.splitlines():
        match = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if match is None:
            continue
        text = match.group(2).lower()
        text = re.sub(r"[^\w\s-]", "", text.replace("_", ""))
        slugs.add(re.sub(r"\s+", "-", text.strip()))
    return slugs


def _anchor_links(markdown: str) -> list[tuple[str, str]]:
    """Every ``(target_file, anchor)`` pair ``markdown`` links to.

    Covers both the inline ``[label](file.md#anchor)`` and the reference-style
    ``[label]: file.md#anchor`` forms. The second is not optional polish: it is
    how ``docs/plugins.md`` carries its ``LoadContext`` link, so a parser
    written for the inline form alone would skip the single most important
    anchor in the set. A same-document link (``](#anchor)``) yields an empty
    target file.
    """
    inline = re.findall(r"\]\(([^)\s#]*)#([^)\s]+)\)", markdown)
    reference = re.findall(r"^\[[^\]]+\]:\s*([^\s#]*)#(\S+)\s*$", markdown, re.M)
    return [*inline, *reference]


def test_anchor_link_parser_reads_both_inline_and_reference_style_links() -> None:
    """``_anchor_links`` finds both markdown link forms, and ``_heading_slugs``
    applies GitHub's slug rule including the leading heading number.

    A direct unit pin on the machinery, separate from the corpus walk below.
    Without it, dropping either regex leaves the corpus test green -- it would
    simply check fewer links, and its count-based positive control cannot tell
    "found fewer" from "there are fewer". That is the failure this test exists
    to make impossible: the reference-style form is the one carrying the
    ``LoadContext`` link.
    """
    sample = (
        "## 6. Reading configuration: only through `LoadContext`\n"
        "See [inline](other.md#some-heading) and [self](#6-reading-configuration"
        "-only-through-loadcontext).\n"
        "\n"
        "[ref]: other.md#reference-target\n"
    )

    expected_slug = "6-reading-configuration-only-through-loadcontext"
    assert _heading_slugs(sample) == {expected_slug}

    links = _anchor_links(sample)
    assert ("other.md", "some-heading") in links, "inline form not parsed"
    assert ("other.md", "reference-target") in links, "reference-style form not parsed"
    assert (
        "",
        "6-reading-configuration-only-through-loadcontext",
    ) in links, "same-document form not parsed"


def test_every_intra_documentation_anchor_link_resolves_to_a_real_heading() -> None:
    """Every anchor link between shipped markdown files points at a heading
    that exists.

    Not hypothetical. At ``e806c57`` two of the three anchors from
    ``docs/plugins.md`` into the contributor guide were broken at once: one had
    been dead since before that batch, and one was *added and verified* earlier
    in the same batch, then broken a few commits later by an unrelated edit that
    inserted a section above its target. Nothing detected either, because a dead
    in-page anchor does not 404 -- the browser simply lands at the top of the
    page.

    ``docs/plugins.md`` is the first page a third-party calculator author reads,
    and these links are how they reach the detailed contract.
    """
    doc_paths = [_REPO_ROOT / "README.md", *sorted((_REPO_ROOT / "docs").rglob("*.md"))]
    doc_paths = [p for p in doc_paths if p.is_file()]
    assert doc_paths, "the documentation set is empty -- this walk found no files"

    slugs_by_path = {
        p: _heading_slugs(p.read_text(encoding="utf-8")) for p in doc_paths
    }

    checked: list[str] = []
    broken: list[str] = []
    for path in doc_paths:
        for target, anchor in _anchor_links(path.read_text(encoding="utf-8")):
            if target and not target.endswith(".md"):
                continue  # not a link into the markdown documentation set
            resolved = (path.parent / target).resolve() if target else path
            if resolved not in slugs_by_path:
                continue  # outside the shipped doc set; not this guard's business
            rel = resolved.relative_to(_REPO_ROOT)
            checked.append(f"{rel}#{anchor}")
            if anchor not in slugs_by_path[resolved]:
                broken.append(
                    f"{path.relative_to(_REPO_ROOT)} -> {rel}#{anchor} "
                    f"(that file's headings define: {sorted(slugs_by_path[resolved])})"
                )

    # Positive control. Without it a regex change that matches nothing leaves
    # this green having verified nothing -- the `vacuous walk` anti-pattern this
    # repo has already shipped twice.
    assert len(checked) >= 3, (
        f"expected at least the three known plugins.md anchors, checked {checked}"
    )
    assert not broken, "dead intra-documentation anchor links:\n" + "\n".join(broken)


def test_no_shipped_doc_claims_fitdocs_ships_no_built_in_calculator() -> None:
    """The shipped documentation set never says fitdocs ships no methodology
    of its own or that importing ``fitdocs.load`` registers nothing.

    ``threshold-load`` supersedes ``training-load`` Req 13.2's "the registry
    is empty of built-ins": fitdocs now ships exactly one built-in,
    ``threshold``, registered by ``fitdocs.load``'s package initializer
    (Req 1.1-1.3). ``docs/contributing-calculators.md`` carried the
    superseded claim in four places (a REMEDIATION ROUND 1 finding) even
    after ``docs/plugins.md`` was corrected -- no guard covered that file, so
    CI did not force the fix. This is that guard, scanning the whole shipped
    corpus (as the module docstring above explains) so the phrasing cannot
    resurface in a new file either.
    """
    text = _shipped_documentation_text()

    # Positive control: without it, a regex/text change that matches nothing
    # would leave this green having verified nothing.
    assert "threshold" in text.lower(), "not reading the shipped documentation set"

    forbidden = [
        "ships no methodology",
        "ships no calculator",
        "fitdocs ships no",
        "registers **nothing**",
        "registers nothing",
        "is empty on a fresh interpreter",
    ]
    found = [phrase for phrase in forbidden if phrase.lower() in text.lower()]
    assert not found, (
        f"shipped docs claim fitdocs ships no built-in calculator: {found}. "
        "fitdocs ships exactly one built-in, threshold, registered by "
        "fitdocs/load/__init__.py's own docstring (Req 1.1-1.3)."
    )


# --- agent-skill packaging docs (build-training-block task 3.2, Req 5.4) ----


def _agent_skills_section(readme_text: str) -> str:
    """The text of README's ``## Agent skills`` section: everything between
    that heading and the next ``## `` heading (or end of file).

    Scoped deliberately, rather than searching the whole documentation
    corpus, so that a ``copy``/``verify``/``upgrade`` mention living
    elsewhere in the corpus (README's ``## Inbox`` section already contains
    the word "copy", in "an archived copy") cannot pre-satisfy a pin that is
    supposed to be about *this* section's install/verify/update prose.
    """
    match = re.search(r"^## Agent skills\n(.*?)(?=^## |\Z)", readme_text, re.S | re.M)
    assert match is not None, (
        "README has no '## Agent skills' section -- the scoped search below "
        "is looking at the wrong place"
    )
    return match.group(1)


def test_agent_skills_readme_section_documents_install_verify_and_update() -> None:
    """Req 5.4: the shipped documentation states, for the packaged skills,
    where to install a skill, how to verify it is active, and how to update
    it on upgrade.

    Every positive pin below is scoped to the ``## Agent skills`` section via
    :func:`_agent_skills_section`, found first and asserted non-empty, so an
    install/verify/update word appearing in some *other* section of the
    corpus cannot satisfy a pin about this one -- confirmed empirically: the
    real README already contains the word "copy" once outside this section
    (``## Inbox``'s "an archived copy"), and the pre-task README (no ``##
    Agent skills`` heading at all) contained neither "verify" nor "upgrade"
    anywhere, so the property this test pins did not hold before this task.
    """
    readme_text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = _agent_skills_section(readme_text)
    assert section.strip(), "the Agent skills section is empty"

    assert "fitdocs skill" in section
    # Backticked form: distinguishes "the command `fitdocs skill`" from a
    # near-miss like "fitdocs skills" (plural, no such command exists) --
    # the bare substring above is satisfied by either.
    assert "`fitdocs skill`" in section
    assert "build-training-block" in section
    assert "copy" in section.lower()
    assert "verify" in section.lower()
    assert "upgrade" in section.lower()

    # README places this section immediately after `## Plugins`: relocating
    # it anywhere else -- above `## Plugins`, or further down past `## Inbox`
    # -- reds this while every pin above stays green (the section's own
    # content is unchanged by relocation). A plain ordering check
    # (`index("## Plugins") < index("## Agent skills")`) only pins "somewhere
    # after", which stays green even when another `## ` section is spliced
    # in between; the next-heading match below pins adjacency instead.
    next_heading_after_plugins = re.search(
        r"^## Plugins\n.*?^## ([^\n]+)$", readme_text, re.S | re.M
    )
    assert next_heading_after_plugins is not None, (
        "README has no '## Plugins' section -- the adjacency check below is "
        "looking at the wrong place"
    )
    assert next_heading_after_plugins.group(1) == "Agent skills"


# --- the documentation entry point (task 5.7, Req 1.9, 3.7, 7.9, 10.6, 10.7) -


_ENTRY_POINT = _REPO_ROOT / "docs" / "index.md"

# The ten pages 7.9/design.md's docs/index.md bullet names, exactly as
# docs/index.md's own links must spell them (relative to docs/index.md
# itself, so the CONTRIBUTING.md target climbs one directory).
_REQUIRED_ENTRY_POINT_LINKS = [
    "install.md",
    "configuration.md",
    "inbox.md",
    "upgrading.md",
    "wiki-integration.md",
    "ownership-contract.md",
    "plugins.md",
    "compatibility.md",
    "releasing.md",
    "../CONTRIBUTING.md",
]


def _plain_link_targets(markdown: str) -> list[str]:
    """Every markdown link target in ``markdown``, external URLs excluded and
    any ``#anchor`` fragment stripped.

    Complements ``_anchor_links`` above: that function only extracts links
    carrying a ``#`` fragment (built for the intra-documentation anchor
    walker), and every link ``docs/index.md`` carries to a sibling page is a
    bare file reference with no anchor at all -- ``_anchor_links`` would find
    none of them.
    """
    targets = re.findall(r"\]\(([^)\s]+)\)", markdown)
    return [
        target.split("#", 1)[0]
        for target in targets
        if not target.startswith(("http://", "https://"))
    ]


def test_documentation_entry_point_links_every_required_page() -> None:
    """7.9/design.md's ``docs/index.md`` bullet: a single entry point linking
    install, configuration, the inbox interface, upgrading, wiki integration,
    the ownership contract, the plugin platform, compatibility, releasing,
    and contributing.

    Each of the ten targets is checked both for presence in the parsed link
    list (a renamed or dropped link is caught even if the file it would have
    pointed at still exists) and for actually resolving to a file on disk (a
    stale link to a renamed page is caught even though the link text is
    still present).

    The inbox link is asserted a second time, by itself and by name: 7.9's
    own text singles it out ("one documentation entry point, inbox
    included") because the inbox is a governed contract and the whole
    subject of the agent skill's workflow -- an entry point that does not
    reach it is a hole, not a spot check.

    Mutation caught (verified, then reverted byte-identically): deleting the
    ``inbox.md`` row from ``docs/index.md`` fails only this test (the
    intra-documentation anchor walker never sees this link at all, because
    none of docs/index.md's links carry a ``#`` fragment); deleting the
    ``compatibility.md`` row is likewise this test's sole failure.
    """
    text = _ENTRY_POINT.read_text(encoding="utf-8")
    targets = _plain_link_targets(text)

    # Positive control: parsing must find at least the ten required links,
    # or the loop below would pass having checked a target list emptied by a
    # broken regex.
    assert len(targets) >= 10, (
        f"expected at least 10 links parsed from docs/index.md, found {targets}"
    )

    for required in _REQUIRED_ENTRY_POINT_LINKS:
        assert required in targets, f"docs/index.md does not link {required!r}"
        resolved = (_ENTRY_POINT.parent / required).resolve()
        assert resolved.is_file(), (
            f"docs/index.md links {required!r}, which does not resolve to a "
            f"real file at {resolved}"
        )

    # 7.9's own "inbox included" clause, pinned by name rather than only via
    # the loop above, so a future edit to _REQUIRED_ENTRY_POINT_LINKS that
    # accidentally dropped "inbox.md" from the list itself would not silently
    # stop checking it.
    assert "inbox.md" in targets, (
        "docs/index.md does not reach the inbox interface -- the inbox is a "
        "governed contract and the whole subject of the agent skill's "
        "workflow (Req 7.9)"
    )


def test_readme_links_the_entry_point_by_project_url() -> None:
    """3.7/7.9: the readme links the documentation entry point by its
    published project URL rather than growing to restate everything itself.

    Mutation caught: deleting the ``docs/index.md`` project-URL link from
    README.md fails only this test.
    """
    readme_text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{_PROJECT_URL_PREFIX}docs/index.md" in readme_text, (
        "README.md does not link the documentation entry point "
        f"({_PROJECT_URL_PREFIX}docs/index.md) by project URL"
    )


# --- preserved statements, scoped to the specific page they live on (10.6) --
#
# 10.6 names six statements. Two already have a dedicated corpus-wide guard
# above (test_inbox_never_delete_guarantee_is_published_somewhere_in_the_docs,
# test_inbox_no_watching_guarantee_is_published_somewhere_in_the_docs) --
# this section does not duplicate them. The other four get a page-scoped
# assertion here: not merely "published somewhere in the corpus" (which the
# corpus-wide tests above already establish the *pattern* for) but pinned to
# the *specific* page 5.2/design.md relocated each statement to, so a
# statement that moved off its intended page without vanishing from the
# corpus entirely (e.g. duplicated into some unrelated file) still reads as
# a defect against the page it is supposed to live on.


def _configuration_doc_text() -> str:
    return (_REPO_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")


def _normalized(text: str) -> str:
    """Whitespace-collapsed ``text``, mirroring
    ``_shipped_documentation_text``'s own collapse -- so a page-level token
    search is not sensitive to where in the prose a paragraph happens to
    hard-wrap (e.g. "rendered\\nlegibly" in the real
    ``docs/configuration.md`` source)."""
    return re.sub(r"\s+", " ", text)


#: Mirrors tests/test_install_docs.py's `_RESOLUTION_ORDER_RE`, built from
#: the same real `fitdocs.config` tokens rather than a hand-typed copy that
#: could drift from either the code or that sibling test. Anchored to
#: newlines and heading numbers, so it only matches the real page text
#: (unwrapped, with real line breaks) -- not the whitespace-collapsed corpus
#: (see `_resolution_order_present_in_order` below for that check).
_RESOLUTION_ORDER_RE = re.compile(
    r"^1\. .*--out.*\n^2\. .*"
    + re.escape(DATA_ROOT_ENV)
    + r".*\n^3\. .*"
    + re.escape(POINTER_RELPATH),
    re.M,
)


def _ordered_tokens_within(text: str, tokens: list[str], *, max_span: int) -> bool:
    """Whether every string in ``tokens`` appears in ``text``, each one
    starting no earlier than the previous token's own start, with the whole
    run spanning no more than ``max_span`` characters end to end.

    Deliberately a plain-string, index-based check rather than a regex:
    ``docs/configuration.md``'s real prose crosses more than one literal
    period between these tokens (the code span `` `<data-root>/fitdocs.toml`
    `` itself contains a period, ahead of the sentence-ending period), so a
    ``[^.]``-bounded regex window -- the pattern the inbox guarantees above
    use safely, because those statements never cross a period at all -- is
    the wrong tool here: it stops at the first accidental period and never
    reaches the real one. Bounding by total character span instead of
    period-count keeps this from matching two unrelated tokens on opposite
    ends of the (very large, multi-file) corpus, without caring how many
    literal periods sit in between.
    """
    pos = 0
    first: int | None = None
    for token in tokens:
        idx = text.index(token, pos)
        if first is None:
            first = idx
        pos = idx + len(token)
    assert first is not None  # tokens is always non-empty at call sites below
    return (pos - first) <= max_span


#: Single, polarity-bearing phrases rather than a pair of separately-located
#: tokens checked only for order/proximity (task 5.7 round-1 review, findings
#: 2 and 3). A two-token ordered-proximity check is blind to what sits
#: *between* the tokens: inserting "never" between "`enabled = false`" and
#: "persistent opt-out" (turning the guarantee into its own negation), or
#: relocating the guarantee into a hedged table cell that still happens to
#: contain both tokens somewhere nearby, would leave a two-token check green.
#: A single contiguous phrase, matched verbatim against the whitespace-
#: normalized text, does not have this hole -- either the exact guarantee
#: sentence (or its exact table-row form) is present, or it is not.
#:
#: The opt-out phrase reuses the identical literal
#: ``tests/test_install_docs.py`` already pins (task 5.7 round-1 review,
#: finding 5): that sibling test's phrase is already the stronger, hedge-
#: resistant page-level pin, so this module's own corpus/page checks now
#: assert the exact same text rather than a weaker proximity approximation.
_PERSISTENT_TILE_OPT_OUT_PHRASE = "is a persistent opt-out: it"

#: The full sentence, not the bare "`attribution`" token: that bare token
#: also names the table row (~line 117) documenting the key itself, which
#: sits well before this prose sentence -- matching on it alone (or on it
#: plus a separately-located "rendered legibly..." token) would make either
#: an ordered-proximity check compare the wrong occurrence, or -- the
#: round-1 defect -- stay green with "never" inserted between the two
#: tokens or with the guarantee relocated into a hedged, altered sentence
#: that still contains both tokens somewhere nearby.
_TILE_ATTRIBUTION_PHRASE = (
    "configured provider's `attribution` text is rendered legibly on every map image"
)


def test_preserved_statement_resolution_order_lives_on_configuration_doc() -> None:
    """10.6: the data-root resolution order (``--out`` > ``FITDOCS_DATA`` >
    the pointer file, in that order) is still published on
    ``docs/configuration.md`` specifically.

    Mutation caught (verified, then reverted byte-identically): removing the
    numbered resolution list from ``docs/configuration.md`` fails this test
    and ``tests/test_install_docs.py::test_configuration_doc_states_the_
    resolution_order_and_no_code_repo_guarantee`` -- the two tests
    deliberately share reach here, since both pin the same real statement on
    the same real page; this one additionally requires the statement to
    survive in the whole-corpus concatenation, which the sibling test does
    not check.
    """
    page_text = _configuration_doc_text()
    assert _RESOLUTION_ORDER_RE.search(page_text), (
        "docs/configuration.md no longer states the --out > FITDOCS_DATA > "
        "pointer-file resolution order as a numbered list"
    )
    assert _ordered_tokens_within(
        _shipped_documentation_text(),
        ["1. The `--out PATH` flag", DATA_ROOT_ENV, POINTER_RELPATH],
        max_span=400,
    ), (
        "the data-root resolution order no longer appears, in order, in the "
        "shipped documentation corpus"
    )


def test_preserved_statement_persistent_tile_opt_out_lives_on_configuration_doc() -> (
    None
):
    """10.6: the persistent tile opt-out (``enabled = false`` under
    ``[tiles]`` disables *all* tile requests, not just the default provider)
    is still published on ``docs/configuration.md``.

    Uses the exact literal ``_PERSISTENT_TILE_OPT_OUT_PHRASE`` --
    round-1 review found the prior two-token ordered-proximity check blind
    to what sits *between* the tokens (an inserted "never", or the
    guarantee relocated into a hedged form that still contains both tokens
    nearby); a single verbatim phrase closes both holes.

    Mutations caught (verified, then reverted byte-identically):
    - deleting "This is a persistent opt-out" from ``docs/configuration.md``
      fails this test as the sole failure in this file;
    - inserting "never" between "enabled = false" and "persistent opt-out"
      (so the sentence reads "...fitdocs.toml`. This is never a persistent
      opt-out: it disables...") fails this test as the sole failure in this
      file -- the two-token proximity check this replaces stayed green
      under this exact mutation.
    """
    page_text = _normalized(_configuration_doc_text())
    assert _PERSISTENT_TILE_OPT_OUT_PHRASE in page_text, (
        "docs/configuration.md no longer states the persistent tile opt-out "
        f"({_PERSISTENT_TILE_OPT_OUT_PHRASE!r})"
    )
    assert _PERSISTENT_TILE_OPT_OUT_PHRASE in _shipped_documentation_text(), (
        "the persistent tile opt-out no longer appears in the shipped "
        "documentation corpus"
    )


def test_preserved_statement_tile_provider_attribution_lives_on_configuration_doc() -> (
    None
):
    """10.6: the tile-provider attribution statement (the configured
    provider's ``attribution`` text is rendered on every map image) is still
    published on ``docs/configuration.md``.

    Uses the exact literal ``_TILE_ATTRIBUTION_PHRASE`` -- round-1 review
    found the prior two-token ordered-proximity check
    (``"configured provider's \\`attribution\\`"`` ... ``"rendered legibly on
    every map image"``) blind to what sits *between* the tokens: inserting
    "never" ("...text is never rendered legibly...") or relocating the
    guarantee into a hedged table row that still contains both tokens nearby
    both left the prior check green. A single verbatim phrase closes both
    holes.

    Mutations caught (verified, then reverted byte-identically):
    - deleting "rendered legibly on every map image" from
      ``docs/configuration.md`` fails this test as the sole failure in this
      file;
    - inserting "never" between "attribution" and "rendered" (so the
      sentence reads "...text is never rendered legibly on every map
      image") fails this test as the sole failure in this file -- the
      two-token proximity check this replaces stayed green under this
      exact mutation.
    """
    page_text = _normalized(_configuration_doc_text())
    assert _TILE_ATTRIBUTION_PHRASE in page_text, (
        "docs/configuration.md no longer states that the configured "
        f"provider's attribution text is rendered on every map image "
        f"({_TILE_ATTRIBUTION_PHRASE!r})"
    )
    assert _TILE_ATTRIBUTION_PHRASE in _shipped_documentation_text(), (
        "the tile-provider attribution statement no longer appears in the "
        "shipped documentation corpus"
    )


def test_preserved_statement_ownership_contract_pointer_lives_on_readme() -> None:
    """10.6: a pointer to the published ownership contract. README carries
    the project URL to ``docs/ownership-contract.md`` directly, and
    ``docs/index.md`` links it too (already pinned by
    ``test_documentation_entry_point_links_every_required_page``, so not
    duplicated here).

    Mutation caught (verified, then reverted byte-identically): deleting
    every ``docs/ownership-contract.md`` project-URL occurrence from
    README.md fails this test as the sole failure in this file.
    """
    readme_text = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    ownership_url = f"{_PROJECT_URL_PREFIX}docs/ownership-contract.md"
    assert ownership_url in readme_text, (
        "README.md no longer points at the published ownership contract by project URL"
    )
    assert ownership_url in _shipped_documentation_text(), (
        "the published ownership contract pointer no longer appears in the "
        "shipped documentation corpus"
    )


# --- shipped/emitted documentation references use the project-URL form -----
# --- (Req 1.9) ---------------------------------------------------------------


def _forbidden_relative_doc_link_targets(text: str) -> list[str]:
    """Every markdown link target in ``text`` that is a repository-relative
    documentation reference: starts with ``docs/``, ``./``, ``../``, or is a
    bare ``*.md`` path with no scheme -- exactly the forms 1.9 forbids inside
    an artifact that ships without a repository, or a tree emitted into a
    user's data root that has no repository at all.

    External (``http``/``https``) targets are never flagged.
    """
    forbidden = []
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://")):
            continue
        no_anchor = target.split("#", 1)[0]
        if (
            target.startswith("docs/")
            or target.startswith("./")
            or target.startswith("../")
            or no_anchor.endswith(".md")
        ):
            forbidden.append(target)
    return forbidden


def test_forbidden_relative_doc_link_target_helper_discriminates_every_relaxation() -> (
    None
):
    """Unit pin on :func:`_forbidden_relative_doc_link_targets` itself,
    against synthetic text, one case per relaxation class -- production docs
    carry no violation today, so a test that only ever ran the helper
    against real shipped files could not tell a genuinely discriminating
    helper from one that always returns ``[]`` (the pre-satisfied-fixture
    anti-pattern).

    | token | relaxation class (no ``.md`` isolates the prefix) | case | expected |
    | --- | --- | --- | --- |
    | ``docs/`` prefix | present | ``docs/CHANGES`` | forbidden |
    | ``docs/`` prefix | absent (URL) | ``https://.../docs/inbox.md`` | allowed |
    | ``./`` prefix | present | ``./CHANGES`` | forbidden |
    | ``../`` prefix | present | ``../CHANGES`` | forbidden |
    | bare ``*.md`` | no folder | ``CHANGELOG.md`` | forbidden |
    | bare ``*.md`` | with anchor | ``CHANGELOG.md#foo`` | forbidden (anchor stripped) |
    | scheme | external non-md | ``https://example.com`` | allowed |
    | scheme | external "docs/" segment | project URL to docs/inbox.md | allowed |

    The first three rows use an extension-less target (``CHANGES``, no
    ``.md``) rather than the more natural ``docs/inbox.md`` / ``./inbox.md``
    / ``../CONTRIBUTING.md``: every one of those *also* ends in ``.md``, so
    they would still be flagged by the bare-``*.md`` disjunct alone even if
    the ``docs/``/``./``/``../`` prefix checks were deleted entirely --
    confirmed by mutation (dropping the ``docs/`` disjunct left this test
    green when the fixture was ``docs/inbox.md``, the confounded-fixture
    failure mode this docstring exists to record). The extension-less form
    is forbidden only because of its prefix, isolating each disjunct from
    the bare-``*.md`` rule that would otherwise silently do all the work.
    """
    forbidden_cases = [
        "[a](docs/CHANGES)",
        "[b](./CHANGES)",
        "[c](../CHANGES)",
        "[d](CHANGELOG.md)",
        "[e](CHANGELOG.md#foo)",
    ]
    allowed_cases = [
        "[f](https://example.com)",
        f"[g]({_PROJECT_URL_PREFIX}docs/inbox.md)",
    ]

    for case in forbidden_cases:
        found = _forbidden_relative_doc_link_targets(case)
        assert found, f"expected {case!r} to be flagged as a relative doc link"

    for case in allowed_cases:
        found = _forbidden_relative_doc_link_targets(case)
        assert not found, f"expected {case!r} to be allowed, but got {found}"


def test_bare_relative_doc_path_helper_discriminates_every_relaxation() -> None:
    """Unit pin on :func:`_bare_relative_doc_paths` (round-1 review, finding
    1): the sibling markdown-link-syntax detector above is vacuous against a
    bare mention with no ``](...)`` syntax at all -- exactly the shape a
    plain-string constant (``CONTRACT_DOCUMENTATION_URL``), a byte-golden
    ``AGENTS.md`` text, or ordinary prose (no link markup) all use.

    | relaxation class | case | expected |
    | --- | --- | --- |
    | bare path, no link syntax | ``see docs/inbox.md in the repository`` | forbidden |
    | already the correct URL | ``https://.../blob/main/docs/inbox.md`` | allowed |
    | link label, correct href (false positive, see below) | see below | allowed |
    | a different repo-relative page | ``see docs/upgrading.md too`` | forbidden |
    | non-doc path (``.py`` not ``.md``) | ``see docs/script.py`` | allowed |

    The third row is the exact false positive round-1 review found at
    README.md's real ``[`docs/plugins.md`](https://.../blob/main/docs/plugins.md)``
    line: the backtick-quoted label is bare text identical in shape to the
    violation, immediately followed by the correct href. Without
    ``_GOOD_PROJECT_LINK_RE`` masking that whole construct out first, this
    case is wrongly forbidden -- confirmed by mutation below.

    Mutation caught (verified, then reverted byte-identically): removing the
    ``_GOOD_PROJECT_LINK_RE.sub("", text)`` masking step from
    :func:`_bare_relative_doc_paths` (so the bare-path regex runs directly
    against the unmasked text) makes the third case wrongly forbidden here,
    and also reproduces the exact real false positive this fixture is
    modeled on: ``test_shipped_and_emitted_doc_references_use_project_urls``
    fails too, flagging README.md's own real
    ``[`docs/plugins.md`](.../blob/main/docs/plugins.md)`` line -- expected
    shared reach, not a vacuous mutation, since both tests exercise the same
    masking step against the same real shape.
    """
    forbidden_cases = [
        "see docs/inbox.md in the repository",
        "see docs/upgrading.md too",
    ]
    allowed_cases = [
        f"see {_PROJECT_URL_PREFIX}docs/inbox.md for detail",
        f"[`docs/plugins.md`]({_PROJECT_URL_PREFIX}docs/plugins.md)",
        "see docs/script.py",
    ]

    for case in forbidden_cases:
        found = _bare_relative_doc_paths(case)
        assert found, f"expected {case!r} to be flagged as a bare relative doc path"

    for case in allowed_cases:
        found = _bare_relative_doc_paths(case)
        assert not found, f"expected {case!r} to be allowed, but got {found}"


_SCANNED_SHIPPED_OR_EMITTED_FILES = [
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "CHANGELOG.md",
    *sorted((_REPO_ROOT / "src" / "fitdocs" / "skills").glob("*/SKILL.md")),
]

#: A well-formed markdown link whose label names a doc page and whose href is
#: the correct project URL, e.g. README.md's own
#: ``[`docs/plugins.md`](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md)``.
#: The *label* half of that construct is bare text that happens to look like
#: a repository-relative path -- masked out below before the bare-path scan
#: runs, so a correctly-linked mention is never confused with the violation
#: 1.9 forbids (a path used *as the link target itself*, or named in prose
#: with no link at all).
_GOOD_PROJECT_LINK_RE = re.compile(
    r"\[[^\]]*\]\(" + re.escape(_PROJECT_URL_PREFIX) + r"[^)]+\)"
)

#: A repository-relative documentation path (``docs/....md``) not immediately
#: preceded by ``blob/main/`` -- i.e. not part of an already-correct project
#: URL. Round-1 review, finding 1: the markdown-link-syntax scan
#: (``_forbidden_relative_doc_link_targets``) is vacuous against a *bare*
#: mention with no ``](...)`` syntax at all -- the exact form both the
#: emitted ``CONTRACT_DOCUMENTATION_URL``/goldens (a plain string, not
#: markdown) and ``src/fitdocs/skills/fitdocs-workouts/SKILL.md:87``'s prose
#: ("see docs/inbox.md in the repository") use. This is the second,
#: independent detector that catches that form.
_BARE_RELATIVE_DOC_PATH_RE = re.compile(r"(?<!blob/main/)\bdocs/[\w.\-/]+\.md\b")


def _bare_relative_doc_paths(text: str) -> list[str]:
    """Every bare, repository-relative ``docs/*.md`` mention in ``text`` that
    is not the label half of an already-correct project-URL markdown link.

    Verified against the real repository (round-1 remediation): without the
    ``_GOOD_PROJECT_LINK_RE`` masking step, this flags a false positive at
    README.md's own ``` [`docs/plugins.md`](https://.../blob/main/docs/plugins.md) ```
    line -- the backtick-quoted *label* is bare text identical to the
    violation form, immediately followed by the correct href. Masking every
    well-formed project-URL link out first removes that label along with its
    href before the bare-path regex ever sees it, while leaving true bare
    mentions (no ``](...)`` at all) untouched.
    """
    masked = _GOOD_PROJECT_LINK_RE.sub("", text)
    return _BARE_RELATIVE_DOC_PATH_RE.findall(masked)


def test_shipped_and_emitted_doc_references_use_project_urls() -> None:
    """1.9: any documentation reference carried inside a published artifact
    (README, the packaged ``SKILL.md`` files) or emitted by the tool into a
    user's tree (the ownership declaration's ``CONTRACT_DOCUMENTATION_URL``,
    and the byte-golden ``AGENTS.md`` texts that constant renders into)
    addresses the documentation by its published project URL rather than a
    repository-relative path.

    Two independent detectors run over every scanned text: markdown-link-
    syntax targets (``_forbidden_relative_doc_link_targets``, for a
    ``](docs/....md)``-style reference) and bare mentions with no link
    syntax at all (``_bare_relative_doc_paths``, round-1 remediation --
    the first detector alone is vacuous against a bare URL string like
    ``CONTRACT_DOCUMENTATION_URL`` or a bare prose mention like
    ``SKILL.md:87``'s "see docs/inbox.md in the repository", since neither
    ever contains ``](...)`` syntax for the first detector to find).

    ``tests/test_packaging.py`` already asserts the *declared*
    ``[project.urls]`` values themselves; this test does not duplicate that
    -- it scans the shipped/emitted surfaces for the repo-relative *form*
    1.9 forbids, regardless of what ``pyproject.toml`` declares.

    Mutations caught (verified, then reverted byte-identically):
    - temporarily adding a ``[Inbox](docs/inbox.md)`` line to README.md's
      Learn More section is flagged as the sole new violation (the
      link-syntax detector);
    - temporarily rewriting ``CONTRACT_DOCUMENTATION_URL`` to the bare path
      ``"docs/ownership-contract.md"`` is flagged as the sole new violation
      (the bare-path detector) -- the link-syntax detector alone left this
      green, since a bare string has no ``](...)`` for it to match;
    - temporarily rewriting one golden's attribution line from the full URL
      to the bare path is flagged as the sole new violation, same reason;
    - ``src/fitdocs/skills/fitdocs-workouts/SKILL.md:87``'s real bare-prose
      mention ("see docs/inbox.md in the repository") is exactly the shape
      the bare-path detector exists to catch -- confirmed clean today by
      running the detector against the real file (no violation), then
      confirmed it fires by temporarily reproducing that exact sentence in
      isolation.
    """
    texts: dict[str, str] = {
        str(path.relative_to(_REPO_ROOT)): path.read_text(encoding="utf-8")
        for path in _SCANNED_SHIPPED_OR_EMITTED_FILES
    }
    texts["fitdocs.declaration.CONTRACT_DOCUMENTATION_URL"] = CONTRACT_DOCUMENTATION_URL
    golden_dir = _REPO_ROOT / "tests" / "declaration_golden"
    goldens = sorted(golden_dir.glob("*.AGENTS.md"))
    for golden in goldens:
        texts[str(golden.relative_to(_REPO_ROOT))] = golden.read_text(encoding="utf-8")

    violations: dict[str, list[str]] = {}
    for name, text in texts.items():
        forbidden = [
            *_forbidden_relative_doc_link_targets(text),
            *_bare_relative_doc_paths(text),
        ]
        if forbidden:
            violations[name] = forbidden

    # Positive controls scoped to the emitted surfaces specifically (round-1
    # review, finding 1): a project-URL count over the whole `texts` dict is
    # satisfied by README.md alone, which would leave this control green even
    # if the emitted constant/goldens were never read at all (an empty
    # `goldens` list, or `CONTRACT_DOCUMENTATION_URL` silently excluded from
    # `texts`) -- exactly the "checked zero files" vacuous-walk failure mode.
    assert goldens, "no tests/declaration_golden/*.AGENTS.md files were read"
    assert _PROJECT_URL_PREFIX in CONTRACT_DOCUMENTATION_URL, (
        "CONTRACT_DOCUMENTATION_URL is not itself in project-URL form -- the "
        "positive control below would be vacuous if it were"
    )
    for golden in goldens:
        golden_text = texts[str(golden.relative_to(_REPO_ROOT))]
        assert _PROJECT_URL_PREFIX in golden_text, (
            f"{golden} does not carry the project-URL prefix at all -- "
            "reading it proves nothing about the form this test pins"
        )

    assert not violations, (
        "shipped or emitted documentation reference(s) use a "
        f"repository-relative form instead of the project URL: {violations}"
    )

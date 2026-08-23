"""Existence and skeleton guard for `docs/reference/history-rewrites.md`
(design.md `#### ProvenanceRecord`, Req 9.1).

Before this test existed, the entire document could be deleted and the suite
stayed at 2573 passed -- Req 9.1 ("the fitdocs repository shall contain a
provenance record...") had no test tying it to anything. This test pins the
document's EXISTENCE, its required section HEADINGS (as literal Markdown H2
headings outside any fenced code block), and that each required section has
some non-whitespace body content before the next heading. It says nothing
about whether any sentence inside the document is true -- that is reviewed by
hand per `tasks.md`'s Implementation Notes ("a prose record is verified per
proposition, not per sentence"), because no mechanical check can decide the
truth of prose. A later reader must not mistake a green run of this module
for a content guarantee.

Relocated from `tests/purge/test_provenance_record.py` to `tests/` at task
9.3, alongside the two named relocations design.md `#### MachineryRetirement`
Phase R1 lists. This module's subject -- the provenance record itself -- is
not that named pair, but its survival is commanded independently of them:
Req 12.3 ("the retirement shall retain the provenance record ... and shall
remove no record Requirement 4 or Requirement 9 requires") and Req 9.1 (the
fitdocs repository shall contain it). Task 9.3's delegation to `tasks.md`'s
enumerated deletion list is conditional, not blanket -- "every deleted
module has planning, executing or verifying the history operation as its
only purpose" -- and this module's only purpose is verifying a
permanently-retained deliverable, which fails that condition. This module is
not named in either `design.md` or `tasks.md`'s deletion or relocation
lists; it was never in the deletion set's field of view, not a deliberate
omission from it.

The required headings enumerated below are exactly `design.md`'s
`ProvenanceRecord` section list, all eight: §1 through §8. §3 (the
history replacement's own record) and §7 (the remote measurement) became
required in this tuple before §8: neither heading existed in the document,
or in this tuple, before task 9.2 (2026-08-23) wrote them. §6 (the remaining
stated positions) was already present, both as a heading in the document and
in this tuple -- task 9.2 completed its body, which the document's first
commit left for "part two adds the remainder"; the heading itself is
unchanged. §8 (the retirement) is task 9.3's own Observable ("section 8 is
populated") and is now required in this tuple, because that task has run.
The task's
own `_Boundary: ProvenanceRecord_` covers a document with no module in the
Component-to-file map, so this test -- not a script under `scripts/purge/`
-- is the only tooling that owns it.

This is a loop over `_REQUIRED_HEADINGS`, so an emptied tuple would make it
vacuous; `test_required_headings_tuple_is_non_empty` is what makes that
mutation visible.

Heading extraction is a CommonMark parse (`markdown_it`), not a hand-rolled
fence scanner: fence semantics (delimiter type and length matching, the
three-space indent limit, no info string on a closer, an unclosed fence
running to end of input) are exactly what a conforming parser already
implements. `test_h2_headings_*` below exercise the extraction function
directly against synthetic markdown, since the real document contains no
fenced code blocks and so cannot exercise this on its own.
"""

from __future__ import annotations

from pathlib import Path

from markdown_it import MarkdownIt

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DOC_PATH = _REPO_ROOT / "docs" / "reference" / "history-rewrites.md"

_REQUIRED_HEADINGS = (
    "## 1. What was removed, when, why, and by which spec",
    "## 2. The 2026-07-26 email rewrite",
    "## 3. The history replacement",
    "## 4. What is no longer verifiable",
    "## 5. What detection was given up",
    "## 6. Stated positions (part two adds the remainder)",
    "## 7. The remote",
    "## 8. Retirement of the replacement machinery",
)

_MD = MarkdownIt("commonmark")


def _h2_sections_with_spans(text: str) -> list[tuple[str, int, int]]:
    """Parse `text` as CommonMark and return, for each literal H2 heading in
    document order, `(heading, heading_start_line, body_start_line)`.

    This is the extraction function: both the heading list and the
    per-section body text below are derived from its output, so a document
    heading that exists only inside a fenced code block never appears here.
    """
    tokens = _MD.parse(text)
    result: list[tuple[str, int, int]] = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open" and token.tag == "h2" and token.map:
            heading_start, body_start = token.map
            content = tokens[index + 1].content
            result.append((f"## {content}", heading_start, body_start))
    return result


def _h2_headings(text: str) -> tuple[str, ...]:
    """The literal H2 headings in `text`, in document order."""
    return tuple(heading for heading, _, _ in _h2_sections_with_spans(text))


def _sections(text: str) -> dict[str, str]:
    """Map each literal H2 heading to the body text between it and the next
    literal H2 heading (or end of document)."""
    lines = text.splitlines()
    spans = _h2_sections_with_spans(text)
    sections: dict[str, str] = {}
    for position, (heading, _, body_start) in enumerate(spans):
        body_end = spans[position + 1][1] if position + 1 < len(spans) else len(lines)
        sections[heading] = "\n".join(lines[body_start:body_end])
    return sections


def test_provenance_record_exists() -> None:
    """Req 9.1: the fitdocs repository shall contain a provenance record.

    Deleting the file entirely is the mutation this pins: with the file gone,
    `_DOC_PATH.exists()` is False and this assertion reds -- the exact gap
    that left Req 9.1 unpinned before this test existed.
    """
    assert _DOC_PATH.exists(), (
        f"{_DOC_PATH.relative_to(_REPO_ROOT)} does not exist -- Req 9.1 "
        "requires a provenance record in the fitdocs repository"
    )


def test_provenance_record_has_every_required_section_heading() -> None:
    """`design.md`'s `ProvenanceRecord` section list, all eight: §1 through
    §8 must each be present as a literal Markdown H2 heading outside any
    fenced code block. §3, §6 and §7 were added or completed by task 9.2
    (2026-08-23); §8 was added by task 9.3 (2026-08-23); §1, §2, §4 and §5
    stood since the document's first commit.
    """
    text = _DOC_PATH.read_text(encoding="utf-8")
    found_headings = _h2_headings(text)

    for heading in _REQUIRED_HEADINGS:
        assert heading in found_headings, (
            f"{heading!r} is missing from "
            f"{_DOC_PATH.relative_to(_REPO_ROOT)} -- required section "
            "headings are design.md's ProvenanceRecord section list"
        )


def test_required_sections_have_body_content() -> None:
    """`tasks.md`'s observable for task 9.2 ("the three sections are
    populated") and task 9.3 ("section 8 is populated") are pinned here
    alongside the original four: each of the eight required sections must
    have some non-whitespace text between its heading and the next literal
    heading.

    A document reduced to the eight bare headings with every body deleted
    would still pass the heading-presence check above; this assertion is
    what reds on that mutation.
    """
    text = _DOC_PATH.read_text(encoding="utf-8")
    sections = _sections(text)

    for heading in _REQUIRED_HEADINGS:
        body = sections.get(heading, "")
        assert body.strip(), (
            f"{heading!r} in {_DOC_PATH.relative_to(_REPO_ROOT)} has no "
            "body content -- tasks.md requires this section populated, "
            "not just present"
        )


def test_sections_empty_section_does_not_inherit_next_sections_body() -> None:
    """`_sections`'s body span for a heading ends at the *next* heading's
    start line, not at end of document -- except for the last heading in
    the document, which has no next heading and legitimately falls back to
    end of document. The real document's last H2 happens to be a
    non-required section, so that fallback branch is never exercised by a
    required heading in `test_required_sections_have_body_content` above; a
    mutation that used end-of-document for every section (not just the
    last) would leave that test green regardless, because it would only
    ever *add* trailing text to an already-nonempty required section.

    This synthetic two-section document isolates the boundary directly:
    §A is empty (no body content) and is *not* the last section, so its
    correct body span ends where §B begins. If body_end were end-of-document
    for every section instead, §A's "body" would incorrectly absorb §B's
    heading line and content -- an emptied section inheriting the
    following section's text -- and this assertion reds.
    """
    text = "## A\n\n## B\npopulated\n"
    sections = _sections(text)
    assert not sections["## A"].strip(), (
        f"expected an empty body for '## A', got {sections['## A']!r} -- "
        "the body span must end at the next heading, not at end of document"
    )


def test_required_headings_tuple_is_non_empty() -> None:
    """Positive control for the walks above (`change-protocol.md`'s Fixture
    Discrimination gate): if `_REQUIRED_HEADINGS` were ever emptied, the
    loops above would iterate zero times and pass having checked nothing.
    This assertion is what keeps that mutation visible -- it reds directly
    on an emptied tuple rather than relying on a loop above to notice.
    """
    assert len(_REQUIRED_HEADINGS) == 8


def test_required_headings_tuple_has_the_eight_distinct_headings() -> None:
    """Cardinality alone (`len(...) == 8`) does not pin identity: a tuple of
    eight copies of the same heading also has length 8, and would make the
    walk above check §1 eight times while never checking §2 through §8.
    This compares the tuple's actual contents against the eight literal
    headings design.md's ProvenanceRecord section list names, so that
    degenerate case reds here instead of passing silently.
    """
    assert _REQUIRED_HEADINGS == (
        "## 1. What was removed, when, why, and by which spec",
        "## 2. The 2026-07-26 email rewrite",
        "## 3. The history replacement",
        "## 4. What is no longer verifiable",
        "## 5. What detection was given up",
        "## 6. Stated positions (part two adds the remainder)",
        "## 7. The remote",
        "## 8. Retirement of the replacement machinery",
    )


# `docs/reference/history-rewrites.md` contains no fenced code blocks at all,
# so it cannot exercise `_h2_sections_with_spans`'s fence handling. These
# tests do that directly against synthetic markdown.


def test_h2_headings_inside_fence_of_same_delimiter_type_is_not_extracted() -> None:
    text = "```\n## Fenced\n```\n"
    assert _h2_headings(text) == ()


def test_h2_headings_inside_fence_nested_in_fence_of_other_type_is_not_extracted() -> (
    None
):
    text = "~~~\n```\n## Fenced\n```\n~~~\n"
    assert _h2_headings(text) == ()


def test_h2_headings_opener_longer_than_closer_stays_fenced() -> None:
    """CommonMark requires a closing fence be at least as long as its
    opener; a five-backtick opener is not closed by three backticks, so a
    too-short "closer" does not close it and the heading that follows stays
    fenced. The heading is placed after the too-short closer (not before
    it) so that a scanner which incorrectly treats the too-short line as a
    closer would expose the heading and red here."""
    text = "`````\n```\n## Fenced\nmore\n`````\n"
    assert _h2_headings(text) == ()


def test_h2_headings_indented_closer_stays_fenced() -> None:
    """CommonMark allows at most three spaces of indentation on a closing
    fence; four spaces does not close it, so the heading that follows the
    over-indented line stays fenced. The heading is placed after that line
    (not before it) so that a scanner which ignores the indent limit would
    expose the heading and red here."""
    text = "```\n    ```\n## Fenced\n```\n"
    assert _h2_headings(text) == ()


def test_h2_headings_closer_with_info_string_stays_fenced() -> None:
    """CommonMark forbids an info string on a closing fence; a line that
    looks like a closer but carries one does not close the fence, so the
    heading that follows stays fenced. The heading is placed after that
    line (not before it) so that a scanner which permits an info string on
    a closer would expose the heading and red here."""
    text = "```\n``` info\n## Fenced\n```\n"
    assert _h2_headings(text) == ()


def test_h2_headings_unclosed_fence_runs_to_end_of_input() -> None:
    text = "```\n## Fenced\n"
    assert _h2_headings(text) == ()


def test_h2_headings_h3_heading_is_not_extracted() -> None:
    """`_h2_sections_with_spans` filters on `token.tag == "h2"`; an h3 is
    reconstructed with the same hardcoded `"## "` prefix at the call site
    if that filter is ever dropped, so a missing level check would make an
    h3 indistinguishable from an h2 here. This pins that the level check is
    load-bearing."""
    text = "### Not an H2\n"
    assert _h2_headings(text) == ()


def test_h2_headings_real_heading_outside_any_fence_is_extracted() -> None:
    """True-negative control: an extractor that always returns an empty
    list would pass every fence case above. This is what reds on that
    mutation."""
    text = "## Real Heading\n"
    assert _h2_headings(text) == ("## Real Heading",)


def test_h2_headings_mid_line_triple_backtick_does_not_disturb_real_headings() -> None:
    """An inline code span written with triple backticks mid-line is not a
    fence delimiter (CommonMark fence markers must start the line); a
    conforming parser leaves surrounding headings intact."""
    text = "See ```literal``` inline.\n\n## Real Heading\n\nbody\n"
    assert _h2_headings(text) == ("## Real Heading",)

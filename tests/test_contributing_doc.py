"""Conformance for task 5.5: the contribution documentation (design.md
"ContributionDocs -- summary-only"; Req 4.5, 9.1, 9.2, 9.3, 9.4, 9.5).

`CONTRIBUTING.md` lives at the repository root and ships in neither the
sdist nor the wheel (design.md "Doc references leave the repository"), so
its internal pointers are legal as repository-relative links -- unlike a
doc that ships inside an artifact, it needs no project-URL form.

Groups:

(a) fixed H2 heading order (>= 8 headings).
(b) "The three quality gates" section names the dev-setup command and all
    three gate commands verbatim, and both the dev-setup fence and the
    combined ruff fence appear as exact fenced blocks (not paraphrased or
    split apart).
(c) "Changelog duty" section names `CHANGELOG.md`, `Unreleased`, the
    polarity-bearing "user-observable behavior, not commit subjects" phrase
    (`CHANGELOG.md`'s own convention note, quoted rather than paraphrased),
    and `tests/test_changelog.py`.
(d) "Versioning a change that moves a contract" links
    `docs/compatibility.md#version-numbering` (real slug).
(e) "Public versus internal" links `docs/compatibility.md#public-versus-internal`
    (real slug) and contains no `fitdocs.<module>` token at any depth,
    backticked or not, and no backticked name drawn from `docs/plugins.md`'s
    own "The public import surface" enumeration -- two positive controls
    show `docs/compatibility.md` carries a `fitdocs.<module>` token, and
    that the derived public-surface name set is non-empty, so an empty
    match in CONTRIBUTING.md is a deliberate by-reference choice, not an
    accident of either regex.
(f) "Publishing your own calculator" section links `docs/plugins.md` and
    `docs/contributing-calculators.md`, contains a fully bounded
    `fitdocs>=X.Y,<X.Y` range example (an open-ended lower bound alone does
    not satisfy this), names the verification command `fitdocs plugins`,
    links `docs/plugins.md#5-verify`, and contains the word "released".
(g) "Encumbered material" section carries the "must never be added" polarity
    pin, and names `FITDOCS_FORBIDDEN_STRINGS` and `scripts.check_artifacts`.
(h) every relative link on the page resolves to a real file, and every
    `#anchor` resolves to a real heading slug in its target file (or the
    page itself) -- reusing `tests/test_docs_guarantees.py`'s
    `_heading_slugs`/`_anchor_links`, with a positive control of at least
    six links.
(i) `CONTRIBUTING.md` is not in the sdist `only-include` allowlist, so it
    never ships inside a published artifact.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from tests.test_docs_guarantees import _anchor_links, _code_block_after, _heading_slugs

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC_PATH = _REPO_ROOT / "CONTRIBUTING.md"

_EXPECTED_HEADINGS = (
    "Development environment",
    "The three quality gates",
    "Changelog duty",
    "Versioning a change that moves a contract",
    "Public versus internal",
    "Publishing your own calculator",
    "Encumbered material",
    "How changes land",
)


def _text() -> str:
    assert _DOC_PATH.is_file(), "CONTRIBUTING.md does not exist"
    return _DOC_PATH.read_text(encoding="utf-8")


def _h2_headings(text: str) -> list[str]:
    return re.findall(r"^## (.+)$", text, re.M)


def _section(text: str, heading: str) -> str:
    """The text of the H2 section named ``heading``, up to the next H2 (or EOF)."""
    headings = _h2_headings(text)
    idx = headings.index(heading)
    start_pat = re.escape(f"## {heading}")
    if idx + 1 < len(headings):
        end_pat = re.escape(f"## {headings[idx + 1]}")
        match = re.search(f"{start_pat}(.*?){end_pat}", text, re.S)
    else:
        match = re.search(f"{start_pat}(.*)", text, re.S)
    assert match is not None, f"could not isolate section {heading!r}"
    return match.group(1)


# --- (a) fixed heading order ------------------------------------------------


def test_headings_appear_in_the_fixed_order() -> None:
    text = _text()
    headings = _h2_headings(text)
    assert len(_EXPECTED_HEADINGS) >= 8
    # Every expected heading must be present, in order, though other H2s
    # (there are none by design) would not break this check.
    positions = [headings.index(h) for h in _EXPECTED_HEADINGS]
    assert positions == sorted(positions), f"headings out of order: {headings!r}"
    assert set(_EXPECTED_HEADINGS).issubset(set(headings))


# --- (b) the three quality gates --------------------------------------------


def test_quality_gates_section_names_dev_setup_and_all_three_gate_commands() -> None:
    section = _section(_text(), "The three quality gates")
    assert "uv sync" in _section(_text(), "Development environment")
    for command in ("uv run pytest", "uv run ruff check", "uv run mypy"):
        assert command in section, f"gate command {command!r} missing from section"


def test_dev_setup_and_gate_commands_appear_as_exact_fenced_blocks() -> None:
    text = _text()
    assert "```\nuv sync\n```" in text, (
        "the dev-setup command is not shown as its own exact fenced block"
    )
    assert "```\nuv run ruff check . && uv run ruff format --check .\n```" in text, (
        "the combined ruff command is not shown as its own exact fenced block"
    )


# --- (c) changelog duty ------------------------------------------------------


def test_changelog_section_names_the_file_the_unreleased_heading_and_the_test() -> None:
    section = _section(_text(), "Changelog duty")
    normalized = re.sub(r"\s+", " ", section)
    changelog_text = (_REPO_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    normalized_changelog = re.sub(r"\s+", " ", changelog_text)
    quote = "entries describe user-observable behavior, not commit subjects"
    # Positive control: the exact quote must actually appear in CHANGELOG.md's
    # own convention note, or pinning it in CONTRIBUTING.md would prove
    # nothing about faithfulness to the source.
    assert quote in normalized_changelog.lower(), (
        "positive control failed -- CHANGELOG.md no longer carries the "
        "exact convention-note phrase this test pins"
    )
    assert "CHANGELOG.md" in section
    assert "Unreleased" in section
    assert quote in normalized.lower()
    assert "tests/test_changelog.py" in section


# --- (d) versioning links the real slug -------------------------------------


def test_versioning_section_links_the_real_version_numbering_slug() -> None:
    section = _section(_text(), "Versioning a change that moves a contract")
    compat_text = (_REPO_ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    real_slugs = _heading_slugs(compat_text)
    assert "version-numbering" in real_slugs
    links = _anchor_links(section)
    assert ("docs/compatibility.md", "version-numbering") in links


# --- (e) public versus internal, by reference only --------------------------


def _public_import_surface_names() -> set[str]:
    """Every name `docs/plugins.md`'s "The public import surface" section
    enumerates, drawn from its two fenced comma-separated lists (`fitdocs`
    and `fitdocs.load`)."""
    plugins_text = (_REPO_ROOT / "docs" / "plugins.md").read_text(encoding="utf-8")
    # Marker-anchored, like tests/test_docs_guarantees.py's own surface-list
    # tests: a fence-pairing scan over the whole section would capture the
    # prose between the two blocks the moment either fence gained a language
    # tag, and pass its non-empty control with a garbage set.
    names: set[str] = set()
    for marker in ("From `fitdocs`:", "From `fitdocs.load`:"):
        names.update(_code_block_after(marker, plugins_text))
    return names


def test_public_versus_internal_links_by_reference_and_names_no_module() -> None:
    section = _section(_text(), "Public versus internal")
    compat_text = (_REPO_ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    real_slugs = _heading_slugs(compat_text)
    assert "public-versus-internal" in real_slugs
    links = _anchor_links(section)
    assert ("docs/compatibility.md", "public-versus-internal") in links

    # Any depth, backticked or not -- `fitdocs.load.threshold.calculator`
    # and a bare fitdocs.version must both be caught.
    module_pattern = re.compile(r"\bfitdocs\.[A-Za-z_][\w.]*")
    assert module_pattern.search(section) is None, (
        "CONTRIBUTING.md's public-versus-internal section restates an "
        "internal or public module-qualified name instead of deferring by "
        "reference"
    )
    # Positive control: the page it defers to DOES enumerate module names,
    # so an empty match above is a deliberate omission, not a regex miss.
    assert module_pattern.search(compat_text) is not None, (
        "positive control failed -- docs/compatibility.md no longer names "
        "any fitdocs.<module> token, so the CONTRIBUTING.md assertion "
        "above cannot discriminate"
    )

    public_names = _public_import_surface_names()
    # Positive control: the derived surface must be non-empty, or the
    # restatement check below vacuously passes no matter what CONTRIBUTING
    # says.
    assert public_names, (
        "positive control failed -- docs/plugins.md's public import "
        "surface parsed to an empty set"
    )
    backticked = set(re.findall(r"`([^`]+)`", section))
    restated = backticked & public_names
    assert not restated, (
        f"CONTRIBUTING.md's public-versus-internal section restates "
        f"enumerated public name(s) {restated} instead of deferring to "
        "docs/plugins.md's own enumeration"
    )


# --- (f) publishing your own calculator -------------------------------------


def test_calculator_section_links_the_two_owning_docs_and_shows_a_range() -> None:
    section = _section(_text(), "Publishing your own calculator")
    assert "docs/plugins.md" in section
    assert "docs/contributing-calculators.md" in section
    # A bounded range, not an open-ended lower bound alone.
    assert re.search(r'"fitdocs>=\d+\.\d+,<\d+\.\d+"', section) is not None
    assert "fitdocs plugins" in section
    assert "released" in section
    links = _anchor_links(section)
    assert ("docs/plugins.md", "5-verify") in links


# --- (g) encumbered material --------------------------------------------------


def test_encumbered_section_states_the_rule_and_names_the_enforcement() -> None:
    section = _section(_text(), "Encumbered material")
    assert "must never be added" in section
    assert "FITDOCS_FORBIDDEN_STRINGS" in section
    assert "scripts.check_artifacts" in section


# --- (h) every relative link, and every anchor, resolves --------------------


def test_every_relative_link_in_contributing_doc_resolves() -> None:
    text = _text()
    targets = re.findall(r"\]\(([^)]+)\)", text)
    relative = [t for t in targets if not t.startswith(("http://", "https://", "#"))]
    # Positive control: the page must link at least six sibling files, or
    # this walk checks almost nothing.
    assert len(relative) >= 6, (
        f"CONTRIBUTING.md carries only {len(relative)} relative link(s); "
        "expected at least six to meaningfully exercise this check"
    )
    for target in relative:
        path_part = target.split("#", 1)[0]
        resolved = (_REPO_ROOT / path_part).resolve()
        assert resolved.is_file(), (
            f"CONTRIBUTING.md links {target!r}, which resolves to "
            f"{resolved}, a file that does not exist"
        )


def test_every_anchor_link_in_contributing_doc_resolves_to_a_real_heading() -> None:
    text = _text()
    links = _anchor_links(text)
    # Positive control: the page must carry at least one #anchor link.
    assert links, "CONTRIBUTING.md carries no #anchor links to check"
    own_slugs = _heading_slugs(text)
    for target_file, anchor in links:
        if target_file == "":
            real_slugs = own_slugs
            label = "CONTRIBUTING.md"
        else:
            target_path = (_REPO_ROOT / target_file).resolve()
            assert target_path.is_file(), (
                f"CONTRIBUTING.md links anchor target {target_file!r}, which "
                f"does not exist"
            )
            real_slugs = _heading_slugs(target_path.read_text(encoding="utf-8"))
            label = target_file
        assert anchor in real_slugs, (
            f"CONTRIBUTING.md links {label}#{anchor}, which matches no "
            f"heading in {label} (real slugs: {sorted(real_slugs)})"
        )


# --- (i) never ships in the sdist --------------------------------------------


def test_contributing_doc_is_not_in_the_sdist_allowlist() -> None:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    only_include = pyproject["tool"]["hatch"]["build"]["targets"]["sdist"][
        "only-include"
    ]
    assert "CONTRIBUTING.md" not in only_include

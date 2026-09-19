"""Conformance for task 5.2: install/configuration/inbox documentation and
the README rewrite (design.md "InstallDocs, ConfigurationDocs, InboxDocs",
"Modified Files -> README.md", "Doc references leave the repository"; Req
1.9, 7.1, 7.2, 7.7, 7.8, 10.6, 10.7).

Six properties, one per test group below:

(a) the three new documentation files exist with non-vacuous H1/H2 structure.
(b) the README no longer claims the project is unreleasable and states both
    install commands.
(c) every documentation-page URL the README carries is in project-URL form,
    and every such URL's page exists on disk. Task 5.7 created
    ``docs/index.md``, retiring the single named exemption that used to cover
    it (there is no blanket allowance -- every ``docs/*.md`` URL the README
    carries must resolve to a real file).
(d) the README still reaches every sibling-published section (Plugins,
    Ownership) and links to the relocated Inbox page.
(e) preservation: a curated set of >=12 distinctive phrases copied verbatim
    from the pre-rewrite README are each asserted against the *specific*
    page they relocated to (``docs/configuration.md`` for the six
    tile/cache statements, ``docs/inbox.md`` for the six inbox statements,
    ``README.md`` itself for the one statement that stayed in place) --
    never against the whole-corpus concatenation, which a moved-but-altered
    paragraph could still satisfy by accident. The positive control reads a
    committed snapshot of the pre-rewrite text
    (``tests/fixtures/readme_pre_5_2.md``), never ``git show`` against
    ``HEAD`` -- once this task's own changes are committed, ``HEAD`` *is*
    the rewritten README, and a ``git``-based control would silently start
    checking the new text against itself.
(f) ``docs/inbox.md`` itself carries the never-delete and no-watching
    guarantees (reusing the exact regexes ``tests/test_docs_guarantees.py``
    already pins these with, so the two modules cannot silently disagree
    about what the guarantee text looks like).
(g) the ``[load]``/``[history]`` defaults ``docs/configuration.md`` states
    are derived, field by field, from the real dataclasses/constants
    (``FlagSettings``, ``SufficiencySettings``, ``DEFAULT_LOAD_SETTINGS``,
    ``SEED_CONSTANTS``, ``COVERAGE_THRESHOLD``, ``DEFAULT_CHANNEL_PRIORITY``)
    rather than hand-typed numbers that can drift from the code -- three
    docs tasks in a row shipped a false sentence in prose, and
    ``compatibility.md`` makes changing a default a breaking-contract
    change, so the number itself is load-bearing. Checked both directions:
    every real field's default is the value the doc *structurally* attaches
    to its key (its own table cell or its own trailing ``(`value`)``, never
    merely the nearest backticked token -- two keys sharing a value, e.g.
    ``k_fitness``/``k_fatigue`` both ``1.0``, defeats a proximity check but
    not a structural one), and every backticked key the section names is a
    real field.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import pytest

from fitdocs.config import DATA_ROOT_ENV, POINTER_RELPATH
from fitdocs.history.settings import DEFAULT_HISTORY_SETTINGS
from fitdocs.history.sources import COVERAGE_THRESHOLD, SEED_CONSTANTS
from fitdocs.load.channels.types import SufficiencySettings
from fitdocs.load.priority import DEFAULT_CHANNEL_PRIORITY
from fitdocs.load.qa.types import FlagSettings
from fitdocs.load.settings import DEFAULT_LOAD_SETTINGS

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_URL = "https://github.com/joshua-stauffer/fitdocs"

_DOC_URL_RE = re.compile(re.escape(_REPO_URL) + r"/blob/main/(docs/[\w.\-/]+\.md)")


def _readme_text() -> str:
    return (_REPO_ROOT / "README.md").read_text(encoding="utf-8")


def _heading_lines(text: str, level: str) -> list[str]:
    """Every ATX heading line at exactly ``level`` (e.g. ``"#"`` or ``"##"``).

    Fenced code blocks (```...```) are skipped: a shell comment such as
    ``# 1. Name it explicitly ...`` inside an example command starts with
    ``"# "`` too, and without this exclusion it is indistinguishable from a
    real H1 -- confirmed empirically against docs/install.md and
    docs/configuration.md's worked examples, both of which contain such
    comments.
    """
    prefix = level + " "
    headings = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith(prefix) and not line.startswith(prefix + "#"):
            headings.append(line[len(prefix) :].strip())
    return headings


# --- (a) the three new files exist with non-vacuous heading structure ------


@pytest.mark.parametrize(
    ("relpath", "expected_h1", "min_h2"),
    [
        ("docs/install.md", "Install", 3),
        ("docs/configuration.md", "Configuration", 3),
        ("docs/inbox.md", "Inbox", 3),
    ],
)
def test_new_doc_exists_with_expected_headings(
    relpath: str, expected_h1: str, min_h2: int
) -> None:
    path = _REPO_ROOT / relpath
    assert path.is_file(), f"{relpath} does not exist"
    text = path.read_text(encoding="utf-8")

    h1s = _heading_lines(text, "#")
    assert h1s == [expected_h1], (
        f"{relpath}: expected a single H1 {expected_h1!r}, got {h1s}"
    )

    h2s = _heading_lines(text, "##")
    # Positive control folded into the assertion itself: min_h2 is >= 3 for
    # every page above, so a page collapsed to a single flat paragraph (no
    # H2 sections at all) fails here rather than passing having found none.
    assert len(h2s) >= min_h2, (
        f"{relpath}: expected at least {min_h2} H2 sections, found {h2s}"
    )


# --- (b) the README status rewrite -----------------------------------------


def test_readme_no_longer_claims_unreleasable_and_states_install_commands() -> None:
    text = _readme_text()
    assert "No installable package yet" not in text
    assert "uv tool install fitdocs" in text
    assert "pipx install fitdocs" in text


# --- 7.7: the data-root resolution order and the no-code-repo guarantee ----


def _configuration_text() -> str:
    return (_REPO_ROOT / "docs" / "configuration.md").read_text(encoding="utf-8")


#: Matches the *numbered resolution list itself* -- item 1 naming ``--out``,
#: item 2 naming the real ``fitdocs.config.DATA_ROOT_ENV`` token, item 3
#: naming the real ``fitdocs.config.POINTER_RELPATH`` token, each on its own
#: line in that order. Scoped this tightly on purpose: an unscoped
#: ``text.index(...)`` triple-ordering check over the *whole page* is
#: satisfied by the loud-failure error-message example
#: (``the --out flag`` / ``the FITDOCS_DATA environment variable`` / ``a
#: .fitdocs/data-root pointer file``, in that same order) even with the
#: numbered list deleted entirely -- confirmed: deleting the list left the
#: unscoped version of this assertion green.
_RESOLUTION_ORDER_RE = re.compile(
    r"^1\. .*--out.*\n^2\. .*"
    + re.escape(DATA_ROOT_ENV)
    + r".*\n^3\. .*"
    + re.escape(POINTER_RELPATH),
    re.M,
)


def test_configuration_doc_states_the_resolution_order_and_no_code_repo_guarantee() -> (
    None
):
    """Requirement 7.7: the resolution order (``--out`` > ``FITDOCS_DATA`` >
    the pointer file) is stated *in that order* as the numbered list itself
    (not merely somewhere on the page -- the loud-failure example lists the
    same three options and would otherwise pre-satisfy this), using the real
    tokens ``fitdocs.config`` defines rather than a hand-typed copy that
    could drift, and the "never writes into a code repository by default"
    guarantee is published verbatim.
    """
    text = _configuration_text()

    assert _RESOLUTION_ORDER_RE.search(text), (
        "docs/configuration.md's numbered data-root resolution list does "
        "not name --out, then FITDOCS_DATA, then the pointer file, in that "
        "order, as items 1/2/3"
    )

    assert "never writes into a code repository by default" in _normalized(text), (
        "docs/configuration.md no longer states the no-code-repository "
        "guarantee verbatim"
    )


# --- (c) project-URL form + on-disk existence for every README doc link ----


def test_readme_doc_urls_are_project_url_form_and_resolve_to_real_pages() -> None:
    text = _readme_text()
    found = _DOC_URL_RE.findall(text)

    # Positive control: the walk must find something, or the assertions below
    # would pass having checked zero links (a vacuous walk).
    assert len(found) >= 5, (
        f"expected at least 5 docs/*.md project-URL references in README, found {found}"
    )

    missing = [page for page in sorted(set(found)) if not (_REPO_ROOT / page).is_file()]
    assert not missing, (
        f"README references these docs/*.md pages by project URL, but they "
        f"do not exist on disk: {missing}"
    )

    # A repo-relative reference to any of the same pages is the exact defect
    # this property exists to catch (Req 1.9): the README is rendered into
    # the distribution metadata, where a repo-relative path resolves to
    # nothing. Scoped to markdown link syntax so a plain-prose mention of a
    # path (there are none today) would not false-positive.
    relative_forms = re.findall(r"\]\((docs/[\w.\-/]+\.md)[^)]*\)", text)
    assert not relative_forms, (
        f"README carries repo-relative documentation link(s), which do not "
        f"resolve once the README is rendered into distribution metadata: "
        f"{relative_forms}"
    )


# --- (d) sibling sections and the inbox link stay reachable -----------------


def test_readme_still_reaches_sibling_sections_and_the_inbox_page() -> None:
    text = _readme_text()
    # Anchored to the full line (^...$, MULTILINE): a substring check like
    # ``"## Plugins" in text`` is satisfied by a demoted ``### Plugins``
    # heading too, since "## Plugins" is itself a substring of "### Plugins"
    # -- confirmed by mutation, this is not a hypothetical.
    assert re.search(r"^## Plugins$", text, re.M), "README has no '## Plugins' heading"
    assert re.search(r"^## Ownership$", text, re.M), (
        "README has no '## Ownership' heading"
    )
    inbox_match = re.search(r"^## Inbox$", text, re.M)
    assert inbox_match is not None, "README has no '## Inbox' heading"

    tail = text[inbox_match.end() :]
    next_heading = re.search(r"^## ", tail, re.M)
    inbox_section = tail[: next_heading.start()] if next_heading else tail
    assert f"{_REPO_URL}/blob/main/docs/inbox.md" in inbox_section, (
        "README's '## Inbox' section no longer links to the relocated "
        "docs/inbox.md by project URL"
    )


# --- (e) statement-level preservation ---------------------------------------

_PRE_REWRITE_SNAPSHOT = _REPO_ROOT / "tests" / "fixtures" / "readme_pre_5_2.md"

#: Distinctive phrases copied verbatim from the pre-rewrite README (snapshot:
#: ``tests/fixtures/readme_pre_5_2.md``), each mapped to the *specific* page
#: it relocated to -- never checked against the whole-corpus concatenation,
#: which a moved-but-altered paragraph, or an unrelated coincidental match
#: elsewhere in the shipped docs (confirmed to happen:
#: ``docs/reference/history-rewrites.md`` independently contains the
#: substring "no configuration ... ever deletes an inbox file" while
#: describing an unrelated requirement number), could satisfy by accident.
#: Six route-maps/tile/cache statements relocated to ``docs/configuration.md``,
#: six inbox statements relocated to ``docs/inbox.md``, and the plugins
#: entry-point-group statement stayed in ``README.md`` in place.
_PRESERVED_PHRASES: tuple[tuple[str, str], ...] = (
    ("docs/configuration.md", "credentials, or personal data are ever sent"),
    ("docs/configuration.md", "is a persistent opt-out: it"),
    ("docs/configuration.md", "built-in OpenTopoMap alternative shown commented below"),
    ("docs/configuration.md", "rendered legibly on every map image"),
    ("docs/configuration.md", "append-only and never pruned"),
    ("docs/configuration.md", "never inside this repository or the installed package"),
    ("docs/inbox.md", "the same user-owned, fitdocs-only-reads settings file"),
    ("docs/inbox.md", "the run's output names the inbox path being drained"),
    (
        "docs/inbox.md",
        "deletion is not an option fitdocs offers, under any disposition",
    ),
    ("docs/inbox.md", "performs no watching and no scheduling of any kind"),
    ("docs/inbox.md", "<data-root>/.fitdocs/quarantine.toml"),
    ("docs/inbox.md", "published ownership contract"),
    ("README.md", "fitdocs.load_calculators` entry point"),
)


def _normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text).lower()


def test_preserved_phrases_were_really_in_the_pre_rewrite_readme() -> None:
    """Positive control for the test below: every curated phrase must
    actually have been present in the real pre-rewrite README snapshot, or
    the per-page assertions would pass having checked a phrase that was
    never there to preserve in the first place.

    Reads a committed snapshot file, never ``git show HEAD:README.md``: once
    this task's changes are committed, ``HEAD`` *is* the rewritten README,
    and the git-based form of this control would then be comparing the new
    text against itself and passing vacuously.
    """
    assert _PRE_REWRITE_SNAPSHOT.is_file(), (
        f"{_PRE_REWRITE_SNAPSHOT} is missing -- the positive control below "
        f"has nothing to check against"
    )
    pre_norm = _normalized(_PRE_REWRITE_SNAPSHOT.read_text(encoding="utf-8"))

    assert len(_PRESERVED_PHRASES) >= 12

    absent_before = [
        phrase for _, phrase in _PRESERVED_PHRASES if phrase.lower() not in pre_norm
    ]
    assert not absent_before, (
        f"positive control failed -- these phrases are not present in the "
        f"pre-rewrite README snapshot at all: {absent_before}"
    )


@pytest.mark.parametrize("page,phrase", _PRESERVED_PHRASES)
def test_preserved_phrase_appears_on_its_specific_relocated_page(
    page: str, phrase: str
) -> None:
    text = _normalized((_REPO_ROOT / page).read_text(encoding="utf-8"))
    assert phrase.lower() in text, (
        f"{page!r} no longer carries the preserved statement {phrase!r} "
        f"from the pre-rewrite README"
    )


# --- (f) docs/inbox.md carries the never-delete and no-watching guarantees -


def test_inbox_doc_carries_never_delete_and_no_watching_guarantees() -> None:
    text = (_REPO_ROOT / "docs" / "inbox.md").read_text(encoding="utf-8").lower()
    normalized = re.sub(r"\s+", " ", text)

    # Same bounded-proximity regexes tests/test_docs_guarantees.py pins these
    # guarantees with, so the two modules cannot silently drift onto
    # different notions of what the guarantee sentence looks like.
    assert re.search(
        r"no configuration[^.]{0,20}ever deletes an inbox file", normalized
    )
    assert re.search(r"performs no watching and no scheduling", normalized)
    assert re.search(
        r"drain happens only when [^.]{0,40}fitdocs sync[^.]{0,40}invoked", normalized
    )


# --- (g) [load]/[history] defaults are derived from the real code ----------


def _load_history_section_text() -> str:
    """The ``### `[load]` ...`` through ``### `[history]` ...`` block of
    ``docs/configuration.md``, up to (not including) the next ``## `` heading.

    This confines every search in this test group to the two sections that
    actually document these settings -- it does NOT, by itself, prevent one
    key's stated default from pre-satisfying a check meant for a
    *different* key inside the same confined text (two keys can share a
    value, e.g. ``k_fitness``/``k_fatigue`` both default to ``1.0``). That
    is exactly why the checks below read the value structurally attached to
    each key -- its own table cell or its own trailing ``(`value`)`` --
    rather than merely searching for the value's text anywhere nearby.
    """
    text = _configuration_text()
    start = text.index("### `[load]`")
    next_h2 = re.search(r"^## ", text[start:], re.M)
    end = start + next_h2.start() if next_h2 else len(text)
    return text[start:end]


def _format_candidates(value: object) -> list[str]:
    """Every plausible rendered form of a default value, so a structural
    match does not need to guess the doc's exact decimal-place convention."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return [str(value).lower()]
    if isinstance(value, int):
        return [str(value)]
    if isinstance(value, float):
        return sorted({f"{value:.1f}", f"{value:.2f}", repr(value), str(value)})
    return [str(value)]


def _stated_default(section: str, key: str) -> str | None:
    """The value the doc *structurally* attaches to ``key`` -- never merely
    the nearest backticked token, which two equal-valued sibling keys (e.g.
    ``k_fitness``/``k_fatigue``, both ``1.0``) or a same-bullet neighbor
    (``aerobic_drift_max_pct`` sharing a bullet with
    ``cadence_lock_max_delta_bpm``, both ``5.0``) can satisfy by accident
    regardless of ``key``'s own real value.

    Two forms this doc uses, tried in order:

    (a) **Table row** -- a line starting with ``|`` that names
        ``` `key` ```: split on ``|``, drop empty cells (the leading/
        trailing split artifacts from a well-formed row), and read the
        *first* backticked token in the *last* cell (the ``Default``
        column).
    (b) **Inline** -- ``` `key` (`value`) ``` with at most a short run of
        whitespace/punctuation between the key's closing backtick and the
        opening parenthesis (this doc wraps that gap across a line break
        in a few places).

    Returns ``None`` if neither form matches.
    """
    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and f"`{key}`" in line:
            cells = [c.strip() for c in stripped.strip("|").split("|") if c.strip()]
            # The key must be the row's OWN first cell: a cross-reference to
            # ``key`` inside another row's meaning column must neither
            # pre-satisfy nor false-fail this key's check.
            if cells and cells[0] == f"`{key}`":
                cell_match = re.search(r"`([^`]+)`", cells[-1])
                if cell_match:
                    return cell_match.group(1)

    inline_match = re.search(re.escape(f"`{key}`") + r"[^`]{0,3}\(`([^`]+)`\)", section)
    if inline_match:
        return inline_match.group(1)
    return None


#: Every ``[load]``/``[history]`` setting this section documents, with its
#: default read directly from the shipped dataclass/constant -- never a
#: hand-typed copy. Three docs tasks in a row shipped a false sentence in
#: prose, and the compatibility policy treats a default change as a breaking
#: change, so the number itself is load-bearing (design.md compatibility.md).
def _real_key_defaults() -> dict[str, object]:
    defaults: dict[str, object] = {
        "default_calculator": DEFAULT_LOAD_SETTINGS.default_calculator,
        "benchmark_staleness_days": DEFAULT_LOAD_SETTINGS.benchmark_staleness_days,
        "tau_fitness_days": SEED_CONSTANTS.tau_fitness_days,
        "tau_fatigue_days": SEED_CONSTANTS.tau_fatigue_days,
        "k_fitness": SEED_CONSTANTS.k_fitness,
        "k_fatigue": SEED_CONSTANTS.k_fatigue,
        "coverage_threshold": COVERAGE_THRESHOLD.value,
        "methodology": DEFAULT_HISTORY_SETTINGS.methodology,
    }
    sufficiency = SufficiencySettings()
    for field in dataclasses.fields(sufficiency):
        defaults[field.name] = getattr(sufficiency, field.name)
    flags = FlagSettings()
    for field in dataclasses.fields(flags):
        defaults[field.name] = getattr(flags, field.name)
    return defaults


_REAL_KEY_DEFAULTS = _real_key_defaults()

#: run/ride/walk/hike are real, valid [load.priority] discipline keys but are
#: not dataclass fields; "null" and "swim" are value/counterexample literals
#: the section legitimately quotes in backticks. None of the five is a typo
#: this reverse check should flag.
_NON_FIELD_BACKTICK_TOKENS = frozenset(
    {"null", "swim", "run", "ride", "walk", "hike", "load"}
)


@pytest.mark.parametrize("key,value", sorted(_REAL_KEY_DEFAULTS.items()))
def test_load_history_key_default_matches_the_real_code(
    key: str, value: object
) -> None:
    section = _load_history_section_text()
    assert f"`{key}`" in section, (
        f"docs/configuration.md's [load]/[history] section never mentions "
        f"the real settings key `{key}`"
    )
    stated = _stated_default(section, key)
    candidates = _format_candidates(value)
    assert stated in candidates, (
        f"docs/configuration.md states `{key}`'s default as {stated!r}, but "
        f"its real default is {value!r} (accepted renderings: {candidates})"
    )


def test_load_history_section_names_no_backticked_key_that_is_not_real() -> None:
    """The reverse direction: every backticked, settings-key-shaped token in
    the ``[load]``/``[history]`` section is either a real field or one of
    the small number of legitimate non-field literals the prose quotes
    (a discipline name, ``null``, or the ``swim`` counterexample) -- never a
    typo of a real key.
    """
    section = _load_history_section_text()
    tokens = set(re.findall(r"`([a-z][a-z0-9_]*)`", section))

    # Positive control: the walk must find real field names, or the
    # membership assertion below would pass having checked nothing.
    assert "benchmark_staleness_days" in tokens

    unknown = tokens - set(_REAL_KEY_DEFAULTS) - _NON_FIELD_BACKTICK_TOKENS
    assert not unknown, (
        f"docs/configuration.md's [load]/[history] section names backticked "
        f"key(s) that are neither a real settings field nor a known "
        f"non-field literal: {sorted(unknown)}"
    )


def test_default_channel_priority_lines_match_the_real_constant() -> None:
    """``[load.priority]``'s stated per-discipline defaults are rendered
    directly from :data:`fitdocs.load.priority.DEFAULT_CHANNEL_PRIORITY`,
    not hand-typed."""
    section = _load_history_section_text()
    for sport, channels in DEFAULT_CHANNEL_PRIORITY.items():
        channel_list = ", ".join(f'"{c.value}"' for c in channels)
        expected_line = f"{sport.value.lower()} = [{channel_list}]"
        assert expected_line in section, (
            f"docs/configuration.md does not render {sport.value.lower()}'s "
            f"real default channel priority as {expected_line!r}"
        )

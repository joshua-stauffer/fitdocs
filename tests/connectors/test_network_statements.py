"""Pins for the honest-network-statement rewrite (design: NetworkStatements,
Req 14.4).

**History.** Before this task, seven docstrings/pages each claimed to name
"the only" network-touching code in the package. Those claims went false in
two separate steps: the *module*-level claim ("only :mod:`fitdocs.tiles`
touches the network") was already false the moment
:mod:`fitdocs.connectors.http` (the connector transport) existed in the
tree, regardless of whether any CLI command used it yet; the
*command*-level claim this task writes instead ("only the connector
commands and the map tiles touch the network") is accurate today but will
itself need re-checking once tasks 5.1/5.2 wire `fitdocs connect` and
`fitdocs pull` into the CLI -- at that point the claim is exercised for the
first time rather than merely stated ahead of the commands existing.

This module pins three things about the rewrite:

* **Negative half.** None of the seven retired phrases below (collapsed to
  single spaces) appears anywhere under ``src/fitdocs/**/*.py``,
  ``README.md``, or ``docs/*.md`` any more -- including the four true
  statements the plan must not touch (``load/engine.py``, ``audit.py``,
  ``docs/contributing-calculators.md``, ``docs/plugins.md``), which stay
  green because they never used these phrases.
* **Positive half.** Each of the eight rewritten places (``docs/configuration.md``
  carries two -- the tiles-section opener and the warm-cache paragraph) now
  names the map tiles, ``fitdocs connect``, and ``fitdocs pull``, within a
  window bounded by an explicit (start, end) anchor pair scoped to the
  claim sentence -- never a whole paragraph, so an unrelated later sentence
  in the same paragraph cannot paper over a dropped mention. The five
  Python-source places also name the connector transport module,
  ``fitdocs.connectors.http``, by its real dotted path -- not "the connector
  package" or any other paraphrase. None of the eight links
  ``docs/connectors.md`` (task 7 declares that page).
* **List-contents pin.** The seven retired phrases are not just made-up
  substrings: each is a real substring of the *original* sentence this task
  replaced (:data:`ORIGINAL_SENTENCES`, transcribed verbatim from the
  pre-task source, independent of :data:`RETIRED_PHRASES` and of the current
  rewritten wording), so the scanner is proven against real prior prose, not
  a fixture invented to match itself.

Every mutation test below computes its mutated text from the **real, current
contents of the file on disk**, in memory only -- it never writes a mutated
file back to disk. That is the evidence the positive pin discriminates: a
change to the actual shipped prose, not a hand-built fixture string that
merely resembles it.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The exact phrases retired by this task, one per retired location, with the
# location on the branch this task started from (design.md
# "NetworkStatementsPin").
RETIRED_PHRASES: dict[str, str] = {
    "cli.py:98": "Network access is confined to :mod:`fitdocs.tiles`",
    "sync.py:44": "That is the *only* network access",
    "tiles.py:7": "**only** network-touching code",
    "tiles.py:246": "The only network-touching code in the package",
    "tiles.py:407": "The package's only network call",
    "README.md:66": "the only time fitdocs touches the network",
    "docs/configuration.md:73-74": "the *only* time fitdocs touches the network",
}

# The seven ORIGINAL full sentences (verbatim, transcribed from the source as
# it stood before this task -- see git history at or before 9c7b03d), one per
# RETIRED_PHRASES label. Written independently of RETIRED_PHRASES so a test
# using these can prove each retired phrase is a real substring of what was
# actually removed, not a string invented to match the scanner's own list.
# ``docs/configuration.md``'s original sentence keeps its real line break.
ORIGINAL_SENTENCES: dict[str, str] = {
    "cli.py:98": (
        "Network access is confined to :mod:`fitdocs.tiles`: the only network "
        "the tool\nperforms is fetching missing basemap tiles during "
        "``sync``/``regen`` map\nrendering, and only while tile requests are "
        "enabled (Req 4.2). Every other\noperation -- and the entire ``load`` "
        "command -- stays fully offline; a warm tile\ncache makes even map "
        "rendering network-free."
    ),
    "sync.py:44": (
        "**Offline guarantee (narrowed, Req 4.2).** The engine is offline "
        "except for one\ncarve-out: the per-file map path may fetch missing "
        "basemap tiles through the\ninjected :class:`~fitdocs.tiles.TileSource` "
        "on a cache miss while resolving a\nroute map. That is the *only* "
        "network access; every other operation --\ndiscovery, decode, "
        "identity, render, merge, write, archive -- stays fully\noffline, and "
        "the source directory remains strictly read-only. A tile that cannot"
    ),
    "tiles.py:7": (
        "This module has two halves that together own everything network- "
        "and cache-\nrelated for route-map basemap tiles. The *settings* "
        "half (below) is the typed,\nread-only ``fitdocs.toml`` ``[tiles]`` "
        "reader. The *store* half\n(:class:`TileSource`, "
        ":class:`TileUnavailableError`, :class:`TileStore`) is the\n"
        "package's **only** network-touching code (Req 4.2): it resolves a "
        "plan's tiles\ncache-first, fetching a miss politely and writing it "
        "through to the cache\natomically before returning, and gates every "
        "request behind the persistent\nopt-out."
    ),
    "tiles.py:246": (
        "# Store half: cache-first tile acquisition (Req 3.1-3.4, 4.2, 5.4)\n"
        "#\n"
        "# The only network-touching code in the package. Everything above "
        "is pure\n"
        "# configuration parsing; everything below reaches the filesystem "
        "cache and,\n"
        "# on a miss, the configured provider over HTTPS.\n"
    ),
    "tiles.py:407": (
        '    """Fetch *url* over HTTPS with the mandatory UA and timeout '
        "(Req 3.4, 4.2).\n\n"
        "    The package's only network call. Issues a single GET carrying"
    ),
    "README.md:66": (
        "## Route maps\n\n"
        "Outdoor activities get a **Map** section drawn over real basemap "
        "tiles —\nthe only time fitdocs touches the network. What leaves "
        "your machine and\nwhen, the persistent opt-out, choosing a "
        "provider, attribution, and the tile\ncache all now live in"
    ),
    "docs/configuration.md:73-74": (
        "Outdoor activities (runs, rides, and other workouts whose samples "
        "carry GPS\npositions) get a **Map** section in their document: the "
        "route drawn over real\nbasemap tiles. Rendering that map is the "
        "*only* time fitdocs touches the\nnetwork — every other operation "
        "runs fully offline."
    ),
}

# The eight rewritten places: (relative path, label, start anchor, end
# anchor). Each anchor pair spans the claim sentence (for README.md:66 and
# tiles.py:7, also the tail of the sentence before it, which carries the
# tiles wording) and is unique in its file, so `_window_after` extracts
# only that span -- a later, unrelated sentence in the same
# paragraph (docs/configuration.md's switch-off sentence, in particular)
# cannot mask a dropped mention inside the claim sentence itself.
# ``docs/configuration.md`` contributes two places -- the tiles-section
# opener (which had a retired phrase) and the separate warm-cache paragraph
# (which never had one but must still name both commands, per the task).
REWRITTEN_PLACES: list[tuple[str, str, str, str]] = [
    (
        "src/fitdocs/cli.py",
        "cli.py:98",
        "Network-capable code lives in exactly two modules",
        "send every request",
    ),
    (
        "src/fitdocs/sync.py",
        "sync.py:44",
        "this engine makes no connector request",
        "network-touching paths",
    ),
    (
        "src/fitdocs/tiles.py",
        "tiles.py:7",
        "network-touching code for map tiles (Req 4.2)",
        "only two network-touching modules",
    ),
    (
        "src/fitdocs/tiles.py",
        "tiles.py:246",
        "The network-touching code for map tiles;",
        "other network-touching module.",
    ),
    (
        "src/fitdocs/tiles.py",
        "tiles.py:407",
        "This module's only network call",
        "``fitdocs pull``.",
    ),
    (
        "README.md",
        "README.md:66",
        "drawn over real basemap tiles.",
        "touches the network.",
    ),
    (
        "docs/configuration.md",
        "docs/configuration.md:73-74",
        "basemap tiles. Rendering that map",
        "touches the network",
    ),
    (
        "docs/configuration.md",
        "docs/configuration.md:94-100",
        "Each map tile",
        "which run only when invoked",
    ),
]

# The subset of REWRITTEN_PLACES that are Python source (not README/docs
# prose): each must name the connector transport module by its real dotted
# path, not a paraphrase like "the connector package" (finding N2).
PYTHON_MODULE_PLACE_LABELS: frozenset[str] = frozenset(
    {
        "cli.py:98",
        "sync.py:44",
        "tiles.py:7",
        "tiles.py:246",
        "tiles.py:407",
    }
)

# The true statements the plan must not edit -- each named by a substring
# that must still be present verbatim, proving the scan actually looked at
# the right paragraph rather than passing by accident.
TRUE_STATEMENTS: list[tuple[str, str]] = [
    ("src/fitdocs/load/engine.py", "Fully offline"),
    ("src/fitdocs/audit.py", "never touches the network"),
    (
        "docs/contributing-calculators.md",
        "never a network fetch at compute time",
    ),
    ("docs/plugins.md", "no network access"),
]


def _collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _candidate_files() -> list[Path]:
    py_files = sorted((_REPO_ROOT / "src" / "fitdocs").rglob("*.py"))
    doc_files = sorted((_REPO_ROOT / "docs").glob("*.md"))
    return [*py_files, _REPO_ROOT / "README.md", *doc_files]


def _load_tree() -> dict[Path, str]:
    return {path: path.read_text(encoding="utf-8") for path in _candidate_files()}


def _find_retired_phrases(texts: dict[Path, str]) -> dict[Path, list[str]]:
    """Every retired phrase (whitespace collapsed) found in *texts*, by file."""
    violations: dict[Path, list[str]] = {}
    for path, text in texts.items():
        collapsed = _collapse(text)
        hits = [
            phrase
            for phrase in RETIRED_PHRASES.values()
            if _collapse(phrase) in collapsed
        ]
        if hits:
            violations[path] = hits
    return violations


def _names_tiles_and_both_commands(window: str) -> bool:
    collapsed = _collapse(window).lower()
    return (
        "map tile" in collapsed
        and "fitdocs connect" in collapsed
        and "fitdocs pull" in collapsed
    )


def _names_connector_transport_module(window: str) -> bool:
    return "fitdocs.connectors.http" in _collapse(window)


def _anchor_pattern(anchor: str) -> str:
    r"""A regex matching *anchor* with any run of whitespace in it treated as
    ``\s+`` -- so a line-wrapped anchor (prose reflows; ``fitdocs\npull``
    wraps the same two words `_collapse` would join) still matches the
    literal text on disk without this module hard-coding today's exact line
    breaks."""
    parts = re.split(r"(\s+)", anchor)
    return "".join(
        r"\s+" if part.isspace() else re.escape(part) for part in parts if part
    )


def _find_anchor(text: str, anchor: str) -> re.Match[str]:
    matches = list(re.finditer(_anchor_pattern(anchor), text))
    if len(matches) != 1:
        raise ValueError(f"anchor {anchor!r} found {len(matches)} times, not once")
    return matches[0]


def _window_after(text: str, start_anchor: str, end_anchor: str) -> str:
    """The text from *start_anchor*'s first character through *end_anchor*'s
    last character, inclusive. Raises :class:`ValueError` if either anchor is
    missing, or if the end anchor's match ends before the start anchor's
    match begins (a caller error, not a drifted anchor)."""
    start_match = _find_anchor(text, start_anchor)
    end_match = _find_anchor(text, end_anchor)
    if end_match.end() < start_match.start():
        raise ValueError(
            f"end anchor {end_anchor!r} precedes start anchor {start_anchor!r}"
        )
    return text[start_match.start() : end_match.end()]


def _place_anchors(label: str) -> tuple[str, str, str]:
    """(relative path, start anchor, end anchor) for a REWRITTEN_PLACES label."""
    for rel_path, lbl, start, end in REWRITTEN_PLACES:
        if lbl == label:
            return rel_path, start, end
    raise KeyError(label)


def _delete_phrase(text: str, phrase: str) -> str:
    """*text* with the one (whitespace-tolerant) occurrence of *phrase*
    removed. Fails loudly if *phrase* is not present exactly once, so a
    mutation test can never silently mutate nothing."""
    pattern = _anchor_pattern(phrase)
    count = len(re.findall(pattern, text))
    if count != 1:
        raise AssertionError(f"phrase {phrase!r} found {count} times, not once")
    return re.sub(pattern, "", text)


def test_delete_phrase_refuses_a_phrase_present_twice() -> None:
    with pytest.raises(AssertionError, match="2 times"):
        _delete_phrase("A `fitdocs pull`, B `fitdocs pull`, C", "`fitdocs pull`,")


def test_window_after_refuses_a_duplicated_anchor() -> None:
    text = "start one. start two. end."
    with pytest.raises(ValueError, match="2 times"):
        _window_after(text, "start", "end.")


# --------------------------------------------------------------------------
# Positive control: the scan actually reads the files it claims to.
# --------------------------------------------------------------------------


def test_candidate_scan_matches_the_real_directory_listings() -> None:
    scanned = set(_candidate_files())
    py_on_disk = {p for p in (_REPO_ROOT / "src" / "fitdocs").rglob("*.py")}
    docs_on_disk = {p for p in (_REPO_ROOT / "docs").glob("*.md")}
    readme_on_disk = {_REPO_ROOT / "README.md"}
    assert scanned == py_on_disk | docs_on_disk | readme_on_disk
    # Not vacuous: a depth-sensitive Path(__file__).parents[N] slip that
    # pointed at an empty or wrong directory would pass an equality check
    # against itself but scan nothing real.
    assert len(py_on_disk) > 50
    assert len(docs_on_disk) > 5


# --------------------------------------------------------------------------
# Negative half: no retired phrase survives anywhere in the real tree.
# --------------------------------------------------------------------------


def test_no_retired_phrase_remains_in_the_real_tree() -> None:
    texts = _load_tree()
    violations = _find_retired_phrases(texts)
    assert violations == {}


def test_true_statements_are_scanned_and_stay_green() -> None:
    """The four true statements the plan must not edit are read by the same
    scan (proving they were not merely absent from the candidate set) and
    raise no violation."""
    texts = _load_tree()
    for rel_path, needle in TRUE_STATEMENTS:
        path = _REPO_ROOT / rel_path
        assert path in texts, f"{rel_path} was not scanned"
        assert needle in texts[path], f"{rel_path} no longer contains {needle!r}"
    violations = _find_retired_phrases(texts)
    for rel_path, _ in TRUE_STATEMENTS:
        assert (_REPO_ROOT / rel_path) not in violations


# --------------------------------------------------------------------------
# List-contents pin: each retired phrase is a real substring of the
# original, pre-task sentence -- not an invented fixture.
# --------------------------------------------------------------------------


def test_original_sentences_cover_every_retired_phrase_label() -> None:
    assert set(ORIGINAL_SENTENCES) == set(RETIRED_PHRASES)


@pytest.mark.parametrize("label", sorted(RETIRED_PHRASES))
def test_original_sentence_contains_its_retired_phrase(label: str) -> None:
    """Each retired phrase is a real (whitespace-collapsed) substring of the
    verbatim pre-task sentence -- including the `docs/configuration.md`
    original's own line break between "the" and "network" at :73-74."""
    collapsed_sentence = _collapse(ORIGINAL_SENTENCES[label])
    assert _collapse(RETIRED_PHRASES[label]) in collapsed_sentence


@pytest.mark.parametrize("label", sorted(RETIRED_PHRASES))
def test_scanner_flags_the_original_sentence_standing_alone(label: str) -> None:
    """The scanner, given nothing but the verbatim original sentence (no
    file on disk, no dependency on today's rewritten wording), flags it."""
    violations = _find_retired_phrases(
        {Path("synthetic.txt"): ORIGINAL_SENTENCES[label]}
    )
    assert violations, f"the original {label} sentence was not flagged"


# --------------------------------------------------------------------------
# _window_after: the anchor mechanics themselves.
# --------------------------------------------------------------------------


def test_window_after_is_scoped_to_the_two_anchors_inclusive() -> None:
    text = "before. START one. Still inside. END here. after, excluded."
    window = _window_after(text, "START", "END here.")
    assert window == "START one. Still inside. END here."


def test_window_after_excludes_a_later_mention_in_the_same_paragraph() -> None:
    """The synthetic case the review asked for directly: a mention of the thing
    under test that appears *after* the end anchor, in the very same
    paragraph (no blank line separates them), must not leak into the
    window."""
    text = (
        "START this sentence names fitdocs pull and map tiles. END sentence "
        "here. A later sentence, same paragraph, also names fitdocs pull "
        "but must be excluded."
    )
    window = _window_after(text, "START", "END sentence here.")
    assert "must be excluded" not in window
    assert window.endswith("END sentence here.")


def test_window_after_raises_when_start_anchor_is_missing() -> None:
    with pytest.raises(ValueError, match="NOPE"):
        _window_after("some text with an END here.", "NOPE", "END here.")


def test_window_after_raises_when_end_anchor_is_missing() -> None:
    with pytest.raises(ValueError, match="NOPE"):
        _window_after("some text with a START here.", "START here.", "NOPE")


def test_window_after_raises_when_end_precedes_start() -> None:
    text = "END marker appears first. Only afterward does START marker appear."
    with pytest.raises(ValueError, match="precedes"):
        _window_after(text, "START marker", "END marker")


# --------------------------------------------------------------------------
# Positive half: each rewritten place names the map tiles, `fitdocs
# connect`, and `fitdocs pull` within its own claim-sentence window; the
# five Python places also name the connector transport module by its real
# dotted path; none links the connectors page.
# --------------------------------------------------------------------------


def test_every_rewritten_place_names_tiles_and_both_commands() -> None:
    for rel_path, label, start, end in REWRITTEN_PLACES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        window = _window_after(text, start, end)
        assert _names_tiles_and_both_commands(window), (
            f"{label} ({rel_path} between {start!r} and {end!r}) does not "
            "name both map tiles and both connector commands"
        )


@pytest.mark.parametrize("label", sorted(PYTHON_MODULE_PLACE_LABELS))
def test_every_python_place_names_the_connector_transport_module(
    label: str,
) -> None:
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    window = _window_after(text, start, end)
    assert _names_connector_transport_module(window), (
        f"{label} does not name the connector transport module "
        "fitdocs.connectors.http by its real dotted path"
    )


def test_no_rewritten_place_links_the_connectors_page() -> None:
    for rel_path, _label, start, end in REWRITTEN_PLACES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        window = _window_after(text, start, end)
        assert "connectors.md" not in window


# --------------------------------------------------------------------------
# Named mutations, computed from the real file on disk, in memory only.
# --------------------------------------------------------------------------


def test_restoring_readmes_old_sentence_reds_the_retired_phrase_pin() -> None:
    """Named mutation: restore README.md:66's old sentence."""
    rewritten = (_REPO_ROOT / "README.md").read_text(encoding="utf-8")
    old_paragraph = (
        "Outdoor activities get a **Map** section drawn over real basemap "
        "tiles —\nthe only time fitdocs touches the network. What leaves "
        "your machine and\nwhen, the persistent opt-out, choosing a "
        "provider, attribution, and the tile\ncache all now live in"
    )
    anchor = "Outdoor activities get a **Map** section"
    idx = rewritten.index(anchor)
    end = rewritten.index("\n\n", idx)
    mutated = rewritten[:idx] + old_paragraph + rewritten[end:]
    assert mutated != rewritten, "the paragraph to replace was not found"
    violations = _find_retired_phrases({Path("README.md"): mutated})
    assert violations, "restoring the retired sentence should have reddened the pin"


@pytest.mark.parametrize("label", sorted(set(RETIRED_PHRASES) - {"README.md:66"}))
def test_restoring_each_other_retired_phrase_reds_the_pin(label: str) -> None:
    """Named mutation (extended): restoring any of the other six retired
    phrases, appended into that place's own real text, reds the pin."""
    rel_path, _start, _end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    mutated = text + "\n" + RETIRED_PHRASES[label] + "\n"
    violations = _find_retired_phrases({Path(rel_path): mutated})
    assert violations, f"restoring {label}'s phrase should have reddened the pin"
    # Sole failure: the clean text for the same file must not already be
    # flagged (otherwise the mutation added nothing observable).
    assert not _find_retired_phrases({Path(rel_path): text})


def test_dropping_map_tiles_from_cli_reds_the_positive_pin() -> None:
    """Named mutation (extended): dropping "basemap tiles" from the cli.py
    claim sentence reds the positive pin."""
    rel_path, start, end = _place_anchors("cli.py:98")
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    window = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window)  # true before the mutation
    mutated_window = re.sub(r"(?i)basemap tiles", "activities", window)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_dropping_pull_clause_from_configuration_opener_reds_the_positive_pin() -> None:
    """Named mutation ("P2b"): delete "and `fitdocs pull` (fetching
    activities from it)" from the docs/configuration.md :72-78 claim
    sentence -- must red on its own, scoped to just that sentence's window,
    not the whole paragraph."""
    rel_path, start, end = _place_anchors("docs/configuration.md:73-74")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window_before)  # true before the mutation
    mutated_text = _delete_phrase(
        text, "and `fitdocs pull` (fetching activities from it)"
    )
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_dropping_connect_clause_from_configuration_opener_reds_the_positive_pin() -> (
    None
):
    """Named mutation ("P2c"): the same as above, but for the
    `fitdocs connect` clause instead of `fitdocs pull`."""
    rel_path, start, end = _place_anchors("docs/configuration.md:73-74")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window_before)  # true before the mutation
    mutated_text = _delete_phrase(
        text,
        "`fitdocs connect` (authenticating once against a configured source) and",
    )
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_dropping_pull_clause_from_configuration_warm_cache_reds_the_positive_pin() -> (
    None
):
    """Named mutation (extended, the para2 analogue of "P2b"): drop
    `fitdocs pull` from the docs/configuration.md :94-100 claim sentence."""
    rel_path, start, end = _place_anchors("docs/configuration.md:94-100")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window_before)  # true before the mutation
    mutated_text = _delete_phrase(text, "`fitdocs pull`,")
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_dropping_map_tiles_from_sync_reds_the_positive_pin() -> None:
    """Named mutation ("Q4b"): drop "map tiles and" from the
    sync.py claim sentence."""
    rel_path, start, end = _place_anchors("sync.py:44")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window_before)  # true before the mutation
    mutated_text = _delete_phrase(text, "map tiles and")
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_dropping_connect_from_sync_reds_the_positive_pin() -> None:
    """Named mutation (extended): dropping `fitdocs connect` from the
    sync.py claim sentence reds the positive pin."""
    rel_path, start, end = _place_anchors("sync.py:44")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_tiles_and_both_commands(window_before)  # true before the mutation
    mutated_text = _delete_phrase(text, "``fitdocs connect`` and")
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_tiles_and_both_commands(mutated_window)


def test_naming_the_connector_package_instead_of_the_module_reds_the_module_pin() -> (
    None
):
    """Named mutation ("N2"): cli.py's claim sentence naming the package
    `fitdocs.connectors` instead of the transport module
    `fitdocs.connectors.http` reds the module-name pin, even though the
    command-name pin (fitdocs connect/fitdocs pull still present) stays
    green -- proving the module check is not redundant with the command
    check."""
    rel_path, start, end = _place_anchors("cli.py:98")
    path = _REPO_ROOT / rel_path
    text = path.read_text(encoding="utf-8")
    window_before = _window_after(text, start, end)
    assert _names_connector_transport_module(window_before)  # true before mutation
    mutated_text = text.replace(
        ":mod:`fitdocs.connectors.http`", ":mod:`fitdocs.connectors`", 1
    )
    assert mutated_text != text, "the module reference was not found"
    mutated_window = _window_after(mutated_text, start, end)
    assert not _names_connector_transport_module(mutated_window)
    # The command-name half is untouched by this mutation -- it is a
    # different assertion catching a different defect.
    assert _names_tiles_and_both_commands(mutated_window)


def test_analytics_index_is_published_in_steering_without_changing_network_scope() -> (
    None
):
    steering = _REPO_ROOT / ".kiro" / "steering"
    tech = (steering / "tech.md").read_text(encoding="utf-8")
    structure = (steering / "structure.md").read_text(encoding="utf-8")

    architecture = tech.split("## Architecture", 1)[1].split("## Core Technologies", 1)[
        0
    ]
    flat_architecture = " ".join(architecture.split())
    assert (
        "No server, no background jobs. One database: a derived, disposable "
        "analytics index outside the data root, rebuilt from the documents "
        "and archived `.fit` files, never read back into a document."
    ) in flat_architecture
    assert (
        "Everything is re-derivable from the `.fit` + profile" not in flat_architecture
    )
    assert (
        "the index itself is a cache, not state, and deleting it costs only "
        "rebuild time." in flat_architecture
    )
    assert "Planned (Phase 10" not in flat_architecture

    libraries = tech.split("## Key Libraries", 1)[1].split(
        "## Network and Credentials", 1
    )[0]
    assert (
        "`duckdb` — the analytics index, imported only by `fitdocs.index.store`; "
        "index connections use no extensions or external file access."
    ) in " ".join(libraries.split())

    network = tech.split("## Network and Credentials", 1)[1].split(
        "## Development Standards", 1
    )[0]
    flat_network = " ".join(network.split())
    assert (
        "`history`, `plan`, `derive-benchmarks`, `index`, and rendering — makes "
        "no connector request"
    ) in flat_network
    assert (
        "Every DuckDB connection fitdocs opens has extension auto-install, "
        "extension auto-load and external file access disabled; the allow-list "
        "binds fitdocs's own connections, not an outside client that opens the "
        "index file."
    ) in flat_network
    assert "connectors add no runtime dependency" in flat_network
    assert "the frozen runtime dependency list is unchanged" not in flat_network

    organization = structure.split("## Code Organization Principles", 1)[1]
    assert (
        "`index` (the analytics index) imports `model`, `metrics`, `compose`, "
        "`ingest`, `contract`, `docio`, `docmerge`, `layout`, `athlete`, "
        "`settings`, `version` and the load payload readers; only `cli` imports "
        "it; only `index.store` imports `duckdb`."
    ) in " ".join(organization.split())

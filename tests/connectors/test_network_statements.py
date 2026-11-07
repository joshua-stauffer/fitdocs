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
* **Positive half.** Each of the nine rewritten places (``docs/configuration.md``
  carries two -- the tiles-section opener and the warm-cache paragraph; the
  connectors page's "What leaves your machine" is the ninth) now
  names the map tiles, ``fitdocs connect`` (and its registration),
  ``fitdocs disconnect``, and ``fitdocs pull``, within a
  window bounded by an explicit (start, end) anchor pair scoped to the
  claim sentence, so an unrelated later sentence in the same paragraph cannot
  paper over a dropped mention (the connectors-page window is the one
  exception in shape: it spans two paragraphs, and the second supplies the
  map-tile wording). The five
  Python-source places also name the connector transport module,
  ``fitdocs.connectors.http``, by its real dotted path -- not "the connector
  package" or any other paraphrase. None of the nine links
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

# The nine rewritten places: (relative path, label, start anchor, end
# anchor). Nine places in all. Each anchor pair spans the claim sentence
# (for README.md:66 and
# tiles.py:7, also the tail of the sentence before it, which carries the
# tiles wording) and is unique in its file, so `_window_after` extracts
# only that span -- a later, unrelated sentence in the same
# paragraph (docs/configuration.md's switch-off sentence, in particular)
# cannot mask a dropped mention inside the claim sentence itself.
# ``docs/configuration.md`` contributes two places -- the tiles-section
# opener (which had a retired phrase) and the separate warm-cache paragraph
# (which never had one but must still name both commands, per the task).
# ``docs/connectors.md`` contributes the ninth: its window spans two
# paragraphs of "What leaves your machine" (the command sentence, then the
# map-tile sentence).
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
    (
        "docs/connectors.md",
        "docs/connectors.md:what-leaves",
        "The only requests any connector instance makes",
        "network request fitdocs ever makes.",
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


def _names_disconnect(window: str) -> bool:
    return "fitdocs disconnect" in _collapse(window).lower()


def _names_registration(window: str) -> bool:
    """The window mentions the registration `fitdocs connect --register`
    performs within the connect clause itself -- after `fitdocs connect` and
    before the next `fitdocs <command>` -- as one of the whole words
    registration/registering/register (not "registered" or "registry"). A
    registration word moved into the disconnect clause does not count."""
    return (
        re.search(
            r"fitdocs connect\b(?:(?!fitdocs [a-z]).)*?"
            r"\bregist(?:ration|ering|er)\b(?:(?!fitdocs [a-z]).)*?fitdocs [a-z]",
            _collapse(window).lower(),
        )
        is not None
    )


def _names_publish_command(window: str) -> bool:
    """The window names ``fitdocs publish --yes``, the one form of the command
    that makes requests. A bare ``fitdocs publish`` or ``fitdocs publish
    --targets`` does not count."""
    return "fitdocs publish --yes" in _collapse(window).lower()


def _names_publish_no_request_forms(text: str) -> bool:
    """The text says that ``fitdocs publish`` without ``--yes`` and ``fitdocs
    publish --targets`` make no request, in one sentence."""
    collapsed = _collapse(text).lower()
    return (
        re.search(
            r"`fitdocs publish` without `--yes` and `fitdocs publish --targets` "
            r"make (?:none|no request)",
            collapsed,
        )
        is not None
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


def test_every_rewritten_place_names_disconnect_and_the_registration() -> None:
    """Req 16.9: a statement listing the network-touching commands names
    `fitdocs disconnect` and the registration of `fitdocs connect`."""
    assert len(REWRITTEN_PLACES) == 9, "a place was added or dropped"
    for rel_path, label, start, end in REWRITTEN_PLACES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        window = _window_after(text, start, end)
        assert _names_disconnect(window), (
            f"{label} ({rel_path}) lacks fitdocs disconnect"
        )
        assert _names_registration(window), (
            f"{label} ({rel_path}) lacks the registration of fitdocs connect"
        )


def _mutate_window(text: str, start: str, end: str, pattern: str, repl: str) -> str:
    """*text* with *pattern* replaced by *repl* only inside the claim window
    (the rest of the file is untouched). Fails loudly if nothing matched."""
    s_match = _find_anchor(text, start)
    e_match = _find_anchor(text, end)
    window = text[s_match.start() : e_match.end()]
    mutated, count = re.subn(pattern, repl, window)
    if count < 1:
        raise AssertionError(f"{pattern!r} not found inside the window")
    return text[: s_match.start()] + mutated + text[e_match.end() :]


@pytest.mark.parametrize("label", [lbl for _p, lbl, _s, _e in REWRITTEN_PLACES])
def test_dropping_disconnect_from_a_place_reds_the_disconnect_pin(label: str) -> None:
    """Named mutation, one per place: rename `fitdocs disconnect` inside that
    place's own window. The window's other pins stay green (sole failure)."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert _names_disconnect(_window_after(text, start, end))  # true before
    mutated = _mutate_window(
        text, start, end, r"fitdocs(\s+)disconnect", r"fitdocs\1forget"
    )
    window = _window_after(mutated, start, end)
    assert not _names_disconnect(window)
    assert _names_tiles_and_both_commands(window)
    assert _names_registration(window)


@pytest.mark.parametrize("label", [lbl for _p, lbl, _s, _e in REWRITTEN_PLACES])
def test_dropping_the_registration_from_a_place_reds_the_registration_pin(
    label: str,
) -> None:
    """Named mutation, one per place: blank every "regist..." word inside that
    place's window."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert _names_registration(_window_after(text, start, end))  # true before
    mutated = _mutate_window(text, start, end, r"(?i)regist\w*", "enrolment")
    window = _window_after(mutated, start, end)
    assert not _names_registration(window)
    assert _names_disconnect(window)
    assert _names_tiles_and_both_commands(window)


@pytest.mark.parametrize("label", [lbl for _p, lbl, _s, _e in REWRITTEN_PLACES])
def test_registered_in_place_of_the_registration_reds_the_registration_pin(
    label: str,
) -> None:
    """Named mutation, one per place: the registration word becomes
    "registered" (a source that is registered, not a registration the command
    performs). A bare "regist" substring would stay green."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    mutated = _mutate_window(text, start, end, r"(?i)\bregist\w*", "registered")
    window = _window_after(mutated, start, end)
    assert "regist" in _collapse(window).lower()  # the old substring test passes
    assert not _names_registration(window)
    assert _names_disconnect(window)
    assert _names_tiles_and_both_commands(window)


@pytest.mark.parametrize(
    ("label", "old", "new"),
    [
        (
            "README.md:66",
            "(authenticating once against a configured source, or registering "
            "with a relay)",
            "(authenticating once against a registered source)",
        ),
        (
            "cli.py:98",
            "(one authentication attempt against a configured source, the "
            "registration of a relay instance, or the consent requests of a "
            "Strava instance to its bound relay)",
            "(one authentication attempt against a registered source)",
        ),
        (
            "tiles.py:7",
            "(relay registration included)",
            "for every registered connector",
        ),
    ],
)
def test_rewriting_the_registration_clause_as_a_registered_source_reds_the_pin(
    label: str, old: str, new: str
) -> None:
    """Named mutations O1 (README), O2 (cli.py docstring), O2b (tiles.py:7)."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert _names_registration(_window_after(text, start, end))  # true before
    mutated = _mutate_window(text, start, end, _anchor_pattern(old), new)
    window = _window_after(mutated, start, end)
    assert "registered" in window
    assert not _names_registration(window)
    assert _names_disconnect(window)


@pytest.mark.parametrize(
    ("label", "old", "new"),
    [
        (
            "tiles.py:407",
            "``fitdocs connect`` (relay registration included), "
            "``fitdocs disconnect``,",
            "``fitdocs connect``, ``fitdocs disconnect`` (ending a relay "
            "registration),",
        ),
        (
            "docs/configuration.md:94-100",
            "`fitdocs connect` (including a relay registration), `fitdocs disconnect`,",
            "`fitdocs connect`, `fitdocs disconnect` (ending a relay registration),",
        ),
        (
            "docs/connectors.md:what-leaves",
            "`fitdocs connect <name>` (including a relay instance's "
            "registration), `fitdocs disconnect <name>` (a relay revocation,",
            "`fitdocs connect <name>`, `fitdocs disconnect <name>` (revoking a "
            "relay registration,",
        ),
    ],
)
def test_moving_the_registration_into_the_disconnect_clause_reds_the_pin(
    label: str, old: str, new: str
) -> None:
    """Named mutations O12 (tiles.py:407), O13 (configuration.md warm-cache),
    O14 (connectors.md): the registration word survives in the window but
    describes `fitdocs disconnect`, not `fitdocs connect`."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert _names_registration(_window_after(text, start, end))  # true before
    mutated = _mutate_window(text, start, end, _anchor_pattern(old), new)
    window = _window_after(mutated, start, end)
    assert re.search(r"\bregistration\b", _collapse(window).lower())
    assert not _names_registration(window)
    assert _names_disconnect(window)


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


_CLI_STRAVA_CONNECT = (
    "(one authentication attempt against a configured source, the "
    "registration of a relay instance, or the consent requests of a Strava "
    "instance to its bound relay)"
)
_CLI_STRAVA_DISCONNECT = (
    "(one revocation call for a relay instance, one disconnect request to its "
    "bound relay for a Strava instance, none otherwise)"
)


def test_the_cli_docstring_names_the_strava_network_requests() -> None:
    """Mutation: dropping either Strava clause from the cli.py network
    docstring reds this pin (the second assertion block runs both drops)."""
    text = _collapse((_REPO_ROOT / "src/fitdocs/cli.py").read_text(encoding="utf-8"))
    assert _CLI_STRAVA_CONNECT in text
    assert _CLI_STRAVA_DISCONNECT in text
    for pinned, dropped in (
        (
            _CLI_STRAVA_CONNECT,
            ", or the consent requests of a Strava instance to its bound relay",
        ),
        (
            _CLI_STRAVA_DISCONNECT,
            ", one disconnect request to its bound relay for a Strava instance",
        ),
    ):
        mutated = text.replace(dropped, "")
        assert mutated != text
        assert pinned not in mutated


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
    mutated_text = _delete_phrase(text, "`fitdocs pull` (fetching activities from it)")
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
        "`fitdocs connect` (authenticating once against a configured source, or "
        "registering with a relay),",
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
    mutated_text = _delete_phrase(text, "``fitdocs connect`` (registration included),")
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


def test_steering_publishes_the_relay_server_and_its_network_calls() -> None:
    steering = _REPO_ROOT / ".kiro" / "steering"
    tech = (steering / "tech.md").read_text(encoding="utf-8")
    structure = (steering / "structure.md").read_text(encoding="utf-8")

    architecture = tech.split("## Architecture", 1)[1].split("## Core Technologies", 1)[
        0
    ]
    flat_architecture = " ".join(architecture.split())
    assert "No server, no background jobs." not in flat_architecture
    assert (
        "A separately deployed relay server lives in `relay/` (package "
        "`fitdocs_relay`, Starlette served by uvicorn). It is its own "
        "distribution with its own dependencies and is never part of the "
        "`fitdocs` release."
    ) in flat_architecture
    assert "SQLite by default and PostgreSQL through an extra" in flat_architecture
    assert "the `fitdocs` CLI never imports it." in flat_architecture
    assert (
        "listed in `SHARED_MODULES` in `scripts/sync_relay_shared.py` (today "
        "`relay_codes`, `relay_envelope`, `publish.outcomes`, `relay_targets` "
        "and `identity.strict`), which the relay carries as pinned "
        "copies under `relay/src/fitdocs_relay/shared/` that a cross-check test "
        "keeps identical to their originals in the `fitdocs` package."
    ) in flat_architecture
    assert (
        "the versions are recorded in `relay/CHANGELOG.md`, tied to the "
        "constants by `relay/tests/test_contract.py`."
    ) in flat_architecture
    assert "v1" not in flat_architecture

    network = tech.split("## Network and Credentials", 1)[1].split(
        "## Development Standards", 1
    )[0]
    flat_network = " ".join(network.split())
    assert (
        "Network-capable code in the `fitdocs` package lives in exactly two places"
    ) in flat_network
    assert "Both of the package's network paths go through" in flat_network
    assert (
        "For a Strava instance, `fitdocs connect` makes one connect-start "
        "request and one poll per stated interval to its bound relay, "
        "`fitdocs disconnect` makes one disconnect request, and `fitdocs "
        "publish --yes` makes at most two requests per page; no fitdocs "
        "command contacts Strava."
    ) in flat_network
    assert (
        "`fitdocs connect` (one authentication call per attempt; for a "
        "registering relay instance, a capabilities read, a registration start "
        "and one poll per stated interval), `fitdocs disconnect` (one "
        "revocation call for a relay instance, one disconnect request to its "
        "bound relay for a Strava instance, none otherwise)"
    ) in flat_network
    assert (
        "tokens, relay tokens included, are stored per user through the same "
        "credential store outside the data root"
    ) in flat_network

    flat_structure = " ".join(structure.split())
    assert "### Relay server **Location**: `relay/`" in flat_structure
    assert (
        "It is a separate distribution with its own dependencies and is never "
        "shipped in fitdocs's release."
    ) in flat_structure
    assert (
        "`fitdocs_relay` imports nothing from `fitdocs` (its `shared/` copies "
        "stand in), and `fitdocs` never imports `fitdocs_relay`."
    ) in flat_structure
    assert (
        "byte-identical to their originals, written by "
        "`scripts/sync_relay_shared.py` and checked by "
        "`tests/test_relay_shared_copies.py`."
    ) in flat_structure
    assert (
        "(the `fitdocs connect`, `fitdocs disconnect` and `fitdocs pull` commands)"
    ) in flat_structure
    assert (
        "listed in `SHARED_MODULES` in `scripts/sync_relay_shared.py` (today "
        "`relay_codes`, `relay_envelope`, `publish.outcomes`, `relay_targets` "
        "and `identity.strict`) import nothing else from the package: "
        "`relay_codes`, `publish.outcomes` and `identity.strict` import only "
        "the standard library, `relay_envelope` only the standard library and "
        "`relay_codes`, and `relay_targets` only the standard library and "
        "`relay_envelope`."
    ) in flat_structure
    assert (
        "`identity.strict` (the strict tier of the match rule) imports only the "
        "standard library, and the relay runs a pinned copy of it."
    ) in flat_structure


# --------------------------------------------------------------------------
# Publishing (intervals-publish Req 10.1-10.4): every window names
# `fitdocs publish --yes`; the statements that list commands making no
# request name the forms that make none.
# --------------------------------------------------------------------------


def test_every_rewritten_place_names_publish_yes() -> None:
    assert len(REWRITTEN_PLACES) == 9, "a place was added or dropped"
    for rel_path, label, start, end in REWRITTEN_PLACES:
        text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
        window = _window_after(text, start, end)
        assert _names_publish_command(window), (
            f"{label} ({rel_path}) does not name `fitdocs publish --yes`"
        )


def test_publish_predicate_accepts_only_the_yes_form() -> None:
    assert _names_publish_command("and ``fitdocs publish --yes`` (requests)")
    assert _names_publish_command("`fitdocs\npublish --yes`")
    assert not _names_publish_command("and `fitdocs publish` (a dry run)")
    assert not _names_publish_command("`fitdocs publish --targets` lists")
    assert not _names_publish_command("`fitdocs publish` without `--yes`")


@pytest.mark.parametrize("label", [lbl for _p, lbl, _s, _e in REWRITTEN_PLACES])
def test_dropping_publish_yes_from_a_place_reds_the_publish_pin(label: str) -> None:
    """Named mutation, one per place: `fitdocs publish --yes` becomes the bare
    `fitdocs publish` inside that place's own window; the window's other pins
    stay green."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    assert _names_publish_command(_window_after(text, start, end))  # true before
    mutated = _mutate_window(
        text, start, end, r"fitdocs(\s+)publish(\s+)--yes", r"fitdocs\1publish"
    )
    window = _window_after(mutated, start, end)
    assert not _names_publish_command(window)
    assert _names_tiles_and_both_commands(window)
    assert _names_disconnect(window)
    assert _names_registration(window)


@pytest.mark.parametrize("label", [lbl for _p, lbl, _s, _e in REWRITTEN_PLACES])
def test_naming_publish_without_the_command_reds_the_publish_pin(label: str) -> None:
    """Named mutation, one per place: `fitdocs publish --yes` becomes
    `fitdocs publish --targets` (the command is named, the form that makes
    requests is not)."""
    rel_path, start, end = _place_anchors(label)
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8")
    mutated = _mutate_window(
        text,
        start,
        end,
        r"fitdocs(\s+)publish(\s+)--yes",
        r"fitdocs\1publish\2--targets",
    )
    window = _window_after(mutated, start, end)
    assert "fitdocs publish --targets" in _collapse(window)
    assert not _names_publish_command(window)


def _network_section_of_tech() -> str:
    tech = (_REPO_ROOT / ".kiro" / "steering" / "tech.md").read_text(encoding="utf-8")
    return tech.split("## Network and Credentials", 1)[1].split(
        "## Development Standards", 1
    )[0]


def test_tech_names_publish_yes_among_the_commands_that_make_requests() -> None:
    network = _network_section_of_tech()
    assert _names_publish_command(network)
    assert _names_publish_no_request_forms(network)


def test_dropping_publish_yes_from_tech_reds_the_publish_pin() -> None:
    network = _network_section_of_tech()
    mutated, count = re.subn(r"`fitdocs publish --yes`", "`fitdocs publish`", network)
    assert count >= 1
    assert not _names_publish_command(mutated)
    assert _names_publish_no_request_forms(mutated)


def test_dropping_the_no_request_forms_from_tech_reds_the_pin() -> None:
    network = _network_section_of_tech()
    mutated, count = re.subn(
        r"`fitdocs publish` without `--yes` and `fitdocs publish --targets` make none",
        "",
        _collapse(network),
    )
    assert count == 1
    assert not _names_publish_no_request_forms(mutated)
    assert _names_publish_command(mutated)


def _what_leaves_section() -> str:
    text = (_REPO_ROOT / "docs" / "connectors.md").read_text(encoding="utf-8")
    return text.split("\n## What leaves your machine\n", 1)[1].split("\n## ", 1)[0]


def test_connectors_page_says_where_a_publish_request_goes() -> None:
    """Req 10.3: the intervals.icu instance's publish requests go to
    intervals.icu, by name and section link, with no URL."""
    section = _what_leaves_section()
    flat = _collapse(section)
    assert (
        "An [intervals.icu](#intervalsicu) instance's publish requests go to "
        "intervals.icu"
    ) in flat
    assert "://" not in section
    assert _names_publish_no_request_forms(section)
    assert "No other fitdocs command ever makes a connector request" not in flat


def test_dropping_the_host_line_from_the_connectors_page_reds_the_pin() -> None:
    flat = _collapse(_what_leaves_section())
    mutated = flat.replace(
        "publish requests go to intervals.icu", "publish requests go"
    )
    assert mutated != flat
    assert "publish requests go to intervals.icu" not in mutated


def _tech_request_list(network: str) -> str:
    """The span that lists the commands making connector requests."""
    flat = _collapse(network)
    return flat.split("Connector requests happen only during", 1)[1].split(
        "every other command \u2014", 1
    )[0]


def _tech_no_request_sentence(network: str) -> str:
    flat = _collapse(network)
    start = flat.index("`fitdocs publish` without")
    return flat[start : flat.index(" make none.", start)]


def _tech_position_ok(network: str) -> bool:
    return (
        _names_publish_command(_tech_request_list(network))
        and "publish --yes" not in _tech_no_request_sentence(network)
        and _tech_no_request_sentence(network).startswith(
            "`fitdocs publish` without `--yes` and `fitdocs publish --targets`"
        )
    )


def test_tech_publish_yes_is_in_the_request_list_not_the_no_request_sentence() -> None:
    assert _tech_position_ok(_network_section_of_tech())


def test_moving_publish_yes_into_the_tech_no_request_sentence_reds_the_pin() -> None:
    """Named mutation (M4): `fitdocs publish --yes` leaves the list of
    commands that make requests and is named in the no-request sentence."""
    network = _collapse(_network_section_of_tech())
    mutated, n = re.subn(
        r" and `fitdocs publish --yes` \(for each page it sends to a target, any of "
        r"a listing, an update and an upload request, one at a time\)",
        "",
        network,
    )
    assert n == 1
    mutated, n = re.subn(
        r"`fitdocs publish` without `--yes`",
        "`fitdocs publish --yes` and `fitdocs publish` without `--yes`",
        mutated,
    )
    assert n == 1
    assert _names_publish_command(mutated)  # presence alone is still true
    assert _names_publish_no_request_forms(mutated)
    assert not _tech_position_ok(mutated)


def _connectors_request_clause(section: str) -> str:
    flat = _collapse(section)
    return flat.split("The only requests any connector instance makes", 1)[1].split(
        "make for that instance", 1
    )[0]


def _connectors_no_request_sentence(section: str) -> str:
    flat = _collapse(section)
    start = flat.index("`fitdocs publish` without")
    return flat[start : flat.index("configured or not.", start)]


def _connectors_position_ok(section: str) -> bool:
    return _names_publish_command(
        _connectors_request_clause(section)
    ) and not _names_publish_command(_connectors_no_request_sentence(section))


def test_connectors_publish_yes_is_in_the_request_clause() -> None:
    assert _connectors_position_ok(_what_leaves_section())


def test_moving_publish_yes_into_the_connectors_no_request_sentence_reds_the_pin() -> (
    None
):
    """Named mutation (M6): `fitdocs publish --yes` leaves "the only requests
    ... make for that instance" and heads the no-request sentence."""
    section = _collapse(_what_leaves_section())
    mutated, n = re.subn(
        r"pull` and `fitdocs publish --yes` make for that instance, while you are "
        r"running one of those four commands",
        "pull` make for that instance, while you are running one of those three "
        "commands",
        section,
    )
    assert n == 1
    mutated, n = re.subn(
        r"`fitdocs publish` without",
        "`fitdocs publish --yes`, `fitdocs publish` without",
        mutated,
    )
    assert n == 1
    assert _names_publish_command(mutated)  # presence alone is still true
    assert _names_publish_no_request_forms(mutated)
    assert not _connectors_position_ok(mutated)


_STRAVA_LINE = (
    "A [Strava](#strava) instance sends only to the relay instance it is bound "
    "to, at that instance's `url`, and never to Strava: its publish and upload "
    "requests, its connect requests and its disconnect request."
)


def test_connectors_page_says_a_strava_instance_sends_to_its_bound_relay() -> None:
    """Req 17.3: the Strava line names the bound relay's `url`, says never to
    Strava, and links the Strava section."""
    section = _what_leaves_section()
    flat = _collapse(section)
    assert flat.count(_STRAVA_LINE) == 1
    assert "://" not in section
    assert "strava.com" not in flat.lower()


def test_dropping_the_strava_line_from_the_connectors_page_reds_the_pin() -> None:
    """Named mutation: delete the Strava line from "What leaves your machine"."""
    flat = _collapse(_what_leaves_section())
    assert flat.count(_STRAVA_LINE) == 1  # true before
    mutated = flat.replace(_STRAVA_LINE, "")
    assert mutated != flat
    assert mutated.count(_STRAVA_LINE) != 1


def test_a_strava_line_sending_to_strava_reds_the_pin() -> None:
    """Named mutation: the line says requests go to Strava, not the relay."""
    flat = _collapse(_what_leaves_section())
    mutated = flat.replace("and never to Strava", "and to Strava")
    assert mutated != flat
    assert mutated.count(_STRAVA_LINE) != 1

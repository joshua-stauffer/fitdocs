"""Automated portability assertions over generated documents (task 5.3).

The golden suite (:mod:`tests.render.test_golden_docs`) freezes render output
byte-for-byte and the sync end-to-end suite (:mod:`tests.test_sync_e2e`) drives
the whole engine; this module instead pins the *document format invariants* the
design's "Document Format Contract -> Invariants" promises, so a future render
change that quietly broke portability (an absolute asset link, a second H1, a
stray plugin fence, a foreign HTML comment) fails loudly here even if it kept
byte-golden parity within some other fixture.

The invariants (design sec. "Document Format Contract"; Req 5.3, 5.4, 5.5, 2.7):

* **Valid frontmatter first** -- the document opens with a ``---``-fenced YAML
  block that ``yaml.safe_load``s to a mapping carrying ``type: workout``.
* **Exactly one H1** -- a single top-level ``#`` heading; every other heading is
  ``##`` or deeper.
* **Only relative asset links that resolve** -- every ``![...](target)`` image
  link is relative (no ``scheme://``, no leading ``/``, under ``assets/``) and,
  over a freshly synced data root, the target file exists relative to the
  document's directory. Moving the data root as a whole never breaks a link.
* **No plugin-dependent syntax** -- beyond the YAML frontmatter, the fitdocs
  region-marker HTML comments (``<!-- fitdocs:(begin|end):<id> -->``), and the
  one generated-document provenance banner (``<!-- fitdocs:generated...-->``,
  wiki-contract Req 4.2-4.4), the body carries no ``[[wikilinks]]``, no other
  HTML comments or raw HTML tags, no plugin code fences
  (``dataview``/``mermaid``/...), and no ``{{ template }}`` directives -- it
  renders in any plain markdown viewer with zero plugins.

The invariants are asserted two ways: over documents FRESHLY SYNCED into a temp
data root (the faithful ``workouts/<stem>.md`` + ``workouts/assets/`` layout,
where the on-disk link-resolution check is meaningful), both with and without an
``athlete.toml`` so the athlete-gated zone-strip asset links are exercised too;
and, as a second guard, over the committed task 5.1 goldens in link-*form* only
(task 5.1 flattened the asset files beside the documents, so their links do not
resolve on disk -- only their shape is portable-checkable there).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import timedelta, timezone, tzinfo
from pathlib import Path

import pytest
import yaml

from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.contract import GENERATED_PREFIX
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.sync import sync
from tests.fixtures import builder

# PINNED timezone: a FIXED -06:00 offset (never the system zone) so document
# stems are byte-stable wherever the suite runs, exactly as the golden and
# end-to-end suites pin it.
_TZ: tzinfo = timezone(timedelta(hours=-6))

# The strictly-ascending HR-zone dividers plus HR thresholds the athlete file
# supplies; ascending dividers unlock the zone strip (Req 8.1) so its asset link
# is exercised for on-disk resolution when ``athlete.toml`` is present.
_ZONE_DIVIDERS = (110, 125, 140, 155, 170)

# Real-shaped fixtures spanning every modality/view: a run with native power and
# sparse HR, a run without GPS, a ride without power, a strength session with no
# sets, and a minimal (generic-fallback) file. Each renders one document.
_FIXTURES: dict[str, bytes] = {
    "run_native_power_sparse_hr.fit": builder.run_native_power_sparse_hr_fit_bytes(),
    "run_no_gps.fit": builder.run_no_gps_fit_bytes(),
    "ride_no_power.fit": builder.ride_no_power_fit_bytes(),
    "strength_no_sets.fit": builder.strength_no_sets_fit_bytes(),
    "minimal.fit": builder.minimal_fit_bytes(),
}

_GOLDEN_DIR = Path(__file__).parent / "render" / "golden_docs"

# Code-fence languages that require a PKM plugin to render; a workout document
# must never emit one (Req 5.3, 5.4). Ordinary fenced code (no language, or a
# plain language like ``python``) stays portable and is not forbidden.
_PLUGIN_FENCE_LANGS = frozenset(
    {"dataview", "dataviewjs", "mermaid", "tasks", "query", "chart", "toc", "run"}
)

# The only HTML comments a portable fitdocs document may contain: the region
# markers ``<!-- fitdocs:begin:<id> -->`` / ``<!-- fitdocs:end:<id> -->`` and the
# one generated-document provenance banner (wiki-contract Req 4.2-4.4).
_REGION_COMMENT = re.compile(r"<!-- fitdocs:(?:begin|end):[a-z]+ -->")

_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_RAW_HTML_TAG = re.compile(r"<[a-zA-Z/][^>]*>")
_HEADING = re.compile(r"^(#+) ", re.MULTILINE)
_FENCE_LANG = re.compile(r"^```([A-Za-z][\w-]*)", re.MULTILINE)


def _split_frontmatter(text: str) -> tuple[str, str]:
    """Split a document into its YAML frontmatter block and its body.

    A portable fitdocs document MUST begin with a ``---``-fenced block; the split
    (maxsplit 2) yields ``["", <yaml>, <body>]``, so an opening fence is required
    for the parse to be meaningful.
    """
    assert text.startswith("---\n"), "document must open with a '---' frontmatter fence"
    parts = text.split("---\n", 2)
    assert len(parts) == 3, "frontmatter block is not closed by a second '---' fence"
    return parts[1], parts[2]


def _assert_document_invariants(
    text: str, doc_dir: Path, *, check_resolution: bool
) -> None:
    """Assert every document-format portability invariant on one document.

    ``check_resolution`` additionally requires each relative asset link to point
    at a file that exists under ``doc_dir`` -- meaningful only over a real synced
    ``workouts/`` layout, not the task 5.1 goldens (which flatten the assets).
    """
    fm_block, body = _split_frontmatter(text)

    # Valid frontmatter: parses to a mapping identifying a fitdocs workout doc.
    frontmatter = yaml.safe_load(fm_block)
    assert isinstance(frontmatter, dict), "frontmatter must be a YAML mapping"
    assert frontmatter.get("type") == "workout", "frontmatter must carry type: workout"

    # Exactly one top-level heading; all others are level two or deeper.
    headings = _HEADING.findall(body)
    h1s = [h for h in headings if len(h) == 1]
    assert len(h1s) == 1, f"expected exactly one H1, found {len(h1s)}"

    # Only relative asset links, all under assets/, each resolving on disk.
    for target in _IMAGE_LINK.findall(body):
        assert "://" not in target, f"asset link must have no scheme: {target}"
        assert not target.startswith("/"), f"asset link must not be absolute: {target}"
        assert target.startswith("assets/"), f"asset link not under assets/: {target}"
        if check_resolution:
            resolved = doc_dir / target
            assert resolved.is_file(), f"asset link does not resolve: {target}"

    # No plugin-dependent syntax beyond frontmatter + fitdocs region markers.
    assert "[[" not in body, "wikilinks are not portable"
    assert "{{" not in body, "template directives are not portable"
    for comment in _HTML_COMMENT.findall(body):
        assert _REGION_COMMENT.fullmatch(comment) or comment.startswith(
            GENERATED_PREFIX
        ), f"foreign HTML comment: {comment!r}"
    assert not _RAW_HTML_TAG.findall(body), "raw HTML tags are not portable"
    plugin_fences = [
        lang
        for lang in _FENCE_LANG.findall(body)
        if lang.lower() in _PLUGIN_FENCE_LANGS
    ]
    assert not plugin_fences, f"plugin code fences are not portable: {plugin_fences}"


def _write_athlete(data_root: Path) -> None:
    """Write an ``athlete.toml`` with ascending HR zones and HR thresholds.

    Ascending ``hr_zones`` dividers unlock the zone-strip asset (Req 8.1) so its
    doc-relative link is exercised for on-disk resolution; the read is exactly
    how the CLI loads the optional inputs.
    """
    dividers = ", ".join(str(d) for d in _ZONE_DIVIDERS)
    (data_root / ATHLETE_FILE).write_text(
        f"resting_hr_bpm = 45\nmax_hr_bpm = 190\nhr_zones = [{dividers}]\n",
        encoding="utf-8",
    )


class _ServingTiles:
    """The always-supplied basemap-tile source these portability syncs inject.

    ``tiles`` is now a required engine argument (task 6.1). Serving deterministic
    PNG bytes for any ref means the GPS-bearing native-power run now renders a Map
    section whose ``![Route map](assets/<stem>-map.svg)`` link resolves on disk --
    so the portability invariants exercise the map link too -- while the no-GPS and
    strength fixtures plan no route and never consult it. Stateless, so one shared
    instance is safe across calls.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


#: One shared, stateless serving source for the portability syncs.
_TILES: _ServingTiles = _ServingTiles()


def _synced_documents(tmp_path: Path, *, with_athlete: bool) -> list[Path]:
    """Sync every real-shaped fixture into a temp data root and return the docs.

    Mirrors the CLI: a pinned timezone and the optional athlete inputs loaded via
    :func:`~fitdocs.athlete.load_athlete_inputs`. Asserts the run itself is clean
    (one document per fixture, no failures) before the invariant checks run.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    if with_athlete:
        _write_athlete(data_root)
    for name, data in _FIXTURES.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_bytes(data)

    athlete = load_athlete_inputs(data_root)
    assert (athlete is not None) is with_athlete  # loaded exactly as the CLI sees it
    report = sync(source, data_root, athlete=athlete, tz=_TZ, tiles=_TILES)
    assert report.failures == (), f"sync reported failures: {report.failures}"
    assert len(report.written) == len(_FIXTURES)

    # Excludes the in-tree ownership declaration (``AGENTS.md``, task 4.2, Req
    # 3.7): sync places it too, and its name happens to end in ``.md``, but it
    # is not a workout document and carries no portability invariant to check.
    docs = sorted(
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    )
    assert len(docs) == len(_FIXTURES)
    return docs


# --- portability over freshly synced documents (links resolve on disk) --------


@pytest.mark.parametrize("with_athlete", [False, True])
def test_synced_documents_satisfy_portability_invariants(
    tmp_path: Path, with_athlete: bool
) -> None:
    """Every freshly synced ``workouts/*.md`` document satisfies the format
    invariants, and every relative asset link RESOLVES to a file under the
    document's directory (Req 5.3, 5.4, 5.5, 2.7).

    Run twice: without an ``athlete.toml`` (hero chart only) and with one (the
    athlete-gated ``-zones.svg`` strip link is present and must also resolve).
    Because the whole data root moves as a unit, doc-relative links never break.

    Mutation caught: an absolute or off-``assets/`` link, a dangling link to a
    missing asset file, a lost/duplicated H1, malformed frontmatter, or any
    injected plugin syntax (wikilink, foreign comment, raw tag, plugin fence,
    template directive) fails one of the per-document assertions."""
    docs = _synced_documents(tmp_path, with_athlete=with_athlete)
    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        _assert_document_invariants(text, doc.parent, check_resolution=True)


# --- second guard: portability form over the committed task 5.1 goldens -------


def test_committed_goldens_satisfy_portability_form() -> None:
    """The committed task 5.1 golden documents satisfy the same frontmatter,
    single-H1, relative-link-*form*, and no-plugin-syntax invariants (Req 5.3,
    5.5). On-disk resolution is skipped because task 5.1 flattened the asset
    files beside the documents rather than under ``assets/``.

    Mutation caught: if a future golden refresh introduced non-portable syntax or
    a second H1, this guard fails even though the byte-golden suite might still
    match its own frozen snapshot."""
    goldens = sorted(_GOLDEN_DIR.glob("*.md"))
    assert goldens, "no committed golden documents found to guard"
    for doc in goldens:
        text = doc.read_text(encoding="utf-8")
        _assert_document_invariants(text, doc.parent, check_resolution=False)


# --- negative controls: the invariant checks actually bite (RED evidence) -----


def test_invariant_checks_reject_non_portable_documents(tmp_path: Path) -> None:
    """The invariant assertions have teeth: a valid baseline passes, but each of a
    family of non-portable mutations is rejected. This is the RED counterpart to
    the green assertions above -- proof that a real portability regression would
    fail rather than silently pass."""
    baseline = (_GOLDEN_DIR / "minimal.md").read_text(encoding="utf-8")
    # The unmodified golden is portable (form only -- goldens flatten assets).
    _assert_document_invariants(baseline, tmp_path, check_resolution=False)

    mutations = [
        # Missing frontmatter fence: body only, no opening '---'.
        baseline.split("---\n", 2)[2],
        # A second top-level heading.
        baseline.replace("## Summary", "# Second Top-Level\n\n## Summary", 1),
        # Wrong document type in the frontmatter.
        baseline.replace("type: workout", "type: note", 1),
        # An absolute asset link (breaks when the data root moves).
        baseline.replace("(assets/", "(/assets/", 1),
        # A wikilink -- degrades to raw text outside a PKM.
        baseline.replace("## Summary", "## Summary\n\nSee [[Other Note]].", 1),
        # A foreign (non-fitdocs) HTML comment.
        baseline.replace("## Summary", "<!-- dataview: table -->\n\n## Summary", 1),
        # A raw HTML tag.
        baseline.replace("## Summary", "<div class='x'>\n\n## Summary", 1),
        # A plugin code fence.
        baseline.replace("## Summary", "```dataview\nTABLE\n```\n\n## Summary", 1),
        # A template directive.
        baseline.replace("## Summary", "## Summary {{ inject }}", 1),
    ]
    for bad in mutations:
        with pytest.raises(AssertionError):
            _assert_document_invariants(bad, tmp_path, check_resolution=False)

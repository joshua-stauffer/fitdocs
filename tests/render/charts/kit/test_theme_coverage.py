"""Theme coverage over every SVG golden of every registered SVG kind.

Requirements 8.5, 8.6, 10.1, 10.2, 11.4, 11.5, 16.3. The golden files are found
through the registry and the kind test modules' ``CASES`` (the naming
convention ``test_<name with - as _>.py``). The colour whitelist is a named re-pin
point: an appended palette adds its colours to ``ALLOWED_COLOURS``.
"""

from __future__ import annotations

import importlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from fitdocs.render.charts.kit.api import render_chart
from fitdocs.render.charts.kit.layout import PAD, text_width
from fitdocs.render.charts.kit.registry import KINDS
from fitdocs.render.charts.kit.schema import Output
from fitdocs.render.charts.kit.theme import INK_ROLES, style_element
from fitdocs.render.charts.palette import CATEGORICAL_RAMP, SEQUENTIAL_RAMP
from tests.render.charts.kit._helpers import Case
from tests.render.charts.kit.goldens import GOLDEN_ROOT

SVG = "{http://www.w3.org/2000/svg}"
RIGHT_MARGIN = 4.0
TOLERANCE = 1e-6

ALLOWED_COLOURS = frozenset(
    colour.lower()
    for colour in (
        *(c for role in INK_ROLES for c in (role.base, role.light, role.dark)),
        *CATEGORICAL_RAMP,
        *SEQUENTIAL_RAMP,
    )
)
FORBIDDEN_TOKENS = (
    "light-dark(",
    "currentColor",
    "<image",
    "<script",
    "<foreignObject",
)
HEX_LITERAL = re.compile(r"#[0-9a-zA-Z]+")
TEXT_OPEN = re.compile(r"<text[\s>/]")


def _svg_kind_cases() -> dict[str, tuple[Case, ...]]:
    found: dict[str, tuple[Case, ...]] = {}
    for spec in KINDS:
        if spec.output is not Output.SVG:
            continue
        module = importlib.import_module(
            f"tests.render.charts.kit.test_{spec.name.replace('-', '_')}"
        )
        found[spec.name] = module.CASES
    return found


def _walk() -> list[Path]:
    return sorted(
        path
        for name in _svg_kind_cases()
        for path in (GOLDEN_ROOT / name).glob("*.svg")
    )


def _is_full_canvas(rect: ET.Element, width: float, height: float) -> bool:
    w, h = rect.get("width") or "", rect.get("height") or ""
    if w.endswith("%") or h.endswith("%"):
        return True
    try:
        return float(w) >= width - TOLERANCE and float(h) >= height - TOLERANCE
    except ValueError:
        return False


def _colours_allowed(element: ET.Element) -> bool:
    """Attribute values only: hex literals whitelisted, fill/stroke hex or none."""
    for name, value in element.attrib.items():
        if any(h.lower() not in ALLOWED_COLOURS for h in HEX_LITERAL.findall(value)):
            return False
        if (
            name in ("fill", "stroke")
            and value != "none"
            and value.lower() not in ALLOWED_COLOURS
        ):
            return False
    return True


def violations(svg: str) -> list[str]:
    """Every theme rule ``svg`` breaks, as short codes (empty when it conforms)."""
    found: list[str] = []
    root = ET.fromstring(svg)
    styles = [e for e in root.iter(f"{SVG}style")]
    if len(styles) != 1:
        found.append("style-count")
    elif styles[0].text != style_element():
        found.append("style-text")
    if root.get("role") != "img":
        found.append("role")
    if not root.get("font-family"):
        found.append("font-family")
    children = list(root)
    if [c.tag for c in children[:2]] != [f"{SVG}title", f"{SVG}desc"]:
        found.append("title-desc-order")
    elif not all((c.text or "").strip() for c in children[:2]):
        found.append("title-desc-empty")

    texts = list(root.iter(f"{SVG}text"))
    if len(TEXT_OPEN.findall(svg)) != len(texts):
        found.append("text-count")
    if any("ck-t" not in (t.get("class") or "").split() for t in texts):
        found.append("text-class")
    for group in root.iter(f"{SVG}g"):
        if group.get("class") in ("ck-axis", "ck-grid"):
            for element in group.iter():
                if (
                    element.get("stroke") is not None
                    and "ck-s" not in (element.get("class") or "").split()
                ):
                    found.append("stroke-class")
                    break

    if any(not _colours_allowed(e) for e in root.iter()):
        found.append("colour")
    if any(e.get("id") is not None for e in root.iter()):
        found.append("id")
    for token in FORBIDDEN_TOKENS:
        if token in svg:
            found.append(f"forbidden {token}")

    width, height = (
        float(root.get("width") or "nan"),
        float(root.get("height") or "nan"),
    )
    if any(_is_full_canvas(r, width, height) for r in root.iter(f"{SVG}rect")):
        found.append("full-canvas-rect")

    for t in texts:
        size = float(t.get("font-size") or "nan")
        extent = text_width(t.text or "", size)
        x = float(t.get("x") or "nan")
        anchor = t.get("text-anchor")
        left = (
            x - extent
            if anchor == "end"
            else x - extent / 2
            if anchor == "middle"
            else x
        )
        if left < PAD - TOLERANCE or left + extent > width - RIGHT_MARGIN + TOLERANCE:
            found.append("text-extent")
            break
    return found


# --- the walk -----------------------------------------------------------------


def test_the_walk_covers_every_case_of_every_svg_kind() -> None:
    cases = _svg_kind_cases()
    assert len(cases) >= 6
    assert len(_walk()) == sum(len(c) for c in cases.values()) >= 50
    for name, kind_cases in cases.items():
        files = {p.stem for p in (GOLDEN_ROOT / name).glob("*.svg")}
        assert files == {c.name for c in kind_cases}, name


def _golden_cases() -> list[tuple[Path, Case]]:
    return [
        (GOLDEN_ROOT / name / f"{case.name}.svg", case)
        for name, cases in _svg_kind_cases().items()
        for case in cases
    ]


@pytest.mark.parametrize(
    ("path", "case"),
    _golden_cases(),
    ids=lambda v: f"{v.parent.name}/{v.stem}" if isinstance(v, Path) else v.name,
)
def test_golden_and_fresh_render_follow_the_theme(path: Path, case: Case) -> None:
    assert violations(path.read_text(encoding="utf-8")) == []
    assert violations(render_chart(case.request, case.data).text) == []


def test_the_walk_reaches_axes_grids_marks_and_colours() -> None:
    corpus = [p.read_text(encoding="utf-8") for p in _walk()]
    assert any('class="ck-axis"' in s for s in corpus)
    assert any('class="ck-grid"' in s for s in corpus)
    assert any('class="ck-marks"' in s for s in corpus)
    seen = {
        m.lower()
        for s in corpus
        for e in ET.fromstring(s).iter()
        for v in e.attrib.values()
        for m in HEX_LITERAL.findall(v)
    }
    assert seen <= ALLOWED_COLOURS
    assert {c.lower() for c in CATEGORICAL_RAMP[:3]} <= seen


# --- the checker can fail (controls over a doctored real golden) ----------------


def _base() -> str:
    return (GOLDEN_ROOT / "line" / "typical.svg").read_text(encoding="utf-8")


def _swap(svg: str, old: str, new: str) -> str:
    assert svg.count(old) >= 1, old
    return svg.replace(old, new, 1)


def _element(tag: str) -> str:
    """The first ``<tag>...</tag>`` of the base golden, verbatim."""
    base = _base()
    return base[base.index(f"<{tag}>") : base.index(f"</{tag}>") + len(tag) + 3]


TEXT_ATTRS = 'class="ck-t" fill="#7f7f7f"'
STYLE = style_element()

CONTROLS = {
    "literal text fill": (
        _swap(_base(), TEXT_ATTRS, 'fill="#333333"'),
        ["text-class", "colour"],
    ),
    "named fill with ck-t kept": (
        _swap(_base(), TEXT_ATTRS, 'class="ck-t" fill="black"'),
        ["colour"],
    ),
    "hex-like text content": (
        _swap(_base(), ">day</text>", ">Run #3 &#8212; #zzz</text>"),
        [],
    ),
    "colour outside the whitelist": (
        _swap(_base(), 'fill="#7f7f7f"', 'fill="#333333"'),
        ["colour"],
    ),
    "no style element": (
        _swap(_base(), f"<style>{STYLE}</style>", ""),
        ["style-count"],
    ),
    "second style element": (
        _swap(_base(), "</svg>", f"<style>{STYLE}</style></svg>"),
        ["style-count"],
    ),
    "changed style": (
        _swap(_base(), STYLE, STYLE.replace("#707070", "#717171", 1)),
        ["style-text"],
    ),
    "root id": (_swap(_base(), "<svg ", '<svg id="x" '), ["id"]),
    "no role": (_swap(_base(), ' role="img"', ""), ["role"]),
    "no font family": (
        _swap(_base(), ' font-family="sans-serif"', ""),
        ["font-family"],
    ),
    "desc before title": (
        _swap(
            _base(),
            _element("title") + _element("desc"),
            _element("desc") + _element("title"),
        ),
        ["title-desc-order"],
    ),
    "empty desc": (
        _swap(_base(), _element("desc"), "<desc></desc>"),
        ["title-desc-empty"],
    ),
    "axis line without ck-s": (
        _swap(
            _base(),
            '<line x1="43.2" y1="262" x2="680.8" y2="262"'
            ' class="ck-s" stroke="#7f7f7f"/>',
            '<line x1="43.2" y1="262" x2="680.8" y2="262" stroke="#7f7f7f"/>',
        ),
        ["stroke-class"],
    ),
    "light-dark": (
        _swap(_base(), "</svg>", '<path fill="light-dark(red,blue)"/></svg>'),
        ["colour", "forbidden light-dark("],
    ),
    "currentColor": (
        _swap(_base(), 'stroke="#7f7f7f"', 'stroke="currentColor"'),
        ["colour", "forbidden currentColor"],
    ),
    "image": (_swap(_base(), "</svg>", "<image/></svg>"), ["forbidden <image"]),
    "script": (_swap(_base(), "</svg>", "<script/></svg>"), ["forbidden <script"]),
    "foreignObject": (
        _swap(_base(), "</svg>", "<foreignObject/></svg>"),
        ["forbidden <foreignObject"],
    ),
    "full-canvas rect": (
        _swap(
            _base(), "</svg>", '<rect width="720" height="320" fill="#ffffff"/></svg>'
        ),
        ["colour", "full-canvas-rect"],
    ),
    "percent rect": (
        _swap(_base(), "</svg>", '<rect width="100%" height="100%"/></svg>'),
        ["full-canvas-rect"],
    ),
    "text beyond the right margin": (
        _swap(
            _base(),
            '<text x="362" y="297" text-anchor="middle"',
            '<text x="719" y="297" text-anchor="start"',
        ),
        ["text-extent"],
    ),
    "text inside the left padding": (
        _swap(
            _base(),
            '<text x="362" y="297" text-anchor="middle"',
            '<text x="7" y="297" text-anchor="start"',
        ),
        ["text-extent"],
    ),
    "text the parse cannot see": (
        _swap(_base(), "</svg>", '<!-- <text x="1"/> --></svg>'),
        ["text-count"],
    ),
}


def test_the_conforming_base_has_no_violations() -> None:
    assert violations(_base()) == []


@pytest.mark.parametrize("name", list(CONTROLS))
def test_the_checker_flags(name: str) -> None:
    svg, expected = CONTROLS[name]
    assert violations(svg) == expected


def test_a_text_at_the_exact_limits_is_inside() -> None:
    right = _swap(
        _base(),
        '<text x="362" y="297" text-anchor="middle" font-size="11" class="ck-t"'
        ' fill="#7f7f7f">day</text>',
        f'<text x="{720 - RIGHT_MARGIN}" y="297" text-anchor="end" font-size="11"'
        ' class="ck-t" fill="#7f7f7f">day</text>',
    )
    assert violations(right) == []
    left = _swap(
        _base(),
        '<text x="362" y="297" text-anchor="middle" font-size="11" class="ck-t"'
        ' fill="#7f7f7f">day</text>',
        '<text x="8" y="297" font-size="11" class="ck-t" fill="#7f7f7f">day</text>',
    )
    assert violations(left) == []

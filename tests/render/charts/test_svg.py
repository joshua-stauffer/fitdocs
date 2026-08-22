"""Behavioral tests for the deterministic SVG builder.

These exercise :mod:`fitdocs.render.charts.svg`: the minimal, portable SVG
primitive builder that the hero chart and zone strip render through. The whole
point of the module is *determinism by construction* (Req 4.1) -- identical
inputs must produce byte-identical SVG text, with no timestamps, generated ids,
or float-representation noise -- and *safety* -- attribute values are XML-escaped
so data can never break the markup.

The invariants under test:

* **Fixed numeric precision** -- :func:`fmt_num` rounds to two decimals, strips
  trailing zeros, and (critically) normalizes negative zero so ``-0.0`` and any
  value rounding to ``-0.00`` render as ``0``, never ``-0``.
* **No float noise** -- ``0.1 + 0.2`` renders as ``0.3``, not
  ``0.30000000000000004``.
* **Attribute order preserved** -- :func:`el` emits attributes in the order of
  the passed mapping; callers control order.
* **Self-closing vs. container** -- no children yields ``<tag .../>``; children
  yield ``<tag ...>...</tag>`` with children joined verbatim.
* **Escaping** -- attribute values and :func:`text` content escape ``& < > "``
  so values can never break out of the markup.
* **Determinism** -- building the same element or document twice is
  byte-identical (4.1).
"""

from __future__ import annotations

from fitdocs.render.charts.svg import el, fmt_num, svg_document, text

# --- fmt_num ----------------------------------------------------------------


def test_fmt_num_strips_trailing_zeros() -> None:
    assert fmt_num(3.0) == "3"
    assert fmt_num(3.5) == "3.5"
    assert fmt_num(3.50) == "3.5"
    assert fmt_num(100.0) == "100"


def test_fmt_num_rounds_to_two_decimals() -> None:
    assert fmt_num(3.14159) == "3.14"
    assert fmt_num(2.718) == "2.72"


def test_fmt_num_no_float_representation_noise() -> None:
    """The classic ``0.1 + 0.2`` binary-float artifact must not leak through."""
    assert 0.1 + 0.2 != 0.3  # sanity: the raw float really is noisy
    assert fmt_num(0.1 + 0.2) == "0.3"


def test_fmt_num_normalizes_negative_zero() -> None:
    """``-0.0`` and any value rounding to ``-0.00`` render as ``0`` (never
    ``-0``) -- the critical determinism trap for this module."""
    assert fmt_num(-0.0) == "0"
    assert fmt_num(-0.001) == "0"
    assert fmt_num(-0.004) == "0"
    assert fmt_num(0.0) == "0"


def test_fmt_num_keeps_genuine_negatives() -> None:
    assert fmt_num(-2.5) == "-2.5"
    assert fmt_num(-2.0) == "-2"
    assert fmt_num(-0.05) == "-0.05"


def test_fmt_num_large_values() -> None:
    assert fmt_num(1234.5) == "1234.5"
    assert fmt_num(1234.567) == "1234.57"


def test_fmt_num_is_deterministic() -> None:
    assert fmt_num(1.0 / 3.0) == fmt_num(1.0 / 3.0)


# --- el ---------------------------------------------------------------------


def test_el_no_children_is_self_closing() -> None:
    assert el("rect", {"x": "1", "y": "2"}) == '<rect x="1" y="2"/>'


def test_el_empty_attrs_no_children() -> None:
    assert el("line", {}) == "<line/>"


def test_el_with_children_wraps_and_joins_verbatim() -> None:
    assert el("g", {"id": "a"}, ["<rect/>"]) == '<g id="a"><rect/></g>'
    assert el("g", {}, ["A", "B"]) == "<g>AB</g>"


def test_el_preserves_attribute_order() -> None:
    """Attribute order follows the mapping's order exactly -- not sorted."""
    attrs = {"z": "1", "a": "2", "m": "3"}
    assert el("path", attrs) == '<path z="1" a="2" m="3"/>'
    # and a different order produces a different string
    assert el("path", {"a": "2", "z": "1"}) == '<path a="2" z="1"/>'


def test_el_escapes_attribute_values() -> None:
    """Ampersand, angle brackets, and quotes in a value are escaped so a value
    can never break out of the attribute or the element."""
    out = el("text", {"data-label": 'a & b < c > d "q"'})
    assert out == '<text data-label="a &amp; b &lt; c &gt; d &quot;q&quot;"/>'


def test_el_escapes_ampersand_first() -> None:
    """Escaping must not double-escape: ``&`` is handled before ``<``/``>``."""
    assert el("g", {"k": "<&>"}) == '<g k="&lt;&amp;&gt;"/>'


def test_el_children_may_be_a_tuple() -> None:
    assert el("g", {}, ("<a/>", "<b/>")) == "<g><a/><b/></g>"


def test_el_is_deterministic() -> None:
    attrs = {"x": "1.5", "y": "2.5", "stroke": "#d5455f"}
    assert el("polyline", attrs, ["<child/>"]) == el("polyline", attrs, ["<child/>"])


# --- text -------------------------------------------------------------------


def test_text_escapes_markup_characters() -> None:
    assert text("a & b < c > d") == "a &amp; b &lt; c &gt; d"


def test_text_as_escaped_child_content() -> None:
    assert el("text", {}, [text("HR <bpm>")]) == "<text>HR &lt;bpm&gt;</text>"


# --- svg_document -----------------------------------------------------------


def test_svg_document_has_namespace_and_viewbox() -> None:
    out = svg_document(800, 260, ["<rect/>"])
    assert out.startswith(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="800" height="260" viewBox="0 0 800 260">'
    )
    assert out.endswith("</svg>")
    assert "<rect/>" in out


def test_svg_document_wraps_multiple_children_in_order() -> None:
    out = svg_document(10, 20, ["<a/>", "<b/>"])
    assert "<a/><b/>" in out


def test_svg_document_has_no_timestamp_or_generated_id() -> None:
    """No run-time nondeterminism leaks into the root element (4.1)."""
    out = svg_document(100, 50, [])
    assert "id=" not in out
    assert "date" not in out.lower()
    assert "time" not in out.lower()


def test_svg_document_is_byte_identical_across_builds() -> None:
    children = ['<rect x="1"/>', '<line y="2"/>']
    assert svg_document(800, 260, children) == svg_document(800, 260, children)

"""Deterministic, minimal SVG element builder (Req 4.1, 7.1).

fitdocs renders charts as static SVG text by hand -- no matplotlib, no template
engine -- so that a workout document displays in any markdown renderer with zero
plugins. This module is the primitive layer the hero chart and HR-zone strip
build on: three pure string-producing functions that guarantee *determinism by
construction*.

Determinism guarantees (identical inputs -> byte-identical output, Req 4.1):

- **Fixed numeric precision.** :func:`fmt_num` formats a float to at most two
  decimals with no float-representation noise, so ``0.1 + 0.2`` renders as
  ``"0.3"`` and never ``"0.30000000000000004"``.
- **Negative-zero normalization.** ``-0.0`` -- and any value that rounds to
  ``-0.00`` -- renders as ``"0"``, never ``"-0"``. This is the one non-obvious
  determinism trap in float formatting: a downstream coordinate computed as a
  tiny negative would otherwise flip a byte between runs. The convention here is
  explicit: **a value whose two-decimal rounding equals zero renders as the
  single character ``"0"``, sign discarded.**
- **Stable attribute order.** :func:`el` emits attributes in the exact order of
  the passed mapping; callers pass ordered dicts and thus control order. Nothing
  is sorted, and no attribute is added implicitly.
- **No nondeterministic content.** Nothing here reads the clock, generates ids,
  or draws on randomness. The builder emits no ``<script>`` and no external
  references -- only the portable presentation-attribute subset (``svg``, ``g``,
  ``path``, ``polyline``, ``rect``, ``circle``, ``line``, ``text``, and
  ``image`` -- the last carrying its bitmap inline as a base64 ``data:`` payload
  via the SVG2 ``href`` attribute, never ``xlink:href``), which restriction is a
  caller discipline; :func:`el` itself is generic.

Attribute values (and :func:`text` content) are XML-escaped so recorded data can
never break out of the markup. This module imports the standard library only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

SVG_NAMESPACE = "http://www.w3.org/2000/svg"


def fmt_num(value: float) -> str:
    """Format ``value`` to fixed two-decimal precision, compactly and
    deterministically (Req 4.1).

    The value is rounded to two decimals, then trailing zeros and a trailing
    decimal point are stripped for compactness: ``3.0 -> "3"``, ``3.5 -> "3.5"``,
    ``3.14159 -> "3.14"``. Rounding happens on the ``round`` result formatted at
    a fixed width, so binary-float artifacts never leak through
    (``fmt_num(0.1 + 0.2) == "0.3"``).

    Negative zero is normalized: any value whose two-decimal rounding is zero --
    ``-0.0``, ``-0.001``, ``0.0`` -- renders as the single character ``"0"``,
    never ``"-0"``. Genuine negatives keep their sign (``-2.5 -> "-2.5"``).
    """
    rounded = round(float(value), 2)
    if rounded == 0.0:
        # Covers +0.0 and -0.0 (which compare equal): emit canonical "0",
        # discarding a negative sign so -0.0 never renders as "-0".
        return "0"
    text = f"{rounded:.2f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _escape_attr(value: str) -> str:
    """Escape a string for safe use inside a double-quoted XML attribute.

    ``&`` is escaped first so the entity ampersands introduced for ``<``, ``>``,
    and ``"`` are not double-escaped.
    """
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def text(content: str) -> str:
    """Return ``content`` XML-escaped for use as element text (child) content.

    Callers pass the result as a child string to :func:`el` (for example inside a
    ``text`` element). Escapes ``&``, ``<``, ``>``, and ``"`` -- a superset of
    what text content strictly requires, which keeps it safe to reuse anywhere a
    child string is expected.
    """
    return _escape_attr(content)


def el(
    tag: str,
    attrs: Mapping[str, str],
    children: Sequence[str] = (),
) -> str:
    """Render one XML element to a string, deterministically (Req 4.1).

    Attributes are emitted in the iteration order of ``attrs`` (nothing is
    sorted), each value XML-escaped so it cannot break the markup. With no
    ``children`` the element is self-closing -- ``<tag k="v"/>``. With children,
    they are joined verbatim (they are already-rendered element or escaped-text
    strings) between an open and close tag -- ``<tag k="v">child0child1</tag>``.

    Pass escaped text content via :func:`text`; pass nested elements as the
    strings returned by :func:`el`. The tag whitelist (the portable
    presentation-attribute subset) is a caller discipline -- ``el`` is generic --
    but it never emits scripts or external references on its own.
    """
    parts = [f' {key}="{_escape_attr(val)}"' for key, val in attrs.items()]
    attr_text = "".join(parts)
    if children:
        return f"<{tag}{attr_text}>{''.join(children)}</{tag}>"
    return f"<{tag}{attr_text}/>"


def svg_document(width: int, height: int, children: Sequence[str]) -> str:
    """Wrap ``children`` in a root ``<svg>`` element (Req 4.1, 7.1).

    The root carries the SVG namespace, ``width``/``height``, and a matching
    ``viewBox="0 0 <width> <height>"`` in fixed attribute order -- no timestamps,
    no generated ids, no randomness. The result is valid, portable SVG.
    """
    attrs = {
        "xmlns": SVG_NAMESPACE,
        "width": str(width),
        "height": str(height),
        "viewBox": f"0 0 {width} {height}",
    }
    return el("svg", attrs, children)

"""The kinds listing, as text and as markdown, from the registry's description.

The caller passes ``describe_kinds()`` entries read at run time; this module
holds no kind name and no count. It keeps its own cell escaper: a table cell
needs only ``|`` and line breaks neutralised, whereas the kit's markdown
escaper would also backslash the ``_``, ``*`` and ``#`` that may appear in
kit-authored channel, option and rule text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

Listing = Mapping[str, object]


def _one_line(text: object) -> str:
    return " ".join(str(text).split())


def _cell(text: object) -> str:
    return _one_line(text).replace("|", "\\|")


def _number(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _number(value)


def _items(listing: Listing, key: str) -> list[Mapping[str, object]]:
    return list(cast("Sequence[Mapping[str, object]]", listing[key]))


def _strings(item: Mapping[str, object], key: str) -> list[str]:
    return [str(v) for v in cast("Sequence[object]", item[key])]


def _bound(listing: Listing) -> str:
    b = cast("Mapping[str, object]", listing["bound"])
    return f"{b['limit']} {b['counts']}, over {b['over']} — {_one_line(b['rule'])}"


def _range(option: Mapping[str, object], joiner: str) -> str | None:
    lo, hi = option["minimum"], option["maximum"]
    if lo is None and hi is None:
        return None
    low = "" if lo is None else _number(lo)
    high = "" if hi is None else _number(hi)
    return f"{low}{joiner}{high}"


def _text_option(option: Mapping[str, object]) -> str:
    parts = [str(option["name"]), str(option["type"])]
    if option["default"] is not None:
        parts.append(f"default={_scalar(option['default'])}")
    choices = _strings(option, "choices")
    if choices:
        parts.append(f"choices={'|'.join(choices)}")
    span = _range(option, "..")
    if span is not None:
        parts.append(f"range={span}")
    return " ".join(parts)


def kinds_text(listings: Sequence[Listing]) -> str:
    """One block per kind, in the order given."""
    blocks: list[str] = []
    for listing in listings:
        description = _one_line(listing["description"])
        lines = [f"{listing['name']} ({listing['output']}) — {description}"]
        channels = _items(listing, "channels")
        if channels:
            lines.append("  channels:")
            for c in channels:
                star = "*" if c["required"] else ""
                lines.append(
                    f"    {c['name']}{star} {'|'.join(_strings(c, 'accepts'))}"
                )
        options = _items(listing, "options")
        if options:
            lines.append("  options:")
            lines.extend(f"    {_text_option(o)}" for o in options)
        lines.append(f"  bound: {_bound(listing)}")
        blocks.append("\n".join(lines) + "\n")
    return "\n".join(blocks)


def _md_values(option: Mapping[str, object]) -> str:
    choices = _strings(option, "choices")
    if choices:
        return ", ".join(choices)
    lo, hi = option["minimum"], option["maximum"]
    if lo is not None and hi is not None:
        return f"{_number(lo)} to {_number(hi)}"
    if lo is not None:
        return f"{_number(lo)} and up"
    if hi is not None:
        return f"up to {_number(hi)}"
    return "-"


def kinds_markdown(listings: Sequence[Listing]) -> str:
    """One H3 section per kind, in the order given."""
    blocks: list[str] = []
    for listing in listings:
        parts = [
            f"### `{listing['name']}`",
            _one_line(listing["description"]),
            f"Output: {listing['output']}",
        ]
        channels = _items(listing, "channels")
        if channels:
            rows = [
                "| Channel | Required | Accepts | Description |",
                "|---|---|---|---|",
            ]
            for c in channels:
                rows.append(
                    f"| {_cell(c['name'])} | {'yes' if c['required'] else 'no'} "
                    f"| {_cell(', '.join(_strings(c, 'accepts')))} "
                    f"| {_cell(c['description'])} |"
                )
            parts.append("\n".join(rows))
        options = _items(listing, "options")
        if options:
            rows = [
                "| Option | Type | Default | Values | Description |",
                "|---|---|---|---|---|",
            ]
            for o in options:
                default = "-" if o["default"] is None else _scalar(o["default"])
                rows.append(
                    f"| {_cell(o['name'])} | {_cell(o['type'])} | {_cell(default)} "
                    f"| {_cell(_md_values(o))} | {_cell(o['description'])} |"
                )
            parts.append("\n".join(rows))
        parts.append(f"Bound: {_bound(listing)}")
        blocks.append("\n\n".join(parts) + "\n")
    return "\n".join(blocks)

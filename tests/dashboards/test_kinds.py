"""The kinds listing: exact text and markdown over stubs, and the live registry."""

from __future__ import annotations

import re
from collections.abc import Mapping

from fitdocs.dashboards.kinds import kinds_markdown, kinds_text
from fitdocs.render.charts.kit import describe_kinds, kind_names

# Names are deliberately not alphabetical (zeta before alpha) so sorting shows.
SVG_STUB: dict[str, object] = {
    "name": "zeta",
    "description": "Zeta marks over x",
    "output": "svg",
    "channels": [
        {
            "name": "x",
            "required": True,
            "accepts": ["number", "date"],
            "description": "The position.",
        },
        {
            "name": "color",
            "required": False,
            "accepts": ["category"],
            "description": "One series per value.",
        },
    ],
    "options": [
        {
            "name": "scale",
            "type": "choice",
            "default": "linear",
            "choices": ["linear", "log"],
            "minimum": None,
            "maximum": None,
            "description": "The axis scale.",
        },
        {
            "name": "width",
            "type": "integer",
            "default": 720,
            "choices": [],
            "minimum": 320.0,
            "maximum": 1600.0,
            "description": "Width in pixels.",
        },
        {
            "name": "stack",
            "type": "boolean",
            "default": False,
            "choices": [],
            "minimum": None,
            "maximum": None,
            "description": "Stack the series.",
        },
        {
            "name": "bin_width",
            "type": "number",
            "default": None,
            "choices": [],
            "minimum": 0.5,
            "maximum": None,
            "description": "Bin width.",
        },
        {
            "name": "cap",
            "type": "number",
            "default": None,
            "choices": [],
            "minimum": None,
            "maximum": 30.0,
            "description": "Upper cap.",
        },
        {
            "name": "offset",
            "type": "number",
            "default": None,
            "choices": [],
            "minimum": None,
            "maximum": None,
            "description": "Plain.",
        },
    ],
    "bound": {
        "limit": 2000,
        "counts": "rows",
        "over": "refuse",
        "rule": "At most 2000 rows.",
    },
    "max_series": 8,
}

MARKDOWN_STUB: dict[str, object] = {
    "name": "alpha",
    "description": "Alpha text",
    "output": "markdown",
    "channels": [],
    "options": [],
    "bound": {
        "limit": 50,
        "counts": "cells",
        "over": "reduce",
        "rule": "Keeps 50 cells.",
    },
    "max_series": None,
}

STUBS = (SVG_STUB, MARKDOWN_STUB)

EXPECTED_TEXT = """\
zeta (svg) — Zeta marks over x
  channels:
    x* number|date
    color category
  options:
    scale choice default=linear choices=linear|log
    width integer default=720 range=320..1600
    stack boolean default=false
    bin_width number range=0.5..
    cap number range=..30
    offset number
  bound: 2000 rows, over refuse — At most 2000 rows.

alpha (markdown) — Alpha text
  bound: 50 cells, over reduce — Keeps 50 cells.
"""

EXPECTED_MARKDOWN = """\
### `zeta`

Zeta marks over x

Output: svg

| Channel | Required | Accepts | Description |
|---|---|---|---|
| x | yes | number, date | The position. |
| color | no | category | One series per value. |

| Option | Type | Default | Values | Description |
|---|---|---|---|---|
| scale | choice | linear | linear, log | The axis scale. |
| width | integer | 720 | 320 to 1600 | Width in pixels. |
| stack | boolean | false | - | Stack the series. |
| bin_width | number | - | 0.5 and up | Bin width. |
| cap | number | - | up to 30 | Upper cap. |
| offset | number | - | - | Plain. |

Bound: 2000 rows, over refuse — At most 2000 rows.

### `alpha`

Alpha text

Output: markdown

Bound: 50 cells, over reduce — Keeps 50 cells.
"""


def test_text_listing_is_pinned_exactly() -> None:
    assert kinds_text(STUBS) == EXPECTED_TEXT


def test_markdown_listing_is_pinned_exactly() -> None:
    assert kinds_markdown(STUBS) == EXPECTED_MARKDOWN


def test_listings_keep_the_given_order_not_name_order() -> None:
    names = [str(s["name"]) for s in STUBS]
    assert names != sorted(names)  # the fixture is out of name order
    text = kinds_text(STUBS)
    md = kinds_markdown(STUBS)
    assert text.index("zeta") < text.index("alpha")
    assert md.index("### `zeta`") < md.index("### `alpha`")
    reversed_md = kinds_markdown(tuple(reversed(STUBS)))
    assert reversed_md.index("### `alpha`") < reversed_md.index("### `zeta`")


def test_required_channels_carry_the_star_and_optional_ones_do_not() -> None:
    lines = kinds_text(STUBS).splitlines()
    assert "    x* number|date" in lines
    assert "    color category" in lines
    assert not any(line.startswith("    color*") for line in lines)


def test_pipe_and_newline_in_descriptions_are_escaped_in_the_markdown_table() -> None:
    stub: dict[str, object] = {
        **SVG_STUB,
        "channels": [
            {
                "name": "x",
                "required": True,
                "accepts": ["number"],
                "description": "left | right\nsecond line",
            }
        ],
        "options": [],
    }
    md = kinds_markdown([stub])
    row = next(line for line in md.splitlines() if line.startswith("| x |"))
    assert row == "| x | yes | number | left \\| right second line |"
    # The row still has exactly the table's five pipes once escapes are removed.
    assert row.replace("\\|", "").count("|") == 5
    assert "second line" in row  # the newline did not push text onto its own line


def test_a_newline_in_a_description_cannot_start_a_generated_marker_line() -> None:
    stub: dict[str, object] = {
        **MARKDOWN_STUB,
        "description": "first\n<!-- fitdocs: chart -->",
    }
    for out in (kinds_text([stub]), kinds_markdown([stub])):
        assert "first" in out
        assert not any(line.startswith("<!-- fitdocs:") for line in out.splitlines())


def test_live_registry_markdown_has_one_h3_per_kind_in_order() -> None:
    listings: tuple[Mapping[str, object], ...] = describe_kinds()
    names = kind_names()
    assert names  # the loop below is not vacuous
    md = kinds_markdown(listings)
    h3 = [line for line in md.splitlines() if line.startswith("### ")]
    assert h3 == [f"### `{name}`" for name in names]


def test_live_registry_text_has_one_header_per_kind_in_order() -> None:
    listings = describe_kinds()
    text = kinds_text(listings)
    headers = [line for line in text.splitlines() if line and not line.startswith(" ")]
    assert len(headers) == len(listings)
    for header, listing in zip(headers, listings, strict=True):
        assert header.startswith(f"{listing['name']} ({listing['output']}) — ")


def test_live_registry_output_has_no_generated_marker_line() -> None:
    listings = describe_kinds()
    assert listings
    for out in (kinds_text(listings), kinds_markdown(listings)):
        assert out.strip()
        assert not any(line.startswith("<!-- fitdocs:") for line in out.splitlines())


def test_every_free_text_field_is_flattened_so_no_marker_line_appears() -> None:
    marker = "first\n<!-- fitdocs:chart -->"
    stub: dict[str, object] = {
        **SVG_STUB,
        "channels": [
            {
                "name": "x",
                "required": True,
                "accepts": ["number"],
                "description": marker,
            }
        ],
        "options": [
            {
                "name": "w",
                "type": "integer",
                "default": 1,
                "choices": [],
                "minimum": None,
                "maximum": None,
                "description": marker,
            }
        ],
        "bound": {
            "limit": 1,
            "counts": "rows",
            "over": "refuse",
            "rule": marker,
        },
    }
    # Text carries only the bound rule; markdown carries all three fields.
    for out, present in ((kinds_text([stub]), 1), (kinds_markdown([stub]), 3)):
        assert out.count("<!-- fitdocs:chart -->") == present
        assert not any(line.startswith("<!-- fitdocs:") for line in out.splitlines())


def test_live_registry_sections_list_every_channel_and_option() -> None:
    listings = describe_kinds()
    assert listings
    md = kinds_markdown(listings)
    sections = re.split(r"(?m)^(?=### )", md)
    sections = [sec for sec in sections if sec.strip()]
    assert len(sections) == len(listings)
    for section, listing in zip(sections, listings, strict=True):
        assert section.startswith(f"### `{listing['name']}`")
        channels = listing["channels"]
        options = listing["options"]
        assert ("| Channel |" in section) == bool(channels)
        assert ("| Option |" in section) == bool(options)
        for channel in channels:
            assert f"| {channel['name']} |" in section
        for option in options:
            assert f"| {option['name']} |" in section


def test_live_registry_text_blocks_list_every_channel_and_option() -> None:
    listings = describe_kinds()
    assert listings
    text = kinds_text(listings)
    blocks = re.split(r"(?m)^(?=\S)", text)
    blocks = [block for block in blocks if block.strip()]
    assert len(blocks) == len(listings)
    for block, listing in zip(blocks, listings, strict=True):
        lines = block.splitlines()
        assert lines[0].startswith(f"{listing['name']} (")
        channels = listing["channels"]
        options = listing["options"]
        assert ("  channels:" in lines) == bool(channels)
        assert ("  options:" in lines) == bool(options)
        for channel in channels:
            star = "*" if channel["required"] else ""
            accepts = "|".join(channel["accepts"])
            assert f"    {channel['name']}{star} {accepts}" in lines
        for option in options:
            assert any(
                line.startswith(f"    {option['name']} {option['type']}")
                for line in lines
            )

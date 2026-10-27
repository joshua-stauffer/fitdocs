"""A fixed fake basemap for render-level tests (compact-chart-assets Req 3.1).

``compose_map`` embeds a :class:`~fitdocs.render.charts.map.Basemap` without
decoding it, so render-level goldens and structural tests use this literal value
rather than a real encode: the bytes are not an image, nothing depends on a
platform's WebP encoder, and no tile is involved. The placement and size cannot
be written exactly with two decimals, so a two-decimal embedding changes them.

Import it as ``from tests.support.basemap import FAKE_BASEMAP, FAKE_PAYLOAD``.
"""

from __future__ import annotations

import base64
from typing import Final

from fitdocs.render.charts.map import Basemap

FAKE_DATA: Final = b"fitdocs fake basemap \x00\x01\x02\xfd\xfe\xff"
FAKE_BASEMAP: Final = Basemap(
    mime="image/webp",
    data=FAKE_DATA,
    x=-0.3333,
    y=-0.6667,
    width=801.3333,
    height=500.6667,
)
#: The base64 text ``compose_map`` writes after ``data:image/webp;base64,``.
FAKE_PAYLOAD: Final = base64.b64encode(FAKE_DATA).decode("ascii")
#: The ``<image>`` placement attributes ``compose_map`` writes for it.
FAKE_PLACEMENT: Final = 'x="-0.3333" y="-0.6667" width="801.3333" height="500.6667"'

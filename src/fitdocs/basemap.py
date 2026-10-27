"""Viewport-cropped raster basemap composition and encoding.

Spec: compact-chart-assets 3.1-3.4, 3.7, 4.1, 4.2, 4.4, 5.1, 5.2, 5.4.

This is the only module in ``src/`` that touches the image library, and it
imports it only inside functions (or under ``TYPE_CHECKING``). It does no file
I/O, no network and reads no clock.

:func:`compose_canvas` decodes each resolved tile as PNG, JPEG or WebP, picks
one pixel density for the whole canvas (the highest tile density, never below
one pixel per output unit), alpha-composites every tile onto opaque white, and
returns the integer-aligned canvas covering the viewport together with its
fractional placement in output units.

A decoded tile must be square with an edge of at most ``MAX_TILE_PX`` (1024)
pixels, which bounds the density at 4 and so the canvas size. Any other tile is
refused with a :class:`BasemapError` naming it, exactly as an undecodable tile
is. Error text is deterministic: Pillow's memory addresses are stripped.
"""

from __future__ import annotations

import io
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from fitdocs.render.charts.map import Basemap, MapPlan, TileRef

if TYPE_CHECKING:
    from PIL import Image

TILE_FORMATS: Final[tuple[str, ...]] = ("PNG", "JPEG", "WEBP")
TILE_UNITS: Final[int] = 256  # output units one tile covers
MAX_TILE_PX: Final[int] = 1024  # largest accepted tile edge; density <= 4
BASEMAP_FORMAT: Final[str] = "WEBP"
BASEMAP_MIME: Final[str] = "image/webp"
BASEMAP_QUALITY: Final[int] = 75
BASEMAP_METHOD: Final[int] = 4

_ADDRESS: Final = re.compile(r" at 0x[0-9a-fA-F]+")


class BasemapError(Exception):
    """A tile could not be used: not PNG/JPEG/WebP, not decodable, not square,
    larger than ``MAX_TILE_PX``, or not composable.

    The message names the tile as ``z/x/y`` and the cause.
    """


class BasemapEncoderError(Exception):
    """The installed image library cannot encode ``BASEMAP_FORMAT``.

    An installation fault, not a tile fault; it does not derive from
    :class:`BasemapError`.
    """


def _name(ref: TileRef) -> str:
    return f"tile {ref.z}/{ref.x}/{ref.y}"


def _cause(exc: Exception) -> str:
    """``Class: message`` with memory addresses removed, so the text is stable."""
    return f"{type(exc).__name__}: {_ADDRESS.sub('', str(exc))}"


@dataclass(frozen=True)
class Canvas:
    """A composed RGB canvas, its pixel density and its placement in output units."""

    image: Image.Image  # RGB
    density: float  # pixels per output unit, >= 1
    x: float  # placement in output units, in (-1/density, 0]
    y: float


def _decode(ref: TileRef, data: bytes) -> Image.Image:
    from PIL import Image

    try:
        opened = Image.open(io.BytesIO(data), formats=TILE_FORMATS)
    except Exception as exc:  # noqa: BLE001 - every decode failure becomes a BasemapError
        raise BasemapError(f"{_name(ref)} cannot be decoded: {_cause(exc)}") from exc
    with opened:
        width, height = opened.size
        if width != height:
            raise BasemapError(f"{_name(ref)} is not square: {width}x{height}")
        if width > MAX_TILE_PX:
            raise BasemapError(f"{_name(ref)} edge {width} px exceeds {MAX_TILE_PX}")
        try:
            opened.load()
            return opened.convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            raise BasemapError(
                f"{_name(ref)} cannot be decoded: {_cause(exc)}"
            ) from exc


def compose_canvas(plan: MapPlan, tiles: Sequence[tuple[TileRef, bytes]]) -> Canvas:
    """Compose the resolved *tiles* into the canvas covering *plan*'s viewport.

    Raises :class:`BasemapError` naming the tile when one is not a decodable
    PNG, JPEG or WebP (a decompression-bomb refusal included), is not square,
    exceeds ``MAX_TILE_PX``, or cannot be resized or composited.
    """
    from PIL import Image

    decoded = [(ref, _decode(ref, data)) for ref, data in tiles]
    tile_px = max([TILE_UNITS, *(image.width for _, image in decoded)])
    density = tile_px / TILE_UNITS

    left = math.floor(plan.origin_x * density)
    top = math.floor(plan.origin_y * density)
    right = math.ceil((plan.origin_x + plan.width) * density)
    bottom = math.ceil((plan.origin_y + plan.height) * density)

    canvas = Image.new("RGBA", (right - left, bottom - top), (255, 255, 255, 255))
    for ref, image in decoded:
        slot = (ref.x * tile_px - left, ref.y * tile_px - top)
        try:
            if image.size != (tile_px, tile_px):
                image = image.resize((tile_px, tile_px), Image.Resampling.LANCZOS)
            canvas.alpha_composite(image, dest=slot)
        except Exception as exc:  # noqa: BLE001 - e.g. a bomb refusal while cropping
            raise BasemapError(
                f"{_name(ref)} cannot be composed: {_cause(exc)}"
            ) from exc

    return Canvas(
        image=canvas.convert("RGB"),
        density=density,
        x=(left - plan.origin_x * density) / density,
        y=(top - plan.origin_y * density) / density,
    )


def encoder_available() -> bool:
    """Whether the installed Pillow can encode ``BASEMAP_FORMAT`` (WebP)."""
    from PIL import features

    return bool(features.check(BASEMAP_FORMAT.lower()))


def require_encoder() -> None:
    """Raise :class:`BasemapEncoderError` unless a WebP encoder is available."""
    if not encoder_available():
        raise BasemapEncoderError(
            "the installed Pillow was built without WebP support, so maps "
            "cannot be written; install a Pillow wheel that includes libwebp"
        )


def encode_canvas(canvas: Canvas) -> Basemap:
    """Encode *canvas* as WebP and return it with its placement in output units.

    The pixels are copied into a fresh RGB image first, so neither metadata on
    the canvas image (ICC profile, EXIF, XMP) nor an alpha plane reaches the file.
    Raises :class:`BasemapEncoderError` when no WebP encoder is available.
    """
    require_encoder()
    from PIL import Image

    source = canvas.image.convert("RGB")
    fresh = Image.frombytes("RGB", source.size, source.tobytes())
    out = io.BytesIO()
    fresh.save(out, BASEMAP_FORMAT, quality=BASEMAP_QUALITY, method=BASEMAP_METHOD)
    return Basemap(
        mime=BASEMAP_MIME,
        data=out.getvalue(),
        x=canvas.x,
        y=canvas.y,
        width=fresh.width / canvas.density,
        height=fresh.height / canvas.density,
    )


def compose_basemap(plan: MapPlan, tiles: Sequence[tuple[TileRef, bytes]]) -> Basemap:
    """Compose the resolved *tiles* for *plan* and encode the result.

    Raises :class:`BasemapEncoderError` before looking at any tile when no WebP
    encoder is available, and :class:`BasemapError` naming the tile otherwise.
    """
    require_encoder()
    return encode_canvas(compose_canvas(plan, tiles))

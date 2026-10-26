"""Synthetic map-tile factory for tests (compact-chart-assets Req 10.1, 10.2).

Import it under an alias, because the bare name ``tiles`` clashes with
``fitdocs.tiles``: ``from tests.support import tiles as tile_factory``.

Everything here is generated in memory from a seed or a literal: no file is
read, and no real place, route or provider tile is represented. Output is
byte-deterministic -- fixed encoder parameters, no metadata, and a private
``random.Random(seed)`` per call.

PNG is written uncompressed (``compress_level=0``) for cross-platform byte
identity. Pillow 13.0.0 wheels link zlib-ng on macOS and stock zlib 1.3.1 on
Linux; in a 2026-10-26 comparison, compressed PNG differed in every case, while
uncompressed PNG, JPEG and lossless WebP were byte-identical on macOS,
linux/amd64 and linux/arm64. Keep tiles small
so uncompressed PNGs stay tiny when embedded in goldens.
"""

from __future__ import annotations

import io
import random
import zlib
from collections.abc import Callable
from typing import Final

from PIL import Image, ImageDraw

Size = tuple[int, int]
Colour = tuple[int, int, int]

FORMATS: Final = ("PNG", "JPEG", "WEBP")
DEFAULT_SIZE: Final[Size] = (8, 8)


def _encode(image: Image.Image, fmt: str) -> bytes:
    """Encode *image* with fixed parameters so identical pixels give identical bytes."""
    if fmt not in FORMATS:
        raise ValueError(f"unsupported tile format {fmt!r}; expected one of {FORMATS}")
    buffer = io.BytesIO()
    if fmt == "PNG":
        image.save(buffer, "PNG", optimize=False, compress_level=0)
    elif fmt == "JPEG":
        image.convert("RGB").save(
            buffer, "JPEG", quality=90, optimize=False, progressive=False, subsampling=0
        )
    else:
        image.save(buffer, "WEBP", lossless=True, quality=80, method=4)
    return buffer.getvalue()


def solid(size: Size, colour: Colour, fmt: str = "PNG") -> bytes:
    """A single-colour opaque tile of *size* in *fmt*."""
    return _encode(Image.new("RGB", size, colour), fmt)


def transparent(size: Size, fmt: str = "PNG") -> bytes:
    """A fully transparent tile (PNG or WEBP; JPEG has no alpha channel)."""
    if fmt == "JPEG":
        raise ValueError("JPEG cannot carry transparency")
    return _encode(Image.new("RGBA", size, (0, 0, 0, 0)), fmt)


def map_like(size: Size, seed: int, fmt: str = "PNG") -> bytes:
    """A procedurally drawn map-like tile: fills, road strokes, label blocks."""
    rng = random.Random(seed)
    width, height = size

    def colour() -> Colour:
        return (rng.randrange(256), rng.randrange(256), rng.randrange(256))

    def point() -> tuple[int, int]:
        return (rng.randrange(max(width, 1)), rng.randrange(max(height, 1)))

    image = Image.new("RGB", size, (235, 232, 224))
    draw = ImageDraw.Draw(image)
    for _ in range(rng.randrange(3, 7)):  # land-use fills
        a, b = point(), point()
        draw.rectangle(
            (min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])),
            fill=colour(),
        )
    for _ in range(rng.randrange(3, 7)):  # road strokes
        draw.line([point(), point(), point()], fill=colour(), width=rng.randrange(1, 6))
    for _ in range(rng.randrange(2, 6)):  # label-like glyph blocks
        x, y = point()
        for glyph in range(rng.randrange(3, 8)):
            gx = x + glyph * 5
            draw.rectangle((gx, y, gx + 3, y + 6), fill=(30, 30, 30))
    return _encode(image, fmt)


class FetchStub:
    """Drop-in for the ``Callable[[str], bytes]`` tile ``fetch`` seam.

    Returns a decodable map-like tile per URL (seeded from the URL, so distinct
    URLs give distinct tiles and the same URL always gives the same bytes) and
    records every URL requested in :attr:`urls`.
    """

    def __init__(self, size: Size = DEFAULT_SIZE, fmt: str = "PNG") -> None:
        self.size = size
        self.fmt = fmt
        self.urls: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.urls.append(url)
        return map_like(self.size, zlib.crc32(url.encode("utf-8")), self.fmt)


def fetch_stub(size: Size = DEFAULT_SIZE, fmt: str = "PNG") -> FetchStub:
    """A fresh :class:`FetchStub` returning decodable *size* tiles in *fmt*."""
    return FetchStub(size, fmt)


# --- undecodable kinds -------------------------------------------------------


def png_signature_only() -> bytes:
    """The 8-byte PNG signature followed by junk, with no image behind it."""
    return b"\x89PNG\r\n\x1a\n" + b"not an image" * 4


def tiff(size: Size = (8, 8)) -> bytes:
    """A real TIFF image (a format outside the PNG/JPEG/WEBP allow-list)."""
    buffer = io.BytesIO()
    Image.new("RGB", size, (10, 20, 30)).save(buffer, "TIFF")
    return buffer.getvalue()


def gif(size: Size = (8, 8)) -> bytes:
    """A real GIF image (a format outside the PNG/JPEG/WEBP allow-list)."""
    buffer = io.BytesIO()
    Image.new("P", size, 1).save(buffer, "GIF")
    return buffer.getvalue()


def eps_signature() -> bytes:
    """A blob carrying the EPS/PostScript signature."""
    return b"%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 8 8\nshowpage\n"


def random_bytes(seed: int = 0, length: int = 256) -> bytes:
    """Seeded random bytes, led by a NUL byte."""
    rng = random.Random(seed)
    return b"\x00" + bytes(rng.randrange(256) for _ in range(length - 1))


UNDECODABLE: Final[dict[str, Callable[[], bytes]]] = {
    "png_signature_only": png_signature_only,
    "tiff": tiff,
    "gif": gif,
    "eps_signature": eps_signature,
    "random_bytes": random_bytes,
}

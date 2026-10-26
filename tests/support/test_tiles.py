"""Tests for the synthetic tile factory (compact-chart-assets Req 10.1, 10.2)."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import zlib
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image, UnidentifiedImageError

from tests.support import tiles

_REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWED = ["PNG", "JPEG", "WEBP"]
DECODABLE = ["PNG", "JPEG", "WEBP"]


def _open(data: bytes, formats: list[str] | None = None) -> Image.Image:
    return Image.open(io.BytesIO(data), formats=formats)


@pytest.mark.parametrize("fmt", DECODABLE)
@pytest.mark.parametrize("size", [(256, 256), (64, 32), (7, 300)])
def test_solid_opens_as_declared_format_and_size(
    fmt: str, size: tuple[int, int]
) -> None:
    data = tiles.solid(size, (200, 30, 90), fmt)
    image = _open(data, ALLOWED)
    assert image.format == fmt
    assert image.size == size
    image.load()


def test_solid_colour_is_the_declared_colour_in_lossless_formats() -> None:
    for fmt in ("PNG", "WEBP"):
        image = _open(tiles.solid((8, 8), (200, 30, 90), fmt), ALLOWED).convert("RGB")
        assert image.getpixel((3, 3)) == (200, 30, 90)
    other = _open(tiles.solid((8, 8), (10, 220, 40), "PNG"), ALLOWED).convert("RGB")
    assert other.getpixel((3, 3)) == (10, 220, 40)


@pytest.mark.parametrize("fmt", ["PNG", "WEBP"])
def test_transparent_tile_has_zero_alpha(fmt: str) -> None:
    image = _open(tiles.transparent((16, 24), fmt), ALLOWED)
    assert image.format == fmt
    assert image.size == (16, 24)
    rgba = image.convert("RGBA")
    assert rgba.getchannel("A").getextrema() == (0, 0)


@pytest.mark.parametrize("fmt", DECODABLE)
def test_map_like_same_seed_identical_bytes(fmt: str) -> None:
    assert tiles.map_like((128, 128), 5, fmt) == tiles.map_like((128, 128), 5, fmt)


@pytest.mark.parametrize("fmt", DECODABLE)
def test_map_like_different_seed_different_bytes(fmt: str) -> None:
    assert tiles.map_like((128, 128), 5, fmt) != tiles.map_like((128, 128), 6, fmt)


@pytest.mark.parametrize("fmt", DECODABLE)
@pytest.mark.parametrize("size", [(256, 256), (96, 40)])
def test_map_like_opens_as_declared_format_and_size(
    fmt: str, size: tuple[int, int]
) -> None:
    image = _open(tiles.map_like(size, 3, fmt), ALLOWED)
    assert image.format == fmt
    assert image.size == size
    image.load()


def test_map_like_has_fills_roads_and_label_blocks() -> None:
    image = _open(tiles.map_like((256, 256), 3, "PNG"), ALLOWED).convert("RGB")
    counted = image.getcolors(maxcolors=1 << 20)
    assert counted is not None
    colours = {colour for _, colour in counted}
    assert (30, 30, 30) in colours  # label-like glyph blocks
    assert (235, 232, 224) in colours  # background still visible
    assert len(colours) >= 8  # fills and road strokes add many more colours
    assert len(colours) <= 40  # but it is a drawing, not noise


def test_map_like_repeated_calls_do_not_share_state() -> None:
    first = tiles.map_like((64, 64), 9, "PNG")
    tiles.map_like((64, 64), 10, "PNG")
    assert tiles.map_like((64, 64), 9, "PNG") == first


def test_unknown_format_is_rejected() -> None:
    with pytest.raises(ValueError):
        tiles.solid((8, 8), (0, 0, 0), "BMP")


@pytest.mark.parametrize("fmt", DECODABLE)
def test_fetch_stub_returns_decodable_tiles_and_records_urls(fmt: str) -> None:
    stub = tiles.fetch_stub(size=(32, 32), fmt=fmt)
    urls = ["https://tiles.invalid/1/2/3.png", "https://tiles.invalid/1/2/4.png"]
    bodies = [stub(url) for url in urls]
    assert stub.urls == urls
    for body in bodies:
        image = _open(body, ALLOWED)
        assert (image.format, image.size) == (fmt, (32, 32))
    assert bodies[0] != bodies[1]  # per-url distinct, and deterministic:
    assert tiles.fetch_stub(size=(32, 32), fmt=fmt)(urls[0]) == bodies[0]


def test_undecodable_registry_binds_each_kind_to_its_maker() -> None:
    expected = {
        "png_signature_only": tiles.png_signature_only,
        "tiff": tiles.tiff,
        "gif": tiles.gif,
        "eps_signature": tiles.eps_signature,
        "random_bytes": tiles.random_bytes,
    }
    assert expected == tiles.UNDECODABLE


@pytest.mark.parametrize("name", sorted(tiles.UNDECODABLE))
def test_undecodable_kinds_fail_to_open_or_load_as_allowed_formats(name: str) -> None:
    make: Callable[[], bytes] = tiles.UNDECODABLE[name]
    data = make()
    assert isinstance(data, bytes)
    with pytest.raises(UnidentifiedImageError):
        _open(data, ALLOWED).load()


def test_undecodable_kinds_are_what_they_claim_to_be() -> None:
    assert tiles.png_signature_only().startswith(b"\x89PNG\r\n\x1a\n")
    assert _open(tiles.tiff()).format == "TIFF"
    assert _open(tiles.gif()).format == "GIF"
    assert tiles.eps_signature().startswith(b"%!PS-Adobe")
    assert tiles.random_bytes() == tiles.random_bytes()
    assert tiles.random_bytes(seed=1) != tiles.random_bytes(seed=2)


def test_png_signature_only_is_not_a_real_png() -> None:
    with pytest.raises(UnidentifiedImageError):
        _open(tiles.png_signature_only(), ["PNG"]).load()


def test_transparent_jpeg_is_refused() -> None:
    with pytest.raises(ValueError):
        tiles.transparent((8, 8), "JPEG")


def test_fetch_stub_bytes_are_identical_across_hash_seeds() -> None:
    code = (
        "import hashlib; from tests.support import tiles; "
        "print(hashlib.sha256(tiles.fetch_stub((8, 8))("
        "'https://tiles.invalid/1/2/3.png')).hexdigest())"
    )
    digests = []
    for hash_seed in ("1", "2"):
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            check=True,
            cwd=_REPO_ROOT,
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
        )
        digests.append(result.stdout.strip())
    assert len(digests[0]) == 64
    assert digests[0] == digests[1]


def test_png_is_written_uncompressed() -> None:
    data = tiles.solid((16, 16), (200, 30, 90), "PNG")
    idat = b""
    pos = 8
    while pos < len(data):
        length = int.from_bytes(data[pos : pos + 4], "big")
        kind = data[pos + 4 : pos + 8]
        if kind == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 12 + length
    assert idat
    assert (idat[0] & 0x0F) == 8  # deflate
    assert (idat[1] >> 6) == 0  # FLEVEL 0: fastest / stored
    assert idat[2] & 0b110 == 0  # first block BTYPE 00: stored
    # Stored blocks carry the raw scanlines, so the stream outgrows them.
    assert len(zlib.decompress(idat)) == 16 * (1 + 16 * 3)
    assert len(idat) > 16 * (1 + 16 * 3)

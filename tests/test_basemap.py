"""Canvas composition and WebP encoding of the basemap (compact-chart-assets 3.1, 3.2).

Tiles come from the synthetic factory or are built in memory. Placement tests
use lossless PNG tiles and compare canvas pixels exactly; only the JPEG/WebP
decode test tolerates codec error. The encoding half pins the WebP bytes by
SHA-256, the encoder-availability check and its distinct error, a time ceiling
for 15 tiles, and an AST guard on where ``PIL`` is imported.
"""

from __future__ import annotations

import ast
import hashlib
import io
import math
import struct
import time
import zlib
from collections.abc import Iterable
from pathlib import Path

import pytest
from PIL import Image

from fitdocs import basemap
from fitdocs.render.charts.map import MapPlan, TileRef
from tests.support import tiles as tile_factory


def _plan(
    tiles: tuple[TileRef, ...],
    *,
    origin: tuple[float, float] = (0.0, 0.0),
    size: tuple[int, int] = (256, 256),
) -> MapPlan:
    return MapPlan(
        zoom=tiles[0].z,
        width=size[0],
        height=size[1],
        origin_x=origin[0],
        origin_y=origin[1],
        tiles=tiles,
        segments=(),
    )


# Pairwise-distinct, asymmetric colours: a 1 px shift or an x/y swap changes pixels.
_COLOURS = {
    (10, 20): (200, 10, 30),
    (11, 20): (20, 180, 40),
    (10, 21): (30, 40, 220),
    (11, 21): (210, 190, 50),
}
_TILES = tuple(TileRef(5, x, y) for (x, y) in _COLOURS)


def _blocks(tile_px: int) -> dict[tuple[int, int], bytes]:
    """Each tile is a left half of its colour and a right half of a darker one,
    so horizontal shifts are visible inside a tile, not only at its seams."""
    out = {}
    for key, colour in _COLOURS.items():
        img = Image.new("RGB", (tile_px, tile_px), colour)
        right = tuple(c // 2 for c in colour)
        for px in range(tile_px // 2, tile_px):
            for py in range(tile_px):
                img.putpixel((px, py), right)
        # a distinguishing top row so y shifts are visible too
        for px in range(tile_px):
            img.putpixel((px, 0), (255 - colour[0], 255 - colour[1], 255 - colour[2]))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        out[key] = buf.getvalue()
    return out


def _mosaic(tile_px: int) -> Image.Image:
    """Reference mosaic of the 2x2 tile block, origin at tile (10, 20)."""
    mosaic = Image.new("RGB", (2 * tile_px, 2 * tile_px), (255, 255, 255))
    for (x, y), data in _blocks(tile_px).items():
        mosaic.paste(
            Image.open(io.BytesIO(data)).convert("RGB"),
            ((x - 10) * tile_px, (y - 20) * tile_px),
        )
    return mosaic


def _compose(origin: tuple[float, float], size: tuple[int, int], tile_px: int = 256):
    blocks = _blocks(tile_px)
    tiles = [(TileRef(5, x, y), blocks[(x, y)]) for (x, y) in _COLOURS]
    plan = _plan(_TILES, origin=origin, size=size)
    return basemap.compose_canvas(plan, tiles)


# Tile (10, 20) world origin is (2560, 5120); origins below sit inside the block.
@pytest.mark.parametrize(
    ("dx", "dy"),
    [(0.0, 0.0), (0.25, 0.75), (100.5, 7.9), (255.0, 255.0), (0.999, 0.001)],
)
def test_canvas_matches_reference_mosaic_exactly(dx: float, dy: float) -> None:
    origin = (2560 + dx, 5120 + dy)
    canvas = _compose(origin, (250, 200))
    left, top = math.floor(origin[0]) - 2560, math.floor(origin[1]) - 5120
    right, bottom = math.ceil(origin[0] + 250) - 2560, math.ceil(origin[1] + 200) - 5120
    expected = _mosaic(256).crop((left, top, right, bottom))
    assert canvas.density == 1
    assert canvas.image.mode == "RGB"
    assert canvas.image.size == expected.size
    assert canvas.image.tobytes() == expected.tobytes()
    # non-trivial: the fixture really contains several distinct colours
    assert len(canvas.image.getcolors(maxcolors=100000)) >= 3


@pytest.mark.parametrize(
    ("dx", "dy"), [(0.0, 0.0), (0.25, 0.75), (100.5, 7.9), (0.999, 0.001)]
)
def test_placement_is_fraction_below_pixel_origin(dx: float, dy: float) -> None:
    origin = (2560 + dx, 5120 + dy)
    canvas = _compose(origin, (200, 150))
    assert canvas.x == math.floor(origin[0]) - origin[0]
    assert canvas.y == math.floor(origin[1]) - origin[1]
    assert -1 < canvas.x <= 0
    assert -1 < canvas.y <= 0


def test_zero_fraction_gives_zero_placement_and_exact_size() -> None:
    canvas = _compose((2560.0, 5120.0), (200, 150))
    assert (canvas.x, canvas.y) == (0.0, 0.0)
    assert canvas.image.size == (200, 150)


def test_overhang_is_under_one_pixel_per_edge() -> None:
    origin = (2560.4, 5120.7)
    canvas = _compose(origin, (200, 150))
    # leading overhang is -placement, trailing is canvas end minus viewport end
    assert 0 < -canvas.x < 1 and 0 < -canvas.y < 1
    trailing_x = canvas.x + canvas.image.width - 200
    trailing_y = canvas.y + canvas.image.height - 150
    assert 0 < trailing_x < 1
    assert 0 < trailing_y < 1
    assert canvas.image.size == (201, 151)


def test_negative_fraction_origin_floors_towards_minus_infinity() -> None:
    """A viewport starting left of/above world pixel 0 (tile x = 0, negative origin)."""
    tile = tile_factory.map_like((256, 256), seed=3)
    plan = _plan((TileRef(0, 0, 0),), origin=(-10.5, -3.25), size=(40, 30))
    canvas = basemap.compose_canvas(plan, [(TileRef(0, 0, 0), tile)])
    assert canvas.x == math.floor(-10.5) - (-10.5) == -0.5
    assert canvas.y == math.floor(-3.25) - (-3.25) == -0.75
    assert canvas.image.size == (
        math.ceil(-10.5 + 40) - math.floor(-10.5),
        math.ceil(-3.25 + 30) - math.floor(-3.25),
    )
    reference = Image.new("RGB", canvas.image.size, (255, 255, 255))
    reference.paste(Image.open(io.BytesIO(tile)).convert("RGB"), (11, 4))
    assert canvas.image.tobytes() == reference.tobytes()


def test_uncovered_pixels_stay_white() -> None:
    canvas = basemap.compose_canvas(
        _plan((TileRef(0, 0, 0),), origin=(-4.0, -4.0), size=(8, 8)),
        [(TileRef(0, 0, 0), tile_factory.solid((256, 256), (9, 9, 9)))],
    )
    assert canvas.image.getpixel((0, 0)) == (255, 255, 255)
    assert canvas.image.getpixel((7, 7)) == (9, 9, 9)


def _density_canvas(sizes: list[int]) -> basemap.Canvas:
    refs = tuple(TileRef(2, i, 0) for i in range(len(sizes)))
    tiles = [
        (r, tile_factory.solid((s, s), (50 + 40 * i, 20, 90)))
        for i, (r, s) in enumerate(zip(refs, sizes, strict=True))
    ]
    return basemap.compose_canvas(_plan(refs, size=(256, 256)), tiles)


@pytest.mark.parametrize(
    ("sizes", "density"),
    [
        ([256], 1.0),
        ([512], 2.0),
        ([4], 1.0),
        ([4, 256], 1.0),
        ([256, 512], 2.0),
        ([512, 256], 2.0),
        ([256, 512, 4], 2.0),
        ([4, 512], 2.0),
        ([768, 256], 3.0),
        ([384], 1.5),
        ([256, 384], 1.5),
        ([1024], 4.0),
    ],
)
def test_density_is_highest_tile_density_never_below_one(
    sizes: list[int], density: float
) -> None:
    canvas = _density_canvas(sizes)
    assert canvas.density == density
    assert canvas.image.size == (int(256 * density),) * 2


def test_higher_density_canvas_places_in_pixels_of_that_density() -> None:
    tile = tile_factory.map_like((512, 512), seed=7)
    ref = TileRef(3, 5, 6)
    # viewport origin 1.3 units into the tile, density 2: pixel origin 2.6
    plan = _plan((ref,), origin=(5 * 256 + 1.3, 6 * 256 + 0.2), size=(100, 50))
    canvas = basemap.compose_canvas(plan, [(ref, tile)])
    assert canvas.density == 2
    assert canvas.x == pytest.approx((2 - 2.6) / 2)
    assert canvas.y == pytest.approx((0 - 0.4) / 2)
    assert canvas.image.size == (
        math.ceil((1.3 + 100) * 2) - 2,
        math.ceil((0.2 + 50) * 2) - 0,
    )
    reference = (
        Image.open(io.BytesIO(tile))
        .convert("RGB")
        .crop((2, 0, 2 + canvas.image.width, canvas.image.height))
    )
    assert canvas.image.tobytes() == reference.tobytes()


def test_other_sized_tiles_are_lanczos_resized_to_their_slot() -> None:
    big = tile_factory.solid((512, 512), (10, 200, 30))
    gradient = Image.new("RGB", (4, 4))
    for px in range(4):
        for py in range(4):
            gradient.putpixel((px, py), (60 * px, 60 * py, 17 * (px + py)))
    buf = io.BytesIO()
    gradient.save(buf, "PNG")
    refs = (TileRef(2, 0, 0), TileRef(2, 1, 0))
    canvas = basemap.compose_canvas(
        _plan(refs, size=(512, 256)), [(refs[0], big), (refs[1], buf.getvalue())]
    )
    assert canvas.density == 2
    slot = canvas.image.crop((512, 0, 1024, 512))
    lanczos = gradient.resize((512, 512), Image.Resampling.LANCZOS)
    nearest = gradient.resize((512, 512), Image.Resampling.NEAREST)
    assert lanczos.tobytes() != nearest.tobytes()
    assert slot.tobytes() == lanczos.tobytes()


def test_transparent_pixels_composite_onto_white() -> None:
    rgba = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    rgba.putpixel((0, 0), (200, 0, 0, 128))  # half-transparent red
    rgba.putpixel((1, 0), (0, 0, 255, 255))  # opaque blue
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    ref = TileRef(0, 0, 0)
    canvas = basemap.compose_canvas(_plan((ref,)), [(ref, buf.getvalue())])
    expected = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
    expected.alpha_composite(rgba)
    half = canvas.image.getpixel((0, 0))
    assert half == expected.convert("RGB").getpixel((0, 0))
    assert half not in {(200, 0, 0), (100, 0, 0), (255, 255, 255), (0, 0, 0)}
    assert canvas.image.getpixel((1, 0)) == (0, 0, 255)
    assert canvas.image.getpixel((9, 9)) == (255, 255, 255)  # fully transparent


def test_jpeg_and_webp_tiles_decode() -> None:
    refs = (TileRef(1, 0, 0), TileRef(1, 1, 0))
    jpeg = tile_factory.solid((256, 256), (120, 30, 200), "JPEG")
    webp = tile_factory.solid((256, 256), (10, 90, 160), "WEBP")
    canvas = basemap.compose_canvas(
        _plan(refs, size=(512, 256)), [(refs[0], jpeg), (refs[1], webp)]
    )
    r, g, b = canvas.image.getpixel((100, 100))
    assert abs(r - 120) < 6 and abs(g - 30) < 6 and abs(b - 200) < 6
    assert canvas.image.getpixel((300, 100)) == (10, 90, 160)


@pytest.mark.parametrize("kind", sorted(tile_factory.UNDECODABLE))
def test_undecodable_tile_raises_basemap_error_naming_the_tile(kind: str) -> None:
    good = tile_factory.solid((256, 256), (1, 2, 3))
    refs = (TileRef(7, 41, 99), TileRef(7, 42, 99))
    with pytest.raises(basemap.BasemapError) as info:
        basemap.compose_canvas(
            _plan(refs, size=(512, 256)),
            [(refs[0], good), (refs[1], tile_factory.UNDECODABLE[kind]())],
        )
    assert "7/42/99" in str(info.value)
    assert "7/41/99" not in str(info.value)


def test_truncated_png_raises_basemap_error() -> None:
    data = tile_factory.map_like((256, 256), seed=1)
    ref = TileRef(3, 1, 2)
    with pytest.raises(basemap.BasemapError, match=r"3/1/2"):
        basemap.compose_canvas(_plan((ref,)), [(ref, data[: len(data) // 2])])


def _png_declaring(width: int, height: int) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + tag
            + body
            + struct.pack(">I", zlib.crc32(tag + body))
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00" * 10)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


def test_decompression_bomb_raises_basemap_error_naming_the_tile() -> None:
    bomb = _png_declaring(60000, 60000)  # 3.6e9 px, tiny on disk
    assert len(bomb) < 200
    ref = TileRef(9, 3, 4)
    with pytest.raises(basemap.BasemapError, match=r"9/3/4") as info:
        basemap.compose_canvas(_plan((ref,)), [(ref, bomb)])
    assert "DecompressionBombError" in str(info.value)


def test_error_names_cause_class() -> None:
    ref = TileRef(4, 5, 6)
    with pytest.raises(basemap.BasemapError) as info:
        basemap.compose_canvas(_plan((ref,)), [(ref, tile_factory.tiff())])
    assert "UnidentifiedImageError" in str(info.value)
    assert "4/5/6" in str(info.value)


# --- density 2 where the fraction times the density is >= 1 ------------------
# At density 2 the pixel origin is 2 * origin, so floor(2 * o) differs from
# 2 * floor(o) whenever frac(o) >= 0.5.


@pytest.mark.parametrize(
    ("dx", "dy"), [(1.7, 0.6), (100.8, 7.8), (255.9, 0.9), (0.75, 99.55)]
)
def test_density_two_placement_and_pixels_use_pixel_granularity(
    dx: float, dy: float
) -> None:
    origin = (2560 + dx, 5120 + dy)
    canvas = _compose(origin, (250, 200), tile_px=512)
    left, top = math.floor(dx * 2), math.floor(dy * 2)
    assert left != 2 * math.floor(dx) and top != 2 * math.floor(
        dy
    )  # fixture precondition
    assert canvas.density == 2
    assert canvas.x == pytest.approx((left - dx * 2) / 2)
    assert canvas.y == pytest.approx((top - dy * 2) / 2)
    assert -0.5 < canvas.x <= 0
    assert -0.5 < canvas.y <= 0
    trailing_x = canvas.x + canvas.image.width / 2 - 250
    trailing_y = canvas.y + canvas.image.height / 2 - 200
    assert 0 <= trailing_x < 0.5
    assert 0 <= trailing_y < 0.5
    right, bottom = math.ceil((dx + 250) * 2), math.ceil((dy + 200) * 2)
    expected = _mosaic(512).crop((left, top, right, bottom))
    assert canvas.image.size == expected.size
    assert canvas.image.tobytes() == expected.tobytes()


def test_density_two_negative_origin() -> None:
    tile = tile_factory.map_like((512, 512), seed=11)
    ref = TileRef(0, 0, 0)
    plan = _plan((ref,), origin=(-10.2, -3.3), size=(40, 30))
    canvas = basemap.compose_canvas(plan, [(ref, tile)])
    # pixel origin (-20.4, -6.6): floors to (-21, -7); unit floors would give (-22, -8)
    assert canvas.density == 2
    assert canvas.x == pytest.approx(-0.3)
    assert canvas.y == pytest.approx(-0.2)
    assert canvas.image.size == (math.ceil(29.8 * 2) + 21, math.ceil(26.7 * 2) + 7)
    reference = Image.new("RGB", canvas.image.size, (255, 255, 255))
    reference.paste(Image.open(io.BytesIO(tile)).convert("RGB"), (21, 7))
    assert canvas.image.tobytes() == reference.tobytes()


@pytest.mark.parametrize("other", [None, 256])
def test_fractional_density_places_pixels_exactly(other: int | None) -> None:
    """Density 1.5: a 384 px tile, alone or beside a 256 px tile resized to 384."""
    tile = tile_factory.map_like((384, 384), seed=5)
    ref = TileRef(3, 5, 6)
    refs = (ref,) if other is None else (ref, TileRef(3, 6, 6))
    tiles = [(ref, tile)]
    if other is not None:
        tiles.append((refs[1], tile_factory.map_like((other, other), seed=6)))
    plan = _plan(refs, origin=(5 * 256 + 1.3, 6 * 256 + 0.4), size=(100, 50))
    canvas = basemap.compose_canvas(plan, tiles)
    left, top = math.floor((5 * 256 + 1.3) * 1.5), math.floor((6 * 256 + 0.4) * 1.5)
    assert canvas.density == 1.5
    assert canvas.x == pytest.approx((left - (5 * 256 + 1.3) * 1.5) / 1.5)
    assert canvas.y == pytest.approx((top - (6 * 256 + 0.4) * 1.5) / 1.5)
    assert canvas.image.size == (
        math.ceil((5 * 256 + 101.3) * 1.5) - left,
        math.ceil((6 * 256 + 50.4) * 1.5) - top,
    )
    ox, oy = left - 5 * 384, top - 6 * 384
    reference = (
        Image.open(io.BytesIO(tile))
        .convert("RGB")
        .crop((ox, oy, ox + canvas.image.width, oy + canvas.image.height))
    )
    assert canvas.image.tobytes() == reference.tobytes()


# --- tile size limits --------------------------------------------------------


def _png(size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, (7, 8, 9)).save(buf, "PNG")  # compressed: stays tiny
    return buf.getvalue()


def test_largest_allowed_tile_is_accepted() -> None:
    assert basemap.MAX_TILE_PX == 1024
    ref = TileRef(1, 0, 0)
    canvas = basemap.compose_canvas(_plan((ref,)), [(ref, _png((1024, 1024)))])
    assert canvas.density == 4
    assert canvas.image.size == (1024, 1024)


@pytest.mark.parametrize("edge", [1025, 2048])
def test_oversized_tile_is_refused_naming_it(edge: int) -> None:
    ok, big = TileRef(6, 1, 1), TileRef(6, 2, 3)
    with pytest.raises(basemap.BasemapError) as info:
        basemap.compose_canvas(
            _plan((ok, big), size=(512, 256)),
            [(ok, _png((256, 256))), (big, _png((edge, edge)))],
        )
    message = str(info.value)
    assert "6/2/3" in message and "6/1/1" not in message
    assert f"edge {edge} px exceeds 1024" in message


@pytest.mark.parametrize("shape", [(290, 1), (256, 128), (128, 256), (4096, 4)])
def test_non_square_tile_is_refused_naming_it(shape: tuple[int, int]) -> None:
    ref = TileRef(8, 12, 13)
    with pytest.raises(basemap.BasemapError) as info:
        basemap.compose_canvas(_plan((ref,)), [(ref, _png(shape))])
    assert "8/12/13" in str(info.value)
    assert f"not square: {shape[0]}x{shape[1]}" in str(info.value)


@pytest.mark.parametrize(
    ("width", "height", "reason"),
    [(2048, 2048, "edge 2048 px exceeds 1024"), (300, 1, "not square: 300x1")],
)
def test_size_is_refused_from_the_header_before_decoding(
    width: int, height: int, reason: str
) -> None:
    # The header declares the size but the pixel data is truncated, so a check
    # made after load() would report "cannot be decoded" instead.
    ref = TileRef(8, 12, 13)
    with pytest.raises(basemap.BasemapError) as info:
        basemap.compose_canvas(_plan((ref,)), [(ref, _png_declaring(width, height))])
    assert reason in str(info.value)
    assert "cannot be decoded" not in str(info.value)


def test_bomb_in_composite_stage_is_a_basemap_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A square 4x4 tile opens under a limit of 8 px (only the warning band, 16 px),
    then the resize to 256x256 makes ``alpha_composite`` refuse in ``crop``.
    Pillow skips that check when the tile exactly covers the canvas, hence the
    5 unit offset."""
    import warnings

    ref = TileRef(2, 3, 1)
    data = tile_factory.solid((4, 4), (1, 2, 3))
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 8)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with pytest.raises(basemap.BasemapError) as info:
            basemap.compose_canvas(
                _plan((ref,), origin=(3 * 256.0 + 5, 256.0)), [(ref, data)]
            )
    assert "2/3/1" in str(info.value)
    assert "cannot be composed" in str(info.value)
    assert "DecompressionBombError" in str(info.value)


# --- deterministic error text ------------------------------------------------


@pytest.mark.parametrize("kind", sorted(tile_factory.UNDECODABLE))
def test_error_text_has_no_memory_address(kind: str) -> None:
    ref = TileRef(7, 1, 2)

    def message() -> str:
        with pytest.raises(basemap.BasemapError) as info:
            basemap.compose_canvas(
                _plan((ref,)), [(ref, tile_factory.UNDECODABLE[kind]())]
            )
        return str(info.value)

    first = message()
    assert "0x" not in first
    assert first.startswith("tile 7/1/2 cannot be decoded: ")
    assert message() == first


def test_address_free_text_is_exercised_by_a_kind_that_embeds_one() -> None:
    """At least one factory kind makes Pillow mention an address."""
    from PIL import Image as PILImage
    from PIL import UnidentifiedImageError

    raw = []
    for make in tile_factory.UNDECODABLE.values():
        try:
            PILImage.open(io.BytesIO(make()), formats=basemap.TILE_FORMATS)
        except UnidentifiedImageError as exc:
            raw.append(str(exc))
        except Exception:  # noqa: BLE001, S112
            continue
    assert any("0x" in text for text in raw)


# --- encoding (compact-chart-assets 3.4, 3.7, 4.4, 5.1, 5.2, 5.4) -------------


def _golden_canvas() -> basemap.Canvas:
    """A fixed 160x96 canvas built from integer arithmetic only, so no codec or
    resampler sits between this code and the pinned bytes."""
    rgb = bytearray()
    for y in range(96):
        for x in range(160):
            rgb += bytes(
                (
                    (x * 7 + y * 3) % 256,
                    (x * y) % 256,
                    255 if (x // 8 + y // 8) % 2 else (x * 5 + y * 11) % 256,
                )
            )
    image = Image.frombytes("RGB", (160, 96), bytes(rgb))
    return basemap.Canvas(image=image, density=2.0, x=-0.25, y=-0.5)


# SHA-256 of encode_canvas(_golden_canvas()) with Pillow 13.0.0 (the uv.lock pin,
# libwebp 1.6.0). The same digest was observed on macOS arm64 and, after
# `uv sync --frozen`, in linux/arm64 and linux/amd64 containers (amd64 emulated
# under Rosetta) on Python 3.11 to 3.13. Real x86-64 hardware is covered only
# once branch CI has run this test.
_GOLDEN_SHA256 = "fa6c615d6652d83f48dcb1b3f3d7edca40449d7bb6c4966589f38c6b61f0bafb"


def _webp_chunks(data: bytes) -> list[bytes]:
    """FourCCs of the top-level RIFF chunks."""
    assert data[:4] == b"RIFF"
    assert data[8:12] == b"WEBP"
    out, pos = [], 12
    while pos < len(data):
        out.append(data[pos : pos + 4])
        size = struct.unpack("<I", data[pos + 4 : pos + 8])[0]
        pos += 8 + size + (size & 1)
    return out


def test_encode_returns_basemap_with_placement() -> None:
    result = basemap.encode_canvas(_golden_canvas())
    assert result.mime == "image/webp"
    assert (result.x, result.y) == (-0.25, -0.5)
    assert (result.width, result.height) == (80.0, 48.0)
    assert _webp_chunks(result.data) == [b"VP8 "]
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert decoded.format == "WEBP"
        assert decoded.size == (160, 96)


def test_encode_is_identical_twice_and_matches_the_pinned_golden() -> None:
    first = basemap.encode_canvas(_golden_canvas())
    second = basemap.encode_canvas(_golden_canvas())
    assert first.data == second.data
    assert len(first.data) > 100
    assert hashlib.sha256(first.data).hexdigest() == _GOLDEN_SHA256


@pytest.mark.parametrize(
    "other",
    [{"quality": 76, "method": 4}, {"quality": 74, "method": 4}]
    + [{"quality": 75, "method": m} for m in (0, 1, 2, 3, 5, 6)],
)
def test_golden_fixture_distinguishes_other_quality_and_method(
    other: dict[str, int],
) -> None:
    """The pin is only worth something if the fixture's bytes move with each
    setting; a neighbouring setting must give different bytes."""
    buf = io.BytesIO()
    _golden_canvas().image.save(buf, "WEBP", **other)
    assert hashlib.sha256(buf.getvalue()).hexdigest() != _GOLDEN_SHA256


def test_encode_ignores_metadata_riding_on_the_canvas_image() -> None:
    plain = basemap.encode_canvas(_golden_canvas()).data
    carrying = _golden_canvas().image
    carrying.info["icc_profile"] = b"\x00" * 64
    carrying.info["exif"] = b"Exif\x00\x00MM\x00*\x00\x00\x00\x08\x00\x00"
    carrying.info["xmp"] = b"<x:xmpmeta/>"
    # Precondition: handed to Pillow's saver, this metadata does reach the file.
    forwarded = io.BytesIO()
    carrying.save(
        forwarded,
        "WEBP",
        quality=75,
        method=4,
        icc_profile=carrying.info["icc_profile"],
        exif=carrying.info["exif"],
        xmp=carrying.info["xmp"],
    )
    assert {b"ICCP", b"EXIF", b"XMP "} <= set(_webp_chunks(forwarded.getvalue()))
    assert forwarded.getvalue() != plain
    # Precondition: Pillow's saver also takes metadata from the image's own
    # encoderinfo, so saving this image directly (without a fresh copy) leaks it.
    carrying.encoderinfo = {
        "icc_profile": carrying.info["icc_profile"],
        "exif": carrying.info["exif"],
        "xmp": carrying.info["xmp"],
        "quality": 100,
    }
    direct = io.BytesIO()
    carrying.save(direct, "WEBP", quality=75, method=4)
    assert {b"ICCP", b"EXIF", b"XMP "} <= set(_webp_chunks(direct.getvalue()))
    result = basemap.encode_canvas(
        basemap.Canvas(image=carrying, density=2.0, x=-0.25, y=-0.5)
    )
    assert result.data == plain
    assert _webp_chunks(result.data) == [b"VP8 "]


def test_encode_drops_alpha_rather_than_encoding_an_rgba_canvas() -> None:
    rgba = _golden_canvas().image.convert("RGBA")
    for x in range(0, 160, 3):
        rgba.putpixel((x, 5), (10, 20, 30, 60))
    # Precondition: encoding the RGBA directly stores an alpha plane.
    direct = io.BytesIO()
    rgba.save(direct, "WEBP", quality=75, method=4)
    assert b"ALPH" in direct.getvalue()
    result = basemap.encode_canvas(
        basemap.Canvas(image=rgba, density=2.0, x=-0.25, y=-0.5)
    )
    assert _webp_chunks(result.data) == [b"VP8 "]
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert decoded.mode == "RGB"
    opaque = basemap.Canvas(image=rgba.convert("RGB"), density=2.0, x=-0.25, y=-0.5)
    assert result.data == basemap.encode_canvas(opaque).data
    assert result.data != basemap.encode_canvas(_golden_canvas()).data


def test_compose_basemap_encodes_the_composed_canvas_without_alpha() -> None:
    rgba = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    rgba.putpixel((3, 3), (200, 0, 0, 128))
    buf = io.BytesIO()
    rgba.save(buf, "PNG")
    ref = TileRef(0, 0, 0)
    plan = _plan((ref,), origin=(0.25, 0.75), size=(200, 100))
    result = basemap.compose_basemap(plan, [(ref, buf.getvalue())])
    canvas = basemap.compose_canvas(plan, [(ref, buf.getvalue())])
    assert result == basemap.encode_canvas(canvas)
    assert (result.x, result.y) == (canvas.x, canvas.y)
    assert (result.x, result.y) != (0.0, 0.0)
    assert (result.width, result.height) == (201.0, 101.0)
    assert _webp_chunks(result.data) == [b"VP8 "]


def test_compose_basemap_density_two_reports_width_in_output_units() -> None:
    ref = TileRef(0, 0, 0)
    plan = _plan((ref,), origin=(0.25, 0.0), size=(100, 50))
    result = basemap.compose_basemap(
        plan, [(ref, tile_factory.solid((512, 512), (9, 9, 9)))]
    )
    assert (result.width, result.height) == (100.5, 50.0)
    assert (result.x, result.y) == (-0.25, 0.0)
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert decoded.size == (201, 100)


def test_composing_fifteen_512px_map_tiles_stays_under_the_ceiling() -> None:
    refs = tuple(TileRef(4, 4 + x, 5 + y) for y in range(3) for x in range(5))
    tiles = [
        (ref, tile_factory.map_like((512, 512), seed=i, fmt="PNG"))
        for i, ref in enumerate(refs)
    ]
    plan = _plan(refs, origin=(4 * 256 + 17.25, 5 * 256 + 9.25), size=(1100, 700))
    started = time.perf_counter()
    result = basemap.compose_basemap(plan, tiles)
    elapsed = time.perf_counter() - started
    with Image.open(io.BytesIO(result.data)) as decoded:
        assert decoded.size == (2201, 1401)
    assert elapsed < _COMPOSE_CEILING_S


_COMPOSE_CEILING_S = 10.0


# --- encoder availability ----------------------------------------------------


class _Check:
    """Stands in for ``PIL.features.check`` and records what it was asked."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.asked: list[str] = []

    def __call__(self, feature: str) -> bool:
        self.asked.append(feature)
        return self.answer


def test_encoder_is_available_in_this_environment() -> None:
    assert basemap.encoder_available() is True
    assert basemap.require_encoder() is None


def test_missing_webp_raises_the_encoder_error(monkeypatch: pytest.MonkeyPatch) -> None:
    check = _Check(False)
    monkeypatch.setattr("PIL.features.check", check)
    assert basemap.encoder_available() is False
    with pytest.raises(basemap.BasemapEncoderError, match="WebP") as raised:
        basemap.require_encoder()
    assert "install a Pillow wheel that includes libwebp" in str(raised.value)
    assert set(check.asked) == {"webp"}


def test_encode_canvas_requires_the_encoder_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("PIL.features.check", _Check(False))
    with pytest.raises(basemap.BasemapEncoderError):
        basemap.encode_canvas(_golden_canvas())


def test_compose_basemap_reports_a_missing_encoder_before_a_bad_tile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installation fault must not be masked as a per-tile warning."""
    monkeypatch.setattr("PIL.features.check", _Check(False))
    ref = TileRef(0, 0, 0)
    with pytest.raises(basemap.BasemapEncoderError):
        try:
            basemap.compose_basemap(_plan((ref,)), [(ref, b"not an image")])
        except basemap.BasemapError:
            pytest.fail("a missing encoder surfaced as a BasemapError")


def test_encoder_error_is_not_a_basemap_error() -> None:
    assert not issubclass(basemap.BasemapEncoderError, basemap.BasemapError)
    assert not issubclass(basemap.BasemapError, basemap.BasemapEncoderError)
    assert basemap.BasemapEncoderError.__mro__[1] is Exception
    caught: list[BaseException] = []
    try:
        try:
            raise basemap.BasemapEncoderError("x")
        except basemap.BasemapError as exc:  # must not catch it
            caught.append(exc)
    except basemap.BasemapEncoderError:
        pass
    assert caught == []


# --- the Pillow import is confined to this module -----------------------------

_SRC = Path(__file__).parents[1] / "src" / "fitdocs"
_BASEMAP = _SRC / "basemap.py"


def _is_type_checking(test: ast.expr) -> bool:
    return (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
        isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
    )


def _is_pil(name: str | None) -> bool:
    return name is not None and (name == "PIL" or name.startswith("PIL."))


def _reaches_pil(node: ast.AST) -> bool:
    """An import statement or a literal-name dynamic import that names PIL."""
    if isinstance(node, ast.Import):
        return any(_is_pil(alias.name) for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        return _is_pil(node.module)
    return (
        isinstance(node, ast.Call)
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
        and _is_pil(node.args[0].value)
        and (
            getattr(node.func, "id", None) in {"__import__", "import_module"}
            or getattr(node.func, "attr", None) == "import_module"
        )
    )


def _pil_sites(source: str) -> list[tuple[int, str]]:
    """Every way the file reaches PIL, as (line, where) with where one of
    ``module``, ``class``, ``function``, ``type_checking``, ``type_checking_else``."""
    sites: list[tuple[int, str]] = []

    def walk_all(nodes: Iterable[ast.AST | None], where: str) -> None:
        for node in nodes:
            if node is not None:
                walk(node, where)

    def walk(node: ast.AST, where: str) -> None:
        if _reaches_pil(node):
            sites.append((node.lineno, where))  # type: ignore[attr-defined]
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            walk(node.test, where)
            walk_all(node.body, "type_checking" if where == "module" else where)
            walk_all(node.orelse, "type_checking_else")
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            # Decorators and default values run when the def statement runs, in
            # the enclosing scope; the body runs later (annotations are not
            # walked).
            walk_all(getattr(node, "decorator_list", []), where)
            walk_all([*node.args.defaults, *node.args.kw_defaults], where)
            body = node.body if isinstance(node.body, list) else [node.body]
            walk_all(body, "function")
        elif isinstance(node, ast.ClassDef):
            walk_all([*node.decorator_list, *node.bases, *node.keywords], where)
            walk_all(node.body, "class" if where == "module" else where)
        else:
            walk_all(ast.iter_child_nodes(node), where)

    walk(ast.parse(source), "module")
    return sites


def _violations(source: str, *, is_basemap: bool) -> list[tuple[int, str]]:
    sites = _pil_sites(source)
    if not is_basemap:
        return sites
    return [(n, w) for n, w in sites if w not in {"function", "type_checking"}]


def test_pil_is_imported_only_inside_basemap_functions_or_type_checking() -> None:
    files = sorted(_SRC.rglob("*.py"))
    assert len(files) > 100, "the walk is looking at the wrong directory"
    assert _BASEMAP in files
    elsewhere = {
        path.relative_to(_SRC).as_posix(): _violations(
            path.read_text(encoding="utf-8"), is_basemap=False
        )
        for path in files
        if path != _BASEMAP
    }
    assert {name: sites for name, sites in elsewhere.items() if sites} == {}
    own = _pil_sites(_BASEMAP.read_text(encoding="utf-8"))
    assert {where for _, where in own} == {"function", "type_checking"}
    assert sum(1 for _, where in own if where == "function") >= 3
    assert _violations(_BASEMAP.read_text(encoding="utf-8"), is_basemap=True) == []


@pytest.mark.parametrize(
    ("source", "is_basemap", "expected"),
    [
        ("import PIL\n", True, [(1, "module")]),
        ("from PIL import Image\n", True, [(1, "module")]),
        ("import PIL.Image as I\n", True, [(1, "module")]),
        ("class C:\n    from PIL import Image\n", True, [(2, "class")]),
        ("if not TYPE_CHECKING:\n    from PIL import Image\n", True, [(2, "module")]),
        (
            "if TYPE_CHECKING:\n    pass\nelse:\n    from PIL import Image\n",
            True,
            [(4, "type_checking_else")],
        ),
        ("def f():\n    __import__('PIL.Image')\n", False, [(2, "function")]),
        (
            "import importlib\ndef f():\n    importlib.import_module('PIL')\n",
            False,
            [(3, "function")],
        ),
        ("def f():\n    from PIL import Image\n", False, [(2, "function")]),
        ("def _probe(_m=__import__('PIL.Image')):\n    pass\n", False, [(1, "module")]),
        ("def _probe(*, _m=__import__('PIL')):\n    pass\n", False, [(1, "module")]),
        (
            "@(lambda f, _m=__import__('PIL'): f)\ndef g():\n    pass\n",
            False,
            [(1, "module")],
        ),
        ("@__import__('PIL').x\ndef g():\n    pass\n", False, [(1, "module")]),
        (
            "def outer():\n    def inner(_m=__import__('PIL')):\n        pass\n",
            False,
            [(2, "function")],
        ),
        (
            "if TYPE_CHECKING:\n    from PIL import Image\n",
            False,
            [(2, "type_checking")],
        ),
        ("import pilot\nfrom os import path\n", False, []),
    ],
)
def test_the_import_guard_flags_planted_violations(
    source: str, is_basemap: bool, expected: list[tuple[int, str]]
) -> None:
    assert _violations(source, is_basemap=is_basemap) == expected


@pytest.mark.parametrize(
    "source",
    [
        "def f():\n    from PIL import Image\n",
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n    from PIL import Image\n",
        "import typing\nif typing.TYPE_CHECKING:\n    from PIL import Image\n",
        "def f():\n    def g():\n        import PIL\n",
    ],
)
def test_the_import_guard_accepts_the_allowed_forms_in_basemap(source: str) -> None:
    assert _pil_sites(source) != []
    assert _violations(source, is_basemap=True) == []


# --- no clock or network imports and no I/O builtins (an import allow list plus
# banned builtins); file access through io.open/io.FileIO or a PIL path is not
# pinned.

_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "io",
        "math",
        "re",
        "collections.abc",
        "dataclasses",
        "typing",
        "fitdocs.render.charts.map",
    }
)


def _imported_modules(source: str) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            dots = "." * node.level
            if node.module:
                found.add(dots + node.module)
            else:
                found.update(dots + alias.name for alias in node.names)
    return found


_BANNED_BUILTINS = frozenset({"open", "__import__", "exec", "eval", "compile"})


def _banned_calls(source: str) -> set[str]:
    return {
        f"{node.func.id}()"
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _BANNED_BUILTINS
    }


def _disallowed_imports(source: str) -> set[str]:
    return {
        name
        for name in _imported_modules(source)
        if name not in _ALLOWED_IMPORTS and not _is_pil(name)
    } | _banned_calls(source)


def test_basemap_imports_only_the_allow_list() -> None:
    source = _BASEMAP.read_text(encoding="utf-8")
    imported = _imported_modules(source)
    assert {"io", "re", "PIL", "fitdocs.render.charts.map"} <= imported
    assert _disallowed_imports(source) == set()


@pytest.mark.parametrize(
    "planted", ["time", "datetime", "os", "pathlib", "socket", "urllib.request"]
)
def test_the_allow_list_flags_planted_clock_file_and_network_imports(
    planted: str,
) -> None:
    base = _BASEMAP.read_text(encoding="utf-8")
    assert _disallowed_imports(base + f"\ndef f():\n    import {planted}\n") == {
        planted
    }
    assert _disallowed_imports(base + f"\nfrom {planted} import x\n") == {planted}


@pytest.mark.parametrize(
    ("planted", "flagged"),
    [
        ("from . import tiles", ".tiles"),
        ("from .tiles import TileStore", ".tiles"),
        ("from .. import cli", "..cli"),
        ("def f():\n    return open(__file__, 'rb').read(1)", "open()"),
        ("def f():\n    return __import__('time')", "__import__()"),
        ("def f():\n    return eval('1')", "eval()"),
    ],
)
def test_the_allow_list_flags_relative_imports_and_io_builtins(
    planted: str, flagged: str
) -> None:
    base = _BASEMAP.read_text(encoding="utf-8")
    assert _disallowed_imports(base + "\n" + planted + "\n") == {flagged}

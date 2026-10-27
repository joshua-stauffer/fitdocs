"""Canvas composition for the viewport-cropped basemap (compact-chart-assets 3.1).

Tiles come from the synthetic factory or are built in memory. Placement tests
use lossless PNG tiles and compare canvas pixels exactly; only the JPEG/WebP
decode test tolerates codec error.
"""

from __future__ import annotations

import io
import math
import struct
import zlib

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

"""Draw Mona Kart's sprite sheets from pixel maps.

Writes assets/karts.png (one column per steering frame: left, straight,
right; one row per racer colour) and assets/props.png (roadside objects and
items in one row). Every sprite is a paletted PNG with transparency so the
badge's image.load keeps the background clear.

    python3 tools/build_sprites.py
"""
import struct
import sys
import zlib
from pathlib import Path

# a kart seen from behind with Mona at the wheel: ears, head, seat, body,
# bumper and four wheels. Letters pick colours; '.' is clear.
KART = (
    "........M.....M.........",
    ".......MM.....MM........",
    ".......MMMMMMMMM........",
    "......MMMMMMMMMMM.......",
    "......MMmMMMMMmMM.......",
    "......MMMMMMMMMMM.......",
    ".......MMMMMMMMM........",
    "........mMMMMMm.........",
    ".......KKKKKKKKK........",
    "......KKKKKKKKKKK.......",
    ".....KKKKkkkkkKKKK......",
    "....KKKKKKKKKKKKKKK.....",
    "...KKKKKKKKKKKKKKKKK....",
    "..WWKKKKKLLLLLKKKKKWW...",
    ".WWWWKKKKLLLLLKKKKWWWW..",
    ".WWWWGGGGGGGGGGGGGWWWW..",
    ".WWWWGGGGGGGGGGGGGWWWW..",
    ".WWWW.............WWWW..",
    "..WW...............WW...",
)
KART_W, KART_H = 24, 19

# (Mona fur, Mona shade, kart paint, kart shade, plate) per racer
RACERS = (
    ((124, 58, 237), (88, 28, 180), (232, 72, 72), (170, 40, 40), (255, 240, 200)),      # player: purple Mona, red kart
    ((48, 96, 200), (24, 60, 150), (255, 200, 48), (190, 140, 20), (255, 255, 255)),     # blue Mona, yellow kart
    ((72, 180, 96), (30, 120, 60), (60, 120, 255), (30, 70, 190), (255, 255, 255)),      # green Mona, blue kart
    ((255, 140, 60), (200, 90, 20), (80, 200, 120), (30, 140, 70), (255, 255, 255)),     # orange Mona, green kart
    ((255, 120, 190), (200, 60, 140), (255, 255, 255), (190, 190, 200), (40, 40, 60)),   # pink Mona, white kart
    ((80, 210, 230), (30, 150, 180), (40, 40, 50), (20, 20, 30), (255, 200, 48)),        # cyan Mona, black kart
)
WHEEL = (28, 28, 36)
BUMPER = (160, 160, 176)

TREE = (
    "......GGGGGG......",
    "....GGGGGGGGGG....",
    "...GGGGggGGGGGG...",
    "..GGGGGGGGGGGGGG..",
    "..GGGggGGGGGggGG..",
    ".GGGGGGGGGGGGGGGG.",
    ".GGGGGGGggGGGGGGG.",
    "..GGGGGGGGGGGGGG..",
    "...GGGGGGGGGGGG...",
    ".....GGGGGGGG.....",
    "........TT........",
    "........TT........",
    "........TT........",
    ".......TTTT.......",
)
BUSH = (
    "......GGGGGG......",
    "....GGGGGGGGGG....",
    "..GGGGggGGGggGG...",
    ".GGGGGGGGGGGGGGGG.",
    ".GGGggGGGGGGGGGGG.",
    "..GGGGGGGGGGGGGG..",
    "....GGGGGGGGGG....",
)
SIGN = (
    "..BBBBBBBBBBBBBB..",
    ".BWWWWWWWWWWWWWWB.",
    ".BWWWWWKKKKWWWWWB.",
    ".BWWWWKKKKKKWWWWB.",
    ".BWWWKKWKKWKKWWWB.",
    ".BWWWKKKKKKKKWWWB.",
    ".BWWWWKKKKKKWWWWB.",
    ".BWWWWWKKKKWWWWWB.",
    ".BWWWWWWWWWWWWWWB.",
    "..BBBBBBBBBBBBBB..",
    "........PP........",
    "........PP........",
    "........PP........",
    "........PP........",
)
COFFEE = (
    "....ss..ss........",
    ".....ss..ss.......",
    "....ss..ss........",
    "..................",
    "..WWWWWWWWWWWW....",
    "..WbbbbbbbbbbWWW..",
    "..WbbbbbbbbbbW.W..",
    "..WWbbbbbbbbWW.W..",
    "...WWWWWWWWWWWW...",
    "....WWWWWWWW......",
    ".....WWWWWW.......",
)
BUG = (
    "...rr......rr.....",
    "....rr....rr......",
    ".....RRRRRR.......",
    "....RRRRRRRR......",
    "...RRRRkkRRRR.....",
    "..RRRRRRRRRRRR....",
    "..RRRkRRRRkRRR....",
    "..RRRRRRRRRRRR....",
    "...RRRRRRRRRR.....",
    "....rr.rr.rr......",
)
PROP_W, PROP_H = 18, 14
PROP_PENS = {
    "G": (48, 150, 70), "g": (90, 200, 100), "T": (120, 80, 40),
    "B": (40, 40, 60), "W": (245, 245, 240), "K": (30, 30, 40), "P": (150, 150, 160),
    "s": (200, 200, 200), "b": (110, 70, 40),
    "R": (220, 60, 60), "r": (60, 30, 30), "k": (20, 20, 30),
}


def png(path, width, height, palette, pixels):
    """A paletted PNG; palette entries are (r, g, b, a), pixels are indexes."""
    rows = b"".join(b"\x00" + bytes(pixels[y * width:(y + 1) * width]) for y in range(height))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)

    data = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", b"".join(bytes(entry[:3]) for entry in palette))
            + chunk(b"tRNS", bytes(entry[3] for entry in palette))
            + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))
    Path(path).write_bytes(data)
    print(path, width, "x", height, len(data), "bytes")


class Sheet:
    def __init__(self, width, height):
        self.width, self.height = width, height
        self.palette = [(0, 0, 0, 0)]
        self.pixels = [0] * (width * height)

    def index(self, rgb):
        entry = (rgb[0], rgb[1], rgb[2], 255)
        if entry not in self.palette:
            self.palette.append(entry)
        return self.palette.index(entry)

    def put(self, x, y, rgb):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.pixels[y * self.width + x] = self.index(rgb)

    def stamp(self, rows, pens, left, top, shift=None):
        for y, line in enumerate(rows):
            dx = shift(y) if shift else 0
            for x, key in enumerate(line):
                if key in pens:
                    self.put(left + x + dx, top + y, pens[key])


def kart_shift(frame):
    """Steering frames lean Mona and the seat the way the kart turns."""
    def shift(y):
        if frame == 1:
            return 0
        lean = -1 if frame == 0 else 1
        if y < 8:
            return lean * 2
        if y < 13:
            return lean
        return 0
    return shift


def main():
    assets = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "apps" / "mona_kart" / "assets"
    assets.mkdir(exist_ok=True)

    karts = Sheet(KART_W * 3, KART_H * len(RACERS))
    for row, (fur, shade, paint, paint_shade, plate) in enumerate(RACERS):
        pens = {"M": fur, "m": shade, "K": paint, "k": paint_shade, "L": plate, "W": WHEEL, "G": BUMPER}
        for frame in range(3):
            karts.stamp(KART, pens, frame * KART_W, row * KART_H, kart_shift(frame))
    png(assets / "karts.png", karts.width, karts.height, karts.palette, karts.pixels)

    props = Sheet(PROP_W * 5, PROP_H)
    for column, rows in enumerate((TREE, BUSH, SIGN, COFFEE, BUG)):
        props.stamp(rows, PROP_PENS, column * PROP_W, PROP_H - len(rows))
    png(assets / "props.png", props.width, props.height, props.palette, props.pixels)


if __name__ == "__main__":
    main()

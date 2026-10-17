"""Build a ROM-independent pixel-font review package using only the standard library.

No ROM is opened. Glyph IDs are Unicode; no game encoding is assigned. All outputs
go into a new directory inside an explicit output policy root. Rasterization is integer-only (no AA).
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import zlib

from patchquest.consoles.snes.tiles import decode_tile, encode_tile
from patchquest.core.context import OutputPolicy

ASSET_ROOT = Path(__file__).resolve().parents[3] / "assets"
DEFAULT_FONT = ASSET_ROOT / "fonts/quest-pixel/glyphs.json"
DEFAULT_SPECIMEN = ASSET_ROOT / "fonts/quest-pixel/specimen.json"
EXTRAS = "‘’“”…—–♥♪←→↑↓×÷°é"
BG = (14, 20, 30)
PANEL = (23, 33, 47)
INK = (242, 237, 215)
GOLD = (225, 183, 103)
MUTED = (142, 161, 176)
LINE = (51, 68, 86)
MINT = (139, 210, 182)


def load_font(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data["format"] != "pixel-grid-v1" or data["canvas"] != [7, 8] or data["cell"] != [8, 8]:
        raise ValueError("Expected a 7x8 drawing canvas in an 8x8 cell")
    glyphs = {}
    for codepoint, encoded in data["glyphs"].items():
        char = chr(int(codepoint, 16))
        rows = encoded.split("/")
        if len(rows) != 8 or any(len(row) != 7 or set(row) - {".", "#"} for row in rows):
            raise ValueError(f"Malformed pixel grid U+{codepoint}")
        if char in glyphs:
            raise ValueError(f"Duplicate character U+{codepoint}")
        glyphs[char] = [[int(pixel == "#") for pixel in row] + [0] for row in rows]
    required = set(map(chr, range(32, 127))) | set(EXTRAS)
    if set(glyphs) != required:
        raise ValueError(f"Character coverage differs: {sorted(set(glyphs) ^ required)!r}")
    if any(any(row) for row in glyphs[" "]):
        raise ValueError("Space must be blank")
    if any(not any(any(row) for row in pixels) for char, pixels in glyphs.items() if char != " "):
        raise ValueError("Only space may be blank")
    return data, glyphs


def bounds(pixels):
    points = [(x, y) for y, row in enumerate(pixels) for x, bit in enumerate(row) if bit]
    if not points:
        return None
    return [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points) + 1, max(p[1] for p in points) + 1]


def profile_glyph(pixels, profile):
    """Return pixel matrix and advance. Proportional is a specimen-only study."""
    if profile == "native":
        return pixels, 8
    if profile == "small-in-16":
        out = [[0] * 16 for _ in range(16)]
        for y, row in enumerate(pixels):
            out[y + 4][4:12] = row
        return out, 16
    doubled = [[v for v in row for _ in range(2)] for row in pixels for _ in range(2)]
    if profile == "fixed-16":
        return doubled, 16
    if profile == "proportional-study":
        box = bounds(doubled)
        if box is None:
            return [[0] * 8 for _ in range(16)], 8
        left, _, right, _ = box
        return [row[left:right] + [0, 0] for row in doubled], right - left + 2
    raise ValueError(f"Unknown profile {profile}")


def text_width(glyphs, text, scale=1, profile="native"):
    return sum(profile_glyph(glyphs[c], profile)[1] for c in text) * scale


class Canvas:
    def __init__(self, width, height, color=BG):
        self.width, self.height = width, height
        self.pixels = [bytearray(color * width) for _ in range(height)]

    def rect(self, x, y, w, h, color):
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise ValueError(f"Rectangle outside canvas: {(x, y, w, h)}")
        for row in self.pixels[y:y + h]:
            row[x * 3:(x + w) * 3] = bytes(color) * w

    def text(self, glyphs, text, x, y, scale=1, color=INK, profile="native"):
        for char in text:
            if char not in glyphs:
                raise ValueError(f"Unsupported character: U+{ord(char):04X}")
            pixels, advance = profile_glyph(glyphs[char], profile)
            for gy, row in enumerate(pixels):
                for gx, bit in enumerate(row):
                    if bit:
                        self.rect(x + gx * scale, y + gy * scale, scale, scale, color)
            x += advance * scale
        return x

    def png(self):
        def chunk(tag, content):
            return struct.pack(">I", len(content)) + tag + content + struct.pack(">I", zlib.crc32(tag + content))
        raw = b"".join(b"\0" + bytes(row) for row in self.pixels)
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def appearance_approval(font_path):
    """Only a matching separate record can approve these exact artwork bytes."""
    source = Path(font_path)
    record = source.with_name('approval.json')
    if not record.is_file():
        return {'status': 'unverified', 'source_hash_matches': False}
    approval = json.loads(record.read_text(encoding='utf-8'))
    matches = approval.get('glyph_source_sha256') == hashlib.sha256(source.read_bytes()).hexdigest()
    approved = matches and approval.get('appearance_status') == 'approved'
    return {'status': 'approved' if approved else 'unverified', 'source_hash_matches': matches}


def specimen(glyphs, sample, appearance_status='unverified'):
    c = Canvas(1280, 1440)
    c.rect(48, 40, 6, 82, GOLD)
    c.text(glyphs, sample["title"], 76, 42, 5)
    c.text(glyphs, sample["revision"], 976, 48, 2, GOLD)
    c.text(glyphs, "PIXEL FONT / LETTERFORM & SPACING SPECIMEN", 76, 102, 2, MUTED)
    c.rect(48, 154, 1184, 2, LINE)
    c.text(glyphs, "01 / LETTERS & NUMBERS", 48, 184, 2, GOLD)
    for line, y in zip(sample["alphabet"], [226, 274, 322]):
        c.text(glyphs, line, 64, y, 4)
    c.text(glyphs, "02 / PUNCTUATION & DIALOGUE SYMBOLS", 48, 390, 2, GOLD)
    for i, line in enumerate(sample["punctuation"]):
        c.text(glyphs, line, 64, 430 + i * 36, 3)
    c.text(glyphs, "03 / RPG DIALOGUE", 48, 566, 2, GOLD)
    for i, lines in enumerate(sample["dialogue"]):
        x, y = 48 + (i % 2) * 608, 606 + (i // 2) * 182
        c.rect(x, y, 576, 158, LINE)
        c.rect(x + 2, y + 2, 572, 154, PANEL)
        for j, line in enumerate(lines):
            if text_width(glyphs, line, 2) > 528:
                raise ValueError("Dialogue does not fit review panel")
            c.text(glyphs, line, x + 24, y + 32 + j * 32, 2)
    c.text(glyphs, "04 / CELL SPACING STUDY", 48, 996, 2, GOLD)
    for i, (label, profile) in enumerate([
        ("16PX / 2X ART", "fixed-16"),
        ("16PX / SMALL ART", "small-in-16"),
        ("VARIABLE / STUDY", "proportional-study"),
    ]):
        x = 48 + i * 400
        c.rect(x, 1036, 384, 122, PANEL)
        c.text(glyphs, label, x + 16, 1054, 2, MINT)
        c.text(glyphs, "A torch.", x + 16, 1098, 2, profile=profile)
    c.text(glyphs, "Spacing studies do not establish runtime rendering.", 48, 1180, 2, MUTED)
    c.text(glyphs, "05 / LETTER DISTINCTION", 48, 1234, 2, GOLD)
    for i, line in enumerate(sample["legibility"]):
        c.text(glyphs, line, 64, 1272 + i * 38, 3)
    c.rect(48, 1366, 1184, 2, LINE)
    label = 'MASTER APPROVED' if appearance_status == 'approved' else 'APPEARANCE UNVERIFIED'
    c.text(glyphs, f"112 GLYPHS / INTEGER PIXELS / {label} / SPECIMEN ONLY", 48, 1394, 2, MUTED)
    return c.png()


def native_sheet(glyphs, sample):
    c = Canvas(512, 288, (0, 0, 0))
    lines = sample["alphabet"] + sample["punctuation"] + [""]
    lines += [line for block in sample["dialogue"] for line in block]
    lines += sample["legibility"]
    for i, line in enumerate(lines):
        c.text(glyphs, line, 8, 8 + i * 12, color=(255, 255, 255))
    return c.png()


def spacing_sheet(glyphs):
    c = Canvas(1280, 1072)
    c.text(glyphs, "ONE DESIGN / FOUR LAYOUTS", 48, 40, 4)
    c.text(glyphs, "ALL PANELS AT 3X DISPLAY SCALE / NO FILTERING", 48, 98, 2, MUTED)
    cases = [
        ("8X8 NATIVE / 8PX ADVANCE", "native", "NES-sized baseline. Requires game-specific tile encoding."),
        ("16X16 / 16PX ADVANCE", "fixed-16", "Integer enlargement study; verify target cell capacity."),
        ("8X8 ART IN 16X16 / 16PX ADVANCE", "small-in-16", "Fits the cell, but empty space still separates each letter."),
        ("16PX ART / VARIABLE ADVANCE", "proportional-study", "Visual study only. Requires new composition and layout code."),
    ]
    for i, (label, profile, note) in enumerate(cases):
        y = 152 + i * 214
        c.text(glyphs, label, 48, y, 2, GOLD)
        c.rect(48, y + 34, 1184, 128, PANEL)
        c.text(glyphs, "Take care, friend!", 72, y + 48, 3, profile=profile)
        c.text(glyphs, "A TORCH   128 gold", 72, y + 102, 3, profile=profile)
        c.text(glyphs, note, 48, y + 180, 2, MUTED)
    c.text(glyphs, "Font placement only; these are not game screenshots.", 48, 1032, 2, MINT)
    return c.png()


def atlas(glyphs):
    c = Canvas(1024, 896)
    for i, char in enumerate(sorted(glyphs, key=ord)):
        x, y = (i % 16) * 64, (i // 16) * 128
        c.rect(x + 1, y + 1, 62, 126, PANEL)
        c.text(glyphs, char, x + 16, y + 24, 4)
        c.text(glyphs, f"{ord(char):04X}", x + 16, y + 86, 1, GOLD)
    return c.png()


def validate_codecs(glyphs):
    """Test bit placement with explicit bit equations as well as codec round trips."""
    for pixels in glyphs.values():
        # NES separates each tile's two planes; this standalone study uses colors 0/1.
        nes = bytes(sum(bit << (7 - x) for x, bit in enumerate(row)) for row in pixels) + bytes(8)
        reconstructed = [[((nes[y] >> (7 - x)) & 1) | (((nes[y + 8] >> (7 - x)) & 1) << 1)
                          for x in range(8)] for y in range(8)]
        if reconstructed != pixels:
            raise ValueError("NES round trip failed")
        big, _ = profile_glyph(pixels, "fixed-16")
        packed = bytearray()
        for tx, ty in [(0, 0), (8, 0), (0, 8), (8, 8)]:
            # Complementary 1/2 palette roles are illustrative; live polarity needs verification.
            tile = [[1 if big[ty + y][tx + x] else 2 for x in range(8)] for y in range(8)]
            encoded = encode_tile(tile, 2)
            expected = bytes(value for row in tile for value in (
                sum((v & 1) << (7 - x) for x, v in enumerate(row)),
                sum(((v >> 1) & 1) << (7 - x) for x, v in enumerate(row))))
            if encoded != expected or decode_tile(encoded, 2) != tile:
                raise ValueError("SNES bitplane round trip failed")
            packed.extend(encoded)
        if len(packed) != 64:
            raise ValueError("Wrong 16x16 storage size")


def build(font_path, sample_path, destination, policy):
    destination = Path(destination).resolve()
    policy.check(destination)
    if destination == policy.root:
        raise ValueError("Choose a fresh child directory")
    if destination.exists():
        raise FileExistsError(destination)
    data, glyphs = load_font(font_path)
    approval = appearance_approval(font_path)
    font_sha = hashlib.sha256(Path(font_path).read_bytes()).hexdigest()
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    validate_codecs(glyphs)
    mapping = {
        "font": data["name"], "revision": data["revision"],
        "id_policy": "Unicode asset identifiers; no ROM token or allocation is assigned.",
        "glyphs": [{"unicode": f"U+{ord(c):04X}", "character": c,
                    "asset_index": i, "bounds_exclusive": bounds(glyphs[c]),
                    "advance_native": 8, "advance_fixed_16": 16,
                    "advance_proportional_study": profile_glyph(glyphs[c], "proportional-study")[1],
                    "rom_token": None} for i, c in enumerate(sorted(glyphs, key=ord))],
    }
    if Path(font_path).resolve() == DEFAULT_FONT:
        recorded_map = json.loads((DEFAULT_FONT.parent / "character-map.json").read_text(encoding="utf-8"))
        if recorded_map != mapping:
            raise ValueError("Source mapping/metrics changed; review and update character-map.json")
    artifacts = {
        "specimen.png": specimen(glyphs, sample, approval['status']),
        "native-1x.png": native_sheet(glyphs, sample),
        "spacing-comparison.png": spacing_sheet(glyphs),
        "glyph-atlas.png": atlas(glyphs),
        "character-map.json": (json.dumps(mapping, indent=2, ensure_ascii=True) + "\n").encode(),
    }
    # The generator's license never grants rights to an arbitrary input font.
    canonical = json.loads(DEFAULT_FONT.with_name('approval.json').read_text(encoding='utf-8'))
    quest_pixel = font_sha == canonical['glyph_source_sha256']
    artifacts['LICENSE-APACHE-2.0.txt'] = (ASSET_ROOT.parent / 'LICENSE').read_bytes()
    if quest_pixel:
        for name in ('LICENSE-CC-BY-3.0.txt', 'ATTRIBUTION.md', 'PROVENANCE.md'):
            artifacts[name] = DEFAULT_FONT.with_name(name).read_bytes()
        scope = ('# Generated package license scope\n\n'
                 'specimen.png, native-1x.png, spacing-comparison.png, glyph-atlas.png and '
                 'character-map.json contain Quest Pixel font material under CC BY 3.0 Unported. '
                 'See [the full terms](LICENSE-CC-BY-3.0.txt), [attribution](ATTRIBUTION.md) '
                 'and [provenance](PROVENANCE.md). Preserve applicable upstream notices and identify changes.\n\n'
                 'Project-authored documentation and validation metadata use '
                 '[Apache-2.0](LICENSE-APACHE-2.0.txt). The standard license texts remain unchanged. '
                 'Public maintainer: BrentW; no exclusive ownership of all glyphs is asserted.\n')
    else:
        scope = ('# Generated package license scope\n\n'
                 'The input font differs from the pinned Quest Pixel source. Its licensing is not determined '
                 'by this generator; retain its own permissions and notices before redistribution. '
                 'The Apache-2.0 generator license does not relicense the input font or rendered glyphs.\n\n'
                 'Project-authored validation metadata uses [Apache-2.0](LICENSE-APACHE-2.0.txt).\n')
    artifacts['LICENSE-SCOPE.md'] = scope.encode('utf-8')
    report = {
        "status": f"SPECIMEN ONLY; MASTER APPEARANCE {approval['status'].upper()}; RUNTIME UNVERIFIED",
        "appearance_approval": approval,
        "font_license": 'CC-BY-3.0' if quest_pixel else 'not determined for this input',
        "font": data["name"], "revision": data["revision"], "glyph_count": len(glyphs),
        "checks": {"full_112_character_coverage": True, "binary_pixel_grids": True,
                   "nes_bitplane_roundtrip": True, "snes_2bpp_roundtrip_and_bit_equations": True,
                   "fixed_cell_bounds": True, "no_rom_input_or_output": True},
        "font_source_sha256": font_sha,
        "specimen_source_sha256": hashlib.sha256(Path(sample_path).read_bytes()).hexdigest(),
        "builder_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "tile_codec_sha256": hashlib.sha256((Path(__file__).resolve().parents[1] / "consoles/snes/tiles.py").read_bytes()).hexdigest(),
        "artifacts": {name: hashlib.sha256(content).hexdigest() for name, content in artifacts.items()},
        "integration": "This specimen does not validate ROM codes, palette polarity, storage, renderer behavior or any game integration.",
    }
    artifacts["validation.json"] = (json.dumps(report, indent=2) + "\n").encode()
    destination.mkdir(parents=True, exist_ok=False)
    for name, content in artifacts.items():
        policy.write_new(destination / name, content)
    return report


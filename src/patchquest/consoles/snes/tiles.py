"""Decode explicit SNES planar tile hypotheses; write PNGs with no third-party libraries."""
import argparse
import struct
import zlib
from pathlib import Path


def decode_tile(data, bpp):
    if bpp not in (1, 2, 4, 8) or len(data) != bpp * 8:
        raise ValueError("Need exactly 8*bpp bytes per tile")
    pixels = []
    for y in range(8):
        row = []
        for x in range(8):
            color = 0
            for plane in range(bpp):
                offset = y if bpp == 1 else (plane // 2) * 16 + y * 2 + plane % 2
                color |= ((data[offset] >> (7 - x)) & 1) << plane
            row.append(color)
        pixels.append(row)
    return pixels


def encode_tile(pixels, bpp):
    data = bytearray(bpp * 8)
    if bpp not in (1, 2, 4, 8) or len(pixels) != 8 or any(len(r) != 8 for r in pixels):
        raise ValueError("Invalid tile")
    for y, row in enumerate(pixels):
        for x, color in enumerate(row):
            if not 0 <= color < 1 << bpp:
                raise ValueError("Color out of range")
            for plane in range(bpp):
                offset = y if bpp == 1 else (plane // 2) * 16 + y * 2 + plane % 2
                data[offset] |= ((color >> plane) & 1) << (7 - x)
    return bytes(data)


def png_gray(pixels, scale=1):
    if scale < 1:
        raise ValueError("Scale must be positive")
    height, width = len(pixels), len(pixels[0])
    raw = bytearray()
    for row in pixels:
        scan = b"\0" + bytes(v for v in row for _ in range(scale))
        raw.extend(scan * scale)
    def chunk(tag, content):
        return struct.pack(">I", len(content)) + tag + content + struct.pack(">I", zlib.crc32(tag + content))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width*scale, height*scale, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def sheet(data, bpp, columns=32):
    size = bpp * 8
    if not data or len(data) % size or columns < 1:
        raise ValueError("Data must contain whole tiles")
    count = len(data) // size
    pixels = [[64] * (columns * 9) for _ in range(((count + columns - 1) // columns) * 9)]
    for i in range(count):
        tile = decode_tile(data[i*size:(i+1)*size], bpp)
        for y in range(8):
            for x in range(8):
                pixels[(i // columns)*9+y][(i % columns)*9+x] = tile[y][x] * 255 // ((1 << bpp)-1)
    return pixels

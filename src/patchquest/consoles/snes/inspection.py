"""Read-only SNES inventory; Python standard library only. Header guesses are not proof."""
import argparse
import hashlib
import json
from pathlib import Path
import zlib


def hashes(data):
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "sha1": hashlib.sha1(data).hexdigest(),
            "crc32": f"{zlib.crc32(data):08x}"}


def mirrored_sum(data):
    """Sum recursively mirrored ROM to the next power-of-two size."""
    if not data:
        return 0
    size = 1 << (len(data).bit_length() - 1)
    result = sum(data[:size])
    tail = data[size:]
    if tail:
        tail_size = 1 << ((len(tail) - 1).bit_length())
        result += mirrored_sum(tail) * (size // tail_size)
    return result & 0xffff


def inspect(path):
    raw = path.read_bytes()
    skip = 512 if len(raw) % 0x8000 == 512 else 0
    data = raw[skip:]
    candidates = []
    for mapping, offset, mode in (("LoROM", 0x7fc0, 0), ("HiROM", 0xffc0, 1),
                                  ("ExHiROM", 0x40ffc0, 5)):
        if offset + 64 > len(data):
            continue
        h = data[offset:offset + 64]
        complement = int.from_bytes(h[28:30], "little")
        checksum = int.from_bytes(h[30:32], "little")
        reset = int.from_bytes(h[60:62], "little")
        printable = sum(32 <= c < 127 or c == 0 for c in h[:21]) >= 19 and any(h[:21])
        pair = checksum ^ complement == 0xffff
        mode_ok = h[21] in (0x20 | mode, 0x30 | mode)
        score = 3 * printable + 4 * pair + 3 * mode_ok + 2 * (reset >= 0x8000)
        candidates.append(dict(mapping=mapping, offset=hex(offset), score=score,
            title=h[:21].decode("ascii", "backslashreplace").rstrip(" \0"),
            map_mode=hex(h[21]), mode_consistent=mode_ok, cartridge_type=hex(h[22]),
            declared_rom_bytes=(1024 << h[23]) if h[23] <= 16 else None,
            declared_sram_bytes=(1024 << h[24]) if 0 < h[24] <= 16 else (0 if h[24] == 0 else None),
            region_code=h[25], licensee_code=hex(h[26]), revision=h[27],
            reset_vector=hex(reset), checksum=f"{checksum:04x}", complement=f"{complement:04x}",
            complement_valid=pair, calculated_checksum=f"{mirrored_sum(data):04x}",
            checksum_matches=checksum == mirrored_sum(data)))
    candidates.sort(key=lambda c: c["score"], reverse=True)
    return dict(file=path.as_posix(), file_bytes=len(raw), payload_bytes=len(data),
                copier_header_bytes_inferred=skip, hashes=hashes(raw), payload_hashes=hashes(data),
                mapping_status="heuristic; validate reset code and emulator mapping before editing",
                candidates=candidates)

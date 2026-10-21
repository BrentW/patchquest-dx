"""Lossless inspection and guarded payload edits for a strict D88 profile.

Apache-2.0. Independently implemented from documented container fields;
no emulator code, disk contents or filesystem assumptions are incorporated.
"""

from dataclasses import dataclass
from hashlib import sha256
from struct import unpack_from

HEADER = 0x2b0

@dataclass(frozen=True)
class Sector:
    disk: int
    track_slot: int
    ordinal: int
    header_offset: int
    data_offset: int
    size: int
    chrn: tuple
    density: int
    deleted: int
    status: int

@dataclass(frozen=True)
class Disk:
    offset: int
    size: int
    sectors: tuple
    warnings: tuple

@dataclass(frozen=True)
class Image:
    original: bytes
    disks: tuple
    def reconstruct(self):
        return self.original


def parse(data):
    """Strict 164-track-table D88 profile; preserve opaque data, never repair.

    Sector data length comes from header +14, as in MAME's D88 loader.
    CHRN, status and density are observations, not inferred geometry/filesystem.
    Unsupported/ambiguous structures fail closed. No game-specific data.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError('expected bytes-like container')
    data = bytes(data)
    if not data:
        raise ValueError('empty container')
    disks = []
    base = 0
    while base < len(data):
        if len(data) - base < HEADER:
            raise ValueError('truncated or unsupported disk header')
        size = unpack_from('<I', data, base + 0x1c)[0]
        if size < HEADER or base + size > len(data):
            raise ValueError('disk extent invalid')
        offsets = unpack_from('<164I', data, base + 0x20)
        used = [p for p in offsets if p]
        if len(used) != len(set(used)):
            raise ValueError('aliased track offsets')
        if any(p < HEADER or p >= size for p in used):
            raise ValueError('track outside disk')
        physical = sorted(used)
        limits = {p: (physical[i+1] if i+1 < len(physical) else size) for i,p in enumerate(physical)}
        sectors, warnings = [], []
        for slot, relative in enumerate(offsets):
            if not relative:
                continue
            pos, end = base + relative, base + limits[relative]
            if pos + 16 > end:
                raise ValueError('truncated sector header')
            count = unpack_from('<H', data, pos+4)[0]
            if not 1 <= count <= (end-pos)//16:
                raise ValueError('invalid sector count')
            for ordinal in range(count):
                if pos + 16 > end:
                    raise ValueError('sector header crosses track')
                if unpack_from('<H', data, pos+4)[0] != count:
                    raise ValueError('inconsistent sector count')
                length = unpack_from('<H', data, pos+14)[0]
                if pos+16+length > end:
                    raise ValueError('sector data crosses track')
                chrn = tuple(data[pos:pos+4])
                if chrn[3] > 7 or length != 128 << chrn[3]:
                    warnings.append(f'track {slot} sector ordinal {ordinal}: declared and nominal sizes differ')
                sectors.append(Sector(len(disks),slot,ordinal,pos,pos+16,length,chrn,data[pos+6],data[pos+7],data[pos+8]))
                pos += 16+length
            if pos != end:
                warnings.append(f'track {slot}: {end-pos} opaque trailing bytes retained')
        disks.append(Disk(base,size,tuple(sectors),tuple(warnings)))
        base += size
    return Image(data,tuple(disks))


def patch_sector(data, expected_sha256, disk_index, track_slot, ordinal, offset, expected, replacement):
    """Equal-size expected-byte edit in one explicitly selected stored sector."""
    if not all(type(value) is int and value >= 0 for value in
               (disk_index, track_slot, ordinal, offset)):
        raise ValueError('selection and offset must be nonnegative integers')
    if not all(isinstance(value, (bytes, bytearray, memoryview)) for value in
               (data, expected, replacement)):
        raise ValueError('expected bytes-like inputs')
    data, expected, replacement = bytes(data), bytes(expected), bytes(replacement)
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError('source SHA-256 mismatch')
    image = parse(data)
    matches = [s for d in image.disks for s in d.sectors if (s.disk,s.track_slot,s.ordinal)==(disk_index,track_slot,ordinal)]
    if len(matches) != 1:
        raise ValueError('sector selection is absent or ambiguous')
    sector = matches[0]
    if not expected or len(expected)!=len(replacement) or offset<0 or offset+len(expected)>sector.size:
        raise ValueError('edit must be nonempty, equal length and contained in sector')
    start = sector.data_offset+offset
    if data[start:start+len(expected)] != expected:
        raise ValueError('expected bytes mismatch')
    result = data[:start]+replacement+data[start+len(expected):]
    if parse(result).disks != image.disks:
        raise ValueError('structure changed')
    return result

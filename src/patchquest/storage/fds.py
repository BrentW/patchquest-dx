"""Strict, lossless FDS container inspection and guarded stored-file edits.

Apache-2.0. Independently implemented from public format definitions. No game
decoder, firmware, emulator implementation or real disk fixture is included.
"""
from dataclasses import dataclass
from hashlib import sha256

SIDE_SIZE = 65500
SIGNATURE = b'\x01*NINTENDO-HVC*'


def _bytes(value):
    if not isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError('Expected bytes-like data')
    return bytes(value)


@dataclass(frozen=True)
class File:
    side: int
    ordinal: int
    header_offset: int
    data_offset: int
    size: int
    number: int
    identifier: int
    name: bytes
    load_address: int
    file_type: int


@dataclass(frozen=True)
class Side:
    index: int
    offset: int
    information: bytes
    declared_files: int
    files: tuple
    tail_offset: int
    warnings: tuple


@dataclass(frozen=True)
class Image:
    original: bytes
    header: bytes
    sides: tuple

    def reconstruct(self):
        """Return the captured bytes, including reserved fields and opaque tails."""
        return self.original


def parse(data):
    """Read contiguous blocks without CRC/gap bytes, with optional 16-byte header.

    Exact side extents are mandatory. Only the declared file count is followed;
    remaining bytes are preserved as opaque, even when they resemble more files.
    Load addresses/types are metadata, not proof of an observed memory mapping.
    """
    data = _bytes(data)
    header = b''
    if data.startswith(b'FDS\x1a'):
        if len(data) < 16 or not data[4]:
            raise ValueError('Missing FDS header or side count')
        header = data[:16]
        count = header[4]
        if len(data) != 16 + count * SIDE_SIZE:
            raise ValueError('FDS declared side count and file size differ')
    else:
        count, remainder = divmod(len(data), SIDE_SIZE)
        if remainder or not 1 <= count <= 255:
            raise ValueError('Unsupported or truncated raw FDS side extent')
    sides = []
    for index in range(count):
        base = len(header) + index * SIDE_SIZE
        end = base + SIDE_SIZE
        if data[base:base + len(SIGNATURE)] != SIGNATURE:
            raise ValueError('Missing disk information block signature')
        if data[base + 56] != 2:
            raise ValueError('Missing file-count block')
        declared = data[base + 57]
        cursor = base + 58
        files, warnings = [], []
        for ordinal in range(declared):
            if cursor + 17 > end or data[cursor] != 3:
                raise ValueError('Missing or truncated file header')
            raw = data[cursor:cursor + 16]
            size = int.from_bytes(raw[13:15], 'little')
            if data[cursor + 16] != 4 or cursor + 17 + size > end:
                raise ValueError('Missing or truncated file data block')
            files.append(File(index, ordinal, cursor, cursor + 17, size,
                              raw[1], raw[2], raw[3:11],
                              int.from_bytes(raw[11:13], 'little'), raw[15]))
            if raw[15] > 2:
                warnings.append(f'File ordinal {ordinal}: unrecognized type retained')
            cursor += 17 + size
        if any(data[cursor:end]):
            warnings.append('Nonzero opaque tail retained; declared count may omit files')
        sides.append(Side(index, base, data[base:base + 56], declared,
                          tuple(files), cursor, tuple(warnings)))
    return Image(data, header, tuple(sides))


def patch_file(data, expected_sha256, side, ordinal, offset, expected, replacement):
    """Return one equal-size expected-byte edit in an explicitly selected file.

    Side/ordinal selection remains unambiguous with duplicate names and IDs.
    Header changes, resizing, tail allocation and CPU/PPU writes are unsupported.
    Callers must establish the edited payload's consumer/ownership separately.
    """
    if any(type(n) is not int or n < 0 for n in (side, ordinal, offset)):
        raise ValueError('Selection and offset must be nonnegative integers')
    data, expected, replacement = map(_bytes, (data, expected, replacement))
    if sha256(data).hexdigest() != expected_sha256:
        raise ValueError('Source SHA-256 mismatch')
    image = parse(data)
    if side >= len(image.sides) or ordinal >= len(image.sides[side].files):
        raise ValueError('Absent file selection')
    file = image.sides[side].files[ordinal]
    if not expected or len(expected) != len(replacement) or offset + len(expected) > file.size:
        raise ValueError('Edit must be nonempty, equal-size and within file data')
    start = file.data_offset + offset
    if data[start:start + len(expected)] != expected:
        raise ValueError('Expected bytes mismatch')
    target = data[:start] + replacement + data[start + len(expected):]
    parsed = parse(target)
    if parsed.header != image.header or parsed.sides != image.sides:
        raise ValueError('Parsed structure changed')
    return target


def inventory(data):
    """JSON-compatible private report. No decoding, ownership or boot claims."""
    image = parse(data)
    return dict(format='fds-contiguous-blocks', bytes=len(image.original),
                sha256=sha256(image.original).hexdigest(), header_bytes=len(image.header),
                header_hex=image.header.hex(), sides=[dict(
                    index=side.index, offset=side.offset, declared_files=side.declared_files,
                    information_hex=side.information.hex(), tail_offset=side.tail_offset,
                    tail_size=side.offset + SIDE_SIZE - side.tail_offset,
                    warnings=list(side.warnings), files=[dict(
                        ordinal=f.ordinal, number=f.number, identifier=f.identifier,
                        name_hex=f.name.hex(), header_offset=f.header_offset,
                        data_offset=f.data_offset, size=f.size, load_address=f.load_address,
                        file_type=f.file_type,
                        sha256=sha256(image.original[f.data_offset:f.data_offset + f.size]).hexdigest())
                        for f in side.files]) for side in image.sides])

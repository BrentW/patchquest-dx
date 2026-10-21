"""Explicit mapped streams and linked BASIC records; Apache-2.0.

No disk discovery, filesystem inference, token decoding or source mutation.
"""
from dataclasses import dataclass
from struct import unpack_from


def integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(name + ' must be a nonnegative integer')
    return value


@dataclass(frozen=True)
class Span:
    logical: int
    source: int
    size: int


@dataclass(frozen=True)
class MappedStream:
    data: bytes
    spans: tuple

    def source_ranges(self, offset, length):
        """Map a logical range to ordered (source offset, length) pieces."""
        integer(offset, 'offset'); integer(length, 'length')
        if offset + length > len(self.data):
            raise ValueError('range outside stream')
        result = []
        for span in self.spans:
            lo = max(offset, span.logical)
            hi = min(offset + length, span.logical + span.size)
            if lo < hi:
                result.append((span.source + lo - span.logical, hi - lo))
        return tuple(result)


def gather(source, ranges):
    """Gather caller-selected nonoverlapping ranges in caller-specified order."""
    if not isinstance(source, (bytes, bytearray, memoryview)):
        raise ValueError('expected bytes-like source')
    source = bytes(source)
    spans, parts, used = [], [], []
    logical = 0
    for offset, length in ranges:
        integer(offset, 'offset'); integer(length, 'length')
        end = offset + length
        if not length or end > len(source):
            raise ValueError('empty or out-of-bounds span')
        if any(offset < b and a < end for a, b in used):
            raise ValueError('overlapping source spans')
        used.append((offset, end))
        spans.append(Span(logical, offset, length))
        parts.append(source[offset:end])
        logical += length
    return MappedStream(b''.join(parts), tuple(spans))


@dataclass(frozen=True)
class Line:
    offset: int
    next_address: int
    number: int
    body: bytes
    end: int


@dataclass(frozen=True)
class Program:
    original: bytes
    lines: tuple
    terminator_offset: int
    consumed: int

    def reconstruct(self):
        """Preserve the complete supplied extent, including uninterpreted tail."""
        return self.original


def parse_lines(data, *, base_address):
    """Read explicit LE16 next-link/line-number records with a final zero link.

    Caller supplies the address corresponding to data[0]. Each nonzero link
    points to the next record; the byte immediately before it must be NUL.
    Internal body NULs are legal (e.g. numeric operands). Bodies remain opaque.
    This profile is not automatic detection of a BASIC dialect or load address.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError('expected bytes-like program')
    data = bytes(data)
    integer(base_address, 'base_address')
    if base_address > 0xffff:
        raise ValueError('base address exceeds 16 bits')
    pos, lines = 0, []
    while True:
        if pos + 2 > len(data):
            raise ValueError('missing terminal link')
        link = unpack_from('<H', data, pos)[0]
        if not link:
            return Program(data, tuple(lines), pos, pos + 2)
        end = link - base_address
        if end < pos + 5 or end + 2 > len(data):
            raise ValueError('invalid forward line link')
        if data[end - 1] != 0:
            raise ValueError('missing line terminator')
        number = unpack_from('<H', data, pos + 2)[0]
        if lines and number <= lines[-1].number:
            raise ValueError('line numbers must increase')
        lines.append(Line(pos, link, number, data[pos + 4:end - 1], end))
        pos = end

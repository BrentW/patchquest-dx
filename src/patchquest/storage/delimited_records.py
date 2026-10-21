"""Read-only, explicitly bounded delimiter records; Apache-2.0.

No encoding, record count, allocation or padding is inferred.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Record:
    offset: int
    end: int
    body: bytes


@dataclass(frozen=True)
class Pool:
    original: bytes
    records: tuple
    consumed: int
    remainder: bytes

    def reconstruct(self):
        return self.original


def parse_records(data, *, delimiter, count):
    """Read exactly count delimiter-terminated opaque records from supplied bytes.

    Offsets are relative to data. End excludes the delimiter. Empty records are
    retained. Remaining bytes are opaque, not automatically reusable padding.
    The caller must supply only the independently established pool extent.
    """
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise ValueError('expected bytes-like pool')
    if type(delimiter) is not int or not 0 <= delimiter <= 255:
        raise ValueError('delimiter must be one byte')
    if type(count) is not int or count < 0:
        raise ValueError('count must be a nonnegative integer')
    data = bytes(data)
    if count > len(data):
        raise ValueError('record count exceeds pool capacity')
    records, pos = [], 0
    for _ in range(count):
        end = data.find(bytes([delimiter]), pos)
        if end < 0:
            raise ValueError('missing delimiter within pool')
        records.append(Record(pos, end, data[pos:end]))
        pos = end + 1
    return Pool(data, tuple(records), pos, data[pos:])

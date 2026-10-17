"""Checksum correction with an explicitly validated payload header location."""
from .inspection import mirrored_sum


def update(data, header_offset, copier_header_bytes=0):
    if copier_header_bytes not in (0, 512):
        raise ValueError('Copier header policy must be explicit: 0 or 512 bytes')
    payload = bytearray(data[copier_header_bytes:])
    if header_offset not in (0x7fc0, 0xffc0, 0x40ffc0) or header_offset + 64 > len(payload):
        raise ValueError('Unsupported or out-of-bounds SNES header')
    at = header_offset + 28
    payload[at:at+4] = b'\xff\xff\x00\x00'
    value = mirrored_sum(payload)
    payload[at:at+4] = (value ^ 65535).to_bytes(2, 'little') + value.to_bytes(2, 'little')
    if mirrored_sum(payload) != value:
        raise ValueError('Checksum field lies in a nonstandard mirrored region')
    return data[:copier_header_bytes] + bytes(payload)

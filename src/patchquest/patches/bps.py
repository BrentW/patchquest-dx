"""Deterministic BPS1 encoder (SourceRead/TargetRead); validates with a strict subset decoder."""
import argparse
from pathlib import Path
import struct
import zlib


def number(value):
    out = bytearray()
    while True:
        byte = value & 127
        value >>= 7
        if value == 0:
            out.append(byte | 128)
            return out
        out.append(byte)
        value -= 1


def crc(data):
    return struct.pack("<I", zlib.crc32(data))


def encode(source, target):
    patch = bytearray(b"BPS1") + number(len(source)) + number(len(target)) + number(0)
    pos = 0
    while pos < len(target):
        equal = pos < len(source) and source[pos] == target[pos]
        end = pos + 1
        while end < len(target) and (end < len(source) and source[end] == target[end]) == equal:
            end += 1
        patch += number(((end - pos - 1) << 2) | (0 if equal else 1))
        if not equal:
            patch += target[pos:end]
        pos = end
    patch += crc(source) + crc(target)
    patch += crc(patch)
    return bytes(patch)


def apply(source, patch):
    if len(patch) < 19 or patch[:4] != b"BPS1" or crc(patch[:-4]) != patch[-4:]:
        raise ValueError("Invalid patch or CRC")
    pos = 4
    limit = len(patch) - 12
    def read():
        nonlocal pos
        value, shift = 0, 1
        while True:
            if pos >= limit:
                raise ValueError("Truncated integer")
            byte = patch[pos]; pos += 1
            value += (byte & 127) * shift
            if byte & 128:
                return value
            shift <<= 7
            value += shift
    size, target_size, metadata_size = read(), read(), read()
    if size != len(source) or crc(source) != patch[-12:-8]:
        raise ValueError("Wrong source")
    pos += metadata_size
    result = bytearray()
    while len(result) < target_size:
        command = read(); length = (command >> 2) + 1; action = command & 3
        if len(result) + length > target_size:
            raise ValueError("Target overflow")
        if action == 0:
            block = source[len(result):len(result) + length]
        elif action == 1:
            if pos + length > limit:
                raise ValueError("Truncated literal")
            block = patch[pos:pos + length]; pos += length
        else:
            raise ValueError("This verifier supports only this encoder's SourceRead/TargetRead subset")
        if len(block) != length:
            raise ValueError("Source overflow")
        result += block
    if pos != limit or crc(result) != patch[-8:-4]:
        raise ValueError("Target CRC or stream mismatch")
    return bytes(result)

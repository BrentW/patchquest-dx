"""Synthetic data only: never writes or modifies a user's ROM."""
import random
import tempfile
import unittest
from pathlib import Path

import _bootstrap
from patchquest.patches.bps import apply, encode, number
from patchquest.core.edits import build, load_source
from patchquest.core.context import OutputPolicy
from patchquest.consoles.snes.inspection import inspect, mirrored_sum


class ToolTests(unittest.TestCase):
    def test_bps_roundtrip(self):
        rng = random.Random(190)
        cases = [(b"", b""), (b"a", b""), (b"", b"x" * 20000),
                 (b"abc", b"abc"), (b"abc", b"axcDE")]
        for _ in range(40):
            source = rng.randbytes(rng.randrange(500))
            target = bytearray(source)
            target[rng.randrange(len(target) + 1):] = rng.randbytes(rng.randrange(500))
            cases.append((source, bytes(target)))
        for source, target in cases:
            patch = encode(source, target)
            self.assertEqual(apply(source, patch), target)
            self.assertEqual(encode(source, target), patch)
            damaged = bytearray(patch); damaged[-1] ^= 1
            with self.assertRaises(ValueError):
                apply(source, damaged)
            with self.assertRaises(ValueError):
                apply(source + b"wrong", patch)

    def test_spec_number_vectors(self):
        self.assertEqual(number(0), b"\x80")
        self.assertEqual(number(127), b"\xff")
        self.assertEqual(number(128), b"\x00\x80")
        self.assertEqual(number(256), b"\x00\x81")

    def test_guarded_edits(self):
        edit = dict(offset="0x1", expected_hex="62", replacement_hex="78")
        self.assertEqual(build(b"abc", [edit]), b"axc")
        self.assertEqual(build(b"abc", []), b"abc")
        for edits in ([edit, edit], [dict(edit, offset="0x99")],
                      [dict(edit, expected_hex="00")], [dict(edit, replacement_hex="7879")],
                      [dict(edit, offset="-1")]):
            with self.assertRaises(ValueError):
                build(b"abc", edits)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "original.sfc"
            path.write_bytes(b"abc")
            with self.assertRaises(ValueError):
                load_source(path, "wrong")
            with self.assertRaises(ValueError):
                OutputPolicy(Path(tmp)/"output",(path,)).write_new(path, b"bad")
            self.assertEqual(path.read_bytes(), b"abc")

    def test_header_and_mirroring(self):
        self.assertEqual(mirrored_sum(b"\x01\x02\x03"), 9)
        data = bytearray(0x8000)
        data[0x7fc0:0x7fd5] = b"TEST" + b" " * 17
        data[0x7fd5] = 0x20
        data[0x7fd7] = 5
        data[0x7ffc:0x7ffe] = b"\x00\x80"
        data[0x7fdc:0x7fe0] = b"\xff\xff\x00\x00"
        checksum = mirrored_sum(data)
        data[0x7fdc:0x7fe0] = (checksum ^ 0xffff).to_bytes(2, "little") + checksum.to_bytes(2, "little")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.sfc"
            path.write_bytes(bytes(512) + data)
            result = inspect(path)
            self.assertEqual(result["copier_header_bytes_inferred"], 512)
            self.assertEqual(result["candidates"][0]["mapping"], "LoROM")
            self.assertTrue(result["candidates"][0]["checksum_matches"])


if __name__ == "__main__":
    unittest.main()

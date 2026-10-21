"""Invented containers only; no firmware, real disk bytes or private imports."""
import contextlib
from hashlib import sha256
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from _bootstrap import ROOT
from patchquest.storage.fds import parse, inventory, patch_file, SIDE_SIZE, SIGNATURE
from patchquest.patches import bps
from patchquest.core.context import OutputPolicy


def side(payloads=(b'Invented message',), tail=b''):
    raw = bytearray(SIDE_SIZE)
    raw[:len(SIGNATURE)] = SIGNATURE
    raw[15:56] = bytes(range(41))  # Authored opaque information, not a capture.
    raw[56:58] = bytes([2, len(payloads)])
    cursor = 58
    for payload in payloads:
        header = bytes([3, 19, 23]) + b'EXAMPLE!' + bytes([0, 0x70]) + len(payload).to_bytes(2, 'little') + b'\0'
        raw[cursor:cursor + 17 + len(payload)] = header + b'\x04' + payload
        cursor += 17 + len(payload)
    raw[cursor:cursor + len(tail)] = tail
    return bytes(raw)


def headed(raw):
    return b'FDS\x1a' + bytes([len(raw) // SIDE_SIZE]) + b'opaque-meta' + raw


class FdsChecks(unittest.TestCase):
    def test_roundtrip_header_and_raw_multiside(self):
        raw = side() + side((b'Other authored text', b''), b'opaque suffix')
        for data in (raw, headed(raw), bytearray(raw), memoryview(raw)):
            image = parse(data)
            self.assertEqual(image.reconstruct(), data)
            self.assertEqual(len(image.sides), 2)
            self.assertEqual(image.sides[1].files[1].size, 0)
            self.assertTrue(image.sides[1].warnings)
        self.assertEqual(parse(headed(raw)).header[5:], b'opaque-meta')

    def test_guarded_selection_and_exact_preservation(self):
        for header in (False, True):
            source = side((b'ABCDEF', b'ABCDEF')) + side((b'ABCDEF',))
            if header: source = headed(source)
            image = parse(source)
            for si, ordinal in ((0, 0), (0, 1), (1, 0)):
                target = patch_file(source, sha256(source).hexdigest(), si, ordinal, 1, b'BCD', b'xyz')
                start = image.sides[si].files[ordinal].data_offset + 1
                self.assertEqual(target[:start], source[:start])
                self.assertEqual(target[start + 3:], source[start + 3:])
                self.assertEqual(target[start:start + 3], b'xyz')
                self.assertEqual(parse(target).sides, image.sides)
                patch = bps.encode(source, target)
                self.assertEqual(bps.encode(source, target), patch)
                self.assertEqual(bps.apply(source, patch), target)
                with self.assertRaises(ValueError): bps.apply(source[:-1] + b'!', patch)

    def test_invalid_containers(self):
        valid = side()
        mutations = [b'', valid[:-1], valid + b'\0', b'\0' * SIDE_SIZE,
                     b'FDS\x1a', headed(valid)[:-1], headed(valid) + b'\0']
        for pos, value in ((0, 2), (56, 0), (58, 4), (74, 3)):
            raw = bytearray(valid); raw[pos] = value; mutations.append(bytes(raw))
        raw = bytearray(valid); raw[71:73] = b'\xff\xff'; mutations.append(bytes(raw))
        h = bytearray(headed(valid)); h[4] = 2; mutations.append(bytes(h))
        h = bytearray(headed(valid)); h[4] = 0; mutations.append(bytes(h))
        for data in mutations:
            with self.subTest(length=len(data), first=data[:5]):
                with self.assertRaises(ValueError): parse(data)

    def test_tail_is_not_implicitly_discovered_or_allocated(self):
        data = side((b'X',), tail=b'\x03Uncounted extra structure')
        image = parse(data)
        self.assertEqual(len(image.sides[0].files), 1)
        self.assertTrue(image.sides[0].warnings)
        with self.assertRaises(ValueError): patch_file(data, sha256(data).hexdigest(), 0, 1, 0, b'X', b'Y')

    def test_guard_failures_and_snapshotted_inputs(self):
        data = side((b'ABC',)); digest = sha256(data).hexdigest()
        for value in (None, 42, 'disk'):
            with self.assertRaises(ValueError): parse(value)
        mutable = bytearray(data); image = parse(mutable); mutable[-1] = 9
        self.assertEqual(image.original, data)
        cases = [(0, 0, 0, b'', b''), (0, 0, 0, b'A', b'XX'), (0, 0, 2, b'BC', b'XY'),
                 (0, 0, 0, b'Z', b'Y'), (True, 0, 0, b'A', b'Z'), (-1, 0, 0, b'A', b'Z'),
                 (0, 0.0, 0, b'A', b'Z'), (2, 0, 0, b'A', b'Z')]
        for args in cases:
            with self.assertRaises(ValueError): patch_file(data, digest, *args)
        with self.assertRaises(ValueError): patch_file(data, '0' * 64, 0, 0, 0, b'A', b'Z')

    def test_exact_side_boundary_and_missing_declared_file(self):
        data = side((b'Z' * (SIDE_SIZE - 75),))
        image = parse(data)
        self.assertEqual(image.sides[0].tail_offset, SIDE_SIZE)
        self.assertEqual(image.sides[0].warnings, ())
        target = patch_file(data, sha256(data).hexdigest(), 0, 0,
                            SIDE_SIZE - 76, b'Z', b'!')
        self.assertEqual(target[-1:], b'!')
        invalid = bytearray(side()); invalid[57] = 2
        with self.assertRaises(ValueError): parse(invalid)

    def test_chained_edits_reject_stale_hash_and_overlaps(self):
        data = side((b'ABCDEFG',)); digest = sha256(data).hexdigest()
        first = patch_file(data, digest, 0, 0, 0, b'AB', b'ab')
        with self.assertRaises(ValueError): patch_file(first, digest, 0, 0, 5, b'FG', b'fg')
        with self.assertRaises(ValueError): patch_file(first, sha256(first).hexdigest(), 0, 0, 1, b'BC', b'bc')
        final = patch_file(first, sha256(first).hexdigest(), 0, 0, 5, b'FG', b'fg')
        other = patch_file(data, digest, 0, 0, 5, b'FG', b'fg')
        self.assertEqual(final, patch_file(other, sha256(other).hexdigest(), 0, 0, 0, b'AB', b'ab'))

    def test_inventory_and_output_policy(self):
        data = headed(side((b'123', b'456')))
        report = inventory(data)
        self.assertEqual(report['header_bytes'], 16)
        self.assertEqual(report['sides'][0]['files'][1]['sha256'], sha256(b'456').hexdigest())
        self.assertEqual(report['sides'][0]['files'][0]['data_offset'], 16 + 75)
        json.dumps(report)
        with TemporaryDirectory() as folder:
            original = Path(folder) / 'original.fds'; original.write_bytes(data)
            policy = OutputPolicy(Path(folder) / 'out', (original,))
            policy.write_new('copy.fds', data)
            with self.assertRaises(FileExistsError): policy.write_new('copy.fds', data)
            with self.assertRaises(ValueError): policy.write_new(original, data)
            self.assertEqual(original.read_bytes(), data)

    def test_cli_uses_explicit_fds_command(self):
        from patchquest.cli import main
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'invented.fds'; path.write_bytes(side())
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = main(['fds-inspect', str(path)])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())['format'], 'fds-contiguous-blocks')


if __name__ == '__main__': unittest.main()

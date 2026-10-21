"""Independent synthetic records; no game or firmware fixtures."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.storage.delimited_records import parse_records
from patchquest.storage.basic_records import gather


class DelimitedRecordsTests(unittest.TestCase):
    def test_empty_and_binary_bodies(self):
        data = b'\x00\x81|next||TAIL'
        pool = parse_records(data, delimiter=124, count=3)
        self.assertEqual([r.body for r in pool.records], [b'\x00\x81', b'next', b''])
        self.assertEqual([(r.offset, r.end) for r in pool.records], [(0, 2), (3, 7), (8, 8)])
        self.assertEqual(pool.remainder, b'TAIL')
        self.assertEqual(pool.reconstruct(), data)

    def test_explicit_count_preserves_later_delimiters(self):
        pool = parse_records(b'A;B;opaque', delimiter=59, count=1)
        self.assertEqual(pool.consumed, 2)
        self.assertEqual(pool.remainder, b'B;opaque')

    def test_does_not_read_past_supplied_extent(self):
        with self.assertRaises(ValueError):
            parse_records(b'not terminated', delimiter=0, count=1)

    def test_zero_records(self):
        pool = parse_records(b'opaque', delimiter=0, count=0)
        self.assertEqual(pool.records, ())
        self.assertEqual(pool.remainder, b'opaque')

    def test_bytes_snapshot(self):
        data = bytearray(b'x\x00tail')
        pool = parse_records(data, delimiter=0, count=1)
        data[0] = 121
        self.assertEqual(pool.records[0].body, b'x')

    def test_cross_span_provenance(self):
        stream = gather(b'AB__CD!tail', [(0, 2), (4, 7)])
        record = parse_records(stream.data, delimiter=33, count=1).records[0]
        self.assertEqual(record.body, b'ABCD')
        self.assertEqual(stream.source_ranges(record.offset, len(record.body)), ((0, 2), (4, 2)))

    def test_invalid_parameters(self):
        for delimiter, count in [(True, 1), (-1, 1), (256, 1), (0, True), (0, -1), (0, 10)]:
            with self.assertRaises(ValueError):
                parse_records(b'a', delimiter=delimiter, count=count)
        with self.assertRaises(ValueError):
            parse_records('text', delimiter=0, count=1)


if __name__ == '__main__':
    unittest.main()

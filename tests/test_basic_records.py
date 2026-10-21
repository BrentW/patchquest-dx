"""Independently invented records; no commercial media or firmware."""
import unittest
from struct import pack
from _bootstrap import ROOT
from patchquest.storage.basic_records import gather, parse_lines


def invented(base=0x2100):
    data = bytearray()
    for n, body in [(7, b'Example\x00operand'), (42, b'Other "sample"')]:
        end = len(data) + 5 + len(body)
        data += pack('<HH', base + end, n) + body + b'\0'
    return bytes(data) + b'\0\0opaque tail'


class BasicRecordsTests(unittest.TestCase):
    def test_opaque_body_nuls_and_tail(self):
        raw = invented()
        p = parse_lines(raw, base_address=0x2100)
        self.assertEqual([x.number for x in p.lines], [7, 42])
        self.assertEqual(p.lines[0].body, b'Example\x00operand')
        self.assertEqual(raw[p.consumed:], b'opaque tail')
        self.assertEqual(p.reconstruct(), raw)

    def test_reordered_spans_cross_boundary_mapping(self):
        s = gather(b'abcdefghijklmno', [(10, 5), (1, 4)])
        self.assertEqual(s.data, b'klmnobcde')
        self.assertEqual(s.source_ranges(3, 4), ((13, 2), (1, 2)))
        self.assertEqual(s.source_ranges(9, 0), ())

    def test_split_record_reassembly(self):
        raw = invented()
        container = raw[:3] + b'UNRELATED' + raw[3:]
        stream = gather(container, [(0, 3), (12, len(raw)-3)])
        self.assertEqual(parse_lines(stream.data, base_address=0x2100).reconstruct(), raw)

    def test_bad_ranges(self):
        for ranges in [[(0, 0)], [(2, 9)], [(0, 3), (2, 1)], [(-1, 1)], [(True, 1)]]:
            with self.subTest(ranges=ranges), self.assertRaises(ValueError):
                gather(b'1234', ranges)
        with self.assertRaises(ValueError): gather('text', [])
        with self.assertRaises(ValueError): gather(b'12', [(0, 2)]).source_ranges(1, 2)

    def test_links_bounds_and_cycles(self):
        raw = invented()
        for link in [1, 0x2100, 0x2104, 0xffff]:
            with self.subTest(link=link), self.assertRaises(ValueError):
                parse_lines(pack('<H', link) + raw[2:], base_address=0x2100)

    def test_missing_terminators(self):
        raw = invented(); p = parse_lines(raw, base_address=0x2100)
        bad = bytearray(raw); bad[p.lines[0].end-1] = 1
        with self.assertRaises(ValueError): parse_lines(bad, base_address=0x2100)
        with self.assertRaises(ValueError): parse_lines(raw[:p.consumed-1], base_address=0x2100)

    def test_line_order(self):
        raw = bytearray(invented()); p = parse_lines(raw, base_address=0x2100)
        off = p.lines[1].offset + 2; raw[off:off+2] = pack('<H', 7)
        with self.assertRaises(ValueError): parse_lines(raw, base_address=0x2100)

    def test_explicit_address_and_immutable_capture(self):
        raw = bytearray(invented(0x400)); p = parse_lines(raw, base_address=0x400)
        raw[4] = 0
        self.assertNotEqual(p.reconstruct(), bytes(raw))
        for base in [-1, True, 0x10000]:
            with self.assertRaises(ValueError): parse_lines(b'\0\0', base_address=base)
        self.assertEqual(parse_lines(b'\0\0', base_address=0).lines, ())


if __name__ == '__main__':
    unittest.main()

"""Invented byte fixtures exercise the documented model, never a real renderer."""
import importlib.util
import itertools
import unittest

from _bootstrap import ROOT

spec = importlib.util.spec_from_file_location(
    'tile_dictionary_model', ROOT / 'examples/tile_dictionary_model.py')
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class TileDictionaryModelTests(unittest.TestCase):
    def test_exact_deduplication_keeps_order_blanks_and_near_matches(self):
        original = (b'ABAB\0\0AC', b'ACAB\0\0', b'')
        dictionary, maps = model.deduplicate(original, 2)
        self.assertEqual(dictionary, b'AB\0\0AC')
        self.assertEqual(maps, ((0, 0, 1, 2), (2, 0, 1), ()))
        rebuilt = tuple(b''.join(dictionary[i*2:i*2+2] for i in m) for m in maps)
        self.assertEqual(rebuilt, original)
        self.assertEqual(model.deduplicate(original, 2), (dictionary, maps))

    def test_bank_and_length_limits_split_otherwise_adjacent_tiles(self):
        runs = model.coalesce((0, 1, 2, 3, 4), tile_bytes=2, dictionary_tiles=5,
                              source_start=4, bank_bytes=8, max_run_bytes=4)
        self.assertEqual(runs, ((4, 0, 4), (8, 4, 4), (12, 8, 2)))

    def test_repeated_and_reversed_indices_do_not_merge(self):
        runs = model.coalesce((1, 1, 0, 1), tile_bytes=2, dictionary_tiles=2,
                              source_start=0, bank_bytes=16, max_run_bytes=8)
        self.assertEqual(runs, ((2, 0, 2), (2, 2, 2), (0, 4, 4)))

    def test_exhaustive_small_maps_reconstruct_independent_expected_bytes(self):
        dictionary = b'catdogowl'
        memory = b'......' + dictionary
        for indices in itertools.product(range(3), repeat=4):
            for cap in (3, 6, 12):
                runs = model.coalesce(indices, tile_bytes=3, dictionary_tiles=3,
                                      source_start=6, bank_bytes=9, max_run_bytes=cap)
                destination = bytearray(b'?' * 12)
                covered = []
                for source, target, size in runs:
                    self.assertLessEqual(size, cap)
                    self.assertEqual(source // 9, (source + size - 1) // 9)
                    destination[target:target+size] = memory[source:source+size]
                    covered.extend(range(target, target+size))
                self.assertEqual(covered, list(range(12)))
                self.assertEqual(destination, b''.join((b'cat', b'dog', b'owl')[i]
                                                      for i in indices))

    def test_descriptor_and_loader_overhead_can_reverse_payload_savings(self):
        example = model.worked_example()
        self.assertEqual(example['original_payload_bytes'], 96)
        self.assertEqual(example['dictionary_bytes'], 16)
        self.assertEqual(example['transfer_count'], 16)
        self.assertEqual(example['total_stored_bytes'], 84)
        # Same invented format without coalescing: 24 descriptors plus overhead.
        uncoalesced_total = 16 + example['uncoalesced_transfer_count'] * 3 + 20
        self.assertEqual(uncoalesced_total, 108)
        self.assertLess(example['total_stored_bytes'], example['original_payload_bytes'])
        self.assertGreater(uncoalesced_total, example['original_payload_bytes'])

    def test_equal_destination_is_not_queue_completion(self):
        # The suffix already matches. Writing the prefix yields equality while
        # a redundant suffix copy is still pending: equality cannot time a load.
        target = b'catdog'
        destination = bytearray(b'???dog')
        queue = [(0, b'cat'), (3, b'dog')]
        offset, data = queue.pop(0)
        destination[offset:offset+len(data)] = data
        self.assertEqual(destination, target)
        self.assertTrue(queue)
        offset, data = queue.pop(0)
        destination[offset:offset+len(data)] = data
        self.assertEqual(destination, target)
        self.assertFalse(queue)

    def test_rejects_partial_tiles_invalid_indices_and_unsplittable_tile(self):
        for payload, size in ((b'odd', 2), ('text', 2), (b'ab', 0), (b'ab', True)):
            with self.assertRaises(ValueError): model.deduplicate((payload,), size)
        base = dict(tile_bytes=2, dictionary_tiles=2, source_start=0,
                    bank_bytes=8, max_run_bytes=4)
        for index in (-1, 2, True, '0'):
            with self.assertRaises(ValueError): model.coalesce((index,), **base)
        for override in ({'source_start': 7}, {'bank_bytes': 1},
                         {'max_run_bytes': 1}, {'source_start': -1}):
            with self.assertRaises(ValueError):
                model.coalesce((0,), **(base | override))
        self.assertEqual(model.coalesce((), **base), ())
        self.assertEqual(model.deduplicate((), 2), (b'', ()))


if __name__ == '__main__':
    unittest.main()

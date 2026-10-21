"""Invented host buffers test the read-only ABI client; no emulator is loaded."""
import ctypes
import unittest

from patchquest.libretro_runtime import Libretro


class Memory:
    def __init__(self):
        self.buffers = {2: ctypes.create_string_buffer(b'abcdefgh', 8),
                        3: ctypes.create_string_buffer(b'123456', 6)}
        self.calls = []

    def retro_get_memory_size(self, key):
        self.calls.append(('size', key))
        return len(self.buffers[key])

    def retro_get_memory_data(self, key):
        self.calls.append(('data', key))
        return ctypes.addressof(self.buffers[key])


class ReadOnlyMemoryTests(unittest.TestCase):
    def setUp(self):
        self.core = object.__new__(Libretro)
        self.core.loaded = True
        self.core.dll = Memory()

    def test_explicit_regions_and_exact_immutable_copy(self):
        memory = self.core.dll
        self.assertEqual(self.core.memory_size('system_ram'), 8)
        self.assertEqual(self.core.memory_size('video_ram'), 6)
        snapshot = self.core.read_memory('system_ram', 2, 3)
        self.assertIs(type(snapshot), bytes)
        self.assertEqual(snapshot, b'cde')
        self.assertEqual(self.core.read_memory('video_ram', 4, 2), b'56')
        self.assertEqual(memory.buffers[2].raw, b'abcdefgh')
        self.assertEqual(memory.buffers[3].raw, b'123456')
        memory.buffers[2][2] = b'X'
        self.assertEqual(snapshot, b'cde')
        self.assertEqual({key for _, key in memory.calls}, {2, 3})

    def test_regions_do_not_accept_arbitrary_ids_or_save_memory(self):
        for region in (0, 2, 3, True, None, [], {}, 'save_ram', 'rtc', 'rom', 'SYSTEM_RAM'):
            with self.subTest(region=region):
                with self.assertRaises(ValueError):
                    self.core.read_memory(region, 0, 1)
                with self.assertRaises(ValueError):
                    self.core.memory_size(region)
        self.assertEqual(self.core.dll.calls, [])

    def test_closed_core_cannot_access_memory(self):
        self.core.loaded = False
        with self.assertRaises(ValueError):
            self.core.memory_size('system_ram')
        with self.assertRaises(ValueError):
            self.core.read_memory('system_ram', 0, 1)
        self.assertEqual(self.core.dll.calls, [])

    def test_invalid_ranges_rejected_before_pointer_access(self):
        for offset, length in ((-1, 1), (True, 1), (0, False), (0, 0), (0, -1),
                               (0, 1.0), ('0', 1), (0, 1024*1024+1),
                               (8, 1), (7, 2), (2**100, 1)):
            with self.subTest(offset=offset, length=length):
                with self.assertRaises(ValueError):
                    self.core.read_memory('system_ram', offset, length)
        self.assertFalse(any(kind == 'data' for kind, _ in self.core.dll.calls))
        self.assertEqual(self.core.read_memory('system_ram', 0, 8), b'abcdefgh')

    def test_unavailable_and_unsupported_sizes_fail_closed(self):
        self.core.dll.retro_get_memory_size = lambda key: 0
        self.assertEqual(self.core.memory_size('system_ram'), 0)
        with self.assertRaises(ValueError):
            self.core.read_memory('system_ram', 0, 1)
        for size in (-1, True, 1.0, 16*1024*1024+1):
            self.core.dll.retro_get_memory_size = lambda key: size
            with self.subTest(size=size):
                with self.assertRaises(ValueError):
                    self.core.memory_size('system_ram')
                with self.assertRaises(ValueError):
                    self.core.read_memory('system_ram', 0, 1)
        self.assertFalse(any(kind == 'data' for kind, _ in self.core.dll.calls))

    def test_null_pointer_is_not_empty_success(self):
        self.core.dll.retro_get_memory_data = lambda key: None
        with self.assertRaises(ValueError):
            self.core.read_memory('system_ram', 0, 1)

    def test_pointer_and_size_are_refreshed_on_each_call(self):
        self.assertEqual(self.core.read_memory('system_ram', 1, 2), b'bc')
        self.core.dll.buffers[2] = ctypes.create_string_buffer(b'WXYZ', 4)
        self.assertEqual(self.core.read_memory('system_ram', 1, 2), b'XY')
        with self.assertRaises(ValueError):
            self.core.read_memory('system_ram', 4, 1)

    def test_copy_limit_boundary_with_independent_large_buffer(self):
        raw = b'x' * (1024*1024)
        self.core.dll.buffers[2] = ctypes.create_string_buffer(raw, len(raw))
        self.assertEqual(self.core.read_memory('system_ram', 0, len(raw)), raw)


if __name__ == '__main__':
    unittest.main()

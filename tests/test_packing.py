import itertools
import unittest

from _bootstrap import ROOT
from patchquest.core.packing import pack_blobs


class PackingTests(unittest.TestCase):
    def test_result_is_within_owned_regions_deterministic_and_nonmutating(self):
        blobs={'north':b'n'*7,'east':b'e'*4,'west':b'w'*3,'south':b's'*5}
        regions=[(31,40),(100,110)];before=dict(blobs)
        placed=pack_blobs(blobs,regions)
        self.assertEqual(placed,pack_blobs(dict(reversed(list(blobs.items()))),regions[::-1]))
        self.assertEqual(blobs,before)
        used=[]
        for key,start in placed.items():
            end=start+len(blobs[key]);self.assertTrue(any(a<=start<end<=z for a,z in regions))
            self.assertTrue(all(end<=a or start>=z for a,z in used));used.append((start,end))

    def test_small_cases_match_exhaustive_independent_bin_feasibility(self):
        for sizes in itertools.product(range(1,5),repeat=4):
            possible=any(sum(size for size,side in zip(sizes,bits) if side==0)<=6 and
                         sum(size for size,side in zip(sizes,bits) if side==1)<=7
                         for bits in itertools.product((0,1),repeat=4))
            blobs={str(i):b'x'*size for i,size in enumerate(sizes)}
            if possible:self.assertEqual(len(pack_blobs(blobs,[(0,6),(20,27)])),4)
            else:
                with self.assertRaises(ValueError):pack_blobs(blobs,[(0,6),(20,27)])

    def test_rejects_unowned_overlapping_unsplittable_and_unbounded_inputs(self):
        for regions in ([(0,4),(3,8)],[(4,4)],[(-1,5)]):
            with self.assertRaises(ValueError):pack_blobs({'a':b'x'},regions)
        with self.assertRaises(ValueError):pack_blobs({'a':b'x'*5},[(0,3),(10,13)])
        with self.assertRaises(ValueError):pack_blobs({'a':b''},[(0,10)])
        with self.assertRaises(ValueError):pack_blobs({'a':b'x','b':b'y'},[(0,4)],search_limit=1)
        self.assertEqual(pack_blobs({},[]),{})


if __name__=='__main__':unittest.main()

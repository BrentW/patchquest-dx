"""Invented allocation tables; no game geometry or directory data."""
import unittest
from _bootstrap import ROOT
from patchquest.storage.fat8 import agree, walk, crosslinks


class Fat8Tests(unittest.TestCase):
    def chain(self, table, start=1, **kwargs):
        return walk(table,start,cluster_count=6,sectors_per_cluster=4,**kwargs)

    def test_fragmented_chain_and_partial_tail(self):
        c=self.chain(bytes([255,4,255,0xc2,3,255]))
        self.assertEqual(c.clusters,(1,4,3))
        self.assertEqual(c.sector_counts,(4,4,2))

    def test_single_full_cluster(self):
        self.assertEqual(self.chain(bytes([255,0xc4,255,255,255,255])).sector_counts,(4,))

    def test_cycle_and_invalid_entries(self):
        for value in (1,6,0xc0,0xc5,0xfe,0xff):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.chain(bytes([255,value,255,255,255,255]))
        with self.assertRaises(ValueError):self.chain(bytes([255,4,255,255,1,255]))

    def test_explicit_terminal_profile(self):
        c=self.chain(bytes([255,0xd1,255,255,255,255]),terminal_first=0xd0)
        self.assertEqual(c.sector_counts,(2,))

    def test_profiles(self):
        for kwargs in [{'start':-1},{'start':6},{'cluster_count':0},
                       {'cluster_count':7},{'cluster_count':True},
                       {'sectors_per_cluster':0},{'sectors_per_cluster':64},
                       {'terminal_first':4}]:
            args=dict(start=1,cluster_count=6,sectors_per_cluster=4);args.update(kwargs)
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                walk(bytes([255]*6),**args)

    def test_copy_disagreement_and_immutable_result(self):
        a=bytearray([1,2]);b=bytearray(a);result=agree([a,b]);a[0]=7
        self.assertEqual(result,b'\1\2')
        for copies in [[],[b''],[b'ab',b'ac'],[b'a',b'aa'],['ab']]:
            with self.assertRaises(ValueError):agree(copies)

    def test_crosslinked_tails(self):
        table=bytes([255,4,4,255,0xc1,255])
        self.assertEqual(crosslinks({'one':self.chain(table),'two':self.chain(table,2)}),{4:('one','two')})


if __name__=='__main__':unittest.main()

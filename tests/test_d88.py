import unittest
from hashlib import sha256
from struct import pack_into
from _bootstrap import ROOT
from patchquest.storage.d88 import parse, patch_sector, HEADER
from patchquest.patches.bps import encode, apply
from patchquest.core.context import OutputPolicy
from pathlib import Path
from tempfile import TemporaryDirectory

def fixture(payload=b'Invented fixture', n=0, count=1, suffix=b''):
    data=bytearray(HEADER+16+len(payload)+len(suffix))
    data[:9]=b'SYNTHETIC'
    pack_into('<I',data,0x1c,len(data))
    pack_into('<I',data,0x20,HEADER)
    data[HEADER:HEADER+4]=bytes([0,0,7,n])
    pack_into('<H',data,HEADER+4,count)
    pack_into('<H',data,HEADER+14,len(payload))
    data[HEADER+16:]=payload+suffix
    return bytes(data)

class D88Checks(unittest.TestCase):
    def test_every_truncated_prefix_is_rejected_except_complete_disk(self):
        first=fixture(bytes(range(128)))
        second=fixture(bytes(reversed(range(128))))
        combined=first+second
        for length in range(len(combined)):
            with self.subTest(length=length):
                if length==len(first):
                    self.assertEqual(parse(combined[:length]).reconstruct(),first)
                else:
                    with self.assertRaises(ValueError): parse(combined[:length])

    def test_payload_edits_preserve_every_unselected_byte_and_other_disk(self):
        # Boundary bytes, duplicate contents and disk headers must not affect
        # selection. These are authored payloads, not disk captures.
        for size in (1,127,128,129,256,513):
            payload=bytes(i%256 for i in range(size))
            source=fixture(payload)+fixture(payload)
            image=parse(source)
            for disk in (0,1):
                sector=image.disks[disk].sectors[0]
                for relative in sorted({0,size//2,size-1}):
                    old=payload[relative:relative+1]
                    new=bytes([old[0]^0xff])
                    target=patch_sector(source,sha256(source).hexdigest(),disk,0,0,relative,old,new)
                    absolute=sector.data_offset+relative
                    self.assertEqual(target[:absolute],source[:absolute])
                    self.assertEqual(target[absolute+1:],source[absolute+1:])
                    self.assertEqual(target[absolute:absolute+1],new)
                    self.assertEqual(parse(target).disks,image.disks)
                    self.assertEqual(apply(source,encode(source,target)),target)
                    restored=patch_sector(target,sha256(target).hexdigest(),disk,0,0,relative,new,old)
                    self.assertEqual(restored,source)

    def test_chained_edits_require_current_identity_and_original_expectations(self):
        source=fixture(b'ABCDEFGH')
        first=patch_sector(source,sha256(source).hexdigest(),0,0,0,0,b'AB',b'ab')
        with self.assertRaises(ValueError):
            patch_sector(first,sha256(source).hexdigest(),0,0,0,6,b'GH',b'gh')
        # Updating the hash cannot authorize stale expected bytes in an overlap.
        with self.assertRaises(ValueError):
            patch_sector(first,sha256(first).hexdigest(),0,0,0,1,b'BC',b'bc')
        forward=patch_sector(first,sha256(first).hexdigest(),0,0,0,6,b'GH',b'gh')
        last=patch_sector(source,sha256(source).hexdigest(),0,0,0,6,b'GH',b'gh')
        reverse=patch_sector(last,sha256(last).hexdigest(),0,0,0,0,b'AB',b'ab')
        self.assertEqual(forward,reverse)
        self.assertEqual(encode(source,forward),encode(source,reverse))

    def test_multiple_sectors_with_duplicate_ids(self):
        raw=bytearray(fixture(b'First',count=2))
        second=fixture(b'Second',count=2)[HEADER:]
        raw.extend(second)
        pack_into('<I',raw,0x1c,len(raw))
        sectors=parse(raw).disks[0].sectors
        self.assertEqual(len(sectors),2)
        self.assertEqual(sectors[0].chrn,sectors[1].chrn)
        edited=patch_sector(raw,sha256(raw).hexdigest(),0,0,1,0,b'Second',b'Edited')
        self.assertEqual(edited[sectors[0].data_offset:sectors[0].data_offset+5],b'First')
        self.assertEqual(edited[sectors[1].data_offset:],b'Edited')
        raw[sectors[1].header_offset+4]=1
        with self.assertRaises(ValueError): parse(raw)
    def test_tracks_in_reverse_physical_order(self):
        raw=bytearray(fixture())
        second_offset=len(raw)
        raw.extend(fixture(b'Other track')[HEADER:])
        pack_into('<I',raw,0x1c,len(raw))
        pack_into('<I',raw,0x20,second_offset)
        pack_into('<I',raw,0x24,HEADER)
        sectors=parse(raw).disks[0].sectors
        self.assertEqual([s.header_offset for s in sectors],[second_offset,HEADER])
        self.assertEqual(parse(raw).reconstruct(),raw)
    def test_immutable_snapshots_and_input_types(self):
        raw=bytearray(fixture())
        image=parse(raw)
        raw[-1]^=1
        self.assertNotEqual(image.original,raw)
        for value in (100,'disk',None):
            with self.assertRaises(ValueError): parse(value)
        source=fixture()
        for selector in (True,0.0,'0',-1):
            with self.assertRaises(ValueError):
                patch_sector(source,sha256(source).hexdigest(),selector,0,0,0,b'I',b'X')
    def test_bps_and_exclusive_output(self):
        source=fixture()+fixture(b'Second invented disk')
        target=patch_sector(source,sha256(source).hexdigest(),1,0,0,0,b'Second',b'Edited')
        patch=encode(source,target)
        self.assertEqual(encode(source,target),patch)
        self.assertEqual(apply(source,patch),target)
        with self.assertRaises(ValueError): apply(source[:-1]+b'!',patch)
        with self.assertRaises(ValueError): apply(source,patch[:-1]+bytes([patch[-1]^1]))
        with TemporaryDirectory() as directory:
            root=Path(directory)
            original=root/'original.d88'
            original.write_bytes(source)
            policy=OutputPolicy(root/'output',inputs=(original,))
            result=policy.write_new('experimental.d88',target)
            self.assertEqual(result.read_bytes(),target)
            with self.assertRaises(FileExistsError): policy.write_new('experimental.d88',target)
            with self.assertRaises(ValueError): policy.write_new(original,target)
            self.assertEqual(original.read_bytes(),source)
    def test_lossless_opaque(self):
        raw=fixture(suffix=b'opaque trailing')
        self.assertEqual(parse(raw).reconstruct(),raw)
        self.assertEqual(len(parse(raw).disks[0].warnings),2)
    def test_multidisk(self):
        raw=fixture()+fixture(b'Other disk')
        image=parse(raw)
        self.assertEqual(len(image.disks),2)
        self.assertEqual(image.reconstruct(),raw)
    def test_out_of_order_tracks(self):
        raw=bytearray(fixture()+b'')
        pack_into('<I',raw,0x20,0)
        pack_into('<I',raw,0x28,HEADER)
        self.assertEqual(parse(raw).disks[0].sectors[0].track_slot,2)
    def test_status_preservation(self):
        raw=bytearray(fixture())
        raw[HEADER+6:HEADER+9]=bytes([0x40,0x10,0xb0])
        sector=parse(raw).disks[0].sectors[0]
        self.assertEqual((sector.density,sector.deleted,sector.status),(0x40,0x10,0xb0))
    def test_nominal_mismatch_not_repaired(self):
        raw=fixture(b'X',7)
        self.assertEqual(parse(raw).disks[0].sectors[0].size,1)
        self.assertTrue(parse(raw).disks[0].warnings)
    def test_zero_data(self):
        self.assertEqual(parse(fixture(b'')).disks[0].sectors[0].size,0)
    def test_bad_sizes(self):
        for size in (0,HEADER-1,999999):
            raw=bytearray(fixture()); pack_into('<I',raw,0x1c,size)
            with self.assertRaises(ValueError): parse(raw)
    def test_bad_tracks(self):
        for offset in (1,HEADER-1,999999):
            raw=bytearray(fixture()); pack_into('<I',raw,0x20,offset)
            with self.assertRaises(ValueError): parse(raw)
    def test_alias_rejected(self):
        raw=bytearray(fixture()); pack_into('<I',raw,0x24,HEADER)
        with self.assertRaises(ValueError): parse(raw)
    def test_truncation_and_trailing(self):
        for raw in (b'',fixture()[:-1],fixture()+b'x'):
            with self.assertRaises(ValueError): parse(raw)
    def test_bad_count(self):
        for count in (0,0x1000,65535):
            with self.assertRaises(ValueError): parse(fixture(count=count))
    def test_crossing_data(self):
        raw=bytearray(fixture()); pack_into('<H',raw,HEADER+14,65535)
        with self.assertRaises(ValueError): parse(raw)
    def test_guarded_edit(self):
        raw=fixture(); digest=sha256(raw).hexdigest()
        a=patch_sector(raw,digest,0,0,0,0,b'Invented',b'Authored')
        b=patch_sector(raw,digest,0,0,0,0,b'Invented',b'Authored')
        self.assertEqual(a,b)
        self.assertEqual(a[:HEADER+16],raw[:HEADER+16])
        self.assertEqual(a[HEADER+24:],raw[HEADER+24:])
        self.assertEqual(parse(a).disks,parse(raw).disks)
    def test_edit_rejections(self):
        raw=fixture(); digest=sha256(raw).hexdigest()
        for args in [('0'*64,0,0,0,0,b'I',b'Z'),(digest,1,0,0,0,b'I',b'Z'),(digest,0,0,0,-1,b'I',b'Z'),(digest,0,0,0,0,b'bad',b'new'),(digest,0,0,0,0,b'I',b'ZZ'),(digest,0,0,0,100,b'I',b'Z')]:
            with self.assertRaises(ValueError): patch_sector(raw,*args)

if __name__=='__main__': unittest.main()

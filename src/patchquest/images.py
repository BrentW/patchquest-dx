"""Bounded PNG/JPEG screenshot inspection using the standard library.

Checks container structure and dimensions; not a general-purpose image decoder.
Uploaded bytes are retained privately and never interpreted as instructions.
"""
import struct
import zlib

MAX_BYTES=10*1024*1024


def dimensions(width,height):
    if not (0<width<=8192 and 0<height<=8192 and width*height<=16777216):
        raise ValueError('Screenshot dimensions exceed limits')


def inspect(data):
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES:
        raise ValueError('Expected a PNG/JPEG screenshot up to 10 MiB')
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        pos=8; width=height=0; has_data=False; first=True
        while pos+12<=len(data):
            length=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8]
            end=pos+12+length
            if end>len(data):raise ValueError('Truncated PNG')
            body=data[pos+8:pos+8+length]
            if zlib.crc32(kind+body)&0xffffffff!=struct.unpack('>I',data[end-4:end])[0]:raise ValueError('PNG checksum mismatch')
            if first and kind!=b'IHDR':raise ValueError('PNG must start with IHDR')
            if kind==b'IHDR':
                if not first or length!=13:raise ValueError('Invalid PNG header')
                width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',body)
                dimensions(width,height)
                if color not in (0,2,3,4,6) or depth not in (1,2,4,8,16) or compression or filtering or interlace not in (0,1):raise ValueError('Unsupported PNG header')
            if kind==b'IDAT':has_data=True
            if kind==b'IEND':
                if length or end!=len(data) or not has_data:raise ValueError('Invalid PNG ending')
                return {'mime':'image/png','width':width,'height':height}
            first=False;pos=end
        raise ValueError('Incomplete PNG')
    if data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9'):
        pos=2;width=height=0
        while pos<len(data)-2:
            if data[pos]!=255:raise ValueError('Invalid JPEG marker')
            while pos<len(data) and data[pos]==255:pos+=1
            if pos>=len(data):break
            marker=data[pos];pos+=1
            if marker in (0xD8,0xD9,0x01) or 0xD0<=marker<=0xD7:continue
            if pos+2>len(data):break
            length=int.from_bytes(data[pos:pos+2],'big')
            if length<2 or pos+length>len(data):raise ValueError('Truncated JPEG segment')
            if marker in (0xC0,0xC1,0xC2):
                if length<8:raise ValueError('Invalid JPEG frame')
                height=int.from_bytes(data[pos+3:pos+5],'big');width=int.from_bytes(data[pos+5:pos+7],'big');dimensions(width,height)
            if marker==0xDA:
                if not width:raise ValueError('JPEG lacks supported frame')
                return {'mime':'image/jpeg','width':width,'height':height}
            pos+=length
    raise ValueError('Unsupported or incomplete screenshot')

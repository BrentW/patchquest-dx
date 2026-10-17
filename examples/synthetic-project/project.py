"""Independently invented bytes and text; not a playable game or extracted fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def run(platform, workspace):
    platform, workspace = Path(platform).resolve(), Path(workspace).resolve()
    sys.path.insert(0, str(platform / 'src'))
    from patchquest.core.context import ProjectContext
    from patchquest.core.edits import build, extract
    from patchquest.consoles.snes.checksum import update
    from patchquest.patches import bps
    from patchquest.typography.layout import Font, layout
    from patchquest.typography.font import DEFAULT_FONT
    from patchquest.consoles.snes.tiles import png_gray

    # A new, fictional one-byte alphabet; no commercial encoding is used.
    alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ!'
    encode = {c: 0x91 + i for i,c in enumerate(alphabet)}
    before = bytes(encode[c] for c in 'LANTERN')
    after = bytes(encode[c] for c in 'BEACON!')
    source = bytearray(0x8000)
    source[0x120:0x122] = (0x242).to_bytes(2, 'little')  # Toy file-offset pointer.
    source[0x240:0x24a] = b'\x7e\x7d' + before + b'\x00'
    source[0x7fc0:0x7fd5] = b'SYNTHETIC SAMPLE'.ljust(21,b' ')
    source[0x7fd5] = 0x20
    source[0x7fd7] = 5
    source[0x7ffc:0x7ffe] = b'\x00\x80'
    source = update(bytes(source),0x7fc0)
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace/'roms').mkdir()
    (workspace/'roms/source.sfc').write_bytes(source)
    manifest = {'schema_version':1,'platform_api':1,'project_id':'synthetic-sample',
                'source':{'path':'roms/source.sfc','sha256':hashlib.sha256(source).hexdigest()},
                'resources':{},'output_directory':'output'}
    (workspace/'project.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    context = ProjectContext.load(workspace/'project.json')
    original = context.read_source()
    offset = int.from_bytes(original[0x120:0x122],'little')
    records = extract(original,[{'offset':hex(offset),'length':7}],{f'{v:02X}':k for k,v in encode.items()})
    assert records[0]['text']=='LANTERN'
    edits = [{'offset':hex(offset),'expected_hex':before.hex(),'replacement_hex':after.hex()}]
    target = update(build(original,edits),0x7fc0)
    assert update(build(original,edits),0x7fc0)==target
    patch = bps.encode(original,target)
    assert bps.apply(original,patch)==target
    assert target[0x240:0x242]==original[0x240:0x242] and target[0x249]==0
    allowed = set(range(offset,offset+7)) | set(range(0x7fdc,0x7fe0))
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(original,target)))
    block = layout(Font(),'The beacon shines.',144,40)
    context.output.write_new('sample.sfc',target)
    context.output.write_new('sample.bps',patch)
    context.output.write_new('typography.png',png_gray([[255*v for v in row] for row in block['raster']],3))
    for name in ('LICENSE-CC-BY-3.0.txt','ATTRIBUTION.md','PROVENANCE.md'):
        context.output.write_new(name,DEFAULT_FONT.with_name(name).read_bytes())
    context.output.write_new('LICENSE-APACHE-2.0.txt',(platform/'LICENSE').read_bytes())
    context.output.write_new('LICENSE-SCOPE.md',(
        '# Synthetic example output licenses\n\n'
        'typography.png contains Quest Pixel font material under CC BY 3.0 Unported. '
        'See [terms](LICENSE-CC-BY-3.0.txt), [attribution](ATTRIBUTION.md) and [provenance](PROVENANCE.md).\n\n'
        'The invented sample bytes, patch, project-authored text and validation metadata use '
        '[Apache-2.0](LICENSE-APACHE-2.0.txt). This is not a playable ROM or a license to commercial game content.\n'
    ).encode())
    report = {'synthetic':True,'playable':False,'source_sha256':hashlib.sha256(source).hexdigest(),
              'target_sha256':hashlib.sha256(target).hexdigest(),'patch_sha256':hashlib.sha256(patch).hexdigest(),
              'reproducible':True,'patch_reconstruction':True,'typography_license':'CC-BY-3.0'}
    context.output.write_new('validation.json',(json.dumps(report,indent=2)+'\n').encode())
    assert context.read_source()==original
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',type=Path,required=True)
    parser.add_argument('--workspace',type=Path,required=True,help='A fresh private directory')
    args=parser.parse_args()
    print(json.dumps(run(args.platform,args.workspace),indent=2))

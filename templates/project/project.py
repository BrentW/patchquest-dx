"""Private runner template. Recipes are explicit data owned by this project."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform',type=Path,required=True)
    parser.add_argument('--name',default='test',help='Fresh output basename')
    args=parser.parse_args()
    if not args.name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.name):
        raise ValueError('Use a simple output basename')
    sys.path.insert(0,str(args.platform.resolve()/'src'))
    from patchquest.core.context import ProjectContext
    from patchquest.core.edits import build
    from patchquest.consoles.snes.checksum import update
    from patchquest.patches import bps
    context=ProjectContext.load(Path(__file__).with_name('project.json'))
    source=context.read_source()
    recipe=json.loads(context.resource('recipe').read_text(encoding='utf-8'))
    if not recipe['edits']:
        raise ValueError('Provide validated expected-byte edits before building')
    target=build(source,recipe['edits'])
    if recipe.get('snes_header_offset') is not None:
        target=update(target,int(recipe['snes_header_offset'],0),recipe['copier_header_bytes'])
    patch=bps.encode(source,target)
    if bps.apply(source,patch)!=target:
        raise ValueError('BPS reconstruction mismatch')
    context.output.write_new(args.name+'.sfc',target)
    context.output.write_new(args.name+'.bps',patch)
    if context.read_source()!=source:
        raise ValueError('Original changed')
    print('Build and BPS reconstruction passed; emulator and hardware testing remain pending.')


if __name__=='__main__':
    main()

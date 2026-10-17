import hashlib
import importlib.util
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from _bootstrap import ROOT
from patchquest.config import doctor, load_config
from patchquest.core.context import OutputPolicy, ProjectContext
from patchquest.core.edits import extract
from patchquest.consoles.snes.checksum import update
from patchquest.consoles.snes.inspection import mirrored_sum
from patchquest.consoles.snes.tiles import encode_tile, decode_tile
from patchquest.consoles.cpu65816 import disassemble
from patchquest.typography.font import DEFAULT_FONT, load_font, bounds, build as specimen, DEFAULT_SPECIMEN, appearance_approval
from patchquest.typography.layout import Font, layout, resolve_runs


class ContextTests(unittest.TestCase):
    def test_output_roots_aliases_traversal_and_exclusive_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'original';source.write_bytes(b'immutable')
            policy=OutputPolicy(root/'output',(source,))
            for path in ('../escape',source,root/'elsewhere'):
                with self.assertRaises(ValueError):policy.write_new(path,b'bad')
            policy.write_new('result',b'one')
            with self.assertRaises(FileExistsError):policy.write_new('result',b'two')
            with self.assertRaises(ValueError):OutputPolicy(root,(source,)).write_new(source,b'bad')
            self.assertEqual(source.read_bytes(),b'immutable')

    def test_symlink_escape(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'output').mkdir();(root/'outside').mkdir()
            try:(root/'output/link').symlink_to(root/'outside',target_is_directory=True)
            except OSError as error:
                if sys.platform!='win32':self.skipTest('OS does not permit test symlinks: '+type(error).__name__)
                environment=os.environ.copy()
                environment.update(PATCHQUEST_TEST_LINK=str(root/'output/link'),PATCHQUEST_TEST_TARGET=str(root/'outside'))
                command='New-Item -ItemType Junction -Path $env:PATCHQUEST_TEST_LINK -Target $env:PATCHQUEST_TEST_TARGET -ErrorAction Stop | Out-Null'
                subprocess.run(['powershell','-NoProfile','-Command',command],env=environment,check=True,capture_output=True)
            with self.assertRaises(ValueError):OutputPolicy(root/'output').write_new('link/leak',b'bad')

    def test_manifest_paths_are_not_cwd_dependent(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';source.write_bytes(b'fiction')
            data={'schema_version':1,'platform_api':1,'project_id':'example',
                  'source':{'path':'source','sha256':hashlib.sha256(b'fiction').hexdigest()},
                  'resources':{'notes':'docs'},'output_directory':'out'}
            path=root/'project.json'
            def load(changes):
                path.write_text(json.dumps(data|changes));return ProjectContext.load(path)
            context=load({})
            self.assertEqual(context.read_source(),b'fiction')
            self.assertEqual(context.resource('notes'),root/'docs')
            for changes in ({'platform_api':9},{'output_directory':'.'},{'output_directory':'../escape'},
                            {'resources':{'notes':'../escape'}},{'resources':{'notes':'out/data'}}):
                with self.assertRaises(ValueError):load(changes)
            load({});source.write_bytes(b'changed')
            with self.assertRaises(ValueError):ProjectContext.load(path).read_source()

    def test_no_configuration_or_project_required(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            self.assertEqual(load_config(root)['projects'],{})
            self.assertEqual(doctor(root)['registered_projects'],0)
            self.assertFalse((root/'.local').exists())
            path=root/'.local/config/local.json';path.parent.mkdir(parents=True)
            for data in ({'schema_version':1},{'unknown':True},{'projects':[]},{'emulators':{'bad':None}}):
                path.write_text(json.dumps(data))
                with self.assertRaises(ValueError):load_config(root)


class PrimitiveTests(unittest.TestCase):
    def test_linear_disassembly_tracks_explicit_width_changes(self):
        code=bytes.fromhex('e2 30 a9 51 c2 20 a9 34 12 ea')
        lines=list(disassemble(code,0,len(code)))
        self.assertEqual(len(lines),5)
        self.assertIn('LDA #$51',lines[1]);self.assertIn('LDA #$1234',lines[3])
        with self.assertRaises(ValueError):list(disassemble(b'\xa9',0,1))

    def test_extraction_preserves_unknown_bytes(self):
        record=extract(b'\x99\xfe\x00',[{'offset':'0','length':3}],{'99':'X'})[0]
        self.assertEqual(record['text'],'X<FE><00>')
        self.assertEqual(bytes.fromhex(record['original_hex']),b'\x99\xfe\x00')
        with self.assertRaises(ValueError):extract(b'one',[{'offset':'2','length':2}])

    def test_checksum_changes_only_explicit_header_fields(self):
        source=bytes((i*37+11)%256 for i in range(0x18000))
        target=update(source,0x7fc0)
        value=int.from_bytes(target[0x7fde:0x7fe0],'little')
        self.assertEqual(value,mirrored_sum(target))
        self.assertEqual(target[:0x7fdc],source[:0x7fdc]);self.assertEqual(target[0x7fe0:],source[0x7fe0:])
        self.assertEqual(update(b'x'*512+source,0x7fc0,512),b'x'*512+target)
        with self.assertRaises(ValueError):update(source,4)

    def test_all_tile_bit_depths(self):
        for bits in (1,2,4,8):
            tile=[[(x+3*y)%2**bits for x in range(8)] for y in range(8)]
            self.assertEqual(decode_tile(encode_tile(tile,bits),bits),tile)

    def test_approved_artwork_and_metrics(self):
        approval=json.loads(DEFAULT_FONT.with_name('approval.json').read_text())
        self.assertEqual(hashlib.sha256(DEFAULT_FONT.read_bytes()).hexdigest(),approval['glyph_source_sha256'])
        _,glyphs=load_font(DEFAULT_FONT);self.assertEqual(len(glyphs),112)
        self.assertEqual(Font().metrics(),json.loads(DEFAULT_FONT.with_name('compact-metrics.json').read_text()))
        self.assertLess(Font().measure('iii')['advance'],Font().measure('WWW')['advance'])

    def test_alignment_controls_and_overflow(self):
        font=Font();block=layout(font,'Beacon\nWait here.',117,44,padding=(6,5,6,5),align='center')
        left,top,right,bottom=block['ink']
        self.assertGreaterEqual(left,6);self.assertLessEqual(right,111)
        self.assertGreaterEqual(top,5);self.assertLessEqual(bottom,39)
        for line in block['lines']:
            x0,_,x1,_=line['ink'];self.assertLessEqual(abs((line['x']+x0)-(117-line['x']-x1)),1)
        text,events=resolve_runs([{'text':'Hi '},{'variable':'traveler'},{'control':{'wait':7}},{'break':True},{'text':'Rest.'}],{'traveler':'Mira'})
        self.assertEqual(text,'Hi Mira\nRest.');self.assertEqual(events,[{'position':7,'control':{'wait':7}}])
        with self.assertRaises(ValueError):layout(font,'Unbreakable',8,12)
        with self.assertRaises(ValueError):layout(font,'A\nB\nC',40,8)

    def test_mixed_case_font_box_baselines_and_descenders(self):
        font=Font()
        samples=['Beacon', 'Gypsy', 'jumpy', 'WILL', "I'll wait."]
        blocks=[layout(font,s,120,20,padding=(4,2,4,2),vertical_metrics='font') for s in samples]
        self.assertEqual(len({b['lines'][0]['baseline'] for b in blocks}),1)
        for text,block in zip(samples,blocks):
            self.assertEqual(block['lines'][0]['text'],text)
            line=block['lines'][0];pen=line['x']
            expected=[[0]*120 for _ in range(20)]
            for char in text:
                glyph=font.glyphs[char]
                for y,row in enumerate(glyph['pixels']):
                    for x,bit in enumerate(row):
                        if bit:expected[line['y']+y][pen+x]=1
                pen+=glyph['advance']
            self.assertEqual(block['raster'],expected)
        self.assertGreater(font.glyphs['g']['ink'][3],font.baseline+1)
        lines=layout(font,'Bridge\nBeyond',80,32,vertical_metrics='font')['lines']
        self.assertEqual(lines[1]['baseline']-lines[0]['baseline'],font.line_step)
        with self.assertRaises(ValueError):layout(font,'jumpy',80,7,padding=(0,0,0,0),vertical_metrics='font')
        with self.assertRaises(ValueError):layout(font,'A',80,20,vertical_metrics='guess')

    def test_specimen_has_no_rom_dependency(self):
        with tempfile.TemporaryDirectory() as folder:
            policy=OutputPolicy(Path(folder))
            result=specimen(DEFAULT_FONT,DEFAULT_SPECIMEN,Path(folder)/'review',policy)
            self.assertEqual(result['glyph_count'],112)
            self.assertEqual(result['appearance_approval'],{'status':'approved','source_hash_matches':True})
            self.assertEqual(result['font_license'],'CC-BY-3.0')
            output=Path(folder)/'review'
            for name in ('LICENSE-CC-BY-3.0.txt','ATTRIBUTION.md','PROVENANCE.md'):
                self.assertEqual((output/name).read_bytes(),DEFAULT_FONT.with_name(name).read_bytes())
            self.assertEqual((output/'LICENSE-APACHE-2.0.txt').read_bytes(),(ROOT/'LICENSE').read_bytes())
            self.assertEqual(set(result['artifacts']),{p.name for p in output.iterdir()}-{'validation.json'})

    def test_changed_font_cannot_inherit_stale_approval_or_quest_license(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);font=root/'glyphs.json'
            self.assertEqual(appearance_approval(font)['status'],'unverified')
            data=json.loads(DEFAULT_FONT.read_text())
            data['glyphs']['0041']=data['glyphs']['0042']
            font.write_text(json.dumps(data),encoding='utf-8')
            shutil.copyfile(DEFAULT_FONT.with_name('approval.json'),root/'approval.json')
            self.assertEqual(appearance_approval(font),{'status':'unverified','source_hash_matches':False})
            result=specimen(font,DEFAULT_SPECIMEN,root/'changed',OutputPolicy(root))
            self.assertEqual(result['appearance_approval']['status'],'unverified')
            self.assertEqual(result['font_license'],'not determined for this input')
            self.assertFalse((root/'changed/LICENSE-CC-BY-3.0.txt').exists())


class EndToEndTests(unittest.TestCase):
    def test_cli_and_template_use_explicit_private_inputs(self):
        with tempfile.TemporaryDirectory(prefix='quest adapter ') as folder:
            root=Path(folder);source=root/'source.sfc';source.write_bytes(b'abcd')
            recipe={'source_sha256':hashlib.sha256(b'abcd').hexdigest(),
                    'edits':[{'offset':'1','expected_hex':'62','replacement_hex':'78'}],
                    'ranges':[{'offset':'0','length':4}],'table':{'61':'A'}}
            manifest=root/'recipe.json';manifest.write_text(json.dumps(recipe))
            out=root/'out'
            def cli(*args):
                return subprocess.run([sys.executable,'-B',str(ROOT/'tools/patchquest.py'),*map(str,args)],cwd=root,check=True,capture_output=True)
            cli('extract',source,manifest,out/'text.json','--output-root',out)
            self.assertEqual(json.loads((out/'text.json').read_text())[0]['original_hex'],'61626364')
            cli('insert',source,manifest,out/'changed.sfc','--output-root',out)
            cli('bps-create',source,out/'changed.sfc',out/'change.bps','--output-root',out)
            cli('bps-apply',source,out/'change.bps',out/'restored.sfc','--output-root',out)
            self.assertEqual((out/'restored.sfc').read_bytes(),b'axcd')
            project=root/'project';shutil.copytree(ROOT/'templates/project',project)
            data=json.loads((project/'project.example.json').read_text())
            data['source']={'path':str(source),'sha256':recipe['source_sha256']}
            (project/'project.json').write_text(json.dumps(data))
            (project/'data/recipe.json').write_text(json.dumps({'edits':recipe['edits'],'snes_header_offset':None}))
            subprocess.run([sys.executable,'-B',str(project/'project.py'),'--platform',str(ROOT)],cwd=root,check=True,capture_output=True)
            self.assertEqual((project/'output/test.sfc').read_bytes(),b'axcd')
            self.assertEqual(source.read_bytes(),b'abcd')

    def test_external_and_local_placement_from_unrelated_cwd(self):
        with tempfile.TemporaryDirectory(prefix='quest sample ') as folder:
            root=Path(folder);results=[]
            for workspace in (root/'external project',root/'.local/projects/example'):
                subprocess.run([sys.executable,'-B',str(ROOT/'examples/synthetic-project/project.py'),
                                '--platform',str(ROOT),'--workspace',str(workspace)],cwd=root,check=True,capture_output=True)
                subprocess.run([sys.executable,'-B',str(ROOT/'tools/patchquest.py'),'project-check',str(workspace/'project.json')],cwd=root,check=True,capture_output=True)
                results.append({p.name:p.read_bytes() for p in (workspace/'output').iterdir()})
                self.assertEqual(results[-1]['LICENSE-CC-BY-3.0.txt'],DEFAULT_FONT.with_name('LICENSE-CC-BY-3.0.txt').read_bytes())
                self.assertEqual(json.loads(results[-1]['validation.json'])['typography_license'],'CC-BY-3.0')
            self.assertEqual(results[0],results[1])


if __name__=='__main__':unittest.main()

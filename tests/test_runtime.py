"""Invented RGB frames only. These tests never claim emulator execution."""
import copy,ctypes,json,tempfile,time,unittest
from pathlib import Path
from _bootstrap import ROOT
from patchquest.runtime import Frame,run,register,reports,scenario_data,sha
from patchquest.state import Store
from patchquest.state_api import execute,READ_ACTIONS,WRITE_ACTIONS
from patchquest.images import inspect
from patchquest.libretro_runtime import Libretro,unpack_pixels
from test_state import project,invented


class Fake:
    def __init__(self,delay=0):self.n=0;self.delay=delay;self.closed=False
    def describe(self):return {'kind':'synthetic','name':'Invented color grid','sha256':'1'*64,'options':{}}
    def load(self,rom,work):self.rom=rom
    def step(self,buttons):
        self.n+=1
        if self.delay:time.sleep(self.delay)
        return Frame(4,2,bytes(([255,0,0] if 'Down' in buttons else [0,0,255])*8))
    def restore(self,state):self.state=state
    def load_save_ram(self,raw):self.sram=raw
    def close(self):self.closed=True


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.store=Store(project(self.root));self.store.put(invented('greeting'),0)
        self.snapshot=self.store.snapshot()['sha256'];self.rom=self.store.context.output.write_new('invented.bin',b'not a ROM')
        self.store.build(dict(id='invented',snapshot=self.snapshot,status='validated',artifacts={'rom':str(self.rom)}),0)
        self.s=dict(schema=1,id='menu-move',snapshot=self.snapshot,rom_sha256=sha(self.rom.read_bytes()),records={'greeting':1},initial={'kind':'cold_boot'},timeout_seconds=2,
          steps=[dict(frames=2,capture='before',assertions=[dict(label='Known blue initial state',kind='color_count',rect=[0,0,4,2],color=[0,0,255],minimum=8)]),
                 dict(frames=1,buttons=['Down'],capture='after',assertions=[dict(label='Selection changes',kind='difference',capture='before',rect=[0,0,4,2],minimum=8)])])

    def test_sequence_and_binding(self):
        adapter=Fake();report=run(self.store,'invented',self.s,adapter,'runtime-one')
        self.assertEqual(report['status'],'passed');self.assertEqual(report['level'],'synthetic');self.assertTrue(adapter.closed)
        self.assertEqual(report['frames'],3);self.assertEqual(report['captures'][1]['frame'],3)
        self.assertEqual(inspect((self.store.context.output.root/'runtime-one/after.png').read_bytes())['width'],4)
        register(self.store,'runtime-one');self.assertEqual(len(self.store.attachments()),2)
        self.assertEqual(execute(self.store,'runtime-reports',{'key':'greeting'})[0]['current'],True)
        self.assertIn('runtime-reports',READ_ACTIONS);self.assertNotIn('runtime-reports',WRITE_ACTIONS)
        self.assertEqual(self.store.record_evidence('greeting'),[])
        self.assertEqual(self.store.snapshot()['sha256'],self.snapshot)
        register(self.store,'runtime-one');self.assertEqual(len(reports(self.store)),1)

    def test_human_correction_stales_report_and_is_untouched(self):
        run(self.store,'invented',self.s,Fake(),'evidence');register(self.store,'evidence')
        data=invented('greeting');data['target']='Please stay.';self.store.put(data,1,role='human')
        self.assertFalse(reports(self.store)[0]['current']);self.assertTrue(self.store.get('greeting')['human_corrected'])
        self.assertEqual(self.store.get('greeting')['target'],'Please stay.')

    def test_failed_navigation_is_saved_without_approval(self):
        self.s['steps'][1]['buttons']=[]
        report=run(self.store,'invented',self.s,Fake(),'failed');self.assertEqual(report['status'],'failed')
        self.assertFalse(report['human_accepted']);self.assertFalse(report['assertions'][-1]['passed'])
        register(self.store,'failed');self.assertEqual(reports(self.store)[0]['status'],'failed')

    def test_wrong_rom_snapshot_revision_and_destination(self):
        for key,value in [('rom_sha256','0'*64),('snapshot','0'*64),('records',{'greeting':2})]:
            with self.subTest(key=key):
                data=copy.deepcopy(self.s);data[key]=value
                with self.assertRaises(ValueError):run(self.store,'invented',data,Fake(),'bad')
        with self.assertRaises(ValueError):run(self.store,'invented',self.s,Fake(),'../outside')
        run(self.store,'invented',self.s,Fake(),'unique')
        with self.assertRaises(FileExistsError):run(self.store,'invented',self.s,Fake(),'unique')

    def test_tampered_captures_and_build_rejected(self):
        run(self.store,'invented',self.s,Fake(),'run')
        (self.store.context.output.root/'run/after.png').write_bytes(b'changed')
        with self.assertRaises(ValueError):register(self.store,'run')
        self.assertEqual(self.store.attachments(),[])
        self.rom.write_bytes(b'changed')
        with self.assertRaises(ValueError):register(self.store,'run')

    def test_scenario_and_configuration_provenance_tampering_rejected(self):
        for name,field,value in [('kind','level','automated_runtime'),('config','configuration_sha256','0'*64),('approval','human_accepted',True)]:
            run(self.store,'invented',self.s,Fake(),name)
            p=self.store.context.output.root/name/'runtime.json';data=json.loads(p.read_bytes());data[field]=value;p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):register(self.store,name)
        run(self.store,'invented',self.s,Fake(),'changed-scenario')
        p=self.store.context.output.root/'changed-scenario/scenario.json';data=json.loads(p.read_bytes());data['steps'][0]['frames']+=1;p.write_text(json.dumps(data))
        with self.assertRaises(ValueError):register(self.store,'changed-scenario')

    def test_limits_and_bad_regions(self):
        for change in [dict(frames=0),dict(frames=1,buttons=['not a key']),dict(frames=1,capture='../escape'),dict(frames=1,command='execute')]:
            s=copy.deepcopy(self.s);s['steps'][0]=change
            with self.assertRaises(ValueError):scenario_data(s)
        self.s['steps'][0]['assertions'][0]['rect']=[3,0,2,2]
        report=run(self.store,'invented',self.s,Fake(),'bad-region');self.assertEqual(report['status'],'failed')

    def test_state_requires_same_emulator_and_rom(self):
        state=self.root/'state.bin';state.write_bytes(b'invented state')
        self.s['initial']=dict(kind='state',path='state.bin',sha256=sha(state.read_bytes()),rom_sha256=self.s['rom_sha256'],emulator_sha256='2'*64)
        report=run(self.store,'invented',self.s,Fake(),'bad-state');self.assertEqual(report['status'],'failed')
        self.s['initial']['emulator_sha256']='1'*64;adapter=Fake()
        self.assertEqual(run(self.store,'invented',self.s,adapter,'good-state')['status'],'passed')
        self.assertEqual(adapter.state,state.read_bytes())

    def test_timeout_closes_adapter(self):
        self.s['timeout_seconds']=1;adapter=Fake(.6)
        report=run(self.store,'invented',self.s,adapter,'timeout');self.assertEqual(report['status'],'failed');self.assertTrue(adapter.closed)
        self.assertEqual(report['error']['type'],'TimeoutError')

    def test_sram_boot_is_not_state_restore_and_checks_provenance(self):
        save=self.root/'new-test.srm';save.write_bytes(b'invented battery save')
        self.s['initial']=dict(kind='sram',path=save.name,sha256=sha(save.read_bytes()),rom_sha256=self.s['rom_sha256'],emulator_sha256='1'*64)
        adapter=Fake();report=run(self.store,'invented',self.s,adapter,'battery')
        self.assertEqual(report['status'],'passed');self.assertEqual(adapter.sram,save.read_bytes());self.assertFalse(hasattr(adapter,'state'))
        for field in ('sha256','rom_sha256','emulator_sha256'):
            s=copy.deepcopy(self.s);s['initial'][field]='0'*64;adapter=Fake()
            self.assertEqual(run(self.store,'invented',s,adapter,'wrong-'+field)['status'],'failed')
            self.assertFalse(hasattr(adapter,'sram'))
        self.s['initial']['path']='../escape.srm'
        self.assertEqual(run(self.store,'invented',self.s,Fake(),'escape-save')['status'],'failed')

    def test_battery_memory_copy_is_exact_bounded_and_before_first_frame(self):
        buffer=ctypes.create_string_buffer(b'ABCD',4);calls=[]
        class Memory:
            def retro_get_memory_size(self,key):calls.append(key);return 4
            def retro_get_memory_data(self,key):calls.append(key);return ctypes.addressof(buffer)
        adapter=object.__new__(Libretro);adapter.loaded=True;adapter.frames=0;adapter.dll=Memory()
        self.assertEqual(adapter.save_ram(),b'ABCD');adapter.load_save_ram(b'WXYZ')
        self.assertEqual(buffer.raw,b'WXYZ');self.assertEqual(adapter.initial_save['sha256'],sha(b'WXYZ'));self.assertEqual(set(calls),{0})
        with self.assertRaises(ValueError):adapter.load_save_ram(b'bad')
        adapter.frames=1
        with self.assertRaises(ValueError):adapter.load_save_ram(b'1234')
        self.assertEqual(buffer.raw,b'WXYZ');adapter.loaded=False
        with self.assertRaises(ValueError):adapter.save_ram()
        adapter.loaded=True
        for size in (0,16*1024*1024+1):
            adapter.dll.retro_get_memory_size=lambda key:size
            with self.assertRaises(ValueError):adapter.save_ram()
        adapter.dll.retro_get_memory_size=lambda key:4;adapter.dll.retro_get_memory_data=lambda key:None
        with self.assertRaises(ValueError):adapter.save_ram()

    def test_last_frame_cannot_exceed_timeout_or_compare_itself(self):
        self.s['timeout_seconds']=1;self.s['steps']=self.s['steps'][:1];self.s['steps'][0]['frames']=1
        result=run(self.store,'invented',self.s,Fake(1.05),'late-last-frame')
        self.assertEqual(result['status'],'failed');self.assertEqual(result['frames'],1)
        self.s['steps'][0]['assertions']=[dict(kind='difference',label='Not independent',capture='before',rect=[0,0,4,2],maximum=0)]
        with self.assertRaises(ValueError):scenario_data(self.s)

    def test_core_notifications_do_not_claim_unimplemented_callbacks(self):
        # Exercise the public ABI dispatcher without loading any native library.
        adapter=object.__new__(Libretro);adapter.error=None
        supports_no_game=ctypes.c_bool(True)
        self.assertTrue(adapter.environment(18,ctypes.byref(supports_no_game)))
        self.assertIsNone(adapter.error)
        self.assertFalse(adapter.environment(21,None))
        directory=ctypes.c_char_p()
        self.assertFalse(adapter.environment(9,ctypes.byref(directory)))
        self.assertIsNone(adapter.error)
        adapter.work_bytes=b'/invented/isolated';self.assertTrue(adapter.environment(9,ctypes.byref(directory)))
        self.assertEqual(directory.value,b'/invented/isolated')
        self.assertTrue(adapter.environment(7,None));self.assertIn('shutdown',adapter.error)

    def test_software_pixel_formats_pitch_and_duplicate_boundaries(self):
        red=bytes([255,0,0]);green=bytes([0,255,0]);blue=bytes([0,0,255])
        self.assertEqual(unpack_pixels(b'\x00\x7c\xe0\x03\x1f\x00xx',3,1,8,0).rgb,red+green+blue)
        self.assertEqual(unpack_pixels(b'\x00\xf8\xe0\x07\x1f\x00xx',3,1,8,2).rgb,red+green+blue)
        self.assertEqual(unpack_pixels(b'\x00\x00\xff\x00\x00\xff\x00\x00\xff\x00\x00\x00',3,1,12,1).rgb,red+green+blue)
        with self.assertRaises(ValueError):unpack_pixels(b'xx',2,1,2,2)
        with self.assertRaises(ValueError):unpack_pixels(b'xx',1,1,2,3)

if __name__=='__main__':unittest.main()

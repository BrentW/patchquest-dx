"""Invented captures and claims only; no real game or emulator evidence."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from test_runtime import Fake
from patchquest import screenshot_selection as s
from patchquest.runtime import run, register, sha
from patchquest.state import Store, Conflict, canonical
from patchquest.state_api import execute
from patchquest.studio import StudioServer


def content(**changes):
    return dict(dict(caption='Invented menu spacing comparison.',alt_text='A tiny invented color grid.',
                     spoiler='unknown',build_label='Test build one',capture_kind='unknown',capture_date=''),**changes)


class ScreenshotSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(project(self.root))
        self.store.put(invented('greeting'),0,role='human')
        self.before=self.store.get('greeting');self.snapshot=self.store.snapshot()['sha256']
        self.rom=self.store.context.output.write_new('invented.fixture',b'fictional build')
        self.store.build(dict(id='PRIVATE BUILD',snapshot=self.snapshot,status='validated',
                             artifacts={'rom':str(self.rom)},summary='PRIVATE BUILD LOG'),0)
        self.image=self.store.upload(PIXEL,dict(description='PRIVATE CAPTURE DESCRIPTION',
                                                build_id='PRIVATE BUILD',record_ids=['greeting'],scene='PRIVATE SCENE'))

    def tearDown(self):
        self.assertEqual(self.store.get('greeting'),self.before)
        self.assertEqual(self.store.snapshot()['sha256'],self.snapshot)

    def draft(self, image=None, report='', capture='', data=None, **params):
        digest=(image or self.image)['digest']
        context=s.context(self.store,digest,report,capture)
        return s.put(self.store,digest,context['token'],data or content(),runtime_report=report,
                     runtime_capture=capture,private_notes='PRIVATE EDITOR NOTES',**dict({'expected':0},**params))

    def select(self,item):
        item=s.review(self.store,item['id'],item['revision'],item['review_token'],actor='PRIVATE REVIEWER')
        return s.select(self.store,item['id'],item['revision'],True)

    def attachment_data(self):
        return {key:self.image[key] for key in
                ('description','record_ids','build_id','issue_ids','scene','resource','association')}

    def runtime(self, *, status='passed', actual_shape=False, duplicate=False):
        scenario=dict(schema=1,id='invented-run',snapshot=self.snapshot,rom_sha256=sha(self.rom.read_bytes()),
                      records={'greeting':1},timeout_seconds=2,steps=[dict(frames=1,capture='blue',assertions=[
                          dict(label='Invented blue area',kind='color_count',rect=[0,0,4,2],
                               color=[0,0,255] if status=='passed' else [255,0,0],minimum=8)])])
        if duplicate:scenario['steps'].append(dict(frames=1,capture='same'))
        report=run(self.store,'PRIVATE BUILD',scenario,Fake(),'run')
        if actual_shape:
            # Parser coverage only. This synthetic fixture is never offered as
            # real runtime evidence; the real-shape branch must remain tested.
            report['emulator']['kind']='actual_emulator';report['level']='automated_runtime'
            report['configuration_sha256']=sha(canonical(report['emulator']).encode())
            (self.rom.parent/'run/runtime.json').write_text(canonical(report),encoding='utf8')
        registered=register(self.store,'run')
        image=next(a for a in self.store.attachments() if a['digest']==registered['captures'][0]['digest'])
        return image,registered

    def test_drafts_review_selection_and_exact_allowlist(self):
        a=self.draft();self.assertEqual(s.preview(self.store)['items'],[])
        with self.assertRaises(Conflict):s.select(self.store,a['id'],1,True)
        self.select(a)
        exported=s.preview(self.store)
        self.assertNotIn('PRIVATE',json.dumps(exported))
        self.assertNotIn(str(self.root),json.dumps(exported))
        self.assertEqual(set(exported),{'schema_version','report_type','selection_revision','publication_approved',
                                        'release_approved','images_included','items'})
        item=exported['items'][0]
        self.assertEqual(set(item),{'id','revision','caption','alt_text','spoiler','image','build','capture','metadata_sha256'})
        self.assertEqual(item['image'],dict(sha256=self.image['digest'],mime='image/png',width=1,height=1))
        self.assertEqual(item['build'],dict(label='Test build one',association='provisional'))
        self.assertEqual(item['capture'],dict(basis='reported',kind='unknown',runtime_status=None,frame=None,date=None))
        self.assertEqual(item['spoiler'],'unknown')
        self.assertFalse(exported['publication_approved']);self.assertFalse(exported['release_approved'])
        self.assertFalse(exported['images_included'])

    def test_edits_invalidate_review_and_keep_history(self):
        a=self.select(self.draft())
        a=self.draft(data=content(caption='A changed caption.'),expected=a['revision'],key=a['id'])
        self.assertIsNone(a['review']);self.assertFalse(a['selected'])
        self.assertEqual(s.preview(self.store)['items'],[])
        self.assertEqual(len(s.history(self.store)),4)
        self.assertEqual(s.history(self.store)[0]['payload']['item']['content'],content())
        first=s.history(self.store,limit=1)[0]
        self.assertEqual(len(s.history(self.store,after=first['seq'])),3)

    def test_attachment_change_stales_review_and_blocks_export(self):
        a=self.select(self.draft());board=s.read(self.store)
        data=self.attachment_data();data['association']='confirmed'
        self.store.update_attachment(self.image['digest'],data,1)
        self.assertTrue(s.read(self.store)['items'][0]['stale'])
        with self.assertRaises(Conflict):s.preview(self.store)
        with self.assertRaises(Conflict):s.export(self.store,board['revision'],'stale.json')
        with self.assertRaises(Conflict):s.review(self.store,a['id'],a['revision'],a['review_token'])
        self.assertFalse((self.rom.parent/'stale.json').exists())
        s.select(self.store,a['id'],a['revision'],False)  # Removal works even if evidence is unavailable.
        self.assertEqual(s.preview(self.store)['items'],[])

    def test_context_race_and_review_digest_rejected(self):
        context=s.context(self.store,self.image['digest'])
        self.store.update_attachment(self.image['digest'],self.attachment_data(),1)
        with self.assertRaises(Conflict):s.put(self.store,self.image['digest'],context['token'],content(),0)
        a=self.draft()
        with self.assertRaises(Conflict):s.review(self.store,a['id'],1,'wrong token')
        with self.assertRaises(Conflict):self.draft(key=a['id'],expected=0)

    def test_changed_build_report_stales_selection(self):
        self.select(self.draft())
        build=self.store.builds()[0];revision=build.pop('revision');build['summary']='Changed private summary'
        self.store.build(build,revision)
        self.assertTrue(s.read(self.store)['items'][0]['stale'])
        with self.assertRaises(Conflict):s.preview(self.store)

    def test_registered_synthetic_capture_cannot_be_promoted(self):
        image,r=self.runtime()
        self.assertEqual(s.context(self.store,image['digest'])['runtime_choices'],[dict(report=r['report_sha256'],capture='blue')])
        with self.assertRaises(ValueError):self.draft(image,report=r['report_sha256'],data=content(capture_kind='registered_runtime'))
        self.select(self.draft(image,report=r['report_sha256'],data=content(capture_kind='synthetic')))
        capture=s.preview(self.store)['items'][0]['capture']
        self.assertEqual(capture,dict(basis='registered_run',kind='synthetic',runtime_status='passed',frame=1,date=None))

    def test_actual_runtime_shape_is_distinguished_without_real_execution(self):
        image,r=self.runtime(actual_shape=True)
        self.select(self.draft(image,report=r['report_sha256'],data=content(capture_kind='registered_runtime')))
        self.assertEqual(s.preview(self.store)['items'][0]['capture']['kind'],'registered_runtime')
        self.assertFalse(s.preview(self.store)['release_approved'])

    def test_failed_runtime_capture_remains_failed(self):
        image,r=self.runtime(status='failed')
        self.select(self.draft(image,report=r['report_sha256'],data=content(capture_kind='synthetic')))
        self.assertEqual(s.preview(self.store)['items'][0]['capture']['runtime_status'],'failed')

    def test_repeated_identical_frames_need_explicit_occurrence(self):
        image,r=self.runtime(duplicate=True)
        with self.assertRaises(ValueError):s.context(self.store,image['digest'],r['report_sha256'])
        self.select(self.draft(image,report=r['report_sha256'],capture='same',data=content(capture_kind='synthetic')))
        self.assertEqual(s.preview(self.store)['items'][0]['capture']['frame'],2)

    def test_runtime_artifacts_report_scenario_and_capture_tampering_block(self):
        image,r=self.runtime()
        self.select(self.draft(image,report=r['report_sha256'],data=content(capture_kind='synthetic')))
        for path in [self.rom,self.rom.parent/'run/runtime.json',self.rom.parent/'run/scenario.json',self.rom.parent/'run/blue.png']:
            original=path.read_bytes();path.write_bytes(b'changed')
            try:
                self.assertTrue(s.read(self.store)['items'][0]['stale'])
                with self.assertRaises(Conflict):s.preview(self.store)
            finally:path.write_bytes(original)
        self.assertEqual(len(s.preview(self.store)['items']),1)

    def test_stored_image_tampering_is_not_exported(self):
        self.select(self.draft())
        path=self.store.directory/'evidence'/self.image['digest'];path.write_bytes(b'changed')
        self.assertTrue(s.read(self.store)['items'][0]['stale'])
        with self.assertRaises(Conflict):s.preview(self.store)

    def test_manual_claims_are_reported_and_unlinked_image_has_no_build(self):
        self.store.update_attachment(self.image['digest'],{},1)
        for kind in ['reported_emulator','reported_hardware','static_preview','unknown']:
            self.select(self.draft(data=content(capture_kind=kind,build_label='',spoiler='spoilers')))
        for item in s.preview(self.store)['items']:
            self.assertEqual(item['capture']['basis'],'reported')
            self.assertEqual(item['build'],dict(label='',association='unlinked'))
            self.assertEqual(item['spoiler'],'spoilers')
        with self.assertRaises(ValueError):self.draft(data=content(build_label='Unbound label'))

    def test_schema_limits_unknown_links_and_forged_runtime(self):
        for data in [dict(content(),path='private.png'),content(alt_text=''),content(caption='x'*1001),
                     content(spoiler=True),content(capture_date='2026-02-30'),content(capture_kind='registered_runtime'),
                     content(build_label=''),content(caption='bad\x01')]:
            with self.assertRaises(ValueError):self.draft(data=data)
        with self.assertRaises(ValueError):s.context(self.store,'../escape')
        with self.assertRaises(KeyError):s.context(self.store,'0'*64)
        with self.assertRaises(ValueError):s.context(self.store,self.image['digest'],'0'*64)
        with self.assertRaises(ValueError):s.context(self.store,self.image['digest'],runtime_capture='blue')
        self.store.update_attachment(self.image['digest'],dict(build_id='absent'),1)
        with self.assertRaises(ValueError):self.draft()

    def test_independent_and_conflicting_writes(self):
        a=self.draft();b=self.draft()
        def edit(item):
            try:return self.draft(expected=item['revision'],key=item['id'])
            except Conflict:return None
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,a])),1)
            a=s.read(self.store)['items'][0]
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,b])),2)

    def test_export_only_metadata_empty_selection_and_no_overwrite(self):
        a=self.select(self.draft());before=self.store.attachments()
        preview=s.preview(self.store);result=s.export(self.store,preview['selection_revision'],'metadata/one.json')
        data=Path(result['path']).read_bytes()
        self.assertEqual(json.loads(data),preview)
        self.assertEqual(sha(data),result['sha256'])
        self.assertEqual([p.name for p in Path(result['path']).parent.iterdir()],['one.json'])
        self.assertEqual(self.store.attachments(),before)
        with self.assertRaises(FileExistsError):s.export(self.store,preview['selection_revision'],'metadata/one.json')
        with self.assertRaises(ValueError):s.export(self.store,preview['selection_revision'],'../outside.json')
        s.select(self.store,a['id'],a['revision'],False)
        with self.assertRaises(Conflict):s.export(self.store,preview['selection_revision'],'metadata/stale.json')
        p=s.preview(self.store);empty=s.export(self.store,p['selection_revision'],'metadata/empty.json')
        self.assertEqual(json.loads(Path(empty['path']).read_bytes())['items'],[])
        self.assertEqual(Path(result['path']).read_bytes(),data)

    def test_shared_writer_failure_is_clean(self):
        self.select(self.draft());revision=s.read(self.store)['revision']
        with patch('patchquest.editorial_exports.os.link',side_effect=OSError('unsupported')):
            with self.assertRaises(OSError):s.export(self.store,revision,'failed.json')
        self.assertFalse((self.rom.parent/'failed.json').exists())
        self.assertEqual(list(self.rom.parent.glob('.editorial-*')),[])
        self.assertFalse(any(r['kind'].endswith('.exported') for r in s.history(self.store)))

    def test_project_isolation_and_discovery(self):
        self.select(self.draft());other=self.root/'other';other.mkdir()
        separate=Store(project(other))
        self.assertEqual(s.preview(separate)['items'],[])
        with self.assertRaises(KeyError):s.context(separate,self.image['digest'])
        packet=execute(self.store,'agent-context')
        self.assertIn('screenshot-context',packet['read_actions'])
        self.assertIn('screenshot-selection.md',[Path(i['path']).name for i in packet['instructions']])

    def test_http_auth_scoped_writes_and_freshness(self):
        server=StudioServer(self.store,0,platform_root=self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(action,data=None,token=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if data is not None else 'GET','/api/'+action,body=json.dumps(data) if data is not None else None,
                         headers={'Content-Type':'application/json','X-Studio-Token':server.token if token is None else token})
            r=conn.getresponse();body=json.loads(r.read());conn.close();return r.status,body
        try:
            self.assertEqual(request('screenshot-selection',token='wrong')[0],401)
            _,ctx=request('screenshot-context?digest='+self.image['digest'])
            p=dict(data=content(),expected=0,digest=self.image['digest'],context_token=ctx['token'])
            self.assertEqual(request('screenshot-put',dict(p,actor='forged'))[0],400)
            status,a=request('screenshot-put',p);self.assertEqual(status,200)
            status,a=request('screenshot-review',dict(key=a['id'],expected=1,review_token=a['review_token']))
            self.assertEqual(status,200);self.assertEqual(a['review']['actor'],'Studio user')
            status,a=request('screenshot-select',dict(key=a['id'],expected=a['revision'],selected=True));self.assertEqual(status,200)
            self.assertEqual(request('screenshot-export',dict(expected=a['board_revision'],destination='../escape'))[0],400)
            status,result=request('screenshot-export',dict(expected=a['board_revision']));self.assertEqual(status,200)
            self.assertNotIn('PRIVATE',Path(result['path']).read_text())
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

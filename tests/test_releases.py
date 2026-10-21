"""Release preparation with independently invented byte strings only."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, invented
from patchquest import releases as r
from patchquest.patches import bps
from patchquest.state import Store, Conflict
from patchquest.state_api import execute
from patchquest.studio import StudioServer


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.manifest=project(self.root);self.store=Store(self.manifest)
        self.source=b'fictional input';self.target=b'fictional OUTPUT!'
        self.store.context.source.write_bytes(self.source)
        self.store.put(invented('greeting'),0,role='human')
        self.before=self.store.get('greeting');self.snapshot=self.store.snapshot()['sha256']
        self.patch=bps.encode(self.source,self.target)
        self.artifacts=self.build('first');self.build('repeat')
        self.data=dict(release_id='invented-demo',title='Invented lantern fixture',version='test-1',
            source_label='Invented input revision 1',patch_filename='lantern-test.bps',output_filename='lantern-test.bin',
            compatibility='Exact synthetic input only.',limitations='Synthetic bytes; no game or runtime verification.')

    def tearDown(self):
        self.assertEqual(self.store.get('greeting'),self.before)
        self.assertEqual(self.store.snapshot()['sha256'],self.snapshot)
        self.assertEqual(self.store.proposals('greeting'),[])

    def build(self,key,snapshot=None,target=None,patch_bytes=None,status='validated'):
        output=self.store.context.output.write_new(key+'/output.fixture',self.target if target is None else target)
        patch_file=self.store.context.output.write_new(key+'/patch.fixture',self.patch if patch_bytes is None else patch_bytes)
        artifacts=dict(rom=str(output),patch=str(patch_file))
        self.store.build(dict(id=key,snapshot=snapshot or self.snapshot,status=status,artifacts=artifacts),0)
        return artifacts

    def draft(self,**kwargs):
        return r.put(self.store,**dict(dict(data=self.data,build_id='first',patch_artifact='patch',output_artifact='rom',
            expected=0,private_notes='Private inspection notes.'),**kwargs))

    def validated(self,**kwargs):
        x=self.draft(**kwargs);return r.validate(self.store,x['id'],x['revision'])

    def reviewed(self,**kwargs):
        x=self.validated(**kwargs);return r.review(self.store,x['id'],x['revision'],x['validation']['token'])

    def export(self,x,destination='manifests/test.json'):
        return r.export(self.store,x['id'],x['revision'],x['validation']['token'],destination)

    def test_manifest_checksums_reconstruction_and_private_boundary(self):
        x=self.reviewed(repeat_build_id='repeat');result=self.export(x)
        payload=json.loads(Path(result['path']).read_text());raw=Path(result['path']).read_bytes()
        self.assertEqual(result['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(payload['source']['sha256'],hashlib.sha256(self.source).hexdigest())
        self.assertEqual(payload['output']['sha256'],hashlib.sha256(self.target).hexdigest())
        self.assertEqual(payload['patch']['sha256'],hashlib.sha256(self.patch).hexdigest())
        self.assertEqual(payload['checks']['reconstruction'],'passed')
        self.assertEqual(payload['checks']['repeat_build'],'matched_registered_artifacts')
        self.assertFalse(payload['publication_approved']);self.assertFalse(payload['release_approved'])
        for word in [str(self.root),'Private inspection','snapshot','build_id','greeting','source_sha256','validated_at']:
            self.assertNotIn(word,raw.decode())
        self.assertEqual(self.store.context.source.read_bytes(),self.source)
        self.assertEqual(Path(self.artifacts['rom']).read_bytes(),self.target)
        self.assertEqual(Path(self.artifacts['patch']).read_bytes(),self.patch)
        self.assertEqual(len(list((self.root/'output/manifests').iterdir())),1)

    def test_no_implicit_repeat_runtime_rights_or_approval(self):
        x=self.validated();checks=r.preview(self.store,x['id'])['manifest']['checks']
        self.assertEqual(checks['repeat_build'],'not_provided')
        self.assertEqual(checks['runtime'],'not_assessed');self.assertEqual(checks['rights'],'not_assessed')
        self.assertGreater(checks['literal_bytes'],0)
        for field in ['publication_approved','release_approved']:
            with self.assertRaises(ValueError):self.draft(data=dict(self.data,**{field:True}))

    def test_required_validation_and_review_gates(self):
        x=self.draft()
        with self.assertRaises(Conflict):r.preview(self.store,x['id'])
        x=r.validate(self.store,x['id'],1)
        with self.assertRaises(Conflict):self.export(x)
        with self.assertRaises(Conflict):r.review(self.store,x['id'],x['revision'],'wrong')
        self.assertFalse((self.root/'output/manifests').exists())

    def test_changed_draft_revokes_checks_and_retains_history(self):
        x=self.reviewed();self.export(x)
        edited=self.draft(key=x['id'],expected=x['revision'],private_notes='A changed private note.')
        self.assertIsNone(edited['validation']);self.assertIsNone(edited['review'])
        with self.assertRaises(Conflict):r.preview(self.store,x['id'])
        self.assertEqual(len(r.history(self.store)),5)
        self.assertTrue((self.root/'output/manifests/test.json').exists())

    def test_changed_patch_target_and_source_block_export(self):
        x=self.reviewed()
        for path,old in [(Path(self.artifacts['patch']),self.patch),(Path(self.artifacts['rom']),self.target),(self.store.context.source,self.source)]:
            path.write_bytes(old+b'x')
            with self.subTest(path=path.name),self.assertRaises((ValueError,Conflict)):self.export(x)
            path.write_bytes(old)
        self.assertFalse((self.root/'output/manifests').exists())

    def test_missing_inputs_and_build_report_changes(self):
        x=self.reviewed();p=Path(self.artifacts['rom']);p.unlink()
        with self.assertRaises(OSError):self.export(x)
        p.write_bytes(self.target)
        self.store.build(dict(id='first',snapshot=self.snapshot,status='validated',artifacts=self.artifacts,summary='Changed report.'),1)
        with self.assertRaises(Conflict):self.export(x)

    def test_wrong_source_and_header_are_never_normalized(self):
        for wrong in [b'fictional inpuX',bytes(512)+self.source]:
            self.store.context.source.write_bytes(wrong)
            with self.assertRaises(ValueError):self.validated()
        self.store.context.source.write_bytes(self.source)

    def test_manifest_source_identity_change_requires_reload(self):
        x=self.reviewed();data=json.loads(self.manifest.read_text());data['data']={'note':'changed'}
        self.manifest.write_text(json.dumps(data))
        with self.assertRaises(Conflict):self.export(x)

    def test_foreign_missing_snapshot_and_nonvalidated_builds(self):
        self.build('failed',status='failed')
        with self.assertRaises(ValueError):self.validated(build_id='failed')
        self.store.build(dict(id='no-snapshot',status='validated',artifacts=self.artifacts),0)
        with self.assertRaises(ValueError):self.validated(build_id='no-snapshot')
        with self.store.connection() as db:
            db.execute('UPDATE snapshots SET payload=? WHERE digest=?',('{}',self.snapshot))
        with self.assertRaises(ValueError):self.validated()

    def test_wrong_patch_same_size_target_bad_crc_and_truncation(self):
        variants=[self.patch[:-1],self.patch[:-1]+bytes([self.patch[-1]^1]),bps.encode(b'other fictional',self.target),bps.encode(self.source,b'x'*len(self.target))]
        for i,data in enumerate(variants):
            self.build('bad-'+str(i),patch_bytes=data)
            with self.subTest(case=i),self.assertRaises(ValueError):self.validated(build_id='bad-'+str(i))

    def test_repeat_build_mismatch_and_snapshot_mismatch(self):
        self.build('different',target=b'different')
        with self.assertRaises(ValueError):self.validated(repeat_build_id='different')
        current=self.store.get('greeting');data={k:v for k,v in current.items() if k not in ('revision','human_corrected','provenance')}
        self.store.put(dict(data,target='A later protected correction.'),1,role='human')
        self.before=self.store.get('greeting');self.snapshot=self.store.snapshot()['sha256']
        self.build('later')
        with self.assertRaises(ValueError):self.validated(repeat_build_id='later')
        # A frozen earlier release candidate remains valid; it does not claim latest text.
        self.assertEqual(self.validated()['validation']['manifest']['checks']['reconstruction'],'passed')

    def test_duplicate_build_and_missing_artifact_roles(self):
        for params in [dict(repeat_build_id='first'),dict(output_artifact='patch')]:
            with self.assertRaises(ValueError):self.draft(**params)
        with self.assertRaises(KeyError):self.draft(build_id='absent')
        with self.assertRaises(ValueError):self.validated(output_artifact='missing')

    def test_metadata_and_paths_rejected(self):
        for field,value in [('release_id','../escape'),('title',''),('version','x\x00'),('source_label',False),('patch_filename','../test.bps'),('patch_filename','CON.bps'),('patch_filename','test.ips'),('output_filename','script.exe'),('output_filename','two.words.bin')]:
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):self.draft(data=dict(self.data,**{field:value}))
        self.assertEqual(r.read(self.store)['items'],[])

    def test_export_no_clobber_and_traversal(self):
        x=self.reviewed();result=self.export(x);old=Path(result['path']).read_bytes()
        with self.assertRaises(FileExistsError):self.export(x)
        for name in ['../escape.json',str(self.root/'absolute.json')]:
            with self.assertRaises(ValueError):self.export(x,name)
        self.assertEqual(Path(result['path']).read_bytes(),old)

    def test_source_and_artifact_bounds(self):
        with patch.object(r,'MAX_BYTES',5),self.assertRaises(ValueError):self.validated()
        with patch.object(r,'MAX_BYTES',len(self.source)),self.assertRaises(ValueError):self.validated()

    def test_bps_metadata_is_counted_never_exported_and_commands_bounded(self):
        metadata=b'private invented patch metadata'
        stream=b'BPS1'+bps.number(len(self.source))+bps.number(len(self.target))+bps.number(len(metadata))+metadata+bps.number(((len(self.target)-1)<<2)|1)+self.target
        stream+=bps.crc(self.source)+bps.crc(self.target);patch_data=stream+bps.crc(stream)
        self.build('metadata',patch_bytes=patch_data)
        x=self.validated(build_id='metadata');manifest=x['validation']['manifest']
        self.assertEqual(manifest['checks']['metadata_bytes'],len(metadata));self.assertNotIn(metadata.decode(),json.dumps(manifest))
        bad=b'BPS1'+b'\x00'*11+b'\x80'+bytes(12)
        with self.assertRaises(ValueError):r._patch_check(self.source,self.target,bad)
        with self.assertRaises(ValueError):r._patch_check(self.source,self.target,b'BPS1'+bps.number(len(self.source))+bps.number(2**40)+bps.number(0)+bytes(12))
        moves=b'BPS1'+bps.number(len(self.source))+bps.number(len(self.target))+bps.number(0)+bps.number(2)+bytes(12)
        with self.assertRaisesRegex(ValueError,'SourceRead'):r._patch_check(self.source,self.target,moves)

    def test_independent_and_competing_candidate_writes(self):
        a=self.draft();b=self.draft()
        def edit(x):
            try:return self.draft(key=x['id'],expected=x['revision'])
            except Conflict:return None
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,a])),1)
        a=next(x for x in r.read(self.store)['items'] if x['id']==a['id'])
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,b])),2)

    def test_http_auth_forced_actor_no_destination_or_approval(self):
        context=execute(self.store,'agent-context');self.assertIn('release-export',context['write_actions'])
        self.assertIn('release-preparation.md',[Path(x['path']).name for x in context['instructions']])
        server=StudioServer(self.store,0,platform_root=self.root);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(action,data=None,token=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if data is not None else 'GET','/api/'+action,body=json.dumps(data) if data is not None else None,
                headers={'Content-Type':'application/json','X-Studio-Token':server.token if token is None else token})
            response=conn.getresponse();body=json.loads(response.read());conn.close();return response.status,body
        try:
            self.assertEqual(request('release-candidates',token='wrong')[0],401)
            params=dict(data=self.data,build_id='first',patch_artifact='patch',output_artifact='rom',expected=0)
            self.assertEqual(request('release-put',dict(params,actor='forged'))[0],400)
            self.assertEqual(request('release-put',dict(params,approved=True))[0],400)
            status,x=request('release-put',params);self.assertEqual(status,200)
            status,x=request('release-validate',dict(key=x['id'],expected=x['revision']));self.assertEqual(status,200)
            token=x['validation']['token'];status,x=request('release-review',dict(key=x['id'],expected=x['revision'],validation_token=token));self.assertEqual(status,200)
            args=dict(key=x['id'],expected=x['revision'],validation_token=token)
            self.assertEqual(request('release-export',dict(args,destination='forged.json'))[0],400)
            status,result=request('release-export',args);self.assertEqual(status,200)
            self.assertEqual(Path(result['path']).parent,self.root/'output/release-manifests')
            self.assertEqual(r.history(self.store)[-1]['payload']['actor'],'Studio user')
            self.assertEqual(request('release-review',dict(args,expected=1))[0],409)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

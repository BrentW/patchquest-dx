"""Independently invented tester submissions; no game data or network intake."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from patchquest.state import Store, Conflict
from patchquest.state_api import execute
from patchquest.studio import StudioServer
from patchquest import tester_reports as t


class TesterReportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(project(self.root))
        self.store.put(invented('greeting'),0,role='human',actor='Invented tester')
        self.before=self.store.get('greeting');self.snapshot=self.store.snapshot()['sha256']
        self.artifact=self.store.context.output.write_new('invented.fixture',b'invented test artifact')
        self.store.build(dict(id='test-build',snapshot=self.snapshot,status='validated',artifacts={'rom':str(self.artifact)}),0)
        self.digest=hashlib.sha256(self.artifact.read_bytes()).hexdigest()

    def tearDown(self):
        self.assertEqual(self.store.get('greeting'),self.before)
        self.assertEqual(self.store.snapshot()['sha256'],self.snapshot)

    def document(self, **changes):
        return dict(schema_version=1,report_type='tester-reports',project_id=self.store.context.manifest['project_id'],
                    source='invented-local-intake',reports=[dict(dict(external_id='one',title='Invented spacing problem',
                    observed='The invented label touches its frame.',suggested_translation='An inactive suggestion.'),**changes)])

    def ingest(self, document=None):
        document=document or self.document()
        p=t.preview_import(self.store,document)
        r=t.import_reports(self.store,document,p['token'])
        return t.get(self.store,r['ids'][0])

    def triage(self, report, **changes):
        params=dict(build_id='test-build',record_ids=['greeting'],attachment_digests=[],status='needs_info',
                    notes='Need an independently observed retest.')
        params.update(changes)
        ctx=t.context(self.store,report['id'],**{k:params[k] for k in ('build_id','record_ids','attachment_digests')})
        return t.triage(self.store,report['id'],report['revision'],ctx['token'],**params)

    def test_preview_has_no_writes_and_import_preserves_submission(self):
        before=self.store.events();doc=self.document();p=t.preview_import(self.store,doc)
        self.assertEqual(self.store.events(),before)
        self.assertEqual(p['new'],1);self.assertEqual(p['existing'],0)
        result=t.import_reports(self.store,doc,p['token']);r=t.get(self.store,result['ids'][0])
        self.assertEqual(r['content']['suggested_translation'],'An inactive suggestion.')
        self.assertEqual(r['triage']['status'],'new');self.assertEqual(result['translations_changed'],0)
        self.assertEqual(self.store.issues(),[]);self.assertEqual(self.store.proposals('greeting'),[])
        self.assertEqual(len(t.history(self.store,r['id'])),1)

    def test_identical_reimport_keeps_triage_and_history(self):
        doc=self.document();r=self.triage(self.ingest(doc));before=t.history(self.store,r['id'])
        p=t.preview_import(self.store,doc);result=t.import_reports(self.store,p['document'],p['token'])
        self.assertEqual(result['existing'],1);self.assertEqual(result['imported'],0)
        self.assertEqual(t.history(self.store,r['id']),before)
        self.assertEqual(t.get(self.store,r['id'])['triage'],r['triage'])

    def test_batch_conflicting_content_is_atomic(self):
        r=self.ingest();doc=self.document();doc['reports'][0]['observed']='Changed submission.'
        doc['reports'].insert(0,dict(external_id='two',title='Another',observed='Something else.'))
        with self.assertRaises(Conflict):t.preview_import(self.store,doc)
        with self.assertRaises(Conflict):t.import_reports(self.store,doc,'unreviewed')
        self.assertEqual(t.list_reports(self.store)['total'],1)
        self.assertEqual(len(t.history(self.store,r['id'])),1)

    def test_import_race_requires_new_preview(self):
        doc=self.document();p=t.preview_import(self.store,doc)
        self.ingest(doc)
        with self.assertRaises(Conflict):t.import_reports(self.store,doc,p['token'])
        self.assertEqual(t.list_reports(self.store)['total'],1)

    def test_namespaces_and_explicit_project_isolation(self):
        a=self.ingest();doc=self.document();doc['source']='different-local-intake'
        b=self.ingest(doc);self.assertNotEqual(a['id'],b['id'])
        doc['project_id']='another-project'
        with self.assertRaises(ValueError):t.preview_import(self.store,doc)
        other=self.root/'other';other.mkdir();store=Store(project(other))
        self.assertEqual(t.list_reports(store)['items'],[])
        with self.assertRaises(KeyError):t.get(store,a['id'])

    def test_invalid_import_shapes_limits_and_embedded_paths(self):
        bad=[]
        for key,value in [('schema_version',True),('schema_version',2),('report_type','anything'),('reports',[]),('source','')]:
            doc=self.document();doc[key]=value;bad.append(doc)
        for changes in [dict(title=''),dict(observed=''),dict(category='approved'),dict(artifact_sha256='bad'),
                        dict(attachment_digests=['a'*64,'a'*64]),dict(attachment_digests=['../private.png']),
                        dict(path='outside.json'),dict(approved=True),dict(description='x'*8001),dict(environment='bad\x01')]:
            doc=self.document();doc['reports'][0].update(changes);bad.append(doc)
        doc=self.document();doc['reports']*=2;bad.append(doc)
        doc=self.document();doc['reports']=[dict(external_id=str(i),title='Example',observed='x'*8000) for i in range(50)];bad.append(doc)
        for doc in bad:
            with self.subTest(doc=str(doc)[:100]),self.assertRaises((ValueError,TypeError)):
                t.import_reports(self.store,doc,'anything')
        self.assertEqual(t.list_reports(self.store)['total'],0)

    def test_build_snapshot_and_reported_hash_binding(self):
        r=self.ingest(self.document(artifact_sha256=self.digest))
        ctx=t.context(self.store,r['id'],'test-build',['greeting'])
        self.assertEqual(ctx['artifact_match'],'matched');self.assertEqual(ctx['matched_artifacts'],['rom'])
        self.assertEqual(ctx['binding']['records'],{'greeting':1})
        self.assertEqual(ctx['binding']['build']['snapshot'],self.snapshot)
        a=self.triage(r,status='accepted',create_issue=True)
        issue=self.store.issues()[0]
        self.assertEqual(a['triage']['issue_id'],issue['id'])
        self.assertEqual(issue['status'],'open');self.assertEqual(issue['build_id'],'test-build')
        self.assertIn('tester-report:'+r['id'],issue['references'])
        self.assertEqual(self.store.record_evidence('greeting'),[])

    def test_unknown_unreported_and_mismatching_builds(self):
        r=self.ingest(self.document(artifact_sha256='0'*64))
        self.assertEqual(t.context(self.store,r['id'])['artifact_match'],'unlinked')
        self.assertEqual(t.context(self.store,r['id'],'test-build')['artifact_match'],'mismatch')
        with self.assertRaises(ValueError):self.triage(r,status='accepted',create_issue=True)
        self.assertEqual(self.store.issues(),[])
        self.triage(r,status='needs_info')
        no_hash=self.ingest(self.document(external_id='no-hash'))
        self.assertEqual(t.context(self.store,no_hash['id'],'test-build')['artifact_match'],'unreported')
        self.triage(no_hash,status='accepted',create_issue=True)

    def test_missing_build_record_or_artifacts_blocks_binding(self):
        r=self.ingest()
        with self.assertRaises(KeyError):t.context(self.store,r['id'],'absent')
        with self.assertRaises(ValueError):t.context(self.store,r['id'],'',['greeting'])
        with self.assertRaises(ValueError):t.context(self.store,r['id'],'test-build',['absent'])
        self.artifact.unlink()
        with self.assertRaises(OSError):self.triage(r)
        self.assertEqual(t.get(self.store,r['id'])['revision'],1)

    def test_context_rejects_tampered_artifact_before_save(self):
        r=self.ingest();ctx=t.context(self.store,r['id'],'test-build',['greeting'])
        self.artifact.write_bytes(b'changed artifact')
        with self.assertRaises(Conflict):t.triage(self.store,r['id'],1,ctx['token'],'needs_info','Investigate.',build_id='test-build',record_ids=['greeting'])
        self.assertEqual(t.get(self.store,r['id'])['revision'],1)

    def test_historical_revisions_do_not_follow_current_human_correction(self):
        r=self.triage(self.ingest());ctx=t.context(self.store,r['id'],'test-build',['greeting'])
        changed=invented('greeting');changed['target']='A later protected human correction.'
        self.store.put(changed,1,role='human');self.before=self.store.get('greeting');self.snapshot=self.store.snapshot()['sha256']
        with self.assertRaises(Conflict):t.triage(self.store,r['id'],r['revision'],ctx['token'],'closed','Retest needed.',build_id='test-build',record_ids=['greeting'])
        view=t.get(self.store,r['id']);self.assertTrue(view['changed_since_triage'])
        self.assertEqual(view['context']['differs_from_build'],['greeting'])
        self.assertEqual(view['triage']['binding']['records'],{'greeting':1})
        self.triage(view,notes='Historical report retained; current text differs.')
        self.assertEqual(t.get(self.store,r['id'])['triage']['binding']['records'],{'greeting':1})

    def test_issue_link_creation_failure_and_live_issue_status(self):
        r=self.ingest()
        with self.assertRaises(KeyError):self.triage(r,status='accepted',issue_id='absent')
        with self.assertRaises(ValueError):self.triage(r,status='accepted')
        self.assertEqual(t.get(self.store,r['id'])['revision'],1)
        r=self.triage(r,status='accepted',create_issue=True);issue=self.store.issues()[0]
        revision=issue.pop('revision');issue['status']='resolved'
        self.store.put_issue(issue,revision)
        self.assertEqual(t.get(self.store,r['id'])['issue']['status'],'resolved')
        before=self.store.issue_history(issue['id'])
        self.triage(r,status='closed',issue_id=issue['id'],notes='Intake closed; retest remains a separate check.')
        self.assertEqual(self.store.issue_history(issue['id']),before)

    def test_duplicate_cycles_and_missing_original_are_rejected(self):
        a=self.ingest();b=self.ingest(self.document(external_id='two'))
        with self.assertRaises(KeyError):self.triage(a,status='duplicate',duplicate_of='absent')
        with self.assertRaises(ValueError):self.triage(a,status='duplicate',duplicate_of=a['id'])
        with self.assertRaises(ValueError):self.triage(a,status='duplicate')
        a=self.triage(a,status='duplicate',duplicate_of=b['id'])
        with self.assertRaises(ValueError):self.triage(b,status='duplicate',duplicate_of=a['id'])
        a=self.triage(a,status='new',notes='Reopened for independent investigation.')
        self.assertEqual(len(t.history(self.store,a['id'])),3)

    def test_attachment_context_and_missing_evidence_can_be_unlinked(self):
        image=self.store.upload(PIXEL,dict(description='Invented pixel'))
        r=self.triage(self.ingest(),attachment_digests=[image['digest']])
        self.store.update_attachment(image['digest'],dict(description='Updated association'),1)
        self.assertTrue(t.get(self.store,r['id'])['changed_since_triage'])
        (self.store.directory/'evidence'/image['digest']).unlink()
        self.assertTrue(t.get(self.store,r['id'])['binding_unavailable'])
        result=self.triage(r,build_id='',record_ids=[],status='closed',notes='Missing evidence; original context remains in history.')
        self.assertEqual(result['triage']['binding']['attachments'],{})
        self.assertIn(image['digest'],t.history(self.store,r['id'])[1]['report']['triage']['binding']['attachments'])

    def test_independent_and_competing_triage(self):
        a=self.ingest();b=self.ingest(self.document(external_id='two'))
        def edit(r):
            try:return self.triage(r)
            except Conflict:return None
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,a])),1)
            a=t.get(self.store,a['id'])
            self.assertEqual(sum(x is not None for x in pool.map(edit,[a,b])),2)

    def test_pagination_status_and_history(self):
        a=self.ingest();b=self.ingest(self.document(external_id='two'));self.triage(a)
        self.assertEqual(t.list_reports(self.store,limit=1)['total'],2)
        self.assertEqual(len(t.list_reports(self.store,offset=1,limit=1)['items']),1)
        self.assertEqual(t.list_reports(self.store,status='new')['items'][0]['id'],b['id'])
        first=t.history(self.store,a['id'],limit=1)[0]
        self.assertEqual(len(t.history(self.store,a['id'],after=first['seq'])),1)
        for params in [dict(limit=0),dict(offset=-1),dict(limit=True),dict(status='fixed')]:
            with self.assertRaises(ValueError):t.list_reports(self.store,**params)

    def test_notes_decisions_and_create_issue_options(self):
        r=self.ingest()
        for params in [dict(status='approved'),dict(status='closed',notes=''),dict(create_issue='yes'),
                       dict(create_issue=True),dict(status='accepted',create_issue=True,issue_id='anything')]:
            with self.assertRaises(ValueError):self.triage(r,**params)
        self.assertEqual(t.get(self.store,r['id'])['revision'],1)
        self.assertEqual(self.store.issues(),[])

    def test_shared_discovery_and_http_permissions(self):
        packet=execute(self.store,'agent-context')
        self.assertIn('tester-import',packet['write_actions'])
        self.assertIn('tester-workflow.md',[Path(i['path']).name for i in packet['instructions']])
        server=StudioServer(self.store,0,platform_root=self.root);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(action,data=None,token=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if data is not None else 'GET','/api/'+action,body=json.dumps(data) if data is not None else None,
                         headers={'Content-Type':'application/json','X-Studio-Token':server.token if token is None else token})
            response=conn.getresponse();body=json.loads(response.read());conn.close();return response.status,body
        try:
            self.assertEqual(request('tester-reports',token='wrong')[0],401)
            status,p=request('tester-import-preview',dict(document=self.document()));self.assertEqual(status,200)
            params=dict(document=self.document(),preview_token=p['token'])
            self.assertEqual(request('tester-import',dict(params,actor='forged'))[0],400)
            status,r=request('tester-import',params);self.assertEqual(status,200)
            key=r['ids'][0];status,ctx=request('tester-context',dict(key=key));self.assertEqual(status,200)
            status,r=request('tester-triage',dict(key=key,expected=1,context_token=ctx['token'],status='needs_info',notes='Need build identity.'));self.assertEqual(status,200)
            self.assertEqual(t.history(self.store,key)[-1]['actor'],'Studio user')
            self.assertEqual(request('tester-triage',dict(key=key,expected=1,context_token=ctx['token'],status='closed',notes='Old write.'))[0],409)
        finally:server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()

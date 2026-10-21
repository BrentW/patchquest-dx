"""Synthetic authoritative Store/Jobs/Coordination preservation and exclusion."""
import copy
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from patchquest.runtime_artifact_state import ArtifactState, POLICY_KEY
from patchquest.runtime_artifacts import RuntimeArtifacts, ArtifactError, reference
from patchquest.runtime_contracts import validate
from patchquest.state import Store, Conflict
from patchquest.jobs import Jobs
from patchquest.collaboration import Coordination
from patchquest import tester_reports


class ArtifactStateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name); self.store = Store(project(self.root))
        self.store.put(invented('greeting'), 0, role='human')
        self.before = self.store.get('greeting')
        self.connector = ArtifactState(self.store, self.store.directory/'runtime-artifacts')
        self.artifacts = RuntimeArtifacts(self.connector.directory, budget_bytes=1024*1024,
                                         graph_guard=self.connector.guard)
        self.data = b'independently invented capture'
        self.ref = reference(self.data, evidence_id='capture-one', media_type='application/octet-stream',
            provenance=dict(producer='invented-adapter',method='synthetic',run_id='run-one',case_id='fictional-greeting-page-0'),
            retention='disposable')
        self.digest = self.ref['sha256']
        self.connector.set_policy(pins=[],ownership={self.digest:'managed'},expected=0)
        self.ref = self.artifacts.register(self.ref,self.data)

    def tearDown(self):
        self.assertEqual(self.store.get('greeting'),self.before)

    def graph(self):
        with self.connector.guard() as g: return g

    def build(self, approval=None):
        snap = self.store.snapshot()['sha256']
        path = self.store.context.output.write_new('retained.fixture', b'invented build')
        return self.store.build(dict(id='invented-build', snapshot=snap, status='validated',
            artifacts={'rom':str(path)}, approval=approval or {}),0)

    def observation(self, build, failed=False):
        obs=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']['CaseObservation']
        obs['binding']['snapshot']=build['snapshot']
        obs['captures'][0]['evidence']=self.ref
        if failed:obs.update(assertion='failed',reason='Invented injected missing glyph')
        return validate('CaseObservation',obs)

    def test_actual_guard_constructs_complete_graph_without_mirror_database(self):
        graph=self.graph()
        self.assertTrue(graph['complete'])
        self.assertEqual(graph['ownership'][self.digest],'managed')
        self.assertEqual(graph['ownership'][self.store.context.manifest['source']['sha256']],'original')
        self.assertEqual([p.name for p in self.store.directory.glob('*.sqlite3')],['state.sqlite3'])
        row=next(r for r in self.artifacts.retention_plan([self.ref])['rows'] if r['sha256']==self.digest)
        self.assertEqual(row['action'],'propose_delete')

    def test_policy_cas_pins_and_protected_classifications(self):
        self.connector.set_policy(pins=[self.digest],ownership={self.digest:'user_save'},expected=1)
        self.assertIn(self.digest,self.graph()['pins'])
        with self.assertRaises(Conflict):self.connector.set_policy(pins=[],ownership={},expected=1)
        with self.assertRaises(ArtifactError):self.connector.set_policy(pins=[],ownership={self.digest:'managed'},expected=2)
        self.assertEqual(next(r for r in self.artifacts.retention_plan([self.ref])['rows'] if r['sha256']==self.digest)['action'],'retain')

    def test_explicit_unpin_does_not_reactivate_historical_pin(self):
        self.connector.set_policy(pins=[self.digest],ownership={self.digest:'managed'},expected=1)
        self.connector.set_policy(pins=[],ownership={self.digest:'managed'},expected=2)
        self.assertNotIn(self.digest,self.graph()['pins'])
        self.assertEqual(next(r for r in self.artifacts.retention_plan([self.ref])['rows'] if r['sha256']==self.digest)['action'],'propose_delete')

    def test_run_and_failed_capture_preserved_in_build_history(self):
        build=self.build();obs=self.observation(build,failed=True)
        saved=self.connector.record_run(build['id'],[obs],expected=1)
        graph=self.graph()
        kinds={r['kind'] for r in graph['references'] if r['sha256']==self.digest}
        self.assertTrue({'run','failure','build'}<=kinds)
        self.assertEqual(saved['validation']['runtime_cases'][0]['captures'][0]['evidence'],self.ref)
        # Historical evidence survives a later report omitting its runtime validation.
        updated=dict(saved);updated.pop('revision');updated['validation']={}
        self.store.build(updated,2)
        self.assertIn(self.digest,{r['sha256'] for r in self.graph()['references'] if r['kind']=='failure'})

    def test_run_publish_cas_identity_and_snapshot(self):
        build=self.build();obs=self.observation(build)
        self.connector.record_run(build['id'],[obs],expected=1)
        with self.assertRaises(Conflict):self.connector.record_run(build['id'],[obs],expected=1)
        changed=copy.deepcopy(obs);changed['reason']='Different evidence identity contents'
        with self.assertRaises(ArtifactError):self.connector.record_run(build['id'],[changed],expected=2)
        wrong=copy.deepcopy(obs);wrong['binding']['snapshot']='0'*64
        with self.assertRaises(ArtifactError):self.connector.record_run(build['id'],[wrong],expected=2)

    def test_build_paths_and_checkpoint_approval_references(self):
        build=self.build(approval={'approved':True,'reference':self.digest})
        graph=self.graph();kinds={r['kind'] for r in graph['references'] if r['sha256']==self.digest}
        self.assertIn('checkpoint_approval',kinds)
        digest=hashlib.sha256(b'invented build').hexdigest()
        # A readable path is not evidence of an immutable historical role hash.
        self.assertNotIn(digest,{r['sha256'] for r in graph['references'] if r['kind']=='build'})
        self.assertIn(self.digest,graph['pins'])
        self.assertTrue(build['approval']['approved'])

    def test_real_tester_report_reference_is_retained(self):
        doc=dict(schema_version=1,report_type='tester-reports',project_id='invented-demo',source='invented-intake',
                 reports=[dict(external_id='report-one',title='Invented spacing defect',observed='A label crosses the edge.',artifact_sha256=self.digest)])
        preview=tester_reports.preview_import(self.store,doc)
        tester_reports.import_reports(self.store,doc,preview['token'])
        self.assertIn(self.digest,{r['sha256'] for r in self.graph()['references'] if r['kind']=='tester_report'})

    def test_actual_attachment_and_history_reference(self):
        uploaded=self.store.upload(PIXEL,dict(description='Invented one-pixel fixture'))
        self.assertIn(uploaded['digest'],{r['sha256'] for r in self.graph()['references'] if r['kind']=='attachment'})

    def test_active_and_unreconciled_expired_build_worker_protect_all(self):
        Jobs(self.store).register('worker-one','Invented worker')
        self.assertTrue(any(l['sha256']==self.digest and l['active'] for l in self.graph()['leases']))
        # Test-only fault injection; production reads never bypass lease-owner APIs.
        with self.store.connection() as db:db.execute('UPDATE build_worker SET expires=0')
        self.assertTrue(self.graph()['leases'])
        Jobs(self.store).unregister('worker-one')
        self.assertEqual(self.graph()['leases'],[])

    def test_actual_task_session_and_fence_protect_all(self):
        queue=Coordination(self.store)
        session=queue.start('synthetic',label='Invented reader')['session']
        queue.create('fixture-task','Read invented bytes',resources=['invented-runtime'])
        lease=queue.claim(session,'fixture-task')
        self.assertTrue(any(l['owner']=='task:fixture-task' for l in self.graph()['leases']))
        queue.finish(session,'fixture-task',lease['fence'],'done','Synthetic read complete')
        self.assertTrue(any(l['owner']=='session:'+session for l in self.graph()['leases']))
        queue.close(session)
        self.assertEqual(self.graph()['leases'],[])

    def test_guard_excludes_concurrent_job_claim(self):
        jobs=Jobs(self.store);jobs.register('worker-one','Invented worker');jobs.submit('request-0001')
        started=threading.Event();done=threading.Event();errors=[]
        def claim():
            started.set()
            try:jobs.claim('worker-one')
            except Exception as e:errors.append(e)
            finally:done.set()
        with self.connector.guard() as graph:
            worker=threading.Thread(target=claim);worker.start();self.assertTrue(started.wait(3))
            self.assertFalse(done.wait(.05))
            self.assertTrue(graph['leases'])
        worker.join(5);self.assertTrue(done.is_set());self.assertEqual(errors,[])
        self.assertEqual(jobs.list()[0]['status'],'running')

    def test_concurrent_pin_cas_and_plan_recheck(self):
        plan=self.artifacts.retention_plan([self.ref])
        self.connector.set_policy(pins=[self.digest],ownership={self.digest:'managed'},expected=1)
        with self.assertRaises(ArtifactError):self.artifacts.recheck_plan(plan,[self.ref])
        self.assertEqual(self.artifacts.resolve(self.ref)['data'],self.data)

    def test_missing_build_path_and_opaque_legacy_reference_pin_conservatively(self):
        self.store.build(dict(id='missing-build',status='failed',artifacts={'rom':'missing.fixture'},evidence={'reference':'Unresolved legacy reference'}),0)
        self.assertIn(self.digest,self.graph()['pins'])
        self.assertEqual(next(r for r in self.artifacts.retention_plan([self.ref])['rows'] if r['sha256']==self.digest)['action'],'retain')

    def path_only_build(self, path_value, *, key='path-only-build'):
        return self.store.build(dict(id=key,snapshot=self.store.snapshot()['sha256'],
            status='validated',artifacts={'rom':path_value}),0)

    def retained_row(self, plan):
        return next(row for row in plan['rows'] if row['sha256']==self.digest)

    def test_changed_live_canonical_path_cannot_release_retained_h1(self):
        path=self.store.context.output.write_new('path-only.fixture',self.data)
        self.path_only_build(str(path))
        before=self.artifacts.retention_plan([self.ref])
        self.assertEqual(self.retained_row(before)['action'],'retain')
        # Fault injection into an invented disposable canonical fixture only.
        changed=b'independently invented H2 canonical bytes'
        path.write_bytes(changed)
        fresh=self.artifacts.retention_plan([self.ref])
        self.assertEqual(self.retained_row(fresh)['integrity'],'verified')
        self.assertEqual(self.retained_row(fresh)['action'],'retain')
        self.assertEqual(self.artifacts.recheck_plan(fresh,[self.ref]),fresh)
        self.assertEqual(self.artifacts.resolve(self.ref)['data'],self.data)
        self.assertEqual(path.read_bytes(),changed)
        # Current readable H2 is not a recorded immutable role identity.
        h2=hashlib.sha256(changed).hexdigest()
        self.assertNotIn(h2,{r['sha256'] for r in self.graph()['references']})

    def test_historical_path_only_reference_survives_current_row_change(self):
        path=self.store.context.output.write_new('historical-path.fixture',self.data)
        build=self.path_only_build(str(path))
        old=self.artifacts.retention_plan([self.ref])
        changed=b'independently invented replacement fixture'
        path.write_bytes(changed)
        latest=dict(build);latest.pop('revision');latest['artifacts']={}
        self.store.build(latest,1)
        self.assertEqual(self.store.builds()[0]['artifacts'],{})
        with self.assertRaises(ArtifactError):self.artifacts.recheck_plan(old,[self.ref])
        fresh=self.artifacts.retention_plan([self.ref])
        self.assertEqual(self.retained_row(fresh)['action'],'retain')
        self.assertEqual(self.artifacts.recheck_plan(fresh,[self.ref]),fresh)
        self.assertEqual(self.artifacts.resolve(self.ref)['data'],self.data)

    def test_missing_path_only_reference_retains_without_unrelated_opaque_fields(self):
        self.path_only_build('never-created.fixture')
        row=self.retained_row(self.artifacts.retention_plan([self.ref]))
        self.assertEqual(row['action'],'retain')
        self.assertIn(self.digest,self.graph()['pins'])

    def test_digest_looking_filename_is_not_an_immutable_role_digest(self):
        filename=hashlib.sha256(b'independently invented filename').hexdigest()
        path=self.store.context.output.write_new(filename,self.data)
        # Store output policy also supports a relative path consisting of hex.
        self.path_only_build(filename)
        path.write_bytes(b'independently invented later file version')
        row=self.retained_row(self.artifacts.retention_plan([self.ref]))
        self.assertEqual(row['action'],'retain')
        self.assertEqual(self.artifacts.resolve(self.ref)['data'],self.data)

    def test_completed_job_path_result_is_still_an_uncertain_reference(self):
        path=self.store.context.output.write_new('job-result.fixture',self.data)
        jobs=Jobs(self.store);jobs.register('invented-worker','Invented worker')
        jobs.submit('request-0001');jobs.claim('invented-worker')
        jobs.update('request-0001','invented-worker','Complete','validated',
                    result=dict(status='validated',artifacts={'rom':str(path)}))
        jobs.unregister('invented-worker')
        self.assertEqual(self.graph()['leases'],[])
        path.write_bytes(b'independently invented changed job output')
        row=self.retained_row(self.artifacts.retention_plan([self.ref]))
        self.assertEqual(row['action'],'retain')
        self.assertIn(self.digest,self.graph()['pins'])

    def test_typed_immutable_role_binding_does_not_become_a_path_uncertainty(self):
        binding=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']['RunBinding']
        binding['artifacts']={'rom':self.digest};binding['snapshot']=self.store.snapshot()['sha256']
        self.store.build(dict(id='typed-binding-build',snapshot=binding['snapshot'],
                              status='validated',evidence=binding),0)
        graph=self.graph()
        self.assertIn(self.digest,{r['sha256'] for r in graph['references']})
        self.assertNotIn(self.digest,graph['pins'])
        self.assertEqual(self.retained_row(self.artifacts.retention_plan([self.ref]))['action'],'retain')

    def test_unknown_metadata_or_table_fails_closed(self):
        with self.store.connection() as db:db.execute('INSERT INTO metadata VALUES(?,?)',('unknown-reference.v2','{}'))
        with self.assertRaises(ArtifactError):self.graph()
        with self.store.connection() as db:db.execute('DELETE FROM metadata WHERE key=?',('unknown-reference.v2',));db.execute('CREATE TABLE future_reference(id TEXT)')
        with self.assertRaises(ArtifactError):self.graph()

    def test_unknown_reference_column_fails_closed(self):
        with self.store.connection() as db:db.execute('ALTER TABLE builds ADD COLUMN future_reference TEXT')
        with self.assertRaises(ArtifactError):self.graph()

    def test_unknown_build_extension_cannot_release_bytes(self):
        self.store.build(dict(id='future-build',status='failed',validation={'future_detector':{'private_link':'opaque'}}),0)
        self.assertIn(self.digest,self.graph()['pins'])

    def test_reads_do_not_expire_leases_or_change_state(self):
        Jobs(self.store).register('worker-one','Invented worker')
        with self.store.connection() as db:before=[tuple(r) for r in db.execute('SELECT * FROM build_worker')]
        events=self.store.events();self.artifacts.resolve(self.ref);self.artifacts.retention_plan([self.ref])
        with self.store.connection() as db:after=[tuple(r) for r in db.execute('SELECT * FROM build_worker')]
        self.assertEqual(before,after);self.assertEqual(self.store.events(),events)


    def fast_artifacts(self):
        return RuntimeArtifacts(self.connector.directory, budget_bytes=1024*1024,
            graph_guard=self.connector.guard, read_guard=self.connector.read_guard)

    def test_resolution_read_guard_skips_history_and_rehashes_each_read(self):
        # Independently invented large retained history; no game-derived payload.
        for revision in range(16):
            self.store.build(dict(id='large-invented-history',status='failed',
                validation={'invented_padding':'x'*200000}),revision)
        fast=self.fast_artifacts();queries=[];original=self.store.connection
        before=self.store.events();head=self.store.get('greeting')
        @contextmanager
        def traced():
            with original() as db:
                db.set_trace_callback(queries.append)
                yield db
        with mock.patch.object(self.store,'connection',traced), \
                mock.patch.object(self.connector,'_inventory',side_effect=AssertionError('No retention inventory on read')), \
                mock.patch.object(self.connector,'_load_policy',side_effect=AssertionError('No retention policy on read')):
            self.assertEqual(fast.resolve(self.ref)['data'],self.data)
            (fast.directory/self.digest).write_bytes(b'X'*len(self.data))
            changed=fast.resolve(self.ref)
            self.assertFalse(changed['available']);self.assertIsNone(changed['data'])
            self.assertEqual(changed['evidence']['integrity'],'mismatch')
        selects=[sql for sql in queries if sql.upper().startswith('SELECT')]
        self.assertEqual(len(selects),4)  # schema names + selected identity for each read
        self.assertTrue(all('sqlite_master' in sql or "key='identity'" in sql for sql in selects))
        self.assertEqual(self.store.events(),before);self.assertEqual(self.store.get('greeting'),head)
        self.assertFalse((fast.directory/'.writer-lock').exists())

    def test_read_guard_excludes_job_claim_and_policy_writer(self):
        jobs=Jobs(self.store);jobs.register('read-guard-worker','Invented worker');jobs.submit('request-read-guard')
        started=[threading.Event(),threading.Event()];done=[threading.Event(),threading.Event()];errors=[]
        def write(index, operation):
            started[index].set()
            try:operation()
            except Exception as error:errors.append(error)
            finally:done[index].set()
        operations=[lambda:jobs.claim('read-guard-worker'),lambda:self.connector.set_policy(
            pins=[self.digest],ownership={self.digest:'managed'},expected=1)]
        threads=[threading.Thread(target=write,args=(i,op)) for i,op in enumerate(operations)]
        try:
            with self.connector.read_guard() as authority:
                self.assertIsNone(authority)  # no graph/deletion authority
                for thread in threads:thread.start()
                self.assertTrue(all(event.wait(3) for event in started))
                self.assertTrue(all(not event.wait(.05) for event in done))
        finally:
            for thread in threads:
                if thread.ident is not None:thread.join(5)
        self.assertTrue(all(event.is_set() for event in done));self.assertEqual(errors,[])
        self.assertEqual(jobs.list()[0]['status'],'running')
        self.assertIn(self.digest,self.connector.policy()['pins'])

    def test_resolution_read_guard_rejects_unknown_table(self):
        fast=self.fast_artifacts()
        with self.store.connection() as db:db.execute('CREATE TABLE unknown_read_reference(id TEXT)')
        with self.assertRaises(ArtifactError):fast.resolve(self.ref)
        self.assertFalse((fast.directory/'.writer-lock').exists())

    def test_resolution_read_guard_rejects_unknown_column(self):
        fast=self.fast_artifacts()
        with self.store.connection() as db:db.execute('ALTER TABLE builds ADD COLUMN future_read_reference TEXT')
        with self.assertRaises(ArtifactError):fast.resolve(self.ref)
        self.assertFalse((fast.directory/'.writer-lock').exists())

    def test_resolution_read_guard_rejects_version_and_wrong_identity(self):
        fast=self.fast_artifacts()
        with self.store.connection() as db:db.execute('PRAGMA user_version=4')
        with self.assertRaises(ArtifactError):fast.resolve(self.ref)
        with self.store.connection() as db:
            db.execute('PRAGMA user_version=3')
            db.execute("UPDATE metadata SET value='{}' WHERE key='identity'")
        with self.assertRaises(ArtifactError):fast.resolve(self.ref)
        self.assertFalse((fast.directory/'.writer-lock').exists())


if __name__=='__main__':unittest.main()

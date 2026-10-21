"""Invented bytes and graph fixtures; no private game or emulator evidence."""
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.runtime_artifacts import (RuntimeArtifacts, ArtifactError, ArtifactBusy,
                                         BudgetExceeded, reference)


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.graph = dict(revision='1', complete=True, references=[], pins=[], leases=[], ownership={})
        self.lock = threading.RLock()
        self.store = RuntimeArtifacts(self.base/'blobs', budget_bytes=24, graph_guard=self.guard)
        self.data = b'invented capture'
        self.ref = reference(self.data, evidence_id='capture-a', media_type='application/octet-stream',
            provenance=dict(producer='invented-adapter', method='synthetic', run_id='run-a', case_id='case-a'),
            retention='disposable')
        self.digest = self.ref['sha256']
        self.graph['ownership'][self.digest] = 'managed'

    @contextmanager
    def guard(self):
        with self.lock:
            yield copy.deepcopy(self.graph)

    def register(self):
        return self.store.register(self.ref, self.data)

    def test_dedup_preserves_each_case_and_run(self):
        first = self.register()
        other = copy.deepcopy(self.ref)
        other['evidence_id'] = 'capture-b'
        other['provenance'].update(run_id='run-b', case_id='case-b')
        second = self.store.register(other, self.data)
        self.assertNotEqual(first['provenance'], second['provenance'])
        self.assertEqual(len(list(self.store.directory.iterdir())), 1)
        self.assertEqual(self.store.retention_plan([first, second])['rows'][0]['evidence_ids'], ['capture-a','capture-b'])
        self.assertEqual(self.ref['integrity'], 'unverified')
        self.assertEqual(second['provenance']['method'], 'synthetic')

    def test_invalid_reference_bytes_not_written(self):
        with self.assertRaises(ValueError): self.store.register(self.ref, b'wrong')
        self.assertEqual(list(self.store.directory.iterdir()), [])

    def test_missing_is_unavailable(self):
        out = self.store.resolve(self.ref)
        self.assertFalse(out['available'])
        self.assertEqual(out['evidence']['integrity'], 'missing')
        self.assertIsNone(out['data'])

    def test_changed_bytes_are_unavailable_and_never_overwritten(self):
        self.register()
        p = self.store.directory/self.digest
        p.write_bytes(b'x'*len(self.data))
        self.assertEqual(self.store.resolve(self.ref)['evidence']['integrity'], 'mismatch')
        with self.assertRaises(ArtifactError): self.register()
        self.assertEqual(p.read_bytes(), b'x'*len(self.data))

    def test_changed_size(self):
        self.register(); (self.store.directory/self.digest).write_bytes(b'partial')
        self.assertEqual(self.store.resolve(self.ref)['evidence']['integrity'], 'mismatch')
        self.assertEqual(self.store.retention_plan([self.ref])['rows'][0]['action'], 'retain')

    def test_exact_budget_dedup_and_failed_admission(self):
        self.store.budget_bytes = len(self.data)
        self.register(); self.register()
        extra = reference(b'q', evidence_id='q', media_type='text/plain', provenance=self.ref['provenance'])
        with self.assertRaises(BudgetExceeded): self.store.register(extra, b'q')
        report = self.store.budget(1)
        self.assertFalse(report['allowed']); self.assertFalse(report['complete'])
        self.assertEqual(report['execution'], 'interrupted')
        self.assertTrue(self.store.resolve(self.ref)['available'])

    def test_bad_budgets(self):
        for v in (True, -1, 1.5, None):
            with self.subTest(v=v), self.assertRaises(ArtifactError): self.store.budget(v)

    def test_concurrent_writers_cannot_overbook(self):
        self.store.budget_bytes = 16
        barrier = threading.Barrier(2)
        results = []
        def write(data):
            r = reference(data, evidence_id=data.decode(), media_type='text/plain', provenance=self.ref['provenance'])
            barrier.wait()
            try: self.store.register(r,data); results.append('ok')
            except (BudgetExceeded, ArtifactBusy): results.append('blocked')
        threads = [threading.Thread(target=write,args=(d,)) for d in (b'aaaaaaaaaaaa',b'bbbbbbbbbbbb')]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertEqual(sorted(results), ['blocked','ok'])
        self.assertLessEqual(self.store.budget(0)['used_bytes'],16)

    def test_shared_references_failure_reports_approvals_and_pins(self):
        self.register()
        kinds = ['run', 'failure', 'tester_report', 'checkpoint_approval', 'attachment', 'build']
        self.graph['references'] = [dict(sha256=self.digest,kind=k,id=k+'-one') for k in kinds]
        self.graph['pins'] = [self.digest]
        row = self.store.retention_plan([self.ref])['rows'][0]
        self.assertEqual(row['action'],'retain')
        self.assertEqual(len(row['reasons']),7)
        self.assertEqual((self.store.directory/self.digest).read_bytes(), self.data)

    def test_active_job_or_task_blocks_retention(self):
        self.register()
        self.graph['leases'] = [dict(sha256=self.digest,owner='invented-worker',active=True)]
        row = self.store.retention_plan([self.ref])['rows'][0]
        self.assertIn('active_lease:invented-worker',row['reasons'])

    def test_new_lease_invalidates_plan_without_deleting(self):
        self.register(); plan = self.store.retention_plan([self.ref])
        self.graph['leases'] = [dict(sha256=self.digest,owner='new-worker',active=True)]
        with self.assertRaises(ArtifactError): self.store.recheck_plan(plan,[self.ref])
        self.assertTrue(self.store.resolve(self.ref)['available'])

    def test_concurrent_lease_claim_serializes_with_graph_snapshot(self):
        self.register()
        held = threading.Event()
        release = threading.Event()
        def claimant():
            with self.lock:
                self.graph['leases'] = [dict(sha256=self.digest, owner='concurrent-job', active=True)]
                held.set()
                release.wait(5)
        worker = threading.Thread(target=claimant)
        worker.start()
        self.assertTrue(held.wait(5))
        observed = []
        reader = threading.Thread(target=lambda: observed.append(self.store.retention_plan([self.ref])))
        reader.start()
        release.set()
        worker.join(5); reader.join(5)
        self.assertFalse(worker.is_alive()); self.assertFalse(reader.is_alive())
        self.assertIn('active_lease:concurrent-job', observed[0]['rows'][0]['reasons'])
        self.assertEqual(observed[0]['rows'][0]['action'], 'retain')

    def test_reference_added_during_review_invalidates_plan(self):
        self.register(); plan = self.store.retention_plan([self.ref])
        self.graph['references'].append(dict(sha256=self.digest,kind='run',id='later'))
        with self.assertRaises(ArtifactError): self.store.recheck_plan(plan,[self.ref])

    def test_changed_hash_invalidates_plan(self):
        self.register(); plan = self.store.retention_plan([self.ref])
        (self.store.directory/self.digest).write_bytes(b'changed')
        with self.assertRaises(ArtifactError): self.store.recheck_plan(plan,[self.ref])

    def test_retention_revision_invalidates_plan(self):
        self.register(); plan = self.store.retention_plan([self.ref])
        self.graph['revision']='2'
        with self.assertRaises(ArtifactError): self.store.recheck_plan(plan,[self.ref])

    def test_original_save_checkpoint_and_unknown_protected(self):
        self.register()
        for owner in ('original','user_save','checkpoint','unknown'):
            self.graph['ownership'][self.digest]=owner
            row=self.store.retention_plan([self.ref])['rows'][0]
            self.assertEqual(row['action'],'retain')
        self.graph['ownership'].clear()
        self.assertEqual(self.store.retention_plan([self.ref])['rows'][0]['action'],'retain')

    def test_reference_retention_declaration_protected(self):
        self.register()
        for policy in ('pinned','referenced'):
            r=copy.deepcopy(self.ref); r['retention']=policy
            self.assertEqual(self.store.retention_plan([r])['rows'][0]['action'],'retain')

    def test_dry_run_only_and_interrupted_review(self):
        self.register()
        before=(self.store.directory/self.digest).read_bytes()
        plan=self.store.retention_plan([self.ref])
        self.assertEqual(plan['rows'][0]['action'],'propose_delete')
        self.assertEqual(plan['rows'][0]['recoverability'],'not_established')
        self.assertTrue(plan['dry_run'])
        self.assertEqual(plan,self.store.recheck_plan(plan,[self.ref]))
        self.assertEqual((self.store.directory/self.digest).read_bytes(),before)
        self.assertFalse(hasattr(self.store,'delete'))

    def test_interrupted_lock_fails_closed(self):
        lock=self.store.directory/'.writer-lock'; lock.write_bytes(b'')
        with self.assertRaises(ArtifactBusy): self.store.retention_plan([])
        self.assertTrue(lock.exists())

    def test_incomplete_or_malformed_graph_fails_closed(self):
        for field,value in [('complete',False),('leases',[dict(sha256=self.digest,owner='x',active=None)]),('ownership',{self.digest:'guessed'})]:
            old=self.graph[field]; self.graph[field]=value
            with self.assertRaises(ArtifactError): self.store.retention_plan([])
            self.graph[field]=old
        self.assertFalse((self.store.directory/'.writer-lock').exists())

    def test_unknown_storage_entries_block_writes(self):
        (self.store.directory/'unexpected').write_bytes(b'preserve')
        with self.assertRaises(ArtifactError): self.register()
        self.assertEqual((self.store.directory/'unexpected').read_bytes(),b'preserve')

    def test_restore_from_retained_identical_source(self):
        source=self.base/'retained'; source.write_bytes(self.data)
        restored=self.store.restore(self.ref,source)
        self.assertEqual(restored['integrity'],'verified')
        self.assertEqual(source.read_bytes(),self.data)
        self.assertEqual(self.store.resolve(self.ref)['data'],self.data)

    def test_restore_rejects_wrong_source_without_overwrite(self):
        source=self.base/'retained'; source.write_bytes(b'z'*len(self.data))
        with self.assertRaises(ArtifactError): self.store.restore(self.ref,source)
        self.assertFalse((self.store.directory/self.digest).exists())

    def test_worker_copy_mutation_is_isolated(self):
        self.register(); dest=self.base/'worker.bin'
        self.store.worker_copy(self.ref,dest,budget_bytes=64)
        dest.write_bytes(b'adapter changed this')
        self.assertEqual(self.store.resolve(self.ref)['data'],self.data)
        with self.assertRaises(FileExistsError): self.store.worker_copy(self.ref,dest,budget_bytes=64)
        with self.assertRaises(ArtifactError): self.store.worker_copy(self.ref,self.store.directory/'worker',budget_bytes=64)
        with self.assertRaises(ArtifactError): self.store.worker_copy(self.ref,self.base/'another',budget_bytes=1)

    def test_build_role_checked_against_contract(self):
        self.register()
        fixture=json.loads((Path(__file__).parent/'fixtures/runtime_coverage/conformance.json').read_text())
        binding=fixture['connectors']['RunBinding']; binding['artifacts']['rom']=self.digest
        self.assertTrue(self.store.retained_build(binding,'rom',self.ref)['available'])
        with self.assertRaises(ArtifactError): self.store.retained_build(binding,'absent',self.ref)

    def test_missing_graph_reference_visible(self):
        self.graph['references']=[dict(sha256=self.digest,kind='failure',id='failed-run')]
        row=self.store.retention_plan([])['rows'][0]
        self.assertEqual(row['integrity'],'missing'); self.assertEqual(row['action'],'retain')
        self.assertIsNone(row['byte_length'])

    def test_duplicate_evidence_identity_rejected(self):
        with self.assertRaises(ArtifactError): self.store.retention_plan([self.ref,self.ref])

    def test_path_traversal_rejected(self):
        r=copy.deepcopy(self.ref); r['sha256']='../outside'
        with self.assertRaises(ValueError): self.store.resolve(r)

    def test_symlink_storage_is_rejected(self):
        target=self.base/'target'; target.mkdir()
        link=self.base/'link'
        try: link.symlink_to(target,target_is_directory=True)
        except OSError: self.skipTest('Symlink creation unavailable on this host')
        with self.assertRaises(ArtifactError): RuntimeArtifacts(link,budget_bytes=24,graph_guard=self.guard)



    def test_optional_read_guard_never_supplies_mutation_or_retention_authority(self):
        self.register();calls=[]
        @contextmanager
        def read_guard():
            calls.append('read')
            self.assertTrue((self.store.directory/'.writer-lock').exists())
            yield None
        self.store.read_guard=read_guard
        self.graph['complete']=False
        self.assertEqual(self.store.resolve(self.ref)['data'],self.data)
        for operation in (self.register,lambda:self.store.budget(0),lambda:self.store.retention_plan([self.ref])):
            with self.assertRaises(ArtifactError):operation()
        self.assertEqual(calls,['read'])
        self.assertFalse((self.store.directory/'.writer-lock').exists())

    def test_optional_read_guard_preserves_directory_writer_exclusion(self):
        self.register()
        @contextmanager
        def read_guard():
            # Even a second service instance cannot write during detached-byte resolution.
            with self.assertRaises(ArtifactBusy):self.register()
            yield None
        self.store.read_guard=read_guard
        self.assertEqual(self.store.resolve(self.ref)['data'],self.data)
        lock=self.store.directory/'.writer-lock';lock.write_bytes(b'')
        with self.assertRaises(ArtifactBusy):self.store.resolve(self.ref)
        self.assertTrue(lock.exists());lock.unlink()

    def test_invalid_optional_read_guard_is_refused(self):
        for bad in (True,False,1,object()):
            with self.subTest(bad=type(bad).__name__),self.assertRaises(ArtifactError):
                RuntimeArtifacts(self.base/'invalid-read-guard',budget_bytes=1,graph_guard=self.guard,read_guard=bad)
        self.assertFalse((self.base/'invalid-read-guard').exists())

if __name__ == '__main__': unittest.main()

"""Synthetic builder lifecycles, competing requests and immutable project inputs."""
import json
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import test_studio_projects as selection_tests
from test_state import invented
from patchquest.jobs import Jobs, BuildWorker
from patchquest.state import Conflict
from patchquest.studio_builders import BuilderBinding, StudioBuilders


class BuilderTests(unittest.TestCase):
    close_server = selection_tests.ProjectSelectionTests.close_server
    request = selection_tests.ProjectSelectionTests.request

    def setUp(self):
        selection_tests.ProjectSelectionTests.setUp(self)
        self.entered = threading.Event()
        self.release = threading.Event()
        self.release.set()
        self.addCleanup(self.release.set)
        self.calls = []

        def pipeline(index):
            def run(job, progress):
                self.calls.append((index, job['snapshot']))
                progress('Checking invented saved revisions')
                self.entered.set()
                if not self.release.wait(10):
                    raise ValueError('Synthetic test timed out')
                return {'status':'validated', 'approval':{'approved':False}, 'snapshot':job['snapshot']}
            return run

        self.manager = StudioBuilders(self.server.projects, [
            BuilderBinding(s.manifest_path, pipeline(i), f'Invented builder {i}')
            for i, s in enumerate(self.stores)])
        self.server.builders = self.manager
        self.manager.switch(self.keys[0], self.manager.version)

    def status(self, index=1):
        code, raw = self.request('/api/builder-status', self.keys[index])
        self.assertEqual(code, 200, raw)
        return json.loads(raw)

    def switch(self, index=1, expected=None):
        expected = self.status(index)['version'] if expected is None else expected
        return self.request('/api/builder-switch', self.keys[index], {'expected':expected})

    def wait_done(self, index):
        for _ in range(100):
            rows = Jobs(self.stores[index]).list()
            if rows and rows[0]['status'] == 'validated':
                return rows[0]
            time.sleep(.03)
        self.fail('Synthetic build did not finish')

    def test_status_and_mutations_require_auth_origin_and_explicit_targets(self):
        state = self.status()
        self.assertEqual(state['workers'][0]['id'], self.keys[0])
        self.assertTrue(state['workers'][0]['managed'])
        self.assertIsNone(state['workers'][0]['job'])
        self.assertTrue(state['can_switch'])
        self.assertNotIn(str(self.root), json.dumps(state))
        for route, body in [('/api/builder-status',None),('/api/builder-switch',{'expected':state['version']})]:
            self.assertEqual(self.request(route, self.keys[1], body, authorized=False)[0],401)
            self.assertEqual(self.request(route, self.keys[1], body, headers={'Origin':'https://foreign.invalid'})[0],403)
            self.assertEqual(self.request(route,'unknown',body)[0],404)
        for body in ({}, {'expected':state['version'],'command':'anything'}, {'expected':state['version'],'project':self.keys[0]}):
            self.assertEqual(self.request('/api/builder-switch',self.keys[1],body)[0],400)
        self.assertEqual(self.request('/api/builder-status?command=anything',self.keys[1])[0],400)
        self.assertEqual(self.manager.active,self.keys[0])

    def test_switch_and_target_build_preserve_corrections_and_snapshots(self):
        self.stores[0].put(invented(target='Protected harbor correction'),1,'human')
        before = [s.snapshot() for s in self.stores]
        self.assertEqual(self.switch()[0],200)
        self.assertFalse(Jobs(self.stores[0]).capabilities()['available'])
        self.assertTrue(Jobs(self.stores[1]).capabilities()['available'])
        self.assertEqual(self.calls,[])  # Loading never builds anything.
        job = Jobs(self.stores[1]).submit('invented-garden-build')
        result = self.wait_done(1)
        self.assertEqual(self.calls,[(1,job['snapshot'])])
        self.assertFalse(result['payload']['result']['approval']['approved'])
        self.assertEqual(before,[s.snapshot() for s in self.stores])
        self.assertTrue(self.stores[0].get('line-01')['human_corrected'])
        self.assertEqual(self.switch(0)[0],200)
        self.assertEqual(Jobs(self.stores[1]).list()[0]['id'],job['id'])

    def test_running_build_reports_stage_and_prevents_switch(self):
        self.release.clear()
        job = Jobs(self.stores[0]).submit('invented-running-build')
        self.assertTrue(self.entered.wait(5))
        state = self.status()
        self.assertFalse(state['can_switch'])
        self.assertEqual(state['workers'][0]['job'],dict(id=job['id'],status='running',stage='Checking invented saved revisions'))
        self.assertEqual(self.switch()[0],409)
        self.assertEqual(self.manager.active,self.keys[0])
        self.release.set()
        self.wait_done(0)
        self.assertEqual(self.switch()[0],200)

    def test_queued_job_blocks_atomic_release(self):
        self.manager.worker.close_if_idle()
        jobs = Jobs(self.stores[0]); jobs.register('paused-worker','Synthetic paused worker')
        jobs.submit('invented-queued-build')
        with self.assertRaises(Conflict):jobs.release_idle('paused-worker')
        self.assertTrue(jobs.capabilities()['available'])
        self.assertEqual(jobs.list()[0]['status'],'queued')
        jobs.unregister('paused-worker')
        self.manager.worker=None; self.manager.active=None

    def test_unconfigured_target_keeps_current_builder(self):
        del self.manager.bindings[self.keys[1]]
        version=self.status()['version']
        self.assertFalse(self.status()['selected']['configured'])
        self.assertEqual(self.switch()[0],409)
        self.assertEqual(self.manager.version,version)
        self.assertTrue(Jobs(self.stores[0]).capabilities()['available'])

    def test_external_worker_and_orphaned_queue_are_never_taken_over(self):
        jobs=Jobs(self.stores[1]);jobs.register('external','Separate launcher')
        self.assertFalse(self.status()['selected']['managed'])
        self.assertEqual(self.switch()[0],409)
        jobs.submit('invented-orphan-queue');jobs.unregister('external')
        self.assertFalse(self.status()['can_switch'])
        self.assertEqual(self.switch()[0],409)
        self.assertEqual(jobs.list()[0]['status'],'queued')
        self.assertEqual(self.calls,[])

    def test_stale_tab_and_competing_switches(self):
        version=self.status()['version']
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:self.switch(expected=version)[0],range(2)))
        self.assertEqual(sorted(results),[200,409])
        self.assertEqual(self.switch(0,expected=version)[0],409)
        self.assertEqual(self.manager.active,self.keys[1])

    def test_submission_race_never_strands_a_queued_build(self):
        self.release.clear()
        for i in range(12):
            if self.manager.active!=self.keys[0]:self.assertEqual(self.switch(0)[0],200)
            barrier=threading.Barrier(2)
            version=self.manager.version
            def submit():
                barrier.wait()
                try:return Jobs(self.stores[0]).submit(f'invented-race-{i:03}')['id']
                except Conflict:return None
            def switch():
                barrier.wait()
                try:self.manager.switch(self.keys[1],version);return True
                except Conflict:return False
            with ThreadPoolExecutor(max_workers=2) as pool:
                a=pool.submit(submit);b=pool.submit(switch)
                submitted,switched=a.result(),b.result()
            self.assertNotEqual(bool(submitted),switched)
            if submitted:
                self.assertTrue(Jobs(self.stores[0]).capabilities()['available'])
                self.release.set();self.wait_done(0);self.release.clear()

    def test_target_start_failure_restores_previous_worker(self):
        real_start=self.manager._start
        def fail_target(key):
            if key==self.keys[1]:raise OSError('Private machine path must not leak')
            return real_start(key)
        with patch.object(self.manager,'_start',side_effect=fail_target):
            code,raw=self.switch()
        self.assertEqual(code,409)
        self.assertIn('previous builder was restored',raw.decode())
        self.assertNotIn('Private machine path',raw.decode())
        self.assertEqual(self.manager.active,self.keys[0])
        self.assertTrue(Jobs(self.stores[0]).capabilities()['available'])

    def test_partial_thread_start_failure_cleans_registration(self):
        self.manager.close()
        worker=BuildWorker(self.stores[0],lambda job,progress:None)
        with patch('threading.Thread.start',side_effect=RuntimeError('Synthetic thread failure')):
            with self.assertRaises(RuntimeError):worker.start(require_idle=True)
        self.assertFalse(Jobs(self.stores[0]).capabilities()['available'])
        self.assertEqual(self.switch()[0],200)

    def test_loading_from_idle_empty_session_and_failed_rollback(self):
        self.manager.close()
        self.assertEqual(self.status()['workers'],[])
        self.assertEqual(self.switch()[0],200)
        with patch.object(self.manager,'_start',side_effect=OSError('Synthetic failure')):
            self.assertEqual(self.switch(0)[0],409)
        self.assertEqual(self.status()['workers'],[])
        self.assertIsNone(self.manager.worker)
        self.assertEqual(self.switch(0)[0],200)

    def test_target_claim_race_preserves_external_worker_and_restores_current(self):
        real_start=self.manager._start
        def race(key):
            if key==self.keys[1]:Jobs(self.stores[1]).register('external','Competing launcher')
            return real_start(key)
        with patch.object(self.manager,'_start',side_effect=race):
            self.assertEqual(self.switch()[0],409)
        self.assertEqual(Jobs(self.stores[1]).capabilities()['worker'],'Competing launcher')
        self.assertEqual(self.manager.active,self.keys[0])


if __name__=='__main__':unittest.main()

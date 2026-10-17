import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor

from _bootstrap import ROOT
from test_state import project, invented
from patchquest.state import Store, Conflict
from patchquest.jobs import Jobs, BuildWorker


class JobTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(project(Path(self.temp.name)));self.store.put(invented(),0)
        self.jobs=Jobs(self.store)

    def test_submit_is_idempotent_serial_and_freezes_revisions(self):
        with self.assertRaises(Conflict):self.jobs.submit('request-0001')
        self.jobs.register('owner','Invented pipeline')
        first=self.jobs.submit('request-0001')
        self.store.put(invented(target='Later edit'),1,'human')
        self.assertEqual(self.jobs.submit('request-0001')['snapshot'],first['snapshot'])
        frozen=json.loads(Path(self.store.export_snapshot(first['snapshot'])).read_text(encoding='utf8'))
        self.assertEqual(frozen['records'][0]['target'],invented()['target'])
        with self.assertRaises(Conflict):self.jobs.submit('request-0002')
        with self.assertRaises(ValueError):self.jobs.submit('../../escape')
        with self.assertRaises(ValueError):self.jobs.submit('request-0003',mode='shell')
        with self.assertRaises(Conflict):self.jobs.register('another','Other worker')

    def test_two_clicks_cannot_start_two_jobs(self):
        self.jobs.register('owner','Invented pipeline')
        def submit(i):
            try:return self.jobs.submit('request-'+str(i).zfill(4))['status']
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,(1,2)))
        self.assertEqual(sorted(results),['conflict','queued'])

    def test_restart_marks_abandoned_running_job_and_retains_queue(self):
        self.jobs.register('old-worker','Old')
        self.jobs.submit('request-0001');self.jobs.claim('old-worker')
        with self.store.connection() as db:db.execute('UPDATE build_worker SET expires=0')
        reopened=Jobs(Store(self.store.context.root/'project.json'));reopened.register('new-worker','New')
        self.assertEqual(reopened.list()[0]['status'],'interrupted')
        self.assertIsNone(reopened.claim('new-worker'))
        with self.assertRaises(Conflict):reopened.update('request-0001','old-worker','Done','validated',{'status':'validated'})
        reopened.submit('request-0002');reopened.unregister('new-worker')
        reopened.register('third-worker','Restarted')
        self.assertEqual(reopened.claim('third-worker')['id'],'request-0002')

    def test_worker_failure_progress_and_retry_preserve_snapshot(self):
        entered=threading.Event();release=threading.Event();self.addCleanup(release.set)
        def pipeline(job,progress):
            progress('Synthetic validation stage');entered.set();release.wait(5)
            if job['id']=='request-0001':raise ValueError('Synthetic layout limit exceeded')
            return {'status':'validated','approval':{'approved':False},'artifacts':{'example':'invented output'}}
        worker=BuildWorker(self.store,pipeline).start();self.addCleanup(worker.close)
        first=self.jobs.submit('request-0001');self.assertTrue(entered.wait(5))
        self.assertEqual(self.jobs.list()[0]['payload']['stage'],'Synthetic validation stage')
        self.store.put(invented(target='Newer wording'),1,'human');release.set()
        self.wait_status('failed')
        row=self.jobs.list()[0];self.assertEqual(row['snapshot'],first['snapshot'])
        self.assertIn('Synthetic layout limit',row['payload']['error']['message'])
        self.assertTrue(Path(row['payload']['error']['log']).is_file())
        second=self.jobs.submit('request-0002');self.assertNotEqual(second['snapshot'],first['snapshot'])
        self.wait_status('validated')
        self.assertFalse(self.jobs.list()[0]['payload']['result']['approval']['approved'])

    def wait_status(self,status):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if self.jobs.list()[0]['status']==status:return
            time.sleep(.02)
        self.fail('Job did not reach '+status)

    def test_graceful_close_keeps_heartbeat_until_callback_finishes(self):
        entered=threading.Event();release=threading.Event()
        def pipeline(job,progress):
            entered.set();release.wait(5)
            progress('Final validation')
            return {'status':'validated','approval':{'approved':False}}
        worker=BuildWorker(self.store,pipeline).start();self.addCleanup(worker.close)
        self.jobs.submit('request-0001');self.assertTrue(entered.wait(5))
        closing=threading.Thread(target=worker.close);closing.start()
        try:
            self.assertTrue(closing.is_alive());self.assertTrue(self.jobs.capabilities()['available'])
        finally:release.set();closing.join(5)
        self.assertFalse(closing.is_alive());self.assertEqual(self.jobs.list()[0]['status'],'validated')
        self.assertFalse(self.jobs.capabilities()['available'])

    def test_unexpected_loop_failure_does_not_leave_online_worker(self):
        worker=BuildWorker(self.store,lambda *_:None)
        def fail_claim(owner):raise RuntimeError('Synthetic storage failure')
        worker.jobs.claim=fail_claim;worker.start();self.addCleanup(worker.close)
        worker.thread.join(5)
        self.assertIsInstance(worker.failure,RuntimeError)
        self.assertFalse(self.jobs.capabilities()['available'])


if __name__=='__main__':unittest.main()

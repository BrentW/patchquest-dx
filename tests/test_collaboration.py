import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from _bootstrap import ROOT
from test_state import project, invented
from patchquest.state import Store, Conflict
from patchquest.collaboration import Coordination
from patchquest.state_api import execute


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.manifest=project(Path(self.temp.name));self.store=Store(self.manifest)
        self.store.put(invented(),0);self.store.put(invented(key='second'),0)
        self.work=Coordination(self.store)
        self.a=self.work.start('codex',model='synthetic-model')['session']
        self.b=self.work.start('claude-code',model='synthetic-model')['session']

    def task(self,key='task-one',records=None,**kw):
        return self.work.create(key,'Invented review',record_ids=records or ['line-01'],**kw)

    def publish(self,lease,target='New wording',expected=1,key='line-01'):
        return self.work.publish(lease['owner'],lease['id'],lease['fence'],[{'id':key,'target':target,'expected':expected}])

    def test_real_processes_compete_for_one_claim(self):
        self.task()
        def claim(session):
            r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/patchquest.py'),'state',str(self.manifest),'work-claim','--input','-'],input=json.dumps({'session':session,'key':'task-one'}),text=True,capture_output=True)
            return r.returncode,json.loads(r.stdout)
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(claim,[self.a,self.b]))
        self.assertEqual(sorted(r[0] for r in results),[0,3])
        self.assertEqual(len([r for r in self.work.list() if r['status']=='leased']),1)

    def test_disjoint_work_and_shared_resource_conflict(self):
        self.task(resources=['shared-font']);self.task('task-two',['second'],resources=['shared-font'])
        one=self.work.claim(self.a,'task-one')
        with self.assertRaises(Conflict):self.work.claim(self.b,'task-two')
        self.work.finish(self.a,one['id'],one['fence'],handoff='Font read complete')
        two=self.work.claim(self.b,'task-two');self.publish(two,key='second')
        self.task('task-three');self.assertIsNotNone(self.work.claim(self.a,'task-three'))

    def test_human_edit_wins_and_agent_alternative_is_only_proposal(self):
        self.task();lease=self.work.claim(self.a,'task-one')
        self.store.put(invented(target='Human wording'),1,'human')
        with self.assertRaises(Conflict):self.publish(lease)
        result=self.publish(lease,expected=2)
        self.assertEqual(result['results'][0]['outcome'],'proposed')
        self.assertEqual(self.store.get('line-01')['target'],'Human wording')
        self.assertEqual(len(self.store.proposals('line-01')),1)
        self.assertEqual(self.store.memory(key='second')[0]['target'],'Human wording')

    def test_atomic_batch_rejects_stale_or_out_of_scope(self):
        self.task(records=['line-01','second']);lease=self.work.claim(self.a,'task-one')
        self.store.put(invented(key='second',target='Human second'),1,'human')
        with self.assertRaises(Conflict):self.work.publish(self.a,lease['id'],lease['fence'],[
            {'id':'line-01','target':'Must roll back','expected':1},{'id':'second','target':'Stale','expected':1}])
        self.assertEqual(self.store.get('line-01')['revision'],1)
        with self.assertRaises(ValueError):self.publish(lease,key='unknown')
        with self.assertRaises(ValueError):self.work.publish(self.a,lease['id'],lease['fence'],[{'id':'line-01','expected':1,'target':'x','controls':[]}])

    def test_expiry_fences_stale_agent_and_unmanaged_bypass(self):
        self.task();old=self.work.claim(self.a,'task-one')
        with self.store.connection() as db:db.execute('UPDATE work_items SET expires=0')
        new=self.work.claim(self.b,'task-one');self.assertGreater(new['fence'],old['fence'])
        for fn in [lambda:self.publish(old),lambda:self.work.renew(self.a,old['id'],old['fence']),lambda:self.work.finish(self.a,old['id'],old['fence'])]:
            with self.assertRaises(Conflict):fn()
        self.work.finish(self.b,new['id'],new['fence'])
        with self.assertRaises(Conflict):self.store.put(invented(target='Unfenced late write'),1)
        self.store.put(invented(target='Human override'),1,'human')
        self.assertTrue(self.store.get('line-01')['human_corrected'])

    def test_dependencies_priority_handoff_and_close(self):
        self.task();self.task('dependent',['second'],dependencies=['task-one'],priority=100)
        lease=self.work.claim(self.a);self.assertEqual(lease['id'],'task-one')
        self.assertIsNone(self.work.claim(self.b))
        blocked=self.work.finish(self.a,lease['id'],lease['fence'],'blocked','Needs contextual evidence')
        self.assertIsNone(self.work.claim(self.b))
        with self.assertRaises(Conflict):self.work.resolve('task-one',blocked['revision']-1,'queued','New evidence')
        self.work.resolve('task-one',blocked['revision'],'queued','New evidence available')
        one=self.work.claim(self.b);self.assertIn('evidence',one['payload']['handoff'])
        self.work.finish(self.b,one['id'],one['fence'])
        two=self.work.claim(self.a);self.assertEqual(two['id'],'dependent')
        self.work.close(self.a);self.assertEqual(self.work.list()[1]['status'],'queued')
        with self.assertRaises(Conflict):self.work.heartbeat(self.a)
        self.assertGreaterEqual(len(self.work.history('task-one')),5)

    def test_restart_and_session_expiry_are_durable(self):
        self.task();old=self.work.claim(self.a,'task-one')
        with self.store.connection() as db:db.execute('UPDATE agent_sessions SET expires=0 WHERE id=?',(self.a,))
        reopened=Coordination(Store(self.manifest));self.assertEqual(reopened.list()[0]['status'],'queued')
        with self.assertRaises(Conflict):reopened.renew(self.a,old['id'],old['fence'])
        new=reopened.claim(self.b,'task-one');self.assertGreater(new['fence'],old['fence'])

    def test_claims_do_not_change_build_snapshot_and_publish_does(self):
        before=self.store.snapshot()['sha256'];self.task();lease=self.work.claim(self.a,'task-one')
        self.assertEqual(self.store.snapshot()['sha256'],before)
        self.publish(lease)
        self.assertNotEqual(self.store.snapshot()['sha256'],before)
        frozen=json.loads(Path(self.store.export_snapshot(before)).read_text(encoding='utf8'))
        self.assertEqual(frozen['records'][0]['target'],invented()['target'])

    def test_schema_two_upgrade_preserves_history_and_snapshot(self):
        self.store.put(invented(target='Human migration wording'),1,'human')
        frozen=self.store.snapshot()['sha256'];history=self.store.history('line-01')
        with self.store.connection() as db:
            for table in ('agent_sessions','work_items','work_history','work_managed'):
                db.execute('DROP TABLE '+table)
            db.execute('PRAGMA user_version=2')
        upgraded=Store(self.manifest)
        self.assertEqual(upgraded.snapshot()['sha256'],frozen)
        self.assertEqual(upgraded.history('line-01'),history)
        self.assertTrue(upgraded.get('line-01')['human_corrected'])
        self.assertEqual(Coordination(upgraded).list(),[])
        with upgraded.connection() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)

    def test_terminal_dependencies_cannot_be_reopened(self):
        self.task();lease=self.work.claim(self.a,'task-one')
        done=self.work.finish(self.a,lease['id'],lease['fence'])
        with self.assertRaises(Conflict):self.work.resolve(done['id'],done['revision'],'queued','Redo')
        self.task('cancel-me',['second'])
        task=next(t for t in self.work.list() if t['id']=='cancel-me')
        cancelled=self.work.resolve(task['id'],task['revision'],'cancelled','Scope no longer needed')
        with self.assertRaises(Conflict):self.work.resolve(cancelled['id'],cancelled['revision'],'queued','Redo')
        with self.assertRaises(ValueError):self.work.create('invalid','Invalid',record_ids='',resources=['thing'])

    def test_context_and_cli_match_shared_contract(self):
        packet=execute(self.store,'agent-context')
        self.assertIn('work-publish',packet['write_actions'])
        self.assertIn('build-submit',packet['write_actions'])
        self.assertTrue(any(Path(p['path']).parts[-2:]==('translation-collaboration','SKILL.md') for p in packet['instructions']))
        with self.assertRaises(ValueError):self.work.create('bad','Bad',record_ids=['line-01'],dependencies=['not-yet-created'])
        for value in [0,29,3601,True]:
            with self.assertRaises(ValueError):self.work.start('codex',lease_seconds=value)


if __name__=='__main__':unittest.main()

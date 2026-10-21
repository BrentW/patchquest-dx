"""Independently invented source-interpretation migrations; no private data."""
import json
from pathlib import Path
import tempfile
import unittest
from _bootstrap import ROOT
from test_state import project,invented
from patchquest.state import Store,Conflict
from patchquest.collaboration import Coordination
from patchquest.state_api import execute,WRITE_ACTIONS


class SourceRevisionTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.store=Store(project(Path(tmp.name)))
        for key in ('line-01','line-02'):
            self.store.put(dict(invented(key),decoded=False,source_ref={'fixture':'invented text'}),0)
        self.work=Coordination(self.store);self.session=self.work.start('synthetic')['session']
        self.work.create('decode','Interpret synthetic source',record_ids=['line-01','line-02'])
        self.lease=self.work.claim(self.session,'decode')

    def change(self,key='line-01',expected=1,**patch):
        return {'id':key,'expected':expected,'source_patch':patch or {'decoded':True}}

    def apply(self,changes=None,**overrides):
        args={'session':self.session,'key':'decode','fence':self.lease['fence'],
              'changes':changes or [self.change()],'reason':'Synthetic decoder evidence reviewed.','source_revision':True}
        args.update(overrides)
        return execute(self.store,'work-publish',args)

    def test_revision_history_snapshot_and_immutable_fields(self):
        before=self.store.get('line-01');snap=self.store.snapshot()['sha256']
        self.assertIn('work-publish',WRITE_ACTIONS)
        self.apply([self.change(source='The invented lamp is ready.',decoded=True,controls=[],context={'evidence':'invented fixture'})])
        after=self.store.get('line-01');self.assertEqual(after['revision'],2)
        for field in ('target','source_ref','build_binding','uncertainty','speaker','scene','category'):
            self.assertEqual(after[field],before[field])
        self.assertNotEqual(snap,self.store.snapshot()['sha256'])
        frozen=json.loads(Path(self.store.export_snapshot(snap)).read_text(encoding='utf8'))
        self.assertFalse(frozen['records'][0]['decoded'])
        self.assertEqual(len(self.store.history('line-01')),2)
        self.assertEqual(self.apply([self.change(expected=2,source=after['source'],decoded=True,controls=[],context=after['context'])])['results'][0]['outcome'],'unchanged')

    def test_protected_correction_is_inactive_source_proposal(self):
        current=self.store.get('line-01');data={k:v for k,v in current.items() if k not in ('revision','human_corrected','provenance')}
        data['target']='Protected human wording';self.store.put(data,1,'human')
        with self.assertRaises(Conflict):self.apply()
        result=self.apply([self.change(expected=2)])
        self.assertEqual(result['results'][0]['outcome'],'proposed')
        after=self.store.get('line-01');self.assertFalse(after['decoded']);self.assertEqual(after['revision'],2)
        proposal=self.store.proposals('line-01')[0]['payload']
        self.assertTrue(proposal['decoded']);self.assertEqual(proposal['target'],'Protected human wording')

    def test_atomic_scope_revision_validation_and_field_rejection(self):
        bad=[self.change(key='outside'),self.change(expected=99),self.change(decoded='yes')]
        bad += [self.change(**{key:'forbidden'}) for key in ('target','source_ref','build_binding','id','uncertainty')]
        for second in bad:
            # Different second record is important: rejection must roll back first.
            if second['id']=='line-01':second['id']='line-02'
            with self.assertRaises((ValueError,Conflict)):
                self.apply([self.change(),second])
            self.assertEqual(self.store.get('line-01')['revision'],1)
        with self.assertRaises(ValueError):self.apply([self.change(),self.change()])
        with self.assertRaises(ValueError):self.apply(reason=' ')
        with self.assertRaises(ValueError):self.apply(source_revision=1)
        with self.assertRaises(ValueError):self.apply(source_revision=False)

    def test_stale_fence_closed_session_and_expired_lease(self):
        with self.assertRaises(Conflict):self.apply(fence=self.lease['fence']+1)
        with self.store.connection() as db:db.execute('UPDATE work_items SET expires=0')
        with self.assertRaises(Conflict):self.apply()
        self.work.close(self.session)
        with self.assertRaises(Conflict):self.apply()
        self.assertEqual(self.store.get('line-01')['revision'],1)


if __name__=='__main__':unittest.main()

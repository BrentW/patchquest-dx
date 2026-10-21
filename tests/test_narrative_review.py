"""Independent fictional clue and context; no game files or external inference."""
import copy
import http.client
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, PIXEL
from patchquest.state import Store, Conflict, record_data
from patchquest.state_api import execute, READ_ACTIONS, WRITE_ACTIONS
from patchquest.collaboration import Coordination
from patchquest import narrative_review as review


SOURCE = '青い灯が消えていない時だけ、二番目の扉を開けて。'
BAD = 'Open the second door only when the blue light is off.'
GOOD = 'Open the second door only while the blue light is still on.'


def finding():
    checks = {name: dict(status='unknown', reason='Not established from this small sample.') for name in review.CHECKS}
    for name in ('meaning', 'clue', 'condition', 'negation', 'puzzle_answer'):
        checks[name] = dict(status='concern', reason='The current wording reverses the lamp condition and changes when the door should open.')
    checks['number'] = dict(status='consistent', reason='The second door remains the second door.')
    return dict(source_span='消えていない', source_reason='The negation means the lamp has not gone out. The fluent draft reverses the fictional puzzle condition.', uncertainty='Speaker intent beyond the literal condition is unknown.', checks=checks)


class NarrativeReviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name); self.manifest = project(self.root); self.store = Store(self.manifest)
        self.store.put(dict(id='clue', source=SOURCE, target=BAD), 0)
        self.store.put(dict(id='neighbor', source='灯を見て。', target='Watch the light.'), 0)
        self.store.put(dict(id='gloss', kind='glossary', source='灯', target='light'), 0)
        self.inputs = dict(record_ids=['clue'], adjacent_ids=['neighbor'], glossary_ids=['gloss'],
            functional_requirements={'clue': dict(basis='Authored synthetic puzzle rule.', description='Door 2 opens only if blue lamp is on.')},
            layout_constraints={'clue': dict(basis='Invented adapter limit.', description='Two pages of 96 pixels; measure before insertion.')})

    def create(self, key='sample', budget=None):
        ctx = review.context(self.store, self.inputs)
        return review.create(self.store, key, self.inputs, ctx['token'], 'Synthetic reviewer', budget)

    def propose(self, key='sample', expected=1):
        return review.propose(self.store, key, expected, 'clue', GOOD, finding(), 'Synthetic reviewer')

    def accept(self):
        self.create(); r = self.propose(); seq = r['proposals'][0]['seq']
        review.decide(self.store, 'sample', 2, seq, 'accepted', 'Restores the authored lamp condition.', 'Synthetic reviewer')
        return seq

    def change(self, key, **fields):
        row = self.store.get(key)
        data = {k:v for k,v in row.items() if k not in ('revision','human_corrected','provenance')}
        return self.store.put(dict(data, **fields), row['revision'], 'human')

    def install_guide(self):
        data = json.loads((ROOT/'templates/project/narrative.example.json').read_text(encoding='utf8'))
        data['source_sha256'] = self.store.context.manifest['source']['sha256']
        path = self.root/'guide.json'; path.write_text(json.dumps(data), encoding='utf8')
        manifest = json.loads(self.manifest.read_text()); manifest['resources']['narrative_context'] = path.name
        self.manifest.write_text(json.dumps(manifest))
        return path

    def test_package_is_scoped_versioned_and_honest_about_unknowns(self):
        before = self.store.snapshot()['sha256']; ctx = review.context(self.store, self.inputs)
        p = ctx['package']
        self.assertEqual(set(p['records']), {'clue','neighbor','gloss'})
        self.assertEqual(p['records']['clue']['revision'], 1)
        self.assertEqual(p['records']['clue']['source'], SOURCE)
        self.assertEqual(p['narrative']['status'], 'not_configured')
        self.assertTrue(any('speaker unknown' in x for x in p['unknowns']))
        self.assertEqual(before, self.store.snapshot()['sha256'])
        self.assertFalse((self.root/'original.fixture').exists())

    def test_fluent_clue_reversal_is_an_inactive_explained_proposal(self):
        self.create(); before = self.store.snapshot()['sha256']; r = self.propose()
        self.assertEqual(r['proposals'][0]['finding']['checks']['puzzle_answer']['status'], 'concern')
        self.assertEqual(self.store.proposals('clue')[0]['payload']['target'], GOOD)
        self.assertEqual(self.store.get('clue')['target'], BAD)
        self.assertEqual(self.store.snapshot()['sha256'], before)
        self.assertEqual(self.store.record_evidence('clue'), [])

    def test_decisions_retain_reasons_and_history_without_applying(self):
        self.create(); r = self.propose(); seq = r['proposals'][0]['seq']
        for revision, decision in enumerate(('deferred','rejected','accepted'), 2):
            r = review.decide(self.store,'sample',revision,seq,decision,'An explicit editorial explanation.','Reviewer')
        events = review.history(self.store,'sample')
        self.assertEqual([e['review']['proposals'][0]['decision'] for e in events if e['action']=='decision'], ['deferred','rejected','accepted'])
        self.assertEqual(self.store.get('clue')['revision'], 1)
        with self.assertRaises(Conflict):review.decide(self.store,'sample',2,seq,'accepted','Stale decision.','Reviewer')

    def test_apply_requires_separate_authority_and_does_not_allow_human_override(self):
        seq = self.accept()
        with self.assertRaises(ValueError):review.apply(self.store,'sample',3,seq,'Reviewer')
        saved = review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)
        self.assertEqual(saved['outcome'],'saved'); self.assertEqual(saved['record']['target'],GOOD)
        self.assertEqual(saved['record']['provenance']['role'],'agent')
        self.assertTrue(review.read(self.store,'sample')['stale'])
        self.assertEqual(self.store.record_evidence('clue'), [])

    def test_human_corrections_are_preserved_even_when_accepted(self):
        self.change('clue', target='Protected human wording.')
        seq = self.accept(); before = self.store.snapshot()['sha256']
        self.assertEqual(review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)['outcome'],'protected')
        self.assertEqual(self.store.snapshot()['sha256'],before)
        self.assertEqual(len(self.store.proposals('clue')),1)

    def test_source_target_and_context_changes_make_reviews_stale(self):
        cases = [('clue', {'source':SOURCE+'！'}), ('clue', {'target':'New human text.'}),
                 ('clue', {'context':{'meaning':'New context.'}}),
                 ('neighbor', {'target':'A changed adjacent utterance.'}), ('gloss', {'target':'lamp'})]
        for number,(key,fields) in enumerate(cases):
            name = 'scope-'+str(number); self.create(name); self.change(key,**fields)
            self.assertTrue(review.read(self.store,name)['stale'])
            with self.assertRaises(Conflict):self.propose(name)

    def test_guide_pointer_and_same_revision_byte_change_invalidate(self):
        path = self.install_guide(); self.create()
        self.assertFalse(review.read(self.store,'sample')['stale'])
        path.write_bytes(path.read_bytes()+b' ')
        self.assertTrue(review.read(self.store,'sample')['stale'])
        with self.assertRaises(Conflict):self.propose()
        path.unlink(); self.assertEqual(review.read(self.store,'sample')['input_status'],'unavailable')

    def test_changed_layout_definition_requires_new_context_token(self):
        ctx = review.context(self.store,self.inputs)
        self.inputs['layout_constraints']['clue']['description'] = 'Now a different width.'
        with self.assertRaises(Conflict):review.create(self.store,'sample',self.inputs,ctx['token'],'Reviewer')

    def test_stale_accept_and_apply_rejected_but_defer_explanation_retained(self):
        seq = self.accept(); self.change('neighbor',target='Changed.')
        with self.assertRaises(Conflict):review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)
        with self.assertRaises(Conflict):review.decide(self.store,'sample',3,seq,'accepted','Outdated.','Reviewer')
        review.decide(self.store,'sample',3,seq,'deferred','Context changed; re-review.','Reviewer')
        self.assertEqual(review.read(self.store,'sample')['proposals'][0]['decision'],'deferred')

    def test_concurrent_review_decisions_cannot_lose_history(self):
        self.create(); r=self.propose(); seq=r['proposals'][0]['seq']; barrier=threading.Barrier(2)
        def decide(decision):
            barrier.wait()
            try:review.decide(self.store,'sample',2,seq,decision,'Parallel review reason.','Reviewer');return 'saved'
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(decide,['accepted','rejected'])),['conflict','saved'])
        self.assertEqual(len([e for e in review.history(self.store,'sample') if e['action']=='decision']),1)

    def test_concurrent_human_and_agent_application_never_loses_human_text(self):
        seq=self.accept(); barrier=threading.Barrier(2)
        def human():
            barrier.wait()
            # Read again after a CAS conflict, as an actual correction client must.
            for _ in range(2):
                try:return self.change('clue',target='Final human wording.')
                except Conflict:pass
            self.fail('Human correction could not reconcile')
        def agent():
            barrier.wait()
            try:return review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)['outcome']
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            a=pool.submit(human);b=pool.submit(agent);a.result();b.result()
        self.assertEqual(self.store.get('clue')['target'],'Final human wording.')
        self.assertTrue(self.store.get('clue')['human_corrected'])

    def test_managed_application_requires_live_fence_and_correct_scope(self):
        work=Coordination(self.store); session=work.start('synthetic')['session']
        work.create('task','Review clue',record_ids=['clue']); lease=work.claim(session,'task')
        seq=self.accept()
        with self.assertRaises(Conflict):review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)
        request=dict(session=session,key='task',fence=lease['fence']+1)
        with self.assertRaises(Conflict):review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True,work=request)
        request['fence']=lease['fence']
        self.assertEqual(review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True,work=request)['outcome'],'saved')

    def test_guide_changes_during_apply_roll_back_record_and_task_journal(self):
        self.install_guide(); seq=self.accept(); original=review._guide; calls=[]
        def changed(*args):
            result=original(*args);calls.append(1)
            if len(calls)>1:result['sha256']='f'*64
            return result
        before=self.store.snapshot()['sha256']
        with patch.object(review,'_guide',side_effect=changed),self.assertRaises(Conflict):
            review.apply(self.store,'sample',3,seq,'Reviewer',authorized=True)
        self.assertEqual(self.store.snapshot()['sha256'],before)
        self.assertEqual(review.read(self.store,'sample')['revision'],3)

    def test_screenshot_provenance_integrity_and_association_are_pinned(self):
        pixel=self.root/'synthetic.png';pixel.write_bytes(PIXEL)
        attachment=self.store.attach(pixel,description='Authored synthetic pixel.',record_ids=['clue'])
        self.inputs['screenshots']=[dict(digest=attachment['digest'],runtime_report='',runtime_capture='')]
        r=self.create(); image=r['package']['screenshots'][0]['context']
        self.assertEqual(image['capture']['basis'],'reported')
        self.assertEqual(image['build_association'],'unlinked')
        path=self.store.directory/'evidence'/attachment['digest'];path.write_bytes(b'changed')
        self.assertEqual(review.read(self.store,'sample')['input_status'],'unavailable')
        with self.assertRaises(ValueError):self.propose()

    def test_scope_and_source_based_reason_are_required(self):
        self.create()
        with self.assertRaises(ValueError):review.propose(self.store,'sample',1,'neighbor',GOOD,finding(),'Reviewer')
        f=finding();f['source_span']='not in source'
        with self.assertRaises(ValueError):review.propose(self.store,'sample',1,'clue',GOOD,f,'Reviewer')
        f=finding();del f['checks']['negation']
        with self.assertRaises(ValueError):review.propose(self.store,'sample',1,'clue',GOOD,f,'Reviewer')
        self.assertEqual(self.store.proposals('clue'),[])
        with self.assertRaises(ValueError):review.context(self.store,{'record_ids':[]})

    def test_explicit_store_proposal_is_inactive_and_cas_guarded(self):
        row=record_data(dict(id='clue',source=SOURCE,target=GOOD))
        result=execute(self.store,'propose',dict(data=row,expected=1,actor='Reviewer',reason='Synthetic source-based alternative.'))
        self.assertEqual(result['outcome'],'proposed');self.assertEqual(self.store.get('clue')['revision'],1)
        with self.assertRaises(Conflict):self.store.propose(row,0,reason='Stale.')
        with self.assertRaises(ValueError):self.store.propose(row,1,reason='')

    def test_runtime_binding_uses_actual_selected_artifact_and_record_revisions(self):
        import hashlib
        binding=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']['RunBinding']
        binding=copy.deepcopy(binding)
        snapshot=self.store.snapshot()['sha256']
        path=self.root/'output'/'invented.fixture';path.parent.mkdir();path.write_bytes(b'Independent invented build bytes.')
        self.store.build(dict(id='invented-build',snapshot=snapshot,status='validated',artifacts={'rom':path.name}),0)
        binding.update(build_id='invented-build',snapshot=snapshot,records={'clue':1},artifacts={'rom':hashlib.sha256(path.read_bytes()).hexdigest()})
        self.inputs['run_binding']=binding
        self.create(); self.assertFalse(review.read(self.store,'sample')['stale'])
        path.write_bytes(b'Changed synthetic build.')
        self.assertTrue(review.read(self.store,'sample')['stale'])
        with self.assertRaises(Conflict):self.propose()

    def test_missing_check_reason_and_malformed_budgets_fail_without_writes(self):
        self.create(); f=finding();f['checks']['voice']['reason']=''
        with self.assertRaises(ValueError):review.propose(self.store,'sample',1,'clue',GOOD,f,'Reviewer')
        for value in (float('nan'), -1, True):
            budget=self.budget();budget['max_cost_usd']=value
            with self.assertRaises(ValueError):self.create('bad-budget',budget)
        self.assertEqual(self.store.proposals('clue'),[])

    def test_unaccepted_or_out_of_scope_proposals_cannot_be_applied(self):
        self.create();r=self.propose();seq=r['proposals'][0]['seq']
        with self.assertRaises(Conflict):review.apply(self.store,'sample',2,seq,'Reviewer',authorized=True)
        with self.assertRaises(KeyError):review.apply(self.store,'sample',2,seq+1,'Reviewer',authorized=True)
        self.assertEqual(self.store.get('clue')['revision'],1)

    def budget(self):
        return dict(provider='invented-provider',model='invented-model',authorization_reference='Synthetic fixture authorization.',
                    max_records=1,max_requests=2,max_input_tokens=100,max_output_tokens=50,max_cost_usd=0.02)

    def test_provider_is_optional_and_no_reservation_without_authorization(self):
        self.create()
        with self.assertRaises(ValueError):review.reserve_call(self.store,'sample',1,'call',dict(input_tokens=10,output_tokens=10,cost_usd=0.01),'Reviewer')
        self.assertEqual(review.read(self.store,'sample')['calls'],[])

    def test_provider_caps_unknown_usage_and_refusals_remain_separate(self):
        self.create(budget=self.budget()); maximum=dict(input_tokens=60,output_tokens=40,cost_usd=0.015)
        review.reserve_call(self.store,'sample',1,'call',maximum,'Reviewer')
        review.finish_call(self.store,'sample',2,'call','refused','Reviewer',note='Synthetic provider refusal; no replacement wording.')
        with self.assertRaises(ValueError):review.reserve_call(self.store,'sample',3,'call2',maximum,'Reviewer')
        self.assertEqual(review.read(self.store,'sample')['calls'][0]['usage'],None)
        self.assertEqual(self.store.get('clue')['target'],BAD)
        self.assertEqual(self.store.proposals('clue'),[])

    def test_actual_usage_retained_after_stale_inputs_and_cap_overrun(self):
        self.create(budget=self.budget()); maximum=dict(input_tokens=20,output_tokens=10,cost_usd=0.005)
        review.reserve_call(self.store,'sample',1,'call',maximum,'Reviewer');self.change('neighbor',target='Changed.')
        actual=dict(input_tokens=30,output_tokens=10,cost_usd=0.007)
        r=review.finish_call(self.store,'sample',2,'call','failed','Reviewer',usage=actual,note='Synthetic usage measurement.')
        self.assertTrue(r['calls'][0]['exceeded_reservation']);self.assertEqual(r['calls'][0]['usage'],actual)
        with self.assertRaises(Conflict):review.finish_call(self.store,'sample',3,'call','completed','Reviewer',usage=actual)

    def test_budget_reservations_are_atomic_and_duplicates_are_not_retried(self):
        self.create(budget=self.budget()); maximum=dict(input_tokens=70,output_tokens=40,cost_usd=0.015)
        def reserve(key):
            try:review.reserve_call(self.store,'sample',1,key,maximum,'Reviewer');return 'reserved'
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertEqual(sorted(pool.map(reserve,['a','b'])),['conflict','reserved'])
        r=review.read(self.store,'sample')
        with self.assertRaises(Conflict):review.reserve_call(self.store,'sample',2,r['calls'][0]['id'],maximum,'Reviewer')
        with self.assertRaises(ValueError):review.reserve_call(self.store,'sample',2,'c',maximum,'Reviewer')

    def test_json_api_and_cli_expose_the_same_provider_independent_workflow(self):
        self.assertIn('review-context',READ_ACTIONS);self.assertIn('review-apply',WRITE_ACTIONS)
        ctx=execute(self.store,'review-context',{'inputs':self.inputs})
        execute(self.store,'review-create',dict(key='sample',inputs=self.inputs,context_token=ctx['token'],actor='Reviewer'))
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/patchquest.py'),'state',str(self.manifest),'review-get','--input','-'],
            input=json.dumps({'key':'sample'}),capture_output=True,text=True,encoding='utf8')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['package']['records']['clue']['source'],SOURCE)

    def test_studio_read_views_require_auth_and_do_not_add_write_routes(self):
        from patchquest.studio import StudioServer
        self.create()
        server=StudioServer(self.store,0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            for route in ('review-get','review-history'):
                for authenticated in (False,True):
                    conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                    try:
                        headers={'X-Studio-Token':server.token} if authenticated else {}
                        conn.request('GET','/api/'+route+'?key=sample',headers=headers)
                        response=conn.getresponse();response.read()
                        self.assertEqual(response.status,200 if authenticated else 401)
                    finally:conn.close()
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
            try:
                conn.request('POST','/api/review-apply',body='{}',headers={'X-Studio-Token':server.token,'Content-Type':'application/json'})
                response=conn.getresponse();response.read();self.assertEqual(response.status,404)
            finally:conn.close()
        finally:server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()

"""Invented read-only review and exact-pixel contact-sheet checks."""
from contextlib import contextmanager
import base64
import copy
import hashlib
import json
import re
from pathlib import Path
import time
import threading
import unittest
from unittest import mock

from _bootstrap import ROOT
import test_runtime_coverage as fixtures
from patchquest.runtime_artifacts import RuntimeArtifacts
from patchquest.runtime_artifacts import ArtifactBusy
from patchquest.runtime_artifact_state import ArtifactState
from patchquest.runtime_contracts import ContractError, contract_digest
from patchquest.runtime_review import ReviewProvider, comparison, review_page, write_contact_sheets


@contextmanager
def invented_graph():
    yield dict(revision='invented-review-only-store', complete=True, references=[], pins=[], leases=[], ownership={})


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CoverageTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.group=self.fixture.fixture(actual=True)
        self.store=self.fixture.store
        self.root=self.fixture.root
        self.provider=ReviewProvider(self.store,[self.group],admit_run=self.fixture.proofs.get,
            artifacts=self.fixture, historical_contexts=[dict(candidate_context_id='invented-old-context',
            retained_legacy_execution_status='failed', source_candidate_inventory='private-path-not-for-browser')])

    def resolve(self, ref):
        return self.fixture.resolve(ref)

    def page(self, **params):
        return self.provider.read(self.store,dict(method='automated_runtime',purpose='renderer',**params))

    def test_counts_and_methods_are_copied_without_global_awards_or_writes(self):
        before=self.store.overview();record=self.store.get('greeting')
        page=self.page();source=self.fixture.run_group(self.group)['groups'][0]
        self.assertEqual(page['groups'][0]['binding'],source['report']['binding'])
        for a,b in zip(page['groups'][0]['sections'],source['report']['sections']):
            self.assertEqual(a,{k:v for k,v in b.items() if k!='rows'})
        self.assertEqual(page['items'][0]['status'],'passed')
        self.assertEqual(page['items'][0]['observations'][0]['assertion'],'not_assessed')
        self.assertEqual(page['historical_contexts']['total'],1)
        self.assertEqual(page['historical_contexts']['items'][0]['retained_legacy_execution_status'],'failed')
        self.assertNotIn('source_candidate_inventory',page['historical_contexts']['items'][0])
        self.assertNotIn('admission',json.dumps(page))
        self.assertIsNone(page['global_verified_percent']);self.assertFalse(page['verification_awards'])
        self.assertEqual(self.store.overview(),before);self.assertEqual(self.store.get('greeting'),record)

    def test_current_stale_contexts_do_not_rewrite_original_pass(self):
        old=self.store.get('greeting');fields={k:v for k,v in old.items() if k not in ('revision','human_corrected','provenance')}
        fields['target']='A later invented protected correction.'
        self.store.put(fields,old['revision'],role='human')
        page=self.page(status='stale');item=page['items'][0]
        self.assertEqual(item['status'],'passed');self.assertEqual(item['freshness'],'stale')
        self.assertEqual(item['record_revisions']['greeting'],1)
        self.assertEqual(item['current_revisions']['greeting'],2)
        self.assertEqual(item['observations'][0]['binding']['records']['greeting'],1)

    def test_image_allowlist_checks_selected_project_digest_and_current_bytes(self):
        page=self.page();ref=page['items'][0]['captures'][0]
        self.assertEqual(self.provider.image(self.store,ref['evidence_id'],ref['sha256']),self.fixture.blobs[ref['sha256']])
        for identity,sha in [('unknown',ref['sha256']),(ref['evidence_id'],'0'*64)]:
            with self.assertRaises(ContractError):self.provider.image(self.store,identity,sha)
        other=mock.Mock();other.context.root=self.root/'another-project';other.context.manifest=self.store.context.manifest
        with self.assertRaises(ContractError):self.provider.read(other,{})
        with self.assertRaises(ContractError):self.provider.image(other,ref['evidence_id'],ref['sha256'])
        self.fixture.blobs[ref['sha256']]=b'changed'
        with self.assertRaises(ContractError):self.provider.image(self.store,ref['evidence_id'],ref['sha256'])

    def test_filtered_missing_purpose_remains_untested_and_failed_evidence_stays_failed(self):
        normal=self.provider.read(self.store,{'method':'automated_runtime','purpose':'normal_gameplay'})
        self.assertEqual(normal['items'][0]['status'],'untested');self.assertEqual(normal['items'][0]['captures'],[])
        group=self.fixture.fixture(actual=True,suffix='-bad',failed=True)
        page=review_page(self.fixture.run_group(group),[group],{'purpose':'renderer','method':'automated_runtime'})
        self.assertEqual(page['items'][0]['status'],'failed')
        self.assertTrue(page['items'][0]['captures'])

    def test_filter_bounds_and_freshness_refusal_precede_response(self):
        for params in ({'path':'private'},{'limit':201},{'offset':-1},{'limit':True},{'method':'hardware'}, {'status':'not_run'}):
            with self.subTest(params=params), self.assertRaises(ContractError):self.provider.read(self.store,params)
        with mock.patch('patchquest.runtime_review.catalog_unchanged',return_value=False),self.assertRaises(ContractError):
            self.page()

    def test_unadmitted_attempts_stay_visible_without_counting_them_as_scope_passes(self):
        result=self.fixture.run_group(self.group,admit=lambda _:None)
        page=review_page(result,[self.group],{'purpose':'renderer','method':'automated_runtime'})
        item=page['items'][0]
        self.assertEqual(item['status'],'untested');self.assertEqual(item['captures'],[])
        self.assertEqual(len(item['unselected_attempts']),1)
        old=item['unselected_attempts'][0]['observation']
        self.assertTrue(old['captures']);self.assertEqual(old['assertion'],'not_assessed')

    def test_large_inventory_paginates_without_repeating_record_arrays(self):
        for index in range(1000):
            case=copy.deepcopy(self.group['cases'][0]);case.update(case_id='invented-unexecuted-'+str(index),page=index+1,record_ids=[])
            self.group['cases'].append(case)
        result=self.fixture.run_group(self.group)
        started=time.monotonic()
        page=review_page(result,[self.group],{'purpose':'renderer','method':'automated_runtime','offset':990,'limit':10})
        self.assertEqual(page['total'],1001);self.assertEqual(len(page['items']),10)
        self.assertTrue(all(i['status']=='untested' for i in page['items']))
        self.assertNotIn('rows',page['groups'][0]['current_catalog'][0])
        self.assertNotIn('case_digests',page['groups'][0]['scope'])
        self.assertLess(len(json.dumps(page).encode()),2*1024*1024)
        self.assertLess(time.monotonic()-started,5)

    def test_pair_explains_configuration_starting_state_and_timing_limits(self):
        item=self.page()['items'][0];other=copy.deepcopy(item)
        result=comparison(item,other)
        self.assertIn('unknown_starting_state',result['differences'])
        self.assertFalse(result['same_recorded_setup'])
        other['comparison_axes']['binding']['configuration_sha256']='0'*64
        self.assertIn('binding',comparison(item,other)['differences'])
        self.assertIn('animation',result['limitation'])

    def test_nullable_message_and_page_metadata_sort_without_inventing_values(self):
        for number,(message,page) in enumerate([(None,None),('greeting-script',None),('greeting-script',1)]):
            case=copy.deepcopy(self.group['cases'][0]);case.update(case_id='invented-nullable-'+str(number),
                record_ids=[],message_id=message,page=page);self.group['cases'].append(case)
        result=self.fixture.run_group(self.group)
        page=review_page(result,[self.group],{'purpose':'renderer','method':'automated_runtime'})
        self.assertEqual(page['total'],4)
        self.assertIsNone(page['items'][0]['message_id']);self.assertIsNone(page['items'][0]['page'])

    def test_contact_sheet_keeps_exact_png_pixels_metadata_and_immutable_outputs(self):
        items=self.page()['items'];original=copy.deepcopy(items)
        artifacts=RuntimeArtifacts(self.root/'derived',budget_bytes=1024*1024,graph_guard=invented_graph)
        output=self.root/'contact-sheet'
        package=write_contact_sheets(items,resolve_evidence=self.resolve,artifacts=artifacts,destination=output,page_size=1)
        self.assertEqual(package['source_count'],1)
        proof=json.loads((output/'provenance.json').read_bytes())
        self.assertEqual(proof['sources'][0]['original'],items[0]['captures'][0]['reference'])
        self.assertTrue(proof['originals_unchanged']);self.assertFalse(proof['verification_awards'])
        document=(output/'contact-sheet-1.html').read_text()
        self.assertIn('width="1" height="1"',document)
        self.assertIn('data:image/png;base64,',document)
        encoded=re.findall(r'src="data:image/png;base64,([^"]+)"',document)
        self.assertEqual(len(encoded),1)
        self.assertEqual(hashlib.sha256(base64.b64decode(encoded[0])).hexdigest(),
                         items[0]['captures'][0]['sha256'])
        for ref in [package['provenance'],package['pages'][0]['reference']]:self.assertTrue(artifacts.resolve(ref)['available'])
        self.assertEqual(items,original)
        before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
        with self.assertRaises(ContractError):write_contact_sheets(items,resolve_evidence=self.resolve,artifacts=artifacts,destination=output)
        self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()})

    def test_missing_contact_sheet_input_refuses_before_creating_destination(self):
        items=self.page()['items'];self.fixture.blobs.clear()
        artifacts=RuntimeArtifacts(self.root/'derived',budget_bytes=1024*1024,graph_guard=invented_graph)
        with self.assertRaises(ContractError):
            write_contact_sheets(items,resolve_evidence=self.resolve,artifacts=artifacts,destination=self.root/'missing')
        self.assertFalse((self.root/'missing').exists())

    def test_contact_sheet_retains_each_admitted_purpose_in_both_selection_orders(self):
        for scenario in ('positive','negative','conflicting'):
            config={'invented_sheet_case':scenario}
            group=self.fixture.fixture(actual=True,suffix='-sheet-'+scenario,
                config=config,failed=scenario=='negative')
            self.fixture.proof(group)['purposes'][contract_digest('CaseSpec',group['cases'][0])]['normal_gameplay']={
                'reason':'Independently invented limited behavior.', 'reference':'Synthetic sheet association fixture.'}
            if scenario=='conflicting':
                # The second renderer-only failure makes that view unknown;
                # gameplay retains its separately admitted passing attempt.
                other=self.fixture.fixture(actual=True,suffix='-renderer-failure',config=config,failed=True)
                group['runs'].extend(other['runs'])
            page=review_page(self.fixture.run_group(group),[group],{'method':'automated_runtime'})
            views=page['items']
            self.assertEqual({v['purpose'] for v in views},{'renderer','normal_gameplay'})
            states={v['purpose']:v['status'] for v in views}
            self.assertEqual(states,{'normal_gameplay':'passed','renderer':'unknown'} if scenario=='conflicting' else
                {'normal_gameplay':'failed' if scenario=='negative' else 'passed',
                 'renderer':'failed' if scenario=='negative' else 'passed'})
            self.assertTrue(set(c['evidence_id'] for c in views[0]['captures']) &
                            set(c['evidence_id'] for c in views[1]['captures']))
            expected={(v['purpose'],v['method'],c['observation_id'],c['frame'],c['evidence_id']):
                (v['status'],c['reference']) for v in views for c in v['captures']}
            for order, items in [('forward',views),('reverse',list(reversed(views)))]:
                with self.subTest(scenario=scenario,order=order):
                    label=scenario+'-'+order;original=copy.deepcopy(items)
                    artifacts=RuntimeArtifacts(self.root/('derived-'+label),budget_bytes=1024*1024,
                        graph_guard=invented_graph)
                    out=self.root/('sheet-'+label)
                    package=write_contact_sheets(items,resolve_evidence=self.resolve,
                        artifacts=artifacts,destination=out)
                    proof=json.loads((out/'provenance.json').read_bytes())
                    self.assertEqual(package['source_count'],len(expected))
                    self.assertEqual(len(proof['sources']),len(expected))
                    actual={(s['purpose'],s['method'],s['observation_id'],s['frame'],s['original']['evidence_id']):
                        (s['status'],s['original']) for s in proof['sources']}
                    self.assertEqual(actual,expected)
                    document=(out/'contact-sheet-1.html').read_text()
                    self.assertIn('renderer · automated runtime',document)
                    self.assertIn('normal gameplay · automated runtime',document)
                    self.assertEqual(items,original)

    def authoritative_artifacts(self):
        connector=ArtifactState(self.store,self.store.directory/'invented-review-artifacts')
        receipt=self.fixture.proof(self.group)
        refs=list(receipt['artifacts'].values())+[receipt['emulator']]
        manifest=json.loads(self.group['runs'][0]['manifest_bytes'])
        refs.extend(c['evidence'] for o in manifest['observations'] for c in o['captures'])
        digests=sorted({r['sha256'] for r in refs})
        connector.set_policy(pins=digests,ownership={sha:'managed' for sha in digests},expected=0)
        artifacts=RuntimeArtifacts(connector.directory,budget_bytes=1024*1024,graph_guard=connector.guard)
        for ref in refs:artifacts.register(ref,self.fixture.blobs[ref['sha256']])
        self.provider.artifacts=artifacts
        capture=self.page()['items'][0]['captures'][0]
        return artifacts,capture

    def overlapping_artifact_calls(self,first_operation,*,fail_first=False):
        artifacts,capture=self.authoritative_artifacts()
        entered=threading.Event();release=threading.Event();second_started=threading.Event();second_done=threading.Event()
        answers={};original=artifacts._read
        def read(ref):
            if threading.current_thread().name=='invented-review-first':
                entered.set()
                if not release.wait(5):raise AssertionError('Invented release not received')
                if fail_first:raise ValueError('Invented immutable-byte read failure')
            return original(ref)
        def call(label):
            if label=='second':second_started.set()
            try:
                answers[label]=self.page() if label=='first' and first_operation=='read' else self.provider.image(
                    self.store,capture['evidence_id'],capture['sha256'])
            except Exception as error:answers[label]=error
            finally:
                if label=='second':second_done.set()
        first=threading.Thread(target=call,args=('first',),name='invented-review-first')
        second=threading.Thread(target=call,args=('second',),name='invented-review-second')
        with mock.patch.object(artifacts,'_read',side_effect=read):
            try:
                first.start();self.assertTrue(entered.wait(3))
                second.start();self.assertTrue(second_started.wait(3))
                self.assertFalse(second_done.wait(.2),'Overlapping image reached the busy artifact guard')
            finally:
                release.set();first.join(5)
                if second.ident is not None:second.join(5)
        self.assertFalse(first.is_alive());self.assertFalse(second.is_alive())
        self.assertEqual(answers['second'],self.fixture.blobs[capture['sha256']])
        if fail_first:self.assertIsInstance(answers['first'],ValueError)
        elif first_operation=='read':self.assertEqual(answers['first']['items'][0]['status'],'passed')
        else:self.assertEqual(answers['first'],self.fixture.blobs[capture['sha256']])
        self.assertEqual(self.page()['items'][0]['status'],'passed')

    def test_overlapping_images_serialize_with_authoritative_store_graph(self):
        self.overlapping_artifact_calls('image')

    def test_overlapping_review_and_image_serialize_with_authoritative_store_graph(self):
        self.overlapping_artifact_calls('read')

    def test_failed_image_releases_operation_lock_for_waiting_image_and_recovery(self):
        self.overlapping_artifact_calls('image',fail_first=True)

    def test_external_artifact_contention_is_still_propagated_without_retry(self):
        artifacts,capture=self.authoritative_artifacts()
        with artifacts._guard(),self.assertRaises(ArtifactBusy):
            self.provider.image(self.store,capture['evidence_id'],capture['sha256'])
        self.assertEqual(self.provider.image(self.store,capture['evidence_id'],capture['sha256']),
                         self.fixture.blobs[capture['sha256']])


if __name__=='__main__':unittest.main()

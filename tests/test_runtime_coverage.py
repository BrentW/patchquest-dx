"""Invented pixels, records and producer receipts; no emulator/game execution."""
import copy
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from _bootstrap import ROOT
from test_state import project, invented
from patchquest.state import Store, canonical
from patchquest.runtime import Frame
from patchquest.runtime_artifacts import reference
from patchquest.runtime_contracts import ContractError, contract_digest, validate
from patchquest.runtime_detectors import detect, expectation_manifest, expectation_digest
from patchquest.runtime_coverage import reconcile, read_catalog, catalog_unchanged, digest


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(project(self.root))
        for key in ('greeting', 'name', 'unseen'):
            self.store.put(invented(key), 0, role='human')
        self.snapshot = self.store.snapshot()['sha256']
        self.store.build(dict(id='invented-build', snapshot=self.snapshot, status='validated'), 0)
        self.base = json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.blobs = {}
        self.proofs = {}

    def evidence(self, data, key, run='invented-run', case='fictional-greeting-page-0', method='synthetic'):
        ref = reference(data, evidence_id=key, media_type='image/png' if data.startswith(b'\x89PNG') else
                        'application/octet-stream', provenance=dict(producer='invented-adapter',
                        method=method, run_id=run, case_id=case))
        ref['integrity'] = 'verified'; self.blobs[ref['sha256']] = data
        return ref

    def resolve(self, ref):
        return dict(available=ref['sha256'] in self.blobs, data=self.blobs.get(ref['sha256']))

    def fixture(self, *, actual=False, suffix='', config=None, failed=False, selected_frames=None):
        """An invented actual-labelled record is a validator fixture, not runtime proof."""
        case = copy.deepcopy(self.base['CaseSpec'])
        case['record_ids'] = ['greeting', 'name']
        caps = copy.deepcopy(self.base['AdapterCapabilities'])
        caps['provenance'] = 'actual_emulator' if actual else 'synthetic'
        method = 'automated_runtime' if actual else 'synthetic'
        binding = copy.deepcopy(self.base['RunBinding'])
        binding.update(snapshot=self.snapshot, records={'greeting':1, 'name':1},
                       configuration_sha256=digest(config or {}),
                       detectors={'image_region':'1' if selected_frames is None else '2'})
        rom = self.evidence(b'Invented build fixture', 'invented-rom')
        emulator = self.evidence(b'Invented emulator identity fixture', 'invented-emulator')
        binding['artifacts'] = {'rom':rom['sha256']}
        binding['emulator']['sha256'] = emulator['sha256']
        checks = [dict(id='pixel', kind='image_region', rect=[0,0,1,1],
                       rgb_sha256=hashlib.sha256(b'\x01\x02\x03').hexdigest(), expected_match=True)]
        if selected_frames is not None:
            checks = [dict(id='pixel-'+str(frame), kind='image_region', capture={'frame':frame},
                rect=[0,0,1,1], expected_match=True,
                rgb_sha256=hashlib.sha256(b'\x04\x05\x06' if frame == 3 else b'\x01\x02\x03').hexdigest())
                for frame in selected_frames]
        plan = expectation_manifest([dict(schema_version=1 if selected_frames is None else 2, expectation_id='invented-region',
            case_sha256=contract_digest('CaseSpec', case),
            basis=dict(method='independent_inspection' if actual else 'synthetic_control',
                reference_sha256=hashlib.sha256(b'authored one pixel expectation').hexdigest(),
                reason='Independently authored pixel; no game-derived fixture.'),
            checks=checks,
            exceptions=[])])
        binding['expectation_sha256'] = expectation_digest(plan)
        binding = validate('RunBinding', binding)
        run = 'invented-run' + suffix
        ref = self.evidence(Frame(1,1,b'\x04\x05\x06' if failed else b'\x01\x02\x03').png(),
                            'capture' + suffix, run, case['case_id'], method)
        observation = copy.deepcopy(self.base['CaseObservation'])
        observation.update(observation_id='observation' + suffix, run_id=run, binding=binding,
            case_id=case['case_id'], case_sha256=contract_digest('CaseSpec',case), frames=1,
            captures=[dict(frame=1,evidence=ref)], assertion='not_assessed', provenance=caps['provenance'],
            method=method, reach_method='cold_boot_navigation', glyphs=None, resources=None, controls={})
        if selected_frames is not None:
            final = self.evidence(Frame(1,1,b'\x04\x05\x06').png(), 'final'+suffix,
                                  run, case['case_id'], method)
            observation.update(frames=3, captures=[dict(frame=1,evidence=ref),dict(frame=3,evidence=final)])
        definition = dict(binding=binding, capabilities=caps, configuration=config or {},
                          requests=[dict(case=case)])
        manifest = dict(schema_version=1, runner_version='3', run_id=run, definition=definition,
                        definition_sha256=digest(definition), observations=[observation],
                        inventories=[], gaps=[], history=[], workers=[])
        finding = detect(case,observation,caps,plan,self.resolve)
        build = read_catalog(self.store,['invented-build'])['builds']['invented-build']
        proof = dict(binding_sha256=contract_digest('RunBinding',binding),
            capabilities_sha256=contract_digest('AdapterCapabilities',caps),
            reviewer='Invented reviewer', reference='Independently authored test receipt',
            reason='Validator fixture only, not execution proof.', artifacts={'rom':rom}, emulator=emulator,
            build_revision=build['revision'], build_payload_sha256=build['payload_sha256'],
            purposes={contract_digest('CaseSpec',case):{
                'renderer':dict(reason='Authored pixel comparison only.',reference='Invented control design')}})
        bundle = dict(manifest_bytes=canonical(manifest).encode(),expectations=plan,findings=finding)
        self.proofs[hashlib.sha256(bundle['manifest_bytes']).hexdigest()] = proof
        cid=case['case_id']
        group=dict(binding=binding,cases=[case],runs=[bundle],
            scope=dict(id='invented-scope',description='Explicit invented context',
                       extraction_completeness='unknown',extraction_basis=''),
            associations={cid:dict(kind='exact',case_sha256=contract_digest('CaseSpec',case),
                                  records=binding['records'].copy(),basis='Authored composed context.')},
            record_requirements={k:dict(case_ids=[cid],complete=True,basis='Only this invented context.')
                                 for k in case['record_ids']})
        return group

    def proof(self, g):
        return self.proofs[hashlib.sha256(g['runs'][0]['manifest_bytes']).hexdigest()]

    def reseal(self, g, mutate):
        """A caller-reviewed alternative invented manifest, never used on real evidence."""
        bundle=g['runs'][0]; proof=self.proof(g)
        m=json.loads(bundle['manifest_bytes']); mutate(m)
        m['definition_sha256']=digest(m['definition'])
        bundle['manifest_bytes']=canonical(m).encode()
        self.proofs[hashlib.sha256(bundle['manifest_bytes']).hexdigest()]=proof

    def run_group(self, g, **kw):
        return reconcile(self.store,[g],admit_run=kw.get('admit',self.proofs.get),
                         resolve_evidence=kw.get('resolve',self.resolve))

    def section(self, result, scope='renderer', method='synthetic'):
        return next(s for s in result['groups'][0]['report']['sections']
                    if (s['scope_kind'],s['method'])==(scope,method))

    def test_composed_context_and_uninventoried_record_remain_distinct(self):
        r=self.run_group(self.fixture())
        self.assertEqual(self.section(r)['rows'][0]['status'],'passed')
        self.assertIsNone(r['global_verified_percent']);self.assertFalse(r['verification_awards'])
        rows=r['groups'][0]['historical_catalog'][0]['rows']
        self.assertEqual({x['record_id']:x['status'] for x in rows},
                         {'greeting':'passed','name':'passed','unseen':'unknown'})

    def test_selected_pages_reconcile_without_rewriting_original_run(self):
        g = self.fixture(selected_frames=(1,3)); before = copy.deepcopy(g)
        before_catalog = read_catalog(self.store, ['invented-build'])
        result = self.run_group(g)
        self.assertEqual(self.section(result)['counts']['passed'], 1)
        self.assertEqual(g, before)
        self.assertEqual(read_catalog(self.store, ['invented-build']), before_catalog)
        self.assertFalse(result['verification_awards'])

    def test_passing_final_diagnostic_cannot_hide_failed_required_page(self):
        g = self.fixture(selected_frames=(1,3), failed=True)
        self.assertEqual([f['status'] for f in g['runs'][0]['findings']], ['failed','passed'])
        self.assertEqual(self.section(self.run_group(g))['counts']['failed'], 1)
        g['runs'][0]['findings'] = g['runs'][0]['findings'][1:]
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'], 1)

    def test_missing_page_and_missing_page_bytes_do_not_pass(self):
        g = self.fixture(selected_frames=(2,3))
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'], 1)
        g = self.fixture(selected_frames=(1,3), suffix='-missing')
        manifest = json.loads(g['runs'][0]['manifest_bytes'])
        del self.blobs[manifest['observations'][0]['captures'][0]['evidence']['sha256']]
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'], 1)

    def test_forged_page_pass_cannot_use_a_different_selected_capture(self):
        g = self.fixture(selected_frames=(1,3))
        findings = g['runs'][0]['findings']
        findings[0]['evidence_ids'] = findings[1]['evidence_ids'][:]
        with self.assertRaises(ContractError): self.run_group(g)

    def test_edited_selector_cannot_reinterpret_original_run_binding(self):
        g = self.fixture(selected_frames=(1,3))
        plan = next(iter(g['runs'][0]['expectations']['cases'].values()))
        plan['checks'][0]['capture']['frame'] = 3
        with self.assertRaisesRegex(ContractError, 'expectation plan differs'): self.run_group(g)

    def test_cold_route_does_not_admit_gameplay(self):
        g=self.fixture(actual=True);r=self.run_group(g)
        self.assertEqual(self.section(r,method='automated_runtime')['counts']['passed'],1)
        self.assertEqual(self.section(r,'normal_gameplay','automated_runtime')['counts']['untested'],1)

    def test_explicit_purpose_cannot_override_state_route(self):
        g=self.fixture(actual=True)
        self.proof(g)['purposes'][contract_digest('CaseSpec',g['cases'][0])]['normal_gameplay']={
            'reason':'Limited invented behavior', 'reference':'Invented independent review'}
        self.assertEqual(self.section(self.run_group(g),'normal_gameplay','automated_runtime')['counts']['passed'],1)
        self.reseal(g,lambda m:m['observations'][0].update(reach_method='emulator_state'))
        with self.assertRaises(ValueError):self.run_group(g)

    def test_missing_composed_revision_is_rejected_before_assessment(self):
        g=self.fixture();g['binding']['records'].pop('name')
        with self.assertRaisesRegex(ContractError,'composed'):self.run_group(g)

    def test_observation_capability_mismatch_is_rejected(self):
        g=self.fixture()
        self.reseal(g,lambda m:m['observations'][0].update(provenance='actual_emulator',method='automated_runtime'))
        with self.assertRaises(ValueError):self.run_group(g)

    def test_naked_pass_labels_and_missing_admission_never_pass(self):
        g=self.fixture();r=self.run_group(g,admit=lambda _:None)
        self.assertEqual(self.section(r)['counts']['untested'],1)
        g['runs'][0].update(expectations=None,findings=[])
        self.reseal(g,lambda m:m['observations'][0].update(assertion='passed'))
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)

    def test_missing_plan_findings_and_changed_capture_do_not_pass(self):
        g=self.fixture();g['runs'][0]['findings']=[]
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)
        g=self.fixture();capture=json.loads(g['runs'][0]['manifest_bytes'])['observations'][0]['captures'][0]['evidence']
        self.blobs[capture['sha256']]=b'changed'
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)

    def test_changed_immutable_build_input_does_not_pass(self):
        g=self.fixture();self.blobs[self.proof(g)['artifacts']['rom']['sha256']]=b'changed'
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)

    def test_imported_finding_disagreement_is_unknown(self):
        g=self.fixture(failed=True);g['runs'][0]['findings'][0]['status']='passed'
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)

    def test_captured_failure_is_exercised_not_passed(self):
        r=self.run_group(self.fixture(failed=True));row=self.section(r)['rows'][0]
        self.assertEqual(row['status'],'failed')
        record=r['groups'][0]['historical_catalog'][0]['rows'][0]
        self.assertEqual(record['status'],'failed');self.assertTrue(record['exercised_case_ids'])

    def test_partial_composed_mapping_credits_neither_fragment(self):
        g=self.fixture();g['associations'][g['cases'][0]['case_id']]['records'].pop('name')
        r=self.run_group(g)
        self.assertTrue(all(x['status']=='unknown' for x in r['groups'][0]['historical_catalog'][0]['rows']))
        self.assertEqual(sum(x['kind']=='unexercised' for x in r['groups'][0]['report']['gap_candidates']),3)

    def test_missing_capture_preserves_noncompleted_execution_and_validity(self):
        expected = dict(unsupported='unsupported', excluded='excluded', not_run='untested',
                        interrupted='interrupted', failed='failed', running='in_progress')
        for execution, status in expected.items():
            with self.subTest(execution=execution):
                g=self.fixture();g['runs'][0]['findings']=[]
                self.reseal(g,lambda m:m['observations'][0].update(
                    execution=execution, assertion='not_assessed', frames=0, captures=[],
                    reason='Invented execution stopped before its first capture.'))
                r=self.run_group(g)
                self.assertEqual(self.section(r)['rows'][0]['status'],status)
                self.assertFalse(next(iter(r['groups'][0]['attempts'].values()))['captured'])
        for validity, status in [('stale','stale'),('unknown','unknown')]:
            with self.subTest(validity=validity):
                g=self.fixture();g['runs'][0]['findings']=[]
                self.reseal(g,lambda m:m['observations'][0].update(
                    validity=validity, assertion='not_assessed', frames=0, captures=[],
                    reason='Invented capture validity cannot be established.'))
                self.assertEqual(self.section(self.run_group(g))['rows'][0]['status'],status)

    def test_invalid_mapping_basis_never_hides_gaps_or_credits_records(self):
        for basis in ('', '   ', 1, ['reason'], 'x'*4001):
            with self.subTest(basis_type=type(basis).__name__):
                g=self.fixture();g['associations'][g['cases'][0]['case_id']]['basis']=basis
                r=self.run_group(g);group=r['groups'][0]
                rows=group['historical_catalog'][0]['rows']
                self.assertTrue(all(x['status']=='unknown' and not x['exercised_case_ids'] for x in rows))
                self.assertEqual(sum(x['kind']=='unexercised' for x in group['report']['gap_candidates']),3)
                self.assertEqual(sum(x['kind']=='unmapped' for x in group['report']['gap_candidates']),1)

    def test_unknown_context_completeness_prevents_record_pass(self):
        g=self.fixture();g['record_requirements']['greeting']['complete']=False
        self.assertEqual(self.run_group(g)['groups'][0]['historical_catalog'][0]['rows'][0]['status'],'unknown')

    def test_unexecuted_context_keeps_denominator_and_record_unknown(self):
        g=self.fixture();c=copy.deepcopy(g['cases'][0]);c['case_id']='invented-other-window'
        g['cases'].append(c)
        for req in g['record_requirements'].values():req['case_ids']=sorted([x['case_id'] for x in g['cases']])
        r=self.run_group(g);s=self.section(r)
        self.assertEqual((s['denominator'],s['passed_percent']),(2,50.0))
        self.assertEqual(r['groups'][0]['historical_catalog'][0]['rows'][0]['status'],'unknown')

    def test_human_correction_is_preserved_and_historical_result_not_rewritten(self):
        g=self.fixture();old=json.loads(g['runs'][0]['manifest_bytes'])
        self.store.put(invented('name',target='The saved human name'),1,role='human')
        before=self.store.get('name');r=self.run_group(g)
        self.assertEqual(self.section(r)['counts']['passed'],1)
        current={x['record_id']:x for x in r['groups'][0]['current_catalog'][0]['rows']}
        self.assertEqual(current['name']['status'],'stale')
        self.assertEqual(current['greeting']['status'],'stale') # Composed name also changed.
        self.assertEqual(self.store.get('name'),before)
        self.assertEqual(json.loads(g['runs'][0]['manifest_bytes']),old)

    def test_new_catalog_record_is_not_omitted_from_current_lens(self):
        g=self.fixture();self.store.put(invented('new'),0,role='human')
        r=self.run_group(g)
        self.assertEqual(r['groups'][0]['current_catalog'][0]['denominator'],4)
        self.assertEqual(r['groups'][0]['historical_catalog'][0]['denominator'],3)

    def test_groups_with_different_configuration_remain_separate(self):
        a=self.fixture();b=self.fixture(suffix='b',config={'invented_mode':2})
        r=reconcile(self.store,[a,b],admit_run=self.proofs.get,resolve_evidence=self.resolve)
        self.assertEqual(len(r['groups']),2)
        self.assertNotEqual(r['groups'][0]['report']['binding'],r['groups'][1]['report']['binding'])

    def test_conflicting_reruns_need_reasoned_same_purpose_supersession(self):
        g=self.fixture();bad=self.fixture(suffix='bad',failed=True);g['runs']+=bad['runs']
        self.assertEqual(self.section(self.run_group(g))['counts']['unknown'],1)
        g['supersessions']=[dict(old='observationbad',new='observation',reason='Reviewed invented rerun')]
        r=self.run_group(g)
        self.assertEqual(self.section(r)['counts']['passed'],1)
        self.assertEqual(len(r['groups'][0]['attempts']),2)
        g['supersessions'].append(dict(old='observation',new='observationbad',reason='Invented cycle'))
        with self.assertRaisesRegex(ValueError,'cycle'):self.run_group(g)

    def test_build_revision_and_project_identity_are_checked(self):
        g=self.fixture();self.store.build(dict(id='invented-build',snapshot=self.snapshot,status='validated'),1)
        with self.assertRaisesRegex(ValueError,'build changed'):self.run_group(g)
        other=replace(self.store.context,manifest=copy.deepcopy(self.store.context.manifest))
        other.manifest['project_id']='another-invented-project'
        with self.assertRaisesRegex(ValueError,'project/source'):read_catalog(other,['invented-build'])

    def test_snapshot_digest_is_checked_not_only_label(self):
        g=self.fixture()
        with closing(sqlite3.connect(self.store.path)) as db, db:
            db.execute("UPDATE snapshots SET payload='{}' WHERE digest=?",(self.snapshot,))
        with self.assertRaisesRegex(ValueError,'snapshot digest'):self.run_group(g)

    def test_catalog_drift_during_reconciliation_is_rejected(self):
        g=self.fixture();old=read_catalog(self.store,['invented-build'])
        def admit(key):
            self.store.put(invented('unseen',target='Changed synthetic record'),1,role='human')
            return self.proofs[key]
        with self.assertRaisesRegex(ValueError,'Catalog changed'):self.run_group(g,admit=admit)
        self.assertFalse(catalog_unchanged(self.store,old))

    def test_read_only_receiver_does_not_create_snapshot_events_or_exports(self):
        g=self.fixture()
        def state():
            with closing(sqlite3.connect(self.store.path)) as db:
                return {table:db.execute('SELECT * FROM '+table).fetchall()
                        for table in ('snapshots','events','revisions','builds','evidence')}
        before=state();self.run_group(g);self.assertEqual(state(),before)
        self.assertFalse((self.store.directory/'snapshots').exists())

    def test_missing_database_is_not_created(self):
        folder=self.root/'empty';folder.mkdir()
        context=type(self.store.context).load(project(folder))
        with self.assertRaisesRegex(ValueError,'does not exist'):read_catalog(context,[])
        self.assertFalse((folder/'.patchquest').exists())

    def test_declarations_remain_gaps_and_stale_revision_is_visible(self):
        g=self.fixture();g['declarations']=[dict(kind='graphics_text',revisions={'unseen':1},
            reason='Invented bitmap label uses another renderer.',reference='Invented reviewed mapping')]
        self.store.put(invented('unseen',target='Changed bitmap label'),1,role='human')
        r=self.run_group(g)
        d=next(x for x in r['groups'][0]['report']['gap_candidates'] if x['kind']=='graphics_text')
        self.assertIn('Historical',d['reason']);self.assertEqual(self.section(r)['denominator'],1)
        g['declarations'][0]['revisions']['unseen']=2
        with self.assertRaisesRegex(ValueError,'Declaration revisions'):self.run_group(g)

    def test_discovery_and_empty_scope_cannot_create_coverage(self):
        g=self.fixture()
        self.reseal(g,lambda m:m.update(gaps=[dict(kind='unplanned',case_id='invented-outside')]))
        r=self.run_group(g)
        self.assertTrue(any(x['kind']=='unmapped' for x in r['groups'][0]['report']['gap_candidates']))
        g['cases']=[];g['record_requirements']={};g['associations']={}
        with self.assertRaisesRegex(ValueError,'denominator'):self.run_group(g)
        g['runs']=[]
        r=self.run_group(g)
        self.assertIsNone(self.section(r)['passed_percent'])


if __name__ == '__main__':
    unittest.main()

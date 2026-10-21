"""Independent synthetic contract conformance; never emulator evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.runtime_contracts import (
    ContractError, UnsupportedCapability, CAPABILITIES, COVERAGE_STATUSES,
    validate, contract_digest, binding_changes, require_capabilities,
    check_observation, check_finding, observation_status, verify_evidence_bytes,
    check_coverage_runtime_links, binding_from_runtime_report,
    expectation_manifest_data, required_finding_plan, assess_observation_findings,
    expectation_capture_frame,
)

FIXTURE = Path(__file__).parent / 'fixtures/runtime_coverage/conformance.json'


class RuntimeContractsTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.records = self.data['connectors']

    def get(self, kind):
        return copy.deepcopy(self.records[kind])

    def test_every_connector_roundtrips_without_mutating_input(self):
        before = copy.deepcopy(self.records)
        for kind, data in self.records.items():
            with self.subTest(kind=kind):
                result = validate(kind, data)
                self.assertEqual(result, validate(kind, json.loads(json.dumps(result))))
                result['extensions']['test:annotation'] = 'detached'
                self.assertNotEqual(result, data)
        self.assertEqual(before, self.records)

    def test_all_conformance_outcomes_remain_distinct(self):
        expected = {'success':'passed', 'failure':'failed', 'partial':'interrupted',
                    'unsupported':'unsupported', 'stale':'stale'}
        for example in self.data['observations']:
            self.assertEqual(observation_status(example['value'], self.get('RunBinding')), expected[example['name']])

    def test_unknown_required_versions_and_fields_fail_closed(self):
        for kind in self.records:
            for field, value in [('schema_version', 2), ('schema_version', True), ('kind', 'unknown'),
                                 ('required_feature', 'not-understood')]:
                with self.subTest(kind=kind,field=field):
                    data=self.get(kind);data[field]=value
                    with self.assertRaises(ContractError):validate(kind,data)

    def test_optional_defaults_and_namespaced_annotations(self):
        case={'schema_version':1,'kind':'CaseSpec','case_id':'invented-unknown',
              'coverage_scope':'invented-scope','required_capabilities':[]}
        result=validate('CaseSpec',case)
        self.assertIsNone(result['message_id']);self.assertEqual(result['record_ids'],[])
        result['extensions']={'example:note':'No semantic override'}
        self.assertEqual(validate('CaseSpec',result),result)
        result['extensions']={'required_capability':'scroll'}
        with self.assertRaises(ContractError):validate('CaseSpec',result)

    def test_non_json_and_nonfinite_values_rejected(self):
        for value in [float('nan'),float('inf'),b'bytes',{1:'non-string-key'},{'nested':set()}]:
            case=self.get('CaseSpec');case['extensions']['test:value']=value
            with self.assertRaises(ContractError):validate('CaseSpec',case)

    def test_depth_limit_and_bad_container_shapes(self):
        deep={};cursor=deep
        for _ in range(45):cursor['test:next']={};cursor=cursor['test:next']
        case=self.get('CaseSpec');case['extensions']=deep
        with self.assertRaises(ContractError):validate('CaseSpec',case)
        for value in [None,[],42,'text']:
            with self.assertRaises(ContractError):validate('CaseSpec',value)

    def test_no_implicit_scrolling_or_glyph_capabilities(self):
        caps=self.get('AdapterCapabilities');caps['capabilities']={'capture_frames':True,'input':True}
        normalized=validate('AdapterCapabilities',caps)
        self.assertEqual(set(normalized['capabilities']),set(CAPABILITIES))
        self.assertFalse(normalized['capabilities']['native_scroll'])
        case=self.get('CaseSpec');case['required_capabilities']=['native_scroll']
        with self.assertRaises(UnsupportedCapability):require_capabilities(case,caps)
        case['required_capabilities']=['future_feature']
        with self.assertRaises(UnsupportedCapability):validate('CaseSpec',case)
        caps['capabilities']['capture_frames']=1
        with self.assertRaises(ContractError):validate('AdapterCapabilities',caps)

    def test_case_identity_is_build_independent_but_definition_is_pinned(self):
        case=self.get('CaseSpec');original=contract_digest('CaseSpec',case)
        obs=self.get('CaseObservation');caps=self.get('AdapterCapabilities')
        self.assertEqual(check_observation(case,obs,caps),obs)
        case['variant_id']='different-name-width'
        self.assertEqual(case['case_id'],obs['case_id'])
        self.assertNotEqual(original,contract_digest('CaseSpec',case))
        with self.assertRaises(ContractError):check_observation(case,obs,caps)
        with self.assertRaises(ContractError):validate('CaseSpec',dict(case,build_id='forbidden'))

    def test_context_page_window_and_unknown_associations(self):
        case=self.get('CaseSpec')
        for field,value in [('page',1),('window_id','menu'),('context_id','second-visit'),('message_id',None)]:
            other=dict(case);other[field]=value
            self.assertNotEqual(contract_digest('CaseSpec',case),contract_digest('CaseSpec',other))
        case['page']=True
        with self.assertRaises(ContractError):validate('CaseSpec',case)

    def test_every_binding_component_invalidates_old_evidence(self):
        b=self.get('RunBinding');obs=self.get('CaseObservation')
        changes={'build_id':'new-build','artifacts':{'rom':'0'*64},'snapshot':'0'*64,
                 'records':{'greeting':2},'scenario_sha256':'0'*64,'configuration_sha256':'0'*64,
                 'adapter':{'id':'invented-adapter','version':'2'},
                 'emulator':{'id':'invented-emulator','version':'2','sha256':'0'*64},
                 'expectation_sha256':'0'*64,'detectors':{'bounds':'2'}}
        for field,value in changes.items():
            with self.subTest(field=field):
                new=copy.deepcopy(b);new[field]=value
                self.assertEqual(binding_changes(b,new),[field])
                self.assertEqual(observation_status(obs,new),'stale')

    def test_binding_requires_actual_revision_numbers(self):
        for value in [0,-1,True,'1',None]:
            b=self.get('RunBinding');b['records']['greeting']=value
            with self.assertRaises(ContractError):validate('RunBinding',b)

    def test_partial_run_cannot_pass(self):
        for execution in ['not_run','running','interrupted','failed','unsupported','excluded']:
            obs=self.get('CaseObservation');obs.update(execution=execution,reason='Invented fault')
            with self.assertRaises(ContractError):validate('CaseObservation',obs)

    def test_completed_execution_can_fail_or_remain_unassessed(self):
        obs=self.get('CaseObservation');obs.update(assertion='failed',reason='Invented faulty bounds')
        self.assertEqual(observation_status(obs,obs['binding']),'failed')
        obs['assertion']='not_assessed'
        self.assertEqual(observation_status(obs,obs['binding']),'unknown')

    def test_changed_binding_requires_explicit_staleness_when_checked(self):
        obs=self.get('CaseObservation');b=self.get('RunBinding');b['records']['greeting']=2
        with self.assertRaises(ContractError):
            check_observation(self.get('CaseSpec'),obs,self.get('AdapterCapabilities'),expected_binding=b)
        obs.update(validity='stale',reason='Translation revision changed')
        self.assertEqual(check_observation(self.get('CaseSpec'),obs,self.get('AdapterCapabilities'),expected_binding=b),obs)

    def test_missing_case_records_and_invented_instrumentation_rejected(self):
        for changes in [{'glyphs':[]},{'resources':{}},{'controls':{'scrolled':True}},
                        {'reach_method':'debug_injection'}]:
            obs=self.get('CaseObservation');obs.update(changes)
            with self.assertRaises(ContractError):check_observation(self.get('CaseSpec'),obs,self.get('AdapterCapabilities'))
        obs=self.get('CaseObservation');obs['binding']['records']={}
        with self.assertRaises(ContractError):check_observation(self.get('CaseSpec'),obs,self.get('AdapterCapabilities'))

    def test_missing_capability_can_be_reported_as_unsupported(self):
        case=self.get('CaseSpec');case['required_capabilities'].append('native_scroll')
        obs=copy.deepcopy(next(x['value'] for x in self.data['observations'] if x['name']=='unsupported'))
        obs['case_sha256']=contract_digest('CaseSpec',case)
        self.assertEqual(check_observation(case,obs,self.get('AdapterCapabilities')),obs)

    def test_capture_integrity_provenance_and_frame_bounds(self):
        for mutation in ['run','method','frame','integrity','duplicate']:
            obs=self.get('CaseObservation');capture=obs['captures'][0]
            if mutation=='run':capture['evidence']['provenance']['run_id']='other-run'
            if mutation=='method':capture['evidence']['provenance']['method']='automated_runtime'
            if mutation=='frame':capture['frame']=obs['frames']+1
            if mutation=='integrity':capture['evidence']['integrity']='missing'
            if mutation=='duplicate':obs['captures'].append(copy.deepcopy(capture))
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):validate('CaseObservation',obs)

    def test_evidence_bytes_are_checked_without_resolving_paths(self):
        evidence=self.get('EvidenceRef');raw=b'Invented capture bytes. Not an emulator frame.'
        self.assertTrue(verify_evidence_bytes(evidence,raw))
        self.assertFalse(verify_evidence_bytes(evidence,raw+b'x'))
        evidence['path']='../../not-allowed'
        with self.assertRaises(ContractError):validate('EvidenceRef',evidence)

    def test_save_state_reference_and_cold_boot_are_distinct(self):
        scene=self.get('SceneHandle');scene['reach_method']='emulator_state'
        with self.assertRaises(ContractError):validate('SceneHandle',scene)
        scene['checkpoint']=self.get('EvidenceRef')
        self.assertEqual(validate('SceneHandle',scene),scene)
        scene['reach_method']='cold_boot_navigation'
        with self.assertRaises(ContractError):validate('SceneHandle',scene)

    def test_finding_versions_and_foreign_capture_links_rejected(self):
        f=self.get('DetectorFinding');obs=self.get('CaseObservation')
        self.assertEqual(check_finding(f,obs),f)
        for field,value in [('detector_version','2'),('evidence_ids',['foreign']),('observation_id','foreign')]:
            changed=copy.deepcopy(f);changed[field]=value
            with self.assertRaises(ContractError):check_finding(changed,obs)

    def test_no_plan_is_unknown_not_one_hundred_percent(self):
        report=self.get('CoverageReport');report['scope']['case_ids']=[];report['scope']['case_digests']={}
        section=report['sections'][0];section.update(rows=[],denominator=0,counts=dict.fromkeys(COVERAGE_STATUSES,0),passed_percent=None)
        validate('CoverageReport',report)
        section['passed_percent']=100
        with self.assertRaises(ContractError):validate('CoverageReport',report)

    def test_unexercised_context_stays_in_denominator(self):
        report=self.get('CoverageReport');report['scope']['case_ids'].append('second-context')
        report['scope']['case_digests']['second-context']='0'*64
        with self.assertRaises(ContractError):validate('CoverageReport',report)
        section=report['sections'][0]
        section['rows'].append(dict(case_id='second-context',status='untested',reason='',observation_ids=[],finding_ids=[]))
        section.update(denominator=2,passed_percent=50);section['counts']['untested']=1
        validate('CoverageReport',report)
        section['rows'][1].update(status='excluded',reason='')
        with self.assertRaises(ContractError):validate('CoverageReport',report)

    def test_no_overall_coverage_percentage_or_method_promotion(self):
        report=self.get('CoverageReport');report['verified_percent']=100
        with self.assertRaises(ContractError):validate('CoverageReport',report)
        for scope,method in [('normal_gameplay','synthetic'),('editorial','automated_runtime'),('hardware','automated_runtime')]:
            report=self.get('CoverageReport');report['sections'][0].update(scope_kind=scope,method=method)
            with self.assertRaises(ContractError):validate('CoverageReport',report)

    def test_cross_record_coverage_rejects_stale_synthetic_and_wrong_context_passes(self):
        report=self.get('CoverageReport');obs=self.get('CaseObservation');f=self.get('DetectorFinding')
        self.assertEqual(check_coverage_runtime_links(report,[obs],[f]),report)
        for mutation in ['synthetic','revision','context','missing','detector']:
            r=copy.deepcopy(report);o=copy.deepcopy(obs);finding=copy.deepcopy(f)
            if mutation=='synthetic':r['sections'][0]['method']='automated_runtime'
            if mutation=='revision':r['binding']['records']['greeting']=2
            if mutation=='context':r['scope']['case_digests'][o['case_id']]='0'*64
            if mutation=='missing':r['sections'][0]['rows'][0]['observation_ids']=['missing']
            if mutation=='detector':finding.update(status='unknown',reason='Detector uncertain')
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):check_coverage_runtime_links(r,[o],[finding])

    def test_debug_and_state_replay_cannot_claim_normal_route_coverage(self):
        # Invented declarations only; this test does not run any emulator.
        obs=self.get('CaseObservation');obs.update(provenance='actual_emulator',method='automated_runtime')
        obs['captures'][0]['evidence']['provenance']['method']='automated_runtime'
        report=self.get('CoverageReport');report['sections'][0].update(scope_kind='normal_gameplay',method='automated_runtime')
        for method in ['debug_injection','emulator_state']:
            obs['reach_method']=method
            with self.assertRaises(ContractError):check_coverage_runtime_links(report,[obs],[self.get('DetectorFinding')])

    def test_selection_is_partitioned_and_unknown_changes_force_full_scope(self):
        plan=self.get('ChangeImpactPlan')
        for mutation in ['deferred','missing','flag']:
            p=copy.deepcopy(plan)
            if mutation=='deferred':p['deferred']=copy.deepcopy(p['selected'])
            if mutation=='missing':p['selected']=[]
            if mutation=='flag':p['full_sweep_required']=False
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):validate('ChangeImpactPlan',p)

    def test_legacy_report_bridge_reuses_identities_without_creating_observations(self):
        b=self.get('RunBinding')
        report=dict(schema=1,build_id=b['build_id'],rom_sha256=b['artifacts']['rom'],snapshot=b['snapshot'],records=b['records'],
                    scenario_sha256=b['scenario_sha256'],configuration_sha256=b['configuration_sha256'],emulator={'sha256':b['emulator']['sha256']})
        options=dict(adapter=b['adapter'],emulator_id=b['emulator']['id'],emulator_version=b['emulator']['version'],
                     expectation_sha256=b['expectation_sha256'],detectors=b['detectors'])
        self.assertEqual(binding_from_runtime_report(report,**options),b)
        del report['emulator']['sha256']
        with self.assertRaises(ContractError):binding_from_runtime_report(report,**options)


class RequiredFindingTests(unittest.TestCase):
    """Invented declarations test linkage; these are not detector executions."""
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text())['connectors']
        self.obs = copy.deepcopy(self.fixture['CaseObservation'])
        self.obs['assertion'] = 'not_assessed'
        self.obs['binding']['detectors'] = {'bounds': '1', 'completion': '1'}
        self.plan = dict(schema_version=1, expectation_id='invented-complete-plan',
            case_sha256=self.obs['case_sha256'],
            basis=dict(method='synthetic_control', reference_sha256='1'*64,
                       reason='Independently invented check plan'),
            checks=[dict(id='interior', kind='bounds', rect=[0, 0, 16, 16], padding=1, tolerance=0),
                    dict(id='last-page', kind='completion')], exceptions=[])
        self.manifest = dict(schema_version=1, kind='RuntimeExpectationManifest',
            finding_id_algorithm='patchquest-detector-v1', cases={self.obs['case_sha256']: self.plan})
        self.pin(self.manifest)

    @staticmethod
    def digest(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
            separators=(',', ':')).encode('utf8')).hexdigest()

    def pin(self, doc):
        self.obs['binding']['expectation_sha256'] = self.digest(doc)
        self.findings = []
        for check in self.plan['checks']:
            f = copy.deepcopy(self.fixture['DetectorFinding'])
            f.update(binding=copy.deepcopy(self.obs['binding']), expectation_id=self.plan['expectation_id'],
                detector_id=check['kind'], detector_version='1', finding_id='detector-' + self.digest(
                    [self.obs['observation_id'], check['id'], self.digest(doc)]))
            self.findings.append(f)

    def assess(self, findings=None, doc=None, binding=None):
        return assess_observation_findings(self.obs, binding or self.obs['binding'],
            self.findings if findings is None else findings,
            expectations=self.manifest if doc is None else doc)

    def report(self, status='passed', findings=None):
        r = copy.deepcopy(self.fixture['CoverageReport'])
        r['binding'] = copy.deepcopy(self.obs['binding'])
        section = r['sections'][0]
        row = section['rows'][0]
        row.update(status=status, reason='' if status == 'passed' else 'Invented check outcome',
                   finding_ids=[f['finding_id'] for f in (self.findings if findings is None else findings)])
        section['counts'] = dict.fromkeys(COVERAGE_STATUSES, 0)
        section['counts'][status] = 1
        section['passed_percent'] = 100 if status == 'passed' else 0
        return r

    def test_opt_in_complete_findings_pass_without_rewriting_capture(self):
        before = copy.deepcopy((self.obs, self.findings, self.manifest))
        r = self.report()
        self.assertEqual(check_coverage_runtime_links(r, [self.obs], self.findings,
                         expectations=self.manifest), r)
        self.assertEqual(self.assess()['status'], 'passed')
        self.assertEqual(before, (self.obs, self.findings, self.manifest))
        with self.assertRaises(ContractError):
            check_coverage_runtime_links(r, [self.obs], self.findings)

    def test_legacy_single_case_plan_and_exact_finding_id_algorithm(self):
        self.pin(self.plan)
        expected = {f['finding_id'] for f in self.findings}
        self.assertEqual(set(required_finding_plan(self.obs, self.plan)), expected)
        self.assertEqual(self.assess(doc=self.plan)['status'], 'passed')

    def test_missing_checks_cannot_pass_even_with_a_passed_capture(self):
        for assertion in ('passed', 'not_assessed'):
            self.obs['assertion'] = assertion
            for subset in ([], self.findings[:1]):
                result = self.assess(subset)
                self.assertEqual(result['status'], 'unknown')
                self.assertTrue(result['missing_finding_ids'])
                with self.assertRaises(ContractError):
                    check_coverage_runtime_links(self.report(findings=subset), [self.obs], subset,
                                                 expectations=self.manifest)

    def test_confirmed_failure_retains_missing_unknown_and_unsupported_checks(self):
        self.findings[0].update(status='failed', reason='Invented overflow')
        for other in ('unknown', 'unsupported'):
            self.findings[1].update(status=other, reason='Invented unavailable observation')
            result = self.assess()
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(len(result[other+'_finding_ids']), 1)
            r = self.report('failed')
            self.assertEqual(check_coverage_runtime_links(r, [self.obs], self.findings,
                             expectations=self.manifest), r)
        result = self.assess(self.findings[:1])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(len(result['missing_finding_ids']), 1)

    def test_unknown_unsupported_invalid_and_stale_cannot_become_passed(self):
        for outcome in ('unknown', 'unsupported'):
            self.findings[0].update(status=outcome, reason='Invented unavailable check')
            self.assertEqual(self.assess()['status'], outcome)
        self.findings[0].update(status='passed', reason='')
        current = copy.deepcopy(self.obs['binding']);current['records']['greeting'] += 1
        self.assertEqual(self.assess(binding=current)['status'], 'stale')
        for validity in ('missing', 'invalid', 'unknown', 'stale'):
            self.obs.update(validity=validity, reason='Invented evidence status')
            self.assertEqual(self.assess()['status'], 'stale' if validity == 'stale' else 'unknown')

    def test_native_execution_failure_and_explicit_uncertainty_remain_authoritative(self):
        self.obs.update(execution='failed', reason='Invented native exit')
        self.assertEqual(self.assess([])['status'], 'failed')
        self.obs['execution'] = 'interrupted'
        self.assertEqual(self.assess([])['status'], 'interrupted')
        self.obs['execution'] = 'completed'
        for assertion in ('failed', 'unknown', 'unsupported'):
            self.obs['assertion'] = assertion
            self.assertEqual(self.assess()['status'], assertion)

    def test_required_id_and_semantic_identity_cannot_be_replaced_by_annotations(self):
        for mutation in ('id', 'expectation', 'kind', 'duplicate', 'annotation'):
            fs = copy.deepcopy(self.findings)
            if mutation == 'id': fs[0]['finding_id'] = 'unplanned'
            if mutation == 'expectation': fs[0]['expectation_id'] = 'other-plan'
            if mutation == 'kind': fs[0]['detector_id'] = 'completion'
            if mutation == 'duplicate': fs.append(copy.deepcopy(fs[0]))
            if mutation == 'annotation':
                fs[0]['finding_id'] = 'unplanned'
                fs[0]['extensions'] = {'patchquest:detector': {'check_id': 'interior'}}
            with self.subTest(mutation=mutation), self.assertRaises(ContractError): self.assess(fs)

    def test_complete_pin_rejects_subset_and_changed_unselected_case(self):
        other = copy.deepcopy(self.plan);other['case_sha256'] = '2'*64
        self.manifest['cases'][other['case_sha256']] = other
        self.pin(self.manifest)
        self.assertEqual(self.assess()['status'], 'passed')
        for change in ('subset', 'other-case', 'selected-case'):
            doc = copy.deepcopy(self.manifest)
            if change == 'subset': del doc['cases']['2'*64]
            if change == 'other-case': doc['cases']['2'*64]['checks'][0]['padding'] = 2
            if change == 'selected-case': doc['cases'][self.obs['case_sha256']]['checks'].pop()
            with self.subTest(change=change), self.assertRaises(ContractError): self.assess(doc=doc)

    def test_manifest_unknown_schema_algorithm_or_mismatched_case_fails_closed(self):
        for key, value in (('schema_version', True), ('schema_version', 2),
                           ('finding_id_algorithm', 'unknown'), ('kind', 'future'), ('cases', {})):
            doc = copy.deepcopy(self.manifest);doc[key] = value
            with self.assertRaises(ContractError): expectation_manifest_data(doc)
        doc = copy.deepcopy(self.manifest)
        doc['cases']['2'*64] = doc['cases'].pop(self.obs['case_sha256'])
        with self.assertRaises(ContractError): expectation_manifest_data(doc)
        doc = copy.deepcopy(self.manifest)
        doc['cases'][self.obs['case_sha256']]['checks'].append(copy.deepcopy(self.plan['checks'][0]))
        with self.assertRaises(ContractError): expectation_manifest_data(doc)

    def test_definite_results_require_final_verified_capture_references(self):
        for mutation in ('integrity', 'final'):
            o = copy.deepcopy(self.obs)
            if mutation == 'integrity': o['captures'][0]['evidence']['integrity'] = 'missing'
            if mutation == 'final': o['frames'] += 1
            with self.subTest(mutation=mutation), self.assertRaises(ContractError):
                assess_observation_findings(o, o['binding'], self.findings, expectations=self.manifest)

    def test_synthetic_basis_cannot_calibrate_actual_evidence_declarations(self):
        # Only contradictory synthetic declarations, not an actual emulator run.
        self.obs.update(provenance='actual_emulator', method='automated_runtime')
        for capture in self.obs['captures']:
            capture['evidence']['provenance']['method'] = 'automated_runtime'
        for status in ('passed', 'failed'):
            for finding in self.findings:
                finding.update(status=status, reason='Contradictory invented declaration')
            with self.assertRaises(ContractError): self.assess()
        for finding in self.findings:
            finding.update(status='unknown', reason='Synthetic expectations cannot calibrate actual evidence')
        self.assertEqual(self.assess()['status'], 'unknown')
        self.plan['basis']['method'] = 'independent_inspection'
        self.pin(self.manifest)
        self.assertEqual(self.assess()['status'], 'passed')


class CaptureSelectionContractTests(unittest.TestCase):
    """Metadata-only adversarial receipts, never actual runtime proof."""
    def setUp(self):
        fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))['connectors']
        self.obs = copy.deepcopy(fixture['CaseObservation'])
        self.obs['assertion'] = 'not_assessed'
        early = copy.deepcopy(self.obs['captures'][0])
        early['frame'] = 3
        early['evidence']['evidence_id'] = 'invented-early-page'
        early['evidence']['media_type'] = 'image/png'
        self.obs['captures'].insert(0, early)
        self.obs['binding']['detectors']['image_region'] = '2'
        self.plan = dict(schema_version=2, expectation_id='invented-capture-plan',
            case_sha256=self.obs['case_sha256'], basis=dict(method='synthetic_control',
                reference_sha256='a'*64, reason='Independent invented region design'),
            checks=[dict(id='required-page', kind='image_region', capture={'frame':3},
                         rect=[0,0,1,1], rgb_sha256='b'*64, expected_match=True)], exceptions=[])
        self.finding = copy.deepcopy(fixture['DetectorFinding'])
        self.pin()

    def pin(self):
        digest = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True,
            ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
        pin = digest(self.plan)
        self.obs['binding']['expectation_sha256'] = pin
        self.finding.update(detector_id='image_region', detector_version='2',
            binding=copy.deepcopy(self.obs['binding']), expectation_id=self.plan['expectation_id'],
            finding_id='detector-' + digest([self.obs['observation_id'], 'required-page', pin]),
            evidence_ids=['invented-early-page'])

    def assess(self):
        return assess_observation_findings(self.obs, self.obs['binding'], [self.finding],
                                           expectations=self.plan)

    def test_intermediate_evidence_keeps_original_identity_and_frames(self):
        before = copy.deepcopy((self.obs, self.plan, self.finding))
        self.assertEqual(self.assess()['status'], 'passed')
        self.assertEqual(before, (self.obs, self.plan, self.finding))
        self.assertEqual(self.obs['frames'], 12)

    def test_other_capture_or_extra_evidence_cannot_satisfy_selected_page(self):
        for ids in (['capture-one'], ['invented-early-page', 'capture-one']):
            self.finding['evidence_ids'] = ids
            with self.subTest(ids=ids), self.assertRaises(ContractError): self.assess()

    def test_duplicate_same_byte_capture_is_ambiguous(self):
        duplicate = copy.deepcopy(self.obs['captures'][0])
        duplicate['evidence']['evidence_id'] = 'invented-duplicate'
        self.obs['captures'].append(duplicate)
        with self.assertRaises(ContractError): self.assess()
        self.finding.update(status='unknown', reason='Ambiguous selected frame', evidence_ids=[])
        self.assertEqual(self.assess()['status'], 'unknown')

    def test_unavailable_frame_is_unknown_and_never_final_fallback(self):
        for frame in (7, 13, 2**63-1):
            self.plan['checks'][0]['capture']['frame'] = frame
            self.pin()
            with self.subTest(frame=frame), self.assertRaises(ContractError): self.assess()
            self.finding.update(status='unknown', reason='Selected frame unavailable', evidence_ids=[])
            self.assertEqual(self.assess()['status'], 'unknown')
            self.finding.update(status='passed', reason='')
        self.assertIsNone(expectation_capture_frame(self.plan['checks'][0], 2, 12))

    def test_selector_shape_and_version_are_enforced(self):
        check = self.plan['checks'][0]
        for selector in ({}, {'frame':True}, {'frame':-1}, {'frame':2**63},
                         {'frame':3, 'fallback':12}, {'frame':'3'}, None):
            bad = dict(check, capture=selector)
            with self.subTest(selector=selector), self.assertRaises(ContractError):
                expectation_capture_frame(bad, 2, None)
        for version in (1, True, 3):
            with self.assertRaises(ContractError): expectation_capture_frame(check, version, 12)
        with self.assertRaises(ContractError):
            expectation_capture_frame(dict(check, kind='completion'), 2, 12)
        self.assertEqual(expectation_capture_frame({'kind':'image_region'}, 1, 12), 12)

    def test_unverified_selected_capture_and_wrong_algorithm_cannot_pass(self):
        self.obs['captures'][0]['evidence']['integrity'] = 'missing'
        with self.assertRaises(ContractError): self.assess()
        self.obs['captures'][0]['evidence']['integrity'] = 'verified'
        self.obs['binding']['detectors']['image_region'] = '1'
        self.pin(); self.finding['detector_version'] = '1'
        with self.assertRaises(ContractError): self.assess()


if __name__=='__main__':unittest.main()

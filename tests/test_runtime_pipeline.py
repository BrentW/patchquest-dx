"""Invented spawned-runner -> artifacts -> detectors -> authoritative Store seam."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from _bootstrap import ROOT
from test_state import project, invented
from test_runtime_sweep import invented_factory, digest
from patchquest.runtime_artifact_state import ArtifactState
from patchquest.runtime_artifacts import RuntimeArtifacts, reference
from patchquest.runtime_contracts import (CAPABILITIES, contract_digest, validate, check_finding,
    check_coverage_runtime_links, COVERAGE_STATUSES, ContractError)
from patchquest import runtime_contracts as contracts
from patchquest.runtime_scenes import SceneLibrary
from patchquest.runtime_sweep import case_inventory, run_sweep
from patchquest import runtime_detectors as detectors
from patchquest.state import Store, Conflict


class RuntimePipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.store=Store(project(self.root))
        self.store.put(invented('greeting'),0,role='human');self.before=self.store.get('greeting')
        fixture=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.binding=copy.deepcopy(fixture['RunBinding']);self.binding['snapshot']=self.store.snapshot()['sha256']
        self.binding['detectors']=dict(detectors.DETECTOR_VERSIONS)
        self.caps=copy.deepcopy(fixture['AdapterCapabilities'])
        self.caps['capabilities']={k:k!='enumerate_messages' for k in CAPABILITIES}
        self.configuration=dict(caps=self.caps,binary_sha256=self.binding['emulator']['sha256'],instrumentation=True)
        self.binding['configuration_sha256']=digest(self.configuration)
        self.raw=b'Independent pipeline build fixture'
        self.binding['artifacts']={'rom':hashlib.sha256(self.raw).hexdigest()}
        self.output=self.store.context.output.write_new('pipeline.fixture',self.raw)
        self.build=self.store.build(dict(id=self.binding['build_id'],snapshot=self.binding['snapshot'],status='validated',artifacts={'rom':str(self.output)}),0)
        self.connector=ArtifactState(self.store,self.store.directory/'runtime-artifacts')
        self.artifacts=RuntimeArtifacts(self.connector.directory,budget_bytes=1024*1024,graph_guard=self.connector.guard)
        ref=reference(self.raw,evidence_id='pipeline-build',media_type='application/octet-stream',provenance=dict(producer='invented-pipeline',method='synthetic',run_id=None,case_id=None))
        self.build_refs={'rom':self.artifacts.register(ref,self.raw)}
        self.cases=[];self.scenes=[];self.exercises={};self.expectations=[]
        for index in range(2):
            case=copy.deepcopy(fixture['CaseSpec']);case.update(case_id='pipeline-case-'+str(index),variant_id='window-'+str(index))
            self.cases.append(case)
            scene=dict(schema_version=1,scene_id='pipeline-scene-'+str(index),case=case,reach_method='cold_boot_navigation',checkpoint=None,checkpoint_binding=None,regenerate_from=None,steps=[],arrival_assertions=[dict(kind='region_hash',label='invented-arrival',rect=[0,0,1,1],sha256=hashlib.sha256(b'\x03\x07\x0b').hexdigest())],limits=dict(frames=20,seconds=10,attempts=1))
            self.scenes.append(scene);self.exercises[case['case_id']]=dict(scene_id=scene['scene_id'],steps=[dict(frames=1,buttons=[],capture=True)])
            self.expectations.append(dict(schema_version=1,expectation_id='pipeline-expectation-'+str(index),case_sha256=contract_digest('CaseSpec',case),basis=dict(method='synthetic_control',reference_sha256=hashlib.sha256(b'Independent invented one-pixel design').hexdigest(),reason='Invented geometry/glyph/control expectations independently specified before the subprocess run.'),checks=[dict(id='glyph-stream',kind='glyphs',glyph_ids=['invented-glyph']),dict(id='final-page',kind='completion')],exceptions=[]))
        self.pin_expectations()

    def pin_expectations(self):
        self.expected_manifest=detectors.expectation_manifest(self.expectations)
        self.binding['expectation_sha256']=detectors.expectation_digest(self.expected_manifest)

    def tearDown(self):
        self.assertEqual(self.store.get('greeting'),self.before)
        self.assertEqual(self.output.read_bytes(),self.raw)

    def capture(self):
        manifest=run_sweep(case_inventory(self.cases,scope=self.cases[0]['coverage_scope'],source='invented pipeline inventory'),SceneLibrary(self.scenes),self.exercises,self.binding,self.caps,self.artifacts,self.build_refs,self.configuration,invented_factory,self.root/'run',limits=dict(startup_seconds=5,case_seconds=3,shutdown_seconds=.3,total_seconds=20,worker_cases=2))
        self.connector.record_run(self.build['id'],manifest['observations'],expected=1)
        return manifest

    def publish_findings(self, findings, *, expected):
        # Explicit composition-root use of the existing Store/build CAS API.
        # This is not an advertised automatic runner publication feature.
        build=next(b for b in self.store.builds() if b['id']==self.build['id'])
        build.pop('revision')
        observed={o['observation_id']:o for o in build['validation']['runtime_cases']}
        for finding in findings:check_finding(finding,observed[finding['observation_id']])
        build['validation']['runtime_findings']=copy.deepcopy(findings)
        return self.store.build(build,expected)

    def first_findings(self, manifest):
        return detectors.detect(self.cases[0],manifest['observations'][0],self.caps,self.expected_manifest,self.artifacts.resolve,expected_binding=self.binding)

    def coverage(self, observation, findings, status):
        case=self.cases[0];counts=dict.fromkeys(COVERAGE_STATUSES,0);counts[status]=1
        return validate('CoverageReport',dict(schema_version=1,kind='CoverageReport',report_id='pipeline-coverage',binding=observation['binding'],
            scope=dict(id='pipeline-renderer-scope',description='One independently invented renderer case',case_ids=[case['case_id']],case_digests={case['case_id']:contract_digest('CaseSpec',case)},extraction_completeness='unknown',extraction_basis=''),
            sections=[dict(scope_kind='renderer',method='synthetic',rows=[dict(case_id=case['case_id'],status=status,reason='Invented deliberate defect' if status=='failed' else '',observation_ids=[observation['observation_id']],finding_ids=[f['finding_id'] for f in findings])],denominator=1,counts=counts,passed_percent=100 if status=='passed' else 0)],gap_candidates=[]))

    def test_complete_passing_findings_can_support_coverage_without_rewriting_capture(self):
        manifest=self.capture();obs=manifest['observations'][0];findings=self.first_findings(manifest)
        self.assertTrue(all(f['status']=='passed' for f in findings))
        report=self.coverage(obs,findings,'passed')
        self.assertEqual(check_coverage_runtime_links(report,[obs],findings,expectations=self.expected_manifest),report)
        self.assertEqual(obs['assertion'],'not_assessed')

    def test_spawned_multi_capture_checks_preserve_required_early_failure(self):
        # The invented worker yields one color at frame 1 and another later.
        # Deliberately expecting the later color at frame 1 must fail, even
        # though the final image matches. No real emulator or private inputs.
        self.binding['detectors']['image_region'] = '2'
        for case, plan in zip(self.cases, self.expectations):
            plan['schema_version'] = 2
            plan['checks'] = [dict(id=label, kind='image_region', capture={'frame':frame},
                rect=[0,0,1,1], rgb_sha256=hashlib.sha256(b'\x02\x04\x06').hexdigest(),
                expected_match=True) for label, frame in (('required-early',1),('final-diagnostic',3))]
            self.exercises[case['case_id']]['steps'] = [dict(frames=1, buttons=[], capture=True),
                                                       dict(frames=1, buttons=[], capture=True)]
        self.pin_expectations()
        manifest = self.capture(); original = copy.deepcopy(manifest)
        obs = manifest['observations'][0]; findings = self.first_findings(manifest)
        self.assertEqual([f['status'] for f in findings], ['failed','passed'])
        self.assertEqual(obs['frames'], 3)
        selected = {c['frame']:c['evidence']['evidence_id'] for c in obs['captures']}
        self.assertEqual([f['evidence_ids'] for f in findings], [[selected[1]],[selected[3]]])
        report = self.coverage(obs, findings, 'failed')
        self.assertEqual(check_coverage_runtime_links(report, [obs], findings,
                         expectations=self.expected_manifest), report)
        with self.assertRaises(ContractError):
            check_coverage_runtime_links(self.coverage(obs, findings[1:], 'passed'), [obs],
                                         findings[1:], expectations=self.expected_manifest)
        self.publish_findings(findings, expected=2)
        stored = next(b for b in self.store.builds() if b['id'] == self.build['id'])
        self.assertEqual(stored['validation']['runtime_cases'], original['observations'])
        self.assertEqual(manifest, original)

    def test_failed_detector_can_support_failed_coverage_without_rewriting_capture(self):
        self.expectations[0]['checks'][0]['glyph_ids']=['invented-deliberate-wrong-glyph']
        self.pin_expectations()
        manifest=self.capture();obs=manifest['observations'][0];findings=self.first_findings(manifest)
        self.assertIn('failed',[f['status'] for f in findings])
        report=self.coverage(obs,findings,'failed')
        self.assertEqual(check_coverage_runtime_links(report,[obs],findings,expectations=self.expected_manifest),report)
        self.assertEqual(obs['assertion'],'not_assessed')

    def test_partial_passing_findings_cannot_prove_a_complete_case(self):
        manifest=self.capture();obs=manifest['observations'][0];findings=self.first_findings(manifest)[:1]
        with self.assertRaises(ContractError):check_coverage_runtime_links(self.coverage(obs,findings,'passed'),[obs],findings,expectations=self.expected_manifest)

    def test_manifest_findings_match_the_shared_complete_required_plan(self):
        manifest=self.capture()
        self.assertEqual(contracts.expectation_manifest_data(self.expected_manifest),self.expected_manifest)
        for case,obs in zip(self.cases,manifest['observations']):
            findings=detectors.detect(case,obs,self.caps,self.expected_manifest,self.artifacts.resolve)
            expected=contracts.required_finding_plan(obs,self.expected_manifest)
            actual={f['finding_id']:{k:f[k] for k in ('detector_id','detector_version','expectation_id')} for f in findings}
            self.assertEqual(actual,expected)

    def test_duplicate_or_cross_case_findings_cannot_satisfy_the_plan(self):
        manifest=self.capture();first,second=manifest['observations'];findings=self.first_findings(manifest)
        report=self.coverage(first,findings,'passed')
        with self.assertRaises(ContractError):check_coverage_runtime_links(report,[first],findings+[findings[0]],expectations=self.expected_manifest)
        others=detectors.detect(self.cases[1],second,self.caps,self.expected_manifest,self.artifacts.resolve)
        with self.assertRaises(ContractError):check_coverage_runtime_links(self.coverage(first,others,'passed'),[first,second],others,expectations=self.expected_manifest)

    def test_changed_revision_report_cannot_inherit_a_completed_case_pass(self):
        manifest=self.capture();obs=manifest['observations'][0];findings=self.first_findings(manifest)
        report=self.coverage(obs,findings,'passed');report['binding']['records']['greeting']+=1
        with self.assertRaises(ContractError):check_coverage_runtime_links(report,[obs],findings,expectations=self.expected_manifest)

    def test_completed_capture_preserves_final_telemetry_and_not_assessed(self):
        manifest=self.capture()
        for case,obs in zip(self.cases,manifest['observations']):
            self.assertEqual(obs['execution'],'completed');self.assertEqual(obs['assertion'],'not_assessed')
            self.assertEqual(obs['case_sha256'],contract_digest('CaseSpec',case))
            self.assertEqual(obs['binding']['records'],{'greeting':1})
            self.assertEqual(obs['glyphs'][0]['frame'],obs['frames'])
            self.assertTrue(obs['controls']['page_complete'])
        self.assertEqual(self.store.builds()[0]['validation']['runtime_cases'],manifest['observations'])

    def test_deduplicated_bytes_keep_each_case_provenance(self):
        manifest=self.capture();a,b=[o['captures'][-1]['evidence'] for o in manifest['observations']]
        self.assertEqual(a['sha256'],b['sha256']);self.assertNotEqual(a['evidence_id'],b['evidence_id'])
        self.assertNotEqual(a['provenance']['case_id'],b['provenance']['case_id'])
        self.assertIsInstance(self.artifacts.resolve(a)['data'],bytes)
        self.assertEqual(a['provenance']['method'],'synthetic')

    def test_changed_bytes_cannot_reuse_a_verified_capture_label(self):
        manifest=self.capture();ref=manifest['observations'][0]['captures'][-1]['evidence']
        self.assertEqual(ref['integrity'],'verified')
        # Deliberate corruption only in this invented disposable temporary store.
        (self.artifacts.directory/ref['sha256']).write_bytes(b'invented corruption')
        findings=self.first_findings(manifest)
        self.assertTrue(all(f['status']=='unknown' for f in findings))
        obs=manifest['observations'][0]
        with self.assertRaises(ContractError):check_coverage_runtime_links(self.coverage(obs,findings,'passed'),[obs],findings,expectations=self.expected_manifest)

    def test_real_glyphless_worker_is_unsupported_and_unobserved_worker_is_unknown(self):
        self.configuration['instrumentation']=False
        self.caps['capabilities']['observe_glyphs']=False
        self.binding['configuration_sha256']=digest(self.configuration)
        manifest=self.capture();findings=self.first_findings(manifest)
        self.assertEqual(findings[0]['status'],'unsupported');self.assertEqual(findings[1]['status'],'unknown')

    def test_advertised_but_unobserved_worker_does_not_pass(self):
        self.configuration['instrumentation']=False;self.binding['configuration_sha256']=digest(self.configuration)
        manifest=self.capture();self.assertTrue(manifest['capture_complete'])
        self.assertTrue(all(f['status']=='unknown' for f in self.first_findings(manifest)))

    def test_persisted_failure_does_not_rewrite_capture_assertion_or_approval(self):
        self.expectations[0]['checks'][0]['glyph_ids']=['invented-fault']
        self.pin_expectations()
        manifest=self.capture();findings=self.first_findings(manifest)
        saved=self.publish_findings(findings,expected=2)
        self.assertIn('failed',[f['status'] for f in saved['validation']['runtime_findings']])
        self.assertEqual(saved['validation']['runtime_cases'],manifest['observations'])
        self.assertTrue(all(o['assertion']=='not_assessed' for o in saved['validation']['runtime_cases']))
        self.assertFalse(saved.get('approval',{}).get('approved',False))

    def test_stale_state_publication_preserves_manifest_and_newer_build(self):
        manifest=self.capture();findings=self.first_findings(manifest)
        path=self.root/'run/manifest.json';raw=path.read_bytes()
        self.publish_findings(findings,expected=2)
        with self.assertRaises(Conflict):self.publish_findings(findings,expected=2)
        self.assertEqual(path.read_bytes(),raw)
        self.assertEqual(self.store.builds()[0]['revision'],3)

    def test_human_revision_drift_is_unknown_without_rewriting_observations(self):
        manifest=self.capture();obs=manifest['observations'][0]
        self.store.put(invented('greeting',target='Protected later human correction.'),1,role='human')
        self.before=self.store.get('greeting')
        current=copy.deepcopy(self.binding);current['records']['greeting']=self.before['revision']
        findings=detectors.detect(self.cases[0],obs,self.caps,self.expected_manifest,self.artifacts.resolve,expected_binding=current)
        self.assertTrue(all(f['status']=='unknown' for f in findings));self.assertEqual(obs['binding']['records']['greeting'],1)

    def test_pin_or_detector_version_mismatch_fails_closed_after_real_capture(self):
        manifest=self.capture();obs=manifest['observations'][0];expectation=copy.deepcopy(self.expected_manifest)
        expectation['cases'][contract_digest('CaseSpec',self.cases[0])]['checks'][0]['glyph_ids']=['changed-expectation']
        with self.assertRaises(detectors.DetectorError):detectors.detect(self.cases[0],obs,self.caps,expectation,self.artifacts.resolve)
        changed=copy.deepcopy(obs);changed['binding']['detectors']['glyphs']='unknown-version'
        with self.assertRaises(detectors.DetectorError):detectors.detect(self.cases[0],changed,self.caps,self.expected_manifest,self.artifacts.resolve)
        self.assertEqual(json.loads((self.root/'run/manifest.json').read_text())['observations'][0],obs)

    def test_batch_can_detect_both_context_variants_without_rewriting_observations(self):
        manifest=self.capture();self.assertTrue(manifest['capture_complete'])
        findings=[]
        before=copy.deepcopy(manifest['observations'])
        for case,obs in zip(self.cases,manifest['observations']):
            findings.extend(detectors.detect(case,obs,self.caps,self.expected_manifest,self.artifacts.resolve,expected_binding=self.binding))
        self.assertEqual(manifest['observations'],before)
        self.assertTrue(all(o['binding']['expectation_sha256']==detectors.expectation_digest(self.expected_manifest) for o in before))
        self.assertEqual({f['expectation_id'] for f in findings},{e['expectation_id'] for e in self.expectations})
        self.assertEqual(len(findings),4)
        self.assertTrue(all(f['status']=='passed' for f in findings))

    def test_findings_can_persist_separately_from_captured_observations(self):
        manifest=self.capture();obs=manifest['observations'][0]
        findings=detectors.detect(self.cases[0],obs,self.caps,self.expected_manifest,self.artifacts.resolve)
        saved=self.publish_findings(findings,expected=2)
        self.assertEqual(saved['validation']['runtime_cases'],manifest['observations'])
        self.assertEqual(saved['validation']['runtime_findings'],findings)
        self.assertTrue(all(o['assertion']=='not_assessed' for o in saved['validation']['runtime_cases']))


if __name__=='__main__':unittest.main()

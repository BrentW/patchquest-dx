"""Independently invented impact planning; no native/private data or benchmark."""
import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from contextlib import contextmanager
from _bootstrap import ROOT
from patchquest.runtime_contracts import validate,contract_digest,COVERAGE_STATUSES
from patchquest.runtime_regression import plan_changes,dependency_map,ordered_cases,RegressionError

def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class TinyAdapter:
    def __init__(self,config):self.config=config
    def reset(self,inputs,configuration,sandbox):self.inputs=inputs
    def describe(self):return dict(kind='synthetic',version='1',sha256=self.config['binary'])
    def capabilities(self):return self.config['caps']
    def configuration(self):return self.config
    def loaded_artifacts(self):return {k:hashlib.sha256(v).hexdigest() for k,v in self.inputs.items()}
    def step(self,buttons):
        from patchquest.runtime import Frame
        return Frame(1,1,bytes([3,5,7]))
    def observe(self,case,frame):return {}
    def close(self):pass
def tiny_factory(config):return TinyAdapter(config)
@contextmanager
def invented_graph():
    yield dict(revision='invented-only',complete=True,references=[],pins=[],leases=[],ownership={})

class RegressionTests(unittest.TestCase):
    def setUp(self):
        fixture=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.b=copy.deepcopy(fixture['RunBinding']);self.b['records']={'alpha':1,'beta':1};self.old=copy.deepcopy(self.b)
        self.cases=[]
        for cid,record,context in [('case-a','alpha','day'),('case-b','beta','night')]:
            c=copy.deepcopy(fixture['CaseSpec']);c.update(case_id=cid,record_ids=[record],context_id=context,required_capabilities=['capture_frames']);self.cases.append(c)
        self.old_cases=copy.deepcopy(self.cases)
        self.revs={'font:shared':'1','context:day':'1','context:night':'1'}
        self.maps={'case-a':['font:shared','context:day'],'case-b':['font:shared','context:night']}
        self.before=dependency_map(self.old_cases,self.old,self.revs,self.maps,complete=True)
        self.report=self.report_for()

    def report_for(self,statuses=None,method='synthetic'):
        statuses=statuses or ['passed','passed'];counts=dict.fromkeys(COVERAGE_STATUSES,0);rows=[]
        for c,status in zip(self.old_cases,statuses):
            counts[status]+=1;rows.append(dict(case_id=c['case_id'],status=status,reason='' if status=='passed' else 'Invented historical '+status,observation_ids=['old-'+c['case_id']],finding_ids=[]))
        return validate('CoverageReport',dict(schema_version=1,kind='CoverageReport',report_id='invented-baseline',binding=self.old,
            scope=dict(id='invented-scope',description='Only two independently invented renderer cases',case_ids=[c['case_id'] for c in self.old_cases],case_digests={c['case_id']:contract_digest('CaseSpec',c) for c in self.old_cases},extraction_completeness='unknown',extraction_basis=''),
            sections=[dict(scope_kind='renderer',method=method,rows=rows,denominator=2,counts=counts,passed_percent=round(100*counts['passed']/2,2))],gap_candidates=[]))

    def plan(self,**kwargs):
        args=dict(baseline_binding=self.old,dependencies=dependency_map(self.cases,self.b,self.revs,self.maps,complete=True),baseline_dependencies=self.before,prior_report=self.report,prior_method='synthetic');args.update(kwargs)
        return plan_changes(self.cases,self.b,**args)
    def selected(self,p):return [x['case_id'] for x in p['selected']]
    def test_unchanged_complete_scope_can_defer_but_never_awards_verification(self):
        p=self.plan();self.assertEqual(self.selected(p),[]);self.assertEqual(len(p['deferred']),2)
        self.assertFalse(p['extensions']['patchquest:regression']['verification_awarded'])
        self.assertTrue(all('NOT verified' in row['reason'] for row in p['deferred']))
        self.assertTrue({'normal-gameplay','cold-boot','save-load','audio'}<=set(p['additional_checks']))

    def test_exact_record_revision_change_selects_all_composed_consumers(self):
        self.b['records']['alpha']=2;self.b['artifacts']['rom']='d'*64
        p=self.plan();self.assertEqual(self.selected(p),['case-a']);self.assertEqual(p['deferred'][0]['case_id'],'case-b')
        self.cases[1]['record_ids'].append('alpha');p=self.plan();self.assertEqual(set(self.selected(p)),{'case-a','case-b'})

    def test_each_known_dependency_category_selects_its_exact_consumers(self):
        for category in ('context','layout','font','control','pointer','renderer','scenario','configuration'):
            with self.subTest(category=category):
                key=category+':local';self.revs[key]='1';self.maps['case-a'].append(key)
                before=dependency_map(self.cases,self.old,self.revs,self.maps,complete=True)
                self.revs[key]='2';p=self.plan(baseline_dependencies=before)
                self.assertEqual(self.selected(p),['case-a']);self.maps['case-a'].pop();self.revs.pop(key)

    def test_shared_font_or_controls_expand_to_full_relevant_scope(self):
        self.revs['font:shared']='2';p=self.plan();self.assertTrue(p['full_sweep_required']);self.assertEqual(len(p['selected']),2)
        self.revs['font:shared']='1';self.revs['control:shared']='1'
        for row in self.maps.values():row.append('control:shared')
        before=dependency_map(self.cases,self.old,self.revs,self.maps,complete=True);self.revs['control:shared']='2'
        self.assertTrue(self.plan(baseline_dependencies=before)['full_sweep_required'])

    def test_unknown_missing_incomplete_and_stale_graphs_force_full_scope(self):
        current=dependency_map(self.cases,self.b,self.revs,self.maps,complete=True)
        variants=[None,dict(current,complete=False),dict(current,binding_sha256='e'*64)]
        missing=copy.deepcopy(current);missing['revisions'].pop('font:shared');variants.append(missing)
        wrong=copy.deepcopy(current);wrong['cases']['case-a']['case_sha256']='f'*64;variants.append(wrong)
        for g in variants:
            with self.subTest(graph=g):self.assertTrue(self.plan(dependencies=g)['full_sweep_required'])

    def test_unknown_category_or_unmapped_change_cannot_narrow_selection(self):
        self.revs['mystery:opaque']='2';self.assertTrue(self.plan()['full_sweep_required'])
        self.revs.pop('mystery:opaque');self.revs['font:unmapped']='2';self.assertTrue(self.plan()['full_sweep_required'])

    def test_unexplained_new_binary_snapshot_or_expectation_forces_full(self):
        for key in ('snapshot','expectation_sha256','build_id'):
            saved=self.b[key];self.b[key]='changed-build' if key=='build_id' else 'e'*64
            self.assertTrue(self.plan()['full_sweep_required']);self.b[key]=saved
        self.b['artifacts']['rom']='f'*64;self.assertTrue(self.plan()['full_sweep_required'])

    def test_config_core_detector_and_unmapped_scenario_changes_are_global(self):
        self.b['configuration_sha256']='a'*64;self.assertTrue(self.plan()['full_sweep_required'])
        self.b=copy.deepcopy(self.old);self.b['emulator']['sha256']='b'*64;self.assertTrue(self.plan()['full_sweep_required'])
        self.b=copy.deepcopy(self.old);self.b['detectors']['invented']='2';self.assertTrue(self.plan()['full_sweep_required'])
        self.b=copy.deepcopy(self.old);self.b['scenario_sha256']='c'*64;self.assertTrue(self.plan()['full_sweep_required'])

    def test_scoped_scenario_change_is_explainable_without_full_fallback(self):
        self.revs['scenario:local']='1';self.maps['case-a'].append('scenario:local')
        before=dependency_map(self.cases,self.old,self.revs,self.maps,complete=True)
        self.revs['scenario:local']='2';self.b['scenario_sha256']='c'*64
        self.assertEqual(self.selected(self.plan(baseline_dependencies=before)),['case-a'])

    def test_failed_stale_unknown_unsupported_and_interrupted_prior_cases_are_selected(self):
        for status in ('failed','stale','unknown','unsupported','interrupted','in_progress','untested','excluded'):
            with self.subTest(status=status):self.assertEqual(self.selected(self.plan(prior_report=self.report_for([status,'passed']))),['case-a'])

    def test_interrupted_batch_replanning_keeps_exact_baseline_and_changes_plan_identity(self):
        self.b['records']['beta']=2
        interrupted=self.report_for(['interrupted','passed']);before=copy.deepcopy(interrupted)
        first=self.plan(prior_report=interrupted)
        self.assertEqual(self.selected(first),['case-b','case-a'])
        self.assertEqual(first,self.plan(prior_report=interrupted));self.assertEqual(interrupted,before)
        after=self.plan(prior_report=self.report_for())
        self.assertEqual(self.selected(after),['case-b']);self.assertNotEqual(first['plan_id'],after['plan_id'])
        self.assertIn('NOT verified',after['deferred'][0]['reason'])

    def test_normal_gameplay_report_cannot_replace_renderer_history(self):
        report=self.report_for(method='automated_runtime');report['sections'][0]['scope_kind']='normal_gameplay'
        validate('CoverageReport',report)
        self.assertTrue(self.plan(prior_report=report,prior_method='automated_runtime')['full_sweep_required'])

    def test_old_binding_or_wrong_method_and_absent_evidence_force_capture(self):
        self.report['binding']['snapshot']='a'*64;self.assertTrue(self.plan()['full_sweep_required'])
        self.report=self.report_for();self.assertTrue(self.plan(prior_report=None)['full_sweep_required'])
        self.assertTrue(self.plan(prior_method='automated_runtime')['full_sweep_required'])

    def test_explicit_full_and_missing_baseline_always_select_every_case(self):
        self.assertTrue(self.plan(full_sweep=True)['full_sweep_required'])
        self.assertTrue(self.plan(baseline_binding=None)['full_sweep_required'])

    def test_new_context_case_and_stale_case_evidence_are_not_reused(self):
        self.cases[0]['context_id']='invented-new-context';self.assertEqual(self.selected(self.plan()),['case-a'])
        self.cases=copy.deepcopy(self.old_cases);self.report['scope']['case_digests']['case-a']='a'*64
        self.assertEqual(self.selected(self.plan()),['case-a'])

    def test_priority_is_explicit_and_ordered_composition_checks_identity(self):
        self.report=self.report_for(['failed','passed']);self.b['records']['beta']=2
        p=self.plan();self.assertEqual(self.selected(p),['case-b','case-a'])
        self.assertEqual([c['case_id'] for c in ordered_cases(self.cases,p)],['case-b','case-a'])
        self.cases[0]['context_id']='tampered'
        with self.assertRaises(RegressionError):ordered_cases(self.cases,p)

    def test_deterministic_immutable_plan_and_graph(self):
        before=copy.deepcopy((self.cases,self.b,self.old,self.revs,self.maps,self.report,self.before))
        a=self.plan();self.assertEqual(a,self.plan());validate('ChangeImpactPlan',a)
        self.assertEqual((self.cases,self.b,self.old,self.revs,self.maps,self.report,self.before),before)
        a['deferred'].clear();self.assertEqual(len(self.plan()['deferred']),2)

    def test_dependency_order_is_normalized_and_absent_case_mapping_is_unknown(self):
        first=self.plan();self.maps['case-a'].reverse();self.assertEqual(first,self.plan())
        self.maps.pop('case-a');self.assertTrue(self.plan()['full_sweep_required'])

    def test_duplicate_scope_and_malformed_graph_are_rejected(self):
        with self.assertRaises(RegressionError):plan_changes([self.cases[0],self.cases[0]],self.b)
        with self.assertRaises(RegressionError):self.plan(dependencies={'complete':True})
        with self.assertRaises(RegressionError):dependency_map([self.cases[0],self.cases[0]],self.b,self.revs,self.maps,complete=True)

    def test_canonical_opaque_case_ids_are_not_dependency_namespace_ids(self):
        cases=copy.deepcopy(self.cases);cases[0]['case_id']='invented case Ω'
        membership={cases[0]['case_id']:self.maps['case-a'],cases[1]['case_id']:self.maps['case-b']}
        checked=validate('CaseSpec',cases[0]);g=dependency_map(cases,self.b,self.revs,membership,complete=True)
        self.assertIn(checked['case_id'],g['cases'])
        self.assertEqual(g['cases'][checked['case_id']]['case_sha256'],contract_digest('CaseSpec',checked))

    def test_real_runner_selection_seam_excludes_deferred_without_pass(self):
        from patchquest.runtime_sweep import case_inventory,run_sweep
        from patchquest.runtime_artifacts import RuntimeArtifacts,reference
        from patchquest.runtime_scenes import SceneLibrary
        fixture=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        caps=copy.deepcopy(fixture['AdapterCapabilities']);raw=b'independently invented byte input, not a ROM'
        self.b['records']['alpha']=2;self.b['artifacts']={'rom':hashlib.sha256(raw).hexdigest()}
        config=dict(caps=caps,binary=self.b['emulator']['sha256']);self.b['configuration_sha256']=digest(config)
        # Same explicit synthetic adapter configuration at the pinned baseline.
        self.old['configuration_sha256']=self.b['configuration_sha256'];self.before=dependency_map(self.old_cases,self.old,self.revs,self.maps,complete=True);self.report=self.report_for()
        p=self.plan();self.assertEqual(self.selected(p),['case-a'])
        scenes=[];exercises={}
        for c in self.cases:
            sid='scene-'+c['case_id'];scenes.append(dict(schema_version=1,scene_id=sid,case=c,reach_method='cold_boot_navigation',checkpoint=None,checkpoint_binding=None,regenerate_from=None,steps=[],arrival_assertions=[dict(kind='region_hash',label='Independently invented RGB dot',rect=[0,0,1,1],sha256=hashlib.sha256(bytes([3,5,7])).hexdigest())],limits=dict(frames=3,seconds=2,attempts=1)))
            exercises[c['case_id']]=dict(scene_id=sid,steps=[dict(frames=1,buttons=[],capture=True)])
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);artifacts=RuntimeArtifacts(root/'blobs',budget_bytes=65536,graph_guard=invented_graph)
            ref=reference(raw,evidence_id='invented-input',media_type='application/octet-stream',provenance=dict(producer='invented-test',method='synthetic',run_id=None,case_id=None));artifacts.register(ref,raw)
            result=run_sweep(case_inventory(ordered_cases(self.cases,p),scope=self.cases[0]['coverage_scope'],source='Invented only'),SceneLibrary(scenes),exercises,self.b,caps,artifacts,{'rom':ref},config,tiny_factory,root/'run',limits=dict(startup_seconds=5,case_seconds=3,total_seconds=15,shutdown_seconds=1),selection_plan=p)
            self.assertEqual(result['completed'],['case-a']);self.assertEqual(result['excluded'],['case-b']);self.assertFalse(result['capture_complete'])
            deferred=next(o for o in result['observations'] if o['case_id']=='case-b');self.assertEqual(deferred['assertion'],'not_assessed');self.assertEqual(deferred['captures'],[])




class CoverageConsumerTests(unittest.TestCase):
    """Current root receiver -> admitted pure planner; invented Store only."""
    def setUp(self):
        from test_runtime_coverage import CoverageTests
        from patchquest.runtime_coverage import reconcile,read_catalog,catalog_unchanged
        from patchquest.runtime_detectors import expectation_manifest,expectation_digest,detect
        from patchquest.state import canonical
        from patchquest.runtime_regression import coverage_identity
        self.seed=CoverageTests();self.seed.setUp();self.addCleanup(self.seed.doCleanups)
        seed=self.seed;g=seed.fixture();m=json.loads(g['runs'][0]['manifest_bytes']);proof=seed.proof(g)
        first=g['cases'][0];second=copy.deepcopy(first)
        second.update(case_id='invented-other-context',record_ids=['name'],context_id='invented-night')
        original=next(iter(g['runs'][0]['expectations']['cases'].values()))
        other=copy.deepcopy(original);other.update(case_sha256=contract_digest('CaseSpec',second),expectation_id='invented-second-region')
        plan=expectation_manifest([original,other]);binding=copy.deepcopy(g['binding']);binding['expectation_sha256']=expectation_digest(plan)
        one=m['observations'][0];one['binding']=binding
        two=copy.deepcopy(one);two.update(observation_id='observation-context-two',case_id=second['case_id'],case_sha256=contract_digest('CaseSpec',second))
        two['captures'][0]['evidence']['evidence_id']='capture-context-two';two['captures'][0]['evidence']['provenance']['case_id']=second['case_id']
        m['observations']=[one,two];m['definition']['binding']=binding;m['definition']['requests'].append(dict(case=second))
        m['definition_sha256']=digest(m['definition']);g.update(binding=binding,cases=[first,second]);g['runs'][0].update(
            manifest_bytes=canonical(m).encode(),expectations=plan,findings=[f for c,o in [(first,one),(second,two)] for f in detect(c,o,m['definition']['capabilities'],plan,seed.resolve)])
        proof['binding_sha256']=contract_digest('RunBinding',binding)
        proof['purposes'][contract_digest('CaseSpec',second)]={'renderer':dict(reason='Invented second exact context.',reference='Independent invented pixel specification')}
        seed.proofs[hashlib.sha256(g['runs'][0]['manifest_bytes']).hexdigest()]=proof
        g['associations'][second['case_id']]=dict(kind='exact',case_sha256=contract_digest('CaseSpec',second),records={'name':1},basis='Independent invented context mapping')
        g['record_requirements']['name']['case_ids']=sorted([first['case_id'],second['case_id']])
        result=reconcile(seed.store,[g],admit_run=seed.proofs.get,resolve_evidence=seed.resolve)
        self.report=result['groups'][0]['report'];self.catalog=result['catalog_receipt'];self.current=copy.deepcopy(self.catalog)
        self.old=copy.deepcopy(binding);self.binding=copy.deepcopy(binding);self.cases=copy.deepcopy(g['cases'])
        self.revisions={'font:shared':'1','context:day':'1','context:night':'1'}
        self.membership={first['case_id']:['font:shared','context:day'],second['case_id']:['font:shared','context:night']}
        self.baseline_graph=dependency_map(self.cases,self.old,self.revisions,self.membership,complete=True)
        self.key=coverage_identity(self.report,self.catalog)
        self.receipt=dict(coverage_sha256=self.key,binding_sha256=contract_digest('RunBinding',self.old),
            catalog_read_sha256=self.catalog['read_sha256'],scope_kind='renderer',method='synthetic',
            reviewer='Invented trusted composition root',reference='Accepted invented root receiver output',reason='Synthetic consumer boundary only')
        self.admit=lambda key:copy.deepcopy(self.receipt) if key==self.key else None
        self.fresh=lambda receipt:catalog_unchanged(seed.store,receipt)
        self.read_catalog=read_catalog

    def plan(self,**overrides):
        from patchquest.runtime_regression import plan_from_coverage
        args=dict(baseline_binding=self.old,coverage_report=self.report,baseline_catalog=self.catalog,
            current_catalog=self.current,admit_coverage=self.admit,check_catalog=self.fresh,
            dependencies=dependency_map(self.cases,self.binding,self.revisions,self.membership,complete=True),
            baseline_dependencies=self.baseline_graph,prior_method='synthetic')
        args.update(overrides)
        return plan_from_coverage(self.cases,self.binding,**args)

    def test_actual_receiver_report_and_read_receipt_can_defer_without_new_verification(self):
        frozen=copy.deepcopy((self.report,self.catalog,self.current,self.cases,self.binding,self.baseline_graph))
        p=self.plan();self.assertEqual(p['selected'],[]);self.assertEqual(len(p['deferred']),2)
        self.assertTrue(p['extensions']['patchquest:regression']['coverage_consumer']['producer_admitted'])
        self.assertFalse(p['extensions']['patchquest:regression']['verification_awarded'])
        self.assertEqual((self.report,self.catalog,self.current,self.cases,self.binding,self.baseline_graph),frozen)
        self.assertTrue({'normal-gameplay','cold-boot','save-load','audio'}<=set(p['additional_checks']))

    def test_absent_producer_or_fresh_read_always_expands_full_declared_scope(self):
        for changed in ({'admit_coverage':None},{'admit_coverage':lambda key:None},{'check_catalog':None},
                        {'check_catalog':lambda receipt:False},{'current_catalog':None},{'baseline_catalog':None}):
            with self.subTest(fields=list(changed)):
                p=self.plan(**changed);self.assertTrue(p['full_sweep_required']);self.assertEqual(len(p['selected']),2)
                self.assertTrue(all('Production admission fallback' in r['reason'] for r in p['selected']))

    def test_changed_report_or_wrong_review_purpose_cannot_inherit_admission(self):
        report=copy.deepcopy(self.report);report['report_id']='invented-different-report'
        self.assertTrue(self.plan(coverage_report=report)['full_sweep_required'])
        for key,value in [('scope_kind','normal_gameplay'),('method','automated_runtime'),('binding_sha256','0'*64)]:
            proof=copy.deepcopy(self.receipt);proof[key]=value
            with self.subTest(key=key):self.assertTrue(self.plan(admit_coverage=lambda pin:proof)['full_sweep_required'])

    def test_current_human_revision_drift_is_conservative_without_rewriting_history(self):
        from test_state import invented
        self.seed.store.put(invented('greeting',target='Saved invented correction'),1,role='human')
        self.current=self.read_catalog(self.seed.store,['invented-build'])
        p=self.plan();self.assertTrue(p['full_sweep_required'])
        self.assertTrue(any('stale or absent' in r['reason'] for r in p['selected']))
        self.assertEqual(self.report['binding']['records']['greeting'],1)

    def test_valid_target_revision_change_selects_composed_consumer_first_only(self):
        from test_state import invented
        self.seed.store.put(invented('greeting',target='New invented derivative text'),1,role='human')
        snap=self.seed.store.snapshot()['sha256']
        self.seed.store.build(dict(id='invented-target',snapshot=snap,status='validated'),0)
        self.binding.update(build_id='invented-target',snapshot=snap,records={'greeting':2,'name':1},
            artifacts={'rom':hashlib.sha256(b'new invented derivative').hexdigest()})
        self.current=self.read_catalog(self.seed.store,['invented-build','invented-target'])
        p=self.plan();self.assertEqual([r['case_id'] for r in p['selected']],[self.cases[0]['case_id']])
        self.assertEqual([r['case_id'] for r in p['deferred']],[self.cases[1]['case_id']])
        self.assertEqual(p['extensions']['patchquest:regression']['coverage_consumer']['fallback_reasons'],[])
        self.assertTrue(all('NOT verified' in r['reason'] for r in p['deferred']))

    def test_baseline_build_row_change_requires_fresh_coverage_admission(self):
        self.seed.store.build(dict(id='invented-build',snapshot=self.old['snapshot'],status='validated',summary='New invented metadata'),1)
        self.current=self.read_catalog(self.seed.store,['invented-build'])
        self.assertTrue(self.plan()['full_sweep_required'])

    def test_cross_project_receipt_and_unknown_dependencies_never_narrow(self):
        current=copy.deepcopy(self.current);current['identity']['project_id']='another-invented-project'
        current['read_sha256']=digest({k:v for k,v in current.items() if k!='read_sha256'})
        self.assertTrue(self.plan(current_catalog=current,check_catalog=lambda r:True)['full_sweep_required'])
        graph=dependency_map(self.cases,self.binding,self.revisions,self.membership,complete=False)
        self.assertTrue(self.plan(dependencies=graph)['full_sweep_required'])

    def test_malformed_receipt_and_implicit_boolean_trust_are_rejected(self):
        bad=copy.deepcopy(self.current);bad['heads']['greeting']=2
        with self.assertRaises(RegressionError):self.plan(current_catalog=bad)
        with self.assertRaises(RegressionError):self.plan(admit_coverage=True)
        with self.assertRaises(RegressionError):self.plan(check_catalog=True)
        with self.assertRaises(RegressionError):self.plan(full_sweep='yes')

    def test_explicit_full_sweep_keeps_obligations_with_valid_admitted_coverage(self):
        p=self.plan(full_sweep=True);self.assertTrue(p['full_sweep_required'])
        self.assertTrue(all('Explicit full sweep' in r['reason'] for r in p['selected']))
        self.assertEqual(len(ordered_cases(self.cases,p)),2)

if __name__=='__main__':unittest.main()

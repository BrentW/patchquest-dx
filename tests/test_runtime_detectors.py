"""Independent invented detector controls; no actual-emulator or OCR evidence."""
import copy
import hashlib
import json
import struct
import zlib
from pathlib import Path
import unittest
from unittest import mock

from _bootstrap import ROOT
from patchquest.runtime import Frame
from patchquest.runtime_artifacts import reference
from patchquest.runtime_contracts import contract_digest, validate
from patchquest.runtime_detectors import (detect, expectation_digest, expectation_data,
    exception_binding, defect_digest, expectation_manifest, DETECTOR_VERSIONS, DetectorError)


class DetectorTests(unittest.TestCase):
    def setUp(self):
        fixtures=json.loads((ROOT/'tests/fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.case=copy.deepcopy(fixtures['CaseSpec'])
        self.obs=copy.deepcopy(fixtures['CaseObservation'])
        self.caps=copy.deepcopy(fixtures['AdapterCapabilities'])
        self.caps['capabilities']={k:True for k in self.caps['capabilities']}
        # Explicitly include all declared public capabilities, regardless of fixture omissions.
        from patchquest.runtime_contracts import CAPABILITIES
        self.caps['capabilities']={k:True for k in CAPABILITIES}
        self.obs['binding']['detectors']=dict(DETECTOR_VERSIONS)
        self.obs['controls']=dict(page_complete=True,line_advanced=True,scrolled=True,input_wait=True,terminated=True)
        self.obs['glyphs']=[dict(glyph_id='invented-A',frame=12,x=4,y=4,width=4,height=6),
                            dict(glyph_id='invented-B',frame=12,x=10,y=4,width=4,height=6)]
        self.obs['resources']={'tiles':2,'sprites':0}
        self.bytes=Frame(24,16,bytes([16,32,48])*24*16).png()
        self.ref=reference(self.bytes,evidence_id='capture-one',media_type='image/png',
            provenance=self.obs['captures'][0]['evidence']['provenance'],retention='referenced')
        self.ref['integrity']='verified';self.obs['captures'][0]['evidence']=self.ref
        self.exp=dict(schema_version=1,expectation_id='invented-expectations',case_sha256=contract_digest('CaseSpec',self.case),
            basis=dict(method='synthetic_control',reference_sha256=hashlib.sha256(b'independent invented control design').hexdigest(),
                       reason='Independently authored geometry, glyph stream and control expectations.'),
            checks=[dict(id='bounds',kind='bounds',rect=[0,0,24,16],padding=2,tolerance=0),
                    dict(id='overlap',kind='overlap',maximum_overlap_pixels=0),
                    dict(id='glyphs',kind='glyphs',glyph_ids=['invented-A','invented-B']),
                    dict(id='source',kind='source_language',source_glyph_ids=['invented-source-sigil'],mapping_sha256=hashlib.sha256(b'invented mapping').hexdigest()),
                    dict(id='completion',kind='completion'),
                    dict(id='controls',kind='controls',expected=dict(line_advanced=True,scrolled=True,input_wait=True,terminated=True)),
                    dict(id='resources',kind='resources',limits={'tiles':8,'sprites':4})],exceptions=[])

    def resolver(self,ref):return dict(available=True,data=self.bytes)

    def run_checks(self, *, resolver=None, expected_binding=None):
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        return detect(self.case,self.obs,self.caps,self.exp,resolver or self.resolver,expected_binding=expected_binding)

    def result(self,kind):return next(f for f in self.run_checks() if f['detector_id']==kind)

    def test_invented_translated_negative_controls_pass_and_do_not_mutate(self):
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        before=copy.deepcopy((self.case,self.obs,self.caps,self.exp))
        findings=detect(self.case,self.obs,self.caps,self.exp,self.resolver)
        self.assertTrue(all(f['status']=='passed' for f in findings))
        self.assertEqual((self.case,self.obs,self.caps,self.exp),before)
        self.assertTrue(all(f['extensions']['patchquest:detector']['synthetic'] for f in findings))

    def test_clipped_and_padding_overflow_fault(self):
        self.obs['glyphs'][0]['x']=0
        result=self.result('bounds');self.assertEqual(result['status'],'failed')
        self.assertEqual(result['region'],[0,4,4,6]);self.assertEqual(result['evidence_ids'],['capture-one'])

    def test_vertical_overflow_fault(self):
        self.obs['glyphs'][0]['y']=12
        self.assertEqual(self.result('bounds')['status'],'failed')

    def test_overlap_fault_and_independent_tolerance(self):
        self.obs['glyphs'][1]['x']=7
        self.assertEqual(self.result('overlap')['status'],'failed')
        self.exp['checks'][1]['maximum_overlap_pixels']=6
        self.assertEqual(self.result('overlap')['status'],'passed')

    def test_missing_and_wrong_glyph_controls(self):
        for value in ([],self.obs['glyphs'][:1],[dict(self.obs['glyphs'][0],glyph_id='invented-wrong')]):
            with self.subTest(value=value):
                self.obs['glyphs']=copy.deepcopy(value)
                self.assertEqual(self.result('glyphs')['status'],'failed')

    def test_known_source_glyph_positive_and_translated_negative_controls(self):
        self.assertEqual(self.result('source_language')['status'],'passed')
        self.obs['glyphs'][1]['glyph_id']='invented-source-sigil'
        result=self.result('source_language');self.assertEqual(result['status'],'failed')
        self.assertIn('source_glyph',result['extensions']['patchquest:detector']['defects'][0]['code'])

    def test_bitmap_text_without_glyph_instrumentation_is_unsupported(self):
        self.obs['glyphs']=None;self.caps['capabilities']['observe_glyphs']=False
        for f in self.run_checks():
            if f['detector_id'] in ('bounds','overlap','glyphs','source_language'):
                self.assertEqual(f['status'],'unsupported')

    def test_advertised_but_unobserved_glyphs_are_unknown(self):
        self.obs['glyphs']=None
        self.assertEqual(self.result('glyphs')['status'],'unknown')

    def test_empty_visual_observation_cannot_vacuously_pass(self):
        self.obs['glyphs']=[]
        for kind in ('bounds','overlap','source_language'):
            self.assertEqual(self.result(kind)['status'],'unknown')

    def test_in_progress_animation_does_not_become_clipping(self):
        self.obs.update(execution='running',assertion='not_assessed')
        self.obs['glyphs'][0]['x']=-10
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks()))

    def test_unfinished_final_page_flags_completion_but_not_final_geometry(self):
        self.obs['controls']['page_complete']=False
        self.obs['glyphs'][0]['x']=-10
        self.assertEqual(self.result('completion')['status'],'failed')
        self.assertEqual(self.result('bounds')['status'],'unknown')

    def test_broken_page_scroll_wait_and_termination_faults(self):
        for control in ('line_advanced','scrolled','input_wait','terminated'):
            with self.subTest(control=control):
                self.obs['controls'][control]=False
                finding=self.result('controls');self.assertEqual(finding['status'],'failed')
                self.assertEqual(finding['control'],control)
                self.obs['controls'][control]=True

    def test_absent_input_observation_is_unknown_not_false(self):
        self.obs['controls']['input_wait']=None
        self.assertEqual(self.result('controls')['status'],'unknown')

    def test_resource_limit_fault_and_missing_metric(self):
        self.obs['resources']['tiles']=9
        self.assertEqual(self.result('resources')['status'],'failed')
        self.obs['resources']={}
        self.assertEqual(self.result('resources')['status'],'unknown')

    def test_optional_resource_and_scroll_capabilities_are_required(self):
        self.obs['resources']=None;self.caps['capabilities']['observe_resources']=False
        self.obs['controls'].pop('scrolled');self.caps['capabilities']['native_scroll']=False
        self.assertEqual(self.result('resources')['status'],'unsupported')
        self.assertEqual(self.result('controls')['status'],'unsupported')

    def test_tampered_or_missing_capture_bytes_prevent_definite_results(self):
        for resolver in (lambda r:dict(available=False,data=None),lambda r:dict(available=True,data=b'changed')):
            self.assertTrue(all(f['status']=='unknown' for f in self.run_checks(resolver=resolver)))

    def test_resolver_failure_retains_unknown(self):
        def failure(r):raise OSError('Invented unavailable file')
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks(resolver=failure)))

    def test_checked_bytes_are_required_even_when_integrity_claims_verified(self):
        self.assertEqual(self.ref['integrity'],'verified')
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks(resolver=lambda r:dict(available=True,data=b'bad'))))

    def test_capture_must_cover_final_frame(self):
        self.obs['captures'][0]['frame']=11
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks()))

    def test_stale_or_changed_content_binding_cannot_pass(self):
        self.obs.update(validity='stale',reason='Invented old revision')
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks()))
        self.obs.update(validity='current',reason='')
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        expected=copy.deepcopy(self.obs['binding']);expected['records']['greeting']+=1
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks(expected_binding=expected)))

    def test_changed_expectation_requires_new_run_binding(self):
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        self.exp['checks'][0]['tolerance']=1
        with self.assertRaises(DetectorError):detect(self.case,self.obs,self.caps,self.exp,self.resolver)

    def test_algorithm_version_cannot_silently_change(self):
        self.obs['binding']['detectors']['bounds']='future-version'
        with self.assertRaises(DetectorError):self.run_checks()

    def test_exact_exception_preserves_reason_and_does_not_suppress_other_defects(self):
        self.obs['glyphs'][0]['x']=0
        defect=self.result('bounds')['extensions']['patchquest:detector']['defects'][0]
        self.exp['exceptions']=[dict(check_id='bounds',defect_sha256=defect_digest(defect),
            content_binding_sha256=exception_binding(self.obs['binding'], self.obs['case_sha256']),reason='Independently inspected decorative drop cap at this exact position.')]
        finding=self.result('bounds');self.assertEqual(finding['status'],'passed')
        self.assertIn('drop cap',finding['extensions']['patchquest:detector']['suppressed'][0]['exception']['reason'])
        self.obs['glyphs'][1]['x']=22
        self.assertEqual(self.result('bounds')['status'],'failed')

    def test_exception_goes_stale_on_content_revision(self):
        self.obs['glyphs'][0]['x']=0
        defect=self.result('bounds')['extensions']['patchquest:detector']['defects'][0]
        self.exp['exceptions']=[dict(check_id='bounds',defect_sha256=defect_digest(defect),content_binding_sha256=exception_binding(self.obs['binding'], self.obs['case_sha256']),reason='Invented inspected exception.')]
        self.obs['binding']['records']['greeting']+=1
        self.assertEqual(self.result('bounds')['status'],'unknown')

    def test_exception_cannot_migrate_to_another_context_variant(self):
        self.obs['glyphs'][0]['x']=0
        defect=self.result('bounds')['extensions']['patchquest:detector']['defects'][0]
        self.exp['exceptions']=[dict(check_id='bounds',defect_sha256=defect_digest(defect),content_binding_sha256=exception_binding(self.obs['binding'], self.obs['case_sha256']),reason='Original invented context only.')]
        self.case['variant_id']='another-window-context'
        digest=contract_digest('CaseSpec',self.case)
        self.exp['case_sha256']=digest;self.obs['case_sha256']=digest
        self.assertEqual(self.result('bounds')['status'],'unknown')

    def test_exceptions_cannot_turn_unobserved_controls_into_pass(self):
        self.obs['controls']['line_advanced']=False
        defect=self.result('controls')['extensions']['patchquest:detector']['defects'][0]
        self.exp['exceptions']=[dict(check_id='controls',defect_sha256=defect_digest(defect),content_binding_sha256=exception_binding(self.obs['binding'], self.obs['case_sha256']),reason='Invented explicit no-advance case.')]
        self.obs['controls']['input_wait']=None
        self.assertEqual(self.result('controls')['status'],'unknown')

    def test_synthetic_baseline_cannot_calibrate_actual_runtime(self):
        self.obs.update(provenance='actual_emulator',method='automated_runtime')
        self.obs['captures'][0]['evidence']['provenance']['method']='automated_runtime'
        self.caps['provenance']='actual_emulator'
        self.assertTrue(all(f['status']=='unknown' for f in self.run_checks()))

    def test_independently_inspected_expectations_preserve_declared_provenance(self):
        self.exp['basis']['method']='independent_inspection'
        self.assertTrue(all(f['status']=='passed' for f in self.run_checks()))
        self.assertEqual(self.obs['provenance'],'synthetic')

    def test_comparison_budget_is_explicit_unknown(self):
        self.obs['glyphs']=[dict(self.obs['glyphs'][0],x=i*5) for i in range(257)]
        self.assertEqual(self.result('overlap')['status'],'unknown')

    def test_geometry_budget_cannot_suppress_unrelated_resource_or_control_defects(self):
        self.obs['glyphs']=[dict(self.obs['glyphs'][0],x=i) for i in range(4097)]
        self.obs['resources']['tiles']=9
        self.obs['controls']['input_wait']=False
        findings={f['detector_id']:f for f in self.run_checks()}
        self.assertEqual(findings['bounds']['status'],'unknown')
        self.assertEqual(findings['resources']['status'],'failed')
        self.assertEqual(findings['controls']['status'],'failed')

    def test_unknown_schema_fields_checks_and_duplicate_ids_rejected(self):
        for mutate in (lambda e:e.update(schema_version=3),lambda e:e.update(extra=True),
                       lambda e:e['checks'][0].update(kind='ocr-guessed'),lambda e:e['checks'].append(copy.deepcopy(e['checks'][0]))):
            e=copy.deepcopy(self.exp);mutate(e)
            with self.assertRaises(DetectorError):expectation_data(e)

    def test_case_context_variant_mismatch_rejected(self):
        self.case['variant_id']='another-invented-context'
        with self.assertRaises(DetectorError):self.run_checks()

    def test_known_failure_dominates_other_unobserved_metrics(self):
        self.obs['resources']={'tiles':9}
        self.assertEqual(self.result('resources')['status'],'failed')

    def manifest_plans(self):
        other=copy.deepcopy(self.exp)
        other['case_sha256']=hashlib.sha256(b'independently invented other case').hexdigest()
        other['expectation_id']='other-invented-expectations'
        return [self.exp,other]

    def detect_manifest(self, manifest):
        return detect(self.case,self.obs,self.caps,manifest,self.resolver)

    def test_manifest_builder_order_is_stable_and_inputs_detached(self):
        plans=self.manifest_plans();before=copy.deepcopy(plans)
        forward=expectation_manifest(plans);reverse=expectation_manifest(tuple(reversed(plans)))
        self.assertEqual(forward,reverse)
        self.assertEqual(expectation_digest(forward),expectation_digest(reverse))
        self.assertEqual(expectation_digest(forward),hashlib.sha256(json.dumps(forward,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode('utf8')).hexdigest())
        forward['cases'][self.exp['case_sha256']]['basis']['reason']='Detached annotation'
        self.assertEqual(plans,before)

    def test_manifest_selects_exact_case_preserving_binding_and_provenance(self):
        manifest=expectation_manifest(self.manifest_plans())
        self.obs['binding']['expectation_sha256']=expectation_digest(manifest)
        before=copy.deepcopy(self.obs)
        findings=self.detect_manifest(manifest)
        self.assertTrue(all(f['status']=='passed' for f in findings))
        self.assertTrue(all(f['expectation_id']==self.exp['expectation_id'] for f in findings))
        self.assertEqual(self.obs,before)
        self.assertTrue(all(f['binding']==before['binding'] for f in findings))
        self.assertTrue(all(f['extensions']['patchquest:detector']['synthetic'] for f in findings))

    def test_manifest_changed_nonselected_case_invalidates_pin(self):
        plans=self.manifest_plans();manifest=expectation_manifest(plans)
        self.obs['binding']['expectation_sha256']=expectation_digest(manifest)
        manifest['cases'][plans[1]['case_sha256']]['basis']['reason']='Updated independent review'
        with self.assertRaisesRegex(DetectorError,'digest differs'):self.detect_manifest(manifest)

    def test_manifest_validates_invalid_nonselected_plan(self):
        plans=self.manifest_plans();manifest=expectation_manifest(plans)
        self.obs['binding']['expectation_sha256']=expectation_digest(manifest)
        manifest['cases'][plans[1]['case_sha256']]['checks'][0]['padding']=-1
        with self.assertRaisesRegex(DetectorError,'Invalid detector integer'):self.detect_manifest(manifest)

    def test_manifest_missing_case_is_not_filled_by_another_case(self):
        manifest=expectation_manifest(self.manifest_plans()[1:])
        self.obs['binding']['expectation_sha256']=expectation_digest(manifest)
        with self.assertRaisesRegex(DetectorError,'no plan for this case'):self.detect_manifest(manifest)

    def test_manifest_mismatched_case_entry_fails_closed(self):
        plans=self.manifest_plans();manifest=expectation_manifest(plans)
        manifest['cases'][plans[1]['case_sha256']]['case_sha256']=self.exp['case_sha256']
        with self.assertRaisesRegex(DetectorError,'case key differs'):expectation_digest(manifest)

    def test_manifest_builder_rejects_duplicate_case_digests(self):
        with self.assertRaisesRegex(DetectorError,'Duplicate case digest'):
            expectation_manifest([self.exp,copy.deepcopy(self.exp)])

    def test_manifest_unknown_version_algorithm_shape_and_inner_version(self):
        manifest=expectation_manifest(self.manifest_plans())
        for change in (lambda m:m.update(schema_version=2),lambda m:m.update(schema_version=True),
                       lambda m:m.update(finding_id_algorithm='unknown-v2'),lambda m:m.update(extra='unknown'),
                       lambda m:m.update(cases={}),lambda m:m['cases'][self.exp['case_sha256']].update(schema_version=3)):
            bad=copy.deepcopy(manifest);change(bad)
            with self.subTest(bad=bad),self.assertRaises(DetectorError):expectation_digest(bad)

    def test_manifest_uses_common_identity_validation(self):
        manifest=expectation_manifest(self.manifest_plans())
        # Local check parameters are valid; the shared envelope owns this ID limit.
        manifest['cases'][self.exp['case_sha256']]['expectation_id']='x'*201
        with self.assertRaisesRegex(DetectorError,'identity'):expectation_digest(manifest)

    def test_manifest_builder_matches_common_case_budget(self):
        plan=copy.deepcopy(self.exp);plan['checks']=[dict(id='done',kind='completion')]
        plans=[dict(plan,case_sha256=hashlib.sha256(('invented-case-'+str(i)).encode()).hexdigest()) for i in range(1001)]
        manifest=expectation_manifest(plans)
        self.assertEqual(len(manifest['cases']),1001)
        with self.assertRaisesRegex(DetectorError,'bounded'):
            expectation_manifest([self.exp]*10001)

    def test_manifest_check_order_remains_part_of_the_pin(self):
        manifest=expectation_manifest(self.manifest_plans());before=expectation_digest(manifest)
        manifest['cases'][self.exp['case_sha256']]['checks'].reverse()
        self.assertNotEqual(expectation_digest(manifest),before)

    def test_final_glyph_stream_order_is_significant(self):
        self.obs['glyphs'].reverse()
        self.assertEqual(self.result('glyphs')['status'],'failed')


class ImageRegionTests(unittest.TestCase):
    """Invented RGB regions only; no language/native calibration is implied."""
    resolver = DetectorTests.resolver
    run_checks = DetectorTests.run_checks

    def setUp(self):
        DetectorTests.setUp(self)
        self.obs.update(glyphs=None, resources=None, controls={}, assertion='not_assessed')
        self.caps['capabilities']={k:k=='capture_frames' for k in self.caps['capabilities']}
        self.case['required_capabilities']=['capture_frames']
        self.obs['case_sha256']=contract_digest('CaseSpec',self.case)
        self.exp['case_sha256']=self.obs['case_sha256']
        self.exp['checks']=[dict(id='invented-image',kind='image_region',rect=[3,2,4,5],
            rgb_sha256=hashlib.sha256(bytes([16,32,48])*4*5).hexdigest(),expected_match=True)]

    def finding(self,**kwargs):return self.run_checks(**kwargs)[0]

    def replace_bytes(self,raw):
        self.bytes=raw
        ref=reference(raw,evidence_id='capture-one',media_type='image/png',provenance=self.ref['provenance'])
        ref['integrity']='verified';self.obs['captures'][0]['evidence']=ref

    @staticmethod
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)

    @classmethod
    def png(cls,scan,*,width=24,height=16,color=2,interlace=0,extra=b''):
        return (b'\x89PNG\r\n\x1a\n'+cls.chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,color,0,0,interlace))+
            extra+cls.chunk(b'IDAT',zlib.compress(scan))+cls.chunk(b'IEND',b''))

    def test_exact_region_works_without_glyph_page_or_input_telemetry(self):
        self.assertEqual(self.finding()['status'],'passed')
        finding=self.finding();d=finding['extensions']['patchquest:detector']
        self.assertEqual(d['measurement'],'scoped_captured_rgb_region')
        self.assertTrue(d['image_region']['observed_match']);self.assertIsNone(self.obs['glyphs'])

    def test_positive_negative_and_deliberate_pixel_fault(self):
        self.exp['checks'][0]['expected_match']=False
        self.assertEqual(self.finding()['status'],'failed')
        self.replace_bytes(Frame(24,16,bytes([9,8,7])*24*16).png())
        self.assertEqual(self.finding()['status'],'passed')
        self.exp['checks'][0]['expected_match']=True
        self.assertEqual(self.finding()['status'],'failed')

    def test_region_excludes_independently_changed_surroundings(self):
        raw=bytearray(bytes([1,2,3])*24*16)
        for y in range(2,7):raw[(y*24+3)*3:(y*24+7)*3]=bytes([16,32,48])*4
        self.replace_bytes(Frame(24,16,bytes(raw)).png())
        self.assertEqual(self.finding()['status'],'passed')

    def test_all_five_png_filters_reconstruct_the_same_invented_rgb(self):
        # Encode deliberately varying pixels with an independent PNG predictor.
        width=24;height=16;stride=width*3
        rgb=bytes((i*19+i//7)%256 for i in range(stride*height))
        self.exp['checks'][0].update(rect=[0,0,width,height],rgb_sha256=hashlib.sha256(rgb).hexdigest())
        for mode in range(5):
            scan=bytearray();previous=bytes(stride)
            for y in range(height):
                row=rgb[y*stride:(y+1)*stride];scan.append(mode)
                for x,value in enumerate(row):
                    a=row[x-3] if x>=3 else 0;b=previous[x];c=previous[x-3] if x>=3 else 0
                    p=a+b-c
                    if mode==4:prediction=min((a,b,c),key=lambda v:abs(p-v))
                    else:prediction=(0,a,b,(a+b)//2)[mode]
                    scan.append((value-prediction)%256)
                previous=row
            with self.subTest(filter=mode):
                self.replace_bytes(self.png(bytes(scan)))
                self.assertEqual(self.finding()['status'],'passed')

    def test_unsupported_or_corrupt_png_is_unknown_even_for_expected_nonmatch(self):
        self.exp['checks'][0]['expected_match']=False
        scan=(b'\0'+bytes([16,32,48])*24)*16
        cases=[b'not PNG',self.bytes+b'trailing',self.bytes[:-1],
            self.png(scan,color=6),self.png(scan,interlace=1),
            self.png(scan,extra=self.chunk(b'tEXt',b'unsupported metadata')),
            self.png(b'\x05'+scan[1:]),self.png(scan+b'excess'),
            self.png(scan[:-1]),self.png(scan,width=4096,height=4096)]
        corrupt=bytearray(self.bytes);corrupt[-1]^=1;cases.append(bytes(corrupt))
        for raw in cases:
            with self.subTest(length=len(raw)):
                self.replace_bytes(raw);self.assertEqual(self.finding()['status'],'unknown')

    def test_decompression_excess_and_encoded_byte_limit_are_unknown(self):
        # Claimed tiny frame cannot cause unbounded inflation or a mismatch pass.
        self.replace_bytes(self.png(b'\0'*(1024*1024),width=1,height=1))
        self.assertEqual(self.finding()['status'],'unknown')

    def test_png_structure_and_zlib_stream_boundaries_fail_closed(self):
        header=self.chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
        prefix=b'\x89PNG\r\n\x1a\n';end=self.chunk(b'IEND',b'')
        data=zlib.compress(b'\0\x10\x20\x30')
        cases=[prefix+header+end,
            prefix+header+self.chunk(b'IDAT',b'bad zlib')+end,
            prefix+header+self.chunk(b'IDAT',data+zlib.compress(b'extra'))+end,
            prefix+header+self.chunk(b'IDAT',data+b'extra')+end,
            prefix+header+self.chunk(b'IDAT',data[:-1])+end,
            prefix+header+header+self.chunk(b'IDAT',data)+end,
            prefix+self.chunk(b'IDAT',data)+end,
            prefix+header+self.chunk(b'IDAT',data),
            prefix+header+self.chunk(b'IDAT',b'')*4096+end]
        for raw in cases:
            with self.subTest(length=len(raw)):
                self.replace_bytes(raw);self.assertEqual(self.finding()['status'],'unknown')
        self.replace_bytes(b'\x89PNG\r\n\x1a\n'+b'x'*(4*1024*1024))
        self.assertEqual(self.finding()['status'],'unknown')

    def test_outside_frame_is_unknown_not_mismatch(self):
        self.exp['checks'][0]['rect']=[23,15,2,2]
        self.assertEqual(self.finding()['status'],'unknown')

    def test_region_shape_digest_and_boolean_fail_validation(self):
        original=copy.deepcopy(self.exp)
        for changes in ({'rect':[-1,0,1,1]},{'rect':[0,0,4096,4096]},
                        {'expected_match':1},{'rgb_sha256':'bad'},{'rect':[0,0,0,1]}):
            self.exp=copy.deepcopy(original);self.exp['checks'][0].update(changes)
            with self.subTest(changes=changes),self.assertRaises(DetectorError):expectation_data(self.exp)

    def test_stale_incomplete_missing_bytes_and_synthetic_basis_remain_unknown(self):
        self.assertEqual(self.finding(resolver=lambda r:dict(available=False))['status'],'unknown')
        self.obs['execution']='running';self.assertEqual(self.finding()['status'],'unknown')
        self.obs['execution']='completed';self.obs['validity']='stale';self.obs['reason']='Invented stale'
        self.assertEqual(self.finding()['status'],'unknown')
        self.obs.update(validity='current',reason='',provenance='actual_emulator',method='automated_runtime')
        self.caps['provenance']='actual_emulator'
        self.obs['captures'][0]['evidence']['provenance']['method']='automated_runtime'
        self.assertEqual(self.finding()['status'],'unknown')

    def test_ambiguous_final_captures_cannot_choose_a_convenient_image(self):
        other=copy.deepcopy(self.obs['captures'][0]);other['evidence']['evidence_id']='capture-two'
        raw=Frame(24,16,bytes([5,6,7])*24*16).png()
        other['evidence'].update(sha256=hashlib.sha256(raw).hexdigest(),byte_length=len(raw))
        self.obs['captures'].append(other)
        resolver=lambda ref:dict(available=True,data=raw if ref['evidence_id']=='capture-two' else self.bytes)
        self.assertEqual(self.finding(resolver=resolver)['status'],'unknown')

    def test_final_capture_is_required_and_old_frames_cannot_substitute(self):
        self.obs['captures'][0]['frame']=self.obs['frames']-1
        self.assertEqual(self.finding()['status'],'unknown')

    def test_shared_required_plan_accepts_generic_image_kind_and_pins_changes(self):
        from patchquest.runtime_contracts import required_finding_plan, assess_observation_findings
        self.exp=expectation_manifest([self.exp]);finding=self.finding()
        self.assertEqual(set(required_finding_plan(self.obs,self.exp)),{finding['finding_id']})
        self.assertEqual(assess_observation_findings(self.obs,self.obs['binding'],[finding],expectations=self.exp)['status'],'passed')
        before=expectation_digest(self.exp)
        next(iter(self.exp['cases'].values()))['checks'][0]['expected_match']=False
        self.assertNotEqual(before,expectation_digest(self.exp))

    def test_independent_actual_basis_does_not_claim_native_glyph_telemetry(self):
        self.obs.update(provenance='actual_emulator',method='automated_runtime')
        self.caps['provenance']='actual_emulator'
        self.obs['captures'][0]['evidence']['provenance']['method']='automated_runtime'
        self.exp['basis']['method']='independent_inspection'
        before=copy.deepcopy((self.obs,self.caps,self.exp));self.assertEqual(self.finding()['status'],'passed')
        # run_checks pins only the binding; detector itself changes no inputs.
        before[0]['binding']['expectation_sha256']=self.obs['binding']['expectation_sha256']
        self.assertEqual((self.obs,self.caps,self.exp),before)

    def test_missing_capture_capability_is_unsupported(self):
        self.caps['capabilities']['capture_frames']=False;self.obs['captures']=[]
        self.obs.update(execution='unsupported',assertion='unsupported',frames=0,reason='Invented unsupported adapter')
        self.assertEqual(self.finding()['status'],'unsupported')

    def test_image_pass_cannot_complete_a_plan_with_unsupported_native_checks(self):
        from patchquest.runtime_contracts import assess_observation_findings
        self.exp['checks'] += [
            dict(id='native-bounds',kind='bounds',rect=[0,0,24,16],padding=0,tolerance=0),
            dict(id='native-resources',kind='resources',limits={'tiles':8}),
            dict(id='native-scroll',kind='controls',expected={'scrolled':True})]
        findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],
                         ['passed','unsupported','unsupported','unsupported'])
        assessment=assess_observation_findings(self.obs,self.obs['binding'],findings,expectations=self.exp)
        self.assertNotEqual(assessment['status'],'passed')
        self.assertEqual(self.obs['assertion'],'not_assessed')
        self.assertEqual(self.obs['controls'],{})

    def test_delivered_input_does_not_observe_wait_or_termination(self):
        from patchquest.runtime_contracts import assess_observation_findings
        self.caps['capabilities']['input']=True
        self.exp['checks'] += [
            dict(id='native-wait',kind='controls',expected={'input_wait':True}),
            dict(id='native-termination',kind='controls',expected={'terminated':True})]
        findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],['passed','unknown','unknown'])
        self.assertTrue(all('Unobserved controls' in f['reason'] for f in findings[1:]))
        assessment=assess_observation_findings(self.obs,self.obs['binding'],findings,expectations=self.exp)
        self.assertNotEqual(assessment['status'],'passed')
        self.assertEqual(self.obs['controls'],{})

    def test_many_image_checks_have_a_shared_comparison_budget(self):
        pixels=bytes([4,8,12])*(1024*1024)
        self.replace_bytes(Frame(1024,1024,pixels).png())
        check=dict(self.exp['checks'][0],rect=[0,0,1024,1024],rgb_sha256=hashlib.sha256(pixels).hexdigest())
        self.exp['checks']=[dict(check,id='image-'+str(i)) for i in range(5)]
        findings=self.run_checks();self.assertTrue(all(f['status']=='passed' for f in findings[:4]))
        self.assertEqual(findings[4]['status'],'unknown');self.assertIn('budget',findings[4]['reason'])


class CaptureSelectionTests(unittest.TestCase):
    """Independently invented pages; no game input or native execution evidence."""
    run_checks = DetectorTests.run_checks

    def setUp(self):
        ImageRegionTests.setUp(self)
        self.exp['schema_version']=2
        self.obs['binding']['detectors']['image_region']='2'
        self.colors={2:bytes([16,32,48]),7:bytes([96,80,64]),12:bytes([7,8,9])}
        self.blobs={};self.obs['captures']=[]
        for frame,color in self.colors.items():self.capture(frame,color)
        self.exp['checks']=[self.check('required',7,self.colors[7])]

    def capture(self,frame,color,identity=None):
        raw=Frame(24,16,color*24*16).png();identity=identity or 'invented-page-'+str(frame)
        ref=reference(raw,evidence_id=identity,media_type='image/png',provenance=self.ref['provenance'])
        ref['integrity']='verified';self.blobs[identity]=raw
        self.obs['captures'].append(dict(frame=frame,evidence=ref))

    def check(self,identity,frame,color):
        return dict(id=identity,kind='image_region',capture={'frame':frame},rect=[3,2,4,5],
            rgb_sha256=hashlib.sha256(color*4*5).hexdigest(),expected_match=True)

    def resolver(self,ref):return dict(available=True,data=self.blobs[ref['evidence_id']])

    def test_earlier_exact_capture_preserves_original_identity_and_needs_no_final(self):
        self.obs['captures']=self.obs['captures'][:2]
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        before=copy.deepcopy((self.obs,self.case,self.exp,self.caps))
        finding=detect(self.case,self.obs,self.caps,self.exp,self.resolver)[0]
        self.assertEqual(finding['status'],'passed');self.assertEqual(finding['detector_version'],'2')
        self.assertEqual(finding['evidence_ids'],['invented-page-7'])
        self.assertEqual(finding['observation_id'],self.obs['observation_id'])
        self.assertEqual(finding['binding'],self.obs['binding'])
        self.assertEqual((self.obs,self.case,self.exp,self.caps),before)

    def test_positive_and_omitted_input_same_target_keep_diagnostic_separate(self):
        from patchquest.runtime_contracts import assess_observation_findings
        for omitted in (False,True):
            with self.subTest(omitted=omitted):
                self.setUp()
                self.case['variant_id']='invented-omitted-input' if omitted else 'invented-positive'
                self.obs['case_sha256']=self.exp['case_sha256']=contract_digest('CaseSpec',self.case)
                if omitted:
                    self.obs['captures']=[c for c in self.obs['captures'] if c['frame']!=7]
                    self.capture(7,self.colors[2])
                diagnostic=self.check('held-first-diagnostic',7,self.colors[2]);diagnostic['expected_match']=omitted
                self.exp['checks'].append(diagnostic)
                findings=self.run_checks()
                self.assertEqual([f['status'] for f in findings],['failed' if omitted else 'passed','passed'])
                assessment=assess_observation_findings(self.obs,self.obs['binding'],findings,expectations=self.exp)
                self.assertEqual(assessment['status'],'failed' if omitted else 'passed')
                self.assertEqual(self.obs['controls'],{});self.assertEqual(self.obs['assertion'],'not_assessed')

    def test_missing_out_of_range_and_ambiguous_selection_never_borrow_final(self):
        for mode in ('missing','beyond','duplicate-same','duplicate-different'):
            with self.subTest(mode=mode):
                self.setUp()
                if mode=='missing':self.obs['captures']=[c for c in self.obs['captures'] if c['frame']!=7]
                elif mode=='beyond':self.exp['checks'][0]['capture']['frame']=13
                else:self.capture(7,self.colors[7] if mode=='duplicate-same' else self.colors[2],'duplicate-page')
                self.exp['checks'][0]['expected_match']=False
                finding=self.run_checks()[0]
                self.assertEqual(finding['status'],'unknown');self.assertEqual(finding['evidence_ids'],[])

    def test_frame_zero_is_valid_and_unrelated_checks_still_need_final(self):
        self.exp['checks'][0]['capture']['frame']=0
        self.assertEqual(self.run_checks()[0]['status'],'unknown')
        self.exp['checks'][0]=self.check('required',2,self.colors[2])
        self.obs['captures']=[c for c in self.obs['captures'] if c['frame']!=12]
        self.caps['capabilities']['observe_resources']=True;self.obs['resources']={'tiles':2}
        self.exp['checks'].append(dict(id='resources',kind='resources',limits={'tiles':8}))
        findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],['passed','unknown'])
        self.assertEqual(findings[0]['evidence_ids'],['invented-page-2'])
        self.assertEqual(findings[1]['detector_version'],'1')

    def test_changed_selected_or_unselected_bytes_fail_closed(self):
        for identity in ('invented-page-7','invented-page-12'):
            with self.subTest(identity=identity):
                self.setUp();self.blobs[identity]=b'changed'
                self.exp['checks'][0]['expected_match']=False
                finding=self.run_checks()[0]
                self.assertEqual(finding['status'],'unknown')
                self.assertEqual(finding['evidence_ids'],['invented-page-7'])

    def test_selected_non_png_and_malformed_png_cannot_pass_nonmatch(self):
        self.exp['checks'][0]['expected_match']=False
        self.obs['captures'][1]['evidence']['media_type']='application/octet-stream'
        self.assertEqual(self.run_checks()[0]['status'],'unknown')
        self.setUp();raw=b'not a PNG';ref=self.obs['captures'][1]['evidence']
        ref.update(sha256=hashlib.sha256(raw).hexdigest(),byte_length=len(raw));self.blobs[ref['evidence_id']]=raw
        self.exp['checks'][0]['expected_match']=False
        self.assertEqual(self.run_checks()[0]['status'],'unknown')

    def test_selector_shape_is_strict_and_versioned(self):
        for capture in (None,{}, {'frame':True},{'frame':-1},{'frame':1.5},{'frame':2**63},{'frame':7,'extra':0}):
            with self.subTest(capture=capture):
                plan=copy.deepcopy(self.exp);plan['checks'][0]['capture']=capture
                with self.assertRaises(DetectorError):expectation_data(plan)
        plan=copy.deepcopy(self.exp);plan['checks'][0].pop('capture')
        with self.assertRaises(DetectorError):expectation_data(plan)
        plan=copy.deepcopy(self.exp);plan['schema_version']=1
        with self.assertRaises(DetectorError):expectation_data(plan)

    def test_capture_and_version_changes_require_original_binding_pins(self):
        self.obs['binding']['expectation_sha256']=expectation_digest(self.exp)
        self.exp['checks'][0]['capture']['frame']=2
        with self.assertRaisesRegex(DetectorError,'digest differs'):
            detect(self.case,self.obs,self.caps,self.exp,self.resolver)
        self.obs['binding']['detectors']['image_region']='1'
        with self.assertRaisesRegex(DetectorError,'version absent or incompatible'):self.run_checks()

    def test_image_exception_cannot_move_between_identical_capture_pixels(self):
        self.obs['captures']=[c for c in self.obs['captures'] if c['frame']!=2]
        self.capture(2,self.colors[7])
        self.exp['checks'][0]['rgb_sha256']=hashlib.sha256(bytes([200,1,2])*4*5).hexdigest()
        finding=self.run_checks()[0]
        defect=finding['extensions']['patchquest:detector']['defects'][0]
        self.assertEqual(defect['capture_frame'],7)
        self.exp['exceptions']=[dict(check_id='required',defect_sha256=defect_digest(defect),
            content_binding_sha256=exception_binding(self.obs['binding'],self.obs['case_sha256']),
            reason='Independent invented exception for frame seven only.')]
        self.assertEqual(self.run_checks()[0]['status'],'passed')
        self.exp['checks'][0]['capture']['frame']=2
        self.assertEqual(self.run_checks()[0]['status'],'failed')

    def test_actual_basis_and_synthetic_provenance_remain_distinct(self):
        finding=self.run_checks()[0];self.assertTrue(finding['extensions']['patchquest:detector']['synthetic'])
        self.obs.update(provenance='actual_emulator',method='automated_runtime');self.caps['provenance']='actual_emulator'
        for c in self.obs['captures']:c['evidence']['provenance']['method']='automated_runtime'
        self.assertEqual(self.run_checks()[0]['status'],'unknown')
        self.exp['basis']['method']='independent_inspection'
        finding=self.run_checks()[0];self.assertEqual(finding['status'],'passed')
        self.assertFalse(finding['extensions']['patchquest:detector']['synthetic'])

    def test_mixed_manifest_keeps_v1_envelope_and_selected_plan_versions(self):
        legacy=copy.deepcopy(self.exp);legacy['schema_version']=1;legacy['case_sha256']='b'*64
        legacy['checks'][0].pop('capture')
        self.exp=expectation_manifest([legacy,self.exp])
        self.assertEqual(self.exp['schema_version'],1);self.assertEqual(self.run_checks()[0]['status'],'passed')

    def test_decode_budget_is_shared_and_identical_bytes_can_reuse_decode(self):
        self.exp['checks']=[self.check('page-'+str(f),f,c) for f,c in self.colors.items()]
        with mock.patch('patchquest.runtime_detectors._IMAGE_DECODE_PIXELS',2*24*16):
            findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],['passed','passed','unknown'])
        self.assertIn('decode pixel budget',findings[-1]['reason'])
        self.obs['captures']=[]
        for f in self.colors:self.capture(f,self.colors[7])
        self.exp['checks']=[self.check('page-'+str(f),f,self.colors[7]) for f in self.colors]
        with mock.patch('patchquest.runtime_detectors._IMAGE_DECODE_PIXELS',24*16):
            self.assertTrue(all(f['status']=='passed' for f in self.run_checks()))

    def test_region_budget_remains_shared_across_selected_frames(self):
        self.exp['checks']=[self.check('page-'+str(f),f,c) for f,c in self.colors.items()]
        with mock.patch('patchquest.runtime_detectors._IMAGE_CHECK_PIXELS',2*4*5):
            self.assertEqual([f['status'] for f in self.run_checks()],['passed','passed','unknown'])

    def install_budget_pages(self,raws):
        self.obs['captures']=[];self.blobs={};self.exp['checks']=[]
        for frame,raw in enumerate(raws,1):
            identity='invented-budget-page-'+str(frame)
            ref=reference(raw,evidence_id=identity,media_type='image/png',provenance=self.ref['provenance'])
            ref['integrity']='verified';self.blobs[identity]=raw
            self.obs['captures'].append(dict(frame=frame,evidence=ref))
            self.exp['checks'].append(dict(id=identity,kind='image_region',capture={'frame':frame},
                rect=[0,0,1,1],rgb_sha256=hashlib.sha256(bytes([16,32,48])).hexdigest(),expected_match=True))

    @staticmethod
    def late_bad_filter_page(color):
        # Correct size, CRCs and compressed stream; only the final row is invalid.
        scan=b''.join((b'\0' if y<31 else b'\5')+color*32 for y in range(32))
        return ImageRegionTests.png(scan,width=32,height=32)

    def test_failed_decode_attempts_spend_shared_pixel_budget(self):
        bad=[self.late_bad_filter_page(bytes([16+i,32,48])) for i in range(3)]
        good=Frame(32,32,bytes([16,32,48])*32*32).png()
        self.install_budget_pages(bad+[good])
        with mock.patch('patchquest.runtime_detectors._IMAGE_DECODE_PIXELS',32*32):
            findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],['unknown']*4)
        self.assertIn('row filter',findings[0]['reason'])
        self.assertTrue(all('decode pixel budget' in f['reason'] for f in findings[1:]))

    def test_failed_digest_cache_preserves_remaining_exact_budget(self):
        bad=self.late_bad_filter_page(bytes([24,32,48]))
        good=Frame(32,32,bytes([16,32,48])*32*32).png()
        self.install_budget_pages([bad,bad,good])
        with mock.patch('patchquest.runtime_detectors._IMAGE_DECODE_PIXELS',2*32*32):
            findings=self.run_checks()
        self.assertEqual([f['status'] for f in findings],['unknown','unknown','passed'])
        self.assertEqual(findings[0]['reason'],findings[1]['reason'])
        self.assertIn('row filter',findings[1]['reason'])

    def test_legacy_duplicate_same_byte_final_capture_keeps_version_one(self):
        ImageRegionTests.setUp(self)
        duplicate=copy.deepcopy(self.obs['captures'][0]);duplicate['evidence']['evidence_id']='legacy-duplicate'
        self.obs['captures'].append(duplicate)
        findings=DetectorTests.run_checks(self,resolver=lambda ref:dict(available=True,data=self.bytes))
        self.assertEqual(findings[0]['status'],'passed');self.assertEqual(findings[0]['detector_version'],'1')
        self.assertEqual(findings[0]['evidence_ids'],['capture-one','legacy-duplicate'])


if __name__=='__main__':unittest.main()

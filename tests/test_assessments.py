"""Non-graphic, invented editorial assertions; never actual game or provider data."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import tempfile
import unittest

from _bootstrap import ROOT
from test_state import invented, project
from patchquest.state import Store, Conflict, canonical
from patchquest.state_api import execute
from patchquest.assessments import CONTENT, EXCEPTIONS, OUTCOMES, binding, context, migrate, read
from patchquest.jobs import Jobs


class AssessmentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.manifest = project(self.root)
        self.store = Store(self.manifest)
        self.store.put(invented(), 0)

    def issue(self, code='missing_context', kind='exception', key='issue-1', record='line-01', **extra):
        packet = context(self.store, record)
        return {'id': key, 'title': 'Invented assessment', 'record_ids': [record],
                'assessment': {'kind': kind, 'code': code, 'rationale': 'A referenced context observation needs evaluation.',
                    'references': ['synthetic-notes:observation-1'], 'bindings': packet['records'],
                    'narrative_sha256': packet['narrative_sha256'], **extra}}

    def test_all_content_labels_are_independent_of_progress_and_permission(self):
        before = self.store.snapshot()['sha256']
        for code in CONTENT:
            self.store.put_issue(self.issue(code, 'content', code), 0)
        self.assertEqual(len(read(self.store)), len(CONTENT))
        self.assertEqual(self.store.snapshot()['sha256'], before)
        self.assertEqual(self.store.status(self.store.get('line-01')), 'translated')
        self.assertEqual(self.store.overview()['open_issues'], 0)
        self.assertTrue(all('provider_outcome' not in r['assessment'] for r in read(self.store)))
        with self.assertRaises(ValueError):
            self.store.put_issue(self.issue('explicit_sexual', 'content', severity='high'), 0)
        with self.assertRaises(ValueError):
            self.store.put_issue(self.issue('explicit_sexual', 'content', build_impact='blocks_build'), 0)

    def test_context_not_keywords_and_age_consent_require_evidence(self):
        # The platform stores evidence-backed decisions; it deliberately does not
        # infer sexual content, ages or consent from a word or portrait.
        self.store.put(dict(invented(), source='An educational anatomy discussion.'), 1)
        self.assertEqual(read(self.store), [])
        for field, value in [('age','adult'), ('consent','consensual')]:
            with self.assertRaises(ValueError):
                self.store.put_issue(self.issue('clinical_educational', 'content', **{field:{'value':value,'references':[]}}), 0)
        self.store.put_issue(self.issue('clinical_educational','content'),0)
        self.assertEqual(read(self.store)[0]['assessment']['age']['value'], 'unknown')
        self.assertEqual(self.store.list(content='explicit_sexual')['total'], 0)

    def test_overlapping_exceptions_and_independent_content_filters(self):
        self.store.put_issue(self.issue(severity='medium'),0)
        self.store.put_issue(self.issue('runtime_verification',key='runtime'),0)
        self.store.put_issue(self.issue('romance','content','label'),0)
        self.assertEqual(self.store.list(exception='missing_context',content='romance',severity='medium')['total'],1)
        self.assertEqual(len(self.store.list()['items'][0]['assessments']),3)
        self.assertEqual(self.store.list(content='nudity')['total'],0)
        with self.assertRaises(ValueError): self.store.list(exception='invented-reason')

    def test_revision_and_context_staleness(self):
        self.store.put_issue(self.issue(),0)
        self.store.put(dict(invented(),context={'new':'scene evidence'}),1)
        self.assertTrue(read(self.store)[0]['stale'])
        self.assertEqual(self.store.list(stale='stale')['total'],1)
        with self.assertRaises(Conflict): self.store.put_issue(self.issue(key='old')|{'assessment':read(self.store)[0]['assessment']},0)
        issue=self.store.issues()[0]
        issue.pop('revision'); issue['status']='investigating'
        self.store.put_issue(issue,1)  # Status update does not falsely refresh evidence.
        self.assertTrue(read(self.store)[0]['stale'])
        issue['assessment']['rationale']='New claim about an unseen changed source'
        with self.assertRaises(Conflict):self.store.put_issue(issue,2)
        fresh=self.issue();self.store.put_issue(fresh,2)
        self.assertFalse(read(self.store)[0]['stale'])

    def test_narrative_guide_pointer_changes_seen_by_long_lived_store(self):
        self.store.put_issue(self.issue(),0)
        (self.root/'context.json').write_text('{"new":"evidence"}')
        manifest=json.loads(self.manifest.read_text());manifest['resources']['narrative_context']='context.json'
        self.manifest.write_text(json.dumps(manifest))
        self.assertIn('narrative_context',read(self.store)[0]['stale_reasons'])
        self.store.put_issue(self.issue(),1)
        self.assertFalse(read(self.store)[0]['stale'])
        (self.root/'context.json').write_text('{"new":"different evidence"}')
        self.assertTrue(read(self.store)[0]['stale'])

    def test_protected_corrections_and_resolution_history(self):
        self.store.put(invented(target='Keep this exact wording.'),1,'human')
        original=self.store.snapshot()['sha256']
        self.store.put_issue(self.issue('fidelity_mismatch',alternatives=['A non-binding editorial suggestion.']),0)
        p=self.store.issues()[0];p.pop('revision');p['status']='needs_input'
        self.store.put_issue(p,1)
        p['status']='resolved';p['assessment']['resolution']='Context supports retaining the correction.'
        self.store.put_issue(p,2)
        self.assertEqual(len(self.store.issue_history('issue-1')),3)
        self.assertEqual(self.store.snapshot()['sha256'],original)
        self.assertEqual(self.store.get('line-01')['revision'],2)
        self.assertTrue(self.store.get('line-01')['human_corrected'])
        self.assertEqual(self.store.overview()['open_issues'],0)

    def test_provider_outcomes_never_publish_refusal_or_success_text(self):
        self.store.put(invented('new',''),0)
        before=self.store.snapshot()['sha256']
        for outcome in OUTCOMES:
            result=execute(self.store,'provider-result',{'key':'new','expected':0,'outcome':outcome,
                'rationale':'Synthetic provider outcome observed without source excerpts.',
                'references':['synthetic-response:'+outcome], 'inputs':context(self.store,'new'),
                'provenance':{'provider':'invented-provider','request_id':outcome},'issue_id':outcome})
            self.assertEqual(result['assessment']['code']=='provider_restriction',outcome=='explicit_refusal')
            self.assertEqual(result['assessment']['provider_outcome'],outcome)
        self.assertEqual(self.store.get('new')['target'],'')
        self.assertEqual(self.store.snapshot()['sha256'],before)
        with self.assertRaises(ValueError):self.store.put_issue(self.issue('provider_restriction'),0)
        with self.assertRaises(ValueError):self.store.put_issue(self.issue('provider_restriction',provider_outcome='timeout'),0)

    def test_provider_input_binding_and_payload_rejection(self):
        inputs=context(self.store,'line-01')
        self.store.put(invented(target='Changed'),1,'human')
        p={'key':'line-01','expected':0,'outcome':'explicit_refusal','rationale':'Observed refusal.',
           'references':['response:1'],'inputs':inputs,'provenance':{'provider':'synthetic'}}
        with self.assertRaises(Conflict):execute(self.store,'provider-result',p)
        with self.assertRaises(TypeError):execute(self.store,'provider-result',dict(p,target='Refusal text'))

    def test_migration_idempotence_and_lossless_snapshots(self):
        self.store.put(dict(invented(),uncertainty='Original note without a known reason.'),1,'human')
        before=self.store.snapshot()['sha256']; history=self.store.history('line-01')
        self.assertEqual(migrate(self.store)['created'],1)
        self.assertEqual(migrate(self.store)['existing'],1)
        issue=read(self.store)[0]
        self.assertEqual(issue['assessment']['code'],'legacy_unspecified')
        self.assertEqual(issue['assessment']['severity'],'info')
        self.assertEqual(issue['description'],'Original note without a known reason.')
        self.assertEqual(self.store.snapshot()['sha256'],before)
        self.assertEqual(self.store.history('line-01'),history)

    def test_competing_issue_writers_cannot_lose_history(self):
        self.store.put_issue(self.issue(),0)
        def save(n):
            try:self.store.put_issue(self.issue(rationale=f'Observation {n}'),1);return 'saved'
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(save,range(4)))
        self.assertEqual(results.count('saved'),1)
        self.assertEqual(len(self.store.issue_history('issue-1')),2)

    def test_build_gate_only_explicit_blockers_and_stale_blockers(self):
        jobs=Jobs(self.store);jobs.register('test','Invented worker')
        self.store.put_issue(self.issue('explicit_sexual','content','flag'),0)
        self.store.put_issue(self.issue('technical_limitation',key='blocker',build_impact='blocks_build'),0)
        self.store.put(invented(target='Changed'),1)
        with self.assertRaises(Conflict):jobs.submit('blocked-test')
        issue=self.store.issues()[0];self.assertEqual(issue['id'],'blocker');issue.pop('revision')
        issue['status']='resolved';issue['assessment']['resolution']='Underlying limitation independently corrected.'
        self.store.put_issue(issue,1)
        self.assertEqual(jobs.submit('allowed-test')['status'],'queued')

    def test_general_activity_contains_no_assessment_excerpts(self):
        self.store.put_issue(self.issue(rationale='PRIVATE ASSESSMENT SENTINEL'),0)
        self.assertNotIn('PRIVATE ASSESSMENT SENTINEL',canonical(self.store.events()))
        self.assertNotIn('PRIVATE ASSESSMENT SENTINEL',canonical(self.store.overview()))
        self.assertNotIn('PRIVATE ASSESSMENT SENTINEL',canonical(self.store.list()))

    def test_missing_context_file_marks_stale_without_breaking_browsing(self):
        self.store.put_issue(self.issue(),0)
        manifest=json.loads(self.manifest.read_text());manifest['resources']['narrative_context']='missing.json'
        self.manifest.write_text(json.dumps(manifest))
        self.assertTrue(read(self.store)[0]['stale'])
        self.assertEqual(self.store.list(stale='stale')['total'],1)
        with self.assertRaises(OSError): context(self.store,'line-01')

    def test_progress_does_not_become_uncertain_from_legacy_note(self):
        self.store.put(dict(invented(),uncertainty='Unspecified concern'),1)
        self.assertEqual(self.store.status(self.store.get('line-01')),'translated')
        self.assertEqual(self.store.list(status='translated')['total'],1)
        self.assertEqual(self.store.list(status='uncertain')['total'],1)


if __name__ == '__main__': unittest.main()

"""Invented coverage and provenance fixtures; no real emulator or game claims."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, invented
from test_runtime import Fake
from patchquest import verification as v
from patchquest.runtime import run, register, sha
from patchquest.state import Store, Conflict, canonical
from patchquest.state_api import execute
from patchquest.progress import ProgressReporter
from patchquest.studio import StudioServer
from patchquest.studio_projects import ProjectDirectory


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(project(self.root))
        self.store.put(invented('greeting'), 0, role='human')
        self.snapshot = self.store.snapshot()['sha256']
        self.rom = self.store.context.output.write_new('invented.fixture', b'invented build bytes')
        self.store.build(dict(id='build-one', snapshot=self.snapshot, status='validated',
                              artifacts={'rom': str(self.rom)}, approval={'approved': True,
                              'reference': 'Invented checkpoint acceptance, not release permission'}), 0)
        self.area = dict(id='greeting-check', label='PRIVATE LABEL SENTINEL',
                         expectation='Check the invented greeting against its source.',
                         stage='language_review', method='manual_review', record_ids=['greeting'])

    def plan(self, areas=None, expected=0, **changes):
        data = dict(build_id='build-one', next_milestone='PRIVATE MILESTONE SENTINEL',
                    areas=areas if areas is not None else [self.area])
        data.update(changes)
        return execute(self.store, 'verification-plan-put', dict(data=data, expected=expected))

    def observe(self, **changes):
        params = dict(area_id=self.area['id'], build_id='build-one', status='passed',
                      reference='PRIVATE REFERENCE SENTINEL', expected=0, plan_revision=1)
        params.update(changes)
        return execute(self.store, 'verification-observe', params)

    def state(self):
        return execute(self.store, 'verification-report')['areas'][0]['status']

    def synthetic_run(self, destination='run', passed=True, registered_kind='synthetic'):
        scenario = dict(schema=1, id='invented-menu', snapshot=self.snapshot,
                        rom_sha256=sha(self.rom.read_bytes()), records={'greeting': 1},
                        timeout_seconds=2, steps=[dict(frames=1, capture='blue', assertions=[
                        dict(label='Known blue initial state', kind='color_count', rect=[0,0,4,2],
                             color=[0,0,255] if passed else [255,0,0], minimum=8)])])
        result = run(self.store, 'build-one', scenario, Fake(), destination)
        # The parser must handle real-run provenance. This controlled fixture
        # changes only a synthetic test report; it is never emulator evidence.
        if registered_kind != 'synthetic':
            result['emulator']['kind'] = registered_kind
            result['level'] = 'automated_runtime'
            result['configuration_sha256'] = sha(canonical(result['emulator']).encode())
            (self.rom.parent / destination / 'runtime.json').write_text(canonical(result), encoding='utf8')
        registered = register(self.store, destination)
        return dict(id='navigation', label='Invented menu movement', stage='gameplay',
                    method='automated_runtime', expectation='The independently specified blue area is visible.',
                    record_ids=['greeting'], scenario_sha256=registered['scenario_sha256'],
                    configuration_sha256=registered['configuration_sha256'],
                    assertions=['Known blue initial state'])

    def test_no_plan_or_catalog_never_means_verified(self):
        summary = execute(self.store, 'readiness')
        self.assertEqual(summary['translation']['status'], 'catalogue_translated')
        self.assertFalse(summary['build_selected'])
        self.assertFalse(summary['release_approved'])
        self.assertEqual({s['status'] for s in summary['stages']}, {'not_assessed'})
        self.assertFalse((self.root / v.REPORT_PATH).exists())
        other = self.root / 'empty'; other.mkdir()
        empty = v.summary(Store(project(other)))
        self.assertEqual(empty['translation']['status'], 'not_assessed')
        self.assertIsNone(empty['translation']['percent_translated'])

    def test_explicit_plan_includes_untested_scope(self):
        self.plan([self.area, dict(self.area, id='second-check')])
        self.observe()
        summary = v.summary(self.store)
        stage = summary['stages'][0]
        self.assertEqual(stage['status'], 'in_progress')
        self.assertEqual(stage['counts']['passed'], 1)
        self.assertEqual(stage['counts']['untested'], 1)
        self.assertEqual(stage['planned'], 2)
        self.assertIsNotNone(stage['last_assessed_at'])

    def test_assessments_preserve_corrections_builds_and_snapshots(self):
        before = (self.store.get('greeting'), self.store.builds(), self.store.snapshot()['sha256'])
        self.plan()
        self.observe(status='failed')
        self.assertEqual(self.state(), 'failed')
        self.observe(expected=1)
        self.assertEqual(self.state(), 'passed')
        summary = execute(self.store, 'readiness-report')
        self.assertEqual(summary['stages'][0]['status'], 'verified_for_scope')
        self.assertFalse(summary['release_approved'])
        self.assertEqual(before, (self.store.get('greeting'), self.store.builds(), self.store.snapshot()['sha256']))
        self.assertTrue(self.store.get('greeting')['human_corrected'])
        history = execute(self.store, 'verification-history')
        self.assertEqual([x['data']['status'] for x in history if x['kind'] == 'verification-observation'], ['failed','passed'])
        self.assertEqual(len(v.history(self.store, after=history[0]['seq'])), 2)

    def test_same_revision_competing_writers_one_wins(self):
        self.plan()
        def write():
            try:
                return v.observe(Store(self.store.manifest_path), self.area['id'], 'build-one',
                                 'passed', 'Invented reference', 0, 1)['revision']
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: write(), range(2)))
        self.assertCountEqual(results, [1, 'conflict'])
        with self.assertRaises(Conflict): self.plan(expected=0)
        with self.assertRaises(Conflict): self.observe(expected=1, plan_revision=0)

    def test_changed_definition_rechecks_but_unrelated_plan_edits_do_not(self):
        self.plan()
        self.observe()
        self.plan(expected=1, next_milestone='Another private milestone')
        self.assertEqual(self.state(), 'passed')
        self.plan([dict(self.area, expectation='Expanded expectation')], expected=2)
        self.assertEqual(self.state(), 'stale')
        self.assertEqual(v.summary(self.store)['stages'][0]['status'], 'needs_recheck')

    def test_correction_and_discovered_text_stale_selected_build(self):
        self.plan()
        self.observe()
        self.store.put(invented('other'), 0)
        self.assertEqual(self.state(), 'passed')  # Scoped historical check remains true.
        self.assertFalse(v.report(self.store)['build_current'])
        self.assertEqual(v.summary(self.store)['stages'][0]['status'], 'needs_recheck')
        data = invented('greeting', target='The protected revision changed.')
        self.store.put(data, 1, role='human')
        self.assertEqual(self.state(), 'stale')
        self.assertEqual(self.store.get('greeting')['target'], data['target'])

    def test_unscoped_manual_check_binds_entire_snapshot(self):
        self.plan([dict(self.area, record_ids=[])])
        self.observe()
        self.store.put(invented('new'), 0)
        self.assertEqual(self.state(), 'stale')

    def test_build_bytes_and_snapshot_bindings(self):
        self.plan()
        self.observe()
        build = self.store.builds()[0]
        expected = build.pop('revision'); build['summary'] = 'Annotation only'
        self.store.build(build, expected)
        self.assertEqual(self.state(), 'passed')
        self.rom.write_bytes(b'changed synthetic artifact')
        self.assertEqual(self.state(), 'stale')
        self.rom.unlink()
        self.assertEqual(v.report(self.store)['problem'], 'build_or_artifacts_unavailable')
        self.assertFalse(v.summary(self.store)['build_available'])

    def test_failed_build_cannot_be_promoted(self):
        self.plan()
        build = self.store.builds()[0]; expected = build.pop('revision')
        build['status'] = 'failed'; self.store.build(build, expected)
        with self.assertRaises(ValueError): self.observe()
        self.observe(status='failed')
        self.assertEqual(v.summary(self.store)['stages'][0]['status'], 'needs_attention')

    def test_missing_area_record_and_cross_build_assessment_rejected(self):
        self.store.put(invented('new'), 0)
        self.plan([dict(self.area, record_ids=['new'])])
        with self.assertRaises(ValueError): self.observe()
        self.plan(expected=1)
        with self.assertRaises(KeyError): self.observe(build_id='absent', plan_revision=2)
        with self.assertRaises(KeyError): self.observe(area_id='absent', plan_revision=2)
        with self.assertRaises(ValueError): self.observe(reference=' ', plan_revision=2)

    def test_synthetic_runtime_never_passes_even_with_checkpoint_approval(self):
        self.plan([self.synthetic_run()])
        area = v.report(self.store)['areas'][0]
        self.assertEqual(area['status'], 'untested')
        self.assertEqual(area['evidence'][0]['reason'], 'synthetic_evidence')
        with self.assertRaises(ValueError):
            self.observe(area_id='navigation')

    def test_controlled_real_provenance_fixture_is_exactly_scoped(self):
        area = self.synthetic_run(registered_kind='actual_emulator')
        self.plan([area])
        self.assertEqual(self.state(), 'passed')
        self.plan([dict(area, configuration_sha256='0' * 64)], expected=1)
        self.assertEqual(self.state(), 'untested')
        self.plan([dict(area, assertions=['Unperformed assertion'])], expected=2)
        self.assertEqual(self.state(), 'stale')
        self.plan([area], expected=3)
        self.store.put(invented('greeting', target='Changed'), 1, role='human')
        self.assertEqual(self.state(), 'stale')

    def test_runtime_report_and_capture_tampering_do_not_pass(self):
        area = self.synthetic_run(registered_kind='actual_emulator')
        self.plan([area])
        capture = self.rom.parent / 'run/blue.png'
        original = capture.read_bytes(); capture.write_bytes(b'invalid')
        self.assertEqual(self.state(), 'stale')
        capture.write_bytes(original)
        report = self.rom.parent / 'run/runtime.json'; report.write_text('{}')
        self.assertEqual(self.state(), 'stale')

    def test_failed_runtime_is_retained_and_later_exact_rerun_resolves_it(self):
        area = self.synthetic_run(registered_kind='actual_emulator')
        self.plan([area])
        # Produce a controlled failed report of the SAME scenario, preserving
        # provenance checks; no actual emulator execution is represented here.
        source = self.rom.parent / 'run'
        for name, status, finished in [('failed','failed','2030-01-01T00:00:00+00:00'),
                                       ('retry','passed','2030-01-02T00:00:00+00:00')]:
            target = self.rom.parent / name; target.mkdir()
            for file in source.iterdir():
                if file.is_file(): (target / file.name).write_bytes(file.read_bytes())
            data = json.loads((target/'runtime.json').read_text())
            data.update(status=status, finished=finished)
            if status == 'failed': data['assertions'][0]['passed'] = False
            (target/'runtime.json').write_text(canonical(data), encoding='utf8')
            register(self.store, name)
            self.assertEqual(self.state(), status)
        self.assertEqual(len(v.report(self.store)['areas'][0]['evidence']), 3)

    def test_invalid_plan_fields_and_no_automated_language_certification(self):
        for change in (dict(stage='everything'), dict(method='pretend'), dict(label=''),
                       dict(record_ids=['missing']), dict(record_ids=['greeting','greeting'])):
            with self.subTest(change=change), self.assertRaises((ValueError, KeyError)):
                self.plan([dict(self.area, **change)])
        area = self.synthetic_run()
        with self.assertRaises(ValueError): self.plan([dict(area, stage='language_review')])
        with self.assertRaises(ValueError): self.plan([self.area, self.area])
        with self.assertRaises(TypeError): execute(self.store, 'readiness-report', {'path':'elsewhere'})

    def test_method_limits_and_summary_visibility(self):
        for stage, method in [('gameplay','static'), ('gameplay','manual_review'),
                              ('language_review','static'), ('language_review','hardware')]:
            with self.subTest(stage=stage,method=method), self.assertRaises(ValueError):
                self.plan([dict(self.area,stage=stage,method=method)])
        self.plan([dict(self.area,stage='graphics_layout',method='static')])
        self.observe()
        stage = next(s for s in v.summary(self.store)['stages'] if s['id']=='graphics_layout')
        self.assertEqual(stage['methods'], {'static': {'planned':1, 'passed':1}})

    def test_corrupt_later_evidence_cannot_fall_back_to_an_earlier_pass(self):
        area = self.synthetic_run(registered_kind='actual_emulator')
        self.plan([area])
        self.synthetic_run('later', registered_kind='actual_emulator')
        (self.rom.parent/'later/runtime.json').write_text('{}')
        self.assertEqual(self.state(), 'stale')

    def test_summary_allowlist_excludes_private_free_text_and_identity(self):
        self.plan()
        self.observe(actor='PRIVATE ACTOR SENTINEL')
        result = execute(self.store, 'readiness-report')
        raw = (self.root/v.REPORT_PATH).read_text()
        for secret in ('SENTINEL', 'build-one', 'greeting', self.snapshot, str(self.root), 'source_sha256'):
            self.assertNotIn(secret, raw)
        self.assertEqual(json.loads(raw), result)
        self.assertEqual(set(result), {'schema_version','report_type','updated_at','plan_updated_at',
                         'plan_revision','build_selected','build_available','build_current','basis',
                         'translation','stages','release_approved'})

    def test_cache_atomic_failure_preserves_previous_and_no_unrelated_overwrite(self):
        v.write_summary(self.store)
        dest = self.root / v.REPORT_PATH; previous = dest.read_bytes()
        self.plan()
        with patch('patchquest.progress.os.replace', side_effect=PermissionError('private diagnostic')):
            with self.assertRaises(PermissionError): v.write_summary(self.store)
        self.assertEqual(dest.read_bytes(), previous)
        self.assertEqual(list(dest.parent.glob('.readiness-summary-*.tmp')), [])
        dest.write_text('{}')
        with self.assertRaises(ValueError): v.write_summary(self.store)
        self.assertEqual(dest.read_text(), '{}')

    def test_cache_refuses_links(self):
        v.write_summary(self.store)
        dest = self.root / v.REPORT_PATH
        linked = self.root / 'preserved.fixture'; os.link(dest, linked)
        prior = linked.read_bytes()
        with self.assertRaises(ValueError): v.write_summary(self.store)
        self.assertEqual(linked.read_bytes(), prior)

    def test_periodic_readiness_failure_does_not_prevent_translation_progress(self):
        reporter = ProgressReporter(ProjectDirectory(self.store))
        with patch('patchquest.verification.write_summary', side_effect=OSError('PRIVATE SENTINEL')):
            with self.assertLogs('patchquest.progress', level='WARNING') as logs:
                reporter.refresh(); reporter.refresh()
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn('SENTINEL', str(logs.output))
        self.assertTrue((self.root/'.patchquest/translation-progress.json').exists())
        reporter.refresh()
        self.assertFalse(reporter.readiness_failures)
        self.assertTrue((self.root/v.REPORT_PATH).exists())

    def test_cli_and_authenticated_http_read_path(self):
        self.plan()
        result = subprocess.run([sys.executable, '-B', str(ROOT/'tools/patchquest.py'), 'state',
                    str(self.store.manifest_path), 'readiness-report'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['report_type'], 'readiness-summary')
        server = StudioServer(self.store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            for path, headers, expected in [('/api/verification-report', {}, 401),
                    ('/api/verification-report?build_id=build-one', {'X-Studio-Token':server.token}, 200),
                    ('/api/readiness', {'X-Studio-Token':server.token}, 200),
                    ('/api/readiness', {'X-Studio-Token':server.token,'Origin':'https://example.invalid'}, 403),
                    ('/api/readiness-report', {'X-Studio-Token':server.token}, 404)]:
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    client.request('GET', path, headers=headers)
                    response = client.getresponse(); self.assertEqual(response.status, expected); response.read()
                finally: client.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()

"""Independently invented arrival routes and spawned adapters; no emulator data."""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.runtime import Frame
from patchquest.runtime_artifacts import RuntimeArtifacts, reference
from patchquest.runtime_contracts import ContractError, validate
from patchquest.runtime_scenes import SceneLibrary, prepare_scene
from patchquest import runtime_sweep as sweep


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(',', ':')).encode())


def pixels(frame):
    return bytes((frame, 11, 23)) * 2


class ArrivalAdapter:
    def __init__(self, configuration):
        self.config = configuration
        self.resets = 0
        self.frames = 0
        self.sandbox = None

    def reset(self, inputs, configuration, sandbox):
        self.inputs = inputs
        self.sandbox = sandbox
        self.frames = 0
        self.resets += 1

    def describe(self):
        return dict(kind='synthetic', version='1', sha256=self.config['binary_sha256'])

    def capabilities(self):
        return self.config['caps']

    def configuration(self):
        return self.config

    def loaded_artifacts(self):
        return {role: sha(raw) for role, raw in self.inputs.items()}

    def step(self, buttons):
        self.frames += 1
        with (self.sandbox/'steps.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(dict(frame=self.frames, buttons=buttons))+'\n')
        if self.frames == self.config.get('pause_frame'):
            (self.sandbox/'pause.flag').write_text('paused', encoding='utf-8')
            time.sleep(2)
        failed = self.config.get('first_attempt_fails') and self.resets == 2
        return Frame(2, 1, pixels(99 if failed else self.frames))

    def observe(self, case, frame):
        (self.sandbox/'observe.json').write_text(json.dumps(dict(frame=frame)), encoding='utf-8')
        return {}

    def restore(self, raw):
        (self.sandbox/'restore.txt').write_text(sha(raw), encoding='utf-8')

    def load_save_ram(self, raw):
        (self.sandbox/'save.txt').write_text(sha(raw), encoding='utf-8')

    def debug_setup(self, tracked):
        (self.sandbox/'debug.txt').write_text('volatile synthetic setup', encoding='utf-8')

    def close(self):
        if self.sandbox is not None:
            (self.sandbox/'close.json').write_text(json.dumps(dict(frame=self.frames)), encoding='utf-8')
        if self.config.get('close_error'):
            raise RuntimeError('invented cleanup failure')


def arrival_factory(configuration):
    return ArrivalAdapter(configuration)


@contextmanager
def arrival_graph():
    yield dict(revision='invented-arrival-graph', complete=True, references=[],
               pins=[], leases=[], ownership={})


class ArrivalSweepTests(unittest.TestCase):
    def setUp(self):
        # Optional retention is for inspecting failed synthetic runs without
        # changing their outputs. Normal test runs clean up their own tempdir.
        retained = os.environ.get('PATCHQUEST_TEST_OUTPUT')
        if retained:
            self.root = Path(tempfile.mkdtemp(prefix=self._testMethodName+'-', dir=retained))
        else:
            temporary = tempfile.TemporaryDirectory()
            self.addCleanup(temporary.cleanup)
            self.root = Path(temporary.name)
        self.caps = validate('AdapterCapabilities', dict(schema_version=1, kind='AdapterCapabilities',
            adapter=dict(id='invented-arrival-adapter', version='1'), provenance='synthetic',
            capabilities=dict(capture_frames=True, input=True)))
        self.configuration = dict(caps=self.caps, binary_sha256=sha(b'invented adapter implementation'))
        self.raw = b'independently invented program bytes'
        self.binding = dict(schema_version=1, kind='RunBinding', build_id='invented-arrival-build',
            artifacts={'program': sha(self.raw)}, snapshot=sha(b'invented snapshot'), records={},
            scenario_sha256=sha(b'invented scenario'), configuration_sha256=digest(self.configuration),
            adapter=self.caps['adapter'], emulator=dict(id='invented-engine', version='1',
            sha256=self.configuration['binary_sha256']), expectation_sha256=sha(b'invented expectations'),
            detectors={})
        self.case = validate('CaseSpec', dict(schema_version=1, kind='CaseSpec',
            case_id='invented-arrival-case', coverage_scope='invented-arrival-scope',
            required_capabilities=['capture_frames']))
        self.scene = dict(schema_version=1, scene_id='invented-arrival-scene', case=self.case,
            reach_method='cold_boot_navigation', checkpoint=None, checkpoint_binding=None,
            regenerate_from=None, steps=[dict(frames=2, buttons=['Left']), dict(frames=1, buttons=['Right'])],
            arrival_assertions=[dict(kind='region_hash', label='invented-arrival-colors',
                rect=[0, 0, 2, 1], sha256=sha(pixels(4)))],
            limits=dict(frames=12, seconds=5, attempts=1))
        self.extra_scenes = []
        self.exercises = {self.case['case_id']: dict(scene_id=self.scene['scene_id'],
                                                    mode='arrival_only', steps=[])}
        self.artifacts = RuntimeArtifacts(self.root/'blobs', budget_bytes=1024*1024,
                                          graph_guard=arrival_graph)
        self.build_refs = {'program': self.register(self.raw, 'invented-program')}
        self.bounds = dict(startup_seconds=5, case_seconds=2, shutdown_seconds=0.3,
                           total_seconds=15, worker_cases=1)

    def register(self, raw, name):
        ref = reference(raw, evidence_id=name, media_type='application/octet-stream',
            provenance=dict(producer='invented-arrival-fixture', method='synthetic', run_id=None, case_id=None))
        return self.artifacts.register(ref, raw)

    def run_sweep(self, name='run', **kwargs):
        self.binding['configuration_sha256'] = digest(self.configuration)
        inventory = sweep.case_inventory([self.case], scope=self.case['coverage_scope'],
                                         source='independently invented explicit case')
        return sweep.run_sweep(inventory, SceneLibrary([self.scene]+self.extra_scenes), self.exercises,
            self.binding, self.caps, self.artifacts, self.build_refs, self.configuration,
            arrival_factory, self.root/name, limits=kwargs.pop('limits', self.bounds), **kwargs)

    def steps(self, name='run'):
        return [json.loads(line) for path in sorted((self.root/name).rglob('steps.jsonl'))
                for line in path.read_text(encoding='utf-8').splitlines()]

    def check_result(self, result, frames, captures, execution='completed'):
        self.assertEqual(result['observed_frames'], frames)
        observation = result['observations'][0]
        self.assertEqual(observation['frames'], frames)
        self.assertEqual(observation['execution'], execution)
        self.assertEqual([c['frame'] for c in observation['captures']], captures)
        self.assertTrue(all(w['shutdown']['final_state'] == 'stopped' for w in result['workers']))
        self.assertEqual(observation['method'], 'synthetic')
        return observation

    def test_public_preparer_and_spawned_arrival_have_exact_accounting(self):
        self.assertEqual(Path(sweep.__file__).resolve(),
                         Path(__file__).resolve().parents[1]/'src/patchquest/runtime_sweep.py')
        adapter = ArrivalAdapter(self.configuration)
        sandbox = self.root/'preparer'
        sandbox.mkdir()
        adapter.reset({'program': self.raw}, self.configuration, sandbox)
        prepared = prepare_scene(SceneLibrary([self.scene]), self.scene['scene_id'], self.case,
            self.binding, self.caps, adapter, isolated_test_session=True)
        self.assertEqual(prepared['handle']['status'], 'ready')
        self.assertEqual(prepared['frames'], 4)
        self.assertEqual(prepared['attempts'][0]['frame'].rgb, pixels(4))
        result = self.run_sweep()
        observation = self.check_result(result, 4, [4])
        self.assertTrue(result['capture_complete'])
        self.assertEqual(result['runner_version'], '5')
        self.assertEqual(result['definition']['requests'][0]['exercise']['mode'], 'arrival_only')
        self.assertEqual(result['definition_sha256'], digest(result['definition']))
        self.assertEqual([s['buttons'] for s in self.steps()], [['Left'], ['Left'], ['Right'], []])
        self.assertEqual(observation['assertion'], 'not_assessed')
        proof = next((self.root/'run').rglob('observe.json'))
        self.assertEqual(json.loads(proof.read_text())['frame'], 4)
        captured = self.artifacts.resolve(observation['captures'][0]['evidence'])
        self.assertEqual(captured['data'], Frame(2, 1, pixels(4)).png())

    def test_failed_arrival_retains_diagnostic_without_exercise_or_observe(self):
        self.scene['arrival_assertions'][0]['sha256'] = sha(b'invented mismatching pixels')
        result = self.run_sweep()
        self.check_result(result, 4, [4], 'failed')
        self.assertFalse(result['capture_complete'])
        self.assertEqual(len(self.steps()), 4)
        self.assertFalse(list((self.root/'run').rglob('observe.json')))

    def test_retry_retains_failed_and_ready_attempts_and_charges_all_frames(self):
        self.scene['limits']['attempts'] = 2
        self.configuration['first_attempt_fails'] = True
        result = self.run_sweep()
        self.check_result(result, 8, [4, 8])
        self.assertTrue(result['capture_complete'])
        self.assertEqual(len(self.steps()), 8)
        self.assertEqual(len(list((self.root/'run').rglob('observe.json'))), 1)

    def test_retry_capture_limit_preserves_first_diagnostic_and_fails(self):
        self.scene['limits']['attempts'] = 2
        self.configuration['first_attempt_fails'] = True
        result = self.run_sweep(limits=dict(self.bounds, captures_per_case=1))
        self.check_result(result, 8, [4], 'interrupted')
        self.assertFalse(result['capture_complete'])
        self.assertEqual(len(self.steps()), 8)
        self.assertFalse(list((self.root/'run').rglob('observe.json')))

    def test_missing_capture_or_scene_input_is_unsupported_before_stepping(self):
        for capability in ('capture_frames', 'input'):
            with self.subTest(capability=capability):
                self.caps['capabilities'][capability] = False
                result = self.run_sweep(name=capability)
                self.check_result(result, 0, [], 'unsupported')
                self.assertFalse(result['capture_complete'])
                self.assertFalse(self.steps(capability))
                self.caps['capabilities'][capability] = True

    def test_legacy_and_explicit_exercise_have_same_plan_and_inputs(self):
        spec = self.exercises[self.case['case_id']]
        del spec['mode']
        spec['steps'] = [dict(frames=2, buttons=['B'], capture=True)]
        original = copy.deepcopy(spec)
        result = self.run_sweep()
        self.check_result(result, 6, [4, 6])
        self.assertEqual(spec, original)  # Normalization does not mutate the caller.
        self.assertEqual([s['buttons'] for s in self.steps()][-2:], [['B'], ['B']])
        spec['mode'] = 'exercise'
        resumed = self.run_sweep(name='explicit', resume=self.root/'run/manifest.json')
        self.assertEqual(result['definition_sha256'], resumed['definition_sha256'])
        self.assertEqual(resumed['workers'], [])
        self.assertTrue(resumed['capture_complete'])

    def test_legacy_exercise_failure_retains_preparation_diagnostic(self):
        spec = self.exercises[self.case['case_id']]
        spec.update(mode='exercise', steps=[dict(frames=2, buttons=['B'], capture=True)])
        self.scene['arrival_assertions'][0]['sha256'] = sha(b'invented mismatch')
        result = self.run_sweep()
        self.check_result(result, 4, [4], 'failed')
        self.assertEqual(len(self.steps()), 4)
        self.assertFalse(list((self.root/'run').rglob('observe.json')))

    def test_request_validation_precedes_resolution_and_output(self):
        valid = copy.deepcopy(self.exercises[self.case['case_id']])
        invalid = [dict(scene_id=self.scene['scene_id'], steps=[]),
            dict(valid, mode='unknown'), dict(valid, mode=None), dict(valid, mode=[]),
            dict(valid, steps=None), dict(valid, extra=True),
            dict(scene_id=self.scene['scene_id'], mode='arrival_only'),
            dict(valid, steps=[dict(frames=1, buttons=[], capture=True)]),
            dict(valid, mode='exercise', steps=[dict(frames=0, buttons=[], capture=True)]),
            dict(valid, mode='exercise', steps=[dict(frames=1, buttons=['Unknown'], capture=True)]),
            dict(valid, mode='exercise', steps=[dict(frames=1, buttons=[], capture=False)])]
        for index, spec in enumerate(invalid):
            with self.subTest(index=index), mock.patch.object(self.artifacts, 'retained_build') as resolved:
                self.exercises[self.case['case_id']] = spec
                with self.assertRaises(ContractError):
                    self.run_sweep(name='invalid-'+str(index))
                resolved.assert_not_called()
                self.assertFalse((self.root/('invalid-'+str(index))).exists())
        self.exercises[self.case['case_id']] = valid
        self.scene['arrival_assertions'] = []
        with self.assertRaises(ContractError):
            self.run_sweep(name='no-assertions')
        self.assertFalse((self.root/'no-assertions').exists())

    def test_frame_limits_include_preparation_and_no_extra_final_frame(self):
        exact = self.run_sweep(name='exact', limits=dict(self.bounds, frames_per_case=4))
        self.check_result(exact, 4, [4])
        short = self.run_sweep(name='short', limits=dict(self.bounds, frames_per_case=3))
        self.check_result(short, 3, [3], 'interrupted')
        self.assertEqual(len(self.steps('short')), 3)
        self.assertFalse(list((self.root/'short').rglob('observe.json')))

    def test_capture_byte_limit_fails_without_an_extra_step(self):
        result = self.run_sweep(limits=dict(self.bounds, capture_bytes=1))
        self.check_result(result, 4, [], 'failed')
        self.assertEqual(len(self.steps()), 4)
        self.assertFalse(list((self.root/'run').rglob('observe.json')))
        self.assertFalse(result['capture_complete'])

    def test_cancel_before_work_and_during_preparation(self):
        before = self.run_sweep(name='before', cancelled=lambda: True)
        self.assertEqual(before['workers'], [])
        self.check_result(before, 0, [], 'not_run')
        self.configuration['pause_frame'] = 2
        during = self.run_sweep(name='during',
            cancelled=lambda: any((self.root/'during').rglob('pause.flag')))
        self.assertFalse(during['capture_complete'])
        self.assertEqual(during['observations'][0]['execution'], 'interrupted')
        self.assertEqual(during['observations'][0]['captures'], [])
        self.assertEqual(len(self.steps('during')), 2)
        self.assertFalse(list((self.root/'during').rglob('observe.json')))
        self.assertEqual(during['workers'][0]['shutdown']['final_state'], 'stopped')

    def test_case_timeout_preserves_interruption_without_extra_capture(self):
        self.configuration['pause_frame'] = 2
        result = self.run_sweep(limits=dict(self.bounds, case_seconds=0.2))
        self.assertFalse(result['capture_complete'])
        self.assertEqual(result['observations'][0]['execution'], 'interrupted')
        self.assertEqual(result['observations'][0]['captures'], [])
        self.assertEqual(len(self.steps()), 2)
        self.assertEqual(result['workers'][0]['shutdown']['final_state'], 'stopped')

    def test_cleanup_failure_cannot_establish_capture_completion(self):
        self.configuration['close_error'] = True
        result = self.run_sweep()
        self.assertEqual(result['observations'][0]['frames'], 4)
        self.assertEqual([c['frame'] for c in result['observations'][0]['captures']], [4])
        self.assertFalse(result['capture_complete'])
        self.assertFalse(result['workers'][0]['clean_exit'])
        self.assertEqual(result['workers'][0]['shutdown']['final_state'], 'stopped')

    def test_exact_arrival_resume_reuses_original_and_refuses_other_modes_and_versions(self):
        result = self.run_sweep()
        resumed = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertTrue(resumed['capture_complete'])
        self.assertEqual(resumed['observed_frames'], 0)
        self.assertEqual(resumed['workers'], [])
        self.assertEqual(resumed['observations'][0], result['observations'][0])
        for version in ('1', '2', '3', '4'):
            prior = copy.deepcopy(result)
            prior['runner_version'] = prior['definition']['runner_version'] = version
            del prior['definition']['requests'][0]['exercise']['mode']
            prior['definition_sha256'] = digest(prior['definition'])
            path = self.root/('prior-'+version+'.json')
            path.write_text(json.dumps(prior), encoding='utf-8')
            with self.subTest(version=version), mock.patch.object(self.artifacts, 'retained_build') as resolved:
                with self.assertRaises(ContractError):
                    self.run_sweep(name='version-'+version, resume=path)
                resolved.assert_not_called()
                self.assertFalse((self.root/('version-'+version)).exists())
        self.exercises[self.case['case_id']].update(mode='exercise',
            steps=[dict(frames=1, buttons=[], capture=True)])
        with mock.patch.object(self.artifacts, 'retained_build') as resolved:
            with self.assertRaises(ContractError):
                self.run_sweep(name='changed-mode', resume=self.root/'run/manifest.json')
            resolved.assert_not_called()
        self.assertFalse((self.root/'changed-mode').exists())

    def test_existing_supported_routes_remain_available_with_arrival_only(self):
        for route, capability, receipt in (('emulator_state', 'restore_state', 'restore.txt'),
                ('in_game_save', 'game_save', 'save.txt'), ('debug_injection', 'debug_access', 'debug.txt')):
            with self.subTest(route=route):
                base = copy.deepcopy(self.scene)
                self.caps['capabilities'][capability] = True
                self.binding['configuration_sha256'] = digest(self.configuration)
                self.scene = copy.deepcopy(base)
                self.scene.update(scene_id='invented-'+route, reach_method=route)
                self.extra_scenes = []
                if route != 'debug_injection':
                    self.scene.update(checkpoint=self.register(b'invented checkpoint '+route.encode(),
                        'invented-checkpoint-'+route), checkpoint_binding=copy.deepcopy(self.binding),
                        regenerate_from='invented-cold-regeneration')
                    cold = copy.deepcopy(base)
                    cold.update(scene_id='invented-cold-regeneration', reach_method='cold_boot_navigation',
                                checkpoint=None, checkpoint_binding=None, regenerate_from=None)
                    self.extra_scenes = [cold]
                else:
                    self.scene.update(checkpoint=None, checkpoint_binding=None, regenerate_from=None)
                self.exercises[self.case['case_id']]['scene_id'] = self.scene['scene_id']
                result = self.run_sweep(name=route)
                self.check_result(result, 4, [4])
                self.assertTrue(result['capture_complete'])
                self.assertTrue(list((self.root/route).rglob(receipt)))
                self.caps['capabilities'][capability] = False
                self.binding['configuration_sha256'] = digest(self.configuration)
                if route != 'debug_injection':
                    self.scene['checkpoint_binding'] = copy.deepcopy(self.binding)
                missing = self.run_sweep(name=route+'-unsupported')
                self.check_result(missing, 0, [], 'unsupported')


if __name__ == '__main__':
    unittest.main()

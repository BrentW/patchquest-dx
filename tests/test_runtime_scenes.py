"""Invented pixels, saves and identities; no game or emulator evidence."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.runtime import Frame
from patchquest.runtime_contracts import ContractError, validate
from patchquest.runtime_scenes import SceneLibrary, checkpoint_changes, prepare_scene, scene_data


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


class InventedAdapter:
    def __init__(self, binding):
        self.binding = binding
        self.events = []
        self.color = b'\x03\x07\x0b'

    def describe(self):
        return dict(kind='synthetic', sha256=self.binding['emulator']['sha256'],
                    version=self.binding['emulator']['version'])

    def step(self, buttons):
        self.events.append(('step', list(buttons)))
        return Frame(1, 1, self.color)

    def restore(self, raw):
        self.events.append(('restore', raw))

    def load_save_ram(self, raw):
        self.events.append(('save', raw))


class SceneTests(unittest.TestCase):
    def setUp(self):
        connectors = json.loads((Path(__file__).parent /
            'fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.binding = connectors['RunBinding']
        self.case = connectors['CaseSpec']
        self.caps = connectors['AdapterCapabilities']
        self.caps['capabilities'].update(input=True, restore_state=True, game_save=True, debug_access=True)
        self.raw = b'independently invented checkpoint payload'
        self.checkpoint = copy.deepcopy(connectors['EvidenceRef'])
        self.checkpoint.update(sha256=sha(self.raw), byte_length=len(self.raw), integrity='unverified')
        self.scene = dict(schema_version=1, scene_id='invented-room', case=self.case,
            reach_method='cold_boot_navigation', checkpoint=None, checkpoint_binding=None,
            regenerate_from=None, steps=[dict(frames=2, buttons=['A'])],
            arrival_assertions=[dict(kind='region_hash', label='invented-destination',
                rect=[0, 0, 1, 1], sha256=sha(b'\x03\x07\x0b'))],
            limits=dict(frames=12, seconds=10, attempts=1))
        self.adapter = InventedAdapter(self.binding)

    def saved(self, route='emulator_state'):
        scene = copy.deepcopy(self.scene)
        scene.update(scene_id='invented-checkpoint', reach_method=route,
                     checkpoint=self.checkpoint, checkpoint_binding=copy.deepcopy(self.binding),
                     regenerate_from='invented-room')
        return scene

    def run_scene(self, scene=None, **kwargs):
        scene = scene or self.scene
        library = SceneLibrary([self.scene, scene] if scene['scene_id'] != self.scene['scene_id'] else [scene])
        return prepare_scene(library, scene['scene_id'], kwargs.pop('case', self.case),
            kwargs.pop('binding', self.binding), kwargs.pop('capabilities', self.caps),
            kwargs.pop('adapter', self.adapter), **kwargs)

    def test_repeatable_cold_boot_setup_and_arrival(self):
        for _ in range(3):
            adapter = InventedAdapter(self.binding)
            result = self.run_scene(adapter=adapter)
            self.assertEqual(result['handle']['status'], 'ready')
            self.assertEqual(result['frames'], 3)
            self.assertEqual(adapter.events, [('step', ['A']), ('step', ['A']), ('step', [])])
            self.assertEqual(result['handle'], validate('SceneHandle', result['handle']))
            self.assertEqual(result['method'], 'synthetic')
            self.assertTrue(result['normal_route'])

    def test_state_and_game_save_use_separate_existing_interfaces(self):
        for route, event in [('emulator_state', 'restore'), ('in_game_save', 'save')]:
            adapter = InventedAdapter(self.binding)
            result = self.run_scene(self.saved(route), adapter=adapter, checkpoint_bytes=self.raw)
            self.assertEqual(result['handle']['status'], 'ready')
            self.assertEqual(adapter.events[0], (event, self.raw))
            self.assertEqual(result['normal_route'], route == 'in_game_save')
            self.assertEqual(result['handle']['checkpoint']['integrity'], 'unverified')

    def test_every_checkpoint_identity_component_rejects_before_restore(self):
        for field in ('build_id', 'artifacts', 'snapshot', 'records', 'adapter', 'emulator', 'configuration_sha256'):
            target = copy.deepcopy(self.binding)
            if field == 'build_id': target[field] += '-new'
            elif field in ('artifacts', 'records'): target[field][next(iter(target[field]))] = sha(b'new') if field == 'artifacts' else 2
            elif field in ('adapter', 'emulator'): target[field]['version'] = '2'
            else: target[field] = sha(b'new')
            caps = copy.deepcopy(self.caps); caps['adapter'] = target['adapter']
            result = self.run_scene(self.saved(), binding=target, capabilities=caps, checkpoint_bytes=self.raw)
            self.assertEqual(result['handle']['status'], 'incompatible', field)
            self.assertIn(field, checkpoint_changes(self.binding, target))
            self.assertEqual(result['regeneration']['regenerate_from'], 'invented-room')
        self.assertEqual(self.adapter.events, [])

    def test_changed_text_revision_invalidates_loadable_state(self):
        target = copy.deepcopy(self.binding); target['records']['greeting'] += 1
        result = self.run_scene(self.saved(), binding=target, checkpoint_bytes=self.raw)
        self.assertEqual(result['handle']['status'], 'incompatible')
        self.assertEqual(self.adapter.events, [])

    def test_independent_scenario_and_detector_identity_do_not_change_checkpoint_bytes(self):
        target = copy.deepcopy(self.binding)
        target.update(scenario_sha256=sha(b'new scenario'), expectation_sha256=sha(b'new assertion'), detectors={})
        self.assertEqual(checkpoint_changes(self.binding, target), [])
        result = self.run_scene(self.saved(), binding=target, checkpoint_bytes=self.raw)
        self.assertEqual(result['handle']['binding'], validate('RunBinding', target))

    def test_missing_corrupt_and_wrong_length_checkpoint_rejected(self):
        for raw in (None, b'wrong', self.raw + b'!'):
            result = self.run_scene(self.saved(), checkpoint_bytes=raw)
            self.assertEqual(result['handle']['status'], 'incompatible')
        self.assertEqual(self.adapter.events, [])

    def test_synthetic_checkpoint_cannot_be_used_as_actual_emulator_evidence(self):
        caps = copy.deepcopy(self.caps); caps['provenance'] = 'actual_emulator'
        result = self.run_scene(self.saved(), capabilities=caps, checkpoint_bytes=self.raw)
        self.assertEqual(result['handle']['status'], 'incompatible')

    def test_failed_arrival_retains_frame_and_check(self):
        self.adapter.color = b'\x00\x00\x00'
        result = self.run_scene()
        self.assertEqual(result['handle']['status'], 'failed')
        attempt = result['attempts'][0]
        self.assertIsInstance(attempt['frame'], Frame)
        self.assertFalse(attempt['checks'][0]['passed'])
        self.assertEqual(result['handle']['reach_method'], 'cold_boot_navigation')

    def test_color_arrival_uses_shared_runtime_assertion(self):
        self.scene['arrival_assertions'] = [dict(kind='color_count', label='invented-color',
            rect=[0, 0, 1, 1], color=[3, 7, 11], minimum=1, maximum=1)]
        self.assertEqual(self.run_scene()['handle']['status'], 'ready')

    def test_capabilities_fail_before_adapter_work(self):
        for capability in ('capture_frames', 'input', 'restore_state', 'game_save', 'debug_access'):
            caps = copy.deepcopy(self.caps); caps['capabilities'][capability] = False
            scene = self.saved('in_game_save' if capability == 'game_save' else 'emulator_state') if capability in ('game_save', 'restore_state') else copy.deepcopy(self.scene)
            if capability == 'debug_access': scene['reach_method'] = 'debug_injection'
            result = self.run_scene(scene, capabilities=caps,
                **({'checkpoint_bytes': self.raw} if scene['checkpoint'] else {}))
            self.assertEqual(result['handle']['status'], 'unsupported')
        self.assertEqual(self.adapter.events, [])

    def test_debug_requires_isolation_and_never_claims_normal_route(self):
        scene = copy.deepcopy(self.scene); scene['reach_method'] = 'debug_injection'
        hooks = []
        hook = lambda adapter: hooks.append(adapter)
        result = self.run_scene(scene, debug_setup=hook)
        self.assertEqual(result['handle']['status'], 'unsupported'); self.assertFalse(hooks)
        result = self.run_scene(scene, debug_setup=hook, isolated_test_session=True)
        self.assertEqual(result['handle']['status'], 'ready'); self.assertEqual(hooks, [self.adapter])
        self.assertTrue(result['debug_assisted']); self.assertFalse(result['normal_route'])
        self.assertEqual(result['handle']['reach_method'], 'debug_injection')

    def test_unrequested_debug_and_checkpoint_rejected(self):
        for kwargs in ({'debug_setup': lambda a: None}, {'checkpoint_bytes': self.raw}):
            with self.assertRaises(ContractError): self.run_scene(**kwargs)

    def test_retries_retain_failures_and_require_fresh_session_reset(self):
        self.scene['limits']['attempts'] = 2
        self.assertEqual(self.run_scene()['handle']['status'], 'unsupported')
        def reset(number):
            self.adapter.color = b'\x00\x00\x00' if number == 1 else b'\x03\x07\x0b'
        result = self.run_scene(reset=reset)
        self.assertEqual([a['status'] for a in result['attempts']], ['failed', 'ready'])
        self.assertEqual(result['frames'], 6)

    def test_frame_budget_is_shared_across_retries(self):
        self.scene['limits'].update(attempts=3, frames=4)
        self.adapter.color = b'\x00\x00\x00'
        result = self.run_scene(reset=lambda n: None)
        self.assertEqual(result['handle']['status'], 'failed')
        self.assertEqual(result['frames'], 4)
        self.assertEqual(len(result['attempts']), 2)

    def test_elapsed_budget_checks_slow_step_and_restore(self):
        for saved in (False, True):
            seconds = [0]
            original = self.adapter.restore if saved else self.adapter.step
            def slow(*args):
                result = original(*args); seconds[0] += 11; return result
            if saved: self.adapter.restore = slow
            else: self.adapter.step = slow
            result = self.run_scene(self.saved() if saved else None,
                clock=lambda: seconds[0], **({'checkpoint_bytes': self.raw} if saved else {}))
            self.assertEqual(result['handle']['status'], 'failed')
            self.assertEqual(result['elapsed_seconds'], 11)

    def test_adapter_failure_is_retained_without_leaking_exception_text(self):
        def bad(buttons): raise RuntimeError('private adapter detail')
        self.adapter.step = bad
        result = self.run_scene()
        self.assertEqual(result['frames'], 1)
        self.assertIn('RuntimeError', result['handle']['reason'])
        self.assertNotIn('private adapter detail', result['handle']['reason'])

    def test_identity_drift_is_rejected(self):
        self.adapter.describe = lambda: dict(kind='actual_emulator', sha256=sha(b'wrong'), version='1')
        self.assertEqual(self.run_scene()['handle']['status'], 'failed')
        self.assertEqual(self.adapter.events, [])

    def test_missing_restore_interface_is_explicitly_unsupported(self):
        self.adapter.restore = None
        result = self.run_scene(self.saved(), checkpoint_bytes=self.raw)
        self.assertEqual(result['handle']['status'], 'unsupported')
        self.assertEqual(self.adapter.events, [])

    def test_identity_drift_after_restore_cannot_pass_arrival(self):
        def changed(raw):
            self.adapter.describe = lambda: dict(kind='synthetic', sha256=sha(b'other'), version='1')
        self.adapter.restore = changed
        result = self.run_scene(self.saved(), checkpoint_bytes=self.raw)
        self.assertEqual(result['handle']['status'], 'failed')
        self.assertEqual(result['frames'], 0)

    def test_timed_out_frame_is_retained_and_no_retry_hides_timeout(self):
        seconds = [0]
        self.scene['limits']['attempts'] = 3
        def step(buttons):
            seconds[0] = 12
            return Frame(1, 1, self.adapter.color)
        self.adapter.step = step
        result = self.run_scene(reset=lambda n: None, clock=lambda: seconds[0])
        self.assertEqual(result['handle']['status'], 'failed')
        self.assertEqual(len(result['attempts']), 1)
        self.assertIsInstance(result['attempts'][0]['frame'], Frame)

    def test_bad_arrival_rectangle_retains_failure(self):
        self.scene['arrival_assertions'][0]['rect'] = [1, 0, 1, 1]
        result = self.run_scene()
        self.assertEqual(result['handle']['status'], 'failed')
        self.assertIsInstance(result['attempts'][0]['frame'], Frame)

    def test_case_definition_and_record_scope_cannot_be_substituted(self):
        case = copy.deepcopy(self.case); case['page'] = 1
        with self.assertRaises(ContractError): self.run_scene(case=case)
        binding = copy.deepcopy(self.binding); binding['records'] = {}
        with self.assertRaises(ContractError): self.run_scene(binding=binding)

    def test_exact_selection_and_detached_definitions(self):
        library = SceneLibrary([self.scene]); self.scene['steps'][0]['frames'] = 99
        self.assertEqual(library.select('invented-room')['steps'][0]['frames'], 2)
        selected = library.select('invented-room'); selected['steps'].clear()
        self.assertTrue(library.select('invented-room')['steps'])
        with self.assertRaises(KeyError): library.select('absent')
        with self.assertRaises(ContractError): SceneLibrary([selected, selected])

    def test_regeneration_rejects_missing_state_debug_and_cyclic_sources(self):
        scene = self.saved()
        with self.assertRaises(ContractError): SceneLibrary([scene])
        for route in ('debug_injection', 'emulator_state'):
            base = copy.deepcopy(self.scene)
            if route == 'emulator_state':
                base.update(reach_method=route, checkpoint=self.checkpoint,
                    checkpoint_binding=self.binding, regenerate_from=scene['scene_id'])
            else: base['reach_method'] = route
            with self.assertRaises(ContractError): SceneLibrary([base, scene])
        a = self.saved('in_game_save'); b = self.saved('in_game_save')
        b['scene_id'] = 'other'; a['regenerate_from'] = 'other'; b['regenerate_from'] = a['scene_id']
        with self.assertRaises(ContractError): SceneLibrary([a, b])

    def test_malformed_definitions_reject_before_execution(self):
        mutations = [lambda s: s.update(schema_version=True), lambda s: s.update(command='bad'),
            lambda s: s['limits'].update(frames=2), lambda s: s['limits'].update(attempts=4),
            lambda s: s['limits'].update(seconds=0), lambda s: s['steps'][0].update(buttons=['A','A']),
            lambda s: s['arrival_assertions'][0].update(sha256='x'*64),
            lambda s: s['arrival_assertions'].append(copy.deepcopy(s['arrival_assertions'][0]))]
        for mutate in mutations:
            scene = copy.deepcopy(self.scene); mutate(scene)
            with self.assertRaises(ContractError): scene_data(scene)


if __name__ == '__main__':
    unittest.main()

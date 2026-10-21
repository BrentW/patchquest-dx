"""Explicit private scene preparation; no discovery, worker lifecycle or file writes.

Synchronous adapters must run inside the runner's bounded worker. Synthetic
preparation proves orchestration only, never actual scene arrival or text quality.
"""
import copy
import hashlib
import json
import time

from .runtime import BUTTONS, Frame, assertion
from .runtime_contracts import (
    ContractError, UnsupportedCapability, contract_digest, require_capabilities,
    validate, verify_evidence_bytes,
)

COMPATIBILITY_FIELDS = ('build_id', 'artifacts', 'snapshot', 'records', 'adapter',
                        'emulator', 'configuration_sha256')


def _need(condition, reason):
    if not condition:
        raise ContractError(reason)


def _integer(value, low, high, name):
    _need(type(value) is int and low <= value <= high, 'Invalid ' + name)
    return value


def _name(value):
    _need(type(value) is str and 0 < len(value) <= 200 and value.strip() == value,
          'Expected bounded nonempty identity')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def scene_data(value):
    """Validate a private definition, retaining exact setup and arrival conditions."""
    _need(type(value) is dict and set(value) == {
        'schema_version', 'scene_id', 'case', 'reach_method', 'checkpoint',
        'checkpoint_binding', 'steps', 'arrival_assertions', 'limits',
        'regenerate_from'}, 'Unknown or missing scene fields')
    d = copy.deepcopy(value)
    _need(type(d['schema_version']) is int and d['schema_version'] == 1,
          'Unsupported scene schema')
    _name(d['scene_id'])
    d['case'] = validate('CaseSpec', d['case'])
    _need(d['reach_method'] in ('cold_boot_navigation', 'in_game_save',
                               'emulator_state', 'debug_injection'), 'Unknown route')
    saved = d['reach_method'] in ('in_game_save', 'emulator_state')
    _need((d['checkpoint'] is not None) == saved and
          (d['checkpoint_binding'] is not None) == saved,
          'Only save/state routes require checkpoint and origin binding')
    if saved:
        d['checkpoint'] = validate('EvidenceRef', d['checkpoint'])
        d['checkpoint_binding'] = validate('RunBinding', d['checkpoint_binding'])
        _name(d['regenerate_from'])
    else:
        _need(d['regenerate_from'] is None, 'Fresh routes do not regenerate checkpoints')
    _need(type(d['steps']) is list and len(d['steps']) <= 500, 'Bounded setup steps required')
    total = 1  # Always observe a fresh arrival frame, even after restore.
    for step in d['steps']:
        _need(type(step) is dict and set(step) == {'frames', 'buttons'}, 'Invalid setup step')
        total += _integer(step['frames'], 1, 3600, 'step frames')
        buttons = step['buttons']
        _need(type(buttons) is list and all(type(b) is str and b in BUTTONS for b in buttons)
              and len(buttons) == len(set(buttons)), 'Invalid setup buttons')
    checks = d['arrival_assertions']
    _need(type(checks) is list and 1 <= len(checks) <= 100, 'Named arrival assertions required')
    names = []
    for check in checks:
        _need(type(check) is dict, 'Invalid arrival assertion')
        kind = check.get('kind')
        fields = {'kind', 'label', 'rect'}
        if kind == 'region_hash':
            fields |= {'sha256'}
            _need(type(check.get('sha256')) is str and len(check['sha256']) == 64
                  and all(c in '0123456789abcdef' for c in check['sha256']), 'Invalid arrival hash')
        elif kind == 'color_count':
            fields |= {'color', 'tolerance', 'minimum', 'maximum'}
            color = check.get('color')
            _need(type(color) is list and len(color) == 3, 'Expected arrival RGB')
            for channel in color:
                _integer(channel, 0, 255, 'RGB channel')
            _integer(check.get('tolerance', 0), 0, 255, 'color tolerance')
        else:
            raise ContractError('Unsupported arrival assertion')
        _need(not set(check) - fields and {'kind', 'label', 'rect'} <= set(check),
              'Unknown arrival assertion fields')
        _name(check['label']); names.append(check['label'])
        rect = check['rect']
        _need(type(rect) is list and len(rect) == 4, 'Expected arrival rectangle')
        for coordinate in rect[:2]:
            _integer(coordinate, 0, 2047, 'rectangle origin')
        for size in rect[2:]:
            _integer(size, 1, 2048, 'rectangle size')
        if kind == 'color_count':
            count = rect[2] * rect[3]
            minimum = _integer(check.get('minimum', 0), 0, count, 'minimum pixels')
            _integer(check.get('maximum', count), minimum, count, 'maximum pixels')
    _need(len(names) == len(set(names)), 'Duplicate arrival assertion identity')
    limits = d['limits']
    _need(type(limits) is dict and set(limits) == {'frames', 'seconds', 'attempts'}, 'Explicit scene limits required')
    _integer(limits['frames'], 1, 20000, 'total frames')
    _integer(limits['seconds'], 1, 600, 'elapsed seconds')
    _integer(limits['attempts'], 1, 3, 'attempt count')
    _need(total <= limits['frames'], 'Setup exceeds frame budget')
    return d


class SceneLibrary:
    """An explicitly supplied inventory; reads neither manifests nor directories."""

    def __init__(self, scenes):
        _need(type(scenes) is list and len(scenes) <= 1000, 'Bounded scene list required')
        self._scenes = {}
        for value in scenes:
            scene = scene_data(value)
            _need(scene['scene_id'] not in self._scenes, 'Duplicate scene identity')
            self._scenes[scene['scene_id']] = scene
        for scene in self._scenes.values():
            target = scene['regenerate_from']
            if target is not None:
                _need(target in self._scenes and target != scene['scene_id'], 'Missing regeneration route')
                _need(self._scenes[target]['reach_method'] in ('cold_boot_navigation', 'in_game_save'),
                      'Regenerate from cold boot or independently checked in-game save')
                visited = {scene['scene_id']}
                while target is not None:
                    _need(target not in visited, 'Cyclic regeneration route')
                    visited.add(target)
                    target = self._scenes[target]['regenerate_from']

    def select(self, scene_id):
        """Exact named selection; missing names never fall back."""
        if scene_id not in self._scenes:
            raise KeyError('Requested scene is not registered')
        return copy.deepcopy(self._scenes[scene_id])

    def regeneration(self, scene_id):
        """Return a plan only; never run a fallback or overwrite an old state."""
        scene = self.select(scene_id)
        return dict(scene_id=scene_id, regenerate_from=scene['regenerate_from'],
                    instructions='Explicitly prepare the regeneration route on the new build, verify arrival, '
                    'capture a new checkpoint through the runner, and register a new definition. '
                    'Preserve the prior checkpoint and its binding.')


def checkpoint_changes(origin, current):
    """Conservative exact-build/save compatibility; scenario assertions can differ."""
    a, b = validate('RunBinding', origin), validate('RunBinding', current)
    return [key for key in COMPATIBILITY_FIELDS if a[key] != b[key]]


def prepare_scene(library, scene_id, case, binding, capabilities, adapter, *,
                  checkpoint_bytes=None, isolated_test_session=False,
                  debug_setup=None, reset=None, clock=time.monotonic):
    """Prepare on a runner-owned, freshly loaded session and verify arrival.

    Adapter uses existing step/restore/load_save_ram/describe methods. The runner
    verifies loaded artifact/configuration bytes, owns the isolated work directory
    and enforces a hard process timeout. reset(attempt_number) must reload the same
    pinned build on each attempt when retries are enabled. debug_setup(adapter)
    may touch volatile emulator state only. Neither callback receives ROM bytes.
    Returned frames/checks and failed attempts must be retained by the runner.
    """
    scene = library.select(scene_id)
    case, binding = validate('CaseSpec', case), validate('RunBinding', binding)
    caps = validate('AdapterCapabilities', capabilities)
    _need(contract_digest('CaseSpec', case) == contract_digest('CaseSpec', scene['case']),
          'Requested case differs from scene definition')
    _need(set(case['record_ids']) <= set(binding['records']), 'Missing scoped record revisions')
    _need(type(isolated_test_session) is bool, 'Expected isolation declaration')
    route = scene['reach_method']
    method = 'synthetic' if caps['provenance'] == 'synthetic' else 'automated_runtime'
    handle = dict(schema_version=1, kind='SceneHandle', scene_id=scene_id, binding=binding,
                  reach_method=route, checkpoint=scene['checkpoint'],
                  arrival_assertions=[c['label'] for c in scene['arrival_assertions']],
                  status='unknown', reason='Preparation not run')
    result = dict(handle=None, scene_sha256=_digest(scene),
                  case_sha256=contract_digest('CaseSpec', case), method=method,
                  provenance=caps['provenance'], debug_assisted=route == 'debug_injection',
                  normal_route=route in ('cold_boot_navigation', 'in_game_save'),
                  attempts=[], frames=0, elapsed_seconds=0, regeneration=None)
    started = clock()

    def finish(status, reason=''):
        handle.update(status=status, reason=reason)
        result['handle'] = validate('SceneHandle', handle)
        result['elapsed_seconds'] = max(0, clock() - started)
        return result

    if binding['adapter'] != caps['adapter']:
        return finish('incompatible', 'Adapter identity differs from binding')
    if scene['checkpoint'] is not None:
        changes = checkpoint_changes(scene['checkpoint_binding'], binding)
        if changes:
            result['regeneration'] = library.regeneration(scene_id)
            return finish('incompatible', 'Checkpoint identity differs: ' + ', '.join(changes))
        if scene['checkpoint']['provenance']['method'] != method:
            return finish('incompatible', 'Checkpoint provenance differs from adapter execution method')
        if checkpoint_bytes is None or not verify_evidence_bytes(scene['checkpoint'], checkpoint_bytes):
            return finish('incompatible', 'Checkpoint bytes missing or mismatched')
    elif checkpoint_bytes is not None:
        raise ContractError('Checkpoint bytes supplied for a fresh route')
    needed = {'capture_frames'} | set(case['required_capabilities'])
    if any(step['buttons'] for step in scene['steps']):
        needed.add('input')
    if route in ('emulator_state', 'in_game_save', 'debug_injection'):
        needed.add({'emulator_state': 'restore_state', 'in_game_save': 'game_save',
                    'debug_injection': 'debug_access'}[route])
    requested = dict(case, required_capabilities=sorted(needed))
    try:
        require_capabilities(requested, caps)
    except UnsupportedCapability as error:
        return finish('unsupported', str(error))
    if route == 'debug_injection' and (not isolated_test_session or not callable(debug_setup)):
        return finish('unsupported', 'Debug route requires an isolated test session and explicit volatile hook')
    if route != 'debug_injection' and debug_setup is not None:
        raise ContractError('Debug hook supplied for an ordinary route')
    if scene['limits']['attempts'] > 1 and not callable(reset):
        return finish('unsupported', 'Retries require runner-owned fresh-session reset')
    required_methods = ['step', 'describe']
    if route in ('emulator_state', 'in_game_save'):
        required_methods.append('restore' if route == 'emulator_state' else 'load_save_ram')
    if any(not callable(getattr(adapter, name, None)) for name in required_methods):
        return finish('unsupported', 'Selected route adapter interface unavailable')

    def check_time():
        if clock() - started >= scene['limits']['seconds']:
            raise TimeoutError('Scene elapsed-time budget exhausted')

    def identity():
        description = adapter.describe()
        _need(description.get('kind') == caps['provenance'] and
              description.get('sha256') == binding['emulator']['sha256'] and
              description.get('version') == binding['emulator']['version'],
              'Loaded emulator identity/provenance differs')

    def step(buttons):
        check_time()
        if result['frames'] >= scene['limits']['frames']:
            raise TimeoutError('Scene total-frame budget exhausted')
        result['frames'] += 1  # Charge attempted work even if the adapter raises.
        frame = adapter.step(buttons)
        _need(isinstance(frame, Frame), 'Adapter did not return a runtime Frame')
        attempt['frame'] = frame
        check_time()
        return frame

    for number in range(1, scene['limits']['attempts'] + 1):
        attempt = dict(number=number, status='failed', reason='', checks=[], frame=None)
        result['attempts'].append(attempt)
        try:
            check_time()
            if reset is not None:
                reset(number)
                check_time()
            identity()
            check_time()
            if route == 'emulator_state':
                adapter.restore(checkpoint_bytes)
            elif route == 'in_game_save':
                adapter.load_save_ram(checkpoint_bytes)
            elif route == 'debug_injection':
                debug_setup(adapter)
            check_time()
            identity()
            for setup in scene['steps']:
                for _ in range(setup['frames']):
                    step(list(setup['buttons']))
            frame = step([])
            attempt['frame'] = frame
            for check in scene['arrival_assertions']:
                attempt['checks'].append(assertion(frame, check, {}))
                check_time()
            identity()
            check_time()
            if all(c['passed'] for c in attempt['checks']):
                attempt['status'] = 'ready'
                return finish('ready')
            attempt['reason'] = 'Arrival assertions failed'
        except Exception as error:
            # Keep partial observations and the exception class without potentially
            # sensitive adapter exception text; the owning runner retains raw logs.
            attempt['reason'] = 'Scene preparation error: ' + type(error).__name__
            if isinstance(error, TimeoutError):
                return finish('failed', attempt['reason'])
    return finish('failed', result['attempts'][-1]['reason'])

"""Invented worker protocol only: no ROMs, actual emulators or private state."""
from contextlib import contextmanager, redirect_stdout
import copy
import errno
import hashlib
import io
import json
import multiprocessing
import os
from pathlib import Path
import sys
import tempfile
import time
import threading
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from patchquest.runtime import Frame
from patchquest.runtime_artifacts import RuntimeArtifacts, reference
from patchquest.runtime_contracts import ContractError, check_observation, contract_digest
from patchquest.runtime_scenes import SceneLibrary
from patchquest.runtime_sweep import case_inventory, run_sweep, storage_preflight, _stop
from patchquest import runtime_sweep as sweep


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':')).encode()).hexdigest()


class InventedWorkerAdapter:
    def __init__(self, configuration):
        self.config = configuration
        self.caps = configuration['caps']
        self.frames = 0

    def reset(self, inputs, configuration, sandbox):
        self.inputs = inputs
        self.frames = 0
        self.sandbox = sandbox
        (sandbox/'reset-proof.txt').write_text('invented fresh reset')

    def describe(self):
        return dict(kind=self.config.get('reported_provenance', 'synthetic'), version='1',
                    sha256=self.config['binary_sha256'])

    def capabilities(self):
        return self.caps

    def configuration(self):
        return dict(self.config, changed=True) if self.config.get('configuration_drift') else self.config

    def loaded_artifacts(self):
        return {role: hashlib.sha256(raw).hexdigest() for role, raw in self.inputs.items()}

    def step(self, buttons):
        if buttons == ['B']:
            action = self.config.get('action')
            if action == 'crash': os._exit(9)
            if action == 'hang': time.sleep(30)
            if action == 'error': raise RuntimeError('private diagnostic text')
        self.frames += 1
        color = b'\x03\x07\x0b' if self.frames == 1 else b'\x02\x04\x06'
        return Frame(1, 1, color)

    def observe(self, case, frame):
        if self.config.get('bad_telemetry'):
            return dict(controls={'scrolled': True})
        if self.config.get('instrumentation'):
            return dict(glyphs=[dict(glyph_id='invented-glyph', frame=frame, x=0, y=0, width=1, height=1)],
                resources={'invented-tiles': 1}, controls=dict(page_complete=True, line_advanced=True,
                    scrolled=True, input_wait=True, terminated=True))
        return {}

    def enumerate_cases(self, scope):
        return self.config['enumerated_cases']

    def close(self):
        if self.config.get('close_hang'): time.sleep(30)
        if self.config.get('close_error'): raise RuntimeError('invented close error')
        if self.config.get('exit_linger'):
            threading.Thread(target=time.sleep, args=(self.config['exit_linger'],)).start()
        if self.config.get('exit_crash'):
            from multiprocessing.util import Finalize
            Finalize(None, os._exit, args=(23,), exitpriority=0)


def invented_factory(configuration):
    if configuration.get('factory_hang'): time.sleep(30)
    return InventedWorkerAdapter(configuration)


@contextmanager
def invented_graph():
    # Complete only for this independently invented temporary store.
    yield dict(revision='invented-empty-fixture-graph', complete=True, references=[],
               pins=[], leases=[], ownership={})


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        fixture = json.loads((Path(__file__).parent/'fixtures/runtime_coverage/conformance.json').read_text())['connectors']
        self.binding = fixture['RunBinding']
        self.caps = fixture['AdapterCapabilities']
        self.caps['capabilities']['input'] = True
        self.configuration = dict(caps=self.caps, binary_sha256=self.binding['emulator']['sha256'])
        self.raw = b'an invented build, not a ROM'
        self.binding['artifacts'] = {'rom': hashlib.sha256(self.raw).hexdigest()}
        self.cases = []
        self.scenes = []
        self.exercises = {}
        for index in range(2):
            case = copy.deepcopy(fixture['CaseSpec'])
            case.update(case_id='invented-case-'+str(index), page=index, variant_id='invented-min' if index==0 else 'invented-max')
            self.cases.append(case)
            scene = dict(schema_version=1, scene_id='invented-scene-'+str(index), case=case,
                reach_method='cold_boot_navigation', checkpoint=None, checkpoint_binding=None,
                regenerate_from=None, steps=[], arrival_assertions=[dict(kind='region_hash',
                    label='invented-arrival', rect=[0,0,1,1], sha256=hashlib.sha256(b'\x03\x07\x0b').hexdigest())],
                limits=dict(frames=20, seconds=10, attempts=1))
            self.scenes.append(scene)
            self.exercises[case['case_id']] = dict(scene_id=scene['scene_id'],
                steps=[dict(frames=1, buttons=[], capture=True)])
        self.artifacts = RuntimeArtifacts(self.root/'blobs', budget_bytes=1024*1024, graph_guard=invented_graph)
        ref = reference(self.raw, evidence_id='invented-build', media_type='application/octet-stream',
            provenance=dict(producer='invented-fixture', method='synthetic', run_id=None, case_id=None))
        self.build_refs = {'rom': self.artifacts.register(ref, self.raw)}
        self.bounds = dict(startup_seconds=5, case_seconds=2, shutdown_seconds=0.2,
                          total_seconds=20, worker_cases=2)

    def run_sweep(self, name='run', **kwargs):
        self.binding['configuration_sha256'] = digest(self.configuration)
        inventory = case_inventory(self.cases, scope=self.cases[0]['coverage_scope'], source='invented explicit inventory')
        return run_sweep(inventory, SceneLibrary(self.scenes), self.exercises, self.binding,
            self.caps, self.artifacts, self.build_refs, self.configuration,
            kwargs.pop('adapter_factory', invented_factory), self.root/name,
            limits=kwargs.pop('limits', self.bounds), **kwargs)

    def fail_first(self, action):
        self.configuration['action'] = action
        self.exercises[self.cases[0]['case_id']]['steps'] = [dict(frames=1, buttons=[], capture=True),
                                                          dict(frames=1, buttons=['B'], capture=True)]

    @staticmethod
    def io_failure(winerror=None):
        error = PermissionError(errno.EACCES, 'invented private path and detail', 'invented-secret.json')
        if winerror is not None:
            error.winerror = winerror
        return error

    def test_journal_known_sharing_recovers_same_sequence_and_frame_counts(self):
        original = sweep._read_journal_bytes
        attempts = []
        injected = set()
        def read(path):
            attempts.append((path.parent.name, path.name))
            if path.name in ('1.json', '3.json') and path.name not in injected:
                injected.add(path.name)
                raise self.io_failure(32 if path.name == '1.json' else 33)
            return original(path)
        with mock.patch.object(sweep, '_read_journal_bytes', side_effect=read):
            result = self.run_sweep()
        self.assertTrue(result['capture_complete'])
        self.assertEqual(result['observed_frames'], 4)
        self.assertEqual(result['workers'][0]['journal_io']['retry_count'], 2)
        self.assertEqual(result['workers'][0]['journal_io']['recovered_events'], 2)
        self.assertIsNone(result['workers'][0]['journal_io']['pending_sequence'])
        for name in ('1.json', '3.json'):
            positions = [i for i, (_, item) in enumerate(attempts) if item == name]
            self.assertEqual(len(positions), 2)
            self.assertEqual(positions[1], positions[0]+1)

    def test_journal_access_denied_and_unclassified_eacces_fail_without_retry(self):
        self.cases = self.cases[:1]
        self.exercises = {self.cases[0]['case_id']: self.exercises[self.cases[0]['case_id']]}
        for code in (5, None):
            with self.subTest(winerror=code), mock.patch.object(sweep, '_read_journal_bytes',
                    side_effect=self.io_failure(code)) as read:
                result = self.run_sweep(name='denied-'+str(code))
            self.assertFalse(result['capture_complete'])
            self.assertEqual(read.call_count, 1)
            worker = result['workers'][0]
            detail = worker['io_error']
            self.assertEqual(detail['phase'], 'journal_read')
            self.assertEqual(detail['sequence'], 1)
            self.assertEqual(detail['errno'], errno.EACCES)
            self.assertEqual(detail['winerror'], code)
            self.assertFalse(detail['transient_sharing'])
            self.assertEqual(worker['journal_io']['retry_count'], 0)
            self.assertEqual(worker['shutdown']['final_state'], 'stopped')
            self.assertNotIn('invented-secret', json.dumps(result))
            self.assertNotIn('invented private path', json.dumps(result))

    def test_journal_retry_limit_fails_without_acknowledging_or_advancing(self):
        self.cases = self.cases[:1]
        self.exercises = {self.cases[0]['case_id']: self.exercises[self.cases[0]['case_id']]}
        with mock.patch.object(sweep, 'JOURNAL_RETRY_LIMIT', 3), \
             mock.patch.object(sweep, '_read_journal_bytes', side_effect=self.io_failure(32)) as read:
            result = self.run_sweep()
        worker = result['workers'][0]
        self.assertEqual(read.call_count, 4)
        self.assertEqual(worker['journal_io']['retry_count'], 3)
        self.assertTrue(worker['journal_io']['retry_exhausted'])
        self.assertEqual(worker['io_error']['sequence'], 1)
        self.assertEqual(result['observed_frames'], 0)
        self.assertFalse(list((self.root/'run').rglob('*.ack')))
        self.assertFalse(result['capture_complete'])

    def test_journal_contention_respects_case_deadline_and_cancellation(self):
        original = sweep._read_journal_bytes
        for mode in ('deadline', 'cancel'):
            blocked = []
            def read(path):
                if path.name == '3.json':
                    blocked.append(path.name)
                    raise self.io_failure(33)
                return original(path)
            bounds = dict(self.bounds, case_seconds=0.15, total_seconds=3)
            started = time.monotonic()
            with mock.patch.object(sweep, '_read_journal_bytes', side_effect=read):
                result = self.run_sweep(name=mode, limits=bounds,
                    cancelled=(lambda: bool(blocked)) if mode == 'cancel' else None)
            self.assertLess(time.monotonic()-started, 4)
            worker = result['workers'][0]
            self.assertEqual(worker['outcome'], 'interrupted')
            self.assertEqual(worker['reason'], 'Case timeout' if mode == 'deadline' else 'Cancelled by caller')
            self.assertEqual(worker['journal_io']['pending_sequence'], 3)
            self.assertEqual(worker['journal_io']['recovered_events'], 0)
            self.assertFalse(worker['journal_io']['retry_exhausted'])
            self.assertEqual(result['observed_frames'], 0)
            self.assertEqual(worker['shutdown']['final_state'], 'stopped')
            self.assertFalse(result['capture_complete'])

    def test_worker_done_contention_recovers_even_after_process_exit(self):
        original = sweep._read_journal_bytes
        blocked = []
        def read(path):
            raw = original(path)
            if json.loads(raw).get('kind') == 'worker_done' and not blocked:
                blocked.append(path.name)
                time.sleep(0.05)  # Invented worker may exit before the next poll.
                raise self.io_failure(32)
            return raw
        with mock.patch.object(sweep, '_read_journal_bytes', side_effect=read):
            result = self.run_sweep(limits=dict(self.bounds, shutdown_seconds=0.5))
        self.assertTrue(result['capture_complete'])
        self.assertTrue(result['workers'][0]['clean_exit'])
        self.assertEqual(result['workers'][0]['journal_io']['recovered_events'], 1)

    def journal_deadline_fixture(self, mode, *, publish):
        # A synchronous invented producer removes Windows spawn/import timing
        # from this deadline witness. Real worker lifecycle tests remain separate.
        self.cases = self.cases[:1]
        self.scenes = self.scenes[:1]
        self.exercises = {self.cases[0]['case_id']: self.exercises[self.cases[0]['case_id']]}
        elapsed = [0.0]
        process = mock.Mock()
        process.is_alive.return_value = True
        process.exitcode = None
        def terminate():
            process.is_alive.return_value = False
            process.exitcode = -15
        process.terminate.side_effect = terminate
        def make_process(*, target, args):
            def start():
                if publish:
                    (Path(args[-1])/'1.json').write_text('{"kind":"worker_ready"}', encoding='utf8')
            process.start.side_effect = start
            return process
        def advance(seconds):
            elapsed[0] += seconds
            self.assertLessEqual(elapsed[0], 3, 'Invented poll loop exceeded its hard test bound')
        bounds = dict(self.bounds, startup_seconds=0.3 if mode == 'startup' else 3,
                      total_seconds=3 if mode == 'startup' else 0.3)
        with mock.patch.object(sweep.multiprocessing, 'get_context') as spawn, \
             mock.patch.object(sweep, 'time') as clock, \
             mock.patch.object(sweep, '_read_journal_bytes', side_effect=self.io_failure(32)) as read:
            spawn.return_value.Process.side_effect = make_process
            clock.monotonic.side_effect = lambda: elapsed[0]
            clock.sleep.side_effect = advance
            result = self.run_sweep(name=mode, limits=bounds)
        spawn.assert_called_once_with('spawn')
        process.start.assert_called_once_with()
        self.assertEqual(result['workers'][0]['shutdown']['final_state'], 'stopped')
        self.assertAlmostEqual(result['elapsed_seconds'], 0.3)
        return result, read

    def test_journal_contention_does_not_extend_startup_or_whole_run_deadline(self):
        for mode in ('startup', 'whole-run'):
            with self.subTest(mode=mode):
                result, read = self.journal_deadline_fixture(mode, publish=True)
                self.assertGreater(read.call_count, 1)  # Sharing-error retry was actually exercised.
                worker = result['workers'][0]
                self.assertEqual(worker['outcome'], 'interrupted')
                self.assertIn('timeout' if mode == 'startup' else 'elapsed', worker['reason'].lower())
                self.assertFalse(result['capture_complete'])
                self.assertEqual(result['observed_frames'], 0)
                self.assertEqual(worker['journal_io']['pending_sequence'], 1)
                self.assertEqual(worker['journal_io']['retry_count'], read.call_count)
                self.assertFalse(worker['journal_io']['retry_exhausted'])

    def test_missing_journal_event_times_out_without_inventing_contention(self):
        for mode in ('startup', 'whole-run'):
            with self.subTest(mode=mode):
                result, read = self.journal_deadline_fixture(mode, publish=False)
                read.assert_not_called()
                worker = result['workers'][0]
                self.assertEqual(worker['outcome'], 'interrupted')
                self.assertIn('timeout' if mode == 'startup' else 'elapsed', worker['reason'].lower())
                self.assertFalse(result['capture_complete'])
                self.assertEqual(result['observed_frames'], 0)
                self.assertIsNone(worker['journal_io']['pending_sequence'])
                self.assertEqual(worker['journal_io']['retry_count'], 0)
                self.assertIsNone(worker['journal_io']['first_error'])

    def test_successful_read_returning_after_deadline_or_cancel_is_not_accepted(self):
        self.cases = self.cases[:1]
        self.exercises = {self.cases[0]['case_id']: self.exercises[self.cases[0]['case_id']]}
        original = sweep._read_journal_bytes
        for mode in ('startup', 'case', 'whole-run', 'cancel', 'worker_done'):
            with self.subTest(mode=mode):
                returned = []
                elapsed = [0]
                monotonic = time.monotonic
                def read(path):
                    raw = original(path)
                    kind = json.loads(raw)['kind']
                    target = ('worker_done' if mode == 'worker_done' else
                              'progress' if mode == 'case' else 'worker_ready')
                    if kind == target:
                        returned.append(kind)
                        # Advance only the invented parent's clock after a real
                        # read; do not race subprocess startup against tiny limits.
                        if mode != 'cancel': elapsed[0] = 100 if mode == 'whole-run' else 10
                    return raw
                bounds = dict(self.bounds, startup_seconds=5, case_seconds=5,
                    total_seconds=60, shutdown_seconds=0.5)
                with mock.patch.object(sweep, '_read_journal_bytes', side_effect=read), \
                     mock.patch.object(sweep.time, 'monotonic', side_effect=lambda: monotonic()+elapsed[0]):
                    result = self.run_sweep(name=mode, limits=bounds,
                        cancelled=(lambda: bool(returned)) if mode == 'cancel' else None)
                worker = result['workers'][0]
                self.assertTrue(returned)
                self.assertEqual(worker['outcome'], 'interrupted')
                self.assertFalse(worker['worker_done_observed'])
                self.assertFalse(worker['clean_exit'])
                self.assertFalse(result['capture_complete'])
                if mode != 'worker_done':
                    self.assertEqual(result['observed_frames'], 0)
                    self.assertFalse(list((self.root/mode).rglob('*.ack')))

    def test_malformed_journal_is_never_retried_or_acknowledged(self):
        self.cases = self.cases[:1]
        self.exercises = {self.cases[0]['case_id']: self.exercises[self.cases[0]['case_id']]}
        original = sweep._read_journal_bytes
        with mock.patch.object(sweep, '_read_journal_bytes',
                side_effect=lambda path: b'!'*len(original(path))) as read:
            result = self.run_sweep()
        self.assertFalse(result['capture_complete'])
        self.assertEqual(read.call_count, 1)
        self.assertEqual(result['workers'][0]['journal_io']['retry_count'], 0)
        self.assertIn('JSONDecodeError', result['workers'][0]['reason'])
        self.assertFalse(list((self.root/'run').rglob('*.ack')))

    def test_journal_lstat_contention_then_disappearance_is_fatal(self):
        path = self.root/'invented.json'
        path.write_bytes(b'{"kind":"invented"}')
        diagnostics = dict(first_error=None, last_error=None, fatal_error=None,
            retry_count=0, recovered_events=0, pending_sequence=None,
            pending_retries=0, retry_exhausted=False)
        with mock.patch.object(Path, 'lstat', side_effect=self.io_failure(33)):
            self.assertEqual(sweep._read_journal_event(path, 7, diagnostics), (None, True))
        self.assertEqual(diagnostics['last_error']['phase'], 'journal_lstat')
        self.assertEqual(diagnostics['pending_sequence'], 7)
        with mock.patch.object(Path, 'lstat', side_effect=FileNotFoundError(errno.ENOENT, 'invented')):
            with self.assertRaises(FileNotFoundError):
                sweep._read_journal_event(path, 7, diagnostics)
        self.assertEqual(diagnostics['fatal_error']['errno'], errno.ENOENT)
        self.assertFalse(diagnostics['fatal_error']['transient_sharing'])
        self.assertEqual(diagnostics['recovered_events'], 0)
        # The same missing name before any observed publication is just a poll.
        diagnostics['pending_sequence'] = None
        with mock.patch.object(Path, 'lstat', side_effect=FileNotFoundError):
            self.assertEqual(sweep._read_journal_event(path, 8, diagnostics), (None, False))

    def test_worker_publication_sharing_failure_is_not_retried_or_skipped(self):
        log = io.StringIO()
        with mock.patch.object(Path, 'rename', side_effect=self.io_failure(32)) as rename, \
             redirect_stdout(log), self.assertRaises(PermissionError):
            sweep._worker_main(invented_factory, self.configuration, {}, self.binding,
                self.caps, [], {}, sweep._limits(None), self.root)
        self.assertEqual(rename.call_count, 1)
        self.assertTrue((self.root/'1.pending').exists())
        self.assertFalse((self.root/'1.json').exists())
        detail = json.loads(log.getvalue())['detail']
        self.assertEqual(detail['phase'], 'journal_publish')
        self.assertEqual(detail['winerror'], 32)
        self.assertEqual(detail['sequence'], 1)
        self.assertNotIn('invented-secret', log.getvalue())

    def test_old_runner_versions_refuse_resume_before_resolution_or_output(self):
        result = self.run_sweep()
        self.assertEqual(result['runner_version'], '5')
        for version in ('1', '2', '3', '4'):
            prior = copy.deepcopy(result)
            prior['runner_version'] = version
            prior['definition']['runner_version'] = version
            prior['definition_sha256'] = digest(prior['definition'])
            path = self.root/('prior-'+version+'.json')
            path.write_text(json.dumps(prior))
            with mock.patch.object(self.artifacts, 'resolve') as resolve, \
                 mock.patch.object(self.artifacts, 'retained_build') as retained, \
                 mock.patch.object(sweep.multiprocessing, 'get_context') as spawn, \
                 self.assertRaises(ContractError):
                self.run_sweep(name='legacy-'+version, resume=path)
            resolve.assert_not_called(); retained.assert_not_called(); spawn.assert_not_called()
            self.assertFalse((self.root/('legacy-'+version)).exists())
            self.assertEqual(json.loads(path.read_text())['runner_version'], version)

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows file-sharing semantics')
    def test_windows_reader_preserves_actual_sharing_error_and_released_bytes(self):
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        path = self.root/'invented-held.json'
        raw = b'{"kind":"invented"}'
        path.write_bytes(raw)
        handle = kernel.CreateFileW(str(path), 0x80000000, 0, None, 3, 0x80, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            with self.assertRaises(OSError) as error:
                sweep._read_journal_bytes(path)
            self.assertEqual(error.exception.winerror, 32)
            self.assertTrue(sweep._io_detail(error.exception, 'journal_read', 1)['transient_sharing'])
        finally:
            self.assertTrue(kernel.CloseHandle(handle))
        self.assertEqual(sweep._read_journal_bytes(path), raw)

    @unittest.skipUnless(os.name == 'nt', 'Windows ctypes reader error boundaries')
    def test_windows_reader_closes_handles_and_preserves_primary_and_close_errors(self):
        import ctypes
        from types import SimpleNamespace
        scenarios = ('metadata', 'read', 'close', 'read-and-close', 'oversize',
                     'reparse', 'reparse-and-close', 'directory', 'nondisk', 'truncated', 'success')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                closes = []
                reads = []
                def create(*args): return 101
                def metadata(handle, information):
                    if scenario == 'metadata':
                        ctypes.set_last_error(5)
                        return 0
                    information._obj.size_low = 2*1024*1024+1 if scenario == 'oversize' else 3
                    information._obj.attributes = (0x400 if scenario.startswith('reparse') else
                                                   0x10 if scenario == 'directory' else 0x80)
                    return 1
                def kind(handle): return 3 if scenario == 'nondisk' else 1
                def read(handle, buffer, length, count, overlapped):
                    reads.append(length)
                    if scenario in ('read', 'read-and-close'):
                        ctypes.set_last_error(32)
                        return 0
                    raw = b'abc' if len(reads) == 1 and scenario != 'truncated' else b''
                    ctypes.memmove(buffer, raw, len(raw))
                    count._obj.value = len(raw)
                    return 1
                def close(handle):
                    closes.append(handle)
                    if scenario in ('close', 'read-and-close', 'reparse-and-close'):
                        ctypes.set_last_error(5)
                        return 0
                    return 1
                kernel = SimpleNamespace(CreateFileW=create, GetFileInformationByHandle=metadata,
                    GetFileType=kind, ReadFile=read, CloseHandle=close)
                with mock.patch.object(ctypes, 'WinDLL', return_value=kernel):
                    if scenario == 'success':
                        self.assertEqual(sweep._read_journal_bytes(self.root/'invented.json'), b'abc')
                    elif scenario in ('oversize', 'reparse', 'reparse-and-close', 'directory', 'nondisk', 'truncated'):
                        with self.assertRaises(ContractError) as error:
                            sweep._read_journal_bytes(self.root/'invented.json')
                        if scenario == 'reparse-and-close':
                            self.assertEqual(sweep._io_detail(error.exception, 'journal_read', 1)
                                             ['close_error']['winerror'], 5)
                            path = self.root/'invented.json'
                            path.write_bytes(b'abc')
                            diagnostics = dict(first_error=None, last_error=None, fatal_error=None,
                                retry_count=0, recovered_events=0, pending_sequence=None,
                                pending_retries=0, retry_exhausted=False)
                            with self.assertRaises(ContractError):
                                sweep._read_journal_event(path, 1, diagnostics)
                            self.assertEqual(diagnostics['fatal_error']['close_error']['winerror'], 5)
                    else:
                        with self.assertRaises(OSError) as error:
                            sweep._read_journal_bytes(self.root/'invented.json')
                        detail = sweep._io_detail(error.exception, 'journal_read', 9)
                        self.assertEqual(detail['winerror'], 32 if scenario.startswith('read') else 5)
                        self.assertEqual(detail['operation'], 'ReadFile' if scenario.startswith('read') else
                                         'CloseHandle' if scenario == 'close' else 'GetFileInformationByHandle')
                        if scenario == 'read-and-close':
                            self.assertEqual(detail['close_error']['winerror'], 5)
                            self.assertFalse(detail['transient_sharing'])
                self.assertEqual(closes, [101, 101] if scenario == 'reparse-and-close' else [101])
                if scenario in ('oversize', 'reparse', 'reparse-and-close', 'directory', 'nondisk', 'metadata'):
                    self.assertEqual(reads, [])

    def test_fresh_case_reset_amortizes_worker_and_never_awards_detector_pass(self):
        manifest = self.run_sweep()
        self.assertTrue(manifest['capture_complete'])
        self.assertEqual(len(manifest['workers']), 1)
        self.assertEqual(len(list((self.root/'run/worker-1').glob('session-*/reset-proof.txt'))), 2)
        for case, observation in zip(self.cases, manifest['observations']):
            self.assertEqual(observation['execution'], 'completed')
            self.assertEqual(observation['assertion'], 'not_assessed')
            self.assertEqual(observation['method'], 'synthetic')
            self.assertEqual(observation['frames'], 2)
            self.assertEqual(observation['case_sha256'], contract_digest('CaseSpec', case))
            self.assertEqual(observation['glyphs'], None)
            self.assertEqual(observation['controls'], {})
            self.assertEqual(check_observation(case, observation, self.caps), observation)
            for capture in observation['captures']:
                self.assertTrue(self.artifacts.resolve(capture['evidence'])['available'])
        self.assertEqual(manifest['planned'], manifest['completed'])
        self.assertEqual(json.loads((self.root/'run/manifest.json').read_text()), manifest)

    def test_storage_preflight_distinct_and_explicit_shared_ceilings(self):
        bounds = dict(self.bounds, workspace_bytes=2*1024*1024)
        allowance = dict(retained_bytes=1024*1024, workspace_bytes=2*1024*1024)
        result = storage_preflight(self.artifacts, limits=bounds, allowance=allowance)
        self.assertEqual(result['summed_ceiling_bytes'], 3*1024*1024)
        self.assertIsNone(result['allowance']['shared_bytes'])
        self.assertNotIn('shared_bytes', allowance)
        with self.assertRaises(ContractError):
            storage_preflight(self.artifacts, limits=bounds,
                              allowance=dict(allowance, shared_bytes=2*1024*1024))
        result = storage_preflight(self.artifacts, limits=bounds,
                                   allowance=dict(allowance, shared_bytes=3*1024*1024))
        self.assertEqual(result['retained_bytes'], self.artifacts.budget_bytes)
        manifest = self.run_sweep(limits=bounds, storage_allowance=result['allowance'])
        self.assertEqual(manifest['definition']['storage_policy'], result)

    def test_budget_refusal_never_resolves_writes_destination_or_starts_worker(self):
        bounds = dict(self.bounds, workspace_bytes=1024*1024)
        bad = [dict(retained_bytes=1024, workspace_bytes=1024*1024),
               dict(retained_bytes=1024*1024, workspace_bytes=1024),
               dict(retained_bytes=1024*1024, workspace_bytes=1024*1024, shared_bytes=1024*1024),
               dict(retained_bytes=True, workspace_bytes=1024*1024),
               dict(workspace_bytes=1024*1024),
               dict(retained_bytes=1024*1024, workspace_bytes=1024*1024, unexpected=1)]
        files = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        with mock.patch.object(self.artifacts, 'resolve', side_effect=AssertionError('must not resolve')) as resolve, \
             mock.patch.object(self.artifacts, 'retained_build', side_effect=AssertionError('must not read inputs')) as retained, \
             mock.patch('patchquest.runtime_sweep.multiprocessing.get_context') as spawn:
            for allowance in bad:
                with self.subTest(allowance=allowance), self.assertRaises(ContractError):
                    self.run_sweep(limits=bounds, storage_allowance=allowance)
            resolve.assert_not_called(); retained.assert_not_called(); spawn.assert_not_called()
        self.assertEqual(files, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        self.assertFalse((self.root/'run').exists())

    def test_storage_policy_changes_and_legacy_lifecycle_reject_resume(self):
        first = self.run_sweep()
        self.artifacts.budget_bytes += 1
        with self.assertRaises(ContractError):
            self.run_sweep(name='changed-budget', resume=self.root/'run/manifest.json')
        self.artifacts.budget_bytes -= 1
        legacy = copy.deepcopy(first); legacy['runner_version'] = '1'
        path = self.root/'legacy.json'; path.write_text(json.dumps(legacy))
        with self.assertRaises(ContractError):self.run_sweep(name='legacy', resume=path)
        self.assertFalse((self.root/'changed-budget').exists())
        self.assertFalse((self.root/'legacy').exists())

    def test_contradictory_shutdown_cannot_inherit_resume_completion(self):
        first = self.run_sweep()
        first['workers'][0]['shutdown']['exitcode'] = 23
        # A stale clean_exit/outcome flag cannot override the actual exit fields.
        path = self.root/'contradictory.json'; path.write_text(json.dumps(first))
        second = self.run_sweep(name='resume', resume=path)
        self.assertTrue(second['workers']); self.assertTrue(second['capture_complete'])
        self.assertTrue({o['observation_id'] for o in first['observations']}.isdisjoint(
            {o['observation_id'] for o in second['observations']}))

    def test_normal_worker_gets_grace_and_records_parent_lifecycle(self):
        self.configuration['exit_linger'] = 0.15
        manifest = self.run_sweep(limits=dict(self.bounds, shutdown_seconds=1))
        self.assertTrue(manifest['capture_complete'])
        worker = manifest['workers'][0]
        self.assertTrue(worker['worker_done_observed']); self.assertTrue(worker['clean_exit'])
        startup, shutdown = worker['startup'], worker['shutdown']
        self.assertLessEqual(startup['start_requested_monotonic'], startup['start_returned_monotonic'])
        self.assertLessEqual(startup['start_returned_monotonic'], startup['ready_observed_monotonic'])
        self.assertGreater(startup['elapsed_seconds'], 0)
        self.assertGreaterEqual(shutdown['elapsed_seconds'], shutdown['control_elapsed_seconds'])
        self.assertEqual(shutdown['final_state'], 'stopped'); self.assertEqual(shutdown['exitcode'], 0)
        self.assertFalse(shutdown['terminate_requested']); self.assertFalse(shutdown['kill_requested'])
        self.assertEqual(shutdown['errors'], [])

    def test_worker_done_followed_by_hung_exit_is_incomplete_and_not_reused(self):
        self.configuration['exit_linger'] = 30
        manifest = self.run_sweep()
        worker = manifest['workers'][0]
        self.assertTrue(worker['worker_done_observed']); self.assertFalse(worker['clean_exit'])
        self.assertEqual(worker['outcome'], 'interrupted')
        self.assertTrue(worker['shutdown']['terminate_requested'])
        self.assertEqual(worker['shutdown']['final_state'], 'stopped')
        self.assertIsNotNone(worker['shutdown']['exitcode'])
        self.assertTrue(worker['invalidates_completed']); self.assertFalse(manifest['capture_complete'])
        resumed = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertEqual(len(resumed['workers']), 1); self.assertFalse(resumed['capture_complete'])
        self.assertTrue({o['observation_id'] for o in manifest['observations']}.isdisjoint(
            {o['observation_id'] for o in resumed['observations']}))

    def test_worker_done_followed_by_nonzero_exit_cannot_claim_clean_completion(self):
        self.configuration['exit_crash'] = True
        manifest = self.run_sweep()
        worker = manifest['workers'][0]
        self.assertTrue(worker['worker_done_observed']); self.assertFalse(worker['clean_exit'])
        self.assertEqual(worker['shutdown']['exitcode'], 23)
        self.assertEqual(worker['shutdown']['final_state'], 'stopped')
        self.assertFalse(worker['shutdown']['terminate_requested'])
        self.assertEqual(worker['outcome'], 'failed'); self.assertFalse(manifest['capture_complete'])

    def test_unconfirmed_stop_is_recorded_and_blocks_new_workers(self):
        # An unkillable host process is modelled without leaking a real child.
        class Unconfirmed:
            def join(self, seconds):pass
            def is_alive(self):return True
            def terminate(self):raise OSError('invented host failure')
            def kill(self):raise OSError('invented host failure')
        result = _stop(Unconfirmed(), 0.01)
        self.assertEqual(result['final_state'], 'unknown')
        self.assertTrue(result['terminate_requested']); self.assertTrue(result['kill_requested'])
        self.assertIsNone(result['exitcode']); self.assertEqual(result['errors'], ['OSError', 'OSError'])
        from patchquest import runtime_sweep
        real_stop = runtime_sweep._stop
        def uncertain(process, seconds, **kwargs):
            # Really stop our invented worker, then model inability to attest it.
            stopped = real_stop(process, seconds, **kwargs)
            stopped.update(final_state='unknown', exitcode=None)
            return stopped
        self.bounds['worker_cases'] = 1
        with mock.patch.object(runtime_sweep, '_stop', side_effect=uncertain):manifest = self.run_sweep()
        self.assertEqual(len(manifest['workers']), 1)
        self.assertFalse(manifest['capture_complete']); self.assertEqual(len(manifest['not_run']), 1)
        before = (self.root/'run/manifest.json').read_bytes()
        with mock.patch.object(self.artifacts, 'resolve', side_effect=AssertionError('must not resolve')) as resolve, \
             mock.patch.object(self.artifacts, 'retained_build', side_effect=AssertionError('must not resolve inputs')) as retained, \
             mock.patch('patchquest.runtime_sweep.multiprocessing.get_context') as spawn:
            with self.assertRaisesRegex(ContractError, 'confirmed stopped state'):
                self.run_sweep(name='unknown-resume', resume=self.root/'run/manifest.json')
            resolve.assert_not_called(); retained.assert_not_called(); spawn.assert_not_called()
        self.assertFalse((self.root/'unknown-resume').exists())
        self.assertEqual((self.root/'run/manifest.json').read_bytes(), before)

    def test_missing_shutdown_confirmation_refuses_resume_before_resolution(self):
        first = self.run_sweep()
        for missing in ('shutdown', 'final_state'):
            prior = copy.deepcopy(first)
            if missing == 'shutdown':prior['workers'][0].pop('shutdown')
            else:prior['workers'][0]['shutdown'].pop('final_state')
            path = self.root/('missing-'+missing+'.json');path.write_text(json.dumps(prior))
            with mock.patch.object(self.artifacts, 'resolve', side_effect=AssertionError('must not resolve')) as resolve, \
                 mock.patch.object(self.artifacts, 'retained_build', side_effect=AssertionError('must not resolve inputs')) as retained, \
                 mock.patch('patchquest.runtime_sweep.multiprocessing.get_context') as spawn:
                with self.assertRaisesRegex(ContractError, 'confirmed stopped state'):
                    self.run_sweep(name='missing-resume', resume=path)
                resolve.assert_not_called(); retained.assert_not_called(); spawn.assert_not_called()
            self.assertFalse((self.root/'missing-resume').exists())

    def test_kill_escalation_retains_request_and_final_exit_observations(self):
        class NeedsKill:
            alive = True
            exitcode = None
            def join(self, seconds):pass
            def is_alive(self):return self.alive
            def terminate(self):pass
            def kill(self):self.alive=False;self.exitcode=-9
            def close(self):pass
        result = _stop(NeedsKill(), 0.01)
        self.assertTrue(result['terminate_requested']); self.assertTrue(result['kill_requested'])
        self.assertEqual(result['final_state'], 'stopped'); self.assertEqual(result['exitcode'], -9)
        self.assertGreaterEqual(result['elapsed_seconds'], 0); self.assertEqual(result['errors'], [])

    def test_native_crash_retains_partial_capture_and_recovers_in_new_worker(self):
        self.fail_first('crash')
        manifest = self.run_sweep()
        first, second = manifest['observations']
        self.assertEqual(first['execution'], 'failed'); self.assertTrue(first['captures'])
        self.assertEqual(second['execution'], 'completed')
        self.assertEqual(len(manifest['workers']), 2)
        self.assertFalse(manifest['capture_complete'])
        self.assertEqual(manifest['workers'][0]['shutdown']['exitcode'], 9)
        self.assertEqual(manifest['workers'][0]['shutdown']['final_state'], 'stopped')
        self.assertFalse(manifest['workers'][0]['clean_exit'])

    def test_hung_step_is_terminated_and_remaining_case_runs_fresh(self):
        self.fail_first('hang'); self.bounds['case_seconds'] = 0.35
        started = time.monotonic(); manifest = self.run_sweep()
        self.assertLess(time.monotonic()-started, 8)
        first, second = manifest['observations']
        self.assertEqual(first['execution'], 'interrupted'); self.assertTrue(first['captures'])
        self.assertEqual(second['execution'], 'completed')
        self.assertFalse(multiprocessing.active_children())

    def test_cancellation_retains_acknowledged_partial_frames_and_pending_scope(self):
        self.fail_first('hang')
        manifest = self.run_sweep(cancelled=lambda: len(list((self.root/'blobs').glob('[0-9a-f]'*64))) >= 2)
        self.assertEqual(manifest['observations'][0]['execution'], 'interrupted')
        self.assertTrue(manifest['observations'][0]['captures'])
        self.assertEqual(manifest['observations'][1]['execution'], 'not_run')
        self.assertFalse(multiprocessing.active_children())

    def test_cancel_before_start_preserves_entire_planned_denominator(self):
        manifest = self.run_sweep(cancelled=lambda: True)
        self.assertEqual(manifest['not_run'], manifest['planned'])
        self.assertEqual(manifest['workers'], [])

    def test_exact_resume_reuses_only_completed_capture_and_keeps_old_failure(self):
        self.fail_first('error')
        first = self.run_sweep()
        second = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertEqual(second['observations'][1], first['observations'][1])
        self.assertNotEqual(second['observations'][0]['observation_id'], first['observations'][0]['observation_id'])
        self.assertIn(first['observations'][0], second['history'])
        self.assertEqual(len(second['workers']), 1)
        self.assertEqual(second['workers'][0]['outcome'], 'completed')

    def test_changed_build_configuration_case_and_limits_reject_resume(self):
        self.run_sweep()
        mutations = [lambda: self.binding.update(snapshot='a'*64),
            lambda: self.configuration.update(other=True), lambda: self.bounds.update(case_seconds=3)]
        for mutate in mutations:
            binding, config, bounds = copy.deepcopy(self.binding), copy.deepcopy(self.configuration), copy.deepcopy(self.bounds)
            mutate()
            with self.assertRaises(ContractError): self.run_sweep(name='rejected', resume=self.root/'run/manifest.json')
            self.binding, self.configuration, self.bounds = binding, config, bounds
        self.cases[0]['variant_id'] = 'different'; self.scenes[0]['case'] = self.cases[0]
        with self.assertRaises(ContractError): self.run_sweep(name='rejected', resume=self.root/'run/manifest.json')
        self.assertFalse((self.root/'rejected').exists())

    def test_changed_capture_bytes_cannot_inherit_completed_resume(self):
        first = self.run_sweep()
        ref = first['observations'][0]['captures'][0]['evidence']
        (self.root/'blobs'/ref['sha256']).write_bytes(b'corrupt invented bytes')
        second = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertFalse(second['capture_complete'])
        self.assertTrue(all(o['observation_id'] not in {p['observation_id'] for p in first['observations']}
                            for o in second['observations']))
        self.assertIn(first['observations'][0], second['history'])

    def test_optional_instrumentation_is_preserved_and_capability_checked(self):
        self.configuration['instrumentation'] = True
        self.caps['capabilities'].update(observe_glyphs=True, observe_resources=True, page_advance=True, native_scroll=True)
        manifest = self.run_sweep()
        for observation in manifest['observations']:
            self.assertTrue(observation['glyphs']); self.assertTrue(observation['resources'])
            self.assertTrue(observation['controls']['scrolled'])
        self.assertTrue(manifest['capture_complete'])

    def test_unavailable_instrumentation_does_not_turn_into_success(self):
        self.configuration['bad_telemetry'] = True
        manifest = self.run_sweep()
        self.assertEqual(len(manifest['failed']), 2)
        self.assertFalse(manifest['capture_complete'])
        self.assertTrue(all(o['captures'] for o in manifest['observations']))
        self.assertTrue(all(not o['controls'] for o in manifest['observations']))

    def test_configuration_and_provenance_drift_reject_before_capture(self):
        for key, value in [('configuration_drift', True), ('reported_provenance', 'actual_emulator')]:
            self.configuration[key] = value
            manifest = self.run_sweep(name=key)
            self.assertEqual(len(manifest['failed']), 2)
            self.assertTrue(all(o['frames']==0 for o in manifest['observations']))
            del self.configuration[key]

    def test_missing_required_capability_is_unsupported_and_visible(self):
        self.caps['capabilities']['capture_frames'] = False
        manifest = self.run_sweep()
        self.assertEqual(manifest['unsupported'], manifest['planned'])
        self.assertTrue(all(o['frames']==0 and not o['captures'] for o in manifest['observations']))

    def test_artifact_budget_retains_prior_captures_and_never_evicts(self):
        png = Frame(1,1,b'\x03\x07\x0b').png()
        self.artifacts.budget_bytes = len(self.raw)+len(png)
        manifest = self.run_sweep()
        self.assertFalse(manifest['capture_complete'])
        self.assertTrue(manifest['interrupted'])
        self.assertTrue(manifest['observations'][0]['captures'])
        self.assertEqual((self.root/'blobs'/hashlib.sha256(self.raw).hexdigest()).read_bytes(), self.raw)

    def test_frame_limit_allows_exact_boundary_and_rejects_next_case(self):
        self.bounds['total_frames'] = 2
        manifest = self.run_sweep()
        self.assertEqual(manifest['observations'][0]['execution'], 'completed')
        self.assertEqual(manifest['observed_frames'], 2)
        self.assertEqual(manifest['observations'][1]['execution'], 'interrupted')
        self.assertFalse(manifest['capture_complete'])

    def test_close_failure_does_not_certify_complete_worker_lifetime(self):
        self.configuration['close_error'] = True
        manifest = self.run_sweep()
        self.assertEqual(len(manifest['completed']), 2)
        self.assertEqual(manifest['workers'][0]['outcome'], 'failed')
        self.assertFalse(manifest['capture_complete'])
        self.assertIn('invented close error', (self.root/'run/worker-1/worker.log').read_text())
        resumed = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertTrue(resumed['workers'])
        self.assertFalse(resumed['capture_complete'])
        self.assertNotEqual(resumed['observations'][0]['observation_id'], manifest['observations'][0]['observation_id'])

    def test_hung_factory_and_hung_close_have_hard_process_deadlines(self):
        for mode in ('factory_hang', 'close_hang'):
            self.configuration[mode] = True
            bounds = dict(self.bounds, startup_seconds=0.35, worker_cases=2)
            started = time.monotonic()
            manifest = self.run_sweep(name=mode, limits=bounds)
            self.assertLess(time.monotonic()-started, 8)
            self.assertFalse(manifest['capture_complete'])
            self.assertTrue(all(w['outcome']=='interrupted' for w in manifest['workers']))
            self.assertFalse(multiprocessing.active_children())
            del self.configuration[mode]

    def test_managed_workspace_budget_is_bounded_without_cleaning_old_journals(self):
        bounds = dict(self.bounds, workspace_bytes=1200)
        manifest = self.run_sweep(limits=bounds)
        self.assertFalse(manifest['capture_complete'])
        self.assertLessEqual(manifest['managed_workspace_bytes'], 1200)
        self.assertTrue(list((self.root/'run').glob('worker-*/*.json')))

    def test_explicit_selection_keeps_deferred_cases_visible(self):
        self.binding['configuration_sha256'] = digest(self.configuration)
        plan = dict(schema_version=1, kind='ChangeImpactPlan', plan_id='invented-selection',
            binding=self.binding, baseline_binding=self.binding,
            case_ids=[c['case_id'] for c in self.cases], dependency_revisions={'invented': '1'},
            selected=[dict(case_id=self.cases[0]['case_id'], reason='invented impact')],
            deferred=[dict(case_id=self.cases[1]['case_id'], reason='invented unchanged dependency')],
            full_sweep_required=False, additional_checks=[])
        manifest = self.run_sweep(selection_plan=plan)
        self.assertEqual(manifest['completed'], [self.cases[0]['case_id']])
        self.assertEqual(manifest['excluded'], [self.cases[1]['case_id']])
        self.assertEqual(len(manifest['planned']), 2)
        self.assertFalse(manifest['capture_complete'])

    def test_fully_completed_resume_starts_no_worker(self):
        first = self.run_sweep()
        second = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        self.assertEqual(second['observations'], first['observations'])
        self.assertEqual(second['workers'], [])
        self.assertTrue(second['capture_complete'])

    def test_full_repeated_resume_keeps_discoveries_without_fresh_enumeration(self):
        self.caps['capabilities']['enumerate_messages'] = True
        extra = copy.deepcopy(self.cases[0]); extra['case_id'] = 'invented-unplanned'
        self.configuration['enumerated_cases'] = self.cases + [extra]
        first = previous = self.run_sweep()
        self.assertEqual(len(first['gaps']), 1)
        self.assertEqual(first['gaps'][0]['case_id'], extra['case_id'])
        self.assertEqual(first['gaps'][0]['run_id'], first['run_id'])
        self.assertEqual(first['gaps'][0]['worker'], 'worker-1')
        self.assertTrue(first['workers'][0]['enumeration_observed'])
        self.assertEqual(first['enumeration_history'], [])
        original = (self.root/'run/manifest.json').read_bytes()
        sources = [dict(run_id=first['run_id'], manifest_sha256=hashlib.sha256(original).hexdigest(),
                        worker_ids=['worker-1'])]
        path = self.root/'run/manifest.json'
        for name in ('resume', 'again'):
            with mock.patch.object(sweep.multiprocessing, 'get_context') as spawn:
                result = self.run_sweep(name=name, resume=path)
            spawn.assert_not_called()
            self.assertEqual(result['workers'], [])
            self.assertEqual(result['inventories'], first['inventories'])
            self.assertEqual(result['gaps'], first['gaps'])
            self.assertEqual(result['enumeration_history'], sources)
            self.assertEqual(result['history'], previous['history'] + previous['observations'])
            self.assertEqual(result['observations'], first['observations'])
            self.assertEqual(result['planned'], first['planned'])
            self.assertNotIn(extra['case_id'], result['planned'])
            self.assertEqual(result['observed_frames'], 0)
            self.assertTrue(result['capture_complete'])
            self.assertEqual(result['inventories'][0]['completeness'], 'unknown')
            previous, path = result, self.root/name/'manifest.json'
        self.assertEqual((self.root/'run/manifest.json').read_bytes(), original)

    def test_partial_repeated_resume_distinguishes_original_and_new_worker_one(self):
        self.fail_first('error')
        self.bounds['worker_cases'] = 1
        self.caps['capabilities']['enumerate_messages'] = True
        extra = copy.deepcopy(self.cases[0]); extra['case_id'] = 'invented-unplanned'
        self.configuration['enumerated_cases'] = self.cases + [extra]
        first = previous = self.run_sweep()
        self.assertEqual(first['failed'], [self.cases[0]['case_id']])
        self.assertEqual(first['completed'], [self.cases[1]['case_id']])
        path = self.root/'run/manifest.json'
        originals = {path: path.read_bytes()}
        sources = []
        run_ids = [first['run_id'], first['run_id']]
        for name in ('resume', 'again'):
            sources.append(dict(run_id=previous['run_id'],
                manifest_sha256=hashlib.sha256(originals[path]).hexdigest(),
                worker_ids=[w['id'] for w in previous['workers']]))
            result = self.run_sweep(name=name, resume=path)
            run_ids.append(result['run_id'])
            self.assertEqual([i['run_id'] for i in result['inventories']], run_ids)
            self.assertEqual([g['run_id'] for g in result['gaps']], run_ids)
            self.assertEqual([i['worker'] for i in result['inventories']],
                             ['worker-1', 'worker-2'] + ['worker-1'] * (len(run_ids)-2))
            self.assertEqual(result['inventories'][:-1], previous['inventories'])
            self.assertEqual(result['gaps'][:-1], previous['gaps'])
            self.assertEqual(result['enumeration_history'], sources)
            self.assertEqual(result['history'], previous['history'] + previous['observations'])
            self.assertEqual(result['observations'][1], first['observations'][1])
            self.assertNotEqual(result['observations'][0]['observation_id'],
                                previous['observations'][0]['observation_id'])
            self.assertEqual(result['planned'], first['planned'])
            self.assertEqual(result['observed_frames'], first['observations'][0]['frames'])
            self.assertEqual(len(result['workers']), 1)
            self.assertFalse(result['capture_complete'])
            previous, path = result, self.root/name/'manifest.json'
            originals[path] = path.read_bytes()
        for source, raw in originals.items():
            self.assertEqual(source.read_bytes(), raw)

    def test_resumed_empty_and_changed_enumerations_retain_all_gap_kinds(self):
        self.caps['capabilities']['enumerate_messages'] = True
        changed = copy.deepcopy(self.cases[0]); changed['variant_id'] = 'invented-changed'
        for label, cases in [('empty', []), ('changed', [changed, self.cases[1]])]:
            with self.subTest(enumeration=label):
                self.configuration['enumerated_cases'] = cases
                first = self.run_sweep(name=label)
                second = self.run_sweep(name=label+'-resume', resume=self.root/label/'manifest.json')
                self.assertEqual(second['inventories'][:1], first['inventories'])
                self.assertEqual(second['gaps'][:len(first['gaps'])], first['gaps'])
                self.assertEqual(len(second['gaps']), 2 * len(first['gaps']))
                self.assertTrue(all(g['kind'] == 'absent_or_changed' for g in second['gaps']))
                self.assertEqual(first['gaps'][0]['declared_sha256'], contract_digest('CaseSpec', self.cases[0]))
                expected = None if not cases else contract_digest('CaseSpec', changed)
                self.assertEqual(first['gaps'][0]['enumerated_sha256'], expected)
                self.assertFalse(second['capture_complete'])

    def test_malformed_resume_discovery_ledger_refuses_before_artifacts_or_output(self):
        self.caps['capabilities']['enumerate_messages'] = True
        extra = copy.deepcopy(self.cases[0]); extra['case_id'] = 'invented-unplanned'
        self.configuration['enumerated_cases'] = self.cases + [extra]
        first = self.run_sweep()
        second = self.run_sweep(name='resume', resume=self.root/'run/manifest.json')
        mutations = {
            'missing-list': lambda p: p.pop('inventories'),
            'invalid-list': lambda p: p.update(gaps={}),
            'invalid-history': lambda p: p.update(history={}),
            'unknown-run': lambda p: p['inventories'][0].update(run_id='invented-unknown'),
            'unknown-worker': lambda p: p['inventories'][0].update(worker='worker-999'),
            'duplicate-enumeration': lambda p: p['inventories'].append(copy.deepcopy(p['inventories'][0])),
            'missing-enumeration': lambda p: p['inventories'].clear(),
            'changed-source': lambda p: p['inventories'][0].update(source='invented different source'),
            'changed-completeness': lambda p: p['inventories'][0].update(completeness='declared_complete'),
            'changed-case': lambda p: p['inventories'][0]['cases'][-1].update(variant_id='invented-other'),
            'missing-gap': lambda p: p['gaps'].clear(),
            'duplicate-gap': lambda p: p['gaps'].append(copy.deepcopy(p['gaps'][0])),
            'wrong-gap-digest': lambda p: p['gaps'][0].update(enumerated_sha256='0'*64),
            'wrong-gap-origin': lambda p: p['gaps'][0].update(worker='worker-999'),
        }
        current = {
            'missing-worker-event': lambda p: p['workers'][0].pop('enumeration_observed'),
            'cleared-worker-event': lambda p: p['workers'][0].update(enumeration_observed=False),
        }
        inherited = {
            'missing-history': lambda p: p.pop('enumeration_history'),
            'missing-origin': lambda p: p['enumeration_history'].clear(),
            'unknown-origin': lambda p: p['enumeration_history'][0].update(run_id='invented-unknown'),
            'unknown-origin-worker': lambda p: p['enumeration_history'][0].update(worker_ids=['worker-999']),
            'duplicate-origin': lambda p: p['enumeration_history'].append(copy.deepcopy(p['enumeration_history'][0])),
            'duplicate-origin-worker': lambda p: p['enumeration_history'][0]['worker_ids'].append('worker-1'),
            'invalid-manifest-digest': lambda p: p['enumeration_history'][0].update(manifest_sha256='unknown'),
            'mismatched-manifest-digest': lambda p: p['enumeration_history'][0].update(manifest_sha256='0'*64),
        }
        path = self.root/'tampered.json'
        for previous, changes in [(first, {**mutations, **current}), (second, {**mutations, **inherited})]:
            for label, mutate in changes.items():
                with self.subTest(inherited=previous is second, mutation=label):
                    data = copy.deepcopy(previous); mutate(data)
                    path.write_text(json.dumps(data))
                    before = path.read_bytes()
                    with mock.patch.object(self.artifacts, 'resolve') as resolve, \
                         mock.patch.object(self.artifacts, 'retained_build') as retained, \
                         mock.patch.object(sweep.multiprocessing, 'get_context') as spawn, \
                         self.assertRaises(ContractError):
                        self.run_sweep(name='rejected', resume=path)
                    resolve.assert_not_called(); retained.assert_not_called(); spawn.assert_not_called()
                    self.assertFalse((self.root/'rejected').exists())
                    self.assertEqual(path.read_bytes(), before)

    def test_enumeration_reports_unplanned_and_unavailable_cases_without_expanding_scope(self):
        self.caps['capabilities']['enumerate_messages'] = True
        extra = copy.deepcopy(self.cases[0]); extra['case_id'] = 'invented-unplanned'
        self.configuration['enumerated_cases'] = [self.cases[0], extra]
        manifest = self.run_sweep()
        self.assertEqual(manifest['completed'], [self.cases[0]['case_id']])
        self.assertEqual(manifest['unsupported'], [self.cases[1]['case_id']])
        self.assertEqual({g['kind'] for g in manifest['gaps']}, {'unplanned', 'absent_or_changed'})
        self.assertNotIn(extra['case_id'], manifest['planned'])

    def test_resume_rejects_duplicate_scope_and_invented_text_pass(self):
        first = self.run_sweep()
        path = self.root/'tampered-manifest.json'
        for change in ('duplicate', 'pass'):
            data = copy.deepcopy(first)
            if change == 'duplicate': data['observations'][1] = data['observations'][0]
            else: data['observations'][0]['assertion'] = 'passed'
            path.write_text(json.dumps(data))
            with self.assertRaises(ContractError): self.run_sweep(name='rejected', resume=path)

    def test_empty_enumeration_is_an_explicit_gap_not_complete_coverage(self):
        self.caps['capabilities']['enumerate_messages'] = True
        self.configuration['enumerated_cases'] = []
        manifest = self.run_sweep()
        self.assertEqual(manifest['unsupported'], manifest['planned'])
        self.assertEqual(len(manifest['gaps']), 2)
        self.assertFalse(manifest['capture_complete'])

    def test_real_store_connector_retains_observations_and_failure_references(self):
        from patchquest.runtime_artifact_state import ArtifactState
        from patchquest.state import Store
        from test_state import project, invented
        store = Store(project(self.root))
        store.put(invented('greeting'), 0, role='human')
        before = store.get('greeting')
        self.binding['snapshot'] = store.snapshot()['sha256']
        path = store.context.output.write_new('invented-build.fixture', self.raw)
        build = store.build(dict(id=self.binding['build_id'], snapshot=self.binding['snapshot'],
            status='validated', artifacts={'rom': str(path)}), 0)
        connector = ArtifactState(store, store.directory/'runtime-artifacts')
        self.artifacts = RuntimeArtifacts(connector.directory, budget_bytes=1024*1024, graph_guard=connector.guard)
        ref = reference(self.raw, evidence_id='invented-connected-build', media_type='application/octet-stream',
            provenance=dict(producer='invented-fixture', method='synthetic', run_id=None, case_id=None))
        self.build_refs = {'rom': self.artifacts.register(ref, self.raw)}
        self.fail_first('error')
        manifest = self.run_sweep()
        saved = connector.record_run(build['id'], manifest['observations'], expected=build['revision'])
        self.assertEqual(saved['validation']['runtime_cases'], manifest['observations'])
        with connector.guard() as graph:
            first = manifest['observations'][0]['captures'][0]['evidence']['sha256']
            kinds = {r['kind'] for r in graph['references'] if r['sha256']==first}
        self.assertTrue({'run', 'failure', 'build'} <= kinds)
        self.assertEqual(store.get('greeting'), before)
        self.assertEqual(path.read_bytes(), self.raw)

    def test_fresh_destination_and_wrong_build_are_rejected(self):
        self.run_sweep()
        with self.assertRaises(ContractError): self.run_sweep()
        self.binding['artifacts']['rom'] = 'b'*64
        with self.assertRaises(ValueError): self.run_sweep(name='wrong-build')

    def test_inventory_and_exercise_validation_keep_contexts_separate(self):
        with self.assertRaises(ContractError): case_inventory([self.cases[0]]*2, scope='invented-room', source='invented')
        with self.assertRaises(ContractError): case_inventory(self.cases, scope='other', source='invented')
        self.exercises[self.cases[0]['case_id']]['steps'][0]['buttons'] = ['NotAButton']
        with self.assertRaises(ContractError): self.run_sweep()


if __name__ == '__main__':
    unittest.main()

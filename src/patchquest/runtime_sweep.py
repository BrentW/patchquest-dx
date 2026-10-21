"""Bounded, spawn-worker scene/case capture; detector assertions stay separate.

Trusted local factories run in a child process, not a security sandbox. All
inventories, build bytes, configuration and output locations are explicit.
"""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import json
import multiprocessing
import os
import stat
import sys
from pathlib import Path
import time
import traceback
import uuid

from .core.context import OutputPolicy
from .runtime import BUTTONS, Frame
from .runtime_artifacts import BudgetExceeded, reference
from .runtime_contracts import (ContractError, binding_changes, check_observation,
    contract_digest, require_capabilities, validate)
from .runtime_scenes import SceneLibrary, prepare_scene

RUNNER_VERSION = '5'
JOURNAL_RETRY_LIMIT = 100
DEFAULT_LIMITS = dict(case_seconds=30, startup_seconds=30, shutdown_seconds=2,
    total_seconds=600, frames_per_case=20000, total_frames=100000,
    captures_per_case=100, capture_bytes=16 * 1024 * 1024, worker_cases=20,
    workspace_bytes=64 * 1024 * 1024)


def _need(value, reason):
    if not value:
        raise ContractError(reason)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _digest(value):
    return _sha(_json(value).encode('utf-8'))


def _limits(value):
    result = dict(DEFAULT_LIMITS)
    _need(value is None or type(value) is dict and not set(value) - set(result), 'Unknown runner limit')
    result.update(value or {})
    for key, number in result.items():
        if key.endswith('seconds'):
            _need(type(number) in (int, float) and 0 < number <= 3600, 'Invalid time limit')
        else:
            _need(type(number) is int and 1 <= number <= 100000000, 'Invalid runner limit')
    _need(result['frames_per_case'] <= 20000 and result['total_frames'] <= 100000
          and result['captures_per_case'] <= 100 and result['capture_bytes'] <= 16*1024*1024
          and result['worker_cases'] <= 100 and result['workspace_bytes'] <= 100000000,
          'Runner hard bound exceeded')
    return result


def storage_preflight(artifacts, *, limits=None, allowance=None):
    """Pure ceiling check: no graph/byte resolution, directory creation or spawn.

    Retained blobs and managed worker journals/captures are separate counters.
    shared_bytes explicitly approves their summed ceilings, not one deduplicated
    counter or an OS quota. None preserves callers without an approval policy.
    """
    bounds = _limits(limits)
    retained = artifacts.budget_bytes
    _need(type(retained) is int and 1 <= retained <= 2**50, 'Invalid retained byte ceiling')
    approved = None
    if allowance is not None:
        _need(type(allowance) is dict and {'retained_bytes', 'workspace_bytes'} <= set(allowance)
              and not set(allowance) - {'retained_bytes', 'workspace_bytes', 'shared_bytes'},
              'Explicit retained/workspace storage allowances required')
        approved = copy.deepcopy(allowance)
        approved.setdefault('shared_bytes', None)
        for key, value in approved.items():
            _need(key == 'shared_bytes' and value is None or
                  type(value) is int and 1 <= value <= 2**50, 'Invalid approved byte allowance')
        _need(retained <= approved['retained_bytes'], 'Retained byte ceiling exceeds approved allowance')
        _need(bounds['workspace_bytes'] <= approved['workspace_bytes'],
              'Worker workspace ceiling exceeds approved allowance')
        if approved['shared_bytes'] is not None:
            _need(retained + bounds['workspace_bytes'] <= approved['shared_bytes'],
                  'Summed storage ceilings exceed explicit shared allowance')
    return dict(retained_bytes=retained, workspace_bytes=bounds['workspace_bytes'],
                summed_ceiling_bytes=retained + bounds['workspace_bytes'], allowance=approved)


def case_inventory(values, *, scope, source, completeness='unknown'):
    """Validate an explicit adapter-supplied inventory without claiming a whole game."""
    _need(type(values) is list and 1 <= len(values) <= 1000, 'Explicit bounded case inventory required')
    _need(type(source) is str and 0 < len(source) <= 4000, 'Inventory source required')
    _need(completeness in ('unknown', 'partial', 'declared_complete'), 'Invalid inventory completeness')
    cases = [validate('CaseSpec', c) for c in values]
    _need(len({c['case_id'] for c in cases}) == len(cases), 'Duplicate case identity')
    _need(all(c['coverage_scope'] == scope for c in cases), 'Inventory scope differs')
    return dict(scope=scope, source=source, completeness=completeness, cases=cases)


def _enumeration(values, scope):
    if values == []:
        return dict(scope=scope, source='adapter enumeration', completeness='unknown', cases=[])
    return case_inventory(values, scope=scope, source='adapter enumeration')


def _enumeration_gaps(enumerated, inventory, run_id, worker):
    declared = {c['case_id']: contract_digest('CaseSpec', c) for c in inventory['cases']}
    observed = {c['case_id']: contract_digest('CaseSpec', c) for c in enumerated['cases']}
    return [dict(run_id=run_id, worker=worker, case_id=case_id,
                 kind='unplanned' if case_id not in declared else 'absent_or_changed',
                 declared_sha256=declared.get(case_id), enumerated_sha256=observed.get(case_id))
            for case_id in sorted(set(declared) | set(observed))
            if declared.get(case_id) != observed.get(case_id)]


def _resume_enumeration(prior, inventory, caps, history, manifest_sha256):
    """Validate the complete discovery ledger before touching retained artifacts."""
    inventories, gaps, sources = (prior.get(key) for key in
                                  ('inventories', 'gaps', 'enumeration_history'))
    _need(all(type(rows) is list for rows in (inventories, gaps, sources)),
          'Resume enumeration ledger lists required')
    run_id = prior.get('run_id')
    _need(type(run_id) is str and 0 < len(run_id) <= 200, 'Invalid prior run identity')
    workers = prior['workers']
    _need(len(workers) <= len(inventory['cases'])
          and [w.get('id') for w in workers] == ['worker-'+str(i+1) for i in range(len(workers))]
          and all(type(w.get('enumeration_observed')) is bool for w in workers),
          'Invalid prior enumeration worker provenance')
    current = [w['id'] for w in workers if w['enumeration_observed']]
    _need(caps['capabilities']['enumerate_messages'] or not (inventories or gaps or sources or current),
          'Enumeration ledger requires declared enumeration capability')
    _need(not caps['capabilities']['enumerate_messages'] or all(
        not w.get('completed_case_ids') or w['enumeration_observed'] for w in workers),
        'Completed prior worker is missing enumeration provenance')
    origins = {run_id: set(current)}
    historical_runs = {o['run_id'] for o in history}
    worker_names = {'worker-'+str(i+1) for i in range(1000)}
    for source in sources:
        _need(type(source) is dict and set(source) == {'run_id', 'manifest_sha256', 'worker_ids'},
              'Invalid enumeration source fields')
        origin, sha, ids = source['run_id'], source['manifest_sha256'], source['worker_ids']
        _need(type(origin) is str and origin in historical_runs and origin not in origins
              and type(sha) is str and len(sha) == 64 and all(c in '0123456789abcdef' for c in sha)
              and type(ids) is list and 1 <= len(ids) <= 1000
              and all(type(w) is str and w in worker_names for w in ids)
              and len(set(ids)) == len(ids), 'Invalid enumeration source provenance')
        origins[origin] = set(ids)
        if type(prior.get('prior')) is dict and prior['prior'].get('run_id') == origin:
            _need(prior['prior'].get('sha256') == sha, 'Enumeration source manifest digest differs')
    seen = set()
    expected_gaps = []
    for row in inventories:
        _need(type(row) is dict and set(row) ==
              {'run_id', 'worker', 'scope', 'source', 'completeness', 'cases'},
              'Invalid prior enumeration fields')
        origin, worker = row['run_id'], row['worker']
        _need(type(origin) is str and origin in origins and type(worker) is str
              and worker in origins[origin] and (origin, worker) not in seen,
              'Unknown or duplicate enumeration origin')
        enumerated = _enumeration(row['cases'], inventory['scope'])
        _need(row == dict(run_id=origin, worker=worker, **enumerated),
              'Prior enumeration metadata differs')
        seen.add((origin, worker))
        expected_gaps.extend(_enumeration_gaps(enumerated, inventory, origin, worker))
    _need(seen == {(origin, worker) for origin, ids in origins.items() for worker in ids},
          'Prior enumeration ledger is incomplete')
    _need(gaps == expected_gaps, 'Prior enumeration gaps differ from enumerated definitions')
    sources = copy.deepcopy(sources)
    if current:
        sources.append(dict(run_id=run_id, manifest_sha256=manifest_sha256, worker_ids=current))
    return copy.deepcopy(inventories), copy.deepcopy(gaps), sources


def _requests(inventory, library, exercises):
    _need(type(exercises) is dict and set(exercises) == {c['case_id'] for c in inventory['cases']},
          'Exercise definitions must cover the entire inventory')
    result = []
    for case in inventory['cases']:
        spec = copy.deepcopy(exercises[case['case_id']])
        _need(type(spec) is dict and {'scene_id', 'steps'} <= set(spec)
              and not set(spec) - {'scene_id', 'steps', 'mode'}, 'Unknown exercise fields')
        spec.setdefault('mode', 'exercise')
        _need(type(spec['mode']) is str and spec['mode'] in ('exercise', 'arrival_only'),
              'Unknown exercise mode')
        scene = library.select(spec['scene_id'])
        _need(contract_digest('CaseSpec', scene['case']) == contract_digest('CaseSpec', case),
              'Scene case definition differs')
        steps = spec['steps']
        _need(type(steps) is list, 'Explicit exercise steps required')
        if spec['mode'] == 'arrival_only':
            _need(not steps, 'Arrival-only capture requires empty exercise steps')
        else:
            _need(1 <= len(steps) <= 500, 'Bounded exercise steps required')
        total = 0
        for step in steps:
            _need(type(step) is dict and set(step) == {'frames', 'buttons', 'capture'}, 'Invalid exercise step')
            _need(type(step['frames']) is int and 1 <= step['frames'] <= 3600, 'Invalid exercise frames')
            total += step['frames']
            buttons = step['buttons']
            _need(type(buttons) is list and all(type(b) is str and b in BUTTONS for b in buttons)
                  and len(buttons) == len(set(buttons)), 'Invalid exercise inputs')
            _need(type(step['capture']) is bool, 'Explicit capture flag required')
        if spec['mode'] == 'exercise':
            _need(total <= 20000 and steps[-1]['capture'], 'Bounded final capture required')
        result.append(dict(case=case, scene=scene, exercise=spec))
    return result


def _write(directory, name, data):
    OutputPolicy(directory).write_new(name, data)


def _io_detail(error, phase, sequence):
    """Numeric diagnostics only: no exception message, filename or private path."""
    number = lambda name: getattr(error, name, None) if type(getattr(error, name, None)) is int else None
    winerror = number('winerror')
    operation = getattr(error, '_journal_operation', None)
    if operation not in ('CreateFileW', 'GetFileInformationByHandle', 'GetFileType', 'ReadFile', 'CloseHandle'):
        operation = None
    close_error = getattr(error, '_journal_close_error', None)
    return dict(phase=phase, sequence=sequence, error_type=type(error).__name__,
                errno=number('errno'), winerror=winerror,
                operation=operation,
                close_error=_io_detail(close_error, 'journal_close', sequence) if close_error else None,
                transient_sharing=winerror in (32, 33) and close_error is None)


def _read_journal_bytes(path):
    """Bounded regular-file read; retain Windows errors at the failing call.

    Python's CRT-backed read can discard WinError (including sharing denial).
    Do not diagnose it with a later probe or infer WinError from errno alone.
    All host I/O here is synchronous, as with the other trusted storage calls.
    """
    limit = 2 * 1024 * 1024
    if os.name != 'nt':
        with path.open('rb') as stream:
            return stream.read(limit + 1)
    import ctypes
    from ctypes import wintypes
    class FileInformation(ctypes.Structure):
        _fields_ = [('attributes', wintypes.DWORD), ('created', wintypes.FILETIME),
            ('accessed', wintypes.FILETIME), ('written', wintypes.FILETIME),
            ('volume', wintypes.DWORD), ('size_high', wintypes.DWORD),
            ('size_low', wintypes.DWORD), ('links', wintypes.DWORD),
            ('index_high', wintypes.DWORD), ('index_low', wintypes.DWORD)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.ReadFile.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.GetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.POINTER(FileInformation)]
    kernel.GetFileInformationByHandle.restype = wintypes.BOOL
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    def native_error(operation):
        error = ctypes.WinError(ctypes.get_last_error())
        error._journal_operation = operation
        return error
    # GENERIC_READ; share read/write/delete; OPEN_EXISTING. No permission change.
    # OPEN_REPARSE_POINT avoids following a final-component symbolic link.
    handle = kernel.CreateFileW(str(path), 0x80000000, 7, None, 3, 0x200080, None)
    if handle == ctypes.c_void_p(-1).value:
        raise native_error('CreateFileW')
    try:
        information = FileInformation()
        if not kernel.GetFileInformationByHandle(handle, ctypes.byref(information)):
            raise native_error('GetFileInformationByHandle')
        length = (information.size_high << 32) | information.size_low
        ctypes.set_last_error(0)
        file_type = kernel.GetFileType(handle)
        if file_type == 0 and ctypes.get_last_error():
            raise native_error('GetFileType')
        _need(file_type == 1 and not information.attributes & (0x10 | 0x400)
              and length <= limit, 'Invalid opened worker event file')
        chunks = []
        remaining = length + 1
        while remaining:
            buffer = ctypes.create_string_buffer(remaining)
            count = wintypes.DWORD()
            if not kernel.ReadFile(handle, buffer, remaining, ctypes.byref(count), None):
                raise native_error('ReadFile')
            if not count.value:
                break
            chunks.append(buffer.raw[:count.value])
            remaining -= count.value
        raw = b''.join(chunks)
        _need(len(raw) == length, 'Opened worker event changed')
        return raw
    finally:
        # Preserve both codes, and fail closed if handle closure is uncertain.
        primary = sys.exc_info()[1]
        if not kernel.CloseHandle(handle):
            error = native_error('CloseHandle')
            if primary is None:
                raise error
            primary._journal_close_error = error


def _read_journal_event(path, sequence, diagnostics):
    """One nonblocking poll of the SAME sequence; caller owns all deadlines.

    Windows sharing/lock errors retry only through the outer bounded poll loop.
    Access denied (5), unclassified EACCES and other failures are never assumed
    transient. A missing name is normal only before publication is observed.
    """
    phase = 'journal_lstat'
    try:
        try:
            attributes = path.lstat()
        except FileNotFoundError:
            if diagnostics['pending_sequence'] == sequence:
                raise
            return None, False
        _need(stat.S_ISREG(attributes.st_mode) and attributes.st_size <= 2*1024*1024,
              'Invalid worker event file')
        phase = 'journal_read'
        raw = _read_journal_bytes(path)
        _need(len(raw) == attributes.st_size, 'Published worker event changed')
    except OSError as error:
        detail = _io_detail(error, phase, sequence)
        diagnostics['last_error'] = detail
        if diagnostics['first_error'] is None:
            diagnostics['first_error'] = copy.deepcopy(detail)
        if not detail['transient_sharing'] or diagnostics['pending_retries'] >= JOURNAL_RETRY_LIMIT:
            diagnostics['fatal_error'] = detail
            diagnostics['retry_exhausted'] = detail['transient_sharing']
            raise
        diagnostics['retry_count'] += 1
        diagnostics['pending_retries'] += 1
        diagnostics['pending_sequence'] = sequence
        return None, True
    except Exception as error:
        if getattr(error, '_journal_close_error', None) is not None:
            detail = _io_detail(error, phase, sequence)
            diagnostics['last_error'] = diagnostics['fatal_error'] = detail
            if diagnostics['first_error'] is None:
                diagnostics['first_error'] = copy.deepcopy(detail)
        raise
    event = json.loads(raw)
    if diagnostics['pending_sequence'] == sequence:
        diagnostics['recovered_events'] += 1
        diagnostics['pending_sequence'] = None
        diagnostics['pending_retries'] = 0
    return event, False


def _worker(factory, configuration, inputs, binding, caps, requests, checkpoints, limits, directory):
    with (Path(directory)/'worker.log').open('x', encoding='utf-8') as log:
        with redirect_stderr(log), redirect_stdout(log):
            try:
                _worker_main(factory, configuration, inputs, binding, caps, requests, checkpoints, limits, directory)
            except BaseException:
                traceback.print_exc()  # Raw diagnostics remain in the private worker directory.


def _worker_main(factory, configuration, inputs, binding, caps, requests, checkpoints, limits, directory):
    """Only spawn-picklable trusted factories; never commands or import strings."""
    root = Path(directory)
    sequence = 0
    managed_bytes = 0
    adapter = None
    enumeration = None
    worker_frames = 0

    def emit(kind, **fields):
        nonlocal sequence, managed_bytes
        sequence += 1
        payload = dict(kind=kind, **fields)
        raw = _json(payload).encode('utf-8')
        if len(raw) > 2 * 1024 * 1024:
            raise ContractError('Worker event too large')
        if managed_bytes + len(raw) > limits['workspace_bytes']:
            raise BudgetExceeded('Managed worker journal budget exhausted')
        managed_bytes += len(raw)
        # The ready name is exposed only after a complete exclusive write. Partial
        # staging files survive crashes for diagnosis and are never read as events.
        staging = root / f'{sequence}.pending'
        phase = 'journal_stage_write'
        try:
            with staging.open('xb') as stream:
                stream.write(raw)
            phase = 'journal_publish'
            staging.rename(root / f'{sequence}.json')
        except OSError as error:
            # Publication remains fail-closed; retain safe phase/codes as well
            # as the existing private traceback. Never overwrite/skip a name.
            print(_json(dict(kind='journal_io_failure', detail=_io_detail(error, phase, sequence))))
            raise

    try:
        adapter = factory(copy.deepcopy(configuration))
        emit('worker_ready')
        for request in requests:
            case, scene = request['case'], request['scene']
            emit('case_start', case_id=case['case_id'])
            count = 0
            captures = 0
            frame_numbers = {}
            resets = 0

            def identity():
                description = adapter.describe()
                _need(description.get('kind') == caps['provenance'] and
                      description.get('sha256') == binding['emulator']['sha256'] and
                      description.get('version') == binding['emulator']['version'], 'Emulator identity changed')
                _need(validate('AdapterCapabilities', adapter.capabilities()) == caps, 'Capabilities changed')
                _need(_digest(adapter.configuration()) == binding['configuration_sha256'], 'Configuration changed')
                _need(adapter.loaded_artifacts() == binding['artifacts'], 'Loaded artifact identity changed')

            def reset(_number=1):
                nonlocal resets
                resets += 1
                sandbox = root / f'session-{requests.index(request)}-{resets}'
                sandbox.mkdir()
                adapter.reset(dict(inputs), copy.deepcopy(configuration), sandbox)
                identity()

            class Tracked:
                def __getattr__(self, name):
                    return getattr(adapter, name)

                def step(self, buttons):
                    nonlocal count, worker_frames
                    if count >= limits['frames_per_case'] or worker_frames >= limits['total_frames']:
                        raise TimeoutError('Case frame budget exhausted')
                    returned = adapter.step(buttons)
                    _need(isinstance(returned, Frame), 'Expected runtime Frame')
                    count += 1
                    worker_frames += 1
                    frame = Frame(returned.width, returned.height, returned.rgb)
                    frame_numbers[id(frame)] = count
                    emit('progress', frame=count)
                    return frame

            tracked = Tracked()

            def capture(frame):
                nonlocal sequence, captures, managed_bytes
                if captures >= limits['captures_per_case']:
                    raise TimeoutError('Case capture budget exhausted')
                raw = frame.png()
                _need(len(raw) <= limits['capture_bytes'], 'Capture byte budget exceeded')
                if managed_bytes + len(raw) + 1024 > limits['workspace_bytes']:
                    raise BudgetExceeded('Managed worker capture budget exhausted')
                managed_bytes += len(raw)
                index = sequence + 1
                _write(root, f'{index}.png', raw)
                emit('capture', frame=frame_numbers[id(frame)], sha256=_sha(raw), byte_length=len(raw))
                captures += 1
                deadline = time.monotonic()+limits['case_seconds']
                while not (root/f'{sequence}.ack').exists():
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Parent capture acknowledgement timed out')
                    time.sleep(0.01)

            try:
                require_capabilities(case, caps)
                if any(s['buttons'] for s in request['exercise']['steps']) and not caps['capabilities']['input']:
                    emit('case_done', execution='unsupported', reason='Exercise input unavailable', scene_handle=None,
                         telemetry={})
                    continue
                # Every case starts by reloading pinned immutable inputs, even in
                # a worker which amortizes factory/backend initialization.
                reset()
                if caps['capabilities']['enumerate_messages']:
                    if enumeration is None:
                        _need(callable(getattr(adapter, 'enumerate_cases', None)), 'Enumeration interface unavailable')
                        enumeration = _enumeration(adapter.enumerate_cases(case['coverage_scope']),
                            case['coverage_scope'])['cases']
                        emit('inventory', cases=enumeration)
                        reset()  # Enumeration must not contaminate the selected case.
                    matching = [c for c in enumeration if c['case_id'] == case['case_id']]
                    if not matching or contract_digest('CaseSpec', matching[0]) != contract_digest('CaseSpec', case):
                        emit('case_done', execution='unsupported', reason='Case absent or different in adapter enumeration',
                             scene_handle=None, telemetry={})
                        continue
                prep = prepare_scene(SceneLibrary(checkpoints['scenes']),
                    scene['scene_id'], case, binding, caps, tracked,
                    checkpoint_bytes=checkpoints['bytes'].get(scene['scene_id']),
                    reset=reset if scene['limits']['attempts'] > 1 else None,
                    isolated_test_session=True,
                    debug_setup=getattr(adapter, 'debug_setup', None) if scene['reach_method'] == 'debug_injection' else None)
                for attempt in prep['attempts']:
                    if attempt['frame'] is not None:
                        capture(attempt['frame'])
                handle = prep['handle']
                if handle['status'] != 'ready':
                    execution = ('unsupported' if handle['status'] == 'unsupported' else
                                 'interrupted' if 'TimeoutError' in handle['reason'] else 'failed')
                    emit('case_done', execution=execution,
                         reason=handle['reason'], scene_handle=handle, telemetry={})
                    continue
                # Arrival-only requests have no exercise steps. Preparation's
                # attempt captures above already retain the verified arrival
                # and any failed-attempt diagnostics, without another step.
                for step in request['exercise']['steps']:
                    for _ in range(step['frames']):
                        frame = tracked.step(list(step['buttons']))
                    if step['capture']:
                        capture(frame)
                identity()
                telemetry = adapter.observe(case, count) if callable(getattr(adapter, 'observe', None)) else {}
                emit('case_done', execution='completed', reason='', scene_handle=handle, telemetry=telemetry)
            except Exception as error:
                execution = ('unsupported' if type(error).__name__ == 'UnsupportedCapability' else
                             'interrupted' if isinstance(error, (BudgetExceeded, TimeoutError)) else 'failed')
                emit('case_done', execution=execution,
                     reason='Worker case error: ' + type(error).__name__, scene_handle=None, telemetry={})
    finally:
        if adapter is not None:
            adapter.close()
    emit('worker_done')


def _stop(process, seconds, *, graceful=False, phase_started=None):
    """Bounded parent observations, retained even if process control fails."""
    control_started = time.monotonic()
    started = control_started if phase_started is None else phase_started
    result = dict(started_monotonic=started, finished_monotonic=None, elapsed_seconds=None,
                  control_started_monotonic=control_started, control_elapsed_seconds=None,
                  graceful_wait=graceful, terminate_requested=False, kill_requested=False,
                  exitcode=None, final_state='unknown', errors=[])
    try:
        if graceful:
            process.join(max(0, seconds - (control_started-started)))
        if process.is_alive():
            result['terminate_requested'] = True
            process.terminate()
        process.join(seconds)
        if process.is_alive():
            result['kill_requested'] = True
            process.kill()
            process.join(seconds)
        if not process.is_alive():
            result.update(final_state='stopped', exitcode=process.exitcode)
    except Exception as error:
        result['errors'].append(type(error).__name__)
        # A failed request is not evidence the child stopped. Still try the last
        # escalation and retain unknown if the host cannot establish termination.
        try:
            if process.is_alive():
                result['kill_requested'] = True
                process.kill()
                process.join(seconds)
            if not process.is_alive():
                result.update(final_state='stopped', exitcode=process.exitcode)
        except Exception as error:
            result['errors'].append(type(error).__name__)
    if result['final_state'] == 'stopped':
        try:
            process.close()
        except Exception as error:
            result['errors'].append(type(error).__name__)
    result['finished_monotonic'] = time.monotonic()
    result['elapsed_seconds'] = result['finished_monotonic'] - started
    result['control_elapsed_seconds'] = result['finished_monotonic'] - control_started
    return result


def _clean_worker(info):
    shutdown = info.get('shutdown')
    return (info.get('outcome') == 'completed' and info.get('clean_exit') is True
        and info.get('worker_done_observed') is True and type(shutdown) is dict
        and shutdown.get('final_state') == 'stopped' and type(shutdown.get('exitcode')) is int
        and shutdown['exitcode'] == 0 and shutdown.get('terminate_requested') is False
        and shutdown.get('kill_requested') is False and shutdown.get('errors') == [])


def run_sweep(inventory, library, exercises, binding, capabilities, artifacts,
              build_references, configuration, adapter_factory, destination, *,
              limits=None, cancelled=None, resume=None, selection_plan=None,
              storage_allowance=None):
    """Capture an explicit scope and return its newly written immutable manifest.

    The composition root supplies RuntimeArtifacts with its authoritative graph
    guard, then registers the resulting manifest/associations through state APIs.
    No text assertion, translation write or checkpoint approval occurs here.
    """
    _need(type(inventory) is dict and set(inventory) == {'scope', 'source', 'completeness', 'cases'},
          'Invalid inventory')
    inventory = case_inventory(inventory['cases'], scope=inventory['scope'],
        source=inventory['source'], completeness=inventory['completeness'])
    binding, caps = validate('RunBinding', binding), validate('AdapterCapabilities', capabilities)
    bounds = _limits(limits)
    storage_policy = storage_preflight(artifacts, limits=bounds, allowance=storage_allowance)
    _need(callable(adapter_factory) and (cancelled is None or callable(cancelled)), 'Explicit local callbacks required')
    _need(binding['adapter'] == caps['adapter'], 'Adapter binding differs')
    _need(_digest(configuration) == binding['configuration_sha256'], 'Configuration hash differs')
    requests = _requests(inventory, library, exercises)
    _need(all(set(r['case']['record_ids']) <= set(binding['records']) for r in requests), 'Scoped revisions missing')
    _need(type(build_references) is dict and set(build_references) == set(binding['artifacts']), 'All build roles required')
    selected = {r['case']['case_id'] for r in requests}
    if selection_plan is not None:
        plan = validate('ChangeImpactPlan', selection_plan)
        _need(not binding_changes(plan['binding'], binding) and set(plan['case_ids']) == selected,
              'Selection binding/scope differs')
        selected = {row['case_id'] for row in plan['selected']}
    else:
        plan = None
    definition = dict(runner_version=RUNNER_VERSION, inventory=inventory, requests=requests,
                      binding=binding, capabilities=caps, configuration=configuration,
                      limits=bounds, selection_plan=plan, storage_policy=storage_policy)
    definition_digest = _digest(definition)
    prior = None
    history = []
    reused = {}
    inventories, gaps, enumeration_history = [], [], []
    if resume is not None:
        path = Path(resume)
        _need(path.is_file() and not path.is_symlink() and path.stat().st_size <= 32*1024*1024,
              'Explicit bounded prior manifest required')
        raw = path.read_bytes()
        prior = json.loads(raw)
        _need(type(prior) is dict and prior.get('schema_version') == 1 and prior.get('runner_version') == RUNNER_VERSION
              and prior.get('definition_sha256') == definition_digest
              and prior.get('definition') == definition, 'Resume definition/binding differs')
        _need(type(prior.get('workers')) is list and all(
            type(worker) is dict and type(worker.get('shutdown')) is dict
            and worker['shutdown'].get('final_state') == 'stopped'
            for worker in prior['workers']),
            'Resume requires confirmed stopped state for every prior worker; owner investigation required')
        _need(type(prior.get('history')) is list and type(prior.get('observations')) is list
              and len(prior['history']) + len(prior['observations']) <= 100000,
              'Resume history lists/bound invalid')
        history = prior['history'] + prior['observations']
        _need(all(type(o) is dict and type(o.get('run_id')) is str and type(o.get('case_id')) is str
                  for o in history), 'Invalid resume observation history')
        _need(len(prior['observations']) == len(requests) and
              {o['case_id'] for o in prior['observations']} == {r['case']['case_id'] for r in requests},
              'Resume observations do not cover the original scope uniquely')
        inventories, gaps, enumeration_history = _resume_enumeration(
            prior, inventory, caps, history, _sha(raw))
        invalidated = {case_id for worker in prior['workers'] if worker.get('invalidates_completed')
                       or not _clean_worker(worker)
                       for case_id in worker.get('completed_case_ids', worker['case_ids'])}
        for candidate in prior['observations']:
            case = next((r['case'] for r in requests if r['case']['case_id'] == candidate['case_id']), None)
            _need(case is not None, 'Prior observation outside inventory')
            observation = check_observation(case, candidate, caps, expected_binding=binding)
            _need(observation['assertion'] in ('not_assessed', 'unsupported'), 'Resume cannot introduce text assertions')
            if (observation['execution'] == 'completed' and observation['validity'] == 'current'
                    and case['case_id'] not in invalidated):
                if observation['captures'] and all(artifacts.resolve(c['evidence'])['available'] for c in observation['captures']):
                    reused[case['case_id']] = observation
        prior = dict(sha256=_sha(raw), run_id=prior['run_id'])
    inputs = {}
    for role, ref in build_references.items():
        resolved = artifacts.retained_build(binding, role, ref)
        _need(resolved['available'], 'Pinned build bytes unavailable')
        inputs[role] = resolved['data']
    checkpoints = dict(bytes={}, scenes=[r['scene'] for r in requests])
    scenes = {r['scene']['scene_id'] for r in requests}
    for r in requests:
        scene = r['scene']
        if scene['checkpoint'] is not None:
            resolved = artifacts.resolve(scene['checkpoint'])
            if resolved['available']:
                checkpoints['bytes'][scene['scene_id']] = resolved['data']
        target = scene['regenerate_from']
        while target is not None:
            regen = library.select(target)
            if target not in scenes:
                checkpoints['scenes'].append(regen); scenes.add(target)
            target = regen['regenerate_from']
    out = Path(destination).absolute()
    _need(not out.exists() and out.resolve() == out, 'Fresh unredirected output required')
    storage = artifacts.directory.resolve()
    _need(not out.is_relative_to(storage) and not storage.is_relative_to(out), 'Worker outputs overlap retained storage')
    out.mkdir(parents=True)
    policy = OutputPolicy(out)
    policy.write_new('definition.json', (_json(definition)+'\n').encode('utf-8'))
    run_id = 'sweep-' + uuid.uuid4().hex
    manifest = dict(schema_version=1, runner_version=RUNNER_VERSION, run_id=run_id,
        definition_sha256=definition_digest, definition=definition, prior=prior,
        history=history, observations=[], workers=[], planned=[r['case']['case_id'] for r in requests],
        completed=[], interrupted=[], unsupported=[], failed=[], not_run=[], excluded=[],
        inventories=inventories, gaps=gaps, enumeration_history=enumeration_history,
        elapsed_seconds=0, observed_frames=0, capture_complete=False)
    pending = []
    method = 'synthetic' if caps['provenance'] == 'synthetic' else 'automated_runtime'
    results = {}
    started = time.monotonic()
    workspace_used = 0

    def record(request, execution, reason='', captures=(), frames=0, telemetry=None):
        case = request['case']
        telemetry = telemetry or {}
        _need(type(telemetry) is dict and not set(telemetry) - {'glyphs', 'resources', 'controls'}, 'Unknown telemetry')
        value = dict(schema_version=1, kind='CaseObservation',
            observation_id='observation-' + uuid.uuid4().hex, run_id=run_id,
            case_id=case['case_id'], case_sha256=contract_digest('CaseSpec', case), binding=binding,
            provenance=caps['provenance'], method=method, reach_method=request['scene']['reach_method'],
            execution=execution, assertion='unsupported' if execution == 'unsupported' else 'not_assessed',
            validity='current', frames=frames, captures=list(captures), reason=reason,
            glyphs=telemetry.get('glyphs'), resources=telemetry.get('resources'), controls=telemetry.get('controls', {}))
        value = check_observation(case, value, caps, expected_binding=binding)
        filename = value['observation_id'] + '.json'
        policy.write_new(filename, (_json(value)+'\n').encode('utf-8'))
        results[case['case_id']] = value

    for request in requests:
        case_id = request['case']['case_id']
        if case_id not in selected:
            record(request, 'excluded', 'Deferred by explicit ChangeImpactPlan; no verification awarded')
        elif case_id in reused:
            results[case_id] = reused[case_id]
        else:
            pending.append(request)

    def stopping(check_frames=False):
        if cancelled is not None and cancelled():
            return 'Cancelled by caller'
        if time.monotonic()-started >= bounds['total_seconds']:
            return 'Total elapsed-time budget exhausted'
        if check_frames and manifest['observed_frames'] >= bounds['total_frames']:
            return 'Total observed-frame budget exhausted'
        if workspace_used >= bounds['workspace_bytes']:
            return 'Managed worker workspace budget exhausted'
        return ''

    while pending:
        stop_reason = stopping(check_frames=True)
        if stop_reason:
            for request in pending:
                record(request, 'not_run', stop_reason)
            break
        batch = pending[:bounds['worker_cases']]
        worker_dir = out / ('worker-' + str(len(manifest['workers'])+1))
        worker_dir.mkdir()
        info = dict(id=worker_dir.name, outcome='starting', reason='', invalidates_completed=False,
                    case_ids=[r['case']['case_id'] for r in batch], completed_case_ids=[], clean_exit=False,
                    enumeration_observed=False,
                    worker_done_observed=False, shutdown_phase_started_monotonic=None,
                    startup=dict(start_requested_monotonic=None,
                        start_returned_monotonic=None, ready_observed_monotonic=None,
                        finished_monotonic=None, elapsed_seconds=None), shutdown=None)
        info['journal_io'] = dict(retry_count=0, retry_limit=JOURNAL_RETRY_LIMIT,
            recovered_events=0, pending_sequence=None, pending_retries=0,
            retry_exhausted=False, first_error=None, last_error=None, fatal_error=None)
        manifest['workers'].append(info)
        process = multiprocessing.get_context('spawn').Process(target=_worker,
            args=(adapter_factory, configuration, inputs, binding, caps, batch, checkpoints,
                  dict(bounds, workspace_bytes=bounds['workspace_bytes']-workspace_used,
                       total_frames=bounds['total_frames']-manifest['observed_frames']), str(worker_dir)))
        active = None
        count = 0
        captures = []
        index = 1
        deadline = time.monotonic()+bounds['startup_seconds']
        ready = False
        handled = set()
        info['startup']['start_requested_monotonic'] = time.monotonic()
        try:
            process.start()
            info['startup']['start_returned_monotonic'] = time.monotonic()
        except Exception as error:
            info.update(outcome='failed', reason='Worker start error: '+type(error).__name__)
            info['shutdown'] = _stop(process, bounds['shutdown_seconds'])
            info['startup']['finished_monotonic'] = time.monotonic()
            info['startup']['elapsed_seconds'] = (info['startup']['finished_monotonic'] -
                                                  info['startup']['start_requested_monotonic'])
            record(batch[0], 'failed', info['reason'])
            pending.remove(batch[0])
            if info['shutdown']['final_state'] != 'stopped':
                for request in pending:
                    record(request, 'not_run', 'Worker stopped state unknown; no further worker may start')
                break
            continue
        try:
            phase = 'journal_poll'
            while True:
                stop_reason = stopping()
                if stop_reason:
                    info.update(outcome='interrupted', reason=stop_reason)
                    break
                if time.monotonic() >= deadline:
                    info.update(outcome='interrupted', reason='Case timeout' if active else 'Worker startup/shutdown timeout')
                    break
                path = worker_dir / f'{index}.json'
                phase = 'journal_poll'
                event, retrying = _read_journal_event(path, index, info['journal_io'])
                if event is not None:
                    # Trusted synchronous I/O cannot be interrupted, but a read
                    # returning after cancellation/deadline cannot earn acceptance.
                    stop_reason = stopping()
                    if stop_reason:
                        info.update(outcome='interrupted', reason=stop_reason)
                        break
                    if time.monotonic() >= deadline:
                        info.update(outcome='interrupted', reason='Case timeout' if active else 'Worker startup/shutdown timeout')
                        break
                    phase = 'event_protocol'
                    kind = event.get('kind')
                    if kind == 'worker_ready':
                        _need(set(event) == {'kind'} and not ready, 'Unexpected worker ready')
                        ready = True
                        timestamp = time.monotonic()
                        info['startup'].update(ready_observed_monotonic=timestamp,
                            finished_monotonic=timestamp,
                            elapsed_seconds=timestamp-info['startup']['start_requested_monotonic'])
                        deadline = time.monotonic()+bounds['case_seconds']
                    elif kind == 'case_start':
                        _need(set(event) == {'kind', 'case_id'} and ready and active is None, 'Unexpected case start')
                        expected = next((r for r in batch if r['case']['case_id'] not in handled), None)
                        _need(expected is not None and event['case_id'] == expected['case']['case_id'], 'Case order differs')
                        active = expected; count = 0; captures = []
                        deadline = time.monotonic()+bounds['case_seconds']
                    elif kind == 'progress':
                        _need(set(event) == {'kind', 'frame'} and active is not None
                              and type(event['frame']) is int and event['frame'] == count+1
                              and count < bounds['frames_per_case'], 'Invalid frame progress')
                        if manifest['observed_frames'] >= bounds['total_frames']:
                            raise TimeoutError('Total observed-frame budget exhausted')
                        count += 1; manifest['observed_frames'] += 1
                    elif kind == 'inventory':
                        _need(set(event) == {'kind', 'cases'} and active is not None
                              and caps['capabilities']['enumerate_messages']
                              and not info['enumeration_observed'], 'Unexpected enumeration')
                        enumerated = _enumeration(event['cases'], inventory['scope'])
                        manifest['inventories'].append(dict(run_id=run_id, worker=info['id'], **enumerated))
                        manifest['gaps'].extend(_enumeration_gaps(enumerated, inventory, run_id, info['id']))
                        info['enumeration_observed'] = True
                    elif kind == 'capture':
                        _need(set(event) == {'kind', 'frame', 'sha256', 'byte_length'} and active is not None
                              and type(event['frame']) is int and 1 <= event['frame'] <= count
                              and len(captures) < bounds['captures_per_case'], 'Invalid capture event')
                        image = worker_dir / f'{index}.png'
                        phase = 'capture_validation'
                        _need(image.is_file() and not image.is_symlink() and image.stat().st_size <= bounds['capture_bytes'],
                              'Invalid capture file')
                        phase = 'capture_read'
                        raw = image.read_bytes()
                        ref = reference(raw, evidence_id='capture-'+uuid.uuid4().hex, media_type='image/png',
                            provenance=dict(producer=caps['adapter']['id'], method=method,
                                run_id=run_id, case_id=active['case']['case_id']))
                        _need(ref['sha256'] == event['sha256'] and ref['byte_length'] == event['byte_length'],
                              'Capture transfer bytes differ')
                        phase = 'artifact_register'
                        captures.append(dict(frame=event['frame'], evidence=artifacts.register(ref, raw)))
                        phase = 'capture_acknowledgement'
                        _write(worker_dir, f'{index}.ack', b'')
                    elif kind == 'case_done':
                        _need(set(event) == {'kind', 'execution', 'reason', 'scene_handle', 'telemetry'}
                              and active is not None and event['execution'] in ('completed', 'unsupported', 'failed', 'interrupted'),
                              'Invalid case result')
                        handle = event['scene_handle']
                        if handle is not None:
                            handle = validate('SceneHandle', handle)
                            _need(not binding_changes(handle['binding'], binding)
                                  and handle['scene_id'] == active['scene']['scene_id']
                                  and handle['reach_method'] == active['scene']['reach_method'], 'Scene binding differs')
                        if event['execution'] == 'completed':
                            _need(handle is not None and handle['status'] == 'ready' and bool(captures), 'Capture lacks ready scene')
                        phase = 'observation_write'
                        record(active, event['execution'], event['reason'], captures, count, event['telemetry'])
                        if event['execution'] == 'completed':
                            info['completed_case_ids'].append(active['case']['case_id'])
                        handled.add(active['case']['case_id']); pending.remove(active)
                        active = None; count = 0; captures = []
                        if len(handled) == len(batch):
                            info['shutdown_phase_started_monotonic'] = time.monotonic()
                        deadline = time.monotonic()+bounds['shutdown_seconds'] if len(handled) == len(batch) else time.monotonic()+bounds['case_seconds']
                    elif kind == 'worker_done':
                        _need(set(event) == {'kind'} and active is None and len(handled) == len(batch), 'Worker ended prematurely')
                        info.update(outcome='completed', worker_done_observed=True); break
                    else:
                        raise ContractError('Unknown worker event')
                    index += 1
                    continue
                # A published name blocked by known sharing contention can
                # outlive its producer. Keep its exact sequence pending until
                # read, cancellation or the already running deadline.
                if not retrying and not process.is_alive():
                    info.update(outcome='failed', reason='Worker exited without completion: '+str(process.exitcode))
                    break
                time.sleep(0.01)
        except BudgetExceeded:
            info.update(outcome='interrupted', reason='Artifact byte budget exhausted; capture incomplete')
        except TimeoutError:
            info.update(outcome='interrupted', reason='Total observed-frame budget exhausted')
        except OSError as error:
            info['io_error'] = info['journal_io']['fatal_error'] or _io_detail(error, phase, index)
            info.update(outcome='failed', reason='Runner protocol/storage error: '+type(error).__name__)
        except Exception as error:
            if info['journal_io']['fatal_error'] is not None:
                info['io_error'] = info['journal_io']['fatal_error']
            info.update(outcome='failed', reason='Runner protocol/storage error: '+type(error).__name__)
        finally:
            if info['startup']['finished_monotonic'] is None:
                timestamp = time.monotonic()
                info['startup'].update(finished_monotonic=timestamp,
                    elapsed_seconds=timestamp-info['startup']['start_requested_monotonic'])
            shutdown = _stop(process, bounds['shutdown_seconds'], graceful=info['worker_done_observed'],
                             phase_started=info['shutdown_phase_started_monotonic'])
            info['shutdown'] = shutdown
            info['clean_exit'] = (info['worker_done_observed'] and shutdown['final_state'] == 'stopped'
                and shutdown['exitcode'] == 0 and not shutdown['terminate_requested']
                and not shutdown['kill_requested'] and not shutdown['errors'])
            if info['outcome'] == 'completed' and not info['clean_exit']:
                info.update(outcome='interrupted' if shutdown['terminate_requested'] or shutdown['kill_requested']
                            else 'failed', reason='Worker completion did not establish clean process exit')
        workspace_used += sum(p.stat().st_size for p in worker_dir.iterdir()
                              if p.is_file() and p.suffix in ('.json', '.pending', '.png'))
        if info['outcome'] != 'completed':
            info['invalidates_completed'] = bool(info['completed_case_ids'])
            target = active or next((r for r in batch if r['case']['case_id'] not in handled), None)
            if target is not None:
                record(target, 'interrupted' if info['outcome'] == 'interrupted' else 'failed',
                       info['reason'], captures if active else (), count if active else 0)
                pending.remove(target)
        if info['shutdown']['final_state'] != 'stopped':
            for request in pending:
                record(request, 'not_run', 'Worker stopped state unknown; no further worker may start')
            break
    manifest['observations'] = [results[r['case']['case_id']] for r in requests]
    for observation in manifest['observations']:
        execution = observation['execution']
        manifest[execution if execution in ('completed', 'interrupted', 'unsupported', 'failed', 'not_run', 'excluded') else 'failed'].append(observation['case_id'])
    manifest['elapsed_seconds'] = round(time.monotonic()-started, 6)
    manifest['managed_workspace_bytes'] = workspace_used
    manifest['capture_complete'] = all(o['execution'] == 'completed' for o in manifest['observations']) and all(
        _clean_worker(w) for w in manifest['workers'])
    policy.write_new('manifest.json', (_json(manifest)+'\n').encode('utf-8'))
    return copy.deepcopy(manifest)

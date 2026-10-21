"""Versioned, side-effect-free contracts for scoped runtime text checks.

JSON dictionaries match the platform's existing state/evidence interfaces.
Validation establishes consistency, not emulator execution or human approval.
No file, database, emulator, network or project discovery operations occur here.
"""
import copy
import hashlib
import json
import math
import re

SCHEMA_VERSION = 1
CAPABILITIES = (
    'enumerate_messages', 'capture_frames', 'observe_glyphs', 'observe_resources',
    'input', 'page_advance', 'native_scroll', 'restore_state', 'game_save', 'debug_access',
)
REACH_METHODS = ('cold_boot_navigation', 'in_game_save', 'emulator_state', 'debug_injection')
METHODS = ('static', 'manual_review', 'reported_human', 'hardware', 'automated_runtime', 'synthetic')
EXECUTIONS = ('not_run', 'running', 'completed', 'failed', 'interrupted', 'unsupported', 'excluded')
ASSERTIONS = ('passed', 'failed', 'not_assessed', 'unknown', 'unsupported')
VALIDITIES = ('current', 'stale', 'missing', 'invalid', 'unknown')
COVERAGE_STATUSES = ('passed', 'failed', 'untested', 'in_progress', 'interrupted',
                     'stale', 'excluded', 'unsupported', 'unknown')
SCOPE_KINDS = ('renderer', 'normal_gameplay', 'editorial', 'hardware')
LIMIT = 100000


class ContractError(ValueError):
    """Invalid or incompatible connector data."""


class UnsupportedCapability(ContractError):
    """A required capability is unknown or not advertised as supported."""


def _need(condition, message):
    if not condition:
        raise ContractError(message)


def _text(value, name, nullable=False):
    if nullable and value is None:
        return
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 4000,
          name + ': expected nonempty text')


def _id(value, name='id', nullable=False):
    if nullable and value is None:
        return
    _text(value, name)
    _need(len(value) <= 200 and not any(ord(c) < 32 for c in value), name + ': invalid identity')


def _integer(value, name, minimum=0):
    _need(type(value) is int and minimum <= value <= 2**63 - 1, name + ': invalid integer')


def _digest(value, name='sha256'):
    _need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None,
          name + ': expected lowercase SHA-256')


def _choice(value, values, name):
    _need(isinstance(value, str) and value in values, name + ': unsupported value')


def _list(value, name):
    _need(type(value) is list and len(value) <= LIMIT, name + ': expected bounded array')


def _ids(value, name):
    _list(value, name)
    for item in value:
        _id(item, name)
    _need(len(set(value)) == len(value), name + ': duplicate identity')


def _object(value, required, optional=()):
    _need(type(value) is dict, 'Expected JSON object')
    _need(set(required) <= set(value), 'Missing fields: ' + ', '.join(sorted(set(required) - set(value))))
    _need(set(value) <= set(required) | set(optional),
          'Unknown fields: ' + ', '.join(sorted(set(value) - set(required) - set(optional))))


def _json(value, depth=0):
    _need(depth <= 40, 'JSON nesting limit exceeded')
    if type(value) is dict:
        _need(len(value) <= LIMIT and all(type(k) is str for k in value), 'Invalid JSON keys')
        for item in value.values():
            _json(item, depth + 1)
    elif type(value) is list:
        _list(value, 'JSON array')
        for item in value:
            _json(item, depth + 1)
    else:
        _need(value is None or type(value) in (bool, int, float, str), 'Non-JSON value')
        if type(value) is float:
            _need(math.isfinite(value), 'Non-finite JSON number')


def _record(value, kind, required, defaults=None):
    defaults = defaults or {}
    _object(value, ('schema_version', 'kind', *required), (*defaults, 'extensions'))
    _need(type(value['schema_version']) is int and value['schema_version'] == SCHEMA_VERSION,
          'Unsupported schema_version')
    _need(value['kind'] == kind, 'Connector kind differs')
    for key, default in defaults.items():
        value.setdefault(key, copy.deepcopy(default))
    value.setdefault('extensions', {})
    _need(type(value['extensions']) is dict, 'extensions must be an object')
    # Extensions are annotations only; required semantics need a versioned field.
    for key in value['extensions']:
        _need(':' in key and len(key) <= 200, 'Extension keys must be namespaced')


def _reason(value, required=False):
    _need(isinstance(value, str) and len(value) <= 4000, 'Invalid reason')
    if required:
        _text(value, 'reason')


def _revisions(value):
    _need(type(value) is dict and len(value) <= LIMIT, 'Expected revision map')
    for key, revision in value.items():
        _id(key, 'record id')
        _integer(revision, 'record revision', 1)


def _versions(value):
    _need(type(value) is dict and len(value) <= LIMIT, 'Expected version map')
    for key, version in value.items():
        _id(key)
        _text(version, 'version')


def _adapter(value, binary=False):
    _object(value, ('id', 'version', 'sha256') if binary else ('id', 'version'))
    _id(value['id'])
    _text(value['version'], 'version')
    if binary:
        _digest(value['sha256'])


def _capabilities(d):
    _record(d, 'AdapterCapabilities', ('adapter', 'provenance', 'capabilities'))
    _adapter(d['adapter'])
    _choice(d['provenance'], ('actual_emulator', 'synthetic'), 'provenance')
    _object(d['capabilities'], (), CAPABILITIES)
    for key, value in d['capabilities'].items():
        _need(type(value) is bool, key + ': capability must be boolean')
    for key in CAPABILITIES:
        d['capabilities'].setdefault(key, False)


def _case(d):
    _record(d, 'CaseSpec', ('case_id', 'coverage_scope', 'required_capabilities'),
            dict(record_ids=[], message_id=None, page=None, window_id=None, context_id=None, variant_id=None))
    for key in ('case_id', 'coverage_scope'):
        _id(d[key], key)
    _ids(d['record_ids'], 'record_ids')
    for key in ('message_id', 'window_id', 'context_id', 'variant_id'):
        _id(d[key], key, nullable=True)
    if d['page'] is not None:
        _integer(d['page'], 'page')
    _ids(d['required_capabilities'], 'required_capabilities')
    if set(d['required_capabilities']) - set(CAPABILITIES):
        raise UnsupportedCapability('Unknown required capability')


def _binding(d):
    _record(d, 'RunBinding', ('build_id', 'artifacts', 'snapshot', 'records', 'scenario_sha256',
            'configuration_sha256', 'adapter', 'emulator', 'expectation_sha256', 'detectors'))
    _id(d['build_id'], 'build_id')
    _need(type(d['artifacts']) is dict and 0 < len(d['artifacts']) <= LIMIT, 'Pinned artifacts required')
    for key, digest in d['artifacts'].items():
        _id(key, 'artifact role')
        _digest(digest)
    for key in ('snapshot', 'scenario_sha256', 'configuration_sha256', 'expectation_sha256'):
        _digest(d[key], key)
    _revisions(d['records'])
    _adapter(d['adapter'])
    _adapter(d['emulator'], binary=True)
    _versions(d['detectors'])


def _evidence(d):
    _record(d, 'EvidenceRef', ('evidence_id', 'sha256', 'media_type', 'byte_length', 'provenance'),
            dict(integrity='unverified', retention='referenced'))
    _id(d['evidence_id'], 'evidence_id')
    _digest(d['sha256'])
    _text(d['media_type'], 'media_type')
    _integer(d['byte_length'], 'byte_length')
    _choice(d['integrity'], ('verified', 'unverified', 'missing', 'mismatch'), 'integrity')
    _choice(d['retention'], ('referenced', 'pinned', 'disposable'), 'retention')
    p = d['provenance']
    _object(p, ('producer', 'method', 'run_id', 'case_id'))
    _id(p['producer'], 'producer')
    _choice(p['method'], METHODS, 'method')
    _id(p['run_id'], 'run_id', nullable=True)
    _id(p['case_id'], 'case_id', nullable=True)


def _scene(d):
    _record(d, 'SceneHandle', ('scene_id', 'binding', 'reach_method', 'arrival_assertions', 'status'),
            dict(checkpoint=None, reason=''))
    _id(d['scene_id'], 'scene_id')
    d['binding'] = validate('RunBinding', d['binding'])
    _choice(d['reach_method'], REACH_METHODS, 'reach_method')
    _ids(d['arrival_assertions'], 'arrival_assertions')
    _need(bool(d['arrival_assertions']), 'Explicit arrival assertions required')
    _choice(d['status'], ('ready', 'incompatible', 'unsupported', 'failed', 'unknown'), 'scene status')
    _reason(d['reason'], d['status'] != 'ready')
    if d['checkpoint'] is not None:
        d['checkpoint'] = validate('EvidenceRef', d['checkpoint'])
    if d['reach_method'] in ('emulator_state', 'in_game_save'):
        _need(d['checkpoint'] is not None, 'Checkpoint reference required')
    if d['reach_method'] == 'cold_boot_navigation':
        _need(d['checkpoint'] is None, 'Cold boot cannot restore a checkpoint')


def _observation(d):
    _record(d, 'CaseObservation', ('observation_id', 'run_id', 'case_id', 'case_sha256', 'binding',
            'provenance', 'method', 'reach_method', 'execution', 'assertion', 'validity', 'frames', 'captures'),
            dict(reason='', glyphs=None, resources=None, controls={}))
    for key in ('observation_id', 'run_id', 'case_id'):
        _id(d[key], key)
    _digest(d['case_sha256'], 'case_sha256')
    d['binding'] = validate('RunBinding', d['binding'])
    _choice(d['provenance'], ('actual_emulator', 'synthetic'), 'provenance')
    _need(d['method'] == {'actual_emulator': 'automated_runtime', 'synthetic': 'synthetic'}[d['provenance']],
          'Method differs from adapter provenance')
    _choice(d['reach_method'], REACH_METHODS, 'reach_method')
    _choice(d['execution'], EXECUTIONS, 'execution')
    _choice(d['assertion'], ASSERTIONS, 'assertion')
    _choice(d['validity'], VALIDITIES, 'validity')
    _reason(d['reason'], d['execution'] in ('failed', 'interrupted', 'unsupported', 'excluded')
            or d['assertion'] in ('failed', 'unknown', 'unsupported') or d['validity'] != 'current')
    _integer(d['frames'], 'frames')
    if d['assertion'] == 'passed':
        _need(d['execution'] == 'completed', 'Partial/unexecuted case cannot pass')
    if d['execution'] in ('not_run', 'excluded', 'unsupported'):
        _need(d['assertion'] in ('not_assessed', 'unsupported') and d['frames'] == 0 and not d['captures'],
              'Unexecuted case cannot claim captured/asserted results')
    _list(d['captures'], 'captures')
    evidence_ids = []
    for capture in d['captures']:
        _object(capture, ('frame', 'evidence'))
        _integer(capture['frame'], 'capture frame', 1)
        _need(capture['frame'] <= d['frames'], 'Capture outside observed frames')
        capture['evidence'] = validate('EvidenceRef', capture['evidence'])
        e = capture['evidence']
        p = e['provenance']
        _need(p['run_id'] == d['run_id'] and p['case_id'] == d['case_id'] and p['method'] == d['method'],
              'Capture provenance differs from observation')
        evidence_ids.append(e['evidence_id'])
        if d['validity'] == 'current' and d['assertion'] == 'passed':
            _need(e['integrity'] == 'verified', 'Current pass needs checked evidence')
    _ids(evidence_ids, 'capture references')
    if d['assertion'] == 'passed':
        _need(d['frames'] > 0 and bool(d['captures']), 'Pass needs observed frames/captures')
    _object(d['controls'], (), ('page_complete', 'line_advanced', 'scrolled', 'input_wait', 'terminated'))
    for key, value in d['controls'].items():
        _need(value is None or type(value) is bool, 'Control observation must be boolean or unknown')
    if d['glyphs'] is not None:
        _list(d['glyphs'], 'glyphs')
        for glyph in d['glyphs']:
            _object(glyph, ('glyph_id', 'frame', 'x', 'y', 'width', 'height'))
            _id(glyph['glyph_id'], 'glyph_id')
            _integer(glyph['frame'], 'glyph frame', 1)
            _need(glyph['frame'] <= d['frames'], 'Glyph outside observed frames')
            for key in ('x', 'y'):
                _integer(glyph[key], key, -65536)
            for key in ('width', 'height'):
                _integer(glyph[key], key, 1)
    if d['resources'] is not None:
        _need(type(d['resources']) is dict, 'Expected resource observations')
        for key, value in d['resources'].items():
            _id(key, 'resource')
            _integer(value, 'resource count')


def _finding(d):
    _record(d, 'DetectorFinding', ('finding_id', 'observation_id', 'case_id', 'case_sha256', 'binding',
            'detector_id', 'detector_version', 'expectation_id', 'status', 'evidence_ids'),
            dict(reason='', region=None, control=None))
    for key in ('finding_id', 'observation_id', 'case_id', 'detector_id', 'expectation_id'):
        _id(d[key], key)
    _digest(d['case_sha256'])
    _text(d['detector_version'], 'detector_version')
    d['binding'] = validate('RunBinding', d['binding'])
    _need(d['binding']['detectors'].get(d['detector_id']) == d['detector_version'],
          'Detector version not pinned in binding')
    _choice(d['status'], ('passed', 'failed', 'unknown', 'unsupported'), 'finding status')
    _reason(d['reason'], d['status'] != 'passed')
    _ids(d['evidence_ids'], 'evidence_ids')
    if d['status'] in ('passed', 'failed'):
        _need(bool(d['evidence_ids']), 'Definite findings need evidence')
    if d['region'] is not None:
        _need(type(d['region']) is list and len(d['region']) == 4, 'Expected x,y,width,height')
        for v in d['region'][:2]:
            _integer(v, 'region origin', -65536)
        for v in d['region'][2:]:
            _integer(v, 'region size', 1)
    _id(d['control'], 'control', nullable=True)


def _coverage(d):
    _record(d, 'CoverageReport', ('report_id', 'binding', 'scope', 'sections', 'gap_candidates'))
    _id(d['report_id'], 'report_id')
    d['binding'] = validate('RunBinding', d['binding'])
    scope = d['scope']
    _object(scope, ('id', 'description', 'case_ids', 'case_digests', 'extraction_completeness', 'extraction_basis'))
    _id(scope['id'])
    _text(scope['description'], 'scope description')
    _ids(scope['case_ids'], 'scope case_ids')
    _need(type(scope['case_digests']) is dict and set(scope['case_digests']) == set(scope['case_ids']),
          'Explicit case definitions required for the full scope')
    for digest in scope['case_digests'].values():
        _digest(digest, 'case digest')
    _choice(scope['extraction_completeness'], ('unknown', 'partial', 'declared_complete'), 'extraction completeness')
    _reason(scope['extraction_basis'], scope['extraction_completeness'] != 'unknown')
    _list(d['sections'], 'sections')
    seen = set()
    for section in d['sections']:
        _object(section, ('scope_kind', 'method', 'rows', 'denominator', 'counts', 'passed_percent'))
        _choice(section['scope_kind'], SCOPE_KINDS, 'scope_kind')
        _choice(section['method'], METHODS, 'method')
        pair = (section['scope_kind'], section['method'])
        _need(pair not in seen, 'Duplicate coverage section')
        seen.add(pair)
        if pair[0] == 'normal_gameplay':
            _need(pair[1] in ('automated_runtime', 'reported_human', 'hardware'), 'Gameplay needs observed execution')
        if pair[0] == 'editorial':
            _need(pair[1] in ('manual_review', 'reported_human'), 'Pixels cannot certify editorial review')
        if pair[0] == 'hardware':
            _need(pair[1] == 'hardware', 'Emulation cannot certify hardware')
        _list(section['rows'], 'rows')
        counts = dict.fromkeys(COVERAGE_STATUSES, 0)
        ids = []
        for row in section['rows']:
            _object(row, ('case_id', 'status', 'reason', 'observation_ids', 'finding_ids'))
            _id(row['case_id'], 'case_id')
            ids.append(row['case_id'])
            _choice(row['status'], COVERAGE_STATUSES, 'coverage status')
            _reason(row['reason'], row['status'] in ('failed', 'stale', 'interrupted', 'excluded', 'unsupported', 'unknown'))
            _ids(row['observation_ids'], 'observation_ids')
            _ids(row['finding_ids'], 'finding_ids')
            if row['status'] in ('passed', 'failed'):
                _need(bool(row['observation_ids']), 'Assessed row needs evidence references')
            counts[row['status']] += 1
        _ids(ids, 'coverage rows')
        _need(set(ids) == set(scope['case_ids']), 'Every scoped case must remain in the denominator')
        _integer(section['denominator'], 'denominator')
        _need(section['denominator'] == len(ids), 'Coverage denominator differs')
        _object(section['counts'], COVERAGE_STATUSES)
        for key, count in section['counts'].items():
            _integer(count, 'coverage count')
        _need(section['counts'] == counts, 'Coverage counts differ from rows')
        expected = round(100 * counts['passed'] / len(ids), 2) if ids else None
        actual = section['passed_percent']
        _need((actual is None if expected is None else type(actual) in (int, float) and actual == expected),
              'Empty scope is unknown; percentages must use the entire declared scope')
    _list(d['gap_candidates'], 'gap_candidates')
    for gap in d['gap_candidates']:
        _object(gap, ('kind', 'observation_ids', 'record_ids', 'reason'))
        _choice(gap['kind'], ('uncatalogued', 'unexercised', 'unmapped', 'preserved_source', 'graphics_text'), 'gap kind')
        _ids(gap['observation_ids'], 'gap observations')
        _ids(gap['record_ids'], 'gap records')
        _reason(gap['reason'], True)


def _impact(d):
    _record(d, 'ChangeImpactPlan', ('plan_id', 'binding', 'baseline_binding', 'case_ids', 'dependency_revisions',
            'selected', 'deferred', 'full_sweep_required', 'additional_checks'))
    _id(d['plan_id'], 'plan_id')
    d['binding'] = validate('RunBinding', d['binding'])
    if d['baseline_binding'] is not None:
        d['baseline_binding'] = validate('RunBinding', d['baseline_binding'])
    _ids(d['case_ids'], 'plan case_ids')
    if d['dependency_revisions'] is not None:
        _versions(d['dependency_revisions'])
    _need(type(d['full_sweep_required']) is bool, 'Expected full_sweep_required boolean')
    selected = []
    deferred = []
    for key, ids in (('selected', selected), ('deferred', deferred)):
        _list(d[key], key)
        for row in d[key]:
            _object(row, ('case_id', 'reason'))
            _id(row['case_id'])
            _reason(row['reason'], True)
            ids.append(row['case_id'])
        _ids(ids, key)
    _need(not set(selected) & set(deferred) and set(selected + deferred) == set(d['case_ids']),
          'Selection must partition the full scope')
    if d['baseline_binding'] is None or not d['dependency_revisions']:
        _need(d['full_sweep_required'], 'Unknown dependencies/baseline require full sweep')
    if d['full_sweep_required']:
        _need(not deferred, 'Full sweep cannot defer cases')
    _ids(d['additional_checks'], 'additional_checks')


_VALIDATORS = {
    'AdapterCapabilities': _capabilities, 'CaseSpec': _case, 'RunBinding': _binding,
    'EvidenceRef': _evidence, 'SceneHandle': _scene, 'CaseObservation': _observation,
    'DetectorFinding': _finding, 'CoverageReport': _coverage, 'ChangeImpactPlan': _impact,
}


def validate(kind, value):
    """Return a detached, normalized JSON dictionary, or raise ContractError.

    Unknown fields fail closed except namespaced, non-semantic `extensions`.
    Missing optional fields receive documented defaults; the caller is unmodified.
    """
    _need(isinstance(kind, str) and kind in _VALIDATORS, 'Unknown connector kind')
    _json(value)
    result = copy.deepcopy(value)
    _VALIDATORS[kind](result)
    return result


def contract_digest(kind, value):
    """Digest normalized semantic input, conservatively including annotations."""
    data = json.dumps(validate(kind, value), sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def binding_changes(previous, current):
    """Changed top-level binding fields; never changes or certifies stored evidence."""
    a, b = validate('RunBinding', previous), validate('RunBinding', current)
    return sorted(k for k in a if a[k] != b[k])


def require_capabilities(case, capabilities):
    c, a = validate('CaseSpec', case), validate('AdapterCapabilities', capabilities)
    missing = sorted(k for k in c['required_capabilities'] if not a['capabilities'][k])
    if missing:
        raise UnsupportedCapability('Required capabilities unavailable: ' + ', '.join(missing))
    return a


def check_observation(case, observation, capabilities, *, expected_binding=None):
    """Validate cross-record identity/capability consistency, not actual execution."""
    c = validate('CaseSpec', case)
    o = validate('CaseObservation', observation)
    a = validate('AdapterCapabilities', capabilities)
    _need(o['case_id'] == c['case_id'] and o['case_sha256'] == contract_digest('CaseSpec', c),
          'Case identity/definition differs')
    _need(set(c['record_ids']) <= set(o['binding']['records']), 'Case record revisions missing from binding')
    _need(a['adapter'] == o['binding']['adapter'] and a['provenance'] == o['provenance'], 'Adapter identity/provenance differs')
    if o['execution'] not in ('not_run', 'unsupported', 'excluded'):
        require_capabilities(c, a)
    observed = {'capture_frames': bool(o['captures']), 'observe_glyphs': o['glyphs'] is not None,
                'observe_resources': o['resources'] is not None,
                'page_advance': o['controls'].get('line_advanced') is not None or o['controls'].get('page_complete') is not None,
                'native_scroll': o['controls'].get('scrolled') is not None,
                'input': o['controls'].get('input_wait') is not None}
    if o['execution'] not in ('not_run', 'unsupported', 'excluded'):
        observed.update(restore_state=o['reach_method'] == 'emulator_state',
                        game_save=o['reach_method'] == 'in_game_save', debug_access=o['reach_method'] == 'debug_injection')
    _need(all(not used or a['capabilities'][name] for name, used in observed.items()),
          'Observation claims unavailable instrumentation')
    if expected_binding is not None:
        changed = binding_changes(o['binding'], expected_binding)
        _need(not changed or o['validity'] == 'stale', 'Changed binding must be explicitly stale')
    return o


def check_finding(finding, observation):
    """Validate finding links and versions; no detector is executed."""
    f, o = validate('DetectorFinding', finding), validate('CaseObservation', observation)
    for key in ('observation_id', 'case_id', 'case_sha256'):
        _need(f[key] == o[key], 'Finding refers to a different observation/case')
    _need(not binding_changes(f['binding'], o['binding']), 'Finding binding differs')
    _need(set(f['evidence_ids']) <= {c['evidence']['evidence_id'] for c in o['captures']}, 'Finding evidence missing')
    if f['status'] == 'passed':
        _need(o['execution'] == 'completed', 'Detector cannot pass incomplete execution')
    return f


def verify_evidence_bytes(reference, data):
    """Check supplied bytes only. The caller owns safe resolution and storage."""
    r = validate('EvidenceRef', reference)
    _need(type(data) is bytes, 'Expected evidence bytes')
    return len(data) == r['byte_length'] and hashlib.sha256(data).hexdigest() == r['sha256']


def observation_status(observation, expected_binding):
    """Classify one supplied observation; do not aggregate or select latest runs."""
    o = validate('CaseObservation', observation)
    if binding_changes(o['binding'], expected_binding) or o['validity'] == 'stale':
        return 'stale'
    if o['validity'] != 'current':
        return 'unknown'
    if o['execution'] != 'completed':
        return {'not_run': 'untested', 'running': 'in_progress', 'failed': 'failed',
                'interrupted': 'interrupted', 'unsupported': 'unsupported', 'excluded': 'excluded'}[o['execution']]
    return {'passed': 'passed', 'failed': 'failed', 'not_assessed': 'unknown',
            'unknown': 'unknown', 'unsupported': 'unsupported'}[o['assertion']]


FINDING_ID_ALGORITHM = 'patchquest-detector-v1'


def expectation_capture_frame(check, schema_version, frames):
    """Resolve an image check's frame without changing an observation.

    Schema 1 keeps its final-frame default. Schema 2 image checks require an
    explicit frame; a valid selector beyond the observed run is unavailable,
    not permission to substitute another capture. ``frames=None`` validates
    selector syntax before an observation exists.
    """
    _need(type(schema_version) is int and schema_version in (1, 2),
          'Unsupported expectation version')
    _need(type(check) is dict, 'Expected check object')
    if frames is not None:
        _integer(frames, 'observed frames')
    if schema_version == 2 and check.get('kind') == 'image_region':
        _need('capture' in check, 'Explicit image capture selector required')
        _object(check['capture'], ('frame',))
        frame = check['capture']['frame']
        _integer(frame, 'capture selector frame')
        return frame if frames is None or frame <= frames else None
    _need('capture' not in check, 'Capture selector requires a schema-2 image check')
    return frames


def _expectation_case(value):
    """Check common plan identity; detector owners validate check parameters."""
    _object(value, ('schema_version', 'expectation_id', 'case_sha256', 'basis', 'checks', 'exceptions'))
    _need(type(value['schema_version']) is int and value['schema_version'] in (1, 2),
          'Unsupported expectation version')
    _id(value['expectation_id'], 'expectation_id')
    _digest(value['case_sha256'])
    _object(value['basis'], ('method', 'reference_sha256', 'reason'))
    _choice(value['basis']['method'], ('independent_inspection', 'synthetic_control'), 'expectation basis')
    _digest(value['basis']['reference_sha256'])
    _text(value['basis']['reason'], 'expectation basis reason')
    _list(value['checks'], 'expectation checks')
    _need(0 < len(value['checks']) <= 1000, 'Complete nonempty check plan required')
    seen = set()
    for check in value['checks']:
        _need(type(check) is dict and {'id', 'kind'} <= set(check), 'Check identity/kind required')
        _text(check['id'], 'check id')
        _id(check['kind'], 'detector id')
        expectation_capture_frame(check, value['schema_version'], None)
        _need(check['id'] not in seen, 'Duplicate expectation check')
        seen.add(check['id'])
    _list(value['exceptions'], 'exceptions')


def expectation_manifest_data(value):
    """Validate the shared v1 envelope without normalizing its pinned contents.

    Check-specific parameters remain owned by the detector. This function does
    not execute checks, verify independent expectations or load private files.
    """
    _json(value)
    _object(value, ('schema_version', 'kind', 'finding_id_algorithm', 'cases'))
    _need(type(value['schema_version']) is int and value['schema_version'] == 1,
          'Unsupported expectation manifest version')
    _need(value['kind'] == 'RuntimeExpectationManifest', 'Unknown expectation manifest kind')
    _need(value['finding_id_algorithm'] == FINDING_ID_ALGORITHM, 'Unknown finding ID algorithm')
    _need(type(value['cases']) is dict and 0 < len(value['cases']) <= 10000,
          'Explicit nonempty bounded expectation cases required')
    for digest, plan in value['cases'].items():
        _digest(digest)
        _expectation_case(plan)
        _need(plan['case_sha256'] == digest, 'Manifest case key differs from plan')
    return copy.deepcopy(value)


def _expectation_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


def required_finding_plan(observation, expectations):
    """Derive every required result from the full pinned document, never a subset.

    Legacy single-case v1 plans explicitly use patchquest-detector-v1 identities.
    Returned keys are semantic finding IDs, not diagnostic extension fields.
    """
    o = validate('CaseObservation', observation)
    _json(expectations)
    if type(expectations) is dict and 'kind' in expectations:
        doc = expectation_manifest_data(expectations)
        _need(o['case_sha256'] in doc['cases'], 'Observation case missing from expectation manifest')
        plan = doc['cases'][o['case_sha256']]
    else:
        _expectation_case(expectations)
        doc = expectations
        plan = doc
    _need(plan['case_sha256'] == o['case_sha256'], 'Expectation case definition differs')
    pin = _expectation_hash(doc)
    _need(pin == o['binding']['expectation_sha256'], 'Expectation digest differs from RunBinding')
    result = {}
    for check in plan['checks']:
        detector = check['kind']
        _need(detector in o['binding']['detectors'], 'Required detector version not pinned')
        if detector == 'image_region':
            version = '2' if plan['schema_version'] == 2 else '1'
            _need(o['binding']['detectors'][detector] == version,
                  'Image detector version differs from expectation schema')
        identity = 'detector-' + _expectation_hash([o['observation_id'], check['id'], pin])
        result[identity] = dict(detector_id=detector,
            detector_version=o['binding']['detectors'][detector], expectation_id=plan['expectation_id'])
    return result


def assess_observation_findings(observation, expected_binding, findings, *, expectations):
    """Assess linked results without rewriting capture history or resolving bytes.

    Missing/unknown/unsupported requirements stay explicit even if a separate
    current finding confirms failure. Consumers must recheck actual evidence
    bytes and independently validate the checks before claiming runtime proof.
    """
    o = validate('CaseObservation', observation)
    required = required_finding_plan(o, expectations)
    plan = (expectations['cases'][o['case_sha256']]
            if expectations.get('kind') == 'RuntimeExpectationManifest' else expectations)
    supplied = {}
    captures = {c['evidence']['evidence_id']: c for c in o['captures']}
    checks = dict(zip(required, plan['checks']))
    for value in findings:
        f = check_finding(value, o)
        key = f['finding_id']
        _need(key in required and key not in supplied, 'Unexpected or duplicate required finding')
        _need(all(f[k] == v for k, v in required[key].items()), 'Finding differs from complete check plan')
        if f['status'] in ('passed', 'failed'):
            _need(o['provenance'] != 'actual_emulator' or plan['basis']['method'] == 'independent_inspection',
                  'Synthetic expectations cannot calibrate actual emulator evidence')
            check = checks[key]
            frame = expectation_capture_frame(check, plan['schema_version'], o['frames'])
            if plan['schema_version'] == 2 and check['kind'] == 'image_region':
                selected = [c for c in o['captures'] if c['frame'] == frame]
                _need(len(selected) == 1 and
                      f['evidence_ids'] == [selected[0]['evidence']['evidence_id']] and
                      selected[0]['evidence']['media_type'] == 'image/png',
                      'Definite image assessment requires one exact selected PNG capture')
            _need(all(captures[e]['evidence']['integrity'] == 'verified' for e in f['evidence_ids']) and
                  any(captures[e]['frame'] == frame for e in f['evidence_ids']),
                  'Definite assessment requires verified selected-frame evidence')
        supplied[key] = f
    result = dict(status=observation_status(o, expected_binding),
        required_finding_ids=sorted(required), missing_finding_ids=sorted(set(required) - set(supplied)))
    for status in ('failed', 'unknown', 'unsupported'):
        result[status + '_finding_ids'] = sorted(k for k, f in supplied.items() if f['status'] == status)
    # Preserve stale/invalid/native-failure/incomplete and explicit uncertainty.
    if (o['validity'] != 'current' or binding_changes(o['binding'], expected_binding) or
            o['execution'] != 'completed' or o['assertion'] not in ('not_assessed', 'passed')):
        return result
    if result['failed_finding_ids']:
        result['status'] = 'failed'
    elif result['missing_finding_ids'] or result['unknown_finding_ids']:
        result['status'] = 'unknown'
    elif result['unsupported_finding_ids']:
        result['status'] = 'unsupported'
    else:
        result['status'] = 'passed'
    return result


def check_coverage_runtime_links(report, observations, findings=(), *, expectations=None):
    """Check runtime/synthetic references; other assessment methods need their owners.

    Does not select observations, run detectors or verify artifact files. #7 owns
    reconciliation, latest-run policy and assessment integration.
    """
    r = validate('CoverageReport', report)
    _list(observations, 'observations')
    by_id = {}
    for value in observations:
        o = validate('CaseObservation', value)
        _need(o['observation_id'] not in by_id, 'Duplicate observation id')
        by_id[o['observation_id']] = o
    by_finding = {}
    for value in findings:
        f = validate('DetectorFinding', value)
        _need(f['finding_id'] not in by_finding, 'Duplicate finding id')
        _need(f['observation_id'] in by_id, 'Finding observation missing')
        by_finding[f['finding_id']] = check_finding(f, by_id[f['observation_id']])
    for section in r['sections']:
        if section['method'] not in ('automated_runtime', 'synthetic'):
            continue
        for row in section['rows']:
            statuses = []
            finding_statuses = []
            for key in row['observation_ids']:
                _need(key in by_id, 'Referenced observation missing')
                o = by_id[key]
                _need(o['case_id'] == row['case_id'], 'Coverage case association differs')
                _need(o['method'] == section['method'], 'Synthetic evidence cannot satisfy actual runtime')
                if section['scope_kind'] == 'normal_gameplay':
                    _need(o['reach_method'] in ('cold_boot_navigation', 'in_game_save'),
                          'Debug/state shortcuts cannot satisfy normal-route coverage')
                if expectations is None:
                    status = observation_status(o, r['binding'])
                else:
                    selected = [by_finding[f] for f in row['finding_ids'] if f in by_finding and
                                by_finding[f]['observation_id'] == key]
                    status = assess_observation_findings(o, r['binding'], selected,
                        expectations=expectations)['status']
                if o['case_sha256'] != r['scope']['case_digests'][row['case_id']]:
                    status = 'stale'
                statuses.append(status)
            for key in row['finding_ids']:
                _need(key in by_finding, 'Referenced finding missing')
                f = by_finding[key]
                _need(f['observation_id'] in row['observation_ids'], 'Finding refers outside row observations')
                finding_statuses.append(f['status'])
            if row['status'] == 'passed':
                _need(bool(statuses) and all(s == 'passed' for s in statuses + finding_statuses),
                      'Runtime pass lacks current passing evidence')
            if row['status'] == 'failed':
                _need('failed' in statuses or ('failed' in finding_statuses and
                      all(s in ('passed', 'failed') for s in statuses)), 'Runtime failure lacks current failed evidence')
    return r


def binding_from_runtime_report(report, *, adapter, emulator_id, emulator_version,
                                expectation_sha256, detectors):
    """Adapt legacy report identity fields without inferring missing new evidence.

    Explicit caller-supplied versions/expectations are mandatory. This does not
    convert a legacy report into a CaseObservation or certify its assertions.
    """
    _need(type(report) is dict and type(report.get('schema')) is int and report['schema'] == 1,
          'Expected runtime report schema 1')
    try:
        result = dict(schema_version=1, kind='RunBinding', build_id=report['build_id'],
            artifacts={'rom': report['rom_sha256']}, snapshot=report['snapshot'], records=report['records'],
            scenario_sha256=report['scenario_sha256'], configuration_sha256=report['configuration_sha256'],
            adapter=adapter, emulator=dict(id=emulator_id, version=emulator_version, sha256=report['emulator']['sha256']),
            expectation_sha256=expectation_sha256, detectors=detectors)
    except (KeyError, TypeError) as error:
        raise ContractError('Legacy runtime report lacks pinned identity fields') from error
    return validate('RunBinding', result)

"""Private, scoped verification plans and readiness summaries.

Reuses the state metadata/event journal and registered runtime reports. No schema
migration, emulator execution, translation edits or publication takes place here.
"""
import hashlib
import json
import re
from datetime import datetime

from .core.context import confined
from .state import Conflict, canonical, identity, now, text

PLAN_KEY = 'verification.plan.v1'
REPORT_PATH = '.patchquest/readiness-summary.json'
STAGES = ('language_review', 'graphics_layout', 'gameplay', 'release_preparation')
METHODS = ('static', 'manual_review', 'reported_human', 'hardware', 'automated_runtime')
OUTCOMES = ('passed', 'failed', 'in_progress')


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected SHA-256')
    return value


def _load(db, key, default):
    row = db.execute('SELECT value FROM metadata WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else default


def _plan(db):
    return _load(db, PLAN_KEY, dict(schema_version=1, revision=0, updated_at=None,
                                   build_id='', next_milestone='', areas=[]))


def plan(store):
    with store.connection() as db:
        return _plan(db)


def _save(store, db, key, value, kind):
    db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (key, canonical(value)))
    store._event(db, kind, value)


def _expect(actual, expected):
    if type(expected) is not int or actual != expected:
        raise Conflict('Verification state changed; reload and reconcile')


def _area(data):
    if not isinstance(data, dict) or set(data) - {'id', 'label', 'stage', 'expectation',
            'method', 'record_ids', 'scenario_sha256', 'configuration_sha256', 'assertions'}:
        raise ValueError('Invalid verification area')
    result = {k: text(data.get(k, ''), k, 4000) for k in ('label', 'expectation')}
    if not all(v.strip() for v in result.values()):
        raise ValueError('Label and independently justified expectation required')
    result.update(id=identity(data.get('id')), stage=data.get('stage'), method=data.get('method'))
    if result['stage'] not in STAGES or result['method'] not in METHODS:
        raise ValueError('Invalid verification stage or method')
    if result['stage'] == 'language_review' and result['method'] not in ('manual_review', 'reported_human'):
        raise ValueError('Language review requires an explicit editorial assessment')
    if result['stage'] == 'gameplay' and result['method'] not in ('automated_runtime', 'reported_human', 'hardware'):
        raise ValueError('Gameplay verification requires observed execution')
    ids = data.get('record_ids', [])
    if not isinstance(ids, list) or len(ids) > 500 or len(set(ids)) != len(ids):
        raise ValueError('Invalid verification record scope')
    result['record_ids'] = sorted(identity(k) for k in ids)
    if result['method'] == 'automated_runtime':
        if result['stage'] not in ('graphics_layout', 'gameplay'):
            raise ValueError('Pixel assertions cannot certify language or release preparation')
        result['scenario_sha256'] = _digest(data.get('scenario_sha256'))
        result['configuration_sha256'] = _digest(data.get('configuration_sha256'))
        labels = data.get('assertions')
        if not isinstance(labels, list) or not labels or len(labels) > 100:
            raise ValueError('Explicit assertion labels required')
        result['assertions'] = sorted(set(identity(k) for k in labels))
    elif any(k in data for k in ('scenario_sha256', 'configuration_sha256', 'assertions')):
        raise ValueError('Runtime identities require the automated_runtime method')
    return result


def put_plan(store, data, expected, actor='agent'):
    if not isinstance(data, dict) or set(data) - {'build_id', 'areas', 'next_milestone'}:
        raise ValueError('Invalid verification plan')
    areas = data.get('areas')
    if not isinstance(areas, list) or len(areas) > 500:
        raise ValueError('Expected up to 500 explicitly scoped areas')
    areas = [_area(a) for a in areas]
    if len({a['id'] for a in areas}) != len(areas):
        raise ValueError('Duplicate verification area')
    build_id = data.get('build_id', '')
    if build_id:
        identity(build_id)
    elif not isinstance(build_id, str):
        raise ValueError('Invalid build selection')
    result = dict(schema_version=1, revision=expected + 1 if type(expected) is int else 0,
                  updated_at=now(), actor=text(actor, 'actor', 200), build_id=build_id,
                  next_milestone=text(data.get('next_milestone', ''), 'milestone', 4000), areas=areas)
    with store.connection() as db, store.transaction(db):
        _expect(_plan(db)['revision'], expected)
        if build_id and not db.execute('SELECT 1 FROM builds WHERE id=?', (build_id,)).fetchone():
            raise KeyError('Unknown selected build')
        for a in areas:
            for key in a['record_ids']:
                store._get(db, key)
        _save(store, db, PLAN_KEY, result, 'verification-plan')
    return result


def _build(store, db, key):
    row = db.execute('SELECT payload FROM builds WHERE id=?', (key,)).fetchone()
    if not row:
        raise KeyError('Unknown build')
    build = json.loads(row[0])
    snapshot = db.execute('SELECT payload FROM snapshots WHERE digest=?', (build.get('snapshot'),)).fetchone()
    if not snapshot or hashlib.sha256(snapshot[0].encode('utf8')).hexdigest() != build['snapshot']:
        raise ValueError('Build lacks an intact immutable snapshot')
    artifacts = build.get('artifacts')
    if not isinstance(artifacts, dict) or not artifacts or len(artifacts) > 32:
        raise ValueError('Build needs explicit artifact paths')
    hashes = {}
    for name, value in artifacts.items():
        identity(name)
        if not isinstance(value, str) or not value:
            raise ValueError('Expected artifact path')
        path = store.context.output.check(value)
        # Stream explicitly selected output artifacts; never discover source ROMs.
        h = hashlib.sha256()
        with path.open('rb') as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                h.update(chunk)
        hashes[name] = h.hexdigest()
    binding = dict(snapshot=build['snapshot'], artifacts=hashes)
    records = {r['id']: r['revision'] for r in json.loads(snapshot[0])['records']}
    return build, binding, records


def _observation_key(build_id, area_id):
    return 'verification.observation.v1.' + _hash([build_id, area_id])


def observe(store, area_id, build_id, status, reference, expected, plan_revision, actor='agent'):
    """Record an explicit assessment, not an inferred human or release approval."""
    if status not in OUTCOMES or not text(reference, 'reference', 4000).strip():
        raise ValueError('Outcome and evidence reference required')
    identity(area_id)
    identity(build_id)
    with store.connection() as db, store.transaction(db):
        p = _plan(db)
        _expect(p['revision'], plan_revision)
        area = next((a for a in p['areas'] if a['id'] == area_id), None)
        if area is None:
            raise KeyError('Unknown verification area')
        if area['method'] == 'automated_runtime':
            raise ValueError('Register runtime evidence with the existing runner')
        build, binding, records = _build(store, db, build_id)
        if status == 'passed' and build['status'] != 'validated':
            raise ValueError('Passing assessments require a validated build')
        if any(k not in records for k in area['record_ids']):
            raise ValueError('Area records missing from build snapshot')
        key = _observation_key(build_id, area_id)
        previous = _load(db, key, {'revision': 0})
        _expect(previous['revision'], expected)
        value = dict(revision=expected + 1, plan_revision=plan_revision, area_id=area_id,
                     build_id=build_id, definition_sha256=_hash(area), binding=binding,
                     status=status, reference=reference, method=area['method'],
                     actor=text(actor, 'actor', 200), assessed_at=now())
        _save(store, db, key, value, 'verification-observation')
    return value


def history(store, after=0, limit=100):
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Invalid verification history range')
    with store.connection() as db:
        return [dict(seq=r['seq'], kind=r['kind'], data=json.loads(r['payload'])) for r in db.execute(
            "SELECT * FROM events WHERE kind IN ('verification-plan','verification-observation') AND seq>? ORDER BY seq LIMIT ?",
            (after, limit))]


def _runtime(area, build, binding, records, heads, store):
    """Only exact planned assertions from an intact registered real run qualify."""
    evidence = []
    for run in build.get('validation', {}).get('runtime', []):
        if (run.get('scenario_sha256') != area['scenario_sha256'] or
                run.get('configuration_sha256') != area['configuration_sha256']):
            continue
        result = dict(kind=run.get('level'), status=run.get('status'),
                      report_sha256=run.get('report_sha256'), eligible=False, current=False)
        evidence.append(result)
        try:
            path = store.context.output.check(run['report'])
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != _digest(run['report_sha256']):
                raise ValueError('Runtime report changed')
            actual = json.loads(raw)
            for key in ('snapshot', 'rom_sha256', 'records', 'scenario_sha256',
                        'configuration_sha256', 'level', 'status', 'assertions', 'emulator'):
                if actual.get(key) != run.get(key):
                    raise ValueError('Registered runtime identity changed')
            if actual.get('build_id') != build['id'] or actual.get('human_accepted') is not False:
                raise ValueError('Runtime provenance differs')
            finished = datetime.fromisoformat(actual['finished'])
            if finished.utcoffset() is None:
                raise ValueError('Runtime timestamp must have a timezone')
            result['assessed_at'] = actual['finished']
            if _hash(actual['emulator']) != actual['configuration_sha256']:
                raise ValueError('Runtime configuration changed')
            for capture in actual['captures']:
                image = confined(path.parent, capture['file']).read_bytes()
                if hashlib.sha256(image).hexdigest() != capture['sha256']:
                    raise ValueError('Runtime capture changed')
            if run['level'] != 'automated_runtime' or run['emulator'].get('kind') != 'actual_emulator':
                result['reason'] = 'synthetic_evidence'
                continue
            if (run['snapshot'] != binding['snapshot'] or run['rom_sha256'] != binding['artifacts'].get('rom')
                    or any(records.get(k) != v for k, v in run['records'].items())
                    or any(k not in run['records'] for k in area['record_ids'])):
                raise ValueError('Runtime build or scope differs')
            result['current'] = all(heads.get(k) == v for k, v in
                                    (run['records'] or records).items())
            checks = run['assertions']
            labels = {c['label'] for c in checks}
            if len(labels) != len(checks):
                raise ValueError('Ambiguous assertion labels')
            if run['status'] == 'passed' and (not set(area['assertions']) <= labels
                    or not checks or not all(c.get('passed') is True for c in checks)):
                raise ValueError('Planned assertions were not all passed')
            if run['status'] not in ('passed', 'failed'):
                raise ValueError('Invalid runtime outcome')
            # A failed run remains a failure even if it stopped before later assertions.
            result['eligible'] = True
        except (ValueError, KeyError, OSError, TypeError):
            result.update(reason='invalid_or_missing_evidence')
    return evidence


def _report(store, db, build_id=None):
    p = _plan(db)
    key = p['build_id'] if build_id is None else build_id
    heads = {r['id']: r['revision'] for r in db.execute('SELECT id,revision FROM records')}
    build = binding = records = None
    problem = None
    if key:
        identity(key)
        try:
            build, binding, records = _build(store, db, key)
        except (ValueError, KeyError, OSError, TypeError):
            problem = 'build_or_artifacts_unavailable'
    rows = []
    for area in p['areas']:
        row = dict(area, status='untested', evidence=[], observation_revision=0)
        rows.append(row)
        if problem:
            row['status'] = 'stale'
            continue
        if build is None:
            continue
        scope = {k: records.get(k) for k in area['record_ids']} if area['record_ids'] else records
        scope_current = all(v is not None and heads.get(k) == v for k, v in scope.items())
        if not area['record_ids']:
            scope_current = scope_current and heads == records
        if area['method'] == 'automated_runtime':
            row['evidence'] = _runtime(area, build, binding, records, heads, store)
            eligible = [e for e in row['evidence'] if e['eligible']]
            invalid = any(e.get('reason') == 'invalid_or_missing_evidence' for e in row['evidence'])
            current = [e for e in eligible if e['current'] and scope_current]
            if current:
                # A later exact-scenario rerun can resolve a failure, retaining
                # both runs. At equal timestamps a failure wins conservatively.
                latest = max(datetime.fromisoformat(e['assessed_at']) for e in current)
                latest_runs = [e for e in current if datetime.fromisoformat(e['assessed_at']) == latest]
                row['status'] = 'failed' if any(e['status'] == 'failed' for e in latest_runs) else 'passed'
                if invalid and row['status'] == 'passed':
                    row['status'] = 'stale'
            elif eligible or invalid:
                row['status'] = 'stale'
        else:
            observation = _load(db, _observation_key(key, area['id']), None)
            if observation:
                current = (observation['definition_sha256'] == _hash(area)
                           and observation['binding'] == binding and scope_current)
                row.update(status=observation['status'] if current else 'stale',
                           observation_revision=observation['revision'],
                           evidence=[dict(observation, current=current, eligible=True)])
        if build['status'] != 'validated' and row['status'] == 'passed':
            row['status'] = 'stale'
    return dict(schema_version=1, report_type='verification-coverage', updated_at=now(),
                plan_revision=p['revision'], plan_updated_at=p['updated_at'],
                build_id=key, build_available=build is not None,
                build_current=bool(build is not None and records == heads and build['status'] == 'validated'),
                problem=problem, next_milestone=p['next_milestone'], areas=rows,
                basis='explicitly_planned_areas', release_approved=False)


def report(store, build_id=None):
    with store.connection() as db, store.transaction(db, write=False):
        return _report(store, db, build_id)


def _summary(store, db):
    coverage = _report(store, db)
    progress = store._progress(db)
    stages = []
    for key in STAGES:
        rows = [a for a in coverage['areas'] if a['stage'] == key]
        counts = {status: sum(a['status'] == status for a in rows)
                  for status in ('passed', 'failed', 'stale', 'in_progress', 'untested')}
        assessed = [e.get('assessed_at') for a in rows for e in a['evidence'] if e.get('eligible')]
        assessed = [t for t in assessed if isinstance(t, str)]
        status = 'not_assessed'
        if counts['failed']:
            status = 'needs_attention'
        elif counts['stale'] or (counts['passed'] and not coverage['build_current']):
            status = 'needs_recheck'
        elif rows and counts['passed'] == len(rows):
            status = 'verified_for_scope'
        elif counts['passed'] or counts['in_progress']:
            status = 'in_progress'
        methods = {method: dict(planned=sum(a['method'] == method for a in rows),
                               passed=sum(a['method'] == method and a['status'] == 'passed' for a in rows))
                   for method in METHODS if any(a['method'] == method for a in rows)}
        stages.append(dict(id=key, status=status, planned=len(rows), counts=counts, methods=methods,
                           last_assessed_at=max(assessed) if assessed else None))
    percent = progress['percent_translated']
    translation = dict(status='not_assessed' if percent is None else
                       'catalogue_translated' if progress['remaining_records'] == 0 else 'in_progress',
                       **{k: progress[k] for k in ('basis', 'total_records', 'translated_records',
                                                  'remaining_records', 'percent_translated')})
    # Deliberate allowlist: no labels, references, paths, hashes, build/record IDs,
    # actor names, free-form milestone text, captures or approval records escape.
    return dict(schema_version=1, report_type='readiness-summary', updated_at=coverage['updated_at'],
                plan_updated_at=coverage['plan_updated_at'], plan_revision=coverage['plan_revision'],
                build_selected=bool(coverage['build_id']), build_available=coverage['build_available'],
                build_current=coverage['build_current'], basis='explicitly_planned_areas',
                translation=translation, stages=stages, release_approved=False)


def summary(store):
    with store.connection() as db, store.transaction(db, write=False):
        return _summary(store, db)


def write_summary(store):
    from .progress import _write_cache
    return _write_cache(store, REPORT_PATH, 'readiness-summary', _summary, 16384)

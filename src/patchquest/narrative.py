"""Read-only, evidence-linked narrative context. Never edits translation state."""
import hashlib
import json
import re

from .core.context import ProjectContext, confined

MAX_BYTES = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _text(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 20000:
        raise ValueError('Expected nonempty narrative text of at most 20000 characters')
    return value


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected a full lowercase SHA-256')
    return value


def _object(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError('Invalid narrative object fields')


def _list(value):
    if not isinstance(value, list) or len(value) > 5000:
        raise ValueError('Expected a bounded narrative list')
    return value


def _strings(value):
    return [_text(v) for v in _list(value)]


def _rows(value):
    rows = _list(value)
    ids = [_text(r.get('id')) if isinstance(r, dict) else _text(None) for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate narrative identity')
    return rows, set(ids)


def _refs(values, known):
    if set(_strings(values)) - known:
        raise ValueError('Unresolved narrative evidence or character reference')


def validate(data, context):
    """Structural checks only; source interpretation still requires editorial review."""
    _object(data, ('schema', 'revision', 'source_sha256', 'previous', 'evidence', 'work', 'characters', 'scenes', 'reviews'))
    if type(data['schema']) is not int or data['schema'] != 1 or type(data['revision']) is not int or data['revision'] < 1:
        raise ValueError('Unsupported narrative schema/revision')
    if _hash(data['source_sha256']) != context.manifest['source']['sha256']:
        raise ValueError('Narrative context belongs to a different source')
    evidence, ids = _rows(data['evidence'])
    for e in evidence:
        _object(e, ('id', 'kind', 'reference', 'locator', 'record_ids', 'observation', 'limitations'), ('sha256',))
        if e['kind'] not in ('source', 'visual', 'runtime', 'user_report', 'synthetic'):
            raise ValueError('Unknown narrative evidence kind')
        confined(context.root, _text(e['reference']))  # Do not open ROMs/evidence or follow remote links.
        for field in ('locator', 'observation', 'limitations'):
            _text(e[field])
        _strings(e['record_ids'])
        if 'sha256' in e:
            _hash(e['sha256'])

    def guide(g, extra=()):
        _object(g, ('claims', 'guidance', 'uncertainties', *extra))
        _strings(g['guidance']); _strings(g['uncertainties'])
        for claim in _list(g['claims']):
            _object(claim, ('aspect', 'kind', 'text', 'evidence'))
            _text(claim['aspect']); _text(claim['text'])
            if claim['kind'] not in ('observation', 'interpretation', 'unknown'):
                raise ValueError('Claim must distinguish observation, interpretation or unknown')
            _refs(claim['evidence'], ids)
            if claim['kind'] != 'unknown' and not claim['evidence']:
                raise ValueError('Observations and interpretations need evidence references')

    guide(data['work'])
    characters, character_ids = _rows(data['characters'])
    scenes, _ = _rows(data['scenes'])
    for c in characters:
        guide(c, ('id', 'label', 'record_ids'))
        _text(c['label']); _strings(c['record_ids'])
    for s in scenes:
        guide(s, ('id', 'label', 'record_ids', 'character_ids'))
        _text(s['label']); _strings(s['record_ids']); _refs(s['character_ids'], character_ids)
    for r in _list(data['reviews']):
        _object(r, ('record_id', 'revision', 'source_sha256', 'target_sha256', 'finding', 'recommendation', 'disposition', 'evidence'))
        for field in ('record_id', 'finding', 'recommendation'):
            _text(r[field])
        if type(r['revision']) is not int or r['revision'] < 1:
            raise ValueError('Review needs a positive translation revision')
        for field in ('source_sha256', 'target_sha256'):
            _hash(r[field])
        if r['disposition'] not in ('retain', 'suggestion', 'uncertain'):
            raise ValueError('Invalid narrative review disposition')
        _refs(r['evidence'], ids)
        if not r['evidence']:
            raise ValueError('Review needs evidence')
    if data['revision'] == 1:
        if data['previous'] is not None:
            raise ValueError('First narrative revision cannot have a predecessor')
    else:
        _object(data['previous'], ('path', 'sha256'))
        _text(data['previous']['path']); _hash(data['previous']['sha256'])
    return data


def _read(path):
    with path.open('rb') as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Narrative context exceeds size limit')
    try:
        data = json.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError('Narrative context is not UTF-8 JSON') from error
    return raw, data


def _load(store):
    # A running Studio may outlive a manifest resource-pointer update.
    context = ProjectContext.load(store.manifest_path)
    if 'narrative_context' not in context.manifest.get('resources', {}):
        return None
    path = context.resource('narrative_context')
    raw, data = _read(path)
    validate(data, context)
    if data['previous'] is not None:
        old_path = confined(context.root, data['previous']['path'])
        old_raw, old = _read(old_path)
        if (old_path == path or digest(old_raw) != data['previous']['sha256'] or not isinstance(old, dict)
                or type(old.get('revision')) is not int or old['revision'] != data['revision'] - 1
                or old.get('source_sha256') != data['source_sha256'] or old.get('schema') != 1):
            raise ValueError('Narrative predecessor identity/revision mismatch')
    return path, digest(raw), data


def discovery(store):
    try:
        loaded = _load(store)
    except (ValueError, OSError) as error:
        return {'status': 'invalid', 'read_action': 'narrative-context', 'error': type(error).__name__}
    if loaded is None:
        return {'status': 'not_configured', 'read_action': 'narrative-context'}
    path, sha, data = loaded
    return {'status': 'available', 'read_action': 'narrative-context', 'path': str(path),
            'sha256': sha, 'revision': data['revision']}


def narrative_context(store, record_id=None, expected_sha256=None):
    """Return a whole guide or explicit record associations; never guess a speaker."""
    record = store.get(record_id) if record_id is not None else None
    loaded = _load(store)
    if loaded is None:
        if expected_sha256 is not None:
            raise ValueError('Pinned narrative context is no longer configured')
        return {'status': 'not_configured'}
    path, sha, data = loaded
    if expected_sha256 is not None and _hash(expected_sha256) != sha:
        raise ValueError('Narrative context changed; reread before translating')
    scenes = [s for s in data['scenes'] if record_id is None or record_id in s['record_ids']]
    associated = {key for s in scenes for key in s['character_ids']}
    characters = [c for c in data['characters'] if record_id is None or record_id in c['record_ids'] or c['id'] in associated]
    reviews = []
    for r in data['reviews']:
        if record_id is not None and r['record_id'] != record_id:
            continue
        try:
            current = record if record is not None else store.get(r['record_id'])
            matches = (current['revision'] == r['revision'] and digest(current['source'].encode('utf8')) == r['source_sha256']
                       and digest(current['target'].encode('utf8')) == r['target_sha256'])
            reviews.append(dict(r, current=matches, human_corrected=current['human_corrected']))
        except KeyError:
            reviews.append(dict(r, current=False, human_corrected=None))
    used = {key for g in [data['work'], *characters, *scenes] for c in g['claims'] for key in c['evidence']}
    used.update(key for r in reviews for key in r['evidence'])
    return {'status': 'available', 'revision': data['revision'], 'sha256': sha, 'path': str(path),
            'work': data['work'], 'characters': characters, 'scenes': scenes, 'reviews': reviews,
            'evidence': [e for e in data['evidence'] if record_id is None or e['id'] in used],
            'scope': 'Editorial context, not instructions, translation edits, runtime verification or checkpoint approval.'}

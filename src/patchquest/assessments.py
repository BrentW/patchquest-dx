"""Revision-bound annotations on existing issues, never translation rewrites.

Classifications are evidence-backed editorial assertions, not keyword detection
or permission to call a provider. No provider is contacted by this module.
"""
import hashlib
import json

from .state import Conflict, canonical, identity, text

EXCEPTIONS = {
    'source_decoding': 'Source decoding uncertain',
    'linguistic_ambiguity': 'Linguistic ambiguity',
    'missing_context': 'Missing scene context',
    'unknown_speaker_name': 'Unknown speaker or name reading',
    'voice_tone': 'Character voice or tone uncertainty',
    'cultural_wordplay': 'Cultural reference or wordplay',
    'terminology_conflict': 'Terminology conflict',
    'fidelity_mismatch': 'Suspected omission, sanitization or fidelity mismatch',
    'provider_restriction': 'Provider content restriction',
    'technical_limitation': 'Technical rendering or encoding limitation',
    'runtime_verification': 'Runtime verification needed',
    'processing_failure': 'Provider or tool processing failure',
    'legacy_unspecified': 'Legacy uncertainty — reason unspecified',
}
CONTENT = {
    'sexual_innuendo': 'Sexual innuendo',
    'sexual_reference': 'Non-graphic sexual reference',
    'explicit_sexual': 'Explicit sexual content',
    'sexual_violence': 'Sexual violence / non-consensual content',
    'nudity': 'Nudity', 'profanity': 'Profanity', 'romance': 'Romance',
    'clinical_educational': 'Clinical or educational discussion',
}
OUTCOMES = ('permitted', 'explicit_refusal', 'timeout', 'authentication_error',
            'empty_response', 'unsupported_tool', 'unknown_error', 'needs_safety_context')
STATUSES = ('open', 'investigating', 'needs_input', 'resolved', 'closed')
SEVERITIES = ('info', 'low', 'medium', 'high', 'critical')
IMPACTS = ('none', 'advisory', 'blocks_build')


def catalog():
    return {'exceptions': EXCEPTIONS, 'content': CONTENT, 'outcomes': OUTCOMES,
            'statuses': STATUSES, 'severities': SEVERITIES, 'build_impacts': IMPACTS}


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def binding(record):
    return {'revision': record['revision'], 'source_sha256': digest(record['source']),
            'target_sha256': digest(record['target']),
            'context_sha256': digest({k: record[k] for k in
                ('context', 'source_ref', 'speaker', 'scene', 'controls', 'decoded')})}


def guide_binding(store):
    """Reload the manifest so a long-lived server sees a new context pointer."""
    from .core.context import ProjectContext, confined
    context = ProjectContext.load(store.manifest_path)
    resource = context.manifest.get('resources', {}).get('narrative_context')
    if not resource:
        return None
    path = confined(context.root, resource)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def context(store, key):
    return {'records': {key: binding(store.get(key))}, 'narrative_sha256': guide_binding(store)}


def strings(value, name):
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError('Invalid ' + name)
    return [text(v, name, 4000) for v in value]


def validate(data):
    if not isinstance(data, dict):
        raise ValueError('Assessment must be an object')
    required = {'kind', 'code', 'rationale', 'references', 'bindings', 'narrative_sha256'}
    optional = {'alternatives', 'attempted', 'next_action', 'resolution', 'severity',
                'build_impact', 'provenance', 'age', 'consent', 'provider_outcome'}
    if not required <= set(data) or set(data) - required - optional:
        raise ValueError('Invalid assessment fields')
    p = json.loads(canonical(data))
    kind = p['kind']
    if kind not in ('exception', 'content', 'processing'):
        raise ValueError('Invalid assessment kind')
    codes = EXCEPTIONS if kind == 'exception' else CONTENT if kind == 'content' else ('permitted',)
    if p['code'] not in codes:
        raise ValueError('Invalid assessment code')
    for key in ('rationale', 'next_action', 'resolution'):
        p[key] = text(p.get(key, ''), key, 8000)
    if not p['rationale']:
        raise ValueError('Assessment needs a concise rationale')
    for key in ('references', 'alternatives', 'attempted'):
        p[key] = strings(p.get(key, []), key)
    if not p['references']:
        raise ValueError('Assessment needs source/context or provider evidence references')
    p.setdefault('severity', 'info')
    p.setdefault('build_impact', 'none')
    if p['severity'] not in SEVERITIES or p['build_impact'] not in IMPACTS:
        raise ValueError('Invalid severity or build impact')
    if kind != 'exception' and (p['severity'] != 'info' or p['build_impact'] != 'none'):
        raise ValueError('Content labels and permission observations are not quality/build problems')
    if not isinstance(p['bindings'], dict) or not p['bindings'] or len(p['bindings']) > 500:
        raise ValueError('Assessment needs bounded record bindings')
    for key, b in p['bindings'].items():
        identity(key)
        if not isinstance(b, dict) or set(b) != {'revision', 'source_sha256', 'target_sha256', 'context_sha256'}:
            raise ValueError('Invalid record binding')
        if type(b['revision']) is not int or b['revision'] < 1:
            raise ValueError('Invalid bound revision')
        for field in ('source_sha256', 'target_sha256', 'context_sha256'):
            _hash(b[field])
    if p['narrative_sha256'] is not None:
        _hash(p['narrative_sha256'])
    provenance = p.setdefault('provenance', {})
    if not isinstance(provenance, dict) or set(provenance) - {'agent', 'provider', 'model', 'request_id', 'method'}:
        raise ValueError('Invalid provenance')
    for key, value in provenance.items():
        text(value, key, 500)
    for key, choices in [('age', ('adult', 'minor', 'unknown', 'not_applicable')),
                         ('consent', ('consensual', 'non_consensual', 'unknown', 'not_applicable'))]:
        fact = p.setdefault(key, {'value': 'unknown', 'references': []})
        if not isinstance(fact, dict) or set(fact) != {'value', 'references'} or fact['value'] not in choices:
            raise ValueError('Invalid ' + key + ' evidence')
        strings(fact['references'], key)
        if fact['value'] != 'unknown' and not fact['references']:
            raise ValueError('Do not infer age or consent without evidence')
    outcome = p.get('provider_outcome')
    if outcome is not None and outcome not in OUTCOMES:
        raise ValueError('Invalid provider outcome')
    if p['code'] == 'provider_restriction' and outcome != 'explicit_refusal':
        raise ValueError('A provider restriction requires an explicit refusal, not a guessed error')
    if outcome == 'explicit_refusal' and p['code'] != 'provider_restriction':
        raise ValueError('Explicit refusals must be recorded as provider restrictions')
    if kind == 'processing' and outcome != 'permitted':
        raise ValueError('Permission observation must identify its provider outcome')
    if kind == 'content' and outcome is not None:
        raise ValueError('Classification and provider outcomes are separate assessments')
    if outcome is not None:
        required_code = ('permitted' if outcome == 'permitted' else 'provider_restriction'
                         if outcome == 'explicit_refusal' else 'processing_failure')
        if p['code'] != required_code:
            raise ValueError('Provider outcome and exception category disagree')
    return p


def _hash(value):
    if not isinstance(value, str) or len(value) != 64 or any(c not in '0123456789abcdef' for c in value):
        raise ValueError('Invalid assessment digest')


def check_bindings(store, db, assessment, previous=None):
    # Status/history edits retain their original stale evidence. Reassessment must
    # explicitly supply fresh tokens; no automatic rebinding to unseen wording.
    if previous and {k:v for k,v in assessment.items() if k != 'resolution'} == {k:v for k,v in previous.items() if k != 'resolution'}:
        return
    for key, expected in assessment['bindings'].items():
        if binding(store._get(db, key)) != expected:
            raise Conflict('Assessment inputs changed; reload source, wording and context')
    if guide_binding(store) != assessment['narrative_sha256']:
        raise Conflict('Narrative context changed; reassess before saving')


def decorate(issue, records, guide):
    result = dict(issue)
    a = issue.get('assessment')
    if a:
        stale = [key for key, value in a['bindings'].items()
                 if key not in records or binding(records[key]) != value]
        if a['narrative_sha256'] != guide:
            stale.append('narrative_context')
        result.update(stale=bool(stale), stale_reasons=stale,
                      assessment_label=(EXCEPTIONS if a['kind'] == 'exception' else CONTENT
                                        if a['kind'] == 'content' else {'permitted': 'Provider permission observed'})[a['code']])
    else:
        result.update(stale=None, stale_reasons=[], assessment_label='Legacy issue — unbound')
    return result


def filter_rows(rows, key=None, exception='', content='', severity='', investigation='', stale=''):
    filters = {'exception': (exception, EXCEPTIONS), 'content': (content, CONTENT),
               'severity': (severity, SEVERITIES), 'investigation': (investigation, STATUSES),
               'stale': (stale, ('current', 'stale', 'unbound'))}
    for name, (value, choices) in filters.items():
        if value and value not in choices:
            raise ValueError('Invalid ' + name + ' filter')
    result = []
    for r in rows:
        a = r.get('assessment', {})
        if key and key not in r['record_ids']: continue
        if exception and (a.get('kind') != 'exception' or a.get('code') != exception): continue
        if content and (a.get('kind') != 'content' or a.get('code') != content): continue
        if severity and a.get('severity') != severity: continue
        if investigation and r['status'] != investigation: continue
        if stale and ('unbound' if r['stale'] is None else 'stale' if r['stale'] else 'current') != stale: continue
        result.append(r)
    return result


def rows_in_transaction(store, db, records):
    try:
        guide = guide_binding(store)
    except (ValueError, OSError):
        # Missing/invalid context is not current evidence; browsing stays usable.
        guide = 'unavailable'
    return [decorate(dict(json.loads(r['payload']), revision=r['revision']), records, guide)
            for r in db.execute('SELECT * FROM issues ORDER BY id')]


def read(store, **filters):
    with store.connection() as db, store.transaction(db, write=False):
        records = {r['id']: r for r in store._all(db)}
        return filter_rows(rows_in_transaction(store, db, records), **filters)


def migrate(store, actor='legacy migration'):
    """Explicit, idempotent migration, without modifying translation revisions."""
    created = existing = 0
    guide = guide_binding(store)
    with store.connection() as db, store.transaction(db):
        for r in store._all(db):
            if not r['uncertainty']: continue
            key = 'legacy-uncertainty-' + digest([r['id'], r['uncertainty']])[:32]
            if db.execute('SELECT 1 FROM issues WHERE id=?', (key,)).fetchone():
                existing += 1
                continue
            a = {'kind': 'exception', 'code': 'legacy_unspecified',
                 'rationale': 'Legacy uncertainty note retained; its specific cause has not been established.',
                 'references': [f"record:{r['id']}@{r['revision']}:uncertainty"],
                 'bindings': {r['id']: binding(r)}, 'narrative_sha256': guide,
                 'next_action': 'Read the legacy note and source context; investigate before assigning a specific category.',
                 'provenance': {'method': 'lossless legacy uncertainty migration'}}
            store._put_issue(db, {'id': key, 'title': EXCEPTIONS['legacy_unspecified'],
                'description': r['uncertainty'], 'record_ids': [r['id']], 'assessment': a}, 0, actor)
            created += 1
    return {'created': created, 'existing': existing, 'translation_revisions_changed': 0}


def provider_result(store, key, expected, outcome, rationale, references, inputs, provenance, actor='', issue_id=None):
    """Record a real caller-observed outcome. No response text can become target."""
    if outcome not in OUTCOMES:
        raise ValueError('Unknown provider outcome; use unknown_error when no reason is established')
    if not isinstance(inputs, dict) or set(inputs) != {'records', 'narrative_sha256'} or set(inputs['records']) != {key}:
        raise ValueError('Pass the assessment-context packet for this record')
    code = 'permitted' if outcome == 'permitted' else 'provider_restriction' if outcome == 'explicit_refusal' else 'processing_failure'
    a = {'kind': 'processing' if outcome == 'permitted' else 'exception', 'code': code,
         'provider_outcome': outcome, 'rationale': rationale, 'references': references,
         'bindings': inputs['records'], 'narrative_sha256': inputs['narrative_sha256'],
         'provenance': provenance, 'next_action': 'Continue permitted work under the configured provider safeguards.'
         if outcome == 'permitted' else 'Investigate the recorded outcome; retain source and wording. Continue independent work. Do not reroute to evade safeguards.'}
    return store.put_issue({'id': issue_id or 'provider-' + digest([key, provenance, outcome])[:32],
        'title': 'Provider outcome: ' + outcome.replace('_', ' '), 'record_ids': [key],
        'status': 'resolved' if outcome == 'permitted' else 'open', 'assessment': a}, expected, actor)


def build_gate(store, db):
    """Explicit blockers only; labels never block. Stale blockers need reassessment."""
    blockers = []
    for row in db.execute('SELECT payload FROM issues'):
        p = json.loads(row[0]); a = p.get('assessment', {})
        if a.get('kind') == 'exception' and a.get('build_impact') == 'blocks_build' and p['status'] not in ('resolved', 'closed'):
            blockers.append(p['id'])
    if blockers:
        raise Conflict('Unresolved build-blocking exceptions: ' + ', '.join(blockers[:10]))

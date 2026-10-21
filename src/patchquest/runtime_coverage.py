"""Read-only runtime/catalog reconciliation over explicitly reviewed evidence.

No emulator, catalog writes, project discovery or verification awards. Caller
configuration and the independent admission callback are trusted local inputs;
imported manifests and passed labels are not authentication.
"""
import copy
import hashlib
import json
from pathlib import Path
import sqlite3

from .core.context import ProjectContext, confined
from .state import canonical
from .runtime_contracts import (
    ContractError, COVERAGE_STATUSES, validate, contract_digest,
    check_observation, check_finding, verify_evidence_bytes, observation_status,
    assess_observation_findings, check_coverage_runtime_links,
)
from .runtime_detectors import detect, expectation_digest


def _need(condition, reason):
    if not condition:
        raise ContractError(reason)


def digest(value):
    """Canonical receiver identity, also used to pin caller-owned admission."""
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _reason(value):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 4000,
          'Explicit bounded review reason/reference required')


def _context(selection):
    context = selection if isinstance(selection, ProjectContext) else selection.context
    _need(isinstance(context, ProjectContext), 'Explicit selected ProjectContext or existing Store required')
    return context


def read_catalog(selection, build_ids):
    """Consistent read of EXISTING state; never constructs/migrates a Store.

    A ProjectContext explicitly selects an existing catalog, or a caller may
    supply its already open Store. SQLite mode=ro prevents creating a missing DB.
    Returned digest is an optimistic read receipt, not an authenticity signature.
    """
    context = _context(selection)
    _need(type(build_ids) in (list, tuple) and len(build_ids) <= 1000, 'Bounded build selection required')
    path = confined(context.root, '.patchquest/state.sqlite3')
    _need(path.is_file(), 'Selected catalog does not exist')
    expected = dict(project_id=context.manifest['project_id'],
                    source_sha256=context.manifest['source']['sha256'])
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, isolation_level=None)
    try:
        db.execute('PRAGMA query_only=ON')
        db.execute('BEGIN')
        row = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
        _need(row is not None and json.loads(row[0]) == expected, 'Catalog project/source differs')
        heads = dict(db.execute('SELECT id,revision FROM records ORDER BY id'))
        builds, snapshots = {}, {}
        for key in sorted(set(build_ids)):
            row = db.execute('SELECT revision,payload FROM builds WHERE id=?', (key,)).fetchone()
            _need(row is not None, 'Retained build missing')
            payload = json.loads(row[1])
            snapshot = payload.get('snapshot')
            _need(payload.get('id') == key and snapshot, 'Build identity/snapshot missing')
            builds[key] = dict(revision=row[0], payload_sha256=digest(payload), snapshot=snapshot)
            if snapshot not in snapshots:
                row = db.execute('SELECT payload FROM snapshots WHERE digest=?', (snapshot,)).fetchone()
                _need(row is not None, 'Retained snapshot missing')
                data = json.loads(row[0])
                _need(hashlib.sha256(row[0].encode('utf8')).hexdigest() == snapshot
                      and digest(data) == snapshot, 'Immutable snapshot digest differs')
                _need(data.get('schema') == 1 and all(data.get(k) == v for k, v in expected.items()),
                      'Snapshot project/source differs')
                records = data['records']
                _need(type(records) is list and len(records) <= 100000, 'Bounded snapshot records required')
                revisions = {r['id']: r['revision'] for r in records}
                _need(len(revisions) == len(records) and
                      all(type(v) is int and v > 0 for v in revisions.values()), 'Invalid snapshot revisions')
                snapshots[snapshot] = revisions
        result = dict(identity=expected, heads=heads, builds=builds, snapshots=snapshots)
        return dict(result, read_sha256=digest(result))
    finally:
        db.rollback()
        db.close()


def catalog_unchanged(selection, receipt):
    """Recheck read freshness; not a lock or permission to bypass a writer's CAS."""
    return read_catalog(selection, list(receipt['builds']))['read_sha256'] == receipt['read_sha256']


def _bytes_ok(ref, resolve):
    try:
        result = resolve(copy.deepcopy(ref))
        return (type(result) is dict and result.get('available') is True and
                verify_evidence_bytes(ref, result.get('data')))
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _admission(proof, binding, caps, requests, build, resolve):
    if proof is None:
        return {}, False
    _need(type(proof) is dict and set(proof) == {
        'binding_sha256', 'capabilities_sha256', 'reviewer', 'reference', 'reason',
        'artifacts', 'emulator', 'purposes', 'build_revision', 'build_payload_sha256'},
        'Invalid trusted admission')
    for key in ('reviewer', 'reference', 'reason'):
        _reason(proof[key])
    _need(proof['binding_sha256'] == contract_digest('RunBinding', binding) and
          proof['capabilities_sha256'] == contract_digest('AdapterCapabilities', caps),
          'Reviewed binding/capabilities differ')
    _need(proof['build_revision'] == build['revision'] and
          proof['build_payload_sha256'] == build['payload_sha256'],
          'Reviewed retained build changed')
    _need(set(proof['artifacts']) == set(binding['artifacts']), 'Reviewed build roles differ')
    refs = []
    for role, ref in proof['artifacts'].items():
        ref = validate('EvidenceRef', ref)
        _need(ref['sha256'] == binding['artifacts'][role], 'Reviewed build bytes differ')
        refs.append(ref)
    emulator = validate('EvidenceRef', proof['emulator'])
    _need(emulator['sha256'] == binding['emulator']['sha256'], 'Reviewed emulator differs')
    refs.append(emulator)
    purposes = proof['purposes']
    known = {contract_digest('CaseSpec', c) for c in requests.values()}
    _need(type(purposes) is dict and set(purposes) <= known, 'Purpose case outside reviewed run')
    for scopes in purposes.values():
        _need(type(scopes) is dict and set(scopes) <= {'renderer', 'normal_gameplay'},
              'Unknown reviewed purpose')
        for detail in scopes.values():
            _need(type(detail) is dict and set(detail) == {'reason', 'reference'},
                  'Purpose needs independent reason/reference')
            _reason(detail['reason']); _reason(detail['reference'])
    return copy.deepcopy(purposes), all(_bytes_ok(r, resolve) for r in refs)


def _attempts(group, cases, binding, catalog, admit_run, resolve):
    attempts, discoveries, runs = {}, [], []
    snapshot = catalog['snapshots'][binding['snapshot']]
    bundles = group.get('runs', [])
    _need(type(bundles) is list and len(bundles) <= 1000, 'Bounded run bundles required')
    for bundle in bundles:
        _need(type(bundle) is dict and set(bundle) == {'manifest_bytes', 'expectations', 'findings'},
              'Invalid run bundle')
        raw = bundle['manifest_bytes']
        _need(type(raw) is bytes and 0 < len(raw) <= 32 * 1024 * 1024, 'Original bounded manifest bytes required')
        manifest_hash = hashlib.sha256(raw).hexdigest()
        manifest = json.loads(raw)
        definition = manifest['definition']
        _need(digest(definition) == manifest['definition_sha256'], 'Run definition changed')
        _need(validate('RunBinding', definition['binding']) == binding, 'Run belongs to another binding group')
        caps = validate('AdapterCapabilities', definition['capabilities'])
        _need(digest(definition['configuration']) == binding['configuration_sha256'], 'Configuration changed')
        requests = {}
        for request in definition['requests']:
            c = validate('CaseSpec', request['case'])
            _need(c['case_id'] not in requests, 'Duplicate requested case')
            requests[c['case_id']] = c
        _need(set(requests) <= set(cases), 'Requested cases cannot be removed from the coverage denominator')
        observations = manifest['observations']
        _need(type(observations) is list and len(observations) <= 10000 and
              len(observations) == len(requests) and
              {o['case_id'] for o in observations} == set(requests),
              'Run must retain every requested observation exactly once')
        proof = admit_run(manifest_hash)
        purposes, inputs_ok = _admission(proof, binding, caps, requests,
                                        catalog['builds'][binding['build_id']], resolve)
        plan = bundle['expectations']
        if plan is not None:
            _need(expectation_digest(plan) == binding['expectation_sha256'], 'Whole expectation plan differs')
        supplied = {}
        for finding in bundle['findings']:
            f = validate('DetectorFinding', finding)
            _need(f['finding_id'] not in supplied, 'Duplicate finding')
            supplied[f['finding_id']] = f
        _need({f['observation_id'] for f in supplied.values()} <= {o['observation_id'] for o in observations},
              'Orphan finding')
        ledgers = dict(inventories=copy.deepcopy(manifest.get('inventories', [])),
                       gaps=copy.deepcopy(manifest.get('gaps', [])),
                       enumeration_history=copy.deepcopy(manifest.get('enumeration_history', [])))
        runs.append(dict(manifest_sha256=manifest_hash, run_id=manifest['run_id'],
                         admission=copy.deepcopy(proof), discovery=ledgers))
        for gap in ledgers['gaps']:
            discoveries.append(dict(kind='unmapped', observation_ids=[], record_ids=[],
                reason='Runner discovery retained without expanding declared scope: ' + canonical(gap)))
        for value in observations:
            case = requests[value['case_id']]
            o = check_observation(case, value, caps, expected_binding=binding)
            _need(all(snapshot.get(k) == v for k, v in o['binding']['records'].items()),
                  'Observed revisions differ from retained snapshot')
            linked = [check_finding(f, o) for f in supplied.values() if f['observation_id'] == o['observation_id']]
            case_id = o['case_id']
            if case_id not in cases:
                discoveries.append(dict(kind='uncatalogued' if set(case['record_ids']) - set(snapshot) else 'unmapped',
                    observation_ids=[o['observation_id']], record_ids=case['record_ids'],
                    reason='Observed case outside the declared coverage inventory; no catalog edit or scope expansion.'))
            else:
                _need(case == cases[case_id], 'Observed case differs from declared context')
            checks = [_bytes_ok(c['evidence'], resolve) for c in o['captures']]
            captured = (proof is not None and inputs_ok and o['execution'] == 'completed' and
                        o['validity'] == 'current' and bool(checks) and all(checks))
            status = observation_status(o, binding)
            reason = 'Execution/capture alone is not a detector pass.'
            assessment = None
            if proof is None or not inputs_ok:
                status, reason = 'unknown', 'Reviewed producer admission or immutable input bytes unavailable.'
            elif o['validity'] != 'current' or o['execution'] != 'completed':
                reason = 'Retained execution disposition: ' + status + '.'
            elif not checks or not all(checks):
                status, reason = 'unknown', 'Capture bytes unavailable or changed.'
            elif plan is None:
                _need(not linked, 'Findings cannot be assessed without their complete plan')
                if o['execution'] == 'completed':
                    status = 'unknown'
            else:
                assessment = assess_observation_findings(o, binding, linked, expectations=plan)
                # Recompute with the existing detector; never invent missing imported checks.
                actual = {f['finding_id']: f for f in detect(case, o, caps, plan, resolve, expected_binding=binding)}
                mismatch = any(actual.get(f['finding_id']) != f for f in linked)
                status = 'unknown' if mismatch else assessment['status']
                reason = ('Received findings disagree with checked bytes/instrumentation.' if mismatch else
                          'Assessment of the complete required plan: ' + status + '.')
            scopes = purposes.get(o['case_sha256'], {})
            captured = captured and bool(scopes)
            if 'normal_gameplay' in scopes:
                _need(o['method'] == 'automated_runtime' and o['reach_method'] in ('cold_boot_navigation', 'in_game_save'),
                      'Reviewed gameplay purpose cannot override execution method/reach')
            attempt = dict(observation=o, findings=linked, status=status, reason=reason,
                           purposes=scopes, captured=captured, assessment=assessment,
                           manifest_sha256s=[manifest_hash], superseded=False)
            key = o['observation_id']
            if key in attempts:
                old = attempts[key]
                _need(all(old[k] == attempt[k] for k in attempt if k != 'manifest_sha256s'),
                      'Conflicting duplicate observation/admission')
                old['manifest_sha256s'].append(manifest_hash)
            else:
                attempts[key] = attempt
    return attempts, discoveries, runs


def _supersede(attempts, replacements):
    _need(type(replacements) is list and len(replacements) <= 10000, 'Bounded supersessions required')
    edges = {}
    for row in replacements:
        _need(type(row) is dict and set(row) == {'old', 'new', 'reason'}, 'Reasoned supersession required')
        _reason(row['reason'])
        a, b = row['old'], row['new']
        _need(a in attempts and b in attempts and a not in edges, 'Unknown/duplicate supersession')
        old, new = attempts[a], attempts[b]
        _need(all(old['observation'][k] == new['observation'][k] for k in
                  ('case_id', 'case_sha256', 'binding', 'method', 'reach_method', 'provenance')) and
              bool(old['purposes']) and old['purposes'] == new['purposes'],
              'Supersession crosses case, binding, method or purpose')
        edges[a] = b
    for start in edges:
        seen, cursor = set(), start
        while cursor in edges:
            _need(cursor not in seen, 'Supersession cycle')
            seen.add(cursor); cursor = edges[cursor]
        attempts[start]['superseded'] = True


def _section(scope, method, rows):
    counts = {s: sum(r['status'] == s for r in rows) for s in COVERAGE_STATUSES}
    return dict(scope_kind=scope, method=method, rows=rows, denominator=len(rows), counts=counts,
                passed_percent=round(100 * counts['passed'] / len(rows), 2) if rows else None)


def _mapped_case(group, case, binding):
    """One strict association predicate for every record and gap view."""
    mapping = group.get('associations', {}).get(case['case_id'])
    if type(mapping) is not dict:
        return False
    basis = mapping.get('basis')
    if not isinstance(basis, str) or not basis.strip() or len(basis) > 4000:
        return False
    if mapping.get('case_sha256') != contract_digest('CaseSpec', case):
        return False
    if not case['record_ids']:
        return mapping.get('kind') == 'screen_only'
    expected = {k: binding['records'][k] for k in case['record_ids']}
    return mapping.get('kind') == 'exact' and mapping.get('records') == expected


def _records(group, catalog, binding, cases, attempts, sections, *, current):
    snapshot = catalog['snapshots'][binding['snapshot']]
    records = catalog['heads'] if current else snapshot
    requirements = group.get('record_requirements', {})
    _need(set(requirements) <= set(snapshot), 'Record requirements outside snapshot')
    result = []
    for section in sections:
        by_case = {r['case_id']: r for r in section['rows']}
        rows = []
        for key, revision in sorted(records.items()):
            required = requirements.get(key)
            declared = sorted(c['case_id'] for c in cases.values() if key in c['record_ids'])
            complete = False
            if required is not None:
                _need(type(required) is dict and set(required) == {'case_ids', 'complete', 'basis'},
                      'Explicit context requirements required')
                _reason(required['basis'])
                _need(type(required['complete']) is bool and required['case_ids'] == declared,
                      'Record requirements must retain all declared contexts')
                complete = required['complete']
            details = []
            for cid in declared:
                case = cases[cid]; row = by_case[cid]
                expected = {k: binding['records'][k] for k in case['record_ids']}
                exact = _mapped_case(group, case, binding)
                stale = current and any(catalog['heads'].get(k) != v for k, v in expected.items())
                status = 'stale' if stale else row['status'] if exact else 'unknown'
                exercised = [oid for oid in row['observation_ids'] if exact and not stale and attempts[oid]['captured']]
                details.append(dict(case_id=cid, status=status, exercised_observation_ids=exercised,
                                    reason='Complete current mapping required.' if not exact or stale else row['reason']))
            statuses = {r['status'] for r in details}
            status = ('failed' if 'failed' in statuses else next(iter(statuses))
                      if len(statuses) == 1 and complete else 'unknown')
            if current and snapshot.get(key) != revision:
                status = 'stale'
            rows.append(dict(record_id=key, revision=revision, status=status, required_case_ids=declared,
                contexts_complete=complete, cases=details,
                exercised_case_ids=[r['case_id'] for r in details if r['exercised_observation_ids']],
                reason='Only explicitly reviewed complete context mappings can verify a record.'))
        result.append(_section(section['scope_kind'], section['method'], rows))
    return result


def reconcile(selection, groups, *, admit_run, resolve_evidence):
    """Return per-binding reports and catalog lenses; never persist or award stages.

    groups are caller-owned inventory/mapping policy, not auto-imported evidence.
    admit_run receives the original manifest-byte SHA-256 and returns a separate,
    trusted review receipt (or None). Never implement it by echoing bundle tags.
    """
    _need(type(groups) is list and len(groups) <= 1000 and
          callable(admit_run) and callable(resolve_evidence), 'Explicit bounded inputs/resolvers required')
    bindings = [validate('RunBinding', g['binding']) for g in groups]
    _need(len({contract_digest('RunBinding', b) for b in bindings}) == len(bindings), 'Duplicate binding group')
    catalog = read_catalog(selection, [b['build_id'] for b in bindings])
    results = []
    for group, binding in zip(groups, bindings):
        _need(catalog['builds'][binding['build_id']]['snapshot'] == binding['snapshot'], 'Build snapshot differs')
        snapshot = catalog['snapshots'][binding['snapshot']]
        _need(all(snapshot.get(k) == v for k, v in binding['records'].items()), 'Bound revisions absent from snapshot')
        values = group['cases']
        _need(type(values) is list and len(values) <= 10000, 'Bounded declared cases required')
        cases = {}
        for value in values:
            case = validate('CaseSpec', value)
            _need(case['case_id'] not in cases, 'Duplicate declared case')
            _need(set(case['record_ids']) <= set(binding['records']), 'Every composed record revision must be bound')
            cases[case['case_id']] = case
        attempts, gaps, runs = _attempts(group, cases, binding, catalog, admit_run, resolve_evidence)
        _supersede(attempts, group.get('supersessions', []))
        sections = []
        for scope, method in (('renderer', 'synthetic'), ('renderer', 'automated_runtime'),
                              ('normal_gameplay', 'automated_runtime')):
            rows = []
            for cid in sorted(cases):
                selected = [a for a in attempts.values() if a['observation']['case_id'] == cid
                            and not a['superseded'] and a['observation']['method'] == method and scope in a['purposes']]
                states = {a['status'] for a in selected}
                status = next(iter(states)) if len(states) == 1 else 'unknown' if states else 'untested'
                rows.append(dict(case_id=cid, status=status,
                    reason='Conflicting attempts require an explicit disposition.' if len(states) > 1 else
                           selected[0]['reason'] if selected else 'No admitted evidence for this purpose and method.',
                    observation_ids=sorted(a['observation']['observation_id'] for a in selected),
                    finding_ids=sorted(f['finding_id'] for a in selected for f in a['findings'])))
            sections.append(_section(scope, method, rows))
        exercised = set()
        for a in attempts.values():
            cid = a['observation']['case_id']
            if cid not in cases or not a['captured'] or a['superseded']:
                continue
            case = cases[cid]
            if _mapped_case(group, case, binding):
                exercised.update(case['record_ids'])
        for key in sorted(set(snapshot) - exercised):
            gaps.append(dict(kind='unexercised', observation_ids=[], record_ids=[key],
                             reason='No admitted complete capture of a declared context; see method/context summaries.'))
        gap_contexts = {}
        for cid, case in cases.items():
            if not case['record_ids'] and not _mapped_case(group, case, binding):
                gap_contexts[str(len(gaps))] = cid
                gaps.append(dict(kind='uncatalogued', observation_ids=[oid for oid, a in attempts.items()
                    if a['observation']['case_id'] == cid], record_ids=[],
                    reason='Observed context has no known catalog association; investigate without inventing source text.'))
            if case['record_ids'] and not _mapped_case(group, case, binding):
                gap_contexts[str(len(gaps))] = cid
                gaps.append(dict(kind='unmapped', observation_ids=[oid for oid, a in attempts.items()
                    if a['observation']['case_id'] == cid], record_ids=case['record_ids'],
                    reason='Exact complete composed mapping unavailable.'))
        for decl in group.get('declarations', []):
            _need(set(decl) == {'kind', 'revisions', 'reason', 'reference'} and
                  decl['kind'] in ('preserved_source', 'graphics_text'), 'Invalid reasoned declaration')
            _reason(decl['reason']); _reason(decl['reference'])
            _need(bool(decl['revisions']) and all(type(v) is int and snapshot.get(k) == v
                                                for k, v in decl['revisions'].items()),
                  'Declaration revisions differ from this snapshot')
            stale = any(catalog['heads'].get(k) != v for k, v in decl['revisions'].items())
            gaps.append(dict(kind=decl['kind'], observation_ids=[], record_ids=sorted(decl['revisions']),
                reason=('Historical declaration; current revisions differ. ' if stale else '') +
                       decl['reason'] + ' Reference: ' + decl['reference']))
        scope = copy.deepcopy(group['scope'])
        scope.update(case_ids=sorted(cases), case_digests={k: contract_digest('CaseSpec', v) for k, v in cases.items()})
        report = validate('CoverageReport', dict(schema_version=1, kind='CoverageReport',
            report_id='coverage-' + digest([binding, scope, sections, gaps]), binding=binding,
            scope=scope, sections=sections, gap_candidates=gaps))
        # Validate each original observation against its own complete plan. Plans
        # share an exact binding pin; capture-only legacy runs have no plan.
        plans = [b['expectations'] for b in group.get('runs', []) if b['expectations'] is not None]
        plan = plans[0] if plans else None
        _need(all(p == plan for p in plans), 'Different plans cannot share a binding group')
        check_coverage_runtime_links(report, [a['observation'] for a in attempts.values()],
            [f for a in attempts.values() for f in a['findings']], expectations=plan)
        results.append(dict(report=report, attempts=attempts, runs=runs, gap_contexts=gap_contexts,
            supersessions=copy.deepcopy(group.get('supersessions', [])),
            historical_catalog=_records(group, catalog, binding, cases, attempts, sections, current=False),
            current_catalog=_records(group, catalog, binding, cases, attempts, sections, current=True)))
    _need(catalog_unchanged(selection, catalog), 'Catalog changed during reconciliation; retry with a fresh read')
    return dict(schema_version=1, catalog_receipt=catalog, groups=results,
                global_verified_percent=None, verification_awards=False,
                limitation='Declared contexts only; extraction completeness and broader gameplay remain separate.')

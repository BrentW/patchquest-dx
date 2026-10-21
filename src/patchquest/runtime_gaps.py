"""Private investigation leads from the existing coverage receiver.

No catalog insertion, verification awards, emulator execution or second store.
Caller-owned groups and receiver results are trusted local inputs, not browser
payloads. Discovery labels describe the route; they never authenticate a run.
"""
import copy
import json
import re

from .runtime_contracts import ContractError, contract_digest, validate
from .runtime_coverage import catalog_unchanged, digest
from .state import Conflict, canonical, text


KINDS = ('uncatalogued', 'unexercised', 'unmapped', 'preserved_source', 'graphics_text', 'discovery')
DISCOVERY_MODES = ('exhaustive_renderer', 'scripted_navigation', 'random_exploration', 'debug_assisted', 'unknown')
LABELS = dict(uncatalogued='No catalog association', unexercised='Known text without a captured context',
              unmapped='Mapping needs investigation', preserved_source='Source text intentionally preserved',
              graphics_text='Text in graphics', discovery='Discovery outside the planned inventory')


def _need(value, reason):
    if not value:
        raise ContractError(reason)


def _hex(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None


def candidates(result, groups):
    """Project reasoned leads without changing any coverage denominator.

    Optional group.discovery_modes maps an original manifest hash to a reviewed
    {mode, reason, reference}. Omission means unknown, never exhaustive.
    """
    _need(result.get('schema_version') == 1 and result.get('verification_awards') is False
          and result.get('global_verified_percent') is None, 'Receiver result required')
    metadata = {contract_digest('RunBinding', g['binding']): g for g in groups}
    receipt = result['catalog_receipt']
    output = {}
    for group in result['groups']:
        report = validate('CoverageReport', group['report'])
        binding = report['binding']
        gid = contract_digest('RunBinding', binding)
        _need(gid in metadata, 'Missing caller-owned group')
        modes = metadata[gid].get('discovery_modes', {})
        _need(type(modes) is dict and set(modes) <= {r['manifest_sha256'] for r in group['runs']},
              'Discovery policy must name an original manifest in this group')
        for sha, value in modes.items():
            _need(_hex(sha) and type(value) is dict and set(value) == {'mode', 'reason', 'reference'}
                  and value['mode'] in DISCOVERY_MODES
                  and all(type(value[k]) is str and 0 < len(value[k].strip()) <= 4000
                          for k in ('reason', 'reference')), 'Invalid reviewed discovery policy')
        snapshot = receipt['snapshots'][binding['snapshot']]

        def add(kind, records, observation_ids, reason, *, discovery=None, case_ids=()):
            observations = [group['attempts'][oid] for oid in observation_ids]
            revisions = {key:snapshot[key] for key in records}
            current = {key:receipt['heads'].get(key) for key in records}
            provenance = [dict(observation_id=a['observation']['observation_id'],
                run_id=a['observation']['run_id'], case_id=a['observation']['case_id'],
                method=a['observation']['method'], reach_method=a['observation']['reach_method'],
                purposes=sorted(a['purposes']), status=a['status'], captured=a['captured'],
                superseded=a['superseded'], manifest_sha256s=a['manifest_sha256s'])
                for a in observations]
            # Identity excludes mutable catalog heads and display order. A fresh
            # build/observation/declaration yields a separate historical lead.
            identity = dict(group_id=gid, kind=kind, records=revisions,
                            observations=sorted(observation_ids), case_ids=sorted(case_ids),
                            reason=reason, discovery=discovery)
            cid = digest(identity)
            output[cid] = dict(candidate_id=cid, issue_id='runtime-gap-'+cid,
                group_id=gid, report_id=report['report_id'], build_id=binding['build_id'],
                snapshot=binding['snapshot'], kind=kind, label=LABELS[kind], reason=reason,
                record_revisions=revisions, current_revisions=current,
                freshness='stale' if revisions != current else 'current',
                observation_ids=sorted(observation_ids), provenance=provenance,
                case_ids=sorted(case_ids), discovery=copy.deepcopy(discovery), verification_awards=False)

        for index, gap in enumerate(report['gap_candidates']):
            # The original diagnostic list remains intact. Its enumeration rows
            # are presented below with their original run and worker provenance.
            if (gap['kind'] == 'unmapped' and not gap['record_ids'] and not gap['observation_ids']
                    and gap['reason'].startswith('Runner discovery retained without expanding declared scope: ')):
                continue
            reason = gap['reason']
            if gap['kind'] == 'uncatalogued' and not any(
                    group['attempts'][oid]['captured'] for oid in gap['observation_ids']):
                reason = 'Declared context has no known catalog association and no confirmed capture. Displayed text is not established.'
            cid = group.get('gap_contexts', {}).get(str(index))
            _need(cid is None or cid in report['scope']['case_ids'], 'Gap context outside declared inventory')
            add(gap['kind'], gap['record_ids'], gap['observation_ids'], reason, case_ids=[cid] if cid else [])
        for run in group['runs']:
            sha = run['manifest_sha256']
            policy = modes.get(sha, dict(mode='unknown', reason='Discovery method not reviewed.', reference=''))
            reaches = sorted({a['observation']['reach_method'] for a in group['attempts'].values()
                              if sha in a['manifest_sha256s']})
            if 'debug_injection' in reaches:
                _need(policy['mode'] in ('unknown', 'debug_assisted'),
                      'Debug access cannot be labeled ordinary navigation or exhaustive rendering')
                mode = 'debug_assisted'
            else:
                mode = policy['mode']
            for gap in run['discovery']['gaps']:
                add('discovery', [], [], 'Enumeration differs from the declared inventory; investigate the original evidence.',
                    discovery=dict(manifest_sha256=sha, run_id=run['run_id'], admitted=run['admission'] is not None,
                        mode=mode, policy=copy.deepcopy(policy), reach_methods=reaches, original=copy.deepcopy(gap),
                        limitation='Enumeration is not proof that this text was displayed. Scope and completeness are unchanged.'))
    return sorted(output.values(), key=lambda c: (KINDS.index(c['kind']), c['build_id'], c['candidate_id']))


def page(store, result, groups, params=None):
    """Bounded, read-only page. Existing issue heads are links, not coverage."""
    p = params or {}
    _need(type(p) is dict and not set(p) - {'kind', 'group_id', 'offset', 'limit'}, 'Unknown gap filter')
    kind, gid = p.get('kind', ''), p.get('group_id', '')
    offset, limit = p.get('offset', 0), p.get('limit', 20)
    _need(kind in ('', *KINDS) and (gid == '' or _hex(gid)), 'Invalid gap filter')
    _need(type(offset) is int and 0 <= offset <= 1000000 and type(limit) is int and 1 <= limit <= 100,
          'Invalid gap page')
    rows = candidates(result, groups)
    counts = {key:sum(r['kind'] == key for r in rows) for key in KINDS}
    rows = [r for r in rows if (not kind or r['kind'] == kind) and (not gid or r['group_id'] == gid)]
    issues = {i['id']:i for i in store.issues()}
    selected = copy.deepcopy(rows[offset:offset+limit])
    for row in selected:
        issue = issues.get(row['issue_id'])
        row['issue'] = ({k:issue[k] for k in ('id', 'revision', 'title', 'status')} if issue else None)
    _need(catalog_unchanged(store, result['catalog_receipt']), 'Catalog changed; refresh discovery')
    return dict(schema_version=1, catalog_read_sha256=result['catalog_receipt']['read_sha256'],
                items=selected, total=len(rows), counts=counts, offset=offset, limit=limit,
                verification_awards=False, global_verified_percent=None,
                limitation='Investigation leads only. Known catalog coverage, discovery and normal gameplay stay separate.')


def create_issue(store, result, groups, *, candidate_id, catalog_read_sha256, note='', actor=''):
    """Create one ordinary issue, checking freshness under the Store writer lock.

    Existing issues are returned unchanged, including resolved human decisions.
    Editing/triage continues through issue-put's existing revision/CAS contract.
    This function receives a newly reconciled server result, not client evidence.
    """
    _need(_hex(candidate_id) and _hex(catalog_read_sha256), 'Invalid candidate/read identity')
    text(note, 'investigation note', 4000)
    receipt = result['catalog_receipt']
    if receipt['read_sha256'] != catalog_read_sha256:
        raise Conflict('Catalog changed; refresh discovery before creating an issue.')
    row = next((r for r in candidates(result, groups) if r['candidate_id'] == candidate_id), None)
    _need(row is not None, 'Candidate is no longer present; refresh discovery')
    # BEGIN IMMEDIATE excludes all cooperating catalog/build writers. The
    # existing read-only receipt API sees the same committed state while this
    # transaction holds that lock; no independent database/schema is introduced.
    with store.connection() as db, store.transaction(db):
        if not catalog_unchanged(store, receipt):
            raise Conflict('Catalog or build changed; refresh discovery.')
        old = db.execute('SELECT revision,payload FROM issues WHERE id=?', (row['issue_id'],)).fetchone()
        if old is not None:
            return dict(created=False, issue=dict(json.loads(old['payload']), revision=old['revision']))
        proof = dict(candidate_id=candidate_id, group_id=row['group_id'], report_id=row['report_id'],
                     catalog_read_sha256=catalog_read_sha256, snapshot=row['snapshot'],
                     build=receipt['builds'][row['build_id']], tested=row['record_revisions'],
                     current=row['current_revisions'], freshness=row['freshness'],
                     case_ids=row['case_ids'], observation_ids=row['observation_ids'],
                     provenance=row['provenance'], discovery=row['discovery'])
        # Large composed contexts are never silently truncated to fit an issue.
        description = (row['reason'] + '\n\nInvestigation candidate only; no source text was invented, '
            'no translation changed and no verification awarded.\n\n' + note.strip() +
            '\n\nEvidence association (historical revisions stay historical):\n' + canonical(proof))
        text(description, 'gap issue evidence', 20000)
        issue = store._put_issue(db, dict(id=row['issue_id'], title=LABELS[row['kind']],
            category='runtime_gap', description=description, status='open',
            record_ids=sorted(row['record_revisions']), build_id=row['build_id'],
            references=['Runtime gap: '+candidate_id, 'Coverage report: '+row['report_id'],
                        'Binding group: '+row['group_id'], 'Catalog read: '+catalog_read_sha256]), 0, actor)
        return dict(created=True, issue=issue)

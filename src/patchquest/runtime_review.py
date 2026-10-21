"""Read-only presentation of reconciled runtime evidence and private contact sheets.

The composition root owns producer admission, the selected catalog and artifact
graph. Browser parameters select only bounded views of that existing evidence.
"""
import base64
import copy
import hashlib
import html
import json
from pathlib import Path
import struct
import threading

from .core.context import OutputPolicy
from .runtime_artifacts import reference
from .runtime_contracts import COVERAGE_STATUSES, ContractError, contract_digest, validate, verify_evidence_bytes
from .runtime_coverage import catalog_unchanged, digest, reconcile


def _need(value, message):
    if not value:
        raise ContractError(message)


def _params(params):
    _need(type(params) is dict and not set(params) -
          {'group_id', 'build_id', 'status', 'method', 'purpose', 'offset', 'limit'}, 'Unknown review filter')
    result = dict(offset=0, limit=50, **{k: v for k, v in params.items() if k not in ('offset', 'limit')})
    for key, default, maximum in (('offset', 0, 1000000), ('limit', 50, 200)):
        value = params.get(key, default)
        _need(type(value) is int and (0 if key == 'offset' else 1) <= value <= maximum, 'Invalid review page')
        result[key] = value
    for key, choices in (('status', COVERAGE_STATUSES), ('method', ('synthetic', 'automated_runtime')),
                         ('purpose', ('renderer', 'normal_gameplay'))):
        _need(result.get(key, '') in ('', *choices), 'Invalid review filter')
    for key in ('group_id', 'build_id'):
        _need(type(result.get(key, '')) is str and len(result.get(key, '')) <= 200, 'Invalid review identity')
    return result


def _summary(section):
    return copy.deepcopy({key: value for key, value in section.items() if key != 'rows'})


def _order(item):
    return (item['build_id'], item['group_id'], item['scene_ids'], item['message_id'] or '',
            -1 if item['page'] is None else item['page'], item['case_id'])


def _metadata(groups):
    result = {}
    for group in groups:
        key = contract_digest('RunBinding', group['binding'])
        cases = {c['case_id']: validate('CaseSpec', c) for c in group['cases']}
        scenes = {}
        for run in group.get('runs', []):
            manifest = json.loads(run['manifest_bytes'])
            for request in manifest['definition']['requests']:
                cid, scene = request['case']['case_id'], request.get('scene')
                if scene is None:
                    continue
                item = dict(scene_id=scene['scene_id'], reach_method=scene['reach_method'],
                            checkpoint=scene.get('checkpoint'), checkpoint_binding=scene.get('checkpoint_binding'),
                            regeneration=scene.get('regenerate_from'), steps=scene.get('steps'))
                if item not in scenes.setdefault(cid, []):
                    scenes[cid].append(item)
        result[key] = cases, scenes
    return result


def review_page(result, groups, params=None, *, historical_contexts=(), contact_sheets=()):
    """Project an existing receiver result; copy its counts, never assess evidence.

    Inputs are trusted local receiver outputs, not imported browser assertions.
    Historical investigation contexts are explicitly separate from CaseSpecs.
    """
    params = _params(params or {})
    _need(result.get('schema_version') == 1 and result.get('global_verified_percent') is None
          and result.get('verification_awards') is False, 'Reconciled receiver result required')
    _need(type(historical_contexts) in (list, tuple) and len(historical_contexts) <= 100000,
          'Bounded historical contexts required')
    metadata = _metadata(groups)
    output, items = [], []
    heads = result['catalog_receipt']['heads']
    for group in result['groups']:
        report = validate('CoverageReport', group['report'])
        binding = report['binding']; gid = contract_digest('RunBinding', binding)
        _need(gid in metadata, 'Group metadata differs from receiver')
        cases, scenes = metadata[gid]
        _need(set(cases) == set(report['scope']['case_ids']) and all(
            contract_digest('CaseSpec', c) == report['scope']['case_digests'][cid] for cid, c in cases.items()),
            'Case metadata differs from receiver')
        output.append(dict(group_id=gid, build_id=binding['build_id'], binding=binding,
            scope={k:copy.deepcopy(v) for k,v in report['scope'].items() if k not in ('case_ids','case_digests')},
            sections=[_summary(s) for s in report['sections']],
            historical_catalog=[_summary(s) for s in group['historical_catalog']],
            current_catalog=[_summary(s) for s in group['current_catalog']],
            gap_candidates=dict(total=len(report['gap_candidates']), items=copy.deepcopy(report['gap_candidates'][:50])),
            runs=[dict(manifest_sha256=r['manifest_sha256'], run_id=r['run_id'],
                admitted=r['admission'] is not None,
                discovery=dict(inventory_count=len(r['discovery']['inventories']),
                    gap_count=len(r['discovery']['gaps']), gaps=copy.deepcopy(r['discovery']['gaps'][:50]),
                    enumeration_history=copy.deepcopy(r['discovery']['enumeration_history']))) for r in group['runs']]))
        current = {}
        for section in group['current_catalog']:
            for record in section['rows']:
                for context in record['cases']:
                    current.setdefault((section['scope_kind'], section['method'], context['case_id']), []).append(
                        dict(record_id=record['record_id'], revision=record['revision'], **context))
        for section in report['sections']:
            purpose, method = section['scope_kind'], section['method']
            for row in section['rows']:
                case = cases[row['case_id']]
                attempts = [group['attempts'][oid] for oid in row['observation_ids']]
                observations = [copy.deepcopy(a['observation']) for a in attempts]
                contexts = current.get((purpose, method, case['case_id']), [])
                freshness = 'stale' if any(c['status'] == 'stale' for c in contexts) else 'current'
                captures = []
                for observation in observations:
                    for capture in observation['captures']:
                        ref = capture['evidence']
                        captures.append(dict(evidence_id=ref['evidence_id'], sha256=ref['sha256'],
                            reference=ref, frame=capture['frame'], source_run_id=observation['run_id'],
                            observation_id=observation['observation_id'], media_type=ref['media_type']))
                basis = scenes.get(case['case_id'], [])
                item = dict(review_id=digest([gid, case['case_id'], purpose, method]), group_id=gid,
                    build_id=binding['build_id'], case_id=case['case_id'], case_sha256=contract_digest('CaseSpec', case),
                    message_id=case['message_id'], page=case['page'], scene_ids=[s['scene_id'] for s in basis],
                    status=row['status'], reason=row['reason'], purpose=purpose, method=method,
                    freshness=freshness, current_contexts=copy.deepcopy(contexts),
                    reach_methods=sorted({o['reach_method'] for o in observations}),
                    record_revisions={k: binding['records'][k] for k in case['record_ids']},
                    current_revisions={k: heads.get(k) for k in case['record_ids']},
                    observations=observations, findings=[copy.deepcopy(f) for a in attempts for f in a['findings']],
                    unselected_attempts=[{key:copy.deepcopy(a[key]) for key in
                        ('observation','findings','status','reason','purposes','captured','superseded')}
                        for oid,a in group['attempts'].items() if a['observation']['case_id']==case['case_id']
                        and oid not in row['observation_ids']],
                    captures=captures, comparison_axes=dict(binding=binding, case=case, starting_states=basis,
                        reach_methods=sorted({o['reach_method'] for o in observations}),
                        capture_frames=[c['frame'] for c in captures]),
                    superseded_observations=[copy.deepcopy(a['observation']) for a in group['attempts'].values()
                        if a['superseded'] and a['observation']['case_id'] == case['case_id']])
                if any(params.get(key) and item[field] != params[key] for key, field in
                       (('group_id', 'group_id'), ('build_id', 'build_id'), ('purpose', 'purpose'), ('method', 'method'))):
                    continue
                status = params.get('status')
                if status and not (item['freshness'] == 'stale' if status == 'stale' else item['status'] == status):
                    continue
                items.append(item)
    items.sort(key=lambda r: (*_order(r), r['purpose'], r['method']))
    start, limit = params['offset'], params['limit']
    return dict(schema_version=1, catalog_read_sha256=result['catalog_receipt']['read_sha256'],
        freshness='current', limitation=result['limitation'], global_verified_percent=None, verification_awards=False,
        groups=output, items=items[start:start+limit], total=len(items), offset=start, limit=limit,
        historical_contexts=dict(total=len(historical_contexts), items=[{k:copy.deepcopy(v) for k,v in row.items()
            if k in {'candidate_context_id','window','records','record_revision_comparison',
                'retained_legacy_execution_status','retained_legacy_frames','unexercised_in_selected_pilot',
                'not_a_new_executable_CaseSpec','observed_values','scope_limit','catalog_mapping_complete'}}
            for row in historical_contexts[:50]],
            limitation='Historical investigation contexts; not executable cases or part of the case denominator.'),
        contact_sheets=copy.deepcopy(list(contact_sheets)))


def comparison(left, right):
    """Explain selected-pair differences without inferring animation or equivalence."""
    axes = ('binding', 'case', 'starting_states', 'reach_methods', 'capture_frames')
    differences = [axis for axis in axes if left['comparison_axes'][axis] != right['comparison_axes'][axis]]
    if not left['comparison_axes']['starting_states'] or not right['comparison_axes']['starting_states']:
        differences.append('unknown_starting_state')
    return dict(differences=differences, same_recorded_setup=not differences,
        limitation='Still captures do not establish animation timing or interchangeable starting states.')


def _image(ref, resolve):
    found = resolve(ref)
    _need(type(found) is dict and found.get('available') is True
          and verify_evidence_bytes(ref, found.get('data')), 'Capture bytes unavailable or changed')
    raw = found['data']
    _need(ref['media_type'] == 'image/png' and 33 <= len(raw) <= 16*1024*1024 and raw[:8] == b'\x89PNG\r\n\x1a\n'
          and raw[12:16] == b'IHDR', 'PNG capture required')
    width, height = struct.unpack('>II', raw[16:24])
    _need(1 <= width <= 4096 and 1 <= height <= 4096 and width*height <= 16000000,
          'Capture dimensions exceed review bounds')
    return raw, width, height


class ReviewProvider:
    """Explicit project-bound provider for the existing authenticated Studio seam."""
    def __init__(self, selection, groups, *, admit_run, artifacts, historical_contexts=(), contact_sheets=()):
        context = selection.context if hasattr(selection, 'context') else selection
        self.project_root = context.root.resolve()
        self.identity = (context.manifest['project_id'], context.manifest['source']['sha256'])
        self.groups = copy.deepcopy(groups)
        self.admit_run, self.artifacts = admit_run, artifacts
        self.historical_contexts = copy.deepcopy(historical_contexts)
        self.contact_sheets = copy.deepcopy(contact_sheets)
        self._images, self._lock = {}, threading.RLock()

    def _selected(self, store):
        _need(store.context.root.resolve() == self.project_root and
              (store.context.manifest['project_id'], store.context.manifest['source']['sha256']) == self.identity,
              'Review provider belongs to another project')

    def read(self, store, params):
        # A single provider shares a nonblocking artifact service across HTTP
        # threads. Serialize full operations, including reconciliation reads.
        with self._lock:
            return self._read(store, params)

    def _read(self, store, params):
        self._selected(store)
        params = _params(params)
        result = reconcile(store, self.groups, admit_run=self.admit_run, resolve_evidence=self.artifacts.resolve)
        page = review_page(result, self.groups, params, historical_contexts=self.historical_contexts,
                           contact_sheets=self.contact_sheets)
        allowed = {}
        for group in result['groups']:
            for attempt in group['attempts'].values():
                for capture in attempt['observation']['captures']:
                    ref = capture['evidence']; allowed[(ref['evidence_id'], ref['sha256'])] = ref
        for sheet in self.contact_sheets:
            ref = validate('EvidenceRef', sheet['reference'])
            allowed[(ref['evidence_id'], ref['sha256'])] = ref
        for item in page['items']:
            for capture in item['captures']:
                try:
                    _, width, height = _image(capture['reference'], self.artifacts.resolve)
                    capture.update(available=True, width=width, height=height)
                except (ValueError, KeyError, OSError, TypeError):
                    capture.update(available=False, reason='Original capture unavailable or changed.')
        _need(catalog_unchanged(store, result['catalog_receipt']), 'Catalog changed; refresh runtime review')
        with self._lock:
            self._images = allowed
        return page

    def image(self, store, evidence_id, sha256):
        self._selected(store)
        with self._lock:
            ref = self._images.get((evidence_id, sha256))
            _need(ref is not None, 'Image outside selected review evidence')
            return _image(ref, self.artifacts.resolve)[0]

    def gaps(self, store, params):
        """Read bounded investigation candidates from the same trusted source."""
        from .runtime_gaps import page
        with self._lock:
            self._selected(store)
            result = reconcile(store, self.groups, admit_run=self.admit_run, resolve_evidence=self.artifacts.resolve)
            return page(store, result, self.groups, params)

    def gap_issue(self, store, params, *, actor=''):
        """Only opaque candidate/read identities cross the browser boundary."""
        from .runtime_gaps import create_issue
        _need(type(params) is dict and set(params) == {'candidate_id', 'catalog_read_sha256'},
              'Candidate and catalog read identities required')
        with self._lock:
            self._selected(store)
            result = reconcile(store, self.groups, admit_run=self.admit_run, resolve_evidence=self.artifacts.resolve)
            return create_issue(store, result, self.groups, actor=actor, **params)


def write_contact_sheets(items, *, resolve_evidence, artifacts, destination, page_size=6):
    """Prepare one immutable private HTML package; never invoked by an HTTP GET.

    Each image embeds exact verified original PNG bytes at native dimensions.
    The artifact graph owner retains the resulting HTML and provenance sidecar.
    """
    _need(type(items) is list and 1 <= len(items) <= 200 and type(page_size) is int
          and 1 <= page_size <= 12, 'Bounded contact-sheet selection required')
    out = Path(destination).absolute()
    _need(not out.exists() and out.resolve() == out, 'Fresh unredirected sheet destination required')
    tiles, sources, input_bytes = [], [], 0
    seen = set()
    for item in sorted(items, key=_order):
        for capture in sorted(item['captures'], key=lambda c: c['frame']):
            ref = validate('EvidenceRef', capture['reference'])
            identity = (item['group_id'], item['case_id'], item['purpose'], item['method'],
                        capture['observation_id'], capture['frame'], ref['evidence_id'])
            if identity in seen:
                continue
            seen.add(identity)
            _need(len(sources) < 200, 'Contact-sheet image bound exceeded')
            raw, width, height = _image(ref, resolve_evidence)
            input_bytes += len(raw)
            _need(input_bytes <= 32*1024*1024, 'Contact-sheet input byte budget exceeded')
            source = dict(group_id=item['group_id'], build_id=item['build_id'], case_id=item['case_id'],
                message_id=item['message_id'], page=item['page'], scene_ids=item['scene_ids'],
                frame=capture['frame'], observation_id=capture['observation_id'],
                source_run_id=capture['source_run_id'], original=ref,
                status=item['status'], purpose=item['purpose'], method=item['method'],
                record_revisions=item['record_revisions'], width=width, height=height)
            sources.append(source)
            image='data:image/png;base64,'+base64.b64encode(raw).decode('ascii')
            label=html.escape(f"{item['case_id']} · page {item['page']} · frame {capture['frame']}")
            tiles.append(f'<figure><a href="{image}" download="{ref["sha256"]}.png">'
                f'<img src="{image}" width="{width}" height="{height}" alt="{label}"></a>'
                f'<figcaption>{label}<br>{html.escape(item["build_id"])} · {html.escape(item["status"])}'
                f'<br>{html.escape(item["purpose"].replace("_", " "))} · {html.escape(item["method"].replace("_", " "))}'
                f'<br>Original {ref["sha256"][:16]} · <a href="provenance.json">Evidence details</a>'
                '</figcaption></figure>')
    _need(bool(sources), 'No captured images selected')
    storage = artifacts.directory.resolve()
    _need(not out.is_relative_to(storage) and not storage.is_relative_to(out), 'Sheet outputs overlap artifact storage')
    out.mkdir(parents=True)
    policy=OutputPolicy(out)
    provenance=dict(schema_version=1, kind='runtime_contact_sheet', derived_only=True,
                    originals_unchanged=True, sources=sources, verification_awards=False)
    proof=(json.dumps(provenance,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf8')
    proof_ref=artifacts.register(reference(proof,evidence_id='sheet-provenance-'+hashlib.sha256(proof).hexdigest(),
        media_type='application/json',provenance=dict(producer='patchquest.runtime_review',method='static',
                                                    run_id=None,case_id=None)),proof)
    policy.write_new('provenance.json',proof)
    pages=[]
    for start in range(0,len(tiles),page_size):
        number=len(pages)+1
        document=('<!doctype html><html lang="en"><meta charset="utf-8"><title>Private runtime contact sheet</title>'
            '<style>body{font:14px system-ui;margin:20px;color:#182d28;background:#f8faf8}'
            '.sheet{display:grid;grid-template-columns:repeat(3,max-content);gap:16px}'
            'figure{margin:0;padding:12px;background:white;border:1px solid #cad7d1}'
            'img{display:block;image-rendering:pixelated}figcaption{max-width:280px;margin-top:8px;overflow-wrap:anywhere}'
            '</style><h1>Private runtime contact sheet</h1><p>Derived review only. Original evidence and findings are unchanged.</p>'
            f'<p>Page {number} · <a href="provenance.json">Exact provenance</a></p><main class="sheet">'+
            ''.join(tiles[start:start+page_size])+'</main></html>').encode('utf8')
        name=f'contact-sheet-{number}.html';policy.write_new(name,document)
        ref=reference(document,evidence_id='contact-sheet-'+hashlib.sha256(document).hexdigest(),
            media_type='text/html',provenance=dict(producer='patchquest.runtime_review',method='static',run_id=None,case_id=None))
        pages.append(dict(filename=name,reference=artifacts.register(ref,document),
                          source_range=[start,min(start+page_size,len(tiles))]))
    return dict(provenance=proof_ref,pages=pages,source_count=len(sources))

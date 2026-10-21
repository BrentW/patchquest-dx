"""Explicit impact planning and reviewed coverage consumption, never verification.

Dependency completeness is a trusted caller declaration, not discovered from a
ROM, labels, unchanged wording or a previous pass. No runner or coverage engine.
"""
import hashlib
import json
import re
from .runtime_contracts import validate, contract_digest, binding_changes

VERSION = '1'
CATEGORIES = frozenset(('context','layout','font','control','pointer','renderer','scenario','configuration'))
FINAL_CHECKS = ('normal-gameplay','cold-boot','save-load','normal-speed-pacing','audio','responsiveness')

class RegressionError(ValueError):
    pass

def need(condition, reason):
    if not condition: raise RegressionError(reason)

def text(value):
    need(type(value) is str and 0 < len(value) <= 200 and
         re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]*',value), 'Invalid dependency identity')

def hashed(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,
        separators=(',',':'),allow_nan=False).encode()).hexdigest()

def names(values):
    items=sorted(values)
    return ', '.join(items[:4])+(' (and '+str(len(items)-4)+' more; pinned graph retains all)' if len(items)>4 else '')

def dependency_map(cases, binding, revisions, case_dependencies, *, complete=False):
    """Freeze an explicit graph; unknown references remain unknown, not guessed."""
    need(type(cases) in (list,tuple) and len(cases)<=10000,'Bounded explicit dependency cases required')
    need(type(case_dependencies) is dict,'Explicit dependency mapping required')
    b=validate('RunBinding',binding);cs=[validate('CaseSpec',c) for c in cases]
    need(len({c['case_id'] for c in cs})==len(cs),'Duplicate dependency case identity')
    need(set(case_dependencies)<={c['case_id'] for c in cs},'Dependency case outside declared scope')
    return graph(dict(schema_version=1,kind='RegressionDependencies',complete=complete,
        binding_sha256=contract_digest('RunBinding',b),revisions=revisions,
        cases={c['case_id']:dict(case_sha256=contract_digest('CaseSpec',c),
            dependencies=case_dependencies.get(c['case_id'],[])) for c in cs}))

def graph(value):
    need(type(value) is dict and set(value)=={'schema_version','kind','complete','binding_sha256','revisions','cases'},'Invalid dependency document')
    need(type(value['schema_version']) is int and value['schema_version']==1 and value['kind']=='RegressionDependencies','Unknown dependency version')
    need(type(value['complete']) is bool,'Explicit completeness boolean required')
    need(type(value['binding_sha256']) is str and re.fullmatch('[0-9a-f]{64}',value['binding_sha256']),'Invalid graph binding hash')
    need(type(value['revisions']) is dict and len(value['revisions'])<=10000,'Bounded dependency revisions required')
    for key,version in value['revisions'].items():
        text(key);need(type(version) is str and 0<len(version)<=200,'Explicit dependency version strings required')
    need(type(value['cases']) is dict and len(value['cases'])<=10000,'Bounded case map required')
    edges=0
    for key,row in value['cases'].items():
        need(type(key) is str and bool(key.strip()) and len(key)<=200 and not any(ord(c)<32 for c in key),
             'Invalid opaque case identity')
        need(type(row) is dict and set(row)=={'case_sha256','dependencies'},'Invalid case dependency row')
        need(type(row['case_sha256']) is str and re.fullmatch('[0-9a-f]{64}',row['case_sha256']),'Invalid dependency case hash')
        ds=row['dependencies'];need(type(ds) is list and len(ds)<=10000 and all(type(d) is str for d in ds),'Invalid dependency list')
        need(len(set(ds))==len(ds),'Duplicate dependency reference');edges+=len(ds)
        need(edges<=100000,'Dependency edge budget exceeded')
        for dep in ds:text(dep)
    normalized=json.loads(json.dumps(value,allow_nan=False))
    for row in normalized['cases'].values():row['dependencies'].sort()
    return normalized

def plan_changes(cases, binding, *, baseline_binding=None, dependencies=None,
                 baseline_dependencies=None, prior_report=None,
                 prior_method='automated_runtime', full_sweep=False):
    """Return contract-v1 ChangeImpactPlan over the entire explicitly declared scope.

    Prior baseline passes are historical scheduling inputs only. The returned
    selected/deferred rows have reasons, never pass/verification statuses.
    """
    need(type(cases) in (list,tuple) and 0<len(cases)<=10000,'Nonempty bounded case scope required')
    cs=[validate('CaseSpec',c) for c in cases];ids=[c['case_id'] for c in cs]
    need(len(set(ids))==len(ids),'Duplicate case identity')
    b=validate('RunBinding',binding);old=validate('RunBinding',baseline_binding) if baseline_binding is not None else None
    need(all(set(c['record_ids'])<=set(b['records']) for c in cs),'Current case record revisions missing')
    need(type(full_sweep) is bool,'Explicit full-sweep boolean required')
    need(prior_method in ('automated_runtime','synthetic'),'Renderer execution method required')
    current=graph(dependencies) if dependencies is not None else None
    previous=graph(baseline_dependencies) if baseline_dependencies is not None else None
    reasons={key:[] for key in ids};priority=set();global_reasons=[]
    def all_cases(reason):
        if reason not in global_reasons:global_reasons.append(reason)
    if full_sweep:all_cases('Explicit full sweep requested.')
    if old is None:all_cases('No pinned baseline binding.')
    if current is None or previous is None:all_cases('Dependency graph unavailable; full declared scope required.')
    changed=set();record_changes=set();binding_delta=binding_changes(old,b) if old is not None else []
    if old is not None:
        record_changes={k for k in set(old['records'])|set(b['records']) if old['records'].get(k)!=b['records'].get(k)}
    if current is not None and previous is not None and old is not None:
        for g,bb,label in ((current,b,'current'),(previous,old,'baseline')):
            if not g['complete']:all_cases(label+' dependency completeness is unknown.')
            if g['binding_sha256']!=contract_digest('RunBinding',bb):all_cases(label+' dependency binding is stale.')
            for cid,row in g['cases'].items():
                if not row['dependencies'] or any(dep not in g['revisions'] for dep in row['dependencies']):
                    all_cases(label+' graph has unknown case dependencies.')
            for dep in g['revisions']:
                if ':' not in dep or not dep.split(':',1)[1] or dep.split(':',1)[0] not in CATEGORIES:all_cases('Unknown dependency category present.')
        if set(current['cases'])!=set(ids):all_cases('Current graph does not cover the exact declared case scope.')
        for case in cs:
            row=current['cases'].get(case['case_id'])
            if row and row['case_sha256']!=contract_digest('CaseSpec',case):all_cases('Current case-to-dependency identity is stale.')
        changed={k for k in set(current['revisions'])|set(previous['revisions']) if current['revisions'].get(k)!=previous['revisions'].get(k)}
        mapped={dep for g in (current,previous) for row in g['cases'].values() for dep in row['dependencies']}
        if changed-mapped:all_cases('Changed dependency has no explained case consumers.')
        for case in cs:
            cid=case['case_id'];now=current['cases'].get(cid);was=previous['cases'].get(cid)
            if was is None or now is None or was['case_sha256']!=contract_digest('CaseSpec',case):reasons[cid].append('New or changed exact case/context definition.')
            if now and was and set(now['dependencies'])!=set(was['dependencies']):reasons[cid].append('Case dependency membership changed.')
            hits=changed & (set(now['dependencies']) if now else set())
            if was:hits |= changed & set(was['dependencies'])
            if hits:reasons[cid].append('Changed dependencies: '+names(hits)+'.')
    for case in cs:
        hits=set(case['record_ids']) & record_changes
        if hits:reasons[case['case_id']].append('Changed exact record revisions: '+names(hits)+'.');priority.add(case['case_id'])
    if set(binding_delta)&{'adapter','emulator','configuration_sha256','detectors'}:
        all_cases('Shared adapter/emulator/configuration/detector binding changed.')
    if old is not None and set(old['artifacts'])!=set(b['artifacts']):all_cases('Artifact role set changed; dependency coverage unknown.')
    if 'scenario_sha256' in binding_delta and not any(k.startswith('scenario:') for k in changed):all_cases('Scenario binding changed without scoped scenario dependency evidence.')
    if set(binding_delta)&{'artifacts','snapshot','build_id','expectation_sha256'} and not (record_changes or changed):
        all_cases('Changed build/content/expectation identity has no explained dependency change.')
    report=validate('CoverageReport',prior_report) if prior_report is not None else None
    rows={}
    if report is None:all_cases('Prior renderer baseline evidence unavailable.')
    elif old is None or binding_changes(report['binding'],old):all_cases('Prior evidence is stale for the pinned baseline.')
    else:
        sections=[s for s in report['sections'] if s['scope_kind']=='renderer' and s['method']==prior_method]
        if sections:rows={r['case_id']:r for r in sections[0]['rows']}
        for case in cs:
            cid=case['case_id'];row=rows.get(cid)
            baseline_case=previous['cases'].get(cid) if previous else None
            if row is None or row['status']!='passed':reasons[cid].append('No passed renderer baseline for requested method (missing/failed/stale/unknown/interrupted).')
            elif baseline_case is None or report['scope']['case_digests'].get(cid)!=baseline_case['case_sha256']:
                reasons[cid].append('Prior evidence case definition does not match baseline dependencies.')
    for cid in ids:
        if global_reasons:reasons[cid]=global_reasons+reasons[cid]
    selected=[dict(case_id=cid,reason=' '.join(reasons[cid])) for cid in ids if reasons[cid]]
    positions={cid:i for i,cid in enumerate(ids)}
    selected.sort(key=lambda row:(row['case_id'] not in priority,positions[row['case_id']]))
    deferred=[dict(case_id=cid,reason='No mapped change and a matching historical renderer baseline; deferred, NOT verified for this build.') for cid in ids if not reasons[cid]]
    versions=None if current is None else dict(current['revisions'],**{'graph-current':hashed(current)})
    if versions is not None and previous is not None:versions['graph-baseline']=hashed(previous)
    result=dict(schema_version=1,kind='ChangeImpactPlan',binding=b,baseline_binding=old,case_ids=ids,
        dependency_revisions=versions,selected=selected,deferred=deferred,
        full_sweep_required=not deferred,additional_checks=list(FINAL_CHECKS),extensions={
            'patchquest:regression':dict(version=VERSION,case_digests={c['case_id']:contract_digest('CaseSpec',c) for c in cs},
                requested_prior_method=prior_method,dependency_basis='Explicit caller-attested complete dependency map; not discovered or independently proven.',
                execution_order=[r['case_id'] for r in selected],verification_awarded=False)})
    result['plan_id']='impact-'+hashed(result)
    return validate('ChangeImpactPlan',result)

def ordered_cases(cases, plan):
    """Compose execution priority explicitly; the runner selection seam uses sets."""
    p=validate('ChangeImpactPlan',plan);cs=[validate('CaseSpec',c) for c in cases]
    by_id={c['case_id']:c for c in cs}
    need(len(by_id)==len(cs) and set(by_id)==set(p['case_ids']),'Case scope differs from plan')
    diagnostic=p.get('extensions',{}).get('patchquest:regression',{})
    need(diagnostic.get('version')==VERSION and diagnostic.get('case_digests')=={k:contract_digest('CaseSpec',v) for k,v in by_id.items()},'Case definitions differ from plan')
    return [by_id[r['case_id']] for r in p['selected']+p['deferred']]


# This receiver is deliberately pure. Catalog freshness and producer trust are
# supplied through explicit local callbacks, never imported flags or paths.
def _catalog_receipt(value):
    need(type(value) is dict and set(value)=={'identity','heads','builds','snapshots','read_sha256'},
         'Complete canonical catalog read receipt required')
    payload={k:v for k,v in value.items() if k!='read_sha256'}
    need(value['read_sha256']==hashed(payload),'Catalog read receipt digest differs')
    identity=value['identity']
    need(type(identity) is dict and set(identity)=={'project_id','source_sha256'},'Catalog identity required')
    need(type(identity['project_id']) is str and 0<len(identity['project_id'])<=200,'Invalid project identity')
    def digest_string(v):return type(v) is str and re.fullmatch('[0-9a-f]{64}',v)
    need(digest_string(identity['source_sha256']),'Invalid selected source identity')
    def revisions(rows):
        need(type(rows) is dict and len(rows)<=100000,'Bounded catalog revision map required')
        need(all(type(k) is str and 0<len(k)<=200 and type(v) is int and v>0 for k,v in rows.items()),
             'Invalid catalog record revisions')
    revisions(value['heads'])
    need(type(value['snapshots']) is dict and len(value['snapshots'])<=1000,'Bounded retained snapshots required')
    for pin,rows in value['snapshots'].items():
        need(digest_string(pin),'Invalid retained snapshot digest');revisions(rows)
    need(type(value['builds']) is dict and len(value['builds'])<=1000,'Bounded retained builds required')
    for key,row in value['builds'].items():
        need(type(key) is str and 0<len(key)<=200 and type(row) is dict and
             set(row)=={'revision','payload_sha256','snapshot'},'Invalid retained build receipt')
        need(type(row['revision']) is int and row['revision']>0 and digest_string(row['payload_sha256']) and
             digest_string(row['snapshot']) and row['snapshot'] in value['snapshots'],
             'Invalid retained build/snapshot link')
    return json.loads(json.dumps(value,allow_nan=False))


def coverage_identity(report, catalog_receipt):
    """Pin a receiver report AND its read receipt for a caller-owned registry.

    This hash is not authentication. The registry must be independently configured
    from accepted runtime_coverage output, never echoed from an imported request.
    """
    report=validate('CoverageReport',report);catalog=_catalog_receipt(catalog_receipt)
    return hashed(dict(report=report,catalog_receipt=catalog))


def plan_from_coverage(cases, binding, *, baseline_binding=None, coverage_report=None,
                       baseline_catalog=None, current_catalog=None, admit_coverage=None,
                       check_catalog=None, dependencies=None, baseline_dependencies=None,
                       prior_method='automated_runtime', full_sweep=False):
    """Conservatively consume admitted canonical receiver output; no I/O or coverage math.

    admit_coverage(pin) is independent trusted local configuration. check_catalog
    is normally a closure over runtime_coverage.catalog_unchanged(selection, r).
    Both missing/false trust and stale current reads force full declared scope.
    Only the existing CoverageReport statuses guide planning; no new coverage or
    record verification is derived, and no Store/runner is constructed.
    """
    b=validate('RunBinding',binding)
    old=validate('RunBinding',baseline_binding) if baseline_binding is not None else None
    report=validate('CoverageReport',coverage_report) if coverage_report is not None else None
    baseline=_catalog_receipt(baseline_catalog) if baseline_catalog is not None else None
    current=_catalog_receipt(current_catalog) if current_catalog is not None else None
    need(admit_coverage is None or callable(admit_coverage),'Explicit local coverage admission callback required')
    need(check_catalog is None or callable(check_catalog),'Explicit local catalog freshness callback required')
    need(type(full_sweep) is bool,'Explicit full-sweep boolean required')
    need(prior_method in ('automated_runtime','synthetic'),'Renderer execution method required')
    fallback=[];proof=None;pin=None;admitted=False
    def expand(reason):
        if reason not in fallback:fallback.append(reason)
    if report is None or baseline is None:
        expand('Reviewed coverage report/catalog read receipt unavailable.')
    else:
        pin=coverage_identity(report,baseline)
        if admit_coverage is not None:
            proof=admit_coverage(pin)
        if proof is None:
            expand('Independent coverage producer admission unavailable.')
        else:
            need(type(proof) is dict and set(proof)=={'coverage_sha256','binding_sha256',
                 'catalog_read_sha256','scope_kind','method','reviewer','reference','reason'},
                 'Invalid independent coverage admission')
            for key in ('reviewer','reference','reason'):
                need(type(proof[key]) is str and bool(proof[key].strip()) and len(proof[key])<=4000,
                     'Independent coverage admission needs a bounded reason/reference')
            if (proof['coverage_sha256']!=pin or proof['binding_sha256']!=contract_digest('RunBinding',report['binding']) or
                    proof['catalog_read_sha256']!=baseline['read_sha256'] or proof['scope_kind']!='renderer' or
                    proof['method']!=prior_method):
                expand('Reviewed coverage identity, binding, read receipt or renderer method differs.')
            else:admitted=True
        rb=report['binding'];build=baseline['builds'].get(rb['build_id']);records=baseline['snapshots'].get(rb['snapshot'])
        if (build is None or build['snapshot']!=rb['snapshot'] or records is None or
                any(records.get(k)!=v for k,v in rb['records'].items())):
            expand('Baseline report differs from retained build/snapshot record revisions.')
    if current is None:
        expand('Current authoritative catalog read receipt unavailable.')
    else:
        if baseline is not None and report is not None and current['builds'].get(report['binding']['build_id'])!=baseline['builds'].get(report['binding']['build_id']):
            expand('Baseline retained build receipt changed or is absent from the current read.')
        if baseline is not None and baseline['identity']!=current['identity']:
            expand('Selected project/source identity differs from baseline coverage.')
        build=current['builds'].get(b['build_id']);records=current['snapshots'].get(b['snapshot'])
        if (build is None or build['snapshot']!=b['snapshot'] or records is None or
                any(records.get(k)!=v for k,v in b['records'].items())):
            expand('Target binding differs from retained build/snapshot record revisions.')
        if any(current['heads'].get(k)!=v for k,v in b['records'].items()):
            expand('Target record revisions are stale or absent from current catalog heads.')
        fresh=False
        if check_catalog is not None:
            try:fresh=check_catalog(json.loads(json.dumps(current))) is True
            except (OSError,ValueError,KeyError,TypeError):fresh=False
        if not fresh:expand('Current catalog read is unconfirmed or changed; refresh before planning.')
    # Do not make a stale/missing read look like the user's explicit full sweep.
    plan=plan_changes(cases,b,baseline_binding=old,dependencies=dependencies,
        baseline_dependencies=baseline_dependencies,prior_report=report,prior_method=prior_method,
        full_sweep=bool(full_sweep or fallback))
    if fallback:
        prefix='Production admission fallback: '+' '.join(fallback)+' '
        for row in plan['selected']:
            reason=row['reason']
            if not full_sweep:reason=reason.replace('Explicit full sweep requested.','').strip()
            row['reason']=prefix+reason
    annotation=plan['extensions']['patchquest:regression']
    annotation['coverage_consumer']=dict(coverage_sha256=pin,
        baseline_catalog_read_sha256=None if baseline is None else baseline['read_sha256'],
        current_catalog_read_sha256=None if current is None else current['read_sha256'],
        producer_admitted=admitted,
        fallback_reasons=fallback,authority='Caller-owned reviewed registry and current read freshness; not imported tags.',
        coverage_recomputed=False,verification_awarded=False)
    plan.pop('plan_id');plan['plan_id']='impact-'+hashed(plan)
    return validate('ChangeImpactPlan',plan)

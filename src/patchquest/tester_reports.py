"""Private, immutable tester submissions and revisioned local triage.

Intake never executes attachments, writes translations or creates verification.
"""
import hashlib
import json

from .state import Conflict, canonical, identity, now, text
from .screenshot_selection import _context as image_context
from .verification import _build

PREFIX = 'tester-report.v1.'
STATUSES = ('new', 'needs_info', 'accepted', 'duplicate', 'rejected', 'closed')
CATEGORIES = ('translation', 'layout', 'gameplay', 'crash', 'other')
LIMIT = 256 * 1024


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _string(value, name, limit, required=False):
    value = text(value, name, limit)
    if required and not value.strip():
        raise ValueError(name + ' is required')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError('Unsupported control characters')
    return value


def _ids(values, limit=100):
    if not isinstance(values, list) or len(values) > limit:
        raise ValueError('Expected a bounded list')
    result = [identity(v) for v in values]
    if len(set(result)) != len(result):
        raise ValueError('Duplicate identifiers')
    return sorted(result)


def _get(db, key):
    identity(key)
    row = db.execute('SELECT value FROM metadata WHERE key=?', (PREFIX + key,)).fetchone()
    if not row:
        raise KeyError('Unknown tester report')
    return json.loads(row[0])


def _save(store, db, report, action, actor):
    actor = _string(actor, 'actor', 200)
    report['revision'] += 1
    report['updated_at'] = now()
    db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (PREFIX + report['id'], canonical(report)))
    store._event(db, 'tester-report.' + report['id'], dict(action=action, actor=actor, report=report))
    return report


def _document(store, document):
    if not isinstance(document, dict) or set(document) != {'schema_version', 'report_type', 'project_id', 'source', 'reports'}:
        raise ValueError('Invalid tester report document')
    if (type(document['schema_version']) is not int or document['schema_version'] != 1 or
            document['report_type'] != 'tester-reports' or document['project_id'] != store.context.manifest['project_id']):
        raise ValueError('Unsupported schema or wrong project')
    if len(canonical(document).encode('utf8')) > LIMIT:
        raise ValueError('Tester import exceeds size limit')
    source = _string(document['source'], 'source namespace', 160, True)
    rows = document['reports']
    if not isinstance(rows, list) or not 1 <= len(rows) <= 50:
        raise ValueError('Supply 1..50 reports')
    parsed = []
    for row in rows:
        fields = {'external_id','title','description','category','steps','expected','observed',
                  'environment','build_label','artifact_sha256','suggested_translation','attachment_digests'}
        if not isinstance(row, dict) or set(row) - fields or not {'external_id','title','observed'} <= set(row):
            raise ValueError('Invalid report fields')
        item = {k: _string(row.get(k,''), k, limit, k in ('external_id','title','observed')) for k,limit in
                [('external_id',160),('title',300),('description',8000),('steps',8000),('expected',4000),
                 ('observed',8000),('environment',2000),('build_label',160),('artifact_sha256',64),
                 ('suggested_translation',4000)]}
        item['category'] = row.get('category','other')
        if item['category'] not in CATEGORIES:
            raise ValueError('Invalid tester category')
        item['attachment_digests'] = _ids(row.get('attachment_digests',[]),20)
        for digest in item['attachment_digests'] + ([item['artifact_sha256']] if item['artifact_sha256'] else []):
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Expected lowercase SHA-256')
        parsed.append(item)
    if len({r['external_id'] for r in parsed}) != len(parsed):
        raise ValueError('Duplicate report IDs in one import')
    return dict(schema_version=1,report_type='tester-reports',project_id=document['project_id'],source=source,reports=parsed)


def _plan(db, document):
    items = []
    for content in document['reports']:
        key = 'tester-' + _hash([document['source'],content['external_id']])
        row = db.execute('SELECT value FROM metadata WHERE key=?',(PREFIX+key,)).fetchone()
        digest = _hash(content)
        if row and json.loads(row[0])['content_sha256'] != digest:
            raise Conflict('An imported report ID already has different content. Preserve it and use a new external ID for a follow-up.')
        items.append(dict(id=key,content_sha256=digest,disposition='existing' if row else 'new'))
    return dict(token=_hash(dict(document=document,items=items)),items=items,
                new=sum(i['disposition']=='new' for i in items),existing=sum(i['disposition']=='existing' for i in items))


def preview_import(store, document):
    document = _document(store,document)
    with store.connection() as db, store.transaction(db,write=False):
        return dict(_plan(db,document),document=document)


def import_reports(store, document, preview_token, actor='agent'):
    document = _document(store,document)
    with store.connection() as db, store.transaction(db):
        plan = _plan(db,document)
        if plan['token'] != preview_token:
            raise Conflict('Import changed since preview. Preview again before importing.')
        count = db.execute('SELECT count(*) FROM metadata WHERE key LIKE ?', (PREFIX+'%',)).fetchone()[0]
        if count + plan['new'] > 5000:
            raise ValueError('Tester report limit reached')
        for entry,content in zip(plan['items'],document['reports']):
            if entry['disposition']=='existing':
                continue
            report = dict(id=entry['id'],revision=0,source=document['source'],content=content,
                          content_sha256=entry['content_sha256'],imported_at=now(),
                          triage=dict(status='new',notes='',issue_id='',duplicate_of='',binding=None))
            _save(store,db,report,'imported',actor)
        return dict(imported=plan['new'],existing=plan['existing'],ids=[i['id'] for i in plan['items']],translations_changed=0)


def _context(store, db, report, build_id='', record_ids=None, attachment_digests=None):
    _string(build_id,'build ID',200)
    records = _ids([] if record_ids is None else record_ids)
    images = _ids([] if attachment_digests is None else attachment_digests,20)
    binding = dict(build_id=build_id,build=None,records={},reviewed_heads={},attachments={})
    if build_id:
        _, build, revisions = _build(store,db,build_id)
        row = db.execute('SELECT revision,payload FROM builds WHERE id=?',(build_id,)).fetchone()
        binding['build'] = dict(build,revision=row['revision'],report_sha256=_hash(json.loads(row['payload'])))
        for key in records:
            if key not in revisions:
                raise ValueError('Record is absent from this build snapshot')
            binding['records'][key] = revisions[key]
            binding['reviewed_heads'][key] = store._get(db,key)['revision']
    elif records:
        raise ValueError('Select a build before linking translation revisions')
    for digest in images:
        ctx = image_context(store,db,digest)
        binding['attachments'][digest] = ctx['token']
    claimed = report['content']['artifact_sha256']
    matches = [name for name,digest in (binding['build'] or {}).get('artifacts',{}).items() if digest==claimed]
    match = 'unlinked' if not build_id else 'unreported' if not claimed else 'matched' if matches else 'mismatch'
    return dict(token=_hash(dict(report=report['content_sha256'],binding=binding)),binding=binding,
                artifact_match=match,matched_artifacts=matches,
                differs_from_build=[k for k,v in binding['records'].items() if binding['reviewed_heads'][k]!=v])


def context(store, key, build_id='', record_ids=None, attachment_digests=None):
    with store.connection() as db, store.transaction(db,write=False):
        return _context(store,db,_get(db,key),build_id,record_ids,attachment_digests)


def _decorate(store, db, report):
    result = dict(report,context=None,binding_unavailable=False,changed_since_triage=False,issue=None)
    binding = report['triage']['binding']
    if binding:
        try:
            result['context'] = _context(store,db,report,binding['build_id'],list(binding['records']),list(binding['attachments']))
            result['changed_since_triage'] = result['context']['binding'] != binding
        except (ValueError,KeyError,OSError,TypeError):
            result['binding_unavailable'] = True
            result['changed_since_triage'] = True
    if report['triage']['issue_id']:
        row=db.execute('SELECT revision,payload FROM issues WHERE id=?',(report['triage']['issue_id'],)).fetchone()
        result['issue']=dict(json.loads(row['payload']),revision=row['revision']) if row else None
    return result


def get(store, key):
    with store.connection() as db, store.transaction(db,write=False):
        return _decorate(store,db,_get(db,key))


def list_reports(store, status='', offset=0, limit=50):
    if status and status not in STATUSES:
        raise ValueError('Unknown intake status')
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:
        raise ValueError('Invalid report page')
    with store.connection() as db:
        total=0;rows=[]
        for row in db.execute('SELECT value FROM metadata WHERE key LIKE ? ORDER BY key',(PREFIX+'%',)):
            report=json.loads(row[0])
            if status and report['triage']['status']!=status:continue
            if offset<=total<offset+limit:rows.append(report)
            total+=1
        # List browsing is cheap; evidence is rechecked in detail/context and writes.
        return dict(total=total,offset=offset,items=rows)


def triage(store, key, expected, context_token, status, notes, build_id='', record_ids=None,
           attachment_digests=None, issue_id='', duplicate_of='', create_issue=False, actor='agent'):
    if status not in STATUSES or type(create_issue) is not bool:
        raise ValueError('Invalid intake status or issue option')
    notes = _string(notes,'triage notes',8000,status!='new')
    _string(issue_id,'issue ID',200);_string(duplicate_of,'duplicate report',200)
    with store.connection() as db, store.transaction(db):
        report = _get(db,key)
        if type(expected) is not int or report['revision'] != expected:
            raise Conflict('Tester report changed; reload and compare')
        ctx = _context(store,db,report,build_id,record_ids,attachment_digests)
        if ctx['token'] != context_token:
            raise Conflict('Build, translations or evidence changed; inspect the current context before triage')
        if create_issue and (issue_id or status!='accepted'):
            raise ValueError('Create an issue only for an accepted report without an existing issue')
        if status=='accepted' and (not build_id or ctx['artifact_match']=='mismatch' or not (issue_id or create_issue)):
            raise ValueError('Accepted reports require a compatible build and an issue')
        if bool(duplicate_of) != (status=='duplicate'):
            raise ValueError('Duplicate status requires its original report')
        if duplicate_of:
            seen={key};cursor=duplicate_of
            while cursor:
                if cursor in seen:
                    raise ValueError('Duplicate report cycle')
                seen.add(cursor);other=_get(db,cursor)
                cursor=other['triage']['duplicate_of']
        if issue_id and not db.execute('SELECT 1 FROM issues WHERE id=?',(issue_id,)).fetchone():
            raise KeyError('Unknown linked issue')
        if create_issue:
            issue_id='issue-'+key
            content=report['content']
            store._put_issue(db,dict(id=issue_id,title=content['title'],category='tester_report',
                description='Reported observation (not verification):\n'+content['observed']+'\n\nTriage:\n'+notes,
                status='open',build_id=build_id,record_ids=list(ctx['binding']['records']),
                references=['tester-report:'+key]),0,actor)
        report['triage']=dict(status=status,notes=notes,issue_id=issue_id,duplicate_of=duplicate_of,binding=ctx['binding'])
        return _save(store,db,report,'triaged',actor)


def history(store, key, after=0, limit=100):
    if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=500:
        raise ValueError('Invalid history page')
    with store.connection() as db:
        _get(db,key)
        return [dict(seq=r['seq'],created=r['created'],**json.loads(r['payload'])) for r in db.execute(
            'SELECT * FROM events WHERE kind=? AND seq>? ORDER BY seq LIMIT ?',('tester-report.'+key,after,limit))]

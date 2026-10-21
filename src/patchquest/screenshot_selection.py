"""Reviewed screenshot metadata. Image bytes and evidence remain private."""
from datetime import date
import hashlib
import json
import re
import uuid

from .core.context import confined
from .editorial_exports import write_snapshot
from .images import inspect, MAX_BYTES
from .state import Conflict, canonical, now, text
from .verification import _build

KEY = 'screenshot-selection.v1'
FIELDS = ('caption', 'alt_text', 'spoiler', 'build_label', 'capture_kind', 'capture_date')
KINDS = ('unknown', 'reported_emulator', 'reported_hardware', 'static_preview', 'synthetic', 'registered_runtime')


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _digest(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Expected an image or report SHA-256')
    return value


def _bytes(path, limit):
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('Evidence exceeds limit')
    return raw


def _load(db):
    row = db.execute('SELECT value FROM metadata WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else dict(schema_version=1, revision=0, items=[])


def _item(board, key):
    for item in board['items']:
        if item['id'] == key:
            return item
    raise KeyError('Unknown screenshot selection')


def _expect(actual, expected):
    if type(expected) is not int or actual != expected:
        raise Conflict('Screenshot selection changed. Reload and compare before retrying.')


def _content(data):
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ValueError('Supply exactly the documented screenshot metadata fields')
    content = {}
    for field, limit in [('caption',1000),('alt_text',500),('spoiler',20),
                         ('build_label',160),('capture_kind',30),('capture_date',10)]:
        value = text(data[field], field, limit)
        if any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('Unsupported control characters')
        content[field] = value
    if not content['caption'].strip() or not content['alt_text'].strip():
        raise ValueError('Caption and accessible description required')
    if content['spoiler'] not in ('unknown','none','spoilers') or content['capture_kind'] not in KINDS:
        raise ValueError('Unknown spoiler or capture classification')
    if content['capture_date'] and date.fromisoformat(content['capture_date']).isoformat() != content['capture_date']:
        raise ValueError('Use an ISO capture date or leave it unknown')
    return content


def _context(store, db, digest, runtime_report='', runtime_capture=''):
    _digest(digest)
    text(runtime_report,'runtime report',64); text(runtime_capture,'runtime capture',80)
    if runtime_capture and not runtime_report:
        raise ValueError('A capture occurrence requires its report')
    row = db.execute('SELECT * FROM attachments WHERE digest=?', (digest,)).fetchone()
    if not row:
        raise KeyError('Unknown registered screenshot')
    revision = db.execute('SELECT max(revision) FROM attachment_history WHERE digest=?', (digest,)).fetchone()[0]
    attachment = store._attachment_row(row, revision)
    raw = _bytes(confined(store.directory, 'evidence/' + digest), MAX_BYTES)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Stored image changed')
    image = dict(inspect(raw), sha256=digest)
    if image['mime'] != row['mime']:
        raise ValueError('Stored image type changed')
    binding = dict(digest=digest, attachment_revision=revision, build=None,
                   runtime_report=runtime_report, runtime_capture=runtime_capture)
    choices = []
    build = None
    if attachment['build_id']:
        row = db.execute('SELECT * FROM builds WHERE id=?', (attachment['build_id'],)).fetchone()
        if not row:
            raise ValueError('Screenshot names a missing build; correct its associations first')
        build = json.loads(row['payload'])
        binding['build'] = dict(id=row['id'], revision=row['revision'], report_sha256=_hash(build))
        choices = [dict(report=r['report_sha256'],capture=c['id'])
                   for r in build.get('validation',{}).get('runtime',[])
                   for c in r.get('captures',[]) if c.get('digest') == digest]
    capture = dict(basis='reported', runtime_status=None, frame=None)
    if runtime_report:
        _digest(runtime_report)
        matches = [r for r in (build or {}).get('validation',{}).get('runtime',[])
                   if r.get('report_sha256') == runtime_report]
        if len(matches) != 1 or not any(c['report'] == runtime_report for c in choices):
            raise ValueError('Choose a registered report containing this exact image')
        run = matches[0]
        report_path = store.context.output.check(run['report'])
        report_bytes = _bytes(report_path, 4*1024*1024)
        if hashlib.sha256(report_bytes).hexdigest() != runtime_report:
            raise ValueError('Runtime report changed')
        actual = json.loads(report_bytes)
        for key in ('snapshot','rom_sha256','records','scenario_sha256','configuration_sha256',
                    'level','status','assertions','emulator'):
            if actual.get(key) != run.get(key):
                raise ValueError('Registered runtime provenance differs')
        _, artifacts, records = _build(store, db, attachment['build_id'])
        if (actual['build_id'] != attachment['build_id'] or actual['snapshot'] != artifacts['snapshot'] or
                actual['rom_sha256'] != artifacts['artifacts'].get('rom') or
                any(records.get(k) != v for k,v in actual['records'].items()) or
                _hash(actual['emulator']) != actual['configuration_sha256']):
            raise ValueError('Runtime build, snapshot or configuration differs')
        scenario = json.loads(_bytes(confined(report_path.parent,'scenario.json'), 4*1024*1024))
        if _hash(scenario) != actual['scenario_sha256']:
            raise ValueError('Runtime scenario changed')
        captures = [c for c in actual['captures'] if c['sha256'] == digest and (not runtime_capture or c['id'] == runtime_capture)]
        registered = [c for c in run['captures'] if c.get('digest') == digest and (not runtime_capture or c['id'] == runtime_capture)]
        # A repeated identical frame is legitimate; require an unambiguous
        # registered capture identity rather than guessing one occurrence.
        if len(captures) != 1 or len(registered) != 1:
            raise ValueError('Capture occurrence is ambiguous')
        c = captures[0]
        if {k:v for k,v in registered[0].items() if k != 'digest'} != c:
            raise ValueError('Capture provenance differs')
        if (type(c['frame']) is not int or c['frame'] < 0 or
                (c['width'],c['height']) != (image['width'],image['height']) or
                _bytes(confined(report_path.parent,c['file']),MAX_BYTES) != raw):
            raise ValueError('Runtime capture differs')
        kind = {'actual_emulator':'registered_runtime','synthetic':'synthetic'}.get(actual['emulator'].get('kind'))
        level = {'registered_runtime':'automated_runtime','synthetic':'synthetic'}.get(kind)
        if not kind or actual['level'] != level or actual['status'] not in ('passed','failed'):
            raise ValueError('Runtime kind or status differs')
        if actual['status'] == 'passed' and (not actual['assertions'] or not all(c.get('passed') is True for c in actual['assertions'])):
            raise ValueError('Passing report lacks passing checks')
        binding['runtime_artifacts'] = artifacts
        capture = dict(basis='registered_run', kind=kind, runtime_status=actual['status'], frame=c['frame'])
    return dict(token=_hash(binding), binding=binding, image=image, capture=capture,
                build_association=attachment['association'] if build else 'unlinked',
                runtime_choices=choices)


def context(store, digest, runtime_report='', runtime_capture=''):
    with store.connection() as db, store.transaction(db, write=False):
        return _context(store, db, digest, runtime_report, runtime_capture)


def _fresh(store, db, item):
    source = item['source']
    current = _context(store, db, source['digest'], source['runtime_report'], source['runtime_capture'])
    if current['token'] != source['token']:
        raise Conflict('Screenshot provenance changed. Save and review a refreshed draft.')
    return current


def _save(store, db, board, item, action, actor):
    item['revision'] += 1
    item['updated_at'] = now()
    board['revision'] += 1
    db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (KEY,canonical(board)))
    store._event(db,'screenshot-selection.'+action,dict(board_revision=board['revision'],item=item,actor=text(actor,'actor',200)))
    return dict(item,board_revision=board['revision'])


def read(store):
    with store.connection() as db, store.transaction(db, write=False):
        board = _load(db)
        for item in board['items']:
            try:
                _fresh(store,db,item)
                item['stale'] = False
            except (ValueError,KeyError,OSError,TypeError):
                item['stale'] = True
        return board


def put(store, digest, context_token, data, expected, key=None, runtime_report='', runtime_capture='', private_notes='', actor='agent'):
    content = _content(data)
    private_notes = text(private_notes,'private notes',8000)
    with store.connection() as db, store.transaction(db):
        source = _context(store,db,digest,runtime_report,runtime_capture)
        if source['token'] != context_token:
            raise Conflict('Screenshot context changed. Reload before saving.')
        if bool(source['binding']['build']) != bool(content['build_label'].strip()):
            raise ValueError('A linked build needs a reviewed label; unlinked images must leave it empty')
        if runtime_report:
            if content['capture_kind'] != source['capture']['kind']:
                raise ValueError('Capture kind must match the registered report')
        elif content['capture_kind'] == 'registered_runtime':
            raise ValueError('Registered runtime provenance requires a checked report')
        board = _load(db)
        if key is None:
            _expect(0,expected)
            if len(board['items']) >= 500:
                raise ValueError('Screenshot selection limit reached')
            item = dict(id='capture-'+uuid.uuid4().hex,revision=0)
            board['items'].append(item)
        else:
            item = _item(board,key)
            _expect(item['revision'],expected)
        item.update(content=content,source=dict(digest=digest,runtime_report=runtime_report,runtime_capture=runtime_capture,token=source['token']),
                    private_notes=private_notes,review=None,selected=False)
        item['review_token'] = _hash(dict(content=content,source=item['source']))
        return _save(store,db,board,item,'saved',actor)


def review(store, key, expected, review_token, actor='agent'):
    with store.connection() as db, store.transaction(db):
        board = _load(db); item = _item(board,key)
        _expect(item['revision'],expected); _fresh(store,db,item)
        if review_token != item['review_token']:
            raise Conflict('Review does not match the displayed screenshot and metadata')
        item['review'] = dict(token=review_token,actor=text(actor,'actor',200),reviewed_at=now())
        return _save(store,db,board,item,'reviewed',actor)


def select(store, key, expected, selected, actor='agent'):
    if type(selected) is not bool:
        raise ValueError('Selection must be a boolean')
    with store.connection() as db, store.transaction(db):
        board = _load(db); item = _item(board,key)
        _expect(item['revision'],expected)
        if selected:
            _fresh(store,db,item)
            if not item['review'] or item['review']['token'] != item['review_token']:
                raise Conflict('Review the exact screenshot and metadata first')
        item['selected'] = selected
        return _save(store,db,board,item,'selected',actor)


def _preview(store, db, board):
    items = []
    for item in board['items']:
        if not item['selected']:
            continue
        try:
            current = _fresh(store,db,item)
        except (ValueError,KeyError,OSError,TypeError) as error:
            raise Conflict('A selected screenshot has stale or unavailable provenance. Refresh its draft or remove it from selection.') from error
        if (not item['review'] or item['review']['token'] != item['review_token'] or
                _hash(dict(content=item['content'],source=item['source'])) != item['review_token']):
            raise Conflict('A selected screenshot needs a fresh review')
        content = _content(item['content'])
        result = dict(id=item['id'],revision=item['revision'],caption=content['caption'],alt_text=content['alt_text'],
                      spoiler=content['spoiler'],image=current['image'],
                      build=dict(label=content['build_label'],association=current['build_association']),
                      capture=dict(current['capture'],kind=content['capture_kind'],date=content['capture_date'] or None))
        result['metadata_sha256'] = _hash(result)
        items.append(result)
    return dict(schema_version=1,report_type='screenshot-selection',selection_revision=board['revision'],
                publication_approved=False,release_approved=False,images_included=False,items=sorted(items,key=lambda i:i['id']))


def preview(store):
    with store.connection() as db, store.transaction(db, write=False):
        return _preview(store,db,_load(db))


def export(store, expected, destination, actor='agent'):
    actor = text(actor,'actor',200)
    with store.connection() as db, store.transaction(db):
        board = _load(db); _expect(board['revision'],expected)
        payload = _preview(store,db,board)
        result = dict(write_snapshot(store.context.output,destination,payload),
                      selection_revision=board['revision'],count=len(payload['items']))
        store._event(db,'screenshot-selection.exported',dict(result,actor=actor))
        return result


def history(store, after=0, limit=100):
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Invalid history page')
    with store.connection() as db:
        return [dict(seq=r['seq'],kind=r['kind'],created=r['created'],payload=json.loads(r['payload'])) for r in db.execute(
            "SELECT * FROM events WHERE seq>? AND kind LIKE 'screenshot-selection.%' ORDER BY seq LIMIT ?",(after,limit))]

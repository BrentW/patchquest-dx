"""Explicit editorial summaries, revision-bound review and private exports.

No log summarization, translation writes, publication or release authorization.
"""
from datetime import date
import hashlib
import json
import uuid

from .state import Conflict, canonical, now, text
from .editorial_exports import write_snapshot

KEY = 'milestones.v1'
CATEGORIES = ('progress', 'translation', 'review', 'testing', 'tooling')
BASES = ('not_verified', 'static', 'automated_runtime', 'reported_human', 'hardware')
FIELDS = ('date', 'title', 'summary', 'category', 'verification_basis', 'limitations')


def _load(db):
    row = db.execute('SELECT value FROM metadata WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else dict(schema_version=1, revision=0, items=[])


def _expect(actual, expected):
    if type(expected) is not int or actual != expected:
        raise Conflict('Milestones changed. Reload and compare before retrying.')


def _item(board, key):
    for item in board['items']:
        if item['id'] == key:
            return item
    raise KeyError('Unknown milestone')


def _content(data):
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ValueError('Supply exactly the documented milestone content fields')
    result = {}
    for field, limit in [('date', 10), ('title', 160), ('summary', 2000),
                         ('category', 30), ('verification_basis', 30), ('limitations', 1000)]:
        value = text(data[field], field, limit)
        if any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('Unsupported control characters')
        result[field] = value
    if not result['title'].strip() or not result['summary'].strip():
        raise ValueError('Title and summary must not be blank')
    if date.fromisoformat(result['date']).isoformat() != result['date']:
        raise ValueError('Use an ISO calendar date')
    if result['category'] not in CATEGORIES or result['verification_basis'] not in BASES:
        raise ValueError('Unknown category or verification basis')
    return result


def _hash(data):
    return hashlib.sha256(canonical(data).encode('utf8')).hexdigest()


def _save(store, db, board, item, kind, actor):
    item['revision'] += 1
    item['updated_at'] = now()
    board['revision'] += 1
    db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
               (KEY, canonical(board)))
    store._event(db, 'milestone.' + kind, dict(board_revision=board['revision'],
                 actor=text(actor, 'actor', 200), item=item))
    return dict(item, board_revision=board['revision'])


def read(store):
    """Private editorial board, including draft content and private notes."""
    with store.connection() as db:
        return _load(db)


def put(store, data, expected, key=None, private_notes='', actor='agent'):
    content = _content(data)
    private_notes = text(private_notes, 'private notes', 8000)
    with store.connection() as db, store.transaction(db):
        board = _load(db)
        if key is None:
            _expect(0, expected)
            if len(board['items']) >= 1000:
                raise ValueError('Milestone limit reached')
            item = dict(id='milestone-' + uuid.uuid4().hex, revision=0)
            board['items'].append(item)
        else:
            item = _item(board, key)
            _expect(item['revision'], expected)
        # Even a notes-only edit requires a fresh review. Selection never floats
        # to a changed draft and the previous revision remains in the journal.
        item.update(content=content, content_sha256=_hash(content), private_notes=private_notes,
                    review=None, selected=False)
        return _save(store, db, board, item, 'saved', actor)


def review(store, key, expected, content_sha256, actor='agent'):
    with store.connection() as db, store.transaction(db):
        board = _load(db)
        item = _item(board, key)
        _expect(item['revision'], expected)
        if content_sha256 != item['content_sha256']:
            raise Conflict('Review does not match the displayed milestone content.')
        item['review'] = dict(content_sha256=content_sha256, draft_revision=item['revision'],
                              actor=text(actor, 'actor', 200), reviewed_at=now())
        return _save(store, db, board, item, 'reviewed', actor)


def select(store, key, expected, selected, actor='agent'):
    if type(selected) is not bool:
        raise ValueError('Selection must be a boolean')
    with store.connection() as db, store.transaction(db):
        board = _load(db)
        item = _item(board, key)
        _expect(item['revision'], expected)
        if selected and (not item['review'] or item['review']['content_sha256'] != item['content_sha256']):
            raise Conflict('Review this exact content before selecting it.')
        item['selected'] = selected
        return _save(store, db, board, item, 'selected', actor)


def _preview(board):
    items = []
    for item in board['items']:
        if not item['selected']:
            continue
        content = _content(item['content'])
        digest = _hash(content)
        if not item['review'] or item['review']['content_sha256'] != digest or item['content_sha256'] != digest:
            raise Conflict('A selected milestone needs a fresh review.')
        # Construct every output field. Never serialize private rows wholesale.
        items.append(dict(id=item['id'], revision=item['revision'], content_sha256=digest,
                          **{field: content[field] for field in FIELDS}))
    return dict(schema_version=1, report_type='milestone-updates',
                selection_revision=board['revision'], publication_approved=False,
                release_approved=False, items=sorted(items, key=lambda i: (i['date'], i['id']), reverse=True))


def preview(store):
    """Exact export payload; no private project identifier or review provenance."""
    with store.connection() as db:
        return _preview(_load(db))


def export(store, expected, destination, actor='agent'):
    """Create a complete immutable file under the explicit project output policy.

    The board lock prevents concurrent edits from changing the reviewed selection
    during export. A same-directory hard link publishes the finished file without
    replacing any existing file. Unsupported filesystems fail closed.
    """
    actor = text(actor, 'actor', 200)
    with store.connection() as db, store.transaction(db):
        board = _load(db)
        _expect(board['revision'], expected)
        payload = _preview(board)
        result = dict(write_snapshot(store.context.output, destination, payload),
                      selection_revision=board['revision'], count=len(payload['items']))
        store._event(db, 'milestone.exported', dict(result, actor=text(actor, 'actor', 200)))
        return result


def history(store, after=0, limit=100):
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Invalid history page')
    with store.connection() as db:
        rows = db.execute("SELECT * FROM events WHERE seq>? AND kind LIKE 'milestone.%' ORDER BY seq LIMIT ?",
                          (after, limit)).fetchall()
    return [dict(seq=r['seq'], kind=r['kind'], created=r['created'], payload=json.loads(r['payload'])) for r in rows]

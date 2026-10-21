"""Private release preparation; exact-file patch checks, never publication.

Original inputs, generated artifacts and translation state remain read-only.
Only an explicitly reviewed checksum manifest can be exported, without binaries.
"""
import hashlib
import json
import re
import uuid
import zlib

from .core.context import ProjectContext
from .editorial_exports import write_snapshot
from .patches import bps
from .state import Conflict, canonical, identity, now, text
from .verification import _build

KEY = 'release-candidates.v1'
MAX_BYTES = 64 * 1024 * 1024
FIELDS = ('release_id', 'title', 'version', 'source_label', 'patch_filename',
          'output_filename', 'compatibility', 'limitations')


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _content(data):
    if not isinstance(data, dict) or set(data) != set(FIELDS):
        raise ValueError('Supply exactly the documented release metadata fields')
    result = {}
    for k in FIELDS:
        value = text(data[k], k, 4000 if k in ('compatibility', 'limitations') else 160)
        if not value.strip() or any(ord(c) < 32 and c not in '\n\t' for c in value):
            raise ValueError('Release metadata must be nonblank plain text')
        result[k] = value
    if not re.fullmatch('[a-z0-9][a-z0-9_-]{0,79}', result['release_id']):
        raise ValueError('Use a stable lowercase release ID')
    for k in ('patch_filename', 'output_filename'):
        name = result[k]
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}\.[a-z0-9]{1,5}', name):
            raise ValueError('Use a portable basename without directories')
        if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
            raise ValueError('Reserved filename')
    if not result['patch_filename'].endswith('.bps'):
        raise ValueError('Only BPS patches are supported')
    if result['output_filename'].split('.')[-1] not in ('sfc','smc','nes','fds','d88','rom','bin'):
        raise ValueError('Unsupported output image extension')
    return result


def _load(db):
    row = db.execute('SELECT value FROM metadata WHERE key=?', (KEY,)).fetchone()
    return json.loads(row[0]) if row else dict(revision=0, items=[])


def _item(board, key):
    return next((i for i in board['items'] if i['id'] == key), None) or _missing()


def _missing():
    raise KeyError('Unknown release candidate')


def _expect(actual, expected):
    if type(expected) is not int or actual != expected:
        raise Conflict('Release candidate changed; reload and compare')


def _save(store, db, board, item, action, actor):
    actor = text(actor, 'actor', 200)
    item['revision'] += 1
    item['updated_at'] = now()
    board['revision'] += 1
    db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (KEY, canonical(board)))
    store._event(db, 'release.' + action, dict(actor=actor, item=item))
    return item


def read(store):
    # Browsing drafts does not open original inputs or artifact files.
    with store.connection() as db:
        return _load(db)


def put(store, data, build_id, patch_artifact, output_artifact, expected, key=None,
        repeat_build_id='', private_notes='', actor='agent'):
    content = _content(data)
    selection = dict(build_id=identity(build_id), patch_artifact=identity(patch_artifact),
                     output_artifact=identity(output_artifact), repeat_build_id=repeat_build_id)
    if not isinstance(repeat_build_id, str):
        raise ValueError('Invalid repeat build')
    if repeat_build_id:
        identity(repeat_build_id)
    if repeat_build_id == build_id or patch_artifact == output_artifact:
        raise ValueError('Use distinct builds and distinct artifact roles')
    private_notes = text(private_notes, 'private notes', 8000)
    with store.connection() as db, store.transaction(db):
        board = _load(db)
        if key is None:
            _expect(0, expected)
            if len(board['items']) >= 100:
                raise ValueError('Release candidate limit reached')
            item = dict(id='release-' + uuid.uuid4().hex, revision=0)
            board['items'].append(item)
        else:
            item = _item(board, key)
            _expect(item['revision'], expected)
        for build in (build_id, repeat_build_id):
            if build and not db.execute('SELECT 1 FROM builds WHERE id=?', (build,)).fetchone():
                raise KeyError('Unknown selected build')
        item.update(content=content, selection=selection, private_notes=private_notes,
                    validation=None, review=None)
        return _save(store, db, board, item, 'saved', actor)


def _bytes(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Selected file exceeds the 64 MiB preparation limit')
    with path.open('rb') as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError('Selected file exceeds the 64 MiB preparation limit')
    return data


def _fingerprint(data):
    return dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), crc32=f'{zlib.crc32(data):08x}')


def _patch_check(source, target, patch):
    """Bound the stream before using the platform's strict subset decoder."""
    if len(patch) < 19 or patch[:4] != b'BPS1':
        raise ValueError('Expected a BPS1 patch')
    pos = 4; limit = len(patch) - 12

    def number():
        nonlocal pos
        value, shift = 0, 1
        for _ in range(10):
            if pos >= limit:
                raise ValueError('Truncated BPS integer')
            b = patch[pos]; pos += 1; value += (b & 127) * shift
            if b & 128:
                return value
            shift <<= 7; value += shift
        raise ValueError('Oversized BPS integer')

    source_size, target_size, metadata_size = number(), number(), number()
    if source_size != len(source) or target_size != len(target):
        raise ValueError('Patch source/output sizes do not match selected exact files')
    if pos + metadata_size > limit:
        raise ValueError('Truncated BPS metadata')
    pos += metadata_size; produced = 0; literals = 0
    while produced < target_size:
        command = number(); length = (command >> 2) + 1; action = command & 3
        if produced + length > target_size:
            raise ValueError('BPS target overflow')
        if action == 1:
            literals += length; pos += length
            if pos > limit:
                raise ValueError('Truncated BPS literals')
        elif action != 0:
            raise ValueError('Only SourceRead/TargetRead BPS actions are supported')
        produced += length
    if pos != limit or bps.apply(source, patch) != target:
        raise ValueError('Patch does not reconstruct the exact selected output')
    return dict(reconstruction='passed', decoder='bps1-source-read-target-read',
                metadata_bytes=metadata_size, literal_bytes=literals)


def _context(store, db, item):
    # A long-lived Studio cannot validate against a changed project contract.
    if ProjectContext.load(store.manifest_path) != store.context:
        raise Conflict('Project manifest changed; reopen the project before preparing a release')
    source = _bytes(store.context.source)
    source_hash = _fingerprint(source)
    if source_hash['sha256'] != store.context.manifest['source']['sha256']:
        raise ValueError('Original source does not match the pinned project SHA-256')
    selection = item['selection']

    def selected_build(key):
        build, binding, _ = _build(store, db, key)
        if build['status'] != 'validated':
            raise ValueError('Select a statically validated build')
        snap = json.loads(db.execute('SELECT payload FROM snapshots WHERE digest=?', (build['snapshot'],)).fetchone()[0])
        if snap['source_sha256'] != source_hash['sha256'] or snap['project_id'] != store.context.manifest['project_id']:
            raise ValueError('Build snapshot does not belong to the pinned project source')
        row = db.execute('SELECT revision,payload FROM builds WHERE id=?', (key,)).fetchone()
        binding.update(report_revision=row['revision'], report_sha256=_hash(json.loads(row['payload'])))
        data = {}
        for role in ('patch_artifact', 'output_artifact'):
            name = selection[role]
            if name not in build['artifacts']:
                raise ValueError('Selected artifact is absent from the build')
            data[role] = _bytes(store.context.output.check(build['artifacts'][name]))
            if _fingerprint(data[role])['sha256'] != binding['artifacts'][name]:
                raise Conflict('Artifact changed during validation')
        return binding, data

    binding, artifacts = selected_build(selection['build_id'])
    patch, target = artifacts['patch_artifact'], artifacts['output_artifact']
    checks = _patch_check(source, target, patch)
    repeat = None
    checks['repeat_build'] = 'not_provided'
    if selection['repeat_build_id']:
        repeat, other = selected_build(selection['repeat_build_id'])
        if repeat['snapshot'] != binding['snapshot'] or other != artifacts:
            raise ValueError('Repeat build must have the same snapshot and exact patch/output bytes')
        checks['repeat_build'] = 'matched_registered_artifacts'
    checks.update(runtime='not_assessed', rights='not_assessed')
    content = _content(item['content'])
    manifest = dict(schema_version=1, report_type='release-manifest', publication_approved=False,
                    release_approved=False, **content, input_policy='exact_file_no_normalization',
                    source=source_hash, output=_fingerprint(target), patch=dict(format='BPS1', **_fingerprint(patch)),
                    checks=checks)
    private_binding = dict(manifest_sha256=_hash(store.context.manifest), source=source_hash,
                           selection=selection, build=binding, repeat_build=repeat)
    return dict(manifest=manifest, binding=private_binding, token=_hash(dict(manifest=manifest, binding=private_binding)))


def validate(store, key, expected, actor='agent'):
    with store.connection() as db, store.transaction(db):
        board = _load(db); item = _item(board, key); _expect(item['revision'], expected)
        ctx = _context(store, db, item)
        item.update(validation=dict(ctx, validated_at=now()), review=None)
        return _save(store, db, board, item, 'validated', actor)


def _preview(store, db, item):
    if not item['validation']:
        raise Conflict('Validate this candidate before reviewing or exporting')
    ctx = _context(store, db, item)
    if ctx['token'] != item['validation']['token']:
        raise Conflict('Candidate inputs or artifacts changed; validate and review again')
    return dict(manifest=ctx['manifest'], token=ctx['token'],
                reviewed=bool(item['review'] and item['review']['token'] == ctx['token']))


def preview(store, key):
    with store.connection() as db, store.transaction(db, write=False):
        return _preview(store, db, _item(_load(db), key))


def review(store, key, expected, validation_token, actor='agent'):
    with store.connection() as db, store.transaction(db):
        board = _load(db); item = _item(board, key); _expect(item['revision'], expected)
        ctx = _preview(store, db, item)
        if ctx['token'] != validation_token:
            raise Conflict('Review must match the exact inspected manifest')
        item['review'] = dict(token=validation_token, actor=text(actor, 'actor', 200), reviewed_at=now())
        return _save(store, db, board, item, 'metadata-reviewed', actor)


def export(store, key, expected, validation_token, destination, actor='agent'):
    actor = text(actor, 'actor', 200)
    with store.connection() as db, store.transaction(db):
        item = _item(_load(db), key); _expect(item['revision'], expected)
        ctx = _preview(store, db, item)
        if not ctx['reviewed'] or ctx['token'] != validation_token:
            raise Conflict('Inspect and review the current manifest before exporting')
        result = write_snapshot(store.context.output, destination, ctx['manifest'])
        store._event(db, 'release.exported', dict(key=key, revision=item['revision'], actor=actor, **result))
        return result


def history(store, after=0, limit=100):
    if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError('Invalid history page')
    with store.connection() as db:
        return [dict(seq=r['seq'], kind=r['kind'], created=r['created'], payload=json.loads(r['payload'])) for r in db.execute(
            "SELECT * FROM events WHERE kind LIKE 'release.%' AND seq>? ORDER BY seq LIMIT ?", (after, limit))]

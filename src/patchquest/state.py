"""Transactional private translation records. No provider SDK or game imports."""
from contextlib import contextmanager
from datetime import datetime, timezone
from difflib import SequenceMatcher
import hashlib
import json
from pathlib import Path
import sqlite3

from .core.context import ProjectContext, OutputPolicy, confined

STAGES = ('inserted', 'automated', 'emulator', 'hardware')
KINDS = ('translation', 'glossary')


class Conflict(ValueError):
    """The caller must reload before retrying a stale write."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def text(value, name, limit=100000):
    if not isinstance(value, str) or len(value) > limit or '\x00' in value:
        raise ValueError('Invalid ' + name)
    return value


def identity(value):
    text(value, 'ID', 200)
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError('Invalid ID')
    return value


def record_data(data):
    """Controls/context are opaque data. Private validators own game semantics."""
    if not isinstance(data, dict):
        raise ValueError('Record must be an object')
    allowed = {'id', 'kind', 'source', 'target', 'speaker', 'scene', 'category',
               'context', 'controls', 'uncertainty', 'decoded', 'source_ref', 'build_binding'}
    if set(data) - allowed:
        raise ValueError('Unsupported record fields')
    result = {'id': identity(data.get('id')), 'kind': data.get('kind', 'translation')}
    if result['kind'] not in KINDS:
        raise ValueError('Unsupported record kind')
    for key in ('source', 'target', 'speaker', 'scene', 'category', 'uncertainty'):
        result[key] = text(data.get(key, ''), key)
    for key in ('context', 'source_ref', 'build_binding'):
        value = data.get(key, {})
        if not isinstance(value, dict):
            raise ValueError(key + ' must be an object')
        result[key] = value
    result['controls'] = data.get('controls', [])
    if not isinstance(result['controls'], list):
        raise ValueError('controls must be a list')
    result['decoded'] = data.get('decoded', False)
    if type(result['decoded']) is not bool:
        raise ValueError('decoded must be a boolean')
    if len(canonical(result).encode('utf-8')) > 250000:
        raise ValueError('Record too large')
    return result


SCHEMA = """
CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, human INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS revisions(
 id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 role TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL,
 PRIMARY KEY(id, revision));
CREATE TABLE IF NOT EXISTS memory(
 id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(id, revision));
CREATE TABLE IF NOT EXISTS proposals(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, base INTEGER NOT NULL,
 payload TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(
 seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, revision INTEGER NOT NULL,
 stage TEXT NOT NULL, passed INTEGER NOT NULL, reference TEXT NOT NULL,
 build_id TEXT NOT NULL, created TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS evidence_record ON evidence(id, revision, stage, seq);
CREATE TABLE IF NOT EXISTS issues(
 id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS issue_history(
 id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, actor TEXT NOT NULL, created TEXT NOT NULL,
 PRIMARY KEY(id, revision));
CREATE TABLE IF NOT EXISTS snapshots(digest TEXT PRIMARY KEY, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS builds(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS build_history(
 id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL,
 PRIMARY KEY(id, revision));
CREATE TABLE IF NOT EXISTS attachments(digest TEXT PRIMARY KEY, mime TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS build_worker(slot INTEGER PRIMARY KEY, owner TEXT NOT NULL, label TEXT NOT NULL, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS build_jobs(id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, status TEXT NOT NULL, owner TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS attachment_history(digest TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL, PRIMARY KEY(digest,revision));
CREATE TABLE IF NOT EXISTS agent_sessions(id TEXT PRIMARY KEY, payload TEXT NOT NULL, status TEXT NOT NULL, expires REAL NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_items(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL, owner TEXT NOT NULL, fence INTEGER NOT NULL, expires REAL NOT NULL, created TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_history(seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL, payload TEXT NOT NULL, created TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work_managed(record_id TEXT PRIMARY KEY);
"""


class Store:
    """One explicit project's local SQLite database; one connection per operation.

    A local filesystem is required (WAL is not for network shares). Callers with
    OS write access are trusted; human/agent roles are provenance, not OS auth.
    """

    def __init__(self, manifest):
        self.manifest_path = Path(manifest).resolve()
        self.context = ProjectContext.load(self.manifest_path)
        self.directory = confined(self.context.root, '.patchquest')
        protected = (self.context.source, *self.context.output.inputs)
        if any(p == self.directory or p.is_relative_to(self.directory)
               or self.directory.is_relative_to(p) for p in protected):
            raise ValueError('State area overlaps a protected resource')
        if self.directory.is_relative_to(self.context.output.root) or self.context.output.root.is_relative_to(self.directory):
            raise ValueError('State and build outputs must be separate')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = confined(self.directory, 'state.sqlite3')
        if self.path.exists() and self.path.stat().st_nlink > 1:
            raise ValueError('State database must not be a hard link')
        with self.connection() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1, 2, 3):
                raise ValueError('Unsupported state schema')
            if version == 0 and db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError('Refusing an unrelated database')
            db.executescript(SCHEMA)
            db.execute('PRAGMA user_version=3')
            db.execute('INSERT OR IGNORE INTO attachment_history SELECT digest,1,payload,? FROM attachments',(now(),))
            with self.transaction(db):
                expected = canonical({'project_id': self.context.manifest['project_id'],
                                      'source_sha256': self.context.manifest['source']['sha256']})
                row = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
                if row and row[0] != expected:
                    raise ValueError('State belongs to a different project/source')
                db.execute("INSERT OR IGNORE INTO metadata VALUES('identity',?)", (expected,))

    @contextmanager
    def connection(self):
        # Recheck symlinks when reopening; not a hostile-process filesystem sandbox.
        if confined(self.context.root, '.patchquest/state.sqlite3') != self.path:
            raise ValueError('State path changed')
        db = sqlite3.connect(self.path, timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self, db, write=True):
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        try:
            yield
        except BaseException:
            db.rollback()
            raise
        else:
            db.commit()

    def _event(self, db, kind, payload):
        db.execute('INSERT INTO events(kind,payload,created) VALUES(?,?,?)', (kind, canonical(payload), now()))

    def _get(self, db, key):
        row = db.execute('SELECT v.*,r.human FROM records r JOIN revisions v ON r.id=v.id AND r.revision=v.revision WHERE r.id=?', (key,)).fetchone()
        if not row:
            raise KeyError(key)
        return dict(json.loads(row['payload']), revision=row['revision'], human_corrected=bool(row['human']),
                    provenance={'role': row['role'], 'actor': row['actor'], 'reason': row['reason'], 'created': row['created']})

    def get(self, key):
        with self.connection() as db:
            return self._get(db, key)

    @staticmethod
    def status(row):
        if not row['target']:
            return 'untranslated'
        if row['human_corrected']:
            return 'corrected'
        return 'uncertain' if row['uncertainty'] else 'translated'

    def _all(self, db):
        rows = db.execute('SELECT v.*,r.human FROM records r JOIN revisions v ON r.id=v.id AND r.revision=v.revision ORDER BY r.id').fetchall()
        return [dict(json.loads(r['payload']), revision=r['revision'], human_corrected=bool(r['human'])) for r in rows]

    def list(self, query='', kind='translation', scene='', speaker='', category='', status='', offset=0, limit=50):
        if kind not in KINDS or status not in ('', 'untranslated', 'corrected', 'uncertain', 'translated'):
            raise ValueError('Invalid filter')
        if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Invalid page')
        q = text(query, 'query', 1000).casefold()
        with self.connection() as db:
            rows = [r for r in self._all(db) if r['kind'] == kind]
        facets = {k: sorted({r[k] for r in rows if r[k]}) for k in ('scene', 'speaker', 'category')}
        rows = [r for r in rows if (not q or q in '\n'.join(r[k] for k in ('id', 'source', 'target', 'speaker', 'scene')).casefold())
                and (not scene or r['scene'] == scene) and (not speaker or r['speaker'] == speaker)
                and (not category or r['category'] == category) and (not status or self.status(r) == status)]
        return {'total': len(rows), 'items': rows[offset:offset+limit], 'facets': facets}

    def _put(self, db, data, expected, role, actor, reason, _work=False):
        data = record_data(data)
        if role not in ('human', 'agent', 'import') or type(expected) is not int or expected < 0:
            raise ValueError('Invalid role or expected revision')
        text(actor, 'actor', 200); text(reason, 'reason', 4000)
        if role != 'human' and not _work and db.execute('SELECT 1 FROM work_managed WHERE record_id=?', (data['id'],)).fetchone():
            raise Conflict('This record uses coordinated work; claim it and publish with the current fence')
        head = db.execute('SELECT * FROM records WHERE id=?', (data['id'],)).fetchone()
        current = head['revision'] if head else 0
        if current != expected:
            raise Conflict('Record changed; reload and reconcile')
        payload = canonical(data)
        if head:
            old = db.execute('SELECT payload FROM revisions WHERE id=? AND revision=?', (data['id'], current)).fetchone()[0]
            if json.loads(old)['kind'] != data['kind']:
                raise ValueError('Record kind is immutable')
            if old == payload and (role != 'human' or head['human']):
                return {'outcome': 'unchanged', 'record': self._get(db, data['id'])}
            if head['human'] and role != 'human':
                db.execute('INSERT INTO proposals(id,base,payload,actor,reason,created) VALUES(?,?,?,?,?,?)',
                           (data['id'], current, payload, actor, reason, now()))
                self._event(db, 'proposal', {'id': data['id'], 'base': current, 'actor': actor})
                return {'outcome': 'proposed', 'record': self._get(db, data['id'])}
        revision = current + 1
        human = role == 'human' or bool(head and head['human'])
        db.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?,?)', (data['id'], revision, payload, role, actor, reason, now()))
        db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,human=excluded.human', (data['id'], revision, int(human)))
        db.execute('INSERT INTO memory VALUES(?,?,?)', (data['id'], revision, payload))
        self._event(db, 'record', {'id': data['id'], 'revision': revision, 'actor': actor, 'role': role})
        return {'outcome': 'saved', 'record': self._get(db, data['id'])}

    def put(self, data, expected, role='agent', actor='', reason=''):
        with self.connection() as db, self.transaction(db):
            return self._put(db, data, expected, role, actor, reason)

    def import_records(self, records, actor='migration'):
        """All-or-nothing, idempotent first import. Never overwrite a migrated edit."""
        if not isinstance(records, list) or len(records) > 100000:
            raise ValueError('Expected a bounded list')
        parsed = [record_data(r) for r in records]
        if len({r['id'] for r in parsed}) != len(parsed):
            raise ValueError('Duplicate import ID')
        count = 0
        with self.connection() as db, self.transaction(db):
            for r in parsed:
                old = db.execute('SELECT payload FROM revisions WHERE id=? AND revision=1', (r['id'],)).fetchone()
                if old:
                    if old[0] != canonical(r):
                        raise Conflict('Import differs from original migration; reconcile explicitly')
                    continue
                self._put(db, r, 0, 'import', actor, 'Lossless legacy import')
                count += 1
        return {'imported': count, 'existing': len(parsed)-count}

    def history(self, key):
        with self.connection() as db:
            self._get(db, key)
            return [dict(r, payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM revisions WHERE id=? ORDER BY revision DESC', (key,))]

    def proposals(self, key):
        with self.connection() as db:
            return [dict(r, payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM proposals WHERE id=? ORDER BY seq DESC', (key,))]

    def restore(self, key, revision, expected, actor=''):
        with self.connection() as db, self.transaction(db):
            row = db.execute('SELECT payload FROM revisions WHERE id=? AND revision=?', (key, revision)).fetchone()
            if not row:
                raise KeyError('Revision not found')
            return self._put(db, json.loads(row[0]), expected, 'human', actor, 'Restore revision '+str(revision))

    def memory(self, key=None, source='', scene='', speaker='', limit=12):
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValueError('Invalid memory limit')
        with self.connection() as db:
            if key:
                active = self._get(db, key)
                source, scene, speaker = active['source'], active['scene'], active['speaker']
            text(source, 'source', 100000)
            result = []
            for row in db.execute('SELECT m.*,r.revision AS head,r.human FROM memory m JOIN records r ON r.id=m.id'):
                p = json.loads(row['payload'])
                if not p['target'] or row['id'] == key:
                    continue
                similarity = SequenceMatcher(None, source[:4000], p['source'][:4000], autojunk=False).ratio()
                term = p['kind'] == 'glossary' and p['source'] and p['source'] in source
                if similarity < .35 and not term:
                    continue
                score = similarity + .2*bool(scene and scene == p['scene']) + .2*bool(speaker and speaker == p['speaker']) + .5*bool(term)
                result.append({'id': row['id'], 'revision': row['revision'], 'source': p['source'], 'target': p['target'],
                               'kind': p['kind'], 'context': p['context'], 'scene': p['scene'], 'speaker': p['speaker'],
                               'controls': p['controls'], 'uncertainty': p['uncertainty'], 'score': round(score, 4),
                               'current': row['revision'] == row['head'],
                               'human_corrected': bool(row['human'] and row['revision'] == row['head'])})
            return sorted(result, key=lambda r: (-r['current'], -r['human_corrected'], -r['score'], r['id'], -r['revision']))[:limit]

    def rebuild_memory(self):
        with self.connection() as db, self.transaction(db):
            db.execute('DELETE FROM memory')
            db.execute('INSERT INTO memory SELECT id,revision,payload FROM revisions')
            self._event(db, 'memory_rebuilt', {})

    def evidence(self, key, revision, stage, passed, reference, build_id=''):
        if stage not in STAGES or type(passed) is not bool or not text(reference, 'reference', 4000):
            raise ValueError('Explicit stage, result and evidence are required')
        with self.connection() as db, self.transaction(db):
            if not db.execute('SELECT 1 FROM revisions WHERE id=? AND revision=?', (key, revision)).fetchone():
                raise KeyError('Unknown record revision')
            db.execute('INSERT INTO evidence(id,revision,stage,passed,reference,build_id,created) VALUES(?,?,?,?,?,?,?)',
                       (key, revision, stage, int(passed), reference, text(build_id, 'build_id', 200), now()))
            self._event(db, 'evidence', {'id': key, 'revision': revision, 'stage': stage, 'passed': passed})
        return {'recorded': True}

    def record_evidence(self, key):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM evidence WHERE id=? ORDER BY seq DESC', (key,))]

    def activity(self, message, actor='', status='working'):
        if status not in ('working', 'idle', 'blocked', 'finished'):
            raise ValueError('Invalid activity state')
        with self.connection() as db, self.transaction(db):
            self._event(db, 'activity', {'message': text(message, 'message', 4000), 'actor': text(actor, 'actor', 200), 'status': status})
        return {'recorded': True}

    def events(self, after=0, limit=100):
        if type(after) is not int or after < 0 or type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError('Invalid cursor')
        with self.connection() as db:
            return [dict(r, payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?', (after, limit))]

    def overview(self):
        with self.connection() as db, self.transaction(db, write=False):
            rows = [r for r in self._all(db) if r['kind'] == 'translation']
            counts = {'discovered': len(rows), 'decoded': sum(r['decoded'] for r in rows),
                      'translated': sum(bool(r['target']) for r in rows), 'uncertain': sum(bool(r['uncertainty']) for r in rows),
                      'human_corrected': sum(r['human_corrected'] for r in rows)}
            for stage in STAGES:
                ids={r['id'] for r in rows}
                facts=db.execute('SELECT e.id FROM evidence e JOIN records r ON r.id=e.id AND r.revision=e.revision WHERE e.stage=? AND e.passed=1 AND e.seq=(SELECT max(x.seq) FROM evidence x WHERE x.id=e.id AND x.revision=e.revision AND x.stage=e.stage)',(stage,))
                counts[stage]=sum(r[0] in ids for r in facts)
            active = db.execute("SELECT * FROM events WHERE kind='activity' ORDER BY seq DESC LIMIT 1").fetchone()
            cursor = db.execute('SELECT coalesce(max(seq),0) FROM events').fetchone()[0]
            issues = [json.loads(r[0]) for r in db.execute('SELECT payload FROM issues')]
            return {'project_id': self.context.manifest['project_id'],
                    'title': self.context.manifest.get('data', {}).get('title', self.context.manifest['project_id']),
                    'counts': counts, 'percentages': {k: round(v*100/len(rows),1) if rows else None for k,v in counts.items()},
                    'denominator': 'catalogued translation records, not the whole game',
                    'open_issues': sum(i['status'] != 'closed' for i in issues), 'cursor': cursor,
                    'activity': dict(active, payload=json.loads(active['payload'])) if active else None}

    def put_issue(self, data, expected, actor=''):
        if not isinstance(data, dict) or set(data) - {'id','title','description','category','status','record_ids','scene','build_id','references'}:
            raise ValueError('Invalid issue')
        p = {'id': identity(data.get('id'))}
        for key in ('title','description','category','scene','build_id'):
            p[key] = text(data.get(key,''), key, 20000)
        if not p['title']:
            raise ValueError('Issue needs a title')
        p['status'] = data.get('status','open')
        if p['status'] not in ('open','investigating','resolved','closed'):
            raise ValueError('Invalid issue status')
        for key in ('record_ids','references'):
            p[key] = data.get(key,[])
            if not isinstance(p[key],list) or not all(isinstance(v,str) and len(v)<4000 for v in p[key]):
                raise ValueError('Invalid issue links')
        with self.connection() as db, self.transaction(db):
            for key in p['record_ids']:
                self._get(db,key)
            head=db.execute('SELECT revision FROM issues WHERE id=?',(p['id'],)).fetchone()
            if type(expected) is not int or expected != (head[0] if head else 0):
                raise Conflict('Issue changed; reload')
            revision=expected+1
            db.execute('INSERT INTO issue_history VALUES(?,?,?,?,?)',(p['id'],revision,canonical(p),text(actor,'actor',200),now()))
            db.execute('INSERT INTO issues VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(p['id'],revision,canonical(p)))
            self._event(db,'issue',{'id':p['id'],'revision':revision,'status':p['status']})
            return dict(p,revision=revision)

    def issues(self):
        with self.connection() as db:
            return [dict(json.loads(r['payload']),revision=r['revision']) for r in db.execute('SELECT * FROM issues ORDER BY id')]

    def issue_history(self, key):
        with self.connection() as db:
            return [dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM issue_history WHERE id=? ORDER BY revision DESC',(key,))]

    def snapshot(self):
        """Freeze authoritative heads atomically, independent of memory and events."""
        with self.connection() as db, self.transaction(db):
            payload = {'schema':1, 'project_id':self.context.manifest['project_id'],
                       'source_sha256':self.context.manifest['source']['sha256'], 'records':self._all(db)}
            raw=canonical(payload)
            digest=hashlib.sha256(raw.encode('utf-8')).hexdigest()
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?)',(digest,raw,now()))
            self._event(db,'snapshot',{'digest':digest,'records':len(payload['records'])})
        return {'sha256':digest,'data':payload}

    def export_snapshot(self, digest):
        with self.connection() as db:
            row=db.execute('SELECT payload FROM snapshots WHERE digest=?',(digest,)).fetchone()
            if not row:
                raise KeyError('Snapshot not found')
            data=row[0].encode('utf-8')
        if hashlib.sha256(data).hexdigest()!=digest:
            raise ValueError('Snapshot hash mismatch')
        policy=OutputPolicy(confined(self.directory,'snapshots'))
        path=policy.check(digest+'.json')
        if path.exists():
            if path.read_bytes()!=data:
                raise ValueError('Existing snapshot differs')
        else:
            try:
                policy.write_new(path,data)
            except FileExistsError:
                if path.read_bytes()!=data:
                    raise ValueError('Concurrent snapshot differs')
        return str(path)

    def build(self, data, expected):
        """Report a private pipeline's build. Does not execute commands or approve it."""
        if not isinstance(data,dict) or set(data)-{'id','snapshot','status','summary','artifacts','validation','approval','evidence'}:
            raise ValueError('Invalid build report')
        p=dict(data);identity(p.get('id'))
        if p.get('status') not in ('queued','running','validated','failed','interrupted','historical'):
            raise ValueError('Invalid build state')
        text(p.get('summary',''),'summary',20000)
        # Approval is external reported evidence, never inferred from success.
        approval=p.get('approval',{})
        if not isinstance(approval,dict) or (approval.get('approved') and not approval.get('reference')):
            raise ValueError('Checkpoint approval needs explicit evidence')
        if len(canonical(p))>250000:
            raise ValueError('Build report too large')
        with self.connection() as db, self.transaction(db):
            if p.get('snapshot') and not db.execute('SELECT 1 FROM snapshots WHERE digest=?',(p['snapshot'],)).fetchone():
                raise KeyError('Unknown snapshot')
            row=db.execute('SELECT revision FROM builds WHERE id=?',(p['id'],)).fetchone()
            if type(expected) is not int or expected!=(row[0] if row else 0):
                raise Conflict('Build report changed')
            revision=expected+1
            db.execute('INSERT INTO build_history VALUES(?,?,?,?)',(p['id'],revision,canonical(p),now()))
            db.execute('INSERT INTO builds VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,payload=excluded.payload',(p['id'],revision,canonical(p)))
            self._event(db,'build',{'id':p['id'],'status':p['status'],'revision':revision})
        return dict(p,revision=revision)

    def builds(self):
        with self.connection() as db:
            return [dict(json.loads(r['payload']),revision=r['revision']) for r in db.execute('SELECT * FROM builds ORDER BY id DESC')]

    @staticmethod
    def _attachment_data(data):
        allowed={'description','record_ids','build_id','issue_ids','scene','resource','association'}
        if not isinstance(data,dict) or set(data)-allowed:raise ValueError('Invalid screenshot metadata')
        p={key:text(data.get(key,''),key,4000) for key in ('description','build_id','scene','resource')}
        for key in ('record_ids','issue_ids'):
            values=data.get(key,[])
            if not isinstance(values,list) or len(values)>200:raise ValueError('Invalid screenshot associations')
            p[key]=list(dict.fromkeys(identity(v) for v in values))
        p['association']=data.get('association','provisional')
        if p['association'] not in ('provisional','confirmed'):raise ValueError('Invalid association status')
        return p

    def _attachment_links(self,db,p):
        for key in p['record_ids']:self._get(db,key)
        for key in p['issue_ids']:
            if not db.execute('SELECT 1 FROM issues WHERE id=?',(key,)).fetchone():raise KeyError('Unknown issue')

    def _attachment_row(self,row,revision):
        return dict(self._attachment_data(json.loads(row['payload'])),digest=row['digest'],mime=row['mime'],revision=revision)

    def upload(self,data,metadata):
        from .images import inspect
        info=inspect(data);p=self._attachment_data(metadata)
        digest=hashlib.sha256(data).hexdigest()
        policy=OutputPolicy(confined(self.directory,'evidence'));dest=policy.check(digest)
        with self.connection() as db, self.transaction(db):
            self._attachment_links(db,p)
            prior=db.execute('SELECT * FROM attachments WHERE digest=?',(digest,)).fetchone()
            if prior:
                if not dest.is_file() or dest.read_bytes()!=data:raise ValueError('Stored screenshot integrity failure')
                revision=db.execute('SELECT max(revision) FROM attachment_history WHERE digest=?',(digest,)).fetchone()[0]
                return dict(self._attachment_row(prior,revision),already_registered=True)
            if dest.exists():
                if dest.read_bytes()!=data:raise ValueError('Evidence copy differs')
            else:policy.write_new(dest,data)
            db.execute('INSERT INTO attachments VALUES(?,?,?)',(digest,info['mime'],canonical(p)))
            db.execute('INSERT INTO attachment_history VALUES(?,?,?,?)',(digest,1,canonical(p),now()))
            self._event(db,'attachment',{'digest':digest,'revision':1})
        return dict(p,digest=digest,mime=info['mime'],revision=1,already_registered=False)

    def attach(self,path,description='',record_ids=None,build_id=''):
        """Explicit CLI registration; browser uploads provide bytes, never paths."""
        source=Path(path)
        source=(source if source.is_absolute() else self.context.root/source).resolve()
        if not source.is_relative_to(self.context.root) or source.suffix.lower() not in ('.png','.jpg','.jpeg'):
            raise ValueError('Expected an image inside the selected private project')
        if source.stat().st_size>10*1024*1024:raise ValueError('Image exceeds 10 MiB')
        data=source.read_bytes();p=self._attachment_data(dict(description=description,record_ids=record_ids or [],build_id=build_id))
        digest=hashlib.sha256(data).hexdigest()
        with self.connection() as db:
            old=db.execute('SELECT payload FROM attachments WHERE digest=?',(digest,)).fetchone()
            if old and self._attachment_data(json.loads(old[0]))!=p:
                raise Conflict('Image already registered with different associations; use a revision-checked update')
        return self.upload(data,p)

    def update_attachment(self,digest,data,expected):
        p=self._attachment_data(data)
        with self.connection() as db, self.transaction(db):
            old=db.execute('SELECT * FROM attachments WHERE digest=?',(digest,)).fetchone()
            if not old:raise KeyError('Unknown screenshot')
            revision=db.execute('SELECT max(revision) FROM attachment_history WHERE digest=?',(digest,)).fetchone()[0]
            if type(expected) is not int or expected!=revision:raise Conflict('Screenshot associations changed; reload before saving')
            self._attachment_links(db,p)
            db.execute('UPDATE attachments SET payload=? WHERE digest=?',(canonical(p),digest))
            db.execute('INSERT INTO attachment_history VALUES(?,?,?,?)',(digest,revision+1,canonical(p),now()))
            self._event(db,'attachment',{'digest':digest,'revision':revision+1})
            return dict(p,digest=digest,mime=old['mime'],revision=revision+1)

    def attachment_history(self,digest):
        with self.connection() as db:
            return [dict(r,payload=json.loads(r['payload'])) for r in db.execute('SELECT * FROM attachment_history WHERE digest=? ORDER BY revision DESC',(digest,))]

    def attachments(self,key=None,issue_id=None):
        with self.connection() as db:
            rows=[self._attachment_row(r,r['revision']) for r in db.execute('SELECT a.*, (SELECT max(revision) FROM attachment_history h WHERE h.digest=a.digest) AS revision FROM attachments a ORDER BY a.digest')]
        return [r for r in rows if (key is None or key in r['record_ids']) and (issue_id is None or issue_id in r['issue_ids'])]

    def image(self, digest):
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('Invalid image ID')
        with self.connection() as db:
            row=db.execute('SELECT mime FROM attachments WHERE digest=?',(digest,)).fetchone()
            if not row:raise KeyError('Unknown image')
        path=confined(self.directory,'evidence/'+digest)
        if path.stat().st_size>10*1024*1024:raise ValueError('Image exceeds limit')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Image integrity check failed')
        return data,row[0]

    def backup(self):
        """Consistent SQLite online backup, including committed WAL transactions."""
        path=OutputPolicy(confined(self.directory,'backups')).write_new(now().replace(':','-')+'.sqlite3',b'')
        with self.connection() as source:
            target=sqlite3.connect(path)
            try:
                source.backup(target)
            finally:
                target.close()
        return str(path)

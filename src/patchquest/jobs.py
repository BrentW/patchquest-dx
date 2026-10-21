"""Durable local build jobs. Private composition roots supply the build callback.

No module discovery, subprocess execution or browser-provided commands occur here.
"""
import json
import re
import threading
import time
import traceback
import uuid

from .state import Conflict, canonical, now, text
from .core.context import OutputPolicy, confined

LEASE_SECONDS = 120


class Jobs:
    def __init__(self, store):
        self.store = store

    def _expire(self, db):
        worker = db.execute('SELECT * FROM build_worker WHERE slot=1').fetchone()
        if worker and worker['expires'] < time.time():
            rows = db.execute("SELECT * FROM build_jobs WHERE status='running'").fetchall()
            for row in rows:
                payload = json.loads(row['payload'])
                payload.update(error={'message':'Worker heartbeat expired. Output may be partial; retry creates a new job.'}, stage='Interrupted')
                db.execute("UPDATE build_jobs SET status='interrupted',payload=?,updated=? WHERE id=?",
                           (canonical(payload), now(), row['id']))
                self.store._event(db, 'job', {'id':row['id'], 'status':'interrupted'})
            db.execute('DELETE FROM build_worker WHERE slot=1')

    def register(self, owner, label, *, require_idle=False):
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            old = db.execute('SELECT * FROM build_worker WHERE slot=1').fetchone()
            if old and old['owner'] != owner:
                raise Conflict('Another build worker is active for this project')
            if require_idle and db.execute("SELECT 1 FROM build_jobs WHERE status IN ('queued','running')").fetchone():
                raise Conflict('This project has an unfinished build. Inspect it before loading a builder.')
            db.execute('INSERT OR REPLACE INTO build_worker VALUES(1,?,?,?)',
                       (owner, text(label, 'worker label', 200), time.time()+LEASE_SECONDS))
            self.store._event(db, 'worker', {'status':'online', 'label':label})

    def heartbeat(self, owner):
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            changed = db.execute('UPDATE build_worker SET expires=? WHERE slot=1 AND owner=?',
                                 (time.time()+LEASE_SECONDS, owner)).rowcount
            if not changed:
                raise Conflict('Build worker ownership lost')

    def unregister(self, owner):
        with self.store.connection() as db, self.store.transaction(db):
            for row in db.execute("SELECT * FROM build_jobs WHERE status='running' AND owner=?", (owner,)).fetchall():
                payload=json.loads(row['payload'])
                payload.update(stage='Interrupted', error={'message':'Worker stopped before recording a validated result. Inspect partial outputs; retry creates a new job.'})
                db.execute("UPDATE build_jobs SET status='interrupted',payload=?,updated=? WHERE id=?",
                           (canonical(payload),now(),row['id']))
                self.store._event(db,'job',{'id':row['id'],'status':'interrupted'})
            if db.execute('DELETE FROM build_worker WHERE slot=1 AND owner=?', (owner,)).rowcount:
                self.store._event(db, 'worker', {'status':'offline'})

    def release_idle(self, owner):
        """Fence submissions/claims before detaching an idle, owned worker."""
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            worker = db.execute('SELECT * FROM build_worker WHERE slot=1').fetchone()
            if worker and worker['owner'] != owner:
                raise Conflict('This builder is controlled by another launcher.')
            if db.execute("SELECT 1 FROM build_jobs WHERE status IN ('queued','running')").fetchone():
                raise Conflict('A build is queued or running. Wait for it to finish before switching builders.')
            if db.execute('DELETE FROM build_worker WHERE slot=1 AND owner=?', (owner,)).rowcount:
                self.store._event(db, 'worker', {'status':'offline'})

    def capabilities(self, owner=None):
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            worker = db.execute('SELECT * FROM build_worker WHERE slot=1').fetchone()
            busy = db.execute("SELECT id,status,payload FROM build_jobs WHERE status IN ('queued','running') ORDER BY created LIMIT 1").fetchone()
            return {'available': bool(worker), 'modes':['full'] if worker else [],
                    'worker': worker['label'] if worker else '', 'active_job':busy['id'] if busy else None,
                    'owned': bool(worker and owner and worker['owner'] == owner),
                    'job': {'id':busy['id'], 'status':busy['status'], 'stage':json.loads(busy['payload'])['stage']} if busy else None,
                    'note':'Full integrated build from saved revisions. Selective builds are not configured.'}

    def submit(self, request_id, mode='full'):
        if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{8,80}', request_id) or mode != 'full':
            raise ValueError('Invalid job request or unsupported build mode')
        # Snapshot and job insertion share a transaction: concurrent edits cannot
        # change which revision set was accepted by this request.
        import hashlib
        with self.store.connection() as db, self.store.transaction(db):
            old = db.execute('SELECT * FROM build_jobs WHERE id=?', (request_id,)).fetchone()
            if old:
                return self._row(old)
            self._expire(db)
            if not db.execute('SELECT 1 FROM build_worker WHERE slot=1').fetchone():
                raise Conflict('No private build worker is online. Start the project Studio launcher.')
            if db.execute("SELECT 1 FROM build_jobs WHERE status IN ('queued','running')").fetchone():
                raise Conflict('A build is already queued or running')
            from .assessments import build_gate
            build_gate(self.store, db)
            snapshot = {'schema':1, 'project_id':self.store.context.manifest['project_id'],
                        'source_sha256':self.store.context.manifest['source']['sha256'],
                        'records':self.store._all(db)}
            raw = canonical(snapshot); digest = hashlib.sha256(raw.encode('utf8')).hexdigest()
            db.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?)', (digest, raw, now()))
            payload = {'mode':mode, 'stage':'Queued', 'result':None, 'error':None}
            db.execute('INSERT INTO build_jobs VALUES(?,?,?,?,?,?,?)',
                       (request_id, digest, 'queued', '', canonical(payload), now(), now()))
            self.store._event(db, 'job', {'id':request_id, 'status':'queued', 'snapshot':digest})
            return self._row(db.execute('SELECT * FROM build_jobs WHERE id=?', (request_id,)).fetchone())

    @staticmethod
    def _row(row):
        return {**dict(row), 'payload':json.loads(row['payload'])}

    def list(self):
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            return [self._row(r) for r in db.execute('SELECT * FROM build_jobs ORDER BY created DESC')]

    def claim(self, owner):
        with self.store.connection() as db, self.store.transaction(db):
            self._expire(db)
            if not db.execute('SELECT 1 FROM build_worker WHERE slot=1 AND owner=?', (owner,)).fetchone():
                raise Conflict('Worker is not registered')
            if db.execute("SELECT 1 FROM build_jobs WHERE status='running'").fetchone():
                return None
            row = db.execute("SELECT * FROM build_jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("UPDATE build_jobs SET status='running',owner=?,updated=? WHERE id=?", (owner, now(), row['id']))
            self.store._event(db, 'job', {'id':row['id'], 'status':'running'})
            return self._row(db.execute('SELECT * FROM build_jobs WHERE id=?', (row['id'],)).fetchone())

    def update(self, key, owner, stage, status='running', result=None, error=None):
        if status not in ('running','validated','failed','interrupted'):
            raise ValueError('Invalid job status')
        if status == 'validated' and (not isinstance(result, dict) or result.get('status') != 'validated'
                                      or result.get('approval',{}).get('approved')):
            raise ValueError('A job requires technical validation and cannot approve a checkpoint')
        with self.store.connection() as db, self.store.transaction(db):
            row = db.execute('SELECT * FROM build_jobs WHERE id=?', (key,)).fetchone()
            if not row or row['owner'] != owner or row['status'] != 'running':
                raise Conflict('Job ownership or state changed')
            payload = json.loads(row['payload'])
            payload.update(stage=text(stage,'stage',2000), result=result, error=error)
            db.execute('UPDATE build_jobs SET status=?,payload=?,updated=? WHERE id=?',
                       (status, canonical(payload), now(), key))
            self.store._event(db, 'job', {'id':key,'status':status,'stage':stage})


class BuildWorker:
    """One explicit callback, supplied by a private launcher; no plugin loading."""
    def __init__(self, store, callback, label='Private build worker'):
        self.jobs=Jobs(store); self.callback=callback; self.owner=uuid.uuid4().hex
        self.label=label; self.stop=threading.Event(); self.draining=threading.Event(); self.thread=None
        self.failure=None

    def start(self, *, require_idle=False):
        self.jobs.register(self.owner,self.label,require_idle=require_idle)
        self.thread=threading.Thread(target=self._run,daemon=True)
        self.heartbeat_thread=threading.Thread(target=self._heartbeat,daemon=True)
        try:
            self.thread.start()
            self.heartbeat_thread.start()
        except Exception:
            self.close()
            raise
        return self

    def _heartbeat(self):
        while not self.stop.wait(2):
            try:self.jobs.heartbeat(self.owner)
            except Exception:self.stop.set()

    def _run(self):
        try:
            while not self.stop.is_set() and not self.draining.is_set():
                job=self.jobs.claim(self.owner)
                if job is None:
                    self.draining.wait(.25);continue
                key=job['id']
                try:
                    self.jobs.store.export_snapshot(job['snapshot'])
                    progress=lambda message:self.jobs.update(key,self.owner,message)
                    progress('Starting validated private build pipeline')
                    result=self.callback(job,progress)
                    self.jobs.update(key,self.owner,'Automated validation passed; awaiting in-game review','validated',result)
                except Exception as error:
                    diagnostics={'message':str(error)[:2000], 'type':type(error).__name__}
                    try:
                        log=OutputPolicy(confined(self.jobs.store.directory,'jobs')).write_new(key+'.log',traceback.format_exc().encode('utf8'))
                        diagnostics['log']=str(log)
                    except OSError:
                        diagnostics['log_error']='Could not write the private diagnostic file.'
                    self.jobs.update(key,self.owner,'Build failed; saved corrections retained','failed',error=diagnostics)
        except BaseException as error:
            # Do not advertise a live worker after its job loop has failed.
            self.failure=error
        finally:
            self.stop.set()
            try:self.jobs.unregister(self.owner)
            except Exception:pass  # A persistent storage failure falls back to lease expiry.

    def close(self):
        # A graceful close lets an in-flight immutable build finish. A hard crash
        # is detected by its expiring heartbeat and never automatically retried.
        self.draining.set()
        if self.thread and self.thread.ident is not None:self.thread.join()
        self.stop.set()
        if self.thread and self.heartbeat_thread.ident is not None:self.heartbeat_thread.join(2)
        self.jobs.unregister(self.owner)

    def close_if_idle(self):
        # Deleting the registration in the same transaction as the busy check
        # prevents a concurrent browser/CLI submission from being stranded.
        self.jobs.release_idle(self.owner)
        self.close()

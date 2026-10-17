"""Provider-neutral, transactional work scheduling. Never launches an AI service.

Leases fence cooperating writers, not processes with arbitrary database access.
"""
import json
import time
import uuid
from .state import Conflict, canonical, identity, now, text


def ttl(value):
    if type(value) is not int or not 30 <= value <= 3600:
        raise ValueError('TTL must be 30..3600 seconds')
    return value


def ids(value, name, limit=200):
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError('Invalid '+name)
    parsed=[identity(v) for v in value]
    if len(set(parsed)) != len(parsed):raise ValueError('Duplicate '+name)
    return sorted(parsed)


class Coordination:
    def __init__(self, store):self.store=store

    @staticmethod
    def row(row):return {**dict(row), 'payload':json.loads(row['payload'])}

    def _save(self, db, item, event):
        item['revision']+=1;item['updated']=now()
        db.execute('UPDATE work_items SET revision=?,status=?,payload=?,owner=?,fence=?,expires=?,updated=? WHERE id=?',
                   (item['revision'],item['status'],canonical(item['payload']),item['owner'],item['fence'],item['expires'],item['updated'],item['id']))
        db.execute('INSERT INTO work_history(id,payload,created) VALUES(?,?,?)',(item['id'],canonical(item),now()))
        self.store._event(db,'work',{'id':item['id'],'revision':item['revision'],'status':item['status'],'event':event})

    def _expire(self, db):
        clock=time.time()
        db.execute("UPDATE agent_sessions SET status='expired',updated=? WHERE status='active' AND expires<=?",(now(),clock))
        for row in db.execute("SELECT * FROM work_items WHERE status='leased'").fetchall():
            agent=db.execute("SELECT 1 FROM agent_sessions WHERE id=? AND status='active'",(row['owner'],)).fetchone()
            if row['expires']<=clock or not agent:
                item=self.row(row);item.update(status='queued',owner='',expires=0,fence=item['fence']+1)
                item['payload']['progress']='Lease expired; reread revisions and handoff before retrying'
                self._save(db,item,'expired')

    def _agent(self, db, session):
        row=db.execute("SELECT * FROM agent_sessions WHERE id=? AND status='active' AND expires>?",(session,time.time())).fetchone()
        if not row:raise Conflict('Agent session expired or closed; start a new session')
        return self.row(row)

    def start(self, provider, model='', label='', lease_seconds=300):
        payload={'provider':text(provider,'provider',100),'model':text(model,'model',100),'label':text(label,'label',200)}
        if not provider:raise ValueError('Provider label required')
        session=uuid.uuid4().hex;expires=time.time()+ttl(lease_seconds)
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db)
            db.execute('INSERT INTO agent_sessions VALUES(?,?,?,?,?,?)',(session,canonical(payload),'active',expires,now(),now()))
            self.store._event(db,'agent',{'session':session,'status':'active',**payload})
        return {'session':session,'expires':expires,**payload}

    def heartbeat(self, session, lease_seconds=300):
        seconds=ttl(lease_seconds)
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db);self._agent(db,session)
            expires=time.time()+seconds
            db.execute('UPDATE agent_sessions SET expires=?,updated=? WHERE id=?',(expires,now(),session))
        return {'session':session,'expires':expires}

    def close(self, session):
        with self.store.connection() as db,self.store.transaction(db):
            db.execute("UPDATE agent_sessions SET status='closed',updated=? WHERE id=?",(now(),session))
            self._expire(db);self.store._event(db,'agent',{'session':session,'status':'closed'})
        return {'closed':session}

    def sessions(self):
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db)
            return [self.row(r) for r in db.execute('SELECT * FROM agent_sessions ORDER BY created DESC')]

    def create(self, key, title, record_ids=None, resources=None, dependencies=None, priority=0, instructions=''):
        identity(key)
        payload={'title':text(title,'title',500),'record_ids':ids([] if record_ids is None else record_ids,'record IDs'),
                 'resources':ids([] if resources is None else resources,'resources'),'dependencies':ids([] if dependencies is None else dependencies,'dependencies'),
                 'priority':priority,'instructions':text(instructions,'instructions',12000),'progress':'','handoff':''}
        if type(priority) is not int or not 0<=priority<=100:raise ValueError('Priority must be 0..100')
        if not title or not (payload['record_ids'] or payload['resources']):raise ValueError('Explicit work scope required')
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db)
            if db.execute('SELECT 1 FROM work_items WHERE id=?',(key,)).fetchone():raise Conflict('Task already exists')
            for record in payload['record_ids']:self.store._get(db,record)
            for dep in payload['dependencies']:
                if not db.execute('SELECT 1 FROM work_items WHERE id=?',(dep,)).fetchone():raise ValueError('Dependency must already exist')
            db.execute('INSERT INTO work_items VALUES(?,0,?,?,?,0,0,?,?)',(key,'queued',canonical(payload),'',now(),now()))
            item=self.row(db.execute('SELECT * FROM work_items WHERE id=?',(key,)).fetchone());self._save(db,item,'created')
        return item

    def list(self):
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db)
            return [self.row(r) for r in db.execute('SELECT * FROM work_items ORDER BY created')]

    def history(self, key):
        with self.store.connection() as db:
            return [json.loads(r[0]) for r in db.execute('SELECT payload FROM work_history WHERE id=? ORDER BY seq',(key,))]

    @staticmethod
    def locks(item):
        p=item['payload']
        return {('record',x) for x in p['record_ids']}|{('resource',x) for x in p['resources']}

    def claim(self, session, key=None, lease_seconds=300):
        seconds=ttl(lease_seconds)
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db);agent=self._agent(db,session)
            items=[self.row(r) for r in db.execute('SELECT * FROM work_items')]
            by_id={r['id']:r for r in items};locked=set()
            for item in items:
                if item['status']=='leased':locked.update(self.locks(item))
            eligible=sorted((r for r in items if r['status']=='queued' and (key is None or r['id']==key)),key=lambda r:(-r['payload']['priority'],r['created'],r['id']))
            for item in eligible:
                if self.locks(item)&locked or any(by_id[d]['status']!='done' for d in item['payload']['dependencies']):continue
                item.update(status='leased',owner=session,fence=item['fence']+1,expires=min(time.time()+seconds,agent['expires']))
                item['payload']['progress']='Claimed; read current context before editing'
                for rid in item['payload']['record_ids']:db.execute('INSERT OR IGNORE INTO work_managed VALUES(?)',(rid,))
                self._save(db,item,'claimed')
                item['records']=[self.store._get(db,rid) for rid in item['payload']['record_ids']]
                return item
            if key is not None:raise Conflict('Task unavailable, blocked by dependencies or overlapping work')
            return None

    def _lease(self, db, session, key, fence):
        self._expire(db);self._agent(db,session)
        row=db.execute('SELECT * FROM work_items WHERE id=?',(key,)).fetchone()
        if type(fence) is not int or not row or row['status']!='leased' or row['owner']!=session or row['fence']!=fence:
            raise Conflict('Stale or foreign task lease; reread and claim again')
        return self.row(row)

    def renew(self, session, key, fence, lease_seconds=300, progress=''):
        seconds=ttl(lease_seconds);text(progress,'progress',2000)
        with self.store.connection() as db,self.store.transaction(db):
            item=self._lease(db,session,key,fence)
            item['expires']=min(time.time()+seconds,self._agent(db,session)['expires'])
            item['payload']['progress']=progress;self._save(db,item,'renewed')
        return item

    def publish(self, session, key, fence, changes, reason=''):
        if not isinstance(changes,list) or not 1<=len(changes)<=200:raise ValueError('Bounded changes required')
        text(reason,'reason',4000);seen=set();results=[]
        with self.store.connection() as db,self.store.transaction(db):
            item=self._lease(db,session,key,fence);agent=self._agent(db,session)
            for change in changes:
                if not isinstance(change,dict) or set(change)-{'id','expected','target','uncertainty'} or not {'id','expected','target'}<=set(change):raise ValueError('Invalid change')
                rid=change['id']
                if rid in seen or rid not in item['payload']['record_ids']:raise ValueError('Duplicate or out-of-scope record')
                seen.add(rid);data=self.store._get(db,rid)
                for field in ('revision','human_corrected','provenance'):data.pop(field)
                data['target']=change['target']
                if 'uncertainty' in change:data['uncertainty']=change['uncertainty']
                actor=agent['payload']['provider']+':'+session
                results.append(self.store._put(db,data,change['expected'],'agent',actor,reason,_work=True))
            item['payload']['progress']='Published '+str(len(results))+' results; proposals remain inactive'
            self._save(db,item,'published')
        return {'task':item,'results':results}

    def finish(self, session, key, fence, status='done', handoff=''):
        if status not in ('done','blocked','queued'):raise ValueError('Invalid finish status')
        text(handoff,'handoff',12000)
        if status!='done' and not handoff.strip():raise ValueError('Handoff/reason required')
        with self.store.connection() as db,self.store.transaction(db):
            item=self._lease(db,session,key,fence)
            item.update(status=status,owner='',expires=0,fence=item['fence']+1)
            item['payload']['handoff']=handoff;item['payload']['progress']='Work '+status
            self._save(db,item,'finished')
        return item

    def resolve(self, key, expected, status, reason):
        """Explicit coordinator recovery. Active work must finish/expire first."""
        if status not in ('queued','cancelled') or not text(reason,'reason',12000).strip():raise ValueError('Recovery status/reason required')
        with self.store.connection() as db,self.store.transaction(db):
            self._expire(db);row=db.execute('SELECT * FROM work_items WHERE id=?',(key,)).fetchone()
            if type(expected) is not int or not row or row['revision']!=expected or row['status'] in ('leased','done','cancelled'):raise Conflict('Task changed, is leased or already terminal; create a new task for follow-up work')
            item=self.row(row);item.update(status=status,owner='',expires=0,fence=item['fence']+1)
            item['payload']['handoff']=reason;self._save(db,item,'coordinator recovery')
        return item

"""Optional local HTTP Studio. No project code loading or command execution."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import base64
import binascii
from pathlib import Path
import secrets
import sqlite3
import csv
import hashlib
import re
from urllib.parse import parse_qs, urlsplit

from .state import Store, Conflict
from .state_api import execute, READ_ACTIONS
from .studio_projects import ProjectDirectory
from .studio_csv import export_csv, import_csv
from .studio_builders import StudioBuilders
from .progress import ProgressReporter, DEFAULT_INTERVAL
from .runtime_contracts import COVERAGE_STATUSES

STATIC = Path(__file__).with_name('studio_assets')
FILES = {'/':('index.html','text/html; charset=utf-8'),
         '/app.js':('app.js','text/javascript; charset=utf-8'),
         '/style.css':('style.css','text/css; charset=utf-8')}
MAX_BODY = 1024 * 1024
MAX_UPLOAD = 14 * 1024 * 1024
MAX_REVIEW_JSON = 2 * 1024 * 1024


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # Detail views request history, memory and evidence while the dashboard polls.
    request_queue_size = 32

    def __init__(self, store, port=8765, *, platform_root=None, builders=(), initial_builder=None,
                 progress_interval=DEFAULT_INTERVAL, runtime_review_providers=()):
        self.store=store
        self.projects=ProjectDirectory(store, platform_root)
        self.runtime_review_providers={}
        available={e['id'] for e in self.projects.catalogue()['projects'] if e['available']}
        for path, provider in runtime_review_providers:
            key=self.projects._key(path)
            if (key not in available or key in self.runtime_review_providers or
                    not callable(getattr(provider,'read',None)) or
                    not callable(getattr(provider,'image',None))):
                raise ValueError('Runtime review requires a unique configured project and provider')
            self.runtime_review_providers[key]=provider
        self.builders=StudioBuilders(self.projects, builders)
        self.progress=ProgressReporter(self.projects, progress_interval)
        self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port), Handler)
        self.origin='http://127.0.0.1:'+str(self.server_port)
        if initial_builder is not None:
            try:
                self.builders.switch(self.projects._key(initial_builder), self.builders.version)
            except Exception:
                self.server_close()
                raise
        self.progress.start()

    def server_close(self):
        try:
            self.progress.close()
        finally:
            try:
                self.builders.close()
            finally:
                super().server_close()

    @property
    def url(self):
        return self.origin+'/#'+self.token


class Handler(BaseHTTPRequestHandler):
    server_version='PatchQuestStudio'
    protocol_version='HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *args):
        # Request URLs and text can contain private information. No access log.
        pass

    def respond(self, status, body, mime='application/json; charset=utf-8'):
        data=body if isinstance(body,bytes) else json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',mime)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def guard(self, auth=True):
        host=self.headers.get('Host','')
        origin=self.headers.get('Origin')
        if host!='127.0.0.1:'+str(self.server.server_port) or (origin and origin!=self.server.origin):
            self.respond(403,{'error':'This Studio accepts only its local origin.'})
            return False
        if auth and not secrets.compare_digest(self.headers.get('X-Studio-Token',''),self.server.token):
            self.respond(401,{'error':'Open the launch URL printed in your local terminal.'})
            return False
        return True

    def do_GET(self):
        if not self.guard(auth=False):
            return
        url=urlsplit(self.path)
        if url.path in FILES and (not url.query or url.path == '/'):
            name,mime=FILES[url.path]
            self.respond(200,(STATIC/name).read_bytes(),mime)
            return
        if not self.guard():
            return
        if url.path == '/api/projects' and not url.query:
            self.respond(200, self.server.projects.catalogue())
            return
        store = self.project_store()
        if store is None:
            return
        if url.path.startswith('/media/') and not url.query:
            try:
                data,mime=store.image(url.path[7:])
                self.respond(200,data,mime)
            except (ValueError,KeyError,OSError):
                self.respond(404,{'error':'Image unavailable'})
            return
        if not url.path.startswith('/api/'):
            self.respond(404,{'error':'Not found'})
            return
        action=url.path[5:]
        if action not in READ_ACTIONS and action not in (
                'csv-export','builder-status','runtime-review','runtime-review-image','runtime-gaps'):
            self.respond(404,{'error':'Unknown read operation'})
            return
        try:
            query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True,max_num_fields=15) if url.query else {}
            if any(len(v)!=1 for v in query.values()):
                raise ValueError('Duplicate parameter')
            params={k:v[0] for k,v in query.items()}
            for key in ('offset','limit','after'):
                if key in params:params[key]=int(params[key])
            if action in ('runtime-review','runtime-review-image','runtime-gaps'):
                self.runtime_review(store,action,params)
            elif action == 'builder-status':
                if params:raise ValueError('Builder status takes no parameters')
                self.respond(200,self.server.builders.status(self.server.projects._key(store.manifest_path)))
            elif action == 'csv-export':
                self.respond(200,export_csv(store,params).encode('utf-8'),'text/csv; charset=utf-8')
            else:
                self.respond(200,execute(store,action,params))
        except (ValueError,TypeError,KeyError) as error:
            self.respond(400,{'error':'Invalid request or missing record.'})
        except Exception:
            self.respond(500,{'error':'State operation failed; check the local workspace.'})

    def runtime_review(self,store,action,params):
        """Dispatch only to an explicitly configured, project-bound local provider."""
        key=self.server.projects._key(store.manifest_path)
        provider=self.server.runtime_review_providers.get(key)
        if action=='runtime-gaps':
            from .runtime_gaps import KINDS
            if (set(params)-{'kind','group_id','offset','limit'} or
                    params.get('kind','') not in ('',*KINDS) or
                    (params.get('group_id','') and not re.fullmatch('[0-9a-f]{64}',params['group_id'])) or
                    type(params.get('offset',0)) is not int or not 0<=params.get('offset',0)<=1000000 or
                    type(params.get('limit',20)) is not int or not 1<=params.get('limit',20)<=100):
                raise ValueError('Invalid discovery page')
            if provider is None or not callable(getattr(provider,'gaps',None)):
                result=dict(available=False,reason='Text coverage and discovery is not configured for this project.',
                            items=[],total=0,offset=0,limit=20)
            else:
                result=dict(provider.gaps(store,params),available=True)
            result.update(schema_version=1,project_key=key)
            data=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf8')
            if len(data)>MAX_REVIEW_JSON:
                raise ValueError('Discovery response exceeds page bound')
            self.respond(200,data)
            return
        def opaque(value):
            return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}',value)
        if action=='runtime-review-image':
            if (set(params)!={'evidence_id','sha256'} or not opaque(params['evidence_id']) or
                    not re.fullmatch(r'[0-9a-f]{64}',params['sha256'])):
                raise ValueError('Invalid image selection')
            if provider is None:
                self.respond(404,{'error':'Runtime review image unavailable.'})
                return
            try:
                data=provider.image(store,params['evidence_id'],params['sha256'])
                if (type(data) is not bytes or len(data)>MAX_UPLOAD or
                        not data.startswith(b'\x89PNG\r\n\x1a\n') or
                        hashlib.sha256(data).hexdigest()!=params['sha256']):
                    raise ValueError('Unavailable immutable PNG')
            except (ValueError,KeyError,OSError):
                self.respond(404,{'error':'Runtime review image unavailable.'})
                return
            self.respond(200,data,'image/png')
            return
        if set(params)-{'group_id','build_id','status','method','purpose','offset','limit'}:
            raise ValueError('Unknown review parameter')
        params=dict(params)
        params.setdefault('offset',0);params.setdefault('limit',50)
        if (type(params['offset']) is not int or not 0<=params['offset']<=1000000 or
                type(params['limit']) is not int or not 1<=params['limit']<=200):
            raise ValueError('Invalid review page')
        for field in ('group_id','build_id'):
            if field in params and not opaque(params[field]):
                raise ValueError('Invalid review selector')
        for field,allowed in (
                ('status',COVERAGE_STATUSES),('method',('synthetic','automated_runtime')),
                ('purpose',('renderer','normal_gameplay'))):
            if field in params and params[field] not in allowed:
                raise ValueError('Invalid review filter')
        if provider is None:
            result=dict(available=False,reason='Runtime review is not configured for this project.',
                        groups=[],items=[],total=0,offset=params['offset'],limit=params['limit'])
        else:
            result=provider.read(store,params)
            if type(result) is not dict:
                raise TypeError('Invalid review provider response')
            result=dict(result,available=True)
        result.update(schema_version=1,project_key=key)
        data=json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf8')
        if len(data)>MAX_REVIEW_JSON:
            raise ValueError('Review provider response exceeds the page bound')
        self.respond(200,data)

    def project_store(self):
        try:
            values = self.headers.get_all('X-Studio-Project')
            if values is not None and len(values) != 1:
                raise ValueError('Duplicate project selector')
            return self.server.projects.select(values[0] if values else None)
        except (KeyError, ValueError, OSError, TypeError, sqlite3.DatabaseError):
            self.respond(404, {'error':'Project unavailable. Choose a configured project or check its local setup.'})
            return None

    def do_POST(self):
        # Consume a bounded body before rejecting a route. Closing a Windows
        # socket with unread request bytes can reset it before the error arrives.
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Unsupported transfer encoding')
            size=int(self.headers.get('Content-Length','-1'))
            limit=MAX_UPLOAD if urlsplit(self.path).path in ('/api/upload','/api/csv-import') else MAX_BODY
            if not 0<=size<=limit:
                raise ValueError('Invalid length')
            body=self.rfile.read(size)
            if len(body)!=size:
                raise ValueError('Incomplete body')
        except (ValueError, OSError):
            self.close_connection=True  # Do not reuse a stream with unread/ambiguous body bytes.
            self.respond(400,{'error':'Invalid or incomplete request body.'})
            return
        if not self.guard():
            return
        url=urlsplit(self.path)
        if url.query or not url.path.startswith('/api/'):
            self.respond(404,{'error':'Not found'})
            return
        action=url.path[5:]
        # Browser edit operations deliberately cannot claim pipeline/hardware
        # evidence, approve builds or run arbitrary commands. CSV accepts only
        # revision-bound wording corrections to existing records.
        if action not in ('edit','restore','issue-put','runtime-gap-issue','snapshot','build-submit','upload','attachment-update','csv-import','builder-switch',
                          'milestone-put','milestone-review','milestone-select','milestone-export',
                          'screenshot-put','screenshot-review','screenshot-select','screenshot-export',
                          'tester-import-preview','tester-import','tester-context','tester-triage',
                          'release-put','release-validate','release-review','release-export'):
            self.respond(404,{'error':'Unsupported browser operation'})
            return
        store = self.project_store()
        if store is None:
            return
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                raise ValueError('JSON required')
            p=json.loads(body)
            if not isinstance(p,dict):raise ValueError('Object required')
            if action.startswith('release-'):
                allowed = {'release-put': {'data','build_id','patch_artifact','output_artifact','repeat_build_id','expected','key','private_notes'},
                           'release-validate': {'key','expected'},
                           'release-review': {'key','expected','validation_token'},
                           'release-export': {'key','expected','validation_token'}}[action]
                if set(p)-allowed:raise ValueError('Unsupported release preparation fields')
                if action=='release-export':
                    import uuid
                    p['destination']='release-manifests/'+uuid.uuid4().hex+'.json'
                result=execute(store,action,dict(p,actor='Studio user'))
            elif action.startswith('tester-'):
                allowed = {'tester-import-preview': {'document'},
                           'tester-import': {'document','preview_token'},
                           'tester-context': {'key','build_id','record_ids','attachment_digests'},
                           'tester-triage': {'key','expected','context_token','status','notes','build_id',
                               'record_ids','attachment_digests','issue_id','duplicate_of','create_issue'}}[action]
                if set(p)-allowed:raise ValueError('Unsupported tester workflow fields')
                if action in ('tester-import','tester-triage'):p['actor']='Studio user'
                result=execute(store,action,p)
            elif action.startswith('screenshot-'):
                allowed = {'screenshot-put': {'data','digest','context_token','expected','key','runtime_report','runtime_capture','private_notes'},
                           'screenshot-review': {'key','expected','review_token'},
                           'screenshot-select': {'key','expected','selected'},
                           'screenshot-export': {'expected'}}[action]
                if set(p)-allowed:raise ValueError('Unsupported screenshot selection fields')
                if action=='screenshot-export':
                    import uuid
                    p['destination']='screenshot-selection/'+uuid.uuid4().hex+'.json'
                result=execute(store,action,dict(p,actor='Studio user'))
            elif action.startswith('milestone-'):
                allowed = {'milestone-put': {'data','expected','key','private_notes'},
                           'milestone-review': {'key','expected','content_sha256'},
                           'milestone-select': {'key','expected','selected'},
                           'milestone-export': {'expected'}}[action]
                if set(p)-allowed:raise ValueError('Unsupported milestone fields')
                if action=='milestone-export':
                    import uuid
                    p['destination']='milestone-updates/'+uuid.uuid4().hex+'.json'
                result=execute(store,action,dict(p,actor='Studio user'))
            elif action=='builder-switch':
                if set(p) != {'expected'}:raise ValueError('Expected builder version required')
                result=self.server.builders.switch(self.server.projects._key(store.manifest_path),p['expected'])
            elif action=='csv-import':
                if set(p) != {'csv'}:raise ValueError('CSV text required')
                result=import_csv(store,p['csv'])
            elif action=='edit':
                if set(p)-{'key','expected','source','target','uncertainty','reason'}:
                    raise ValueError('Unsupported edit fields')
                if not {'source','target','uncertainty'} & set(p):
                    raise ValueError('No editable text supplied')
                current=store.get(p['key'])
                record={k:v for k,v in current.items() if k not in ('revision','human_corrected','provenance')}
                for field in ('source','target','uncertainty'):
                    if field in p:record[field]=p[field]
                result=store.put(record,p['expected'],'human','Studio user',p.get('reason','Human correction'))
            elif action=='restore':
                if set(p)!={'key','revision','expected'}:raise ValueError('Invalid restore')
                result=store.restore(**p,actor='Studio user')
            elif action=='runtime-gap-issue':
                provider=self.server.runtime_review_providers.get(self.server.projects._key(store.manifest_path))
                if provider is None or not callable(getattr(provider,'gap_issue',None)):
                    raise ValueError('Discovery provider unavailable')
                result=provider.gap_issue(store,p,actor='Studio user')
            elif action=='issue-put':
                if set(p)!={'data','expected'}:raise ValueError('Invalid issue')
                result=store.put_issue(**p,actor='Studio user')
            elif action=='build-submit':
                if set(p)-{'request_id','mode'}:raise ValueError('Invalid build request')
                result=execute(store,action,p)
            elif action=='upload':
                if set(p)!={'base64','metadata'} or not isinstance(p['base64'],str):raise ValueError('Invalid upload')
                result=store.upload(base64.b64decode(p['base64'],validate=True),p['metadata'])
            elif action=='attachment-update':
                result=store.update_attachment(**p)
            else:
                if p:raise ValueError('Snapshot takes no parameters')
                frozen=store.snapshot()
                result={'sha256':frozen['sha256'],'records':len(frozen['data']['records']),
                        'path':store.export_snapshot(frozen['sha256'])}
            self.respond(200,result)
        except Conflict as error:
            message=str(error) if action in ('build-submit','upload','attachment-update','csv-import','builder-switch') else 'Another editor or agent changed this record. Your draft is retained. Reload and compare before saving.'
            self.respond(409,{'error':message})
        except (ValueError,TypeError,KeyError,binascii.Error,csv.Error):
            self.respond(400,{'error':'Invalid CSV or missing record. No rows imported. Use an exported CSV and edit only target cells.' if action == 'csv-import' else 'Invalid request or missing record.'})
        except Exception:
            self.respond(500,{'error':'State operation failed; check the local workspace.'})


def serve(manifest, port=8765, *, platform_root=None, builders=(), initial_builder=None,
          progress_interval=DEFAULT_INTERVAL, runtime_review_providers=()):
    store=Store(manifest)
    with StudioServer(store,port,platform_root=platform_root,builders=builders,
                      initial_builder=initial_builder,progress_interval=progress_interval,
                      runtime_review_providers=runtime_review_providers) as server:
        print('Translation Studio is local only. Open this private session URL:',flush=True)
        print(server.url,flush=True)
        print('Leave this terminal running; Ctrl+C stops the server. No AI agent is required.',flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

"""Optional local HTTP Studio. No project code loading or command execution."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import base64
import binascii
from pathlib import Path
import secrets
from urllib.parse import parse_qs, urlsplit

from .state import Store, Conflict
from .state_api import execute, READ_ACTIONS

STATIC = Path(__file__).with_name('studio_assets')
FILES = {'/':('index.html','text/html; charset=utf-8'),
         '/app.js':('app.js','text/javascript; charset=utf-8'),
         '/style.css':('style.css','text/css; charset=utf-8')}
MAX_BODY = 1024 * 1024
MAX_UPLOAD = 14 * 1024 * 1024


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    # Detail views request history, memory and evidence while the dashboard polls.
    request_queue_size = 32

    def __init__(self, store, port=8765):
        self.store=store
        self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',port), Handler)
        self.origin='http://127.0.0.1:'+str(self.server_port)

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
        if url.path in FILES and not url.query:
            name,mime=FILES[url.path]
            self.respond(200,(STATIC/name).read_bytes(),mime)
            return
        if not self.guard():
            return
        if url.path.startswith('/media/') and not url.query:
            try:
                data,mime=self.server.store.image(url.path[7:])
                self.respond(200,data,mime)
            except (ValueError,KeyError,OSError):
                self.respond(404,{'error':'Image unavailable'})
            return
        if not url.path.startswith('/api/'):
            self.respond(404,{'error':'Not found'})
            return
        action=url.path[5:]
        if action not in READ_ACTIONS:
            self.respond(404,{'error':'Unknown read operation'})
            return
        try:
            query=parse_qs(url.query,keep_blank_values=True,strict_parsing=True,max_num_fields=15) if url.query else {}
            if any(len(v)!=1 for v in query.values()):
                raise ValueError('Duplicate parameter')
            params={k:v[0] for k,v in query.items()}
            for key in ('offset','limit','after'):
                if key in params:params[key]=int(params[key])
            self.respond(200,execute(self.server.store,action,params))
        except (ValueError,TypeError,KeyError) as error:
            self.respond(400,{'error':'Invalid request or missing record.'})
        except Exception:
            self.respond(500,{'error':'State operation failed; check the local workspace.'})

    def do_POST(self):
        # Consume a bounded body before rejecting a route. Closing a Windows
        # socket with unread request bytes can reset it before the error arrives.
        try:
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Unsupported transfer encoding')
            size=int(self.headers.get('Content-Length','-1'))
            limit=MAX_UPLOAD if urlsplit(self.path).path=='/api/upload' else MAX_BODY
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
        # evidence, import files, approve builds or run arbitrary commands.
        if action not in ('edit','restore','issue-put','snapshot','build-submit','upload','attachment-update'):
            self.respond(404,{'error':'Unsupported browser operation'})
            return
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                raise ValueError('JSON required')
            p=json.loads(body)
            if not isinstance(p,dict):raise ValueError('Object required')
            store=self.server.store
            if action=='edit':
                if set(p)-{'key','expected','target','uncertainty','reason'}:
                    raise ValueError('Unsupported edit fields')
                current=store.get(p['key'])
                record={k:v for k,v in current.items() if k not in ('revision','human_corrected','provenance')}
                record['target']=p['target']
                if 'uncertainty' in p:record['uncertainty']=p['uncertainty']
                result=store.put(record,p['expected'],'human','Studio user',p.get('reason','Human correction'))
            elif action=='restore':
                if set(p)!={'key','revision','expected'}:raise ValueError('Invalid restore')
                result=store.restore(**p,actor='Studio user')
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
            message=str(error) if action in ('build-submit','upload','attachment-update') else 'Another editor or agent changed this record. Your draft is retained. Reload and compare before saving.'
            self.respond(409,{'error':message})
        except (ValueError,TypeError,KeyError,binascii.Error):
            self.respond(400,{'error':'Invalid request or missing record.'})
        except Exception:
            self.respond(500,{'error':'State operation failed; check the local workspace.'})


def serve(manifest, port=8765):
    store=Store(manifest)
    with StudioServer(store,port) as server:
        print('Translation Studio is local only. Open this private session URL:',flush=True)
        print(server.url,flush=True)
        print('Leave this terminal running; Ctrl+C stops the server. No AI agent is required.',flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

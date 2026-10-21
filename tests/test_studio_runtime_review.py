"""Authenticated read-only review transport with invented providers/projects."""
import hashlib
import http.client
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from patchquest.state import Store
from patchquest.studio import StudioServer
from patchquest.studio import serve


class Provider:
    def __init__(self, store, label):
        self.path=store.manifest_path;self.label=label;self.calls=[]
        self.payload=PIXEL;self.fail=False

    def check(self,store):
        if store.manifest_path!=self.path:
            raise AssertionError('Cross-project provider dispatch')

    def read(self,store,params):
        self.check(store);self.calls.append(dict(params))
        if self.fail:raise RuntimeError('Private provider details must not leak')
        return dict(items=[dict(label=self.label)],total=1,offset=params['offset'],limit=params['limit'])

    def image(self,store,evidence_id,sha256):
        self.check(store);self.calls.append(evidence_id)
        if evidence_id!=self.label:raise KeyError(evidence_id)
        return self.payload


class StudioRuntimeReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.stores=[]
        for name in ('harbor','garden','unset'):
            folder=self.root/name;folder.mkdir()
            store=Store(project(folder));store.put(invented(target=name),0,role='human')
            self.stores.append(store)
        config=self.root/'.local/config/local.json';config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'schema_version':2,'projects':{
            name:f'{name}/project.json' for name in ('harbor','garden','unset')}}))
        self.providers=[Provider(s,name) for s,name in zip(self.stores,('harbor','garden'))]
        self.server=StudioServer(self.stores[0],0,platform_root=self.root,progress_interval=86400,
            runtime_review_providers=[(s.manifest_path,p) for s,p in zip(self.stores,self.providers)])
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
        self.keys=[self.server.projects._key(s.manifest_path) for s in self.stores]

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,*,key=0,auth=True,headers=None,method='GET'):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'X-Studio-Project':self.keys[key]} if type(key) is int else {'X-Studio-Project':key}
        if auth:h['X-Studio-Token']=self.server.token
        h.update(headers or {})
        if method=='POST':h['Content-Length']='0'
        try:
            c.request(method,path,headers=h);r=c.getresponse()
            return r.status,r.read(),dict(r.getheaders())
        finally:c.close()

    def test_existing_auth_origin_project_boundary_precedes_provider(self):
        for route in ('/api/runtime-review','/api/runtime-review-image?evidence_id=harbor&sha256='+'a'*64):
            self.assertEqual(self.request(route,auth=False)[0],401)
            self.assertEqual(self.request(route,headers={'Origin':'https://elsewhere.invalid'})[0],403)
            self.assertEqual(self.request(route,key='not-a-project')[0],404)
        self.assertEqual(self.providers[0].calls,[])

    def test_project_providers_and_unconfigured_state_are_separate(self):
        before=[s.get('line-01') for s in self.stores]
        for i,name in enumerate(('harbor','garden')):
            status,body,headers=self.request('/api/runtime-review?offset=2&limit=10&purpose=renderer',key=i)
            value=json.loads(body);self.assertEqual(status,200)
            self.assertEqual(value['items'][0]['label'],name)
            self.assertEqual(value['project_key'],self.keys[i])
            self.assertEqual(self.providers[i].calls[-1],dict(offset=2,limit=10,purpose='renderer'))
            self.assertEqual(headers['Cache-Control'],'no-store')
            self.assertNotIn(str(self.root),body.decode())
        status,body,_=self.request('/api/runtime-review',key=2)
        self.assertEqual(status,200);self.assertFalse(json.loads(body)['available'])
        self.assertEqual([s.get('line-01') for s in self.stores],before)

    def test_bad_queries_cannot_supply_paths_callbacks_or_expand_page(self):
        for q in ('path=secret','admit_run=x','offset=-1','offset=1000001','limit=0','limit=201',
                  'limit=1&limit=2','group_id=../private','build_id=','method=human',
                  'purpose=anything','status=anything','offset=abc','after=1'):
            self.assertEqual(self.request('/api/runtime-review?'+q)[0],400,q)
        self.assertEqual(self.providers[0].calls,[])

    def test_images_require_exact_project_opaque_identity_hash_and_png(self):
        sha=hashlib.sha256(PIXEL).hexdigest()
        route='/api/runtime-review-image?evidence_id=harbor&sha256='+sha
        status,body,headers=self.request(route)
        self.assertEqual((status,body),(200,PIXEL));self.assertEqual(headers['Content-Type'],'image/png')
        self.assertEqual(self.request(route,key=1)[0],404)
        self.assertEqual(self.request(route,key=2)[0],404)
        self.assertEqual(self.request(route.replace(sha,'a'*64))[0],404)
        for q in ('evidence_id=../secret&sha256='+sha,'evidence_id=harbor','evidence_id=harbor&sha256=bad'):
            self.assertEqual(self.request('/api/runtime-review-image?'+q)[0],400)
        self.providers[0].payload=b'<svg/>'
        self.assertEqual(self.request(route.replace(sha,hashlib.sha256(b'<svg/>').hexdigest()))[0],404)

    def test_provider_errors_are_generic_and_output_is_bounded(self):
        self.providers[0].fail=True
        status,body,_=self.request('/api/runtime-review')
        self.assertEqual(status,500);self.assertNotIn(b'Private provider details',body)
        self.providers[0].fail=False;self.providers[0].label='x'*(2*1024*1024)
        self.assertEqual(self.request('/api/runtime-review')[0],400)
        self.assertIn(self.request('/api/runtime-review',method='POST')[0],(400,404))

    def test_constructor_rejects_unknown_duplicate_or_incomplete_provider(self):
        for entries in ([(self.root/'missing.json',self.providers[0])],
                        [(self.stores[0].manifest_path,self.providers[0])]*2,
                        [(self.stores[0].manifest_path,object())]):
            with self.assertRaises(ValueError):
                StudioServer(self.stores[0],0,platform_root=self.root,runtime_review_providers=entries)

    def test_launcher_entrypoint_serves_selected_provider_through_real_http(self):
        ready=threading.Event();captured={};errors=[]

        class ObservedServer(StudioServer):
            def serve_forever(server, *args, **kwargs):
                captured['server']=server;ready.set()
                return super().serve_forever(*args, **kwargs)

        def launch():
            try:
                serve(self.stores[0].manifest_path,0,platform_root=self.root,
                    progress_interval=86400,runtime_review_providers=[
                        (self.stores[0].manifest_path,self.providers[0])])
            except BaseException as error:
                errors.append(error);ready.set()

        with mock.patch('patchquest.studio.StudioServer',ObservedServer),redirect_stdout(io.StringIO()):
            thread=threading.Thread(target=launch,daemon=True);thread.start()
            self.assertTrue(ready.wait(5),'Launcher did not become ready')
            self.assertEqual(errors,[])
            server=captured['server']
            try:
                connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    connection.request('GET','/api/runtime-review',headers={
                        'X-Studio-Token':server.token,'X-Studio-Project':self.keys[0]})
                    response=connection.getresponse();result=json.loads(response.read())
                    self.assertEqual(response.status,200)
                    self.assertTrue(result['available'])
                    self.assertEqual(result['items'][0]['label'],'harbor')
                finally:
                    connection.close()
            finally:
                server.shutdown();thread.join(5)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors,[])
        self.assertEqual(self.stores[0].get('line-01')['target'],'harbor')


if __name__=='__main__':
    unittest.main()

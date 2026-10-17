import http.client
import base64
import json
from pathlib import Path
import tempfile
import threading
import unittest

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from patchquest.state import Store
from patchquest.studio import StudioServer
from patchquest.jobs import Jobs


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(project(Path(self.temp.name)));self.store.put(invented(),0)
        self.server=StudioServer(self.store,0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,body=None,headers=None,authorized=True):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        h={'X-Studio-Token':self.server.token} if authorized else {}
        if body is not None:h['Content-Type']='application/json'
        h.update(headers or {})
        try:
            connection.request('POST' if body is not None else 'GET',path,body=json.dumps(body) if body is not None else None,headers=h)
            response=connection.getresponse();return response.status,response.read(),dict(response.getheaders())
        finally:connection.close()

    def test_loopback_token_host_origin_and_no_filesystem_browse(self):
        self.assertEqual(self.server.server_address[0],'127.0.0.1')
        self.assertEqual(self.request('/api/overview',authorized=False)[0],401)
        self.assertEqual(self.request('/api/overview',headers={'Host':'external.invalid'})[0],403)
        self.assertEqual(self.request('/api/overview',headers={'Origin':'https://external.invalid'})[0],403)
        self.assertEqual(self.request('/api/overview')[0],200)
        for path in ('/../../project.json','/project.json','/api/execute','/state.sqlite3'):
            self.assertEqual(self.request(path)[0],404)
        status,body,headers=self.request('/',authorized=False)
        self.assertEqual(status,200);self.assertNotIn('あかり'.encode(),body)
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertNotIn('Access-Control-Allow-Origin',headers)

    def test_edit_role_cas_and_agent_precedence(self):
        params={'key':'line-01','expected':1,'target':'User text'}
        self.assertEqual(self.request('/api/edit',params)[0],200)
        self.assertEqual(self.request('/api/edit',params)[0],409)
        self.assertTrue(self.store.get('line-01')['human_corrected'])
        result=self.store.put(invented(target='Other agent'),2)
        self.assertEqual(result['outcome'],'proposed')
        self.assertEqual(self.request('/api/edit',dict(params,expected=2,role='agent'))[0],400)
        self.assertEqual(self.request('/api/restore',{'key':'line-01','revision':1,'expected':2})[0],200)

    def test_snapshot_and_mutation_allowlist(self):
        for action in ('build-report','import','activity','evidence','backup','shell','agent-start','work-publish','work-resolve'):
            self.assertEqual(self.request('/api/'+action,{})[0],404)
        status,body,_=self.request('/api/snapshot',{})
        self.assertEqual(status,200)
        self.assertTrue(Path(json.loads(body)['path']).is_file())
        self.assertEqual(self.request('/api/snapshot')[0],404)
        self.assertEqual(self.request('/api/get?key=line-01&key=other')[0],400)
        self.assertEqual(self.request('/api/list?offset=oops')[0],400)

    def test_agent_read_views_require_token(self):
        for action in ('agent-context','agent-sessions','work-list'):
            self.assertEqual(self.request('/api/'+action,authorized=False)[0],401)
            self.assertEqual(self.request('/api/'+action)[0],200)

    def test_issue_updates_and_private_data_routes(self):
        data={'id':'browser-issue','title':'Wording concern','record_ids':['line-01']}
        self.assertEqual(self.request('/api/issue-put',{'data':data,'expected':0})[0],200)
        self.assertEqual(self.request('/api/issue-put',{'data':dict(data,status='closed'),'expected':1})[0],200)
        status,body,_=self.request('/api/issue-history?key=browser-issue')
        self.assertEqual(status,200);self.assertEqual(len(json.loads(body)),2)
        self.assertEqual(self.request('/api/history?key=line-01',authorized=False)[0],401)

    def test_private_images_require_token_and_integrity(self):
        path=self.store.context.root/'synthetic.png';path.write_bytes(PIXEL)
        attachment=self.store.attach(path,'Invented image',['line-01'])
        route='/media/'+attachment['digest']
        self.assertEqual(self.request(route,authorized=False)[0],401)
        status,body,headers=self.request(route)
        self.assertEqual(status,200);self.assertEqual(body,PIXEL)
        self.assertEqual(headers['Content-Type'],'image/png')
        self.assertEqual(self.request('/media/../../project.json')[0],404)
        (self.store.directory/'evidence'/attachment['digest']).write_bytes(b'corrupt')
        self.assertEqual(self.request(route)[0],404)

    def test_build_button_only_queues_supported_snapshot_jobs(self):
        params={'request_id':'browser-request-0001','mode':'full'}
        self.assertEqual(self.request('/api/build-submit',params)[0],409)
        jobs=Jobs(self.store);jobs.register('test-worker','Synthetic worker')
        self.assertEqual(self.request('/api/build-submit',params,authorized=False)[0],401)
        self.assertEqual(self.request('/api/build-submit',dict(params,command='untrusted'))[0],400)
        status,body,_=self.request('/api/build-submit',params)
        self.assertEqual(status,200);self.assertEqual(json.loads(body)['status'],'queued')
        self.assertEqual(self.request('/api/build-submit',params)[0],200)
        self.assertEqual(len(jobs.list()),1)

    def test_upload_associations_history_conflicts_and_bad_images(self):
        self.store.put_issue({'id':'issue-1','title':'Synthetic screenshot issue'},0)
        metadata={'description':'Invented pixel','issue_ids':['issue-1'],'record_ids':['line-01'],'association':'provisional'}
        payload={'base64':base64.b64encode(PIXEL).decode(),'metadata':metadata}
        self.assertEqual(self.request('/api/upload',payload,authorized=False)[0],401)
        self.assertEqual(self.request('/api/upload',dict(payload,path='outside.png'))[0],400)
        self.assertEqual(self.request('/api/upload',dict(payload,base64='not base64'))[0],400)
        self.assertEqual(self.request('/api/upload',dict(payload,base64=base64.b64encode(b'<svg/>').decode()))[0],400)
        status,body,_=self.request('/api/upload',payload);self.assertEqual(status,200)
        image=json.loads(body);digest=image['digest']
        self.assertEqual(self.store.attachments(issue_id='issue-1')[0]['digest'],digest)
        params={'digest':digest,'expected':1,'data':dict(metadata,association='confirmed',scene='Invented scene')}
        self.assertEqual(self.request('/api/attachment-update',params)[0],200)
        self.assertEqual(self.request('/api/attachment-update',params)[0],409)
        self.assertEqual(len(self.store.attachment_history(digest)),2)
        self.assertEqual(self.store.image(digest)[0],PIXEL)
        self.assertTrue(json.loads(self.request('/api/upload',payload)[1])['already_registered'])
        self.assertEqual(self.store.attachments()[0]['association'],'confirmed')
        self.assertEqual(self.request('/api/upload',dict(payload,metadata=dict(metadata,record_ids=['missing'])))[0],400)


if __name__=='__main__':unittest.main()

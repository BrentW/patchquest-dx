import http.client
import base64
import json
import csv
import io
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

    def csv_rows(self, path='/api/csv-export'):
        status, body, headers = self.request(path)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'text/csv; charset=utf-8')
        return list(csv.DictReader(io.StringIO(body.decode('utf-8-sig'), newline='')))

    def test_source_correction_preserves_translation_raw_metadata_and_snapshots(self):
        original = self.store.get('line-01')
        frozen = self.store.snapshot()
        source = 'あかりを確認しました。\n<FC> <unmapped:01>'
        params = {'key':'line-01','expected':1,'source':source}
        status, body, _ = self.request('/api/edit',params)
        self.assertEqual(status,200)
        saved = json.loads(body)['record']
        self.assertEqual(saved['source'],source)
        for field in ('target','controls','context','source_ref','build_binding','decoded','uncertainty'):
            self.assertEqual(saved[field],original[field])
        self.assertTrue(saved['human_corrected'])
        self.assertEqual(saved['provenance']['role'],'human')
        self.assertEqual(self.store.history('line-01')[-1]['payload']['source'],original['source'])
        self.assertEqual(frozen['data']['records'][0]['source'],original['source'])
        self.assertEqual(self.store.snapshot()['data']['records'][0]['source'],source)
        memories = self.store.memory(source=source)
        self.assertTrue(any(m['current'] and m['source']==source for m in memories))
        self.assertEqual(self.request('/api/edit',params)[0],409)
        proposal = self.store.put(dict(invented(),source='Agent replacement'),saved['revision'])
        self.assertEqual(proposal['outcome'],'proposed')
        self.assertEqual(self.store.get('line-01')['source'],source)
        self.assertEqual(self.request('/api/restore',{'key':'line-01','revision':1,'expected':saved['revision']})[0],200)
        self.assertEqual(self.store.get('line-01')['source'],original['source'])
        self.assertEqual(len(self.store.history('line-01')),3)

    def test_source_edit_validation_auth_and_glossary(self):
        self.store.put(dict(invented('term'),kind='glossary'),0)
        params={'key':'term','expected':1,'source':'新しいあかり','target':'New lantern'}
        self.assertEqual(self.request('/api/edit',params,authorized=False)[0],401)
        self.assertEqual(self.request('/api/edit',params,headers={'Origin':'https://external.invalid'})[0],403)
        for invalid in (None,123,[],{},'bad\x00text','x'*100001):
            self.assertEqual(self.request('/api/edit',dict(params,source=invalid))[0],400)
        for field in ('controls','source_ref','build_binding','decoded','context','role'):
            self.assertEqual(self.request('/api/edit',dict(params,**{field:'changed'}))[0],400)
        self.assertEqual(self.request('/api/edit',{'key':'term','expected':1})[0],400)
        self.assertEqual(self.store.get('term')['revision'],1)
        self.assertEqual(self.request('/api/edit',params)[0],200)
        self.assertEqual(self.store.get('term')['source'],params['source'])
        self.assertEqual(self.store.get('term')['target'],params['target'])
        self.assertEqual(self.store.get('term')['kind'],'glossary')

    def csv_import(self, rows):
        from patchquest.studio_csv import FIELDS
        output = io.StringIO(newline='')
        writer = csv.DictWriter(output, FIELDS)
        writer.writeheader(); writer.writerows(rows)
        return self.request('/api/csv-import', {'csv': output.getvalue()})

    def test_csv_export_all_pages_filters_and_auth(self):
        for i in range(205):
            self.store.put(dict(invented(key=f'bulk-{i:03}',target=''),scene='Invented scene'),0)
        rows = self.csv_rows('/api/csv-export?scene=Invented%20scene&status=untranslated')
        self.assertEqual(len(rows),205)
        self.assertTrue(all(r['id'].startswith('bulk-') for r in rows))
        self.assertEqual(self.csv_rows('/api/csv-export?query=missing'),[])
        self.assertEqual(self.request('/api/csv-export',authorized=False)[0],401)
        self.assertEqual(self.request('/api/csv-import',{'csv':''},authorized=False)[0],401)
        self.assertEqual(self.request('/api/csv-export?limit=1')[0],400)

    def test_csv_export_matches_combined_page_filters(self):
        from urllib.parse import urlencode
        filters = {'kind':'translation', 'query':'lantern', 'scene':'Invented harbor',
                   'speaker':'Invented guide', 'category':'dialogue', 'status':'translated'}
        # Each decoy fails one active filter, so ignoring any filter changes the download.
        for field, value in [('kind','glossary'), ('target','A different message.'),
                             ('scene','Invented hill'), ('speaker','Invented visitor'),
                             ('category','menu'), ('target','')]:
            record = invented(key=f'decoy-{field}-{value}')
            record[field] = value
            self.store.put(record,0)
        query = urlencode(filters)
        listed = json.loads(self.request('/api/list?' + query)[1])
        exported = self.csv_rows('/api/csv-export?' + query)
        self.assertEqual([r['id'] for r in exported], ['line-01'])
        self.assertEqual([r['id'] for r in exported], [r['id'] for r in listed['items']])
        glossary = self.csv_rows('/api/csv-export?kind=glossary')
        self.assertEqual([r['id'] for r in glossary], ['decoy-kind-glossary'])

    def test_csv_unicode_newlines_and_human_history(self):
        rows = self.csv_rows()
        original = self.store.get('line-01')
        self.assertEqual(json.loads(self.csv_import(rows)[1]),{'saved':0,'unchanged':1})
        self.assertEqual(self.store.get('line-01'),original)
        rows[0]['target'] = 'A comma, a "quote"\r\n日本語\n=literal'
        self.assertEqual(json.loads(self.csv_import(rows)[1])['saved'],1)
        saved = self.store.get('line-01')
        self.assertEqual(saved['target'],rows[0]['target'])
        self.assertTrue(saved['human_corrected'])
        self.assertEqual(saved['source'],original['source'])
        self.assertEqual(saved['provenance']['role'],'human')
        self.assertEqual(self.csv_rows()[0]['target'],rows[0]['target'])
        rows = self.csv_rows(); rows[0]['target']=''
        self.assertEqual(self.csv_import(rows)[0],200)
        self.assertEqual(self.store.get('line-01')['target'],'')

    def test_csv_rejects_entire_batch_on_conflict_or_invalid_row(self):
        self.store.put(invented(key='line-02'),0)
        rows = self.csv_rows()
        for row in rows: row['target']='Bulk edit'
        self.request('/api/edit',{'key':'line-02','expected':1,'target':'New correction'})
        self.assertEqual(self.csv_import(rows)[0],409)
        self.assertEqual(self.store.get('line-01')['revision'],1)
        self.assertEqual(self.store.get('line-02')['target'],'New correction')
        rows = self.csv_rows()
        for row in rows: row['target']='Bulk edit'
        for field,value in [('id','unknown'),('revision','oops'),('project_id','other-project')]:
            invalid=[dict(r) for r in rows]; invalid[1][field]=value
            self.assertEqual(self.csv_import(invalid)[0],400)
            self.assertEqual(self.store.get('line-01')['revision'],1)
        self.assertEqual(self.csv_import([rows[0],rows[0]])[0],400)
        self.assertEqual(self.store.get('line-01')['revision'],1)
        self.assertEqual(self.request('/api/csv-import',{'csv':'id,target\nx,y'})[0],400)

    def test_snapshot_and_mutation_allowlist(self):
        for action in ('build-report','import','activity','evidence','backup','shell','agent-start','work-publish','work-resolve'):
            self.assertEqual(self.request('/api/'+action,{})[0],404)
        status,body,_=self.request('/api/snapshot',{})
        self.assertEqual(status,200)
        self.assertTrue(Path(json.loads(body)['path']).is_file())
        self.assertEqual(self.request('/api/snapshot')[0],404)
        self.assertEqual(self.request('/api/get?key=line-01&key=other')[0],400)
        self.assertEqual(self.request('/api/list?offset=oops')[0],400)

    def test_layout_report_matches_frozen_revision_and_retains_human_correction(self):
        self.request('/api/edit',{'key':'line-01','expected':1,'target':'A carefully corrected sentence.'})
        frozen=self.store.snapshot()['sha256']
        report={'id':'synthetic-layout','status':'validated','snapshot':frozen,
                'validation':{'layout':{'schema':1,'counts':{'paginated':1},'records':{
                    'line-01':{'revision':2,'variants':{'invented-small-panel':{
                        'decision':'paginated','pages':2,'lines':2,'width_px':72,'limit_px':80}}}}}}}
        self.store.build(report,0)
        status,body,_=self.request('/api/layout-reports?key=line-01')
        rows=json.loads(body)
        self.assertEqual(status,200);self.assertTrue(rows[0]['current'])
        self.assertEqual(rows[0]['variants']['invented-small-panel']['decision'],'paginated')
        self.assertEqual(self.request('/api/layout-reports?key=line-01',authorized=False)[0],401)
        self.request('/api/edit',{'key':'line-01','expected':2,'target':'A newer human correction.'})
        rows=json.loads(self.request('/api/layout-reports?key=line-01')[1])
        self.assertFalse(rows[0]['current'])
        self.assertEqual(self.store.get('line-01')['target'],'A newer human correction.')
        self.assertTrue(self.store.get('line-01')['human_corrected'])
        report['validation']['layout']['records']['line-01']['revision']=3
        self.store.build(report,1)
        self.assertEqual(json.loads(self.request('/api/layout-reports?key=line-01')[1]),[])

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

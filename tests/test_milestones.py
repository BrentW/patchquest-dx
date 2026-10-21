"""Invented editorial updates only; no game content or real publication."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, invented
from patchquest import milestones as m
from patchquest.state import Store, Conflict
from patchquest.state_api import execute
from patchquest.studio import StudioServer


def content(**changes):
    return dict(dict(date='2026-01-02', title='Invented menu review',
                     summary='The invented menus now have consistent spacing.', category='testing',
                     verification_basis='static', limitations='Runtime navigation remains untested.'), **changes)


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(project(self.root))
        self.store.put(invented(), 0, role='human')
        self.before = self.store.get('line-01')
        self.snapshot = self.store.snapshot()['sha256']

    def tearDown(self):
        self.assertEqual(self.store.get('line-01'), self.before)
        self.assertEqual(self.store.snapshot()['sha256'], self.snapshot)

    def draft(self, **changes):
        return m.put(self.store, content(**changes), 0, private_notes='PRIVATE NOTE SENTINEL')

    def select(self, item):
        reviewed = m.review(self.store, item['id'], item['revision'], item['content_sha256'], actor='PRIVATE REVIEWER')
        return m.select(self.store, item['id'], reviewed['revision'], True)

    def test_explicit_review_and_selection_allowlist(self):
        a = self.draft()
        self.assertEqual(m.preview(self.store)['items'], [])
        with self.assertRaises(Conflict): m.select(self.store, a['id'], 1, True)
        selected = self.select(a)
        self.draft(title='PRIVATE UNSELECTED DRAFT')
        self.store.activity('PRIVATE ACTIVITY SENTINEL', actor='PRIVATE ACTOR')
        result = m.preview(self.store)
        self.assertEqual(set(result), {'schema_version','report_type','selection_revision',
                                      'publication_approved','release_approved','items'})
        self.assertEqual(set(result['items'][0]), set(m.FIELDS)|{'id','revision','content_sha256'})
        self.assertEqual(result['items'][0]['revision'], selected['revision'])
        self.assertEqual(result['items'][0]['summary'], a['content']['summary'])
        self.assertNotIn('PRIVATE', json.dumps(result))
        self.assertNotIn('invented-demo', json.dumps(result))
        self.assertFalse(result['release_approved']); self.assertFalse(result['publication_approved'])

    def test_edits_invalidate_review_and_selection_history_retained(self):
        a = self.select(self.draft())
        revised = m.put(self.store, content(summary='A revised invented summary.'), a['revision'], key=a['id'])
        self.assertIsNone(revised['review']); self.assertFalse(revised['selected'])
        self.assertEqual(m.preview(self.store)['items'], [])
        with self.assertRaises(Conflict): m.review(self.store, a['id'], revised['revision'], a['content_sha256'])
        self.assertEqual(len(m.history(self.store)), 4)
        self.assertEqual(m.history(self.store)[0]['payload']['item']['content'], content())
        first = m.history(self.store, limit=1)[0]
        self.assertEqual(len(m.history(self.store, after=first['seq'])), 3)
        self.assertEqual(m.read(Store(self.store.manifest_path)), m.read(self.store))

    def test_notes_only_edit_also_invalidates_review(self):
        a = self.select(self.draft())
        a = m.put(self.store, a['content'], a['revision'], key=a['id'], private_notes='Updated private evidence')
        self.assertIsNone(a['review']); self.assertFalse(a['selected'])

    def test_stale_writes_and_exports_rejected(self):
        a = self.draft()
        with self.assertRaises(Conflict): m.put(self.store, content(), 0, key=a['id'])
        with self.assertRaises(Conflict): m.review(self.store, a['id'], 1, 'incorrect digest')
        old = m.preview(self.store)['selection_revision']
        a = self.select(a)
        with self.assertRaises(Conflict): m.export(self.store, old, 'stale.json')
        self.assertFalse((self.root/'output/stale.json').exists())
        with self.assertRaises(Conflict): m.select(self.store, a['id'], 1, False)

    def test_racing_edits_have_one_winner(self):
        a = self.draft()
        def edit(index):
            try: return m.put(self.store, content(title='Invented '+str(index)), 1, key=a['id'])
            except Conflict: return None
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(edit, [1,2]))
        self.assertEqual(sum(r is not None for r in results), 1)

    def test_independent_edits_do_not_conflict(self):
        items = [self.draft(title='First invented update'), self.draft(title='Second invented update')]
        def edit(item): return m.put(self.store, item['content'], 1, key=item['id'])
        with ThreadPoolExecutor(2) as pool: results = list(pool.map(edit, items))
        self.assertEqual([r['revision'] for r in results], [2,2])

    def test_export_complete_immutable_and_retraction_is_explicit(self):
        a = self.select(self.draft())
        preview = m.preview(self.store)
        result = m.export(self.store, preview['selection_revision'], 'summaries/one.json')
        path = Path(result['path']); data = path.read_bytes()
        self.assertEqual(hashlib.sha256(data).hexdigest(), result['sha256'])
        self.assertEqual(json.loads(data), preview)
        self.assertEqual(path.stat().st_nlink, 1)
        self.assertEqual(list(path.parent.glob('.editorial-*')), [])
        with self.assertRaises(FileExistsError): m.export(self.store, preview['selection_revision'], 'summaries/one.json')
        m.select(self.store, a['id'], a['revision'], False)
        empty = m.preview(self.store)
        result = m.export(self.store, empty['selection_revision'], 'summaries/empty.json')
        self.assertEqual(json.loads(Path(result['path']).read_bytes())['items'], [])
        self.assertEqual(path.read_bytes(), data)  # Retained history is not silently rewritten.

    def test_export_failure_and_boundaries(self):
        self.select(self.draft()); revision = m.read(self.store)['revision']
        for destination in ['../project.json', str(self.root/'outside.json'), '']:
            with self.assertRaises(ValueError): m.export(self.store, revision, destination)
        with patch('patchquest.editorial_exports.os.link', side_effect=OSError('unsupported')):
            with self.assertRaises(OSError): m.export(self.store, revision, 'failure.json')
        self.assertFalse((self.root/'output/failure.json').exists())
        self.assertEqual(list((self.root/'output').glob('.editorial-*')), [])
        self.assertEqual(m.read(self.store)['revision'], revision)
        self.assertFalse(any(r['kind']=='milestone.exported' for r in m.history(self.store)))

    def test_existing_hardlink_protected(self):
        self.select(self.draft()); revision = m.read(self.store)['revision']
        output=self.root/'output'; output.mkdir()
        protected=self.root/'protected.fixture'; protected.write_bytes(b'preserve')
        os.link(protected,output/'linked.json')
        with self.assertRaises(FileExistsError): m.export(self.store,revision,'linked.json')
        self.assertEqual(protected.read_bytes(),b'preserve')

    def test_export_holds_selection_snapshot_against_concurrent_edit(self):
        a=self.select(self.draft()); revision=m.read(self.store)['revision']
        exporting=threading.Event(); proceed=threading.Event(); editing=threading.Event()
        link=os.link
        def blocked_link(source,target):
            exporting.set()
            if not proceed.wait(5): raise TimeoutError('Test synchronization failed')
            return link(source,target)
        def edit():
            editing.set()
            return m.put(self.store,content(summary='Later wording.'),a['revision'],key=a['id'])
        with ThreadPoolExecutor(2) as pool, patch('patchquest.editorial_exports.os.link',side_effect=blocked_link):
            exported=pool.submit(m.export,self.store,revision,'locked.json')
            try:
                self.assertTrue(exporting.wait(5))
                changed=pool.submit(edit)
                self.assertTrue(editing.wait(5));self.assertFalse(changed.done())
            finally: proceed.set()
            result=exported.result(timeout=10);changed.result(timeout=10)
        self.assertEqual(json.loads(Path(result['path']).read_bytes())['items'][0]['summary'],a['content']['summary'])
        self.assertEqual(m.preview(self.store)['items'],[])

    def test_project_isolation(self):
        self.select(self.draft())
        other=self.root/'other';other.mkdir()
        separate=Store(project(other))
        self.assertEqual(m.read(separate)['items'],[])
        self.assertEqual(m.preview(separate)['selection_revision'],0)
        self.assertEqual(m.history(separate),[])

    def test_schema_limits_and_missing_items(self):
        for data in [dict(content(),logs=['private']),content(title=' '),content(summary='x'*2001),
                     content(date='2026-02-30'),content(date='20260102'),content(verification_basis='approved'),
                     content(category='raw_logs'),content(summary='bad\x01text')]:
            with self.assertRaises(ValueError): m.put(self.store,data,0)
        with self.assertRaises(Conflict): m.put(self.store,content(),True)
        with self.assertRaises(KeyError): m.review(self.store,'absent',0,'absent')
        a=self.draft()
        with self.assertRaises(ValueError): m.select(self.store,a['id'],1,'true')
        with self.assertRaises(ValueError): m.history(self.store,limit=0)

    def test_cli_and_discovery(self):
        a=self.draft()
        r=subprocess.run([sys.executable,'-B',str(ROOT/'tools/patchquest.py'),'state',
                          str(self.store.manifest_path),'milestone-preview'],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['items'],[])
        self.assertIn('milestone-updates.md',[Path(i['path']).name for i in execute(self.store,'agent-context')['instructions']])
        self.assertEqual(execute(self.store,'milestones')['items'][0]['id'],a['id'])

    def test_http_scoped_actions_and_provenance(self):
        server=StudioServer(self.store,0,platform_root=self.root)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def request(action,data=None,token=None):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST' if data is not None else 'GET','/api/'+action,
                         body=json.dumps(data) if data is not None else None,
                         headers={'X-Studio-Token':server.token if token is None else token,'Content-Type':'application/json'})
            r=conn.getresponse(); body=json.loads(r.read());conn.close();return r.status,body
        try:
            self.assertEqual(request('milestones',token='wrong')[0],401)
            self.assertEqual(request('milestone-put',dict(data=content(),expected=0,actor='impersonated'))[0],400)
            status,a=request('milestone-put',dict(data=content(),expected=0,private_notes='PRIVATE HTTP'))
            self.assertEqual(status,200)
            status,a=request('milestone-review',dict(key=a['id'],expected=a['revision'],content_sha256=a['content_sha256']))
            self.assertEqual(status,200);self.assertEqual(a['review']['actor'],'Studio user')
            status,a=request('milestone-select',dict(key=a['id'],expected=a['revision'],selected=True))
            self.assertEqual(status,200)
            self.assertEqual(request('milestone-export',dict(expected=a['board_revision'],destination='../escape'))[0],400)
            status,result=request('milestone-export',dict(expected=a['board_revision']))
            self.assertEqual(status,200)
            self.assertNotIn('PRIVATE',Path(result['path']).read_text())
            self.assertEqual(request('milestone-select',dict(key=a['id'],expected=1,selected=False))[0],409)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__': unittest.main()

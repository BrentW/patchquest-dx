"""Invented projects with colliding record IDs; no real ROMs or registry needed."""
import base64
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor

from _bootstrap import ROOT
from test_state import project, invented, PIXEL
from patchquest.state import Store
from patchquest.jobs import Jobs
from patchquest.studio import StudioServer
from patchquest.studio_projects import ProjectDirectory


class ProjectSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stores = []
        for name in ('harbor', 'garden'):
            folder = self.root / name
            folder.mkdir()
            store = Store(project(folder))
            store.put(invented(target=name), 0)
            self.stores.append(store)
        pending = self.root / 'pending'
        pending.mkdir()
        project(pending)  # A manifest alone must not create a state database.
        registry = self.root / '.local/config/local.json'
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'schema_version': 2, 'projects': {
            'harbor': 'harbor/project.json', 'garden': 'garden/project.json',
            'uninitialized': 'pending/project.json', 'missing': 'missing/project.json'}}))
        self.server = StudioServer(self.stores[0], 0, platform_root=self.root)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.keys = [self.server.projects._key(s.manifest_path) for s in self.stores]

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, route, key=None, body=None, authorized=True, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        h = {'X-Studio-Token': self.server.token} if authorized else {}
        if key is not None:
            h['X-Studio-Project'] = key
        if body is not None:
            h['Content-Type'] = 'application/json'
        h.update(headers or {})
        try:
            connection.request('POST' if body is not None else 'GET', route,
                               json.dumps(body) if body is not None else None, h)
            r = connection.getresponse()
            return r.status, r.read()
        finally:
            connection.close()

    def test_catalogue_is_authenticated_explicit_and_does_not_initialize(self):
        self.assertEqual(self.request('/api/projects', authorized=False)[0], 401)
        self.assertEqual(self.request('/api/projects', headers={'Origin': 'https://elsewhere.invalid'})[0], 403)
        status, body = self.request('/api/projects')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(len(data['projects']), 4)  # Default registry alias is deduplicated.
        self.assertEqual(sum(p['available'] for p in data['projects']), 2)
        self.assertNotIn(str(self.root), body.decode())
        self.assertFalse((self.root / 'pending/.patchquest').exists())
        unavailable = next(p for p in data['projects'] if p['title'] == 'uninitialized')
        self.assertEqual(self.request('/api/overview', unavailable['id'])[0], 404)
        self.assertFalse((self.root / 'pending/.patchquest').exists())
        single = ProjectDirectory(self.stores[0])
        self.assertEqual(len(single.catalogue()['projects']), 1)
        self.assertEqual(self.request('/?project=' + self.keys[1])[0], 200)

    def test_concurrent_tabs_and_colliding_ids_remain_isolated(self):
        def read(index):
            status, data = self.request('/api/get?key=line-01', self.keys[index % 2])
            self.assertEqual(status, 200)
            return json.loads(data)['target']
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(list(pool.map(read, range(24))), ['harbor', 'garden'] * 12)
        p = {'key': 'line-01', 'expected': 1, 'target': 'Garden correction'}
        self.assertEqual(self.request('/api/edit', self.keys[1], p)[0], 200)
        self.assertEqual(self.request('/api/edit', self.keys[1], p)[0], 409)
        self.assertTrue(self.stores[1].get('line-01')['human_corrected'])
        self.assertEqual(self.stores[0].get('line-01')['target'], 'harbor')
        self.assertFalse(self.stores[0].get('line-01')['human_corrected'])
        self.assertEqual(json.loads(self.request('/api/get?key=line-01')[1])['target'], 'harbor')
        snapshot = json.loads(self.request('/api/snapshot', self.keys[1], {})[1])
        self.assertEqual(snapshot['sha256'], self.stores[1].snapshot()['sha256'])
        self.assertNotEqual(snapshot['sha256'], self.stores[0].snapshot()['sha256'])

    def test_missing_or_removed_project_never_falls_back(self):
        for key in ('', '../garden/project.json', 'unregistered', 'f' * 64):
            self.assertEqual(self.request('/api/get?key=line-01', key)[0], 404)
            self.assertEqual(self.request('/api/edit', key, {'key': 'line-01', 'expected': 1, 'target': 'Wrong'})[0], 404)
        self.stores[1].path.unlink()
        self.assertEqual(self.request('/api/get?key=line-01', self.keys[1])[0], 404)
        self.assertFalse(self.stores[1].path.exists())
        self.assertEqual(self.stores[0].get('line-01')['revision'], 1)

    def test_build_workers_jobs_and_images_follow_selected_project(self):
        Jobs(self.stores[0]).register('invented-worker', 'Invented worker')
        self.assertTrue(json.loads(self.request('/api/capabilities', self.keys[0])[1])['available'])
        self.assertFalse(json.loads(self.request('/api/capabilities', self.keys[1])[1])['available'])
        payload = {'request_id': 'synthetic-selection-1'}
        self.assertEqual(self.request('/api/build-submit', self.keys[1], payload)[0], 409)
        self.assertEqual(self.request('/api/build-submit', self.keys[0], payload)[0], 200)
        self.assertEqual(json.loads(self.request('/api/jobs', self.keys[1])[1]), [])
        self.assertEqual(len(json.loads(self.request('/api/jobs', self.keys[0])[1])), 1)
        metadata = {'description': 'Invented garden image', 'record_ids': ['line-01']}
        status, body = self.request('/api/upload', self.keys[1], {'base64': base64.b64encode(PIXEL).decode(), 'metadata': metadata})
        self.assertEqual(status, 200)
        route = '/media/' + json.loads(body)['digest']
        self.assertEqual(self.request(route, self.keys[1]), (200, PIXEL))
        self.assertEqual(self.request(route, self.keys[0])[0], 404)
        self.assertEqual(self.request(route, self.keys[1], authorized=False)[0], 401)


if __name__ == '__main__':
    unittest.main()

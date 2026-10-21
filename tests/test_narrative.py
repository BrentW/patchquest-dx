"""Independent invented narrative examples; no private project or provider calls."""
import copy
import http.client
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from _bootstrap import ROOT
from patchquest.narrative import digest
from patchquest.state import Store
from patchquest.state_api import execute, READ_ACTIONS, WRITE_ACTIONS
from patchquest.studio import StudioServer
from test_state import project, invented


class NarrativeContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.manifest = project(self.root)
        self.store = Store(self.manifest)
        self.data = json.loads((ROOT/'templates/project/narrative.example.json').read_text(encoding='utf8'))
        self.data['source_sha256'] = self.store.context.manifest['source']['sha256']
        for key in ('shop-greeting', 'storm-warning', 'unassociated'):
            self.store.put(invented(key), 0)

    def install(self, data=None, name='context-v001.json'):
        path = self.root/name
        path.write_bytes((json.dumps(self.data if data is None else data, ensure_ascii=False)+'\n').encode('utf8'))
        manifest = json.loads(self.manifest.read_text(encoding='utf8'))
        manifest['resources']['narrative_context'] = name
        self.manifest.write_text(json.dumps(manifest), encoding='utf8')
        return path

    def test_optional_discovery_and_live_manifest_refresh(self):
        self.assertEqual(execute(self.store, 'agent-context')['narrative_context']['status'], 'not_configured')
        self.assertEqual(execute(self.store, 'narrative-context'), {'status':'not_configured'})
        path = self.install()
        packet = execute(self.store, 'agent-context')['narrative_context']
        self.assertEqual(packet['status'], 'available')
        self.assertEqual(packet['sha256'], digest(path.read_bytes()))
        self.assertIn('narrative-context', READ_ACTIONS)
        self.assertNotIn('narrative-context', WRITE_ACTIONS)
        # Both clients reopen the exact advertised manifest and get one guide.
        second = Store(execute(self.store, 'agent-context')['project_manifest'])
        self.assertEqual(execute(self.store, 'narrative-context'), execute(second, 'narrative-context'))

    def test_explicit_scope_keeps_contrast_and_unknowns_without_speaker_guessing(self):
        self.install()
        scoped = execute(self.store, 'narrative-context', {'record_id':'storm-warning'})
        self.assertEqual([c['id'] for c in scoped['characters']], ['clockmaker'])
        self.assertEqual([s['id'] for s in scoped['scenes']], ['storm'])
        self.assertEqual(scoped['scenes'][0]['claims'][1]['kind'], 'unknown')
        # The state's synthetic speaker name must not manufacture an association.
        unrelated = execute(self.store, 'narrative-context', {'record_id':'unassociated'})
        self.assertEqual(unrelated['characters'], [])
        self.assertEqual(unrelated['scenes'], [])
        self.assertEqual(unrelated['work'], self.data['work'])

    def test_reviews_are_revision_bound_and_do_not_mutate_protected_corrections(self):
        row = self.store.get('storm-warning')
        human = {k:v for k,v in row.items() if k not in ('revision','human_corrected','provenance')}
        human['target'] = 'Stay here. It is not safe outside.'
        self.store.put(human, row['revision'], 'human', 'Synthetic reviewer')
        row = self.store.get(row['id'])
        self.data['reviews'] = [dict(record_id=row['id'], revision=row['revision'], source_sha256=digest(row['source'].encode()),
            target_sha256=digest(row['target'].encode()), finding='Keep the warning serious.', recommendation='Retain protected wording.',
            disposition='retain', evidence=['invented-storm'])]
        self.install(); before = self.store.snapshot()['sha256']
        review = execute(self.store, 'narrative-context')['reviews'][0]
        self.assertTrue(review['current']); self.assertTrue(review['human_corrected'])
        self.assertEqual(self.store.snapshot()['sha256'], before)
        human['target'] = 'Stay indoors. The bridge is unsafe.'
        self.store.put(human, row['revision'], 'human', 'Synthetic reviewer')
        self.assertFalse(execute(self.store, 'narrative-context')['reviews'][0]['current'])
        proposal = self.store.put(dict(human, target='A proposed alternative.'), row['revision']+1, 'agent', 'Synthetic agent')
        self.assertEqual(proposal['outcome'], 'proposed')
        self.assertEqual(self.store.get(row['id'])['target'], human['target'])

    def test_content_hash_detects_same_revision_text_drift(self):
        row = self.store.get('storm-warning')
        self.data['reviews'] = [dict(record_id=row['id'], revision=row['revision'], source_sha256=digest(b'different source'),
            target_sha256=digest(row['target'].encode()), finding='Synthetic stale finding.', recommendation='Reread.',
            disposition='uncertain', evidence=['invented-storm'])]
        self.install(); self.assertFalse(execute(self.store, 'narrative-context')['reviews'][0]['current'])

    def test_revisions_pin_predecessor_and_reject_stale_context(self):
        old = self.install(); pin = digest(old.read_bytes())
        newer = copy.deepcopy(self.data); newer['revision'] = 2
        newer['previous'] = {'path':old.name,'sha256':pin}
        self.install(newer, 'context-v002.json')
        self.assertEqual(execute(self.store, 'narrative-context')['revision'], 2)
        with self.assertRaises(ValueError):execute(self.store, 'narrative-context', {'expected_sha256':pin})
        old.write_bytes(old.read_bytes()+b' ')
        with self.assertRaises(ValueError):execute(self.store, 'narrative-context')
        self.assertEqual(execute(self.store, 'agent-context')['narrative_context']['status'], 'invalid')

    def test_malformed_claim_links_source_and_revision_fail_closed(self):
        for change in ('source', 'evidence', 'duplicate', 'claim', 'revision', 'character'):
            with self.subTest(change=change):
                data = copy.deepcopy(self.data)
                if change == 'source':data['source_sha256'] = 'f'*64
                elif change == 'evidence':data['work']['claims'][0]['evidence'] = ['missing']
                elif change == 'duplicate':data['evidence'].append(data['evidence'][0])
                elif change == 'claim':data['work']['claims'][0]['evidence'] = []
                elif change == 'revision':data['revision'] = True
                else:data['scenes'][0]['character_ids'] = ['missing']
                self.install(data)
                with self.assertRaises(ValueError):execute(self.store, 'narrative-context')

    def test_resource_and_evidence_path_escape_rejected(self):
        self.install()
        manifest = json.loads(self.manifest.read_text(encoding='utf8'))
        manifest['resources']['narrative_context'] = '../outside.json'
        self.manifest.write_text(json.dumps(manifest), encoding='utf8')
        with self.assertRaises(ValueError):execute(self.store, 'narrative-context')
        self.data['evidence'][0]['reference'] = '../outside.txt'; self.install()
        with self.assertRaises(ValueError):execute(self.store, 'narrative-context')

    def test_missing_or_oversized_resource_is_not_silently_empty(self):
        path = self.install(); path.unlink()
        with self.assertRaises(OSError):execute(self.store, 'narrative-context')
        path.write_bytes(b' '*(1024*1024+1))
        with self.assertRaises(ValueError):execute(self.store, 'narrative-context')

    def test_cli_runs_without_rom_or_provider_and_keeps_snapshot(self):
        self.install(); before = self.store.snapshot()['sha256']
        params = self.root/'query.json'; params.write_text(json.dumps({'record_id':'storm-warning'}), encoding='utf8')
        run = subprocess.run([sys.executable, '-B', str(ROOT/'tools/patchquest.py'), 'state', str(self.manifest),
                              'narrative-context', '--input', str(params)], capture_output=True, text=True, encoding='utf8')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['scenes'][0]['id'], 'storm')
        self.assertEqual(before, self.store.snapshot()['sha256'])

    def test_authenticated_http_shares_read_only_context(self):
        self.install(); before = self.store.snapshot()['sha256']
        server = StudioServer(self.store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        def request(path, token=True, method='GET'):
            connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
            headers = {'X-Studio-Token':server.token} if token else {}
            if method == 'POST':headers['Content-Type'] = 'application/json'
            try:
                connection.request(method, path, '{}' if method == 'POST' else None, headers)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()
        try:
            self.assertEqual(request('/api/narrative-context', token=False)[0], 401)
            status, packet = request('/api/agent-context')
            self.assertEqual(status, 200)
            pin = packet['narrative_context']['sha256']
            status, actual = request('/api/narrative-context?record_id=storm-warning&expected_sha256='+pin)
            self.assertEqual(status, 200)
            self.assertEqual(actual, execute(self.store, 'narrative-context', {'record_id':'storm-warning'}))
            self.assertEqual(request('/api/narrative-context?expected_sha256='+'0'*64)[0], 400)
            self.assertEqual(request('/api/narrative-context', method='POST')[0], 404)
            self.assertEqual(before, self.store.snapshot()['sha256'])
        finally:
            server.shutdown(); server.server_close(); thread.join()


if __name__ == '__main__':
    unittest.main()

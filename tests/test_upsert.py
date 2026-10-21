"""Independent synthetic records only; no private projects or ROMs are read."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from _bootstrap import ROOT
from patchquest.collaboration import Coordination
from patchquest.state import Conflict, Store
from patchquest.state_api import execute
from test_state import project


def create(key='harbor.sign.welcome'):
    return {'expected': 0, 'data': {'id': key, 'source': 'Welcome, traveler.',
            'target': 'Welcome, traveler.', 'decoded': True, 'scene': 'Invented harbor',
            'controls': ['<wait>'], 'context': {'synthetic': True},
            'source_ref': {'identity': 'independently authored sign'},
            'build_binding': {'adapter': 'synthetic-only'}}}


def update(key='harbor.sign.welcome', expected=1, target='Welcome to the harbor.'):
    return {'expected': expected, 'data': {'id': key, 'target': target}}


class UpsertTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.manifest = project(Path(self.temp.name))
        self.store = Store(self.manifest)

    def apply(self, changes, **kw):
        return self.store.upsert('invented-demo', changes, dry_run=False, **kw)

    def test_create_update_and_replay_are_idempotent(self):
        packet = [create()]
        self.assertEqual(self.apply(packet)['results'][0]['outcome'], 'created')
        cursor = self.store.overview()['cursor']
        self.assertEqual(self.apply(packet)['results'][0]['outcome'], 'unchanged')
        self.assertEqual(self.store.overview()['cursor'], cursor)
        self.assertEqual(self.apply([update()])['results'][0]['revision'], 2)
        cursor = self.store.overview()['cursor']
        self.assertEqual(self.apply([update()])['results'][0]['outcome'], 'unchanged')
        self.assertEqual(self.store.overview()['cursor'], cursor)
        self.assertEqual(len(self.store.history('harbor.sign.welcome')), 2)
        with self.assertRaises(Conflict):
            self.apply(packet)  # Old create cannot replace an updated target.

    def test_preview_is_default_and_preserves_state(self):
        result = self.store.upsert('invented-demo', [create()])
        self.assertTrue(result['dry_run'])
        self.assertEqual(result['results'][0]['outcome'], 'created')
        self.assertEqual(self.store.list()['total'], 0)
        self.apply([create()])
        before = self.store.overview()['cursor']
        self.store.upsert('invented-demo', [update()])
        self.assertEqual(self.store.overview()['cursor'], before)

    def test_stable_ids_survive_reordering_and_target_changes(self):
        self.apply([create('sign.north'), create('sign.south')])
        self.apply([update('sign.south'), update('sign.north')])
        self.assertEqual({r['id'] for r in self.store.list()['items']}, {'sign.north', 'sign.south'})
        self.assertEqual(self.store.list()['total'], 2)

    def test_human_corrections_become_one_inactive_proposal(self):
        self.apply([create()])
        human = dict(create()['data'], target='A warm welcome to our harbor.')
        self.store.put(human, 1, role='human', actor='synthetic reviewer')
        before = self.store.get(human['id'])
        proposal = [update(expected=2)]
        self.assertEqual(self.apply(proposal)['results'][0]['outcome'], 'proposed')
        cursor = self.store.overview()['cursor']
        self.assertEqual(self.apply(proposal)['results'][0]['outcome'], 'proposal_exists')
        self.assertEqual(self.store.overview()['cursor'], cursor)
        self.assertEqual(self.store.get(human['id']), before)
        self.assertEqual(len(self.store.proposals(human['id'])), 1)
        self.assertEqual(self.store.snapshot()['data']['records'][0]['target'], human['target'])

    def test_updates_preserve_all_source_and_binding_fields(self):
        self.apply([create()])
        before = self.store.get('harbor.sign.welcome')
        self.apply([update()])
        after = self.store.get('harbor.sign.welcome')
        for field in ('source', 'controls', 'source_ref', 'build_binding', 'context', 'scene', 'decoded'):
            self.assertEqual(after[field], before[field])
        for field in ('source', 'controls', 'decoded', 'kind', 'build_binding'):
            bad = update(expected=2)
            bad['data'][field] = before[field]
            with self.assertRaises(ValueError):
                self.apply([bad])

    def test_conflict_rolls_back_records_proposals_and_events(self):
        self.apply([create()])
        human = dict(create()['data'], target='Reviewed sign.')
        self.store.put(human, 1, role='human')
        cursor = self.store.overview()['cursor']
        with self.assertRaises(Conflict):
            self.apply([update(expected=2), create('fresh.sign'), update('absent.sign')])
        self.assertEqual(self.store.list()['total'], 1)
        self.assertEqual(self.store.proposals(human['id']), [])
        self.assertEqual(self.store.overview()['cursor'], cursor)

    def test_validation_rejects_malformed_batches_atomically(self):
        cases = [[], [create(), create()], [dict(create(), expected=True)],
                 [{'data': {'id': 'missing-fields'}, 'expected': 0}],
                 [dict(create(), role='human')], [update(expected=-1)],
                 [dict(create(), data=dict(create()['data'], decoded='yes'))],
                 [dict(create(), data=dict(create()['data'], id=''))]]
        for packet in cases:
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                self.apply(packet)
        self.assertEqual(self.store.list()['total'], 0)
        with self.assertRaises(ValueError):
            self.store.upsert('another-project', [create()], dry_run=False)
        with self.assertRaises(ValueError):
            self.store.upsert('invented-demo', [create()], dry_run='false')
        self.apply([create()])
        with self.assertRaises(Conflict):
            self.apply([update(expected=50, target=create()['data']['target'])])

    def test_late_bad_target_rolls_back_earlier_create(self):
        self.apply([create()])
        with self.assertRaises(ValueError):
            self.apply([create('fresh.sign'), update(target=123)])
        with self.assertRaises(KeyError):
            self.store.get('fresh.sign')

    def test_coordinated_records_cannot_bypass_work_publish(self):
        self.apply([create()])
        work = Coordination(self.store)
        work.create(key='sign-review', title='Synthetic review', record_ids=['harbor.sign.welcome'])
        session = work.start(provider='synthetic')['session']
        work.claim(session, key='sign-review')
        with self.assertRaises(Conflict):
            self.apply([create('fresh.sign'), update()])
        self.assertEqual(self.store.list()['total'], 1)

    def test_concurrent_writers_do_not_lose_an_update(self):
        self.apply([create()])
        def write(target):
            try:
                return self.apply([update(target=target)])['results'][0]['outcome']
            except Conflict:
                return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(write, ['North gate open.', 'South gate open.']))
        self.assertCountEqual(results, ['updated', 'conflict'])
        self.assertEqual(len(self.store.history('harbor.sign.welcome')), 2)

    def test_json_action_and_cli_with_no_source_file(self):
        request = {'project_id': 'invented-demo', 'changes': [create()]}
        self.assertTrue(execute(self.store, 'upsert', request)['dry_run'])
        path = Path(self.temp.name)/'request.json'
        request['dry_run'] = False
        path.write_text(json.dumps(request), encoding='utf8')
        run = subprocess.run([sys.executable, '-B', str(ROOT/'tools/patchquest.py'),
                              'state', str(self.manifest), 'upsert', '--input', str(path)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['results'][0]['outcome'], 'created')


if __name__ == '__main__':
    unittest.main()

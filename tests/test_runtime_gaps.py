"""Independent invented coverage fixtures; no private projects or native runs."""
import copy
import hashlib
import http.client
import json
import threading
import unittest
from unittest import mock

from _bootstrap import ROOT
import test_runtime_coverage as fixtures
from patchquest.runtime_contracts import contract_digest
from patchquest import runtime_gaps as gaps
from patchquest.runtime_coverage import digest
from patchquest.runtime_review import ReviewProvider
from patchquest.state import Conflict
from patchquest.studio import StudioServer


class GapTests(unittest.TestCase):
    def setUp(self):
        self.f = fixtures.CoverageTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.store = self.f.store
        self.group = self.f.fixture()

    def result(self):
        return self.f.run_group(self.group)

    def candidate(self, result=None, kind='unexercised'):
        return next(r for r in gaps.candidates(result or self.result(), [self.group]) if r['kind'] == kind)

    def create(self, result=None, row=None, **kwargs):
        result = result or self.result()
        row = row or self.candidate(result)
        return gaps.create_issue(self.store, result, [self.group], candidate_id=row['candidate_id'],
                                 catalog_read_sha256=result['catalog_receipt']['read_sha256'], **kwargs)

    def change_record(self):
        record = self.store.get('unseen')
        fields = {k:v for k,v in record.items() if k not in ('revision', 'human_corrected', 'provenance')}
        fields['target'] = 'A new protected invented correction.'
        self.store.put(fields, record['revision'], role='human')

    def discovery(self, mode=None, *, admitted=True):
        self.f.reseal(self.group, lambda m:m.update(gaps=[dict(run_id=m['run_id'], worker='worker-1',
            case_id='invented-extra', kind='unplanned', declared_sha256=None, enumerated_sha256='b'*64)]))
        sha = hashlib.sha256(self.group['runs'][0]['manifest_bytes']).hexdigest()
        if mode:
            self.group['discovery_modes'] = {sha:dict(mode=mode, reason='Invented bounded discovery design.',
                                                    reference='Independently authored route.')}
        if not admitted:
            self.f.proofs.pop(sha)
        return sha

    def test_read_page_does_not_write_or_award_coverage(self):
        before = self.store.get('unseen'), self.store.history('unseen'), self.store.issues()
        result = self.result()
        page = gaps.page(self.store, result, [self.group])
        self.assertEqual(page['total'], 1)
        self.assertEqual(page['items'][0]['kind'], 'unexercised')
        self.assertIsNone(page['global_verified_percent'])
        self.assertFalse(page['verification_awards'])
        self.assertEqual(before, (self.store.get('unseen'), self.store.history('unseen'), self.store.issues()))

    def test_creates_only_an_issue_with_original_build_and_revisions(self):
        before = self.store.get('unseen'), self.store.history('unseen'), self.store.builds()
        saved = self.create(note='Investigate this invented lead.', actor='Invented reviewer')
        self.assertTrue(saved['created'])
        issue = saved['issue']
        self.assertEqual(issue['category'], 'runtime_gap')
        self.assertEqual(issue['record_ids'], ['unseen'])
        self.assertEqual(issue['build_id'], 'invented-build')
        self.assertIn('Investigation candidate only', issue['description'])
        self.assertEqual(before, (self.store.get('unseen'), self.store.history('unseen'), self.store.builds()))
        self.assertEqual(len(self.store.issue_history(issue['id'])), 1)

    def test_duplicate_creation_preserves_human_resolution_and_history(self):
        saved = self.create()['issue']
        update = {k:v for k,v in saved.items() if k != 'revision'}
        update.update(status='resolved', description='Human disposition retained.')
        self.store.put_issue(update, saved['revision'], actor='Invented human reviewer')
        history = self.store.issue_history(saved['id'])
        again = self.create(note='Must not replace the reviewer note.')
        self.assertFalse(again['created'])
        self.assertEqual(again['issue']['status'], 'resolved')
        self.assertEqual(again['issue']['description'], 'Human disposition retained.')
        self.assertEqual(self.store.issue_history(saved['id']), history)
        self.assertEqual(gaps.page(self.store, self.result(), [self.group])['items'][0]['issue']['status'], 'resolved')

    def test_two_simultaneous_create_requests_produce_one_history_row(self):
        result = self.result()
        barrier = threading.Barrier(2)
        values, errors = [], []
        def run():
            try:
                barrier.wait(timeout=5)
                values.append(self.create(result))
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=run) for _ in range(2)]
        for t in threads:t.start()
        for t in threads:t.join(10)
        self.assertFalse(errors)
        self.assertEqual(sorted(v['created'] for v in values), [False, True])
        self.assertEqual(len(self.store.issue_history(values[0]['issue']['id'])), 1)

    def test_stale_browser_read_is_refused_even_with_fresh_server_reconciliation(self):
        old = self.result()
        row = self.candidate(old)
        self.change_record()
        with self.assertRaises(Conflict):
            gaps.create_issue(self.store, self.result(), [self.group], candidate_id=row['candidate_id'],
                              catalog_read_sha256=old['catalog_receipt']['read_sha256'])
        self.assertFalse(self.store.issues())

    def test_catalog_change_after_reconciliation_is_refused_under_writer_lock(self):
        result = self.result()
        self.change_record()
        with self.assertRaises(Conflict):
            self.create(result)
        self.assertFalse(self.store.issues())

    def test_build_revision_change_rejects_issue_creation(self):
        result = self.result()
        build = self.store.builds()[0]
        self.store.build({k:v for k,v in build.items() if k != 'revision'}, build['revision'])
        with self.assertRaises(Conflict):
            self.create(result)
        self.assertFalse(self.store.issues())

    def test_freshness_check_occurs_inside_authoritative_write_transaction(self):
        original = self.store._put_issue
        calls = []
        def put(db, *args):
            calls.append(db.in_transaction)
            # Another cooperating writer cannot enter while issue admission
            # checks and insertion share the existing BEGIN IMMEDIATE lock.
            with self.store.connection() as other:
                other.execute('PRAGMA busy_timeout=1')
                with self.assertRaisesRegex(Exception, 'locked'):
                    other.execute('BEGIN IMMEDIATE')
            return original(db, *args)
        with mock.patch.object(self.store, '_put_issue', side_effect=put):
            self.create()
        self.assertEqual(calls, [True])

    def test_failed_insert_rolls_back_without_catalog_or_issue_changes(self):
        before = self.store.get('unseen')
        original = self.store._put_issue
        def fail(db, *args):
            original(db, *args)
            raise ValueError('Invented late failure')
        with mock.patch.object(self.store, '_put_issue', side_effect=fail), self.assertRaises(ValueError):
            self.create()
        self.assertFalse(self.store.issues())
        self.assertEqual(self.store.get('unseen'), before)

    def test_stale_historical_candidate_keeps_old_and_current_revisions(self):
        old_id = self.candidate()['candidate_id']
        self.change_record()
        result = self.result()
        row = self.candidate(result)
        self.assertEqual(row['candidate_id'], old_id)
        self.assertEqual(row['freshness'], 'stale')
        issue = self.create(result, row)['issue']
        self.assertIn('"tested":{"unseen":1}', issue['description'])
        self.assertIn('"current":{"unseen":2}', issue['description'])
        self.assertTrue(self.store.get('unseen')['human_corrected'])

    def test_unknown_candidate_and_untrusted_browser_fields_are_rejected(self):
        with self.assertRaises(ValueError):
            self.create(row={'candidate_id':'f'*64})
        provider = ReviewProvider(self.store, [self.group], admit_run=self.f.proofs.get, artifacts=self.f)
        for extra in ('path', 'source', 'groups', 'admit_run', 'target'):
            with self.assertRaises(ValueError):
                provider.gap_issue(self.store, dict(candidate_id='a'*64, catalog_read_sha256='b'*64, **{extra:'x'}))
        self.assertFalse(self.store.issues())

    def test_filters_paginate_and_reject_extra_input(self):
        result = self.result()
        self.assertEqual(gaps.page(self.store, result, [self.group], {'offset':1})['items'], [])
        self.assertEqual(gaps.page(self.store, result, [self.group], {'kind':'uncatalogued'})['total'], 0)
        for p in ({'limit':101}, {'limit':False}, {'offset':-1}, {'kind':'all-game'}, {'path':'file'}, {'group_id':'bad'}):
            with self.assertRaises(ValueError):
                gaps.page(self.store, result, [self.group], p)

    def test_discovery_modes_preserve_enumeration_without_expanding_denominator(self):
        for mode in gaps.DISCOVERY_MODES:
            with self.subTest(mode=mode):
                self.group = self.f.fixture()
                self.discovery(mode)
                result = self.result()
                row = self.candidate(result, 'discovery')
                self.assertEqual(row['discovery']['mode'], mode)
                self.assertIn('not proof', row['discovery']['limitation'])
                self.assertEqual(result['groups'][0]['report']['sections'][0]['denominator'], 1)
                self.assertNotIn('invented-extra', result['catalog_receipt']['heads'])

    def test_distinct_unobserved_contexts_keep_separate_candidate_and_issue_ids(self):
        for key in ('invented-empty-a', 'invented-empty-b'):
            case = copy.deepcopy(self.group['cases'][0])
            case.update(case_id=key, record_ids=[])
            self.group['cases'].append(case)
        result = self.result()
        rows = [r for r in gaps.candidates(result, [self.group]) if r['kind'] == 'uncatalogued']
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]['candidate_id'], rows[1]['candidate_id'])
        self.assertEqual({r['case_ids'][0] for r in rows}, {'invented-empty-a', 'invented-empty-b'})
        for row in rows:
            self.assertIn('Displayed text is not established', row['reason'])
            self.assertEqual(self.create(result, row)['issue']['record_ids'], [])
        self.assertEqual(len(self.store.issues()), 2)

    def test_uncaptured_attempts_never_claim_displayed_text(self):
        for execution in ('unsupported', 'not_run', 'excluded', 'failed', 'interrupted'):
            with self.subTest(execution=execution):
                self.group = self.f.fixture()
                self.group['cases'][0]['record_ids'] = []
                self.group['associations'] = {}
                self.group['record_requirements'] = {}
                case = copy.deepcopy(self.group['cases'][0])
                def mutate(m):
                    m['definition']['requests'][0]['case'] = case
                    m['observations'][0].update(case_sha256=contract_digest('CaseSpec', case),
                        execution=execution, assertion='not_assessed', frames=0, captures=[],
                        reason='Invented unobserved attempt; no captured frame.')
                self.f.reseal(self.group, mutate)
                self.f.proof(self.group)['purposes'] = {contract_digest('CaseSpec', case):{
                    'renderer':dict(reason='Retain invented noncaptured attempt.', reference='Authored fixture')}}
                self.group['runs'][0].update(expectations=None, findings=[])
                result = self.result()
                row = self.candidate(result, 'uncatalogued')
                self.assertEqual(row['observation_ids'], ['observation'])
                self.assertFalse(row['provenance'][0]['captured'])
                self.assertIn('Displayed text is not established', row['reason'])
                issue = self.create(result, row)['issue']
                self.assertIn('Displayed text is not established', issue['description'])

    def test_unreviewed_discovery_and_missing_method_remain_unknown(self):
        self.discovery(admitted=False)
        row = self.candidate(kind='discovery')
        self.assertFalse(row['discovery']['admitted'])
        self.assertEqual(row['discovery']['mode'], 'unknown')
        self.assertEqual(row['record_revisions'], {})

    def test_discovery_policy_cannot_reference_other_manifest_or_claim_unknown_mode(self):
        sha = self.discovery('scripted_navigation')
        self.group['discovery_modes']['f'*64] = self.group['discovery_modes'].pop(sha)
        with self.assertRaises(ValueError):
            self.candidate(kind='discovery')
        self.group['discovery_modes'][sha] = self.group['discovery_modes'].pop('f'*64)
        self.group['discovery_modes'][sha]['mode'] = 'all_game_verified'
        with self.assertRaises(ValueError):
            self.candidate(kind='discovery')

    def test_debug_discovery_cannot_be_labeled_ordinary_or_exhaustive(self):
        def debug(m):
            m['observations'][0]['reach_method'] = 'debug_injection'
            m['definition']['capabilities']['capabilities']['debug_access'] = True
        self.f.reseal(self.group, debug)
        caps = json.loads(self.group['runs'][0]['manifest_bytes'])['definition']['capabilities']
        self.f.proof(self.group)['capabilities_sha256'] = contract_digest('AdapterCapabilities', caps)
        self.discovery('random_exploration')
        with self.assertRaises(ValueError):
            self.candidate(kind='discovery')
        self.group['discovery_modes'] = {}
        self.assertEqual(self.candidate(kind='discovery')['discovery']['mode'], 'debug_assisted')

    def test_declarations_are_reasoned_and_not_excluded_from_catalog(self):
        self.group['declarations'] = [
            dict(kind=kind, revisions={'unseen':1}, reason='Invented explicit reason.', reference='Invented review')
            for kind in ('preserved_source', 'graphics_text')]
        result = self.result()
        rows = gaps.candidates(result, [self.group])
        self.assertEqual({r['kind'] for r in rows}, {'unexercised', 'preserved_source', 'graphics_text'})
        self.assertEqual(result['groups'][0]['current_catalog'][0]['denominator'], 3)

    def test_provider_refuses_cross_project_and_recomputes_after_record_edit(self):
        provider = ReviewProvider(self.store, [self.group], admit_run=self.f.proofs.get, artifacts=self.f)
        first = provider.gaps(self.store, {})
        self.change_record()
        second = provider.gaps(self.store, {})
        self.assertNotEqual(first['catalog_read_sha256'], second['catalog_read_sha256'])
        other = fixtures.CoverageTests();other.setUp();self.addCleanup(other.doCleanups)
        with self.assertRaises(ValueError):
            provider.gaps(other.store, {})

    def test_authenticated_http_creation_and_rejection_use_selected_provider(self):
        provider = ReviewProvider(self.store, [self.group], admit_run=self.f.proofs.get, artifacts=self.f)
        server = StudioServer(self.store, 0, progress_interval=86400,
                             runtime_review_providers=[(self.store.manifest_path, provider)])
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        def request(action, data=None, *, auth=True, origin=None):
            client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
            headers = {'X-Studio-Token':server.token} if auth else {}
            if origin:headers['Origin'] = origin
            if data is not None:headers['Content-Type'] = 'application/json'
            try:
                client.request('GET' if data is None else 'POST', '/api/'+action,
                               body=None if data is None else json.dumps(data), headers=headers)
                response = client.getresponse()
                return response.status, json.loads(response.read())
            finally:client.close()
        try:
            self.assertEqual(request('runtime-gaps', auth=False)[0], 401)
            status, page = request('runtime-gaps?kind=unexercised&limit=10')
            self.assertEqual(status, 200)
            body = dict(candidate_id=page['items'][0]['candidate_id'], catalog_read_sha256=page['catalog_read_sha256'])
            self.assertEqual(request('runtime-gap-issue', body, auth=False)[0], 401)
            self.assertEqual(request('runtime-gap-issue', body, origin='https://elsewhere.invalid')[0], 403)
            self.assertEqual(request('runtime-gap-issue', dict(body, target='No mutation'))[0], 400)
            status, saved = request('runtime-gap-issue', body)
            self.assertEqual(status, 200);self.assertTrue(saved['created'])
            self.assertFalse(request('runtime-gap-issue', body)[1]['created'])
            self.change_record()
            self.assertEqual(request('runtime-gap-issue', body)[0], 409)
            for query in ('path=secret', 'limit=101', 'offset=-1', 'kind=unknown', 'limit=1&limit=2'):
                self.assertEqual(request('runtime-gaps?'+query)[0], 400)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()

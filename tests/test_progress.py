"""Private progress files from independently invented projects; no game data."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from _bootstrap import ROOT
from test_state import project, invented
from patchquest.progress import REPORT_PATH, ProgressReporter, write_report
from patchquest.state import Store, canonical
from patchquest.state_api import execute
from patchquest.studio import StudioServer
from patchquest.studio_projects import ProjectDirectory


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(project(self.root))
        self.path = self.root / REPORT_PATH

    def test_current_translations_only_and_no_private_text(self):
        self.store.put(invented('ready', target='PRIVATE TARGET SENTINEL'), 0)
        self.store.put(invented('blank', target=' \n\t\u3000'), 0)
        self.store.put(invented('empty', target=''), 0, 'human')
        self.store.put(invented('empty', target='INACTIVE PROPOSAL SENTINEL'), 1)
        self.store.put(invented('cleared', target='OLD TARGET SENTINEL'), 0)
        self.store.put(invented('cleared', target=''), 1, 'human')
        self.store.put(dict(invented('glossary'), kind='glossary'), 0)
        before = {a: execute(self.store, a) for a in ('events', 'builds')}
        with self.store.connection() as db:
            records = canonical(self.store._all(db))
        report = execute(self.store, 'progress-report')
        self.assertEqual(json.loads(self.path.read_text()), report)
        self.assertEqual(set(report), {'schema_version', 'report_type', 'updated_at', 'basis',
            'total_records', 'translated_records', 'remaining_records', 'percent_translated'})
        self.assertEqual((report['total_records'], report['translated_records'],
                          report['remaining_records'], report['percent_translated']), (4, 1, 3, 25.0))
        self.assertEqual(report['basis'], 'catalogued_translation_records')
        self.assertTrue(report['updated_at'].endswith('+00:00'))
        for secret in ('SENTINEL', 'Invented guide', str(self.root), 'あかり', 'source_sha256'):
            self.assertNotIn(secret, self.path.read_text())
        with self.store.connection() as db:
            self.assertEqual(canonical(self.store._all(db)), records)
        self.assertEqual(before, {a: execute(self.store, a) for a in before})
        self.assertTrue(self.store.get('empty')['human_corrected'])
        self.assertEqual(len(self.store.proposals('empty')), 1)
        self.assertEqual(self.store.overview()['counts']['translated'], 1)

    def test_empty_denominator_updates_and_exact_completion(self):
        self.assertIsNone(write_report(self.store)['percent_translated'])
        self.store.put(invented(), 0)
        self.assertEqual(write_report(self.store)['percent_translated'], 100.0)
        self.store.put(invented('new', target=''), 0)
        self.assertEqual(write_report(self.store)['percent_translated'], 50.0)
        self.store.put(invented('line-01', target=''), 1, 'human')
        self.assertEqual(write_report(self.store)['percent_translated'], 0.0)
        # Exercise the real aggregate/rounding with many tiny synthetic records.
        with self.store.connection() as db, self.store.transaction(db):
            for n in range(2100):
                self.store._put(db, invented('bulk-' + str(n)), 0, 'import', '', '')
        self.assertLess(write_report(self.store)['percent_translated'], 100.0)
        self.store.put(invented('new'), 1, 'human')
        self.assertEqual(write_report(self.store)['percent_translated'], 99.9)

    def test_read_only_api_and_headless_refresh(self):
        self.store.put(invented(), 0)
        self.assertEqual(execute(self.store, 'progress')['percent_translated'], 100.0)
        self.assertFalse(self.path.exists())
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tools/patchquest.py'),
            'state', str(self.store.manifest_path), 'progress-report'], cwd=ROOT,
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['total_records'], 1)
        self.assertTrue(self.path.is_file())
        with self.assertRaises(TypeError):
            execute(self.store, 'progress-report', {'path': 'unexpected.json'})

    def test_failed_replace_retains_complete_previous_report(self):
        write_report(self.store)
        previous = self.path.read_bytes()
        self.store.put(invented(), 0)
        with patch('patchquest.progress.os.replace', side_effect=PermissionError('synthetic failure')):
            with self.assertRaises(PermissionError):
                write_report(self.store)
        self.assertEqual(self.path.read_bytes(), previous)
        self.assertEqual(list(self.path.parent.glob('.translation-progress-*.tmp')), [])
        self.assertEqual(write_report(self.store)['total_records'], 1)

    def test_unrelated_files_links_and_removed_state_are_preserved(self):
        self.path.write_bytes(b'not a progress report')
        with self.assertRaises(ValueError):
            write_report(self.store)
        self.assertEqual(self.path.read_bytes(), b'not a progress report')
        self.path.unlink()
        write_report(self.store)
        checkpoint = self.root / 'preserved.fixture'
        os.link(self.path, checkpoint)
        previous = checkpoint.read_bytes()
        with self.assertRaises(ValueError):
            write_report(self.store)
        self.assertEqual(checkpoint.read_bytes(), previous)
        self.path.unlink()
        self.store.path.unlink()
        with self.assertRaises(ValueError):
            write_report(self.store)
        self.assertFalse(self.store.path.exists())

    def test_symlink_cannot_redirect_report(self):
        target = self.root / 'checkpoint.fixture'
        target.write_text('preserve')
        try:
            self.path.symlink_to(target)
        except OSError:
            self.skipTest('Symlinks unavailable for this account')
        with self.assertRaises(ValueError):
            write_report(self.store)
        self.assertEqual(target.read_text(), 'preserve')

    def test_writers_serialize_read_and_replace(self):
        self.store.put(invented('ready'), 0)
        entered, release = threading.Event(), threading.Event()
        original = os.replace
        def delayed_replace(*args):
            if not entered.is_set():
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('test barrier')
            return original(*args)
        with ThreadPoolExecutor(max_workers=2) as pool, patch('patchquest.progress.os.replace', delayed_replace):
            first = pool.submit(write_report, self.store)
            try:
                self.assertTrue(entered.wait(5))
                # A separately opened Store must respect the same DB lock.
                def update_and_report():
                    other = Store(self.store.manifest_path)
                    other.put(invented('remaining', target=''), 0)
                    return write_report(other)
                second = pool.submit(update_and_report)
                self.assertFalse(second.done())
            finally:
                release.set()
            self.assertEqual(first.result(5)['percent_translated'], 100.0)
            self.assertEqual(second.result(5)['percent_translated'], 50.0)
        self.assertEqual(json.loads(self.path.read_text())['percent_translated'], 50.0)

    def test_periodic_multiple_projects_no_browser_and_clean_shutdown(self):
        second = self.root / 'second'
        second.mkdir()
        other = Store(project(second))
        other.put(invented(), 0)
        pending = self.root / 'pending'
        pending.mkdir()
        project(pending)
        registry = self.root / '.local/config/local.json'
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'schema_version': 2, 'projects': {
            'second': 'second/project.json', 'pending': 'pending/project.json',
            'missing': 'missing/project.json'}}))
        server = StudioServer(self.store, 0, platform_root=self.root, progress_interval=1)
        try:
            def wait_for(predicate):
                until = time.monotonic() + 5
                while time.monotonic() < until:
                    if predicate():
                        return
                    time.sleep(.02)
                self.fail('Progress did not refresh')
            wait_for(lambda: self.path.exists() and (second / REPORT_PATH).exists())
            self.assertIsNone(json.loads(self.path.read_text())['percent_translated'])
            other.put(invented('remaining', target=''), 0)
            wait_for(lambda: json.loads((second / REPORT_PATH).read_text())['percent_translated'] == 50.0)
            self.assertFalse((pending / '.patchquest').exists())
        finally:
            server.server_close()
        self.assertFalse(server.progress._thread.is_alive())
        previous = self.path.read_bytes()
        server.progress.refresh()
        self.assertEqual(self.path.read_bytes(), previous)

    def test_interval_validation_and_failure_recovery(self):
        directory = ProjectDirectory(self.store)
        for interval in (0, -1, True, 1.5, 86401):
            with self.assertRaises(ValueError):
                ProgressReporter(directory, interval)
        reporter = ProgressReporter(directory)
        self.assertEqual(reporter.interval_seconds, 300)
        with patch('patchquest.progress.write_report', side_effect=OSError('PRIVATE PATH SENTINEL')):
            with self.assertLogs('patchquest.progress', level='WARNING') as logs:
                reporter.refresh()
                reporter.refresh()
        self.assertEqual(len(logs.output), 1)
        self.assertNotIn('SENTINEL', str(logs.output))
        self.assertEqual(len(reporter.failures), 1)
        reporter.refresh()
        self.assertEqual(reporter.failures, set())
        self.assertTrue(self.path.exists())

    def test_local_read_endpoint_stays_authenticated(self):
        server = StudioServer(self.store, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for headers, expected in (({}, 401), ({'X-Studio-Token': server.token}, 200),
                    ({'X-Studio-Token': server.token, 'Origin': 'https://example.invalid'}, 403)):
                client = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
                try:
                    client.request('GET', '/api/progress', headers=headers)
                    response = client.getresponse()
                    self.assertEqual(response.status, expected)
                    response.read()
                finally:
                    client.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()

"""Private, numeric progress snapshots. No network access or build execution."""
import json
import logging
import os
import tempfile
import threading

from .core.context import confined

REPORT_PATH = '.patchquest/translation-progress.json'
DEFAULT_INTERVAL = 300


def _destination(store, relative=REPORT_PATH, report_type='translation-progress', limit=4096):
    path = store.context.root / relative
    if (path.is_symlink() or confined(store.context.root, relative) != path
            or path.parent != store.directory):
        raise ValueError('Progress report path changed or linked')
    if path.exists():
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > limit:
            raise ValueError('Unsafe progress report destination')
        previous = json.loads(path.read_text(encoding='utf8'))
        if (not isinstance(previous, dict) or previous.get('report_type') != report_type
                or previous.get('schema_version') != 1):
            raise ValueError('Refusing an unrelated progress report file')
    return path


def write_report(store):
    """Replace only this cache, serialized with other writers by the state lock.

    No records, events or snapshots are changed. OS write access is trusted,
    matching Store's filesystem boundary; this is not a hostile-process sandbox.
    """
    return _write_cache(store, REPORT_PATH, 'translation-progress', lambda s, db: s._progress(db), 4096)


def _write_cache(store, relative, report_type, producer, limit):
    """Internal fixed-name caches; callers never supply destinations through an API."""
    if relative not in (REPORT_PATH, '.patchquest/readiness-summary.json'):
        raise ValueError('Unsupported private cache')
    if not store.path.is_file():
        raise ValueError('Project state missing')
    temporary = None
    # Serialize read + replace across reporters/CLI processes, preventing an
    # older snapshot from winning a concurrent file write. The DB is unchanged.
    with store.connection() as db, store.transaction(db):
        destination = _destination(store, relative, report_type, limit)
        report = producer(store, db)
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf8', newline='\n',
                    dir=destination.parent, prefix='.' + report_type + '-', suffix='.tmp', delete=False) as output:
                temporary = output.name
                json.dump(report, output, ensure_ascii=True, indent=2, allow_nan=False)
                output.write('\n')
                output.flush()
                os.fsync(output.fileno())
            _destination(store, relative, report_type, limit)
            os.replace(temporary, destination)
        finally:
            if temporary is not None and os.path.exists(temporary):
                os.unlink(temporary)
    return report


class ProgressReporter:
    """Refresh initialized, explicitly registered projects while Studio runs."""
    def __init__(self, projects, interval_seconds=DEFAULT_INTERVAL):
        if type(interval_seconds) is not int or not 1 <= interval_seconds <= 86400:
            raise ValueError('Progress interval must be 1–86400 seconds')
        self.projects = projects
        self.interval_seconds = interval_seconds
        self.failures = set()
        self.readiness_failures = set()
        self._stop = threading.Event()
        self._thread = None

    def refresh(self):
        from .verification import write_summary
        for project in self.projects.catalogue()['projects']:
            if self._stop.is_set():
                break
            if not project['available']:
                continue
            key = project['id']
            try:
                write_report(self.projects.select(key))
                self.failures.discard(key)
            except Exception:
                # Keep the old timestamp on failure, retry next cycle, and avoid
                # leaking paths/content through exception strings or log spam.
                if key not in self.failures:
                    logging.getLogger(__name__).warning(
                        'Translation progress refresh failed; last valid report retained.')
                self.failures.add(key)
            # Independent cache: a readiness failure must not suppress progress.
            try:
                write_summary(self.projects.select(key))
                self.readiness_failures.discard(key)
            except Exception:
                if key not in self.readiness_failures:
                    logging.getLogger(__name__).warning(
                        'Readiness summary refresh failed; last valid report retained.')
                self.readiness_failures.add(key)

    def _run(self):
        while not self._stop.is_set():
            self.refresh()
            if self._stop.wait(self.interval_seconds):
                break

    def start(self):
        if self._thread is not None or self._stop.is_set():
            raise RuntimeError('Progress reporter cannot be restarted')
        self._thread = threading.Thread(target=self._run, name='translation-progress', daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join()

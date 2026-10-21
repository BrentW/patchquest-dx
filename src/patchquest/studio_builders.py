"""Switch explicit private build callbacks; never discover/import code or commands."""
from dataclasses import dataclass
from pathlib import Path
import sqlite3
import threading
import uuid

from .jobs import BuildWorker, Jobs
from .state import Conflict, text


@dataclass(frozen=True)
class BuilderBinding:
    manifest: Path
    callback: object
    label: str = 'Private build worker'


class StudioBuilders:
    """One managed worker per Studio server; other launchers remain independent."""
    def __init__(self, projects, bindings=()):
        self.projects = projects
        self.bindings = {}
        self.lock = threading.RLock()
        self.version = uuid.uuid4().hex
        self.active = None
        self.worker = None
        for binding in bindings:
            key = projects._key(binding.manifest)
            projects.select(key)  # Must already be explicitly registered and initialized.
            if key in self.bindings or not callable(binding.callback):
                raise ValueError('Each project needs one callable build binding')
            text(binding.label, 'worker label', 200)
            self.bindings[key] = binding

    def _status(self, selected):
        entries = []
        for entry in self.projects.catalogue()['projects']:
            key = entry['id']
            row = dict(id=key, title=entry['title'], configured=key in self.bindings,
                       available=False, worker='', job=None, managed=False)
            try:
                store = self.projects.select(key)
                owner = self.worker.owner if self.worker and key == self.active else None
                c = Jobs(store).capabilities(owner)
                row.update(available=c['available'], worker=c['worker'], job=c['job'], managed=c['owned'])
            except (KeyError, ValueError, OSError, sqlite3.DatabaseError):
                if key == selected:
                    raise
            entries.append(row)
        target = next(row for row in entries if row['id'] == selected)
        current = next((row for row in entries if row['id'] == self.active), None)
        if target['available']:
            reason = 'The selected project’s builder is ready.' if not target['job'] else 'The selected project has a build in progress.'
        elif not target['configured']:
            reason = 'No build adapter is configured for this project in this Studio session.'
        elif target['job']:
            reason = 'This project has an unfinished build. Inspect it before loading a builder.'
        elif current and current['job']:
            reason = 'Wait for the loaded builder’s queued or running build to finish before switching.'
        elif current and current['available'] and not current['managed']:
            reason = 'The previous builder is now controlled by another launcher. Restart this Studio session after checking its jobs.'
        else:
            reason = 'Ready to switch builders. Loading a builder does not start a build.'
        can_switch = (target['configured'] and not target['available'] and not target['job']
                      and not (current and (current['job'] or (current['available'] and not current['managed']))))
        return dict(version=self.version, selected=target,
                    workers=[row for row in entries if row['available'] or row['job']],
                    can_switch=bool(can_switch), reason=reason)

    def status(self, selected):
        with self.lock:
            return self._status(selected)

    def _start(self, key):
        binding = self.bindings[key]
        worker = BuildWorker(self.projects.select(key), binding.callback, binding.label)
        worker.start(require_idle=True)
        self.active, self.worker = key, worker

    def switch(self, selected, expected):
        with self.lock:
            if not isinstance(expected, str) or expected != self.version:
                raise Conflict('The loaded builder changed in another tab. Refresh its status before switching.')
            state = self._status(selected)
            if not state['can_switch']:
                raise Conflict(state['reason'])
            previous = self.active
            if self.worker:
                self.worker.close_if_idle()  # Rechecks ownership and jobs atomically.
                self.active, self.worker = None, None
            self.version = uuid.uuid4().hex
            try:
                self._start(selected)  # Rechecks target ownership/unfinished jobs.
            except Exception as error:
                restored = False
                if previous:
                    try:
                        self._start(previous)
                        restored = True
                    except Exception:
                        pass  # Never steal an external worker or resume an orphaned job.
                suffix = 'The previous builder was restored.' if restored else 'Check the current builder status before retrying.'
                raise Conflict('Could not load the selected builder. ' + suffix) from error
            return self._status(selected)

    def close(self):
        with self.lock:
            if self.worker:
                self.worker.close()  # Graceful server shutdown drains an active build.
                self.active, self.worker = None, None

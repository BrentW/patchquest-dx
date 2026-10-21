"""Explicit local Studio project catalogue; never discovers ROMs or loads code."""
import hashlib
import os
import threading
from pathlib import Path

from .config import load_config
from .core.context import ProjectContext, confined
from .state import Store


class ProjectDirectory:
    def __init__(self, store, platform_root=None):
        self._entries = {}
        self._stores = {}
        self._lock = threading.Lock()
        self.default = self._key(store.manifest_path)
        self._add(store.manifest_path, store.context.manifest['project_id'], store)
        # Only an explicitly supplied platform root enables its local registry.
        if platform_root is not None:
            root = Path(platform_root).resolve()
            for alias, path in load_config(root)['projects'].items():
                self._add((root / path).resolve(), alias)

    @staticmethod
    def _key(path):
        # Stable opaque keys avoid exposing manifest paths in the dropdown/URL.
        return hashlib.sha256(os.path.normcase(str(Path(path).resolve())).encode('utf8')).hexdigest()

    def _add(self, path, alias, store=None):
        key = self._key(path)
        if key in self._entries:
            return
        entry = dict(id=key, title=alias, available=False,
                     note='Project unavailable. Check its local setup.')
        context = None
        try:
            context = store.context if store else ProjectContext.load(path)
            entry['title'] = context.manifest.get('data', {}).get('title') or alias
            if not isinstance(entry['title'], str):
                entry['title'] = alias
            state_path = confined(context.root, '.patchquest/state.sqlite3')
            entry['available'] = bool(store) or state_path.is_file()
            entry['note'] = '' if entry['available'] else 'Initialize this project’s translation state first.'
        except (ValueError, OSError, TypeError):
            pass
        self._entries[key] = (Path(path), context, entry)
        if store:
            self._stores[key] = store

    def catalogue(self):
        return {'default': self.default,
                'projects': [dict(item[2]) for item in self._entries.values()]}

    def select(self, key=None):
        # Absence preserves the single-project API; invalid/empty keys fail closed.
        key = self.default if key is None else key
        with self._lock:
            path, context, entry = self._entries[key]
            if not entry['available']:
                raise KeyError('Unavailable project')
            if key in self._stores and not self._stores[key].path.is_file():
                raise KeyError('Project state missing')
            if key not in self._stores:
                if not confined(context.root, '.patchquest/state.sqlite3').is_file():
                    raise KeyError('Project state missing')
                current = ProjectContext.load(path)
                if (current.root != context.root or
                        current.manifest['project_id'] != context.manifest['project_id'] or
                        current.manifest['source'] != context.manifest['source']):
                    raise ValueError('Project identity changed; restart Studio')
                self._stores[key] = Store(path)
            return self._stores[key]

"""Explicit private-project paths; importing this module never discovers a project."""
from dataclasses import dataclass
import json
from pathlib import Path
import re

from patchquest import API_VERSION
from .edits import load_source


def confined(root, value):
    """Resolve a relative resource under its declared root, including symlinks."""
    root = Path(root).resolve()
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Expected a relative path without parent traversal')
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError('Path escapes its declared root')
    return target


@dataclass(frozen=True)
class OutputPolicy:
    root: Path
    inputs: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, 'root', Path(self.root).resolve())
        object.__setattr__(self, 'inputs', tuple(Path(p).resolve() for p in self.inputs))

    def check(self, path):
        path = Path(path)
        if '..' in path.parts:
            raise ValueError('Output parent traversal is not allowed')
        path = (path if path.is_absolute() else self.root / path).resolve()
        if not path.is_relative_to(self.root) or path in self.inputs:
            raise ValueError('Output escapes policy or aliases a protected input')
        return path

    def write_new(self, path, data):
        target = self.check(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        self.check(target)  # Recheck after creating parents.
        with target.open('xb') as stream:
            stream.write(data)
        return target


@dataclass(frozen=True)
class ProjectContext:
    root: Path
    manifest: dict
    source: Path
    output: OutputPolicy

    @classmethod
    def load(cls, manifest_path):
        path = Path(manifest_path).resolve()
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        allowed = {'schema_version', 'platform_api', 'project_id', 'source', 'resources', 'output_directory', 'data'}
        if not isinstance(data, dict) or set(data) - allowed:
            raise ValueError('Unsupported project fields')
        if type(data.get('schema_version')) is not int or data['schema_version'] != 1 or type(data.get('platform_api')) is not int or data['platform_api'] != API_VERSION:
            raise ValueError('Unsupported project schema/platform API')
        if not isinstance(data.get('project_id'), str) or not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', data['project_id']):
            raise ValueError('Invalid project ID')
        source = data.get('source', {})
        if not isinstance(source, dict) or set(source) != {'path', 'sha256'} or not isinstance(source['path'], str) or not source['path']:
            raise ValueError('Expected source path and SHA-256')
        if not isinstance(source['sha256'],str) or not re.fullmatch('[0-9a-f]{64}', source['sha256']):
            raise ValueError('Expected a complete lowercase source SHA-256')
        root = path.parent
        source_path = (root / source['path']).resolve()  # External originals are read-only inputs.
        if not isinstance(data.get('output_directory','output'),str) or not data.get('output_directory','output'):
            raise ValueError('Output directory must be a relative path string')
        output = confined(root, data.get('output_directory', 'output'))
        if output == root or source_path.is_relative_to(output):
            raise ValueError('Outputs must be separate from project root and original source')
        resources = data.get('resources', {})
        if not isinstance(resources, dict) or not all(isinstance(k, str) and isinstance(v, str) for k,v in resources.items()):
            raise ValueError('Resources must be named relative paths')
        protected = [source_path, path]
        for resource in resources.values():
            resolved = confined(root, resource)
            if resolved.is_relative_to(output) or output.is_relative_to(resolved):
                raise ValueError('Output and resource areas must be separate')
            protected.append(resolved)
        return cls(root, data, source_path, OutputPolicy(output, tuple(protected)))

    def read_source(self):
        return load_source(self.source, self.manifest['source']['sha256'])

    def resource(self, name):
        return confined(self.root, self.manifest['resources'][name])

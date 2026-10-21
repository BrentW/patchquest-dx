"""Authoritative Store snapshot connector for runtime artifact preservation.

References are derived from existing rows/history; no reference index or second
DB is created. Explicit pins/ownership use one revisioned policy in Store metadata.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import re

from .core.context import confined
from .runtime_artifacts import ArtifactError, _graph
from .runtime_contracts import validate
from .state import Conflict, canonical

POLICY_KEY = 'runtime-artifact-policy.v1'
_TABLES = frozenset(('metadata', 'records', 'revisions', 'memory', 'proposals',
    'events', 'evidence', 'issues', 'issue_history', 'snapshots', 'builds',
    'build_history', 'attachments', 'attachment_history', 'build_worker',
    'build_jobs', 'agent_sessions', 'work_items', 'work_history', 'work_managed'))
_METADATA = ('identity', 'verification.plan.v1', 'verification.observation.v1.',
    'milestones.v1', 'screenshot-selection.v1', 'release-candidates.v1',
    'tester-report.v1.', 'narrative-review.v1.', POLICY_KEY)
_COLUMNS = {
    'metadata': 'key value', 'records': 'id revision human',
    'revisions': 'id revision payload role actor reason created',
    'memory': 'id revision payload', 'proposals': 'seq id base payload actor reason created',
    'events': 'seq kind payload created',
    'evidence': 'seq id revision stage passed reference build_id created',
    'issues': 'id revision payload', 'issue_history': 'id revision payload actor created',
    'snapshots': 'digest payload created', 'builds': 'id revision payload',
    'build_history': 'id revision payload created', 'attachments': 'digest mime payload',
    'attachment_history': 'digest revision payload created',
    'build_worker': 'slot owner label expires',
    'build_jobs': 'id snapshot status owner payload created updated',
    'agent_sessions': 'id payload status expires created updated',
    'work_items': 'id revision status payload owner fence expires created updated',
    'work_history': 'seq id payload created', 'work_managed': 'record_id',
}
_DIGEST = re.compile(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', re.I)


def _need(condition, message):
    if not condition:
        raise ArtifactError(message)


def _hash(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def _policy(value):
    _need(type(value) is dict and set(value) == {'schema_version', 'revision', 'pins', 'ownership'},
          'Invalid artifact policy')
    _need(type(value['schema_version']) is int and value['schema_version'] == 1,
          'Unknown artifact policy version')
    _need(type(value['revision']) is int and value['revision'] >= 0, 'Invalid policy revision')
    _graph(dict(revision=str(value['revision']), complete=True, references=[], leases=[],
                pins=value['pins'], ownership=value['ownership']))
    return copy.deepcopy(value)


class ArtifactState:
    """Use as graph_guard=connector.guard with the same explicit blob directory.

    BEGIN IMMEDIATE excludes all cooperating Store/Jobs/Coordination writers for
    the duration of the caller's byte operation. No leases are expired or changed
    during reads: unreconciled expired rows remain conservatively protective.
    """
    def __init__(self, store, directory):
        self.store = store
        self.directory = Path(directory).absolute()
        _need(self.directory.resolve() == self.directory, 'Redirected artifact directory')
        relative = self.directory.relative_to(store.directory)
        _need(relative.parts and relative.parts[0] not in ('evidence', 'snapshots', 'backups')
              and not relative.parts[0].startswith('state.sqlite3'),
              'Use a dedicated artifact directory in selected project state')
        _need(confined(store.directory, relative) == self.directory, 'Artifact directory escaped state')

    @staticmethod
    def _load_policy(db):
        row = db.execute('SELECT value FROM metadata WHERE key=?', (POLICY_KEY,)).fetchone()
        return _policy(json.loads(row[0])) if row else dict(schema_version=1, revision=0, pins=[], ownership={})

    def policy(self):
        with self.store.connection() as db, self.store.transaction(db, write=False):
            return self._load_policy(db)

    def set_policy(self, *, pins, ownership, expected):
        """CAS explicit declarations in existing metadata; no derived-reference copy.

        Protected original/save/checkpoint classifications cannot be downgraded.
        Policy history is retained in Store events; superseded pins are not live pins.
        """
        _need(type(expected) is int and expected >= 0, 'Invalid expected revision')
        proposed = _policy(dict(schema_version=1, revision=expected + 1, pins=pins, ownership=ownership))
        with self.store.connection() as db, self.store.transaction(db):
            old = self._load_policy(db)
            if old['revision'] != expected:
                raise Conflict('Artifact policy changed; reload')
            for digest, owner in old['ownership'].items():
                if owner in ('original', 'user_save', 'checkpoint'):
                    _need(proposed['ownership'].get(digest) == owner, 'Protected ownership cannot be downgraded')
            db.execute('INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                       (POLICY_KEY, canonical(proposed)))
            self.store._event(db, POLICY_KEY, proposed)
        return proposed

    def record_run(self, build_id, observations, *, expected):
        """Retain contract observations in existing build reports/history via CAS.

        Does not assert an emulator actually ran, approve a build, replace record
        text, or downgrade earlier run evidence. The caller owns run execution.
        """
        _need(type(observations) is list and 0 < len(observations) <= 100000, 'Explicit observations required')
        observations = [validate('CaseObservation', o) for o in observations]
        _need(len({o['observation_id'] for o in observations}) == len(observations), 'Duplicate observation identity')
        _need(all(o['binding']['build_id'] == build_id for o in observations), 'Observation build differs')
        build = next((b for b in self.store.builds() if b['id'] == build_id), None)
        _need(build is not None, 'Unknown build')
        if type(expected) is not int or build.pop('revision') != expected:
            raise Conflict('Build changed; reload before recording run')
        _need(all(o['binding']['snapshot'] == build.get('snapshot') for o in observations),
              'Observation snapshot differs from retained build')
        validation = build.setdefault('validation', {})
        retained = validation.setdefault('runtime_cases', [])
        _need(type(retained) is list, 'Unknown runtime case storage')
        by_id = {o['observation_id']: o for o in retained}
        for o in observations:
            if o['observation_id'] in by_id:
                _need(by_id[o['observation_id']] == o, 'Observation identity already has different evidence')
            else:
                retained.append(o)
        return self.store.build(build, expected)

    def _inventory(self):
        if not self.directory.exists():
            return set()
        _need(self.directory.resolve() == self.directory and self.directory.is_dir(), 'Artifact directory changed')
        result = set()
        for path in self.directory.iterdir():
            if path.name == '.writer-lock':
                continue
            _need(re.fullmatch('[0-9a-f]{64}', path.name) and path.is_file()
                  and not path.is_symlink(), 'Unknown artifact inventory entry')
            result.add(path.name)
        return result

    def _check_schema(self, db):
        _need(db.execute('PRAGMA user_version').fetchone()[0] == 3, 'Unsupported state version')
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        _need(tables - {'sqlite_sequence'} == _TABLES, 'Unknown or missing reference-bearing state table')
        for table in sorted(_TABLES):
            # Names are module constants, never request-provided SQL.
            columns = {r['name'] for r in db.execute('PRAGMA table_info(' + table + ')')}
            _need(columns == set(_COLUMNS[table].split()), 'Unknown state reference columns')

    @contextmanager
    def read_guard(self):
        """Exclude authoritative writers for resolution; yield no graph authority.

        The same BEGIN IMMEDIATE covers schema/identity and the caller's byte read.
        No retained history or reference payload is scanned, cached or changed.
        """
        with self.store.connection() as db, self.store.transaction(db):
            self._check_schema(db)
            row = db.execute("SELECT value FROM metadata WHERE key='identity'").fetchone()
            expected = canonical(dict(project_id=self.store.context.manifest['project_id'],
                source_sha256=self.store.context.manifest['source']['sha256']))
            _need(row is not None and row[0] == expected, 'Selected state identity changed')
            yield None

    @contextmanager
    def guard(self):
        """Yield a conservative complete graph under authoritative writer exclusion."""
        with self.store.connection() as db, self.store.transaction(db):
            self._check_schema(db)
            rows = {table: [dict(r) for r in db.execute('SELECT * FROM ' + table)]
                    for table in sorted(_TABLES)}
            policy = self._load_policy(db)
            inventory = self._inventory()
            references = set()
            opaque = False

            def walk(value, kind, label):
                nonlocal opaque
                if isinstance(value, dict):
                    if value.get('kind') in ('EvidenceRef', 'CaseObservation', 'RunBinding'):
                        validate(value['kind'], value)
                    for key, item in value.items():
                        if key == 'artifacts' and item and value.get('kind') != 'RunBinding':
                            # Untyped artifact maps also occur in completed job
                            # results/history, after worker leases are released.
                            opaque = True
                        if key in ('reference', 'report', 'file', 'path', 'log') and item and not isinstance(item, (dict, list)):
                            # Opaque legacy refs cannot establish absence of a blob link.
                            if not isinstance(item, str) or not _DIGEST.fullmatch(item):
                                opaque = True
                        walk(item, kind, label)
                elif isinstance(value, list):
                    for item in value:
                        walk(item, kind, label)
                elif isinstance(value, str):
                    for match in _DIGEST.finditer(value):
                        references.add((match.group().lower(), kind, label))

            def build_paths(value):
                nonlocal opaque
                artifacts = value.get('artifacts', {})
                _need(type(artifacts) is dict, 'Unknown build artifact representation')
                if artifacts:
                    # Store build reports contain paths, not typed immutable role
                    # identities. Even a 64-hex filename can name mutable bytes.
                    # Never synthesize a historical identity by reading that path.
                    # Existing recorded digests are handled independently by walk;
                    # undigested links must conservatively protect the inventory.
                    opaque = True

            for table, entries in rows.items():
                for row in entries:
                    label = table + ':' + _hash(row)
                    if table == 'events' and row['kind'] == POLICY_KEY:
                        continue  # Superseded policy is history, not a live pin declaration.
                    kind = 'tester_report' if table == 'metadata' and row['key'].startswith('tester-report.v1.') else (
                        'build' if table in ('builds', 'build_history', 'build_jobs') else 'attachment')
                    if table == 'metadata':
                        key = row['key']
                        _need(key in _METADATA or any(key.startswith(p) for p in _METADATA if p.endswith('.')),
                              'Unknown metadata reference source; coordinate a supported reader')
                        if key == POLICY_KEY:
                            continue
                    parsed = {}
                    for field, value in row.items():
                        if field in ('payload', 'value'):
                            try:
                                parsed[field] = json.loads(value)
                                _need(type(parsed[field]) is dict, 'Unknown state payload shape')
                            except (TypeError, ValueError) as error:
                                raise ArtifactError('Malformed authoritative state payload') from error
                        else:
                            parsed[field] = value
                    walk(parsed, kind, label)
                    if table in ('builds', 'build_history'):
                        build = parsed['payload']
                        build_paths(build)
                        validation = build.get('validation', {})
                        _need(type(validation) is dict, 'Unknown build validation representation')
                        if set(validation) - {'runtime', 'runtime_cases'}:
                            opaque = True  # No unsupported extension can release bytes.
                        runs = validation.get('runtime', [])
                        cases = build.get('validation', {}).get('runtime_cases', [])
                        _need(type(runs) is list and type(cases) is list, 'Unknown runtime reference source')
                        for run in runs + cases:
                            walk(run, 'run', label)
                            if run.get('status') == 'failed' or run.get('execution') in ('failed', 'interrupted') or run.get('assertion') == 'failed':
                                walk(run, 'failure', label)
                        approval = build.get('approval', {})
                        if approval.get('approved'):
                            walk(build, 'checkpoint_approval', label)

            universe = inventory | {r[0] for r in references} | set(policy['pins']) | set(policy['ownership'])
            source_digest = self.store.context.manifest['source']['sha256']
            ownership = dict(policy['ownership'])
            ownership[source_digest] = 'original'
            leases = []
            # Unscoped workers/sessions can use any retained input. Protect the full
            # universe, including expired rows until their owner reconciles them.
            workers = [('worker:' + r['owner']) for r in rows['build_worker']]
            workers += ['job:' + r['id'] for r in rows['build_jobs'] if r['status'] in ('queued', 'running')]
            workers += ['task:' + r['id'] for r in rows['work_items'] if r['status'] == 'leased']
            workers += ['session:' + r['id'] for r in rows['agent_sessions'] if r['status'] == 'active']
            for owner in sorted(set(workers)):
                for digest in sorted(universe):
                    leases.append(dict(sha256=digest, owner=owner, active=True))
            pins = set(policy['pins'])
            if opaque:
                pins.update(universe)
            graph = dict(revision=_hash(dict(rows=rows, inventory=sorted(inventory))), complete=True,
                references=[dict(sha256=d, kind=k, id=i) for d, k, i in sorted(references)],
                pins=sorted(pins), leases=leases, ownership=ownership)
            # Fail clearly on bounded contract limits instead of dropping links.
            yield _graph(graph)

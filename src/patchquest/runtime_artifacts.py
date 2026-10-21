"""Content-addressed runtime bytes; existing state owns references and provenance.

No database, project discovery, emulator execution or artifact deletion. Returned
EvidenceRefs must be published by the caller through its existing state APIs.
"""
from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re

from .runtime_contracts import validate, verify_evidence_bytes
from .core.context import OutputPolicy


class ArtifactError(ValueError):
    """Invalid request, unavailable bytes or uncertain storage ownership."""


class ArtifactBusy(ArtifactError):
    """A cooperating writer is active, or an interrupted lock needs review."""


class BudgetExceeded(ArtifactError):
    """Required evidence cannot fit; caller must record an incomplete run."""


def _need(value, message):
    if not value:
        raise ArtifactError(message)


def _digest(value):
    _need(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Invalid digest')
    return value


def _size(value):
    _need(type(value) is int and 0 <= value <= 2**63 - 1, 'Invalid byte budget')
    return value


def _label(value):
    _need(isinstance(value, str) and bool(value.strip()) and len(value) <= 4000, 'Invalid identity')


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def reference(data, *, evidence_id, media_type, provenance, retention='referenced'):
    """Create a contract-v1 reference without promoting the producer's method."""
    _need(type(data) is bytes, 'Expected bytes')
    return validate('EvidenceRef', dict(schema_version=1, kind='EvidenceRef',
        evidence_id=evidence_id, sha256=_hash(data), byte_length=len(data),
        media_type=media_type, provenance=provenance, retention=retention,
        integrity='unverified'))


def _graph(value):
    """Explicit snapshot supplied under the existing state/job owner's lock."""
    _need(type(value) is dict and set(value) == {
        'revision', 'complete', 'references', 'pins', 'leases', 'ownership'}, 'Invalid reference graph')
    g = copy.deepcopy(value)
    _label(g['revision'])
    _need(g['complete'] is True, 'Incomplete reference graph')
    for key in ('references', 'pins', 'leases'):
        _need(type(g[key]) is list and len(g[key]) <= 100000, 'Invalid graph collection')
    _need(type(g['ownership']) is dict, 'Invalid ownership map')
    for digest, owner in g['ownership'].items():
        _digest(digest)
        _need(owner in ('managed', 'original', 'user_save', 'checkpoint', 'unknown'), 'Unknown ownership')
    for r in g['references']:
        _need(type(r) is dict and set(r) == {'sha256', 'kind', 'id'}, 'Invalid reference link')
        _digest(r['sha256']); _label(r['id'])
        _need(r['kind'] in ('run', 'failure', 'tester_report', 'checkpoint_approval', 'attachment', 'build'),
              'Unknown reference kind')
    for digest in g['pins']:
        _digest(digest)
    for lease in g['leases']:
        _need(type(lease) is dict and set(lease) == {'sha256', 'owner', 'active'}, 'Invalid lease')
        _digest(lease['sha256']); _label(lease['owner'])
        # The authoritative Jobs/Coordination owner evaluates expiry and fences.
        _need(type(lease['active']) is bool, 'Unknown lease activity')
    return g


class RuntimeArtifacts:
    """Explicit, dedicated private blob directory; no durable metadata mirror.

    graph_guard is a callable returning a context manager yielding a complete
    snapshot from authoritative state/job interfaces. It must exclude concurrent
    reference/lease changes for its duration. No default empty graph is allowed.
    Optional read_guard excludes authoritative writers for detached byte resolution
    without constructing a reference graph; it grants no retention authority.
    """
    def __init__(self, directory, *, budget_bytes, graph_guard, read_guard=None):
        self.budget_bytes = _size(budget_bytes)
        _need(callable(graph_guard), 'Explicit state/job graph guard required')
        _need(read_guard is None or callable(read_guard), 'Invalid read guard')
        self.directory = Path(directory).absolute()
        _need(not self.directory.is_symlink(), 'Symlink storage root')
        _need(self.directory.resolve() == self.directory, 'Redirected storage root')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.policy = OutputPolicy(self.directory)
        self.graph_guard = graph_guard
        self.read_guard = read_guard

    def _root(self):
        _need(self.directory.is_dir() and self.directory.resolve() == self.directory,
              'Storage root changed')

    @contextmanager
    def _guard(self, *, resolve_only=False):
        self._root()
        lock = self.directory / '.writer-lock'
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ArtifactBusy('Writer active or interrupted; inspect lock before recovery') from error
        try:
            os.close(fd)
            if resolve_only and self.read_guard is not None:
                with self.read_guard():
                    yield None  # Read exclusion supplies no reference/deletion authority.
            else:
                with self.graph_guard() as graph:
                    yield _graph(graph)
        finally:
            # Only the operational lock is removed; never retained artifacts.
            lock.unlink()

    def _path(self, digest):
        self._root()
        path = self.directory / _digest(digest)
        _need(not path.is_symlink() and path.resolve() == path, 'Redirected artifact')
        return self.policy.check(path)

    def _files(self):
        self._root()
        files = []
        for path in self.directory.iterdir():
            if path.name == '.writer-lock':
                continue
            _digest(path.name)
            _need(not path.is_symlink() and path.is_file() and path.resolve() == path,
                  'Uncertain storage entry')
            files.append(path)
        return sorted(files)

    def _read(self, ref):
        path = self._path(ref['sha256'])
        if not path.exists():
            return None, 'missing'
        _need(path.is_file(), 'Artifact is not a regular file')
        if path.stat().st_size != ref['byte_length']:
            return None, 'mismatch'
        data = path.read_bytes()
        return (data, 'verified') if verify_evidence_bytes(ref, data) else (None, 'mismatch')

    def register(self, ref, data):
        """Check bytes, deduplicate storage, return this distinct association.

        Publishing the returned EvidenceRef is the caller's state transaction.
        A crash before publication leaves conservative unreferenced bytes, never
        overwrites metadata or marks an observation passed.
        """
        r = validate('EvidenceRef', ref)
        _need(verify_evidence_bytes(r, data), 'Supplied bytes differ from reference')
        with self._guard():
            path = self._path(r['sha256'])
            if path.exists():
                _, integrity = self._read(r)
                _need(integrity == 'verified', 'Existing artifact changed; preserved for diagnosis')
            else:
                used = sum(p.stat().st_size for p in self._files())
                if used + len(data) > self.budget_bytes:
                    raise BudgetExceeded('Disk budget exhausted; required evidence not captured, run incomplete')
                with path.open('xb') as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                # Partial writes survive interruption for explicit diagnosis.
                _, integrity = self._read(r)
                _need(integrity == 'verified', 'New artifact integrity failure')
        r['integrity'] = 'verified'
        return r

    def resolve(self, ref):
        """Return detached bytes or explicit unavailable status, never a write path."""
        r = validate('EvidenceRef', ref)
        with self._guard(resolve_only=True):
            data, integrity = self._read(r)
        r['integrity'] = integrity
        return dict(available=integrity == 'verified', evidence=r, data=data,
                    reason='' if data is not None else 'Evidence bytes ' + integrity)

    def retained_build(self, binding, role, ref):
        """Resolve a pinned build role; returns bytes, not mutable canonical paths."""
        b = validate('RunBinding', binding)
        r = validate('EvidenceRef', ref)
        _need(b['artifacts'].get(role) == r['sha256'], 'Build role does not match evidence')
        return self.resolve(r)

    def worker_copy(self, ref, destination, *, budget_bytes):
        """Create an exclusive disposable copy for a potentially mutating adapter."""
        r = validate('EvidenceRef', ref)
        _need(r['byte_length'] <= _size(budget_bytes), 'Worker copy exceeds explicit workspace budget')
        dest = Path(destination).absolute()
        _need(dest.parent.is_dir() and dest.parent.resolve() == dest.parent,
              'Worker directory must already exist without redirects')
        _need(not dest.is_relative_to(self.directory), 'Worker copy must be outside retained storage')
        result = self.resolve(r)
        _need(result['available'], result['reason'])
        policy = OutputPolicy(dest.parent, inputs=(self._path(r['sha256']),))
        with policy.check(dest).open('xb') as stream:
            stream.write(result['data'])
            stream.flush()
            os.fsync(stream.fileno())
        _need(verify_evidence_bytes(r, dest.read_bytes()), 'Worker copy integrity failure')
        return dest

    def restore(self, ref, retained_identical):
        """Restore absent bytes from one explicitly supplied retained identical file.

        Changed destinations are never repaired/overwritten. The source is read
        only; any interrupted partial destination remains diagnostic evidence.
        """
        source = Path(retained_identical)
        _need(source.is_file() and not source.is_symlink(), 'Invalid retained recovery source')
        r = validate('EvidenceRef', ref)
        _need(source.stat().st_size == r['byte_length'], 'Recovery source size differs')
        return self.register(r, source.read_bytes())

    def budget(self, additional_bytes):
        """Admission estimate; register rechecks under lock. No implicit eviction."""
        extra = _size(additional_bytes)
        with self._guard():
            used = sum(p.stat().st_size for p in self._files())
        allowed = used + extra <= self.budget_bytes
        return dict(used_bytes=used, budget_bytes=self.budget_bytes, requested_bytes=extra,
                    allowed=allowed, execution='not_run' if allowed else 'interrupted',
                    complete=False, reason='' if allowed else 'Budget exceeded; reduce declared batch or stop')

    def retention_plan(self, evidence):
        """Inventory and proposed actions only. No deletion execution exists."""
        refs = [validate('EvidenceRef', r) for r in evidence]
        _need(len({r['evidence_id'] for r in refs}) == len(refs), 'Duplicate evidence identity')
        with self._guard() as graph:
            by_digest = {}
            for r in refs:
                by_digest.setdefault(r['sha256'], []).append(r)
            for path in self._files():
                by_digest.setdefault(path.name, [])
            for key in ('pins',):
                for digest in graph[key]:
                    by_digest.setdefault(digest, [])
            for link in graph['references'] + graph['leases']:
                by_digest.setdefault(link['sha256'], [])
            rows = []
            for digest, associations in sorted(by_digest.items()):
                path = self._path(digest)
                exists = path.exists()
                data = path.read_bytes() if exists and path.is_file() else None
                size = len(data) if data is not None else None
                integrity = 'missing' if data is None else ('verified' if _hash(data) == digest and
                    all(r['byte_length'] == size for r in associations) else 'mismatch')
                reasons = []
                owner = graph['ownership'].get(digest, 'unknown')
                if owner != 'managed': reasons.append('ownership:' + owner)
                if integrity != 'verified': reasons.append('integrity:' + integrity)
                for link in graph['references']:
                    if link['sha256'] == digest: reasons.append('reference:' + link['kind'] + ':' + link['id'])
                if digest in graph['pins']: reasons.append('explicit_pin')
                for lease in graph['leases']:
                    if lease['sha256'] == digest and lease['active']: reasons.append('active_lease:' + lease['owner'])
                for r in associations:
                    if r['retention'] != 'disposable': reasons.append('evidence:' + r['retention'])
                rows.append(dict(sha256=digest, byte_length=size, integrity=integrity,
                    evidence_ids=[r['evidence_id'] for r in associations], reasons=sorted(set(reasons)),
                    action='retain' if reasons else 'propose_delete', recoverability='not_established'))
            report = dict(schema_version=1, dry_run=True, graph_revision=graph['revision'],
                          rows=rows, used_bytes=sum(r['byte_length'] or 0 for r in rows),
                          budget_bytes=self.budget_bytes)
            report['plan_sha256'] = _hash(json.dumps(report, sort_keys=True, separators=(',', ':')).encode())
            return report

    def recheck_plan(self, plan, evidence):
        """Fresh reference/lease/hash check; does not authorize or perform deletion."""
        fresh = self.retention_plan(evidence)
        _need(plan == fresh, 'Retention inventory changed; regenerate dry run')
        return fresh

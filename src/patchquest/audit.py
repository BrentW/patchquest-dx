"""Read-only candidate AND index audit. Heuristics require human review, not a security guarantee."""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

from .config import load_config
ROOT = Path(__file__).resolve().parents[2]

PATTERNS = {
    'absolute_local_path': re.compile(r'(?i)(?<![a-z0-9])(?:[a-z]:[\\/]|/(?:Users|home)/|\\\\(?!x[0-9a-f]{2})[a-z0-9_.-]+\\)'),
    'email_address': re.compile(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),
    'private_attachment_id': re.compile(r'codex-clipboard-[0-9a-f-]{36}|\.codex[/\\]attachments[/\\][0-9a-f-]{36}'),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
    'credential_pattern': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{24,})\b'),
    'credential_assignment': re.compile(r'''(?i)["']?(?:password|passwd|api_key|api-key|access_token|client_secret)["']?\s*[:=]\s*["'][^"'\s]{8,}["']'''),
    'private_host': re.compile(r'(?i)\b[a-z0-9-]+\.(?:local|internal|lan)\b'),
}
RESTRICTED_EXTENSIONS = {
    '.sfc', '.smc', '.nes', '.rom', '.bin', '.fig', '.swc', '.srm', '.sav', '.sta', '.frz', '.s9x', '.spc', '.rtc',
    '.bps', '.ips', '.ups', '.dump', '.dmp', '.log', '.tmp', '.bak', '.pem', '.key', '.p12', '.pfx',
    '.zip', '.7z', '.rar', '.exe', '.dll', '.png', '.jpg', '.jpeg', '.gif', '.bmp', '.wav', '.mp3', '.ttf', '.otf',
}


def git(root, *args, input=None):
    return subprocess.check_output(['git', '-C', str(root), *args], input=input, stderr=subprocess.PIPE)


def restricted_path(path):
    p = PurePosixPath(path)
    low = path.lower()
    return (low.startswith(('.local/', 'untranslated roms/', '.git/', 'projects/', 'private/', 'games/', 'notes/'))
            or (low.startswith('output/') and low != 'output/.gitkeep')
            or p.suffix.lower() in RESTRICTED_EXTENSIONS
            or bool(re.search(r'(?i)\.(?:state[^/]*|0[0-9][0-9]|pyc)$', low))
            or p.name.lower().startswith('.env') and p.name.lower() != '.env.example'
            or bool(re.search(r'(?i)\.local\.(?:json|toml|ini)$', low)))


def scan(path, data, terms=()):
    """Findings contain location/category only, never the matched secret or source line."""
    findings = []
    if restricted_path(path):
        findings.append({'category': 'excluded_or_restricted_path', 'line': None})
    try:
        content = data.decode('utf-8-sig')
        if any(ord(c) < 32 and c not in '\r\n\t' for c in content):
            raise UnicodeError()
    except UnicodeError:
        return findings + [{'category': 'binary_or_non_utf8_content', 'line': None}]
    terms = [re.compile(r'(?i)(?<!\w)' + re.escape(t.strip()) + r'(?!\w)') for t in terms if len(t.strip()) >= 3]
    for number, line in enumerate(content.splitlines(), 1):
        for category, pattern in PATTERNS.items():
            if pattern.search(line):
                findings.append({'category': category, 'line': number})
        if any(p.search(line) for p in terms):
            findings.append({'category': 'local_identity_term', 'line': number})
        for address in re.findall(r'(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])', line):
            try:
                if not ipaddress.ip_address(address).is_global:
                    findings.append({'category': 'non_public_network_address', 'line': number})
            except ValueError:
                pass
        # Network literals require review; don't confuse SNES hex addresses with hosts.
        for address in re.findall(r'\[([0-9a-fA-F:]+)\]', line):
            try:
                if not ipaddress.ip_address(address).is_global:
                    findings.append({'category': 'non_public_network_address', 'line': number})
            except ValueError:
                pass
    # A private identity in the filename is also publication data.
    if any(p.search(path) for p in terms):
        findings.append({'category': 'local_identity_in_path', 'line': None})
    return findings


def audit(root=ROOT, terms=()):
    root = Path(root)
    candidates = sorted(set(p.decode('utf-8') for p in git(root, 'ls-files', '--cached', '--others', '--exclude-standard', '-z').split(b'\0') if p))
    index = [p for p in git(root, 'ls-files', '--stage', '-z').split(b'\0') if p]
    ignored_index = {p.decode('utf-8') for p in git(root, 'ls-files', '--cached', '--ignored', '--exclude-standard', '-z').split(b'\0') if p}
    findings, manifest = [], []

    def inspect(path, data, surface):
        manifest.append({'path': path, 'surface': surface, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
        findings.extend({'path': path, 'surface': surface, **f} for f in scan(path, data, terms))

    for path in candidates:
        if not public_path(path):
            findings.append({'path':path,'surface':'working_tree','category':'outside_public_allowlist','line':None})
        p = root / path
        if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()):
            findings.append({'path': path, 'surface': 'working_tree', 'category': 'symlink_or_external_path', 'line': None})
        elif p.is_file():
            inspect(path, p.read_bytes(), 'working_tree')
        elif path not in ignored_index:
            findings.append({'path': path, 'surface': 'working_tree', 'category': 'missing_or_non_file', 'line': None})
    for entry in index:
        header, rawpath = entry.split(b'\t', 1)
        mode, oid, stage = header.split()
        path = rawpath.decode('utf-8')
        if not public_path(path):
            findings.append({'path':path,'surface':'index','category':'outside_public_allowlist','line':None})
        if mode not in (b'100644', b'100755') or stage != b'0':
            findings.append({'path': path, 'surface': 'index', 'category': 'non_regular_or_unmerged_entry', 'line': None})
        if mode in (b'100644', b'100755', b'120000'):
            inspect(path, git(root, 'cat-file', 'blob', oid.decode('ascii')), 'index')
        if path in ignored_index:
            findings.append({'path': path, 'surface': 'index', 'category': 'tracked_but_ignored', 'line': None})
    return {'candidate_files': len(candidates), 'index_entries': len(index), 'findings': findings, 'manifest': manifest,
            'status': 'review_required' if findings else 'no_heuristic_findings',
            'limitations': 'Human privacy and rights review required. No archive decoding or exhaustive secret detection. Optional history scanning is read-only; it never sanitizes Git objects. Public attribution is not automatically private data.'}


def local_terms(root=ROOT):
    terms = load_config(root)['privacy_terms']
    return sorted(set(terms + [v for key in ('USERNAME', 'USER', 'COMPUTERNAME') if (v := os.environ.get(key)) and len(v) >= 3]))



def public_path(path):
    """Publication surface: adding another directory requires deliberate review."""
    return (path in {'.gitignore','AGENTS.md','README.md','LOCALIZATION.md','TYPOGRAPHY.md',
                     'LICENSE','LICENSE-SCOPE.md','THIRD_PARTY_NOTICES.md','output/.gitkeep'}
            or path.startswith(('src/patchquest/','tests/','tools/','docs/','config/','templates/','examples/','assets/fonts/quest-pixel/','localization/','.agents/skills/')))


def history(root, terms=()):
    """Read all local objects, including unreachable blobs and internal tree refs."""
    refs=git(root,'for-each-ref','--format=%(refname) %(objecttype) %(objectname)').decode().splitlines()
    objects=git(root,'cat-file','--batch-all-objects','--batch-check=%(objectname) %(objecttype) %(objectsize)').decode().splitlines()
    counts={};findings=[]
    process=subprocess.Popen(['git','-C',str(root),'cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for item in objects:
            oid,kind,size=item.split();counts[kind]=counts.get(kind,0)+1
            if kind not in ('blob','commit','tag','tree'):continue
            process.stdin.write((oid+'\n').encode());process.stdin.flush()
            header=process.stdout.readline().split()
            if len(header)!=3 or header[0].decode()!=oid:raise ValueError('Unexpected Git object response')
            raw=process.stdout.read(int(header[2]));separator=process.stdout.read(1)
            if separator!=b'\n' or len(raw)!=int(size):raise ValueError('Truncated Git object')
            if kind=='tree':
                # Tree payload contains binary object IDs; scan its filenames separately.
                names=[];pos=0
                while pos<len(raw):
                    end=raw.index(b'\0',pos);names.append(raw[pos:end].split(b' ',1)[1]);pos=end+21
                raw=b'\n'.join(names)
            found=scan('object',raw,terms)
            if found:findings.append({'oid':oid,'kind':kind,'findings':found})
    finally:
        process.stdin.close();process.stdout.close();process.stderr.close();process.wait()
    return {'refs':refs,'object_counts':counts,'objects_with_findings':len(findings),'findings':findings,
            'note':'Private report. Internal refs and unreachable objects can retain private material even with no commits. Never publish a filesystem copy of .git or push with --mirror.'}

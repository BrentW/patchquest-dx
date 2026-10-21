"""Generic commands. Reports from actual projects remain private."""
import argparse
import json
import sys
from pathlib import Path

from .config import doctor
from .core.context import OutputPolicy, ProjectContext
from .core.edits import build, extract, load_source
from .consoles.snes.inspection import inspect
from .patches import bps
from .state import Conflict


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--platform', type=Path, default=Path(__file__).resolve().parents[2])
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    state = commands.add_parser('state', help='Private versioned records, memory, issues and progress as JSON')
    state.add_argument('manifest', type=Path)
    state.add_argument('action')
    state.add_argument('--input', type=Path, help='JSON parameters file; use - for stdin, omit for an empty object')
    studio = commands.add_parser('studio', help='Optional local Translation Studio; no private code execution')
    studio.add_argument('manifest', type=Path)
    studio.add_argument('--port', type=int, default=8765)
    studio.add_argument('--progress-interval', type=int, default=300,
                        help='Private progress report refresh in seconds (1–86400; default 300)')
    check = commands.add_parser('project-check', help='Validate a manifest and its source; never import its code')
    check.add_argument('manifest', type=Path)
    inspection = commands.add_parser('inspect', help='Read one explicitly selected file; keep output private')
    inspection.add_argument('source', type=Path)
    fds_inspection = commands.add_parser('fds-inspect', help='Inspect one explicit FDS container; keep its report private')
    fds_inspection.add_argument('source', type=Path)
    for name in ('extract', 'insert'):
        command = commands.add_parser(name)
        command.add_argument('source', type=Path)
        command.add_argument('manifest', type=Path)
        command.add_argument('destination', type=Path)
        command.add_argument('--output-root', type=Path, required=True)
    for name in ('bps-create', 'bps-apply'):
        command = commands.add_parser(name)
        command.add_argument('source', type=Path)
        command.add_argument('input', type=Path, help='Target ROM or BPS patch')
        command.add_argument('destination', type=Path)
        command.add_argument('--output-root', type=Path, required=True)
    font = commands.add_parser('font', help='Build an independent Quest Pixel specimen')
    font.add_argument('destination', type=Path)
    font.add_argument('--output-root', type=Path, required=True)
    audit = commands.add_parser('audit', help='Inspect candidate/index content and Git objects without modifying them')
    audit.add_argument('--report', type=Path, help='New private report inside .local/logs')
    audit.add_argument('--history', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'studio':
            from .studio import serve
            if not 0 <= args.port <= 65535:
                raise ValueError('Invalid port')
            serve(args.manifest, args.port, platform_root=args.platform, progress_interval=args.progress_interval)
            return 0
        elif args.command == 'state':
            from .state import Store
            from .state_api import execute
            payload = {} if args.input is None else json.loads(sys.stdin.read() if str(args.input) == '-' else args.input.read_text(encoding='utf-8-sig'))
            result = execute(Store(args.manifest), args.action, payload)
        elif args.command == 'doctor':
            result = doctor(args.platform)
        elif args.command == 'project-check':
            context = ProjectContext.load(args.manifest)
            context.read_source()
            result = {'manifest_valid': True, 'source_hash_matches': True, 'private_code_loaded': False}
        elif args.command == 'inspect':
            result = inspect(args.source)
        elif args.command == 'fds-inspect':
            from .storage.fds import inventory
            result = inventory(args.source.read_bytes())
        elif args.command in ('extract', 'insert'):
            manifest = json.loads(args.manifest.read_text(encoding='utf-8-sig'))
            source = load_source(args.source, manifest['source_sha256'])
            data = build(source, manifest['edits']) if args.command == 'insert' else (json.dumps(extract(source, manifest['ranges'], manifest.get('table')),ensure_ascii=False,indent=2)+'\n').encode()
            OutputPolicy(args.output_root,(args.source,args.manifest)).write_new(args.destination.resolve(),data)
            result = {'written': True, 'bytes': len(data)}
        elif args.command.startswith('bps-'):
            source, other = args.source.read_bytes(), args.input.read_bytes()
            data = bps.encode(source, other) if args.command == 'bps-create' else bps.apply(source, other)
            if args.command == 'bps-create' and bps.apply(source, data) != other:
                raise ValueError('BPS reconstruction failed')
            OutputPolicy(args.output_root,(args.source,args.input)).write_new(args.destination.resolve(),data)
            result = {'written': True, 'bytes': len(data)}
        elif args.command == 'font':
            from .typography.font import build as specimen, DEFAULT_FONT, DEFAULT_SPECIMEN
            result = specimen(DEFAULT_FONT, DEFAULT_SPECIMEN, args.destination, OutputPolicy(args.output_root,(DEFAULT_FONT,DEFAULT_SPECIMEN)))
        else:
            from .audit import audit, history, local_terms
            terms = local_terms(args.platform)
            report = audit(args.platform,terms)
            if args.history:
                report['git_history'] = history(args.platform,terms)
            if args.report:
                OutputPolicy(args.platform/'.local/logs').write_new(args.report.resolve(),(json.dumps(report,indent=2)+'\n').encode())
            result = {k:report[k] for k in ('status','candidate_files','index_entries')}
            result['finding_count'] = len(report['findings'])
            if args.history:
                result['history_objects_with_findings'] = report['git_history']['objects_with_findings']
            print(json.dumps(result,indent=2))
            return int(bool(report['findings']) or bool(report.get('git_history',{}).get('objects_with_findings')))
        print(json.dumps(result,indent=2))
        return 0
    except Conflict:
        print(json.dumps({'error':'conflict','message':'State changed or protected input differs. Reload and reconcile; do not blindly retry.'}))
        return 3
    except (ValueError,OSError,KeyError,TypeError) as error:
        # Exceptions may contain private paths, source identifiers or content.
        parser.exit(2, f'Validation failed ({type(error).__name__}); inspect private inputs and setup documentation.\n')

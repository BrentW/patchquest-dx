"""Optional local registry; no code loading or automatic project selection."""
import copy
import json
from pathlib import Path

DEFAULTS = {'schema_version': 2, 'projects': {}, 'emulators': {'snes9x': None, 'mesen': None}, 'privacy_terms': []}


def load_config(platform_root):
    path = Path(platform_root) / '.local/config/local.json'
    data = json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else {}
    if not isinstance(data, dict) or set(data) - set(DEFAULTS):
        raise ValueError('Unsupported configuration fields; migrate using the setup guide')
    config = copy.deepcopy(DEFAULTS)
    config.update(data)
    if type(config['schema_version']) is not int or config['schema_version'] != 2:
        raise ValueError('Unsupported local schema; preserve old configuration before migration')
    if not isinstance(config['projects'], dict) or not all(isinstance(k,str) and k and isinstance(v,str) and v for k,v in config['projects'].items()):
        raise ValueError('Projects must map local aliases to manifest paths')
    if not isinstance(config['emulators'], dict) or set(config['emulators']) - set(DEFAULTS['emulators']):
        raise ValueError('Unsupported emulator settings')
    if not all(v is None or (isinstance(v,str) and v.strip()) for v in config['emulators'].values()):
        raise ValueError('Emulator values must be paths or null')
    if not isinstance(config['privacy_terms'], list) or not all(isinstance(v,str) and len(v.strip())>=3 for v in config['privacy_terms']):
        raise ValueError('Privacy terms must be nonempty strings of at least three characters')
    config['emulators'] = {**DEFAULTS['emulators'], **config['emulators']}
    return config


def doctor(platform_root):
    root = Path(platform_root).resolve()
    data = load_config(root)
    return {'platform_api': 1, 'local_configuration': 'present' if (root/'.local/config/local.json').exists() else 'defaults',
            'registered_projects': len(data['projects']),
            'emulators': {k: {'configured': bool(v), 'file_exists': (root/v).is_file() if v else None} for k,v in data['emulators'].items()},
            'note': 'No project selected, ROM read, private code imported or executable launched.'}

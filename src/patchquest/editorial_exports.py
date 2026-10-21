"""Complete, exclusive private JSON snapshots shared by editorial workflows."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def write_snapshot(policy, destination, payload):
    if not isinstance(destination, str) or not destination or Path(destination).is_absolute():
        raise ValueError('Use a new relative output path')
    data = (json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode('utf8')
    target = policy.check(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    policy.check(target)
    if target.exists():
        raise FileExistsError('Editorial exports must use a fresh destination')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, prefix='.editorial-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        policy.check(target)
        os.link(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return dict(path=str(target), sha256=hashlib.sha256(data).hexdigest())

"""Source-checkout launcher; no installation or external packages required."""
from pathlib import Path
import sys

if __name__ == '__main__':
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from patchquest.cli import main
    raise SystemExit(main())

"""Regenerate thin Claude discovery files, or check for drift without editing."""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from patchquest.agents import sync

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    result=sync(ROOT,args.check)
    print(json.dumps(result,indent=2))
    raise SystemExit(int(bool(result['extra_skills']) or (args.check and not result['matching'])))

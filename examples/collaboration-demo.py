"""Create a ROM-free coordination trial. Does not launch or contact an AI provider."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from patchquest.state import Store
from patchquest.collaboration import Coordination


def create(workspace):
    spec=importlib.util.spec_from_file_location('studio_demo',ROOT/'examples/studio-demo.py')
    demo=importlib.util.module_from_spec(spec);spec.loader.exec_module(demo)
    manifest=demo.create(workspace);store=Store(manifest)
    data=store.get('greeting')
    for key in ('revision','human_corrected','provenance'):data.pop(key)
    data['target']='Welcome to Lantern Harbor.'
    store.put(data,1,'human','Synthetic fixture author','Protected correction for compatibility checks')
    work=Coordination(store)
    work.create('review-greeting','Review a protected greeting',record_ids=['greeting'],
                instructions='Read memory and context. Suggest an alternative without replacing the human correction. Leave a handoff.')
    work.create('review-lantern','Review an unprotected line',record_ids=['lantern'],dependencies=['review-greeting'],
                instructions='Read predecessor handoff, memory and glossary. Improve the lantern wording without changing meaning or controls.')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    print(create(parser.parse_args().workspace))

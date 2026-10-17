"""Entirely invented Studio data. Creates no ROM and calls no AI provider."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from patchquest.core.context import OutputPolicy
from patchquest.state import Store


def create(workspace):
    root=Path(workspace).resolve()
    if root.exists():raise FileExistsError('Choose a fresh demonstration workspace')
    policy=OutputPolicy(root)
    manifest={'schema_version':1,'platform_api':1,'project_id':'invented-lantern-demo',
              'source':{'path':'unprovided-fictional-source','sha256':hashlib.sha256(b'invented fixture, no ROM').hexdigest()},
              'resources':{},'output_directory':'output','data':{'title':'Lantern Harbor · Synthetic demo'}}
    path=policy.write_new('project.json',(json.dumps(manifest,indent=2)+'\n').encode())
    store=Store(path)
    rows=[('greeting','こんにちは。','Hello.','Guide'),('lantern','あかりの用意ができました。','The lantern is ready.','Keeper'),
          ('choice','どちらに行きますか。','Which way will you go?','Guide'),('unknown','まだわかりません。','','')]
    store.import_records([{'id':key,'source':source,'target':target,'speaker':speaker,'scene':'Invented harbor',
                           'category':'dialogue','decoded':True,'uncertainty':'Context not yet established' if not target else '',
                           'context':{'provenance':'Newly authored synthetic demo; not extracted from a game.'},
                           'controls':[],'build_binding':{'mode':'demonstration only'}} for key,source,target,speaker in rows])
    store.put({'id':'term-lantern','kind':'glossary','source':'あかり','target':'lantern','category':'invented setting',
               'context':{'scope':'Use only where an actual lantern is intended.'},'decoded':True},0,'human','Demo author')
    store.activity('Synthetic demonstration initialized; no agent is running.','Demo','idle')
    return path


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--workspace',type=Path,required=True)
    args=parser.parse_args();print(create(args.workspace))

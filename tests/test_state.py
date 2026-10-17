"""Invented records only; no ROM collection or external private project required."""
import copy
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from _bootstrap import ROOT
from patchquest.state import Store, Conflict, canonical

# Authored one-pixel PNG fixture, unrelated to any game or private screenshot.
PIXEL = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')


def project(root):
    manifest=root/'project.json'
    manifest.write_text(json.dumps({'schema_version':1,'platform_api':1,'project_id':'invented-demo',
        'source':{'path':'original.fixture','sha256':hashlib.sha256(b'fictional input').hexdigest()},
        'resources':{},'output_directory':'output'}),encoding='utf8')
    # Browsing and editing intentionally do not require opening the source.
    return manifest


def invented(key='line-01',target='The lantern is ready.'):
    return {'id':key,'source':'あかりの用意ができました。','target':target,
            'speaker':'Invented guide','scene':'Invented harbor','category':'dialogue',
            'context':{'note':'Synthetic language example authored for tests.'},
            'controls':['<pause>'],'decoded':True,'build_binding':{'adapter':'synthetic'}}


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.manifest=project(self.root);self.store=Store(self.manifest)

    def test_human_precedence_and_stale_proposals(self):
        r=invented();self.store.put(r,0)
        human=dict(r,target='The lantern is lit.')
        self.store.put(human,1,'human')
        with self.assertRaises(Conflict):self.store.put(dict(r,target='Outdated'),1)
        result=self.store.put(dict(r,target='Suggested wording'),2,'agent','other provider')
        self.assertEqual(result['outcome'],'proposed')
        self.assertEqual(self.store.get(r['id'])['target'],human['target'])
        self.assertEqual(self.store.proposals(r['id'])[0]['payload']['target'],'Suggested wording')
        self.store.restore(r['id'],1,2)
        self.assertTrue(self.store.get(r['id'])['human_corrected'])
        self.assertEqual(self.store.get(r['id'])['revision'],3)
        self.assertEqual(len(self.store.history(r['id'])),3)

    def test_simultaneous_writers_cannot_lose_updates(self):
        self.store.put(invented(),0)
        def write(n):
            try:return self.store.put(invented(target=str(n)),1,'human')['outcome']
            except Conflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=8) as workers:results=list(workers.map(write,range(8)))
        self.assertEqual(results.count('saved'),1);self.assertEqual(results.count('conflict'),7)
        self.assertEqual(len(self.store.history('line-01')),2)

    def test_import_is_atomic_idempotent_and_respects_later_edits(self):
        self.store.import_records([invented()])
        with self.assertRaises(Conflict):self.store.import_records([invented('new'),invented(target='different')])
        with self.assertRaises(KeyError):self.store.get('new')
        self.store.put(invented(target='User correction'),1,'human')
        self.assertEqual(self.store.import_records([invented()]),{'imported':0,'existing':1})
        self.assertEqual(self.store.get('line-01')['target'],'User correction')
        with self.assertRaises(ValueError):self.store.import_records([invented('new'),invented('new')])

    def test_snapshots_are_consistent_and_independent_of_memory(self):
        self.store.put(invented(),0)
        frozen=self.store.snapshot();path=Path(self.store.export_snapshot(frozen['sha256']))
        self.store.activity('Something else is happening')
        self.store.rebuild_memory()
        self.assertEqual(self.store.snapshot()['sha256'],frozen['sha256'])
        self.store.put(invented(target='Updated'),1)
        self.assertNotEqual(self.store.snapshot()['sha256'],frozen['sha256'])
        self.assertEqual(json.loads(path.read_text(encoding='utf8')),frozen['data'])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),frozen['sha256'])
        self.assertEqual(self.store.export_snapshot(frozen['sha256']),str(path))
        path.write_text('corrupt')
        with self.assertRaises(ValueError):self.store.export_snapshot(frozen['sha256'])

    def test_memory_context_glossary_and_protected_historical_revisions(self):
        self.store.put(invented(),0)
        other=invented('line-02');self.store.put(other,0)
        self.store.put(dict(other,target='Human variant'),1,'human')
        term=invented('term');term.update(kind='glossary',source='あかり',target='lantern')
        self.store.put(term,0,'human')
        result=self.store.memory(key='line-01')
        self.assertTrue(any(r['id']=='term' and r['kind']=='glossary' for r in result))
        self.assertTrue(any(r['target']=='Human variant' and r['human_corrected'] for r in result))
        self.assertTrue(any(r['id']=='line-02' and not r['current'] for r in result))
        self.assertEqual(self.store.get('line-01')['target'],invented()['target'])

    def test_stage_evidence_is_revision_specific_and_not_implied(self):
        self.store.put(invented(),0)
        self.store.put(invented('unknown',''),0)
        self.store.evidence('line-01',1,'automated',True,'synthetic-test')
        counts=self.store.overview()['counts']
        self.assertEqual(counts['translated'],1);self.assertEqual(counts['automated'],1)
        self.assertEqual(counts['inserted'],0);self.assertEqual(counts['emulator'],0)
        self.store.put(invented(target='Edited'),1,'human')
        self.assertEqual(self.store.overview()['counts']['automated'],0)
        self.assertEqual(len(self.store.record_evidence('line-01')),1)
        with self.assertRaises(ValueError):self.store.evidence('line-01',2,'emulator',True,'')

    def test_persistence_backup_and_event_cursor(self):
        self.store.put(invented(),0);self.store.activity('Synthetic task',status='working')
        cursor=self.store.overview()['cursor'];self.store.activity('Done',status='finished')
        self.assertEqual(len(self.store.events(cursor)),1)
        backup=self.store.backup()
        # SQLite's transaction context does not close the connection. Release the
        # backup handle before TemporaryDirectory cleanup, including on Windows.
        with closing(sqlite3.connect(backup)) as db:self.assertEqual(db.execute('SELECT count(*) FROM revisions').fetchone()[0],1)
        reopened=Store(self.manifest)
        self.assertEqual(reopened.get('line-01')['target'],invented()['target'])
        self.assertEqual(reopened.overview()['activity']['payload']['status'],'finished')

    def test_issue_history_and_build_approval_separation(self):
        self.store.put(invented(),0)
        issue={'id':'issue-1','title':'Synthetic concern','record_ids':['line-01']}
        self.store.put_issue(issue,0,'tester')
        self.store.put_issue(dict(issue,status='resolved'),1,'agent')
        with self.assertRaises(Conflict):self.store.put_issue(issue,1)
        self.assertEqual(len(self.store.issue_history('issue-1')),2)
        snapshot=self.store.snapshot()
        self.store.build({'id':'test-build','snapshot':snapshot['sha256'],'status':'validated'},0)
        self.assertFalse(self.store.builds()[0].get('approval',{}).get('approved',False))
        self.assertEqual(self.store.overview()['counts']['automated'],0)
        with self.assertRaises(ValueError):self.store.build({'id':'bad','status':'validated','approval':{'approved':True}},0)

    def test_filters_and_empty_catalog(self):
        self.assertIsNone(self.store.overview()['percentages']['translated'])
        self.store.import_records([invented(),dict(invented('line-02'),uncertainty='Ambiguous'),invented('line-03','')])
        self.assertEqual(self.store.list(status='uncertain')['total'],1)
        self.assertEqual(self.store.list(query='あかり',speaker='Invented guide',limit=1)['total'],3)
        self.assertEqual(self.store.list(query="' OR 1=1 --")['total'],0)
        with self.assertRaises(ValueError):self.store.list(limit=10000)
        with self.assertRaises(ValueError):self.store.put(dict(invented(),decoded='yes'),0)

    def test_wrong_project_state_is_rejected(self):
        data=json.loads(self.manifest.read_text());data['project_id']='different';self.manifest.write_text(json.dumps(data))
        with self.assertRaises(ValueError):Store(self.manifest)

    def test_state_cannot_overlap_protected_inputs_even_before_they_exist(self):
        for resource in ('.patchquest/not-created.json', '.patchquest'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);manifest=project(root)
                data=json.loads(manifest.read_text())
                data['resources']={'language':resource}
                manifest.write_text(json.dumps(data))
                with self.assertRaises(ValueError):Store(manifest)
                self.assertFalse((root/'.patchquest').exists())

    def test_private_image_registration_integrity_and_path_boundary(self):
        self.store.put(invented(),0)
        path=self.root/'synthetic.png';path.write_bytes(PIXEL)
        attachment=self.store.attach(path,'Invented fixture',['line-01'])
        self.assertEqual(self.store.image(attachment['digest']),(PIXEL,'image/png'))
        self.assertEqual(len(self.store.attachments('line-01')),1)
        self.assertEqual(self.store.attachments('unrelated'),[])
        with self.assertRaises(Conflict):self.store.attach(path,'Changed association',[])
        with tempfile.TemporaryDirectory() as temp:
            external=Path(temp)/'external.png';external.write_bytes(PIXEL)
            with self.assertRaises(ValueError):self.store.attach(external)
        path.write_bytes(b'<svg>untrusted content</svg>')
        with self.assertRaises(ValueError):self.store.attach(path)
        (self.store.directory/'evidence'/attachment['digest']).write_bytes(b'changed')
        with self.assertRaises(ValueError):self.store.image(attachment['digest'])

    def test_cli_json_input_and_restart(self):
        command=[sys.executable,'-B',str(ROOT/'tools/patchquest.py'),'state',str(self.manifest)]
        first=subprocess.run(command+['put','--input','-'],input=json.dumps({'data':invented(),'expected':0}),capture_output=True,text=True)
        self.assertEqual(first.returncode,0,first.stderr)
        second=subprocess.run(command+['get','--input','-'],input=json.dumps({'key':'line-01'}),capture_output=True,text=True)
        self.assertEqual(json.loads(second.stdout)['target'],invented()['target'])

    def test_state_symlink_escape(self):
        with tempfile.TemporaryDirectory() as other:
            root=Path(other);manifest=project(root)
            try:(root/'.patchquest').symlink_to(self.root/'.patchquest',target_is_directory=True)
            except OSError as error:self.skipTest(str(error))
            with self.assertRaises(ValueError):Store(manifest)


if __name__=='__main__':unittest.main()

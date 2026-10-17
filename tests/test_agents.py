from pathlib import Path
import re
import shutil
import tempfile
import unittest

from _bootstrap import ROOT
from patchquest.agents import sync, expected_files
from patchquest.state import Store
from patchquest.state_api import execute
from test_state import project


class AgentCompatibilityTests(unittest.TestCase):
    def test_context_preserves_explicit_manifest_filename(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'selected project';root.mkdir()
            manifest=project(root)
            selected=manifest.rename(root/'translation-manifest.json')
            store=Store(selected)
            packet=execute(store,'agent-context')
            self.assertEqual(Path(packet['project_manifest']),selected.resolve())
            # A second agent must be able to reopen the exact advertised project.
            reopened=Store(packet['project_manifest'])
            self.assertEqual(reopened.context.manifest,store.context.manifest)

    def test_actual_adapters_are_current_and_links_resolve(self):
        self.assertTrue(sync(ROOT,check=True)['matching'])
        for name,content in expected_files(ROOT).items():
            for link in re.findall(r'\]\(([^)]+)\)',content):
                self.assertTrue((ROOT/name).parent.joinpath(link).resolve().is_file(),link)
        self.assertIn('@AGENTS.md',(ROOT/'CLAUDE.md').read_text())

    def test_fresh_copy_spaces_and_drift_detection(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)/'fresh source with spaces';root.mkdir()
            shutil.copy2(ROOT/'AGENTS.md',root/'AGENTS.md')
            shutil.copytree(ROOT/'.agents',root/'.agents')
            self.assertFalse(sync(root,check=True)['matching'])
            sync(root);self.assertTrue(sync(root,check=True)['matching'])
            path=next((root/'.agents/skills').glob('*/SKILL.md'))
            path.write_bytes(path.read_text().replace('\n','\r\n').encode('utf8'))
            self.assertTrue(sync(root,check=True)['matching'], 'Git line-ending conversion must not cause drift')
            path.write_text(path.read_text()+'\nUpdated synthetic maintenance note.\n')
            self.assertFalse(sync(root,check=True)['matching'])
            sync(root);self.assertTrue(sync(root,check=True)['matching'])
            (root/'AGENTS.md').unlink()
            with self.assertRaises(ValueError):expected_files(root)

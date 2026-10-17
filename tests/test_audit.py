import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import _bootstrap
from patchquest.audit import audit, scan, history, public_path


class PublicationAuditTests(unittest.TestCase):
    def test_approved_notices_remain_subject_to_privacy_scanning(self):
        for path in ('LICENSE','LICENSE-SCOPE.md','THIRD_PARTY_NOTICES.md',
                     'assets/fonts/quest-pixel/LICENSE-CC-BY-3.0.txt'):
            self.assertTrue(public_path(path))
            secret=('gh'+'p_'+'a'*30).encode()
            self.assertTrue(any(f['category']=='credential_pattern' for f in scan(path,secret)))
        self.assertFalse(public_path('LICENSE-private-notes.md'))
        self.assertFalse(public_path('.git/LICENSE'))

    def test_paths_credentials_and_binary_are_reported_without_values(self):
        # Construct synthetic examples so the repository audit does not flag its own fixtures.
        text = '\n'.join(['C' + ':/' + 'Users/private-person/source',
                          'contact' + '@' + 'example.invalid',
                          '10' + '.20.30.40',
                          'pass' + 'word = "' + 'demonstration-only' + '"',
                          'gh' + 'p_' + 'a'*30])
        result = scan('notes.md', text.encode())
        categories = {x['category'] for x in result}
        self.assertTrue({'absolute_local_path', 'email_address', 'non_public_network_address',
                         'credential_assignment', 'credential_pattern'} <= categories)
        self.assertNotIn('demonstration-only', json.dumps(result))
        self.assertEqual(scan('notes.md', b'\0\xff')[0]['category'], 'binary_or_non_utf8_content')
        self.assertTrue(scan('private-person.md', b'ok', ['private-person']))
        separator = chr(92)
        self.assertTrue(scan('note.md', (separator*2 + 'server' + separator + 'share' + separator + 'file').encode()))

    def test_technical_addresses_hashes_urls_and_public_credit_are_retained(self):
        text = 'PPU register 0x2100 CPU bank 80 SHA256 ' + 'a'*64 + '\nhttps://example.org/docs\nPatrick H. Lauke (redux)\n'
        self.assertEqual(scan('notes.md', text.encode()), [])
        self.assertEqual(scan('inventory.json', json.dumps({'title': r'\xdf\xdd\xfe'}).encode()), [])

    def test_index_secrets_tracked_ignored_files_and_worktree_all_checked(self):
        # An isolated synthetic repository only. Never stages the real workspace.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', '-C', tmp, *args], stderr=subprocess.PIPE)
            git('init', '-q')
            (root/'.gitignore').write_text('/.local/\n*.sfc\n', encoding='utf-8')
            (root/'.local').mkdir()
            (root/'.local/private.txt').write_text('private', encoding='utf-8')
            (root/'bad.sfc').write_bytes(b'fake ROM')
            secret = 'gh' + 'p_' + 'z'*30
            (root/'note.md').write_text(secret, encoding='utf-8')
            git('add', 'note.md')
            git('add', '-f', 'bad.sfc', '.local/private.txt')
            (root/'note.md').write_text('clean working tree', encoding='utf-8')
            before = (root/'.git/index').read_bytes()
            report = audit(root)
            self.assertEqual(report['index_entries'], 3)
            self.assertTrue(any(f['surface'] == 'index' and f['category'] == 'credential_pattern' for f in report['findings']))
            self.assertEqual(len([f for f in report['findings'] if f['category'] == 'tracked_but_ignored']), 2)
            self.assertNotIn(secret, json.dumps(report))
            self.assertEqual((root/'.git/index').read_bytes(), before)
            self.assertEqual(git('rev-list', '--all', '--count').strip(), b'0')
            git('read-tree', '--empty')
            objects=history(root)
            self.assertGreater(objects['objects_with_findings'],0)
            self.assertEqual(objects['object_counts'].get('commit',0),0)


if __name__ == '__main__':
    unittest.main()

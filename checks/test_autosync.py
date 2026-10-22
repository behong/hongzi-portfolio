import json
from pathlib import Path
import sys
import shutil
import uuid
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from AutoSync import blob_sha, sync, target_path


class FakeGitHub:
    def __init__(self, commit, files):
        self.commit = commit
        self.files = files
        self.downloads = 0

    def head(self):
        return self.commit

    def tree(self, commit):
        return {name: blob_sha(data) for name, data in self.files.items()}

    def download(self, sha):
        self.downloads += 1
        return next(data for data in self.files.values() if blob_sha(data) == sha)


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        test_root = Path(__file__).resolve().parents[1] / '.tools' / 'test-autosync'
        self.root = test_root / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        def cleanup():
            assert self.root.resolve().is_relative_to(test_root.resolve())
            shutil.rmtree(self.root)
        self.addCleanup(cleanup)
        self.runtime = self.root / '.tools' / 'autosync'
        self.runtime.mkdir(parents=True)
        self.file = self.root / 'site' / 'index.html'
        self.file.parent.mkdir()
        self.file.write_bytes(b'old homepage')
        self.github = FakeGitHub('first', {'site/index.html': b'old homepage'})
        sync(self.root, self.runtime, self.github)

    def test_unchanged_commit_does_not_download(self):
        self.assertEqual(sync(self.root, self.runtime, self.github), [])
        self.assertEqual(self.github.downloads, 0)

    def test_update_add_delete_and_backup(self):
        self.github = FakeGitHub('second', {'site/new.html': b'new page'})
        self.assertCountEqual(sync(self.root, self.runtime, self.github), ['site/index.html', 'site/new.html'])
        self.assertFalse(self.file.exists())
        self.assertEqual((self.root / 'site/new.html').read_bytes(), b'new page')
        self.assertEqual((self.runtime / 'backups/second/site/index.html').read_bytes(), b'old homepage')

    def test_local_edits_block_entire_update(self):
        self.file.write_bytes(b'local work')
        self.github = FakeGitHub('second', {'site/index.html': b'remote work', 'site/new.html': b'new'})
        with self.assertRaisesRegex(RuntimeError, 'Local changes preserved'):
            sync(self.root, self.runtime, self.github)
        self.assertEqual(self.file.read_bytes(), b'local work')
        self.assertFalse((self.root / 'site/new.html').exists())
        self.assertEqual(json.loads((self.runtime / 'state.json').read_text())['commit'], 'first')

    def test_remote_deletion_preserves_locally_edited_file(self):
        self.file.write_bytes(b'local work')
        self.github = FakeGitHub('second', {})
        with self.assertRaises(RuntimeError):
            sync(self.root, self.runtime, self.github)
        self.assertTrue(self.file.exists())

    def test_failed_download_changes_no_files(self):
        self.github = FakeGitHub('second', {'site/index.html': b'new'})
        def fail(sha):
            raise RuntimeError('network unavailable')
        self.github.download = fail
        with self.assertRaises(RuntimeError):
            sync(self.root, self.runtime, self.github)
        self.assertEqual(self.file.read_bytes(), b'old homepage')

    def test_protected_and_escaping_paths_rejected(self):
        for name in ['../outside', '/outside', '.secrets/tunnel.json', '.git/config', '.GIT/config', '.tools/state.json', '.env', '.ENV.local', '.env.local', 'C:/outside', 'site\\..\\outside']:
            with self.subTest(name=name), self.assertRaises(ValueError):
                target_path(self.root, name)

    def test_new_remote_commit_can_recover_after_partial_application(self):
        self.file.write_bytes(b'new homepage')
        self.github = FakeGitHub('second', {'site/index.html': b'new homepage'})
        sync(self.root, self.runtime, self.github)
        self.assertEqual(json.loads((self.runtime / 'state.json').read_text())['commit'], 'second')

    def test_edit_during_download_is_preserved(self):
        self.github = FakeGitHub('second', {'site/index.html': b'new'})
        def download_with_local_edit(sha):
            self.file.write_bytes(b'concurrent local edit')
            return b'new'
        self.github.download = download_with_local_edit
        with self.assertRaisesRegex(RuntimeError, 'changed during download'):
            sync(self.root, self.runtime, self.github)
        self.assertEqual(self.file.read_bytes(), b'concurrent local edit')

    def test_directory_to_file(self):
        self.github = FakeGitHub('second', {'site': b'site is now a file'})
        sync(self.root, self.runtime, self.github)
        self.assertEqual((self.root / 'site').read_bytes(), b'site is now a file')

    def test_file_to_directory(self):
        self.github = FakeGitHub('second', {'site/index.html/child.txt': b'child'})
        sync(self.root, self.runtime, self.github)
        self.assertEqual((self.file / 'child.txt').read_bytes(), b'child')

    def test_directory_to_file_preserves_untracked_content(self):
        (self.root / 'site/local.txt').write_bytes(b'local')
        self.github = FakeGitHub('second', {'site': b'replacement'})
        with self.assertRaises(RuntimeError):
            sync(self.root, self.runtime, self.github)
        self.assertEqual((self.root / 'site/local.txt').read_bytes(), b'local')


if __name__ == '__main__':
    unittest.main()

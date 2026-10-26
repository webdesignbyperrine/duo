import hashlib
import io
import json
import os
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import desktop_setup
import runtime_paths
import projects

class DesktopTests(unittest.TestCase):
    def test_installed_app_never_discovers_host_assistants_or_accounts(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runtime_paths,'DESKTOP',True), patch.dict(os.environ,{'DUO_DATA_DIR':folder,'OPENAI_API_KEY':'not-a-real-key','ANTHROPIC_API_KEY':'not-a-real-key','CODEX_HOME':'/some/other/profile','CLAUDE_CONFIG_DIR':'/some/other/profile'}):
            env=runtime_paths.provider_environment()
            self.assertEqual(Path(env['CODEX_HOME']),Path(folder).resolve()/'accounts/codex')
            self.assertEqual(Path(env['CLAUDE_CONFIG_DIR']),Path(folder).resolve()/'accounts/claude')
            self.assertNotIn('OPENAI_API_KEY',env);self.assertNotIn('ANTHROPIC_API_KEY',env)
            self.assertEqual(list(Path(env['CODEX_HOME']).iterdir()),[])
            with patch.object(runtime_paths.shutil,'which',return_value='/existing/account/codex'):
                with self.assertRaises(RuntimeError):runtime_paths.provider_binary('codex')
            tools=Path(folder).resolve()/'tools';tools.mkdir();binary=tools/('codex.exe' if os.name=='nt' else 'codex');binary.write_bytes(b'test')
            self.assertEqual(runtime_paths.provider_binary('codex'),str(binary))

    def test_download_rejects_untrusted_urls_before_network(self):
        with patch.object(desktop_setup.urllib.request,'build_opener') as network:
            with self.assertRaises(ValueError):desktop_setup.download_verified({'url':'https://untrusted.example/program','sha256':'a'*64},lambda x:None)
            network.assert_not_called()

    def test_bad_integrity_never_installs(self):
        class Reply(io.BytesIO):headers={'Content-Length':'4'}
        opener=unittest.mock.Mock();opener.open.return_value=Reply(b'data')
        with patch.object(desktop_setup.urllib.request,'build_opener',return_value=opener):
            with self.assertRaisesRegex(ValueError,'Empreinte'):
                desktop_setup.download_verified({'url':'https://downloads.claude.ai/test','sha256':'a'*64},lambda x:None)

    def test_archive_extraction_never_writes_archive_paths(self):
        data=io.BytesIO()
        with tarfile.open(fileobj=data,mode='w:gz') as archive:
            entry=tarfile.TarInfo('../../codex-platform');entry.size=4;archive.addfile(entry,io.BytesIO(b'data'))
        # Only bytes of the single regular executable are returned, never extractall.
        self.assertEqual(desktop_setup.extract_executable(data.getvalue(),'tar.gz','codex'),b'data')

    def test_folder_ignores_work_without_git(self):
        contents={'.gitignore':b'ignored/\n*.secret\n!keep.secret\n','src/.gitignore':b'local.txt\n','src/local.txt':b'a','src/main.ts':b'a','ignored/a.ts':b'a','private.secret':b'a','keep.secret':b'a'}
        with patch.object(projects.shutil,'which',return_value=None):
            ignored=projects.git_ignored(list(contents),contents)
        self.assertEqual(ignored,{'ignored/a.ts','private.secret','src/local.txt'})

    def test_no_formula_workbook_works_without_office_and_formula_is_explicit(self):
        from file_factory import create_workbook
        with tempfile.TemporaryDirectory() as folder,patch('file_factory.office_binary',return_value=None):
            create_workbook(Path(folder)/'plain.xlsx',json.dumps({'sheets':[{'rows':[['Budget'],[1200]]}]}))
            with self.assertRaisesRegex(ValueError,'LibreOffice'):
                create_workbook(Path(folder)/'formula.xlsx',json.dumps({'sheets':[{'rows':[['Budget'],[1200]],'formulas':[{'cell':'B2','formula':'=A2*2'}]}]}))

if __name__=='__main__':unittest.main()

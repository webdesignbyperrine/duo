import base64
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

import projects
import server
from workflows import prompt_for


class ProjectTests(unittest.TestCase):
    def test_project_filters_secrets_dependencies_gitignore_and_binary(self):
        value=projects.prepare_project('Mon projet',{
            'src/index.ts':b'export function solde(budget: number, depense: number) { return budget-depense; }',
            'package.json':b'{"scripts":{"postinstall":"DO_NOT_EXECUTE"}}',
            '.gitignore':b'ignored/\n',
            'ignored/file.ts':b'ignored content',
            'node_modules/tool/index.js':b'dependency content',
            '.env.local':b'TOKEN=PRIVATE_ENV_VALUE',
            'src/secrets.ts':b'const api_key = "super_private_value_to_exclude_9283092";',
            'src/picture.custom':b'\x00\x01\x02',
            'large.txt':b'x'*(projects.MAX_CODE_FILE+1),
        })
        included={f['path'] for f in value['project_manifest']}
        self.assertEqual(included,{'src/index.ts','package.json','.gitignore'})
        omitted={f['path'] for f in value['project_excluded']}
        self.assertTrue({'.env.local','src/secrets.ts','node_modules/tool/index.js','ignored/file.ts','src/picture.custom','large.txt'}<=omitted)
        with zipfile.ZipFile(io.BytesIO(value['raw'])) as archive:
            self.assertFalse(any(b'PRIVATE_ENV_VALUE' in archive.read(n) for n in archive.namelist()))

    def test_folder_upload_keeps_paths_and_materializes_same_bytes(self):
        value=projects.from_upload({'name':'exemple','files':[{'path':'src/main.ts','content':base64.b64encode(b'export const marker = 938201;').decode()},{'path':'node_modules/*','skipped':'excluded'}]})
        value['id']='P-demo'
        with tempfile.TemporaryDirectory() as folder:
            projects.materialize([value],folder)
            self.assertEqual((Path(folder)/'projects/P-demo/src/main.ts').read_bytes(),b'export const marker = 938201;')
            self.assertFalse((Path(folder)/'projects/P-demo/node_modules').exists())
            manifest=json.loads((Path(folder)/'project_manifests/P-demo.json').read_text())
            self.assertEqual(manifest['included'][0]['path'],'src/main.ts')

    def test_paths_cannot_escape_snapshot(self):
        for path in ('../outside.txt','/tmp/outside.txt','src/../../x.ts','a\\b.ts'):
            with self.subTest(path=path),self.assertRaises(ValueError):
                projects.from_upload({'name':'bad','files':[{'path':path,'content':'YWJj'}]})

    def test_github_urls_are_restricted_and_normalized(self):
        self.assertEqual(projects.github_url('git@github.com:octocat/Hello-World.git')[0],'https://github.com/octocat/Hello-World.git')
        for url in ('https://github.com.evil.example/a/b','file:///tmp/repo','https://user:token@github.com/a/b','https://github.com/a/b/tree/main','https://github.com/a/b?token=secret'):
            with self.subTest(url=url),self.assertRaises(ValueError):projects.github_url(url)

    def test_large_code_is_available_via_files_not_silently_inlined(self):
        value=projects.prepare_project('code',{'src/long.ts':b'// ligne de code a lire dans le fichier\n'*5000})
        value['id']='P-large'
        prompt=prompt_for('Codex','Analyse ce projet',[value],[],'Donne ton avis',False)
        self.assertNotIn('// ligne de code',prompt)
        self.assertIn('projects/P-large',prompt)
        self.assertIn('project_manifests/P-large.json',prompt)
        self.assertGreater(value['project_bytes'],140000)

    def test_project_survives_bundle_and_metadata(self):
        value=projects.prepare_project('code',{'README.md':b'Projet de demonstration'})
        value['id']='P-code';d=server.Discussion();d.sources[value['id']]=value;d.active_sources=[value]
        metadata=d.list_sources()[0]
        self.assertTrue(metadata['is_project']);self.assertEqual(metadata['project_files'],1)
        with zipfile.ZipFile(io.BytesIO(d.bundle())) as archive:
            self.assertIn('projets/P-code-inventaire.json',archive.namelist())
            snapshot=archive.read('pieces-originales/P-code-code.zip')
            with zipfile.ZipFile(io.BytesIO(snapshot)) as project:self.assertEqual(project.read('README.md'),b'Projet de demonstration')

    def test_tampered_snapshot_is_not_sent_to_models(self):
        value=projects.prepare_project('code',{'main.ts':b'original'});value['id']='P-code'
        fake=io.BytesIO()
        with zipfile.ZipFile(fake,'w') as archive:archive.writestr('main.ts',b'changed')
        value['raw']=fake.getvalue()
        with tempfile.TemporaryDirectory() as folder,self.assertRaisesRegex(RuntimeError,'changé'):
            projects.materialize([value],folder)


if __name__=='__main__':unittest.main()

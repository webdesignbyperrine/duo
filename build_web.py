"""Build statique : aucun code serveur, compte ou résultat dans le site publié."""
from pathlib import Path
import shutil
import zipfile
ROOT = Path(__file__).resolve().parent
WEB = ROOT / 'web'
if WEB.exists():
    shutil.rmtree(WEB)
WEB.mkdir()
shutil.copyfile(ROOT / 'index.html', WEB / 'index.html')
files = ['server.py','sessions.py','attachments.py','projects.py','workflows.py','file_factory.py','ocr.swift','Ouvrir Duo.command','README.txt','hosting.json','runtime_paths.py','desktop_setup.py','worker.py','desktop_entry.py']
with zipfile.ZipFile(WEB / 'duo-mac.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(ROOT / name, 'Duo/' + name)
    if (ROOT / 'bin/duo-ocr').is_file():
        archive.write(ROOT / 'bin/duo-ocr', 'Duo/bin/duo-ocr')
    for name in ['providers.lock.json','ocr-windows.ps1']:
        archive.write(ROOT / 'desktop' / name, 'Duo/desktop/' + name)
    archive.write(ROOT / 'index.html','Duo/index.html')
print('Site statique et relais personnel préparés.')

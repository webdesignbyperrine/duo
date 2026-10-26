"""Fabrique uniquement le code et les bibliothèques nécessaires, jamais un profil utilisateur."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import plistlib
import shutil
import ssl
import subprocess
import sys

ROOT=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--package',action='store_true');args=parser.parse_args()
    os.chdir(ROOT)
    release=ROOT/'release';release.mkdir(exist_ok=True)
    if sys.platform=='darwin':
        subprocess.run(['xcrun','swiftc','ocr.swift','-o','bin/duo-ocr','-framework','Vision','-framework','AppKit'],check=True)
    # Original artwork, no user image or workspace asset is included.
    from PIL import Image,ImageDraw
    icon=Image.new('RGBA',(1024,1024),'#f5f4ee');draw=ImageDraw.Draw(icon)
    draw.rounded_rectangle((120,170,670,650),radius=95,fill='#285a45');draw.polygon([(230,600),(230,790),(420,600)],fill='#285a45')
    draw.rounded_rectangle((400,390,900,820),radius=85,fill='#bf8062');draw.polygon([(770,770),(850,925),(650,770)],fill='#bf8062')
    iconfile=ROOT/'desktop'/('duo.icns' if sys.platform=='darwin' else 'duo.ico');icon.save(iconfile)
    command=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--onedir','--name','Duo','--distpath',str(ROOT/'dist'),'--workpath',str(ROOT/'.build'),'--specpath',str(ROOT/'.build'),'--icon',str(iconfile),'--collect-all','reportlab','--collect-all','pypdfium2','--collect-all','docx','--collect-all','pptx','--hidden-import','pypdf','--hidden-import','openpyxl','--hidden-import','pathspec','--osx-bundle-identifier','com.duo.assistants']
    # Explicit resource allowlist. Never copy a home directory, auth cache or project tree.
    for source,destination in [('index.html','.'),('hosting.json','.'),('desktop/providers.lock.json','desktop'),('desktop/ocr-windows.ps1','desktop')]:
        command+=['--add-data',str(ROOT/source)+os.pathsep+destination]
    if sys.platform=='darwin':command+=['--add-binary',str(ROOT/'bin/duo-ocr')+os.pathsep+'bin']
    runtime_ca = Path(ssl.__file__).resolve().parent / 'codex-rejected-cas.pem'
    if runtime_ca.is_file():
        command += ['--add-data',str(runtime_ca)+os.pathsep+'.']
    command+=['desktop_entry.py']
    subprocess.run(command,check=True)
    if sys.platform=='darwin':
        plist_path=ROOT/'dist/Duo.app/Contents/Info.plist'
        plist=plistlib.loads(plist_path.read_bytes());plist['LSUIElement']=True
        plist_path.write_bytes(plistlib.dumps(plist))
        subprocess.run(['xattr','-cr',str(ROOT/'dist/Duo.app')],check=True)
        subprocess.run(['codesign','--force','--deep','--sign','-',str(ROOT/'dist/Duo.app')],check=True)
        subprocess.run(['codesign','--verify','--deep','--strict',str(ROOT/'dist/Duo.app')],check=True)
    label=('macOS-'+('AppleSilicon' if platform.machine()=='arm64' else 'Intel')) if sys.platform=='darwin' else 'Windows-x64'
    if args.package:
        if sys.platform=='darwin':
            stage=ROOT/'.build'/'dmg';shutil.rmtree(stage,ignore_errors=True);stage.mkdir(parents=True)
            shutil.copytree(ROOT/'dist/Duo.app',stage/'Duo.app',symlinks=True)
            (stage/'Applications').symlink_to('/Applications')
            subprocess.run(['xattr','-cr',str(stage/'Duo.app')],check=True)
            subprocess.run(['codesign','--verify','--deep','--strict',str(stage/'Duo.app')],check=True)
            output=release/('Duo-'+label+'.dmg')
            output.unlink(missing_ok=True)
            subprocess.run(['hdiutil','create','-volname','Duo','-srcfolder',str(stage),'-ov','-format','UDZO',str(output)],check=True)
        else:
            # Standard per-user GUI installer; never requires an administrator account.
            compiler=shutil.which('ISCC.exe') or 'C:/Program Files (x86)/Inno Setup 6/ISCC.exe'
            subprocess.run([compiler,str(ROOT/'desktop/windows-installer.iss')],check=True)
    manifest={'version':'0.2.0','platform':label,'configuration':'empty-user-profile','conversation_storage':'memory-only','files':[]}
    for path in sorted(release.iterdir()):
        if path.is_file() and path.suffix in ('.dmg','.exe'):
            manifest['files'].append({'name':path.name,'size':path.stat().st_size,'sha256':hashlib.file_digest(path.open('rb'),'sha256').hexdigest()})
    (release/('manifest-'+label+'.json')).write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':main()

"""Installation des binaires officiels vérifiés ; connexion personnelle sans terminal."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
import zipfile
from runtime_paths import ROOT, DESKTOP, user_data, private_directory, provider_binary, provider_environment, hidden_process, terminate_tree

ALLOWED_DOWNLOAD_HOSTS = {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','downloads.claude.ai'}


class TrustedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != 'https' or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS:
            raise ValueError('Le téléchargement a été redirigé vers une adresse non autorisée.')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def platform_key():
    machine=platform.machine().lower()
    arch='arm64' if machine in ('arm64','aarch64') else 'x64' if machine in ('x86_64','amd64') else ''
    key=('win32' if os.name=='nt' else 'darwin' if platform.system()=='Darwin' else 'linux')+'-'+arch
    return key


def download_verified(spec, progress):
    parsed=urllib.parse.urlsplit(spec['url'])
    if parsed.scheme!='https' or parsed.hostname not in ALLOWED_DOWNLOAD_HOSTS or not re.fullmatch(r'[a-f0-9]{64}',spec['sha256']):
        raise ValueError('Source de téléchargement non autorisée.')
    opener=urllib.request.build_opener(TrustedRedirects())
    digest=hashlib.sha256()
    with tempfile.TemporaryFile() as output:
        with opener.open(urllib.request.Request(spec['url'],headers={'User-Agent':'Duo/0.2'}),timeout=40) as response:
            total=int(response.headers.get('Content-Length',0));received=0
            if total>500*1024*1024:raise ValueError('Composant trop volumineux.')
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                received+=len(chunk)
                if received>500*1024*1024:raise ValueError('Composant trop volumineux.')
                output.write(chunk);digest.update(chunk)
                progress('Téléchargement : '+str(received//1024//1024)+' Mo'+(' / '+str(total//1024//1024)+' Mo' if total else '')+'…')
        if digest.hexdigest()!=spec['sha256']:raise ValueError('Empreinte du composant incorrecte. Installation annulée.')
        output.seek(0)
        return output.read()


def extract_executable(raw, kind, provider):
    if kind=='binary':return raw
    extension='.exe' if os.name=='nt' else ''
    if kind=='zip':
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            candidates=[i for i in archive.infolist() if not i.is_dir() and Path(i.filename).name.startswith(provider+'-') and i.filename.endswith(extension) and i.file_size<600*1024*1024]
            if len(candidates)!=1:raise ValueError('Archive du programme non reconnue.')
            return archive.read(candidates[0])
    if kind=='tar.gz':
        with tarfile.open(fileobj=io.BytesIO(raw),mode='r:gz') as archive:
            candidates=[m for m in archive.getmembers() if m.isfile() and Path(m.name).name.startswith(provider+'-') and m.size<600*1024*1024]
            if len(candidates)!=1:raise ValueError('Archive du programme non reconnue.')
            return archive.extractfile(candidates[0]).read()
    raise ValueError('Archive non reconnue.')


class Setup:
    def __init__(self):
        self.lock=threading.RLock()
        self.state={'busy':False,'message':'Connecte tes propres abonnements pour commencer.','error':'','url':'','needs_code':False}
        self.process=None

    def snapshot(self):
        with self.lock:return dict(self.state,desktop=DESKTOP)

    def update(self,**values):
        with self.lock:self.state.update(values)

    def start(self,action,provider):
        if not DESKTOP:raise ValueError('La configuration personnelle est disponible dans l’application installée.')
        if provider not in ('codex','claude') or action not in ('install','login','logout'):
            raise ValueError('Action de configuration inconnue.')
        with self.lock:
            if self.state['busy']:raise ValueError('Une configuration est déjà en cours.')
            self.state.update(busy=True,error='',url='',needs_code=False,message='Préparation…')
        threading.Thread(target=self.run,args=(action,provider),daemon=True).start()

    def run(self,action,provider):
        try:
            if action=='install':
                locks=json.loads((ROOT/'desktop/providers.lock.json').read_text())
                spec=locks[provider].get(platform_key())
                if not spec:raise ValueError('Cet ordinateur n’est pas encore pris en charge par cet installateur.')
                raw=download_verified(spec,lambda text:self.update(message=text))
                executable=extract_executable(raw,spec['archive'],provider)
                tools=private_directory(user_data()/'tools')
                target=tools/(provider+('.exe' if os.name=='nt' else ''))
                temporary=target.with_name(target.stem+'.installing'+target.suffix)
                try:
                    temporary.write_bytes(executable);temporary.chmod(0o700)
                    check=subprocess.run([str(temporary),'--version'],capture_output=True,text=True,timeout=30,env=provider_environment(),**hidden_process())
                    if check.returncode:raise ValueError('Le programme téléchargé ne démarre pas sur cet ordinateur.')
                    os.replace(temporary,target)
                finally:temporary.unlink(missing_ok=True)
                for extra in spec.get('additional', []):
                    if not re.fullmatch(r'[a-z0-9-]+\.exe', extra['name']):raise ValueError('Nom de composant invalide.')
                    payload=download_verified(extra,lambda text:self.update(message=text))
                    helper=tools/extra['name']
                    scratch=helper.with_suffix('.installing.exe')
                    try:
                        scratch.write_bytes(payload);os.replace(scratch,helper)
                    finally:scratch.unlink(missing_ok=True)
                self.update(message=('Codex' if provider=='codex' else 'Claude Code')+' est installé. Clique sur « Connecter mon abonnement ».')
            else:
                command=[provider_binary(provider)]
                if provider=='codex':command+=['login'] if action=='login' else ['logout']
                else:command+=['auth','login','--claudeai'] if action=='login' else ['auth','logout']
                self.update(message='Termine la connexion sur le site officiel qui s’ouvre.' if action=='login' else 'Déconnexion de Duo…')
                with tempfile.TemporaryDirectory(prefix='duo-login-') as folder:
                    process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1,cwd=folder,env=provider_environment(),start_new_session=True,**hidden_process())
                    with self.lock:self.process=process
                    deadline=time.monotonic()+600
                    # Reading in a separate thread keeps a bounded authentication timeout.
                    reader=threading.Thread(target=self.read_output,args=(process,),daemon=True);reader.start()
                    while process.poll() is None:
                        if time.monotonic()>deadline:
                            terminate_tree(process,True);raise ValueError('La connexion a expiré. Clique à nouveau sur « Connecter mon abonnement ».')
                        time.sleep(.2)
                    reader.join(timeout=2)
                    if process.returncode:raise ValueError('La connexion n’a pas abouti. Vérifie le compte choisi puis réessaie.')
                self.update(message='Connexion terminée. Vérifie le statut des comptes.' if action=='login' else 'Compte déconnecté de Duo.',url='',needs_code=False)
        except Exception as error:
            self.update(error=str(error) if isinstance(error,ValueError) else 'Configuration impossible. Vérifie la connexion Internet et réessaie.',message='Configuration interrompue.',url='',needs_code=False)
        finally:
            with self.lock:self.process=None
            self.update(busy=False)

    def read_output(self,process):
        # Never retain stdout: it may contain one-time authentication material.
        for line in process.stdout:
            clean=re.sub(r'\x1b\[[0-9;]*[A-Za-z]','',line)
            for url in re.findall(r'https://[^\s<>]+',clean):
                url=url.rstrip(').,;')
                host=urllib.parse.urlsplit(url).hostname
                if host in {'auth.openai.com','auth0.openai.com','chatgpt.com','claude.ai','console.anthropic.com','platform.claude.com'}:
                    self.update(url=url)
                    webbrowser.open(url)
            if re.search(r'paste.*code|enter.*code|code.*below',clean,re.I):self.update(needs_code=True)

    def submit_code(self,code):
        if not isinstance(code,str) or not 1<=len(code.strip())<=4000 or '\n' in code or '\r' in code:
            raise ValueError('Code de connexion invalide.')
        with self.lock:
            if not self.process or self.process.poll() is not None or not self.state['needs_code']:raise ValueError('Aucune connexion n’attend de code.')
            self.process.stdin.write(code.strip()+'\n');self.process.stdin.flush()
            self.state.update(needs_code=False,url='')

    def cancel(self):
        with self.lock:
            if self.process:terminate_tree(self.process,True)

setup=Setup()

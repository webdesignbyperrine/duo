"""Instantanés de projets locaux ou GitHub, sans checkout, installation ni exécution du projet."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
from runtime_paths import hidden_process
import tempfile
import time
from urllib.parse import urlsplit
import zipfile

MAX_PROJECT_FILES = 5000
MAX_PROJECT_BYTES = 30 * 1024 * 1024
MAX_CODE_FILE = 1024 * 1024
EXCLUDED_DIRS = {'.git', 'node_modules', '.next', '.nuxt', '.output', '.astro', '.vercel', '.netlify', '.cache', '__pycache__', '.venv', 'venv', 'env', 'dist', 'build', 'coverage', 'vendor', 'target', '.idea', '.vscode', '.ssh', '.aws', '.secrets', '.terraform'}
EXCLUDED_NAMES = {'.ds_store', '.npmrc', '.pypirc', '.netrc', '.git-credentials', 'credentials.json', 'service-account.json', 'id_rsa', 'id_ed25519', 'id_dsa', 'keychain.json'}
EXCLUDED_SUFFIXES = {'.pem', '.key', '.p12', '.pfx', '.keystore', '.jks', '.sqlite', '.sqlite3', '.db', '.log', '.map', '.zip', '.gz', '.tar', '.mp4', '.mov', '.mp3', '.wav', '.pdf', '.docx', '.xlsx', '.pptx', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.woff', '.woff2', '.ttf', '.eot', '.exe', '.dll', '.so', '.dylib', '.pyc'}


def clean_path(value):
    if not isinstance(value, str) or not value or len(value) > 700 or '\\' in value or '\x00' in value:
        raise ValueError('Un chemin de fichier du projet est invalide.')
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ('.', '..') for part in value.split('/')) or any(not c.isprintable() for c in value):
        raise ValueError('Le projet contient un chemin qui sort du dossier sélectionné.')
    return str(path)


def exclusion_reason(path):
    p = PurePosixPath(path)
    if any(part.lower() in EXCLUDED_DIRS for part in p.parts[:-1]):
        return 'Dépendances, cache, configuration privée ou fichiers générés'
    name = p.name.lower()
    if name.startswith('.env') or name in EXCLUDED_NAMES or re.search(r'(?:service[_-]?account|credentials|secrets?)[._-].*\.json$', name):
        return 'Fichier susceptible de contenir des secrets'
    if p.suffix.lower() in EXCLUDED_SUFFIXES:
        return 'Format binaire, archive, journal ou fichier généré (à joindre séparément si nécessaire)'
    return ''


def secret_in(text):
    if re.search(r'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----|\b(?:ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{35,}|AKIA[A-Z0-9]{16}|sk-(?:proj-)?[A-Za-z0-9_-]{30,})', text):
        return True
    if re.search(r'''(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|https?)://[^\s"':/]+:[^\s"'@]+@''', text, re.I):
        return True
    for match in re.finditer(r'''(?i)\b(?:api[_-]?key|client[_-]?secret|access[_-]?token|private[_-]?key|password)\b["']?\s*[:=]\s*["']([^"'\r\n]{12,})["']''', text):
        value = match[1].lower()
        if not any(word in value for word in ('example', 'placeholder', 'your_', 'your-', 'replace', 'changeme', 'process.env', 'os.environ', '${', 'test-', 'test_', 'xxx')):
            return True
    return False


def git_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('GIT_'):
            env.pop(key, None)
    env.update(GIT_TERMINAL_PROMPT='0', GIT_LFS_SKIP_SMUDGE='1', GIT_OPTIONAL_LOCKS='0')
    return env


def git_base():
    git = shutil.which('git')
    if not git:
        raise ValueError('Git n’est pas installé sur cet ordinateur. Installe-le avec son installateur graphique ou joins les fichiers du dossier sans clonage.')
    return [git, '-c', 'core.hooksPath=/dev/null', '-c', 'core.fsmonitor=false', '-c', 'protocol.file.allow=never', '-c', 'protocol.ext.allow=never']


def git_ignored(paths, contents):
    ignore_files = {p: raw for p, raw in contents.items() if PurePosixPath(p).name == '.gitignore'}
    if not ignore_files:
        return set()
    if shutil.which('git'):
        with tempfile.TemporaryDirectory(prefix='duo-gitignore-') as folder:
            root = Path(folder)
            result = subprocess.run(git_base() + ['init', '-q', '--template=', str(root)], capture_output=True, env=git_environment(), timeout=15, **hidden_process())
            if result.returncode:
                raise ValueError('Impossible de vérifier les règles .gitignore du projet.')
            for path, raw in ignore_files.items():
                target = root / path;target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(raw)
            result = subprocess.run(git_base() + ['-C', folder, 'check-ignore', '--no-index', '-z', '--stdin'], input='\0'.join(paths).encode() + b'\0', capture_output=True, env=git_environment(), timeout=15, **hidden_process())
            if result.returncode not in (0, 1):
                raise ValueError('Les règles .gitignore n’ont pas pu être évaluées.')
            return {p.decode('utf-8') for p in result.stdout.split(b'\0') if p}
    # Folder import remains available on computers without Git.
    from pathspec import GitIgnoreSpec
    specs={str(PurePosixPath(p).parent):GitIgnoreSpec.from_lines(raw.decode('utf-8-sig',errors='replace').splitlines()) for p,raw in ignore_files.items()}
    ignored=set()
    for path in paths:
        parts=PurePosixPath(path).parts
        inherited=[]
        for depth in range(len(parts)):
            parent='/'.join(parts[:depth]) or '.'
            if parent in specs:inherited.append((depth,specs[parent]))
            target='/'.join(parts[:depth+1])+('/' if depth<len(parts)-1 else '')
            decision=None
            for base,spec in inherited:
                relative='/'.join(parts[base:depth+1])+('/' if depth<len(parts)-1 else '')
                result=spec.check_file(relative)
                if result.include is not None:decision=result.include
            if decision:
                ignored.add(path);break
    return ignored


def prepare_project(name, contents, excluded=None, origin=None):
    """Même filtre appliqué aux dossiers du navigateur et aux dépôts clonés."""
    excluded = list(excluded or [])
    if len(contents) + len(excluded) > 20000:
        raise ValueError('Le projet dépasse 20 000 entrées. Sélectionne un sous-dossier de code.')
    normalized = {}
    for path, raw in contents.items():
        path = clean_path(path)
        reason = exclusion_reason(path)
        if reason:
            excluded.append({'path': path, 'reason': reason});continue
        if len(raw) > MAX_CODE_FILE:
            excluded.append({'path': path, 'reason': 'Fichier de plus de 1 Mo'});continue
        if b'\x00' in raw:
            excluded.append({'path': path, 'reason': 'Fichier binaire'});continue
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            excluded.append({'path': path, 'reason': 'Texte non UTF-8, à joindre séparément'});continue
        if secret_in(text):
            excluded.append({'path': path, 'reason': 'Contenu ressemblant à une clé ou un secret'});continue
        normalized[path] = raw
    ignored = git_ignored(list(normalized), normalized)
    for path in sorted(ignored):
        normalized.pop(path, None);excluded.append({'path': path, 'reason': 'Règle .gitignore du projet'})
    if not normalized:
        raise ValueError('Aucun fichier de code lisible n’a été retenu dans ce projet. Consulte les exclusions ou choisis un sous-dossier.')
    if len(normalized) > MAX_PROJECT_FILES or sum(len(v) for v in normalized.values()) > MAX_PROJECT_BYTES:
        raise ValueError('Le code retenu dépasse 5 000 fichiers ou 30 Mo. Sélectionne un sous-dossier ; aucun projet tronqué n’a été importé.')
    manifest = [{'path': p, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for p, raw in sorted(normalized.items())]
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, raw in sorted(normalized.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0));info.compress_type = zipfile.ZIP_DEFLATED;info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, raw)
    raw = output.getvalue()
    label = ''.join(c for c in str(name) if c.isalnum() or c in ' ._-')[:100].strip() or 'projet'
    warnings = ['Copie de lecture du code retenu. L’import n’exécute aucun script du projet ; les assistants reçoivent une consigne de lecture sans installation ni test.', 'La présence des fichiers ne signifie pas qu’ils ont tous été examinés : les assistants doivent préciser les chemins réellement consultés.']
    if excluded:
        warnings.append(str(len(excluded)) + ' entrées exclues. L’inventaire complet des exclusions reste consultable ; les secrets détectés ne sont pas transmis.')
    summary = ('Projet : ' + label + '\n' + str(len(manifest)) + ' fichiers de texte/code disponibles dans une copie locale en lecture seule.\n' +
               'Le contenu du code n’est pas collé dans ce message. Lis les fichiers utiles avec les outils de lecture autorisés. Le manifeste complet est fourni à côté du projet.\n' +
               'Fichiers exclus : ' + str(len(excluded)) + '. Ne prétends pas avoir audité les fichiers exclus.\n' +
               'Origine : ' + json.dumps(origin or {'type': 'local'}, ensure_ascii=False))
    return {'name': label + '.zip', 'raw': raw, 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'text': summary, 'chars': len(summary), 'warnings': warnings, 'role': 'source', 'is_project': True, 'project_manifest': manifest, 'project_excluded': sorted(excluded, key=lambda item: item['path']), 'project_origin': origin or {'type': 'local'}, 'project_bytes': sum(len(v) for v in normalized.values())}


def from_upload(data):
    if str(data.get('name', '')).lower() in EXCLUDED_DIRS:
        raise ValueError('Choisis la racine du projet, plutôt qu’un dossier de métadonnées, dépendances ou configuration privée.')
    entries = data.get('files')
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20000:
        raise ValueError('Choisis un dossier contenant au maximum 20 000 entrées.')
    contents, excluded = {}, []
    total = 0
    for item in entries:
        if not isinstance(item, dict):raise ValueError('Liste des fichiers invalide.')
        path = clean_path(item.get('path'))
        if path in contents:raise ValueError('Le dossier contient deux chemins identiques.')
        reason = exclusion_reason(path)
        if reason:
            excluded.append({'path': path, 'reason': reason});continue
        if item.get('skipped') == 'large':
            excluded.append({'path': path, 'reason': 'Fichier de plus de 1 Mo'});continue
        encoded = item.get('content')
        if not isinstance(encoded, str) or len(encoded) > MAX_CODE_FILE * 4 // 3 + 8:
            raise ValueError('Un fichier du projet dépasse 1 Mo. Sélectionne un périmètre plus petit.')
        try:raw = base64.b64decode(encoded, validate=True)
        except ValueError:raise ValueError('Un fichier du dossier n’a pas pu être reçu.')
        total += len(raw)
        if total > MAX_PROJECT_BYTES:raise ValueError('Le dossier dépasse 30 Mo de code. Choisis un sous-dossier.')
        contents[path] = raw
    return prepare_project(data.get('name', 'projet-local'), contents, excluded)


def github_url(value):
    if not isinstance(value, str):raise ValueError('Indique une adresse de dépôt GitHub.')
    value = value.strip()
    if value.startswith('git@github.com:'):value = 'https://github.com/' + value.split(':', 1)[1]
    parsed = urlsplit(value)
    if parsed.scheme != 'https' or parsed.netloc.lower() != 'github.com' or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Utilise l’adresse HTTPS d’un dépôt github.com, sans identifiant ni jeton dans le lien.')
    parts = parsed.path.strip('/').split('/')
    if len(parts) != 2 or not all(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', p) for p in parts):
        raise ValueError('Indique le dépôt sous la forme https://github.com/organisation/projet. La branche se choisit dans le champ séparé.')
    owner, repo = parts
    if repo.endswith('.git'):repo = repo[:-4]
    if not repo:raise ValueError('Nom de dépôt invalide.')
    return 'https://github.com/' + owner + '/' + repo + '.git', owner, repo


def limited_git(argv):
    # Le shell exécute une consigne constante ; URL, branche et chemins restent des arguments.
    # Évite preexec_fn, qui n'est pas sûr dans le serveur HTTP à plusieurs threads.
    if os.name == 'nt':
        return argv
    return ['/bin/sh', '-c', 'ulimit -f 245760 || exit 1; exec "$@"', 'duo-git', *argv]


def clone_github(value, branch=''):
    url, owner, repo = github_url(value)
    if not isinstance(branch, str) or len(branch) > 200 or (branch and (branch.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_./-]+', branch))):
        raise ValueError('Le nom de branche est invalide.')
    env = git_environment()
    command = git_base() + ['-c', 'http.followRedirects=false']
    gh = shutil.which('gh')
    if gh:
        # Le programme officiel gère ses propres identifiants ; aucun jeton n’est lu ou copié par Duo.
        command += ['-c', 'credential.helper=', '-c', 'credential.helper=!' + '\"' + gh + '\" auth git-credential']
    with tempfile.TemporaryDirectory(prefix='duo-github-') as folder:
        target = Path(folder) / 'repo'
        clone = command + ['clone', '--quiet', '--depth=1', '--filter=blob:limit=1048576', '--no-checkout', '--no-recurse-submodules', '--no-tags']
        if branch:clone += ['--branch', branch]
        clone += ['--', url, str(target)]
        try:
            result = subprocess.run(limited_git(clone), capture_output=True, env=env, timeout=100, **hidden_process())
        except subprocess.TimeoutExpired:
            raise ValueError('Le clonage a dépassé 100 secondes. Vérifie l’accès au dépôt ou importe un dossier local plus petit.')
        if result.returncode:
            raise ValueError('Clonage impossible. Vérifie le lien, la branche et l’accès du compte GitHub connecté sur ce Mac. Aucun dépôt existant n’a été modifié.')
        def git(args, timeout=20):
            try:
                process = subprocess.run(limited_git(command + ['-C', str(target)] + args), capture_output=True, env=env, timeout=timeout, **hidden_process())
            except subprocess.TimeoutExpired:
                raise ValueError('Une partie du dépôt est trop longue à télécharger. Essaie un dossier local plus petit.')
            if process.returncode:raise ValueError('Une partie du dépôt n’a pas pu être lue. Essaie un dossier local.')
            return process.stdout
        revision = git(['rev-parse', 'HEAD']).decode().strip()
        resolved_branch = git(['symbolic-ref', '--quiet', '--short', 'HEAD']).decode().strip()
        records = git(['ls-tree', '-r', '-z', 'HEAD']).split(b'\0')
        contents, excluded = {}, []
        deadline = time.monotonic() + 100
        total = 0
        for record in records:
            if not record:continue
            if len(contents) + len(excluded) >= 20000:raise ValueError('Le dépôt contient trop de fichiers. Utilise un sous-dossier local.')
            header, raw_path = record.split(b'\t', 1)
            mode, kind, sha = header.decode().split(' ')
            try:path = clean_path(raw_path.decode('utf-8'))
            except UnicodeError:raise ValueError('Le dépôt contient un chemin de fichier non UTF-8.')
            reason = exclusion_reason(path)
            if mode == '120000':reason = 'Lien symbolique non suivi'
            if mode == '160000' or kind != 'blob':reason = 'Sous-module non cloné'
            if reason:
                excluded.append({'path': path, 'reason': reason});continue
            if time.monotonic() > deadline:raise ValueError('La lecture du dépôt est trop longue. Utilise un sous-dossier local.')
            size = int(git(['cat-file', '-s', sha], timeout=20).strip())
            if size > MAX_CODE_FILE:
                excluded.append({'path': path, 'reason': 'Fichier de plus de 1 Mo'});continue
            total += size
            if total > MAX_PROJECT_BYTES:raise ValueError('Le code du dépôt dépasse 30 Mo. Importe un sous-dossier local.')
            contents[path] = git(['cat-file', 'blob', sha])
        return prepare_project(repo, contents, excluded, {'type': 'github', 'url': 'https://github.com/' + owner + '/' + repo, 'branch': resolved_branch, 'revision': revision})


def materialize(sources, folder):
    """Copie les mêmes octets contrôlés dans chaque session de lecture des assistants."""
    root = Path(folder)
    for source in sources:
        if not source.get('is_project'):continue
        destination = root / 'projects' / source['id'];destination.mkdir(parents=True, exist_ok=True)
        known = {f['path']: f for f in source['project_manifest']}
        seen = set()
        with zipfile.ZipFile(io.BytesIO(source['raw'])) as archive:
            for item in archive.infolist():
                path = clean_path(item.filename)
                if path not in known or path in seen or stat.S_ISLNK(item.external_attr >> 16):raise RuntimeError('L’instantané du projet est incohérent.')
                raw = archive.read(item)
                if hashlib.sha256(raw).hexdigest() != known[path]['sha256']:raise RuntimeError('Le contenu du projet a changé de façon inattendue.')
                target = destination / path;target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(raw);target.chmod(0o444)
                seen.add(path)
        if seen != set(known):raise RuntimeError('Des fichiers manquent dans la copie du projet.')
        manifests = root / 'project_manifests';manifests.mkdir(exist_ok=True)
        (manifests / (source['id'] + '.json')).write_text(json.dumps({'project': source['name'], 'origin': source['project_origin'], 'included': source['project_manifest'], 'excluded': source['project_excluded']}, ensure_ascii=False, indent=2))

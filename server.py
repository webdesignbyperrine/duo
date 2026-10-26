"""Relais personnel entre les programmes officiels Codex et Claude Code."""
import json
import io
import base64
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from attachments import decode_upload, extract, MAX_FILE, MAX_TOTAL, MAX_TEXT
from workflows import execute, execute_followup, MODES
from file_factory import build_files, FORMATS
from projects import from_upload, clone_github, materialize
from sessions import Sessions

ROOT = Path(__file__).resolve().parent
PORT = 8786
TOKEN = secrets.token_urlsafe(32)
# Public configuration only: credentials are never written here.
HOSTED_URL = json.loads((ROOT / 'hosting.json').read_text()).get('url', '') if (ROOT / 'hosting.json').exists() else ''
ALLOWED_ORIGINS = {'http://127.0.0.1:8786', 'http://localhost:8786'}
if HOSTED_URL:
    from urllib.parse import urlsplit
    parsed_host = urlsplit(HOSTED_URL)
    if parsed_host.scheme != 'https' or parsed_host.path not in ('', '/') or parsed_host.query or parsed_host.fragment or parsed_host.username:
        raise ValueError('Adresse hébergée invalide.')
    ALLOWED_ORIGINS.add(HOSTED_URL.rstrip('/'))


def environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('ANTHROPIC_', 'OPENAI_', 'AZURE_OPENAI_', 'CLAUDE_CODE_USE_')) or key in ('CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDECODE'):
            env.pop(key, None)
    return env


def binary(name):
    found = shutil.which(name)
    if found:
        return found
    candidates = [Path.home() / '.local/bin' / name]
    if name == 'codex':
        candidates.append(Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex'))
    for path in candidates:
        if path.is_file():
            return str(path)
    raise RuntimeError(name + ' est introuvable sur cet ordinateur.')


def authentication():
    status = {}
    for name in ('codex', 'claude'):
        try:
            command = [binary(name)] + (['login', 'status'] if name == 'codex' else ['auth', 'status'])
            result = subprocess.run(command, capture_output=True, text=True, timeout=15, env=environment(), cwd=tempfile.gettempdir())
            if name == 'codex':
                ok = result.returncode == 0 and 'using ChatGPT' in result.stdout + result.stderr
            else:
                data = json.loads(result.stdout)
                ok = data.get('loggedIn') is True and data.get('authMethod') == 'claude.ai'
            status[name] = {'ok': ok, 'message': 'Compte d’abonnement reconnu' if ok else 'Connexion à l’abonnement requise'}
        except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError):
            status[name] = {'ok': False, 'message': 'Connexion impossible à vérifier'}
    return status


class Discussion:
    def __init__(self):
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.state = {'running': False, 'messages': [], 'status': 'Prêt', 'error': ''}
        self.sources = {}
        self.active_sources = []
        self.generated = {}
        self.closed = False

    def ensure_open(self):
        if self.closed:
            raise ValueError("Cette discussion est terminée. Ouvre une nouvelle discussion.")

    def dispose(self):
        with self.lock:
            self.closed = True
            self.stop_event.set()
            self.sources.clear()
            self.active_sources.clear()
            self.generated.clear()
            self.state = {"running": False, "messages": [], "status": "Discussion effacée", "error": ""}

    def update(self, **values):
        with self.lock:
            if not self.closed:
                self.state.update(values)

    @staticmethod
    def source_metadata(source):
        metadata = {k: source[k] for k in ('id', 'name', 'size', 'sha256', 'warnings', 'chars', 'role')}
        if source.get('is_project'):
            metadata.update(is_project=True, project_files=len(source['project_manifest']), project_exclusions=len(source['project_excluded']), project_origin=source['project_origin'], project_bytes=source['project_bytes'])
        return metadata

    def add_project(self, data, github=False):
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Attends la fin de la réponse pour joindre un projet.')
        try:
            project = clone_github(data.get('url'), data.get('branch', '')) if github else from_upload(data)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError('L’import du projet n’a pas pu aboutir dans le délai prévu. Vérifie l’accès GitHub ou sélectionne un dossier plus petit.')
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('La discussion a commencé pendant l’import. Ajoute le projet après sa fin.')
            if len(self.sources) >= 10 or sum(s['size'] for s in self.sources.values()) + project['size'] > MAX_TOTAL:
                raise ValueError('Le dossier dépasse 10 pièces ou 30 Mo. Retire une pièce avant d’ajouter le projet.')
            if sum(s['chars'] for s in self.sources.values()) + project['chars'] > MAX_TEXT:
                raise ValueError('Le contexte du dossier est trop volumineux. Réduis les autres pièces avant d’ajouter le projet.')
            project['id'] = 'P-' + uuid.uuid4().hex[:8]
            self.sources[project['id']] = project
            return self.source_metadata(project)

    def list_sources(self):
        with self.lock:
            return [self.source_metadata(s) for s in self.sources.values()]

    def upload(self, data):
        name, raw = decode_upload(data)
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Attends la fin de la discussion pour modifier les pièces.')
            if len(self.sources) >= 10 or sum(s['size'] for s in self.sources.values()) + len(raw) > MAX_TOTAL:
                raise ValueError('Un dossier peut contenir 10 pièces et 30 Mo au maximum.')
        content = extract(name, raw)
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('La discussion a démarré pendant la lecture. Ajoute la pièce après sa fin.')
            if len(self.sources) >= 10 or sum(s['size'] for s in self.sources.values()) + len(raw) > MAX_TOTAL:
                raise ValueError('Le dossier dépasse 10 pièces ou 30 Mo.')
            if sum(s['chars'] for s in self.sources.values()) + len(content['text']) > MAX_TEXT:
                raise ValueError('Le texte du dossier dépasse 140 000 caractères. Réduis les pièces ; aucun texte tronqué n’a été ajouté.')
            source = dict(content, id='P-' + uuid.uuid4().hex[:8], name=name, raw=raw, size=len(raw), chars=len(content['text']), role='source')
            self.sources[source['id']] = source
            return self.source_metadata(source)

    def remove_source(self, source_id):
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Attends la fin de la discussion pour retirer une pièce.')
            self.sources.pop(source_id, None)

    def output_context(self, messages):
        with self.lock:
            outputs = []
            for message in messages:
                for metadata in message.get('outputs', []):
                    item = self.generated.get(metadata['id'])
                    if item:
                        outputs.append(dict(metadata, author=message['speaker'], extracted_content=item['review_text']))
            return outputs

    @staticmethod
    def output_metadata(item):
        return {key: item[key] for key in ('id', 'name', 'format', 'size', 'sha256', 'mime', 'warnings', 'checks')}

    def append_result(self, speaker, title, text, received, review=None, file_specs=None):
        if file_specs:
            self.update(status=speaker + ' · création et lecture des fichiers…')
        created, errors = build_files(file_specs or [], self.stop_event)
        with self.lock:
            if self.stop_event.is_set():
                raise InterruptedError()
            artifact_id = uuid.uuid4().hex[:10]
            message = {'id': artifact_id, 'speaker': speaker, 'title': title, 'text': text,
                       'file': ('codex-' if speaker == 'Codex' else 'claude-') + artifact_id + '.md',
                       'received_artifacts': [m['id'] for m in received],
                       'source_ids': [s['id'] for s in self.active_sources],
                       'received_files': [f['id'] for m in received for f in m.get('outputs', [])],
                       'outputs': [], 'file_errors': errors}
            for item in created:
                if sum(f['size'] for f in self.generated.values()) + item['size'] > 60 * 1024 * 1024:
                    message['file_errors'].append(item['name'] + ' : capacité des livrables atteinte (60 Mo). Télécharge le dossier puis commence une nouvelle analyse.')
                    continue
                self.generated[item['id']] = item
                message['outputs'].append(self.output_metadata(item))
            if review:
                message.update({k: review[k] for k in ('verdict', 'open_points', 'source_refs')})
            self.state['messages'].append(message)
            return json.loads(json.dumps(message))

    def export_analysis(self, message_id, kind):
        if kind not in ('docx', 'pdf', 'txt', 'md'):
            raise ValueError('Choisis Word, PDF ou texte pour cet export rapide.')
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Attends la fin de la réponse pour l’exporter.')
            message = next((m for m in self.state['messages'] if m.get('id') == message_id), None)
            if not message:
                raise ValueError('Analyse introuvable.')
            content = artifact_text(message)
        created, errors = build_files([{'name': message['file'].rsplit('.', 1)[0] + '.' + kind, 'format': kind, 'content': content}])
        if errors:
            raise ValueError(errors[0])
        with self.lock:
            if not any(m is message for m in self.state['messages']):
                raise ValueError('La discussion a changé pendant l’export. Réessaie depuis la nouvelle discussion.')
            item = created[0]
            if sum(f['size'] for f in self.generated.values()) + item['size'] > 60 * 1024 * 1024:
                raise ValueError('Capacité des livrables atteinte (60 Mo). Télécharge les résultats avant de commencer une nouvelle analyse.')
            self.generated[item['id']] = item
            message.setdefault('outputs', []).append(self.output_metadata(item))
            return self.output_metadata(item)

    def bundle(self):
        with self.lock:
            output = io.BytesIO()
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                manifest = {'mode': self.state.get('mode', 'discussion'), 'sources': [self.source_metadata(s) for s in self.active_sources], 'outcome': self.state.get('outcome', ''), 'messages': self.state['messages']}
                archive.writestr('dossier-et-echanges.json', json.dumps(manifest, ensure_ascii=False, indent=2))
                for source in self.active_sources:
                    archive.writestr('pieces-originales/' + source['id'] + '-' + source['name'], source['raw'])
                    archive.writestr('texte-fourni/' + source['id'] + '.txt', source['text'])
                    if source.get('is_project'):
                        archive.writestr('projets/' + source['id'] + '-inventaire.json', json.dumps({'origin': source['project_origin'], 'included': source['project_manifest'], 'excluded': source['project_excluded']}, ensure_ascii=False, indent=2))
                for message in self.state['messages']:
                    if message.get('file'):
                        archive.writestr('analyses/' + message['file'], artifact_text(message))
                for item in self.generated.values():
                    archive.writestr('livrables/' + item['id'] + '-' + item['name'], item['raw'])
                archive.writestr('discussion.md', '\n\n---\n\n'.join(artifact_text(m) for m in self.state['messages']))
            return output.getvalue()

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(self.state))

    def start(self, topic, rounds, confirmed, mode='discussion', first='Codex', source_selection=None, output_formats=None):
        if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 12000:
            raise ValueError('Écris une question de 1 à 12 000 caractères.')
        if type(rounds) is not int or not 1 <= rounds <= 4:
            raise ValueError('Choisis entre 1 et 4 allers-retours.')
        if confirmed is not True:
            raise ValueError('Confirme que les crédits supplémentaires sont désactivés dans les deux comptes.')
        if mode not in MODES or first not in ('Codex', 'Claude Code'):
            raise ValueError('Choisis un mode de travail et le premier assistant.')
        output_formats = self.validate_formats(output_formats)
        source_selection = [] if source_selection is None else source_selection
        if not isinstance(source_selection, list) or len(source_selection) > 10:
            raise ValueError('La sélection des pièces est invalide.')
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Une discussion est déjà en cours.')
            selected = []
            seen = set()
            for item in source_selection:
                if not isinstance(item, dict) or item.get('id') not in self.sources or item.get('role') not in ('source', 'analysis') or item['id'] in seen:
                    raise ValueError('Une pièce n’est plus disponible ou sa catégorie est invalide. Actualise la liste.')
                seen.add(item['id'])
                self.sources[item['id']]['role'] = item['role']
                selected.append(dict(self.sources[item['id']], role=item['role']))
            self.active_sources = selected
            self.generated = {}
            self.stop_event.clear()
            self.state = {'running': True, 'messages': [{'speaker': 'Toi', 'text': topic.strip()}], 'status': 'Vérification des connexions…', 'error': '', 'mode': mode, 'first': first, 'rounds': rounds, 'sources': [self.source_metadata(s) for s in selected], 'outcome': '', 'converged': False, 'output_formats': output_formats}
            threading.Thread(target=self.run, args=(rounds,), daemon=True).start()

    @staticmethod
    def validate_formats(formats):
        formats = [] if formats is None else formats
        if not isinstance(formats, list) or len(formats) > 6 or any(f not in FORMATS for f in formats):
            raise ValueError('Choisis au maximum six formats de sortie pris en charge.')
        return list(dict.fromkeys(formats))

    def followup(self, note, recipient, confirmed, output_formats=None, source_selection=None):
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 12000:
            raise ValueError('Écris ta nouvelle demande (12 000 caractères maximum).')
        if recipient not in ('Codex', 'Claude Code', 'both') or confirmed is not True:
            raise ValueError('Choisis le destinataire et confirme l’utilisation des abonnements.')
        formats = self.validate_formats(output_formats)
        with self.lock:
            self.ensure_open()
            if self.state['running']:
                raise ValueError('Une réponse est déjà en cours.')
            if not self.state['messages']:
                raise ValueError('Commence une discussion avant de demander une suite.')
            if source_selection is not None:
                if not isinstance(source_selection, list) or len(source_selection) > 10:
                    raise ValueError('La liste des pièces est invalide.')
                selected, seen = [], set()
                for item in source_selection:
                    if not isinstance(item, dict) or item.get('id') not in self.sources or item['id'] in seen or item.get('role') not in ('source', 'analysis'):
                        raise ValueError('Une pièce n’est plus disponible. Actualise la liste.')
                    seen.add(item['id'])
                    selected.append(dict(self.sources[item['id']], role=item['role']))
                self.active_sources = selected
                self.state['sources'] = [self.source_metadata(s) for s in selected]
            self.stop_event.clear()
            self.state['messages'].append({'speaker': 'Toi', 'text': note.strip(), 'title': 'Nouvelle demande'})
            self.state.update(running=True, error='', status='Vérification des connexions…', outcome='', converged=False, output_formats=formats)
            threading.Thread(target=self.run, args=(1, (note.strip(), recipient)), daemon=True).start()

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.state['running']:
                self.state['status'] = 'Arrêt en cours…'

    def call(self, speaker, prompt, schema=None):
        if self.stop_event.is_set():
            raise InterruptedError()
        with tempfile.TemporaryDirectory(prefix='duo-discussion-') as folder:
            has_projects = any(s.get('is_project') for s in self.active_sources)
            if has_projects:
                materialize(self.active_sources, folder)
            if speaker == 'Codex':
                output = Path(folder) / 'answer.txt'
                command = [binary('codex'), 'exec', '--ignore-user-config', '--ignore-rules', '--ephemeral', '--sandbox', 'read-only', '--skip-git-repo-check', '-c', 'model_provider="openai"', '-c', 'approval_policy="never"', '-o', str(output), '-']
            else:
                command = [binary('claude'), '-p', '--output-format', 'json', '--tools', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}', '--setting-sources', '', '--settings', '{"disableAllHooks":true}', '--disable-slash-commands', '--no-session-persistence', '--permission-mode', 'dontAsk']
                if has_projects:
                    command[command.index('--tools') + 1] = 'Read,Glob,Grep'
                    command.extend(['--restricted', '--allowedTools', 'Read,Glob,Grep'])
            if schema:
                if speaker == 'Codex':
                    schema_path = Path(folder) / 'response-schema.json'
                    schema_path.write_text(json.dumps(schema))
                    command[2:2] = ['--output-schema', str(schema_path)]
                else:
                    command.extend(['--json-schema', json.dumps(schema)])
            with tempfile.TemporaryFile(mode='w+t') as stdout, tempfile.TemporaryFile(mode='w+t') as stderr:
                if self.stop_event.is_set():
                    raise InterruptedError()
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr, cwd=folder, env=environment(), start_new_session=True, text=True)
                try:
                    process.stdin.write(prompt)
                    process.stdin.close()
                    deadline = time.monotonic() + 360
                    while process.poll() is None:
                        if self.stop_event.wait(0.2):
                            raise InterruptedError()
                        if time.monotonic() > deadline:
                            raise RuntimeError(speaker + ' n’a pas répondu après 6 minutes. Les analyses déjà reçues restent disponibles.')
                    stdout.seek(0)
                    raw = stdout.read()
                    if speaker == 'Claude Code':
                        try:
                            payload = json.loads(raw)
                        except ValueError:
                            payload = {}
                        failure = str(payload.get('result', ''))
                        if payload.get('api_error_status') == 401 or 'OAuth access token is invalid' in failure:
                            raise RuntimeError('La connexion de Claude Code a expiré ou est invalide. Renouvelle sa connexion avec ton compte Claude Pro. Être connecté dans Claude Desktop ou dans le navigateur ne renouvelle pas cette session.')
                        if payload.get('api_error_status') == 429 or 'usage limit' in failure.lower() or 'hit your limit' in failure.lower():
                            raise RuntimeError('Claude Code a atteint une limite d’utilisation. Attends le renouvellement de ton quota ; n’active pas les crédits supplémentaires pour continuer.')
                        if process.returncode or payload.get('is_error'):
                            raise RuntimeError('Claude Code a interrompu sa réponse. Vérifie sa connexion dans Claude Code. Aucun basculement vers une clé API n’a été effectué.')
                        text = payload.get('result', '')
                        if schema and payload.get('structured_output'):
                            text = json.dumps(payload['structured_output'], ensure_ascii=False)
                    else:
                        if process.returncode:
                            raise RuntimeError('Codex a interrompu sa réponse. Vérifie sa connexion et les limites de ton abonnement.')
                        text = output.read_text() if output.exists() else ''
                    if not text.strip():
                        raise RuntimeError(speaker + ' n’a renvoyé aucun texte.')
                    if len(text) > 90000:
                        raise RuntimeError(speaker + ' a produit une réponse trop volumineuse. Demande une analyse plus concise ; aucune version tronquée n’a été transmise.')
                    return text.strip()
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid, signal.SIGTERM)
                        try:
                            process.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            os.killpg(process.pid, signal.SIGKILL)
                            process.wait()

    def run(self, rounds, followup=None):
        try:
            if not all(v['ok'] for v in authentication().values()):
                raise RuntimeError('Connecte Codex et Claude Code avec tes abonnements avant de démarrer.')
            end_status = execute_followup(self, *followup) if followup else execute(self, rounds, self.state.get('mode', 'discussion'), self.state.get('first', 'Codex'), self.active_sources)
            with self.lock:
                self.state['status'] = end_status
        except InterruptedError:
            with self.lock:
                self.state['status'] = 'Discussion arrêtée'
        except Exception as error:
            with self.lock:
                self.state['error'] = str(error) if isinstance(error, RuntimeError) else 'La discussion a rencontré une erreur. Vérifie les connexions.'
                self.state['status'] = 'Discussion interrompue'
        finally:
            with self.lock:
                self.state['running'] = False
                if self.closed:
                    self.dispose()


sessions = Sessions(Discussion)


def artifact_text(message):
    header = '# ' + message.get('title', 'Message') + '\n\nAuteur : ' + message['speaker']
    if message.get('source_ids'):
        header += '\n\nPièces fournies : ' + ', '.join(message['source_ids'])
    if message.get('received_artifacts'):
        header += '\n\nAnalyses reçues : ' + ', '.join(message['received_artifacts'])
    if message.get('verdict'):
        header += '\n\nPosition déclarée : ' + message['verdict']
    text = header + '\n\n' + message['text']
    if message.get('open_points'):
        text += '\n\n## Points ouverts\n\n' + '\n'.join('- ' + v for v in message['open_points'])
    return text


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, code, data, kind='application/json'):
        body = data if isinstance(data, bytes) else (json.dumps(data, ensure_ascii=False) if kind == 'application/json' else data).encode()
        self.send_response(code)
        self.send_header('Content-Type', kind if isinstance(data, bytes) else kind + '; charset=utf-8')
        origin = self.headers.get('Origin')
        if origin in ALLOWED_ORIGINS:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def allowed(self):
        return self.headers.get('Host') in ('127.0.0.1:' + str(PORT), 'localhost:' + str(PORT))

    def origin_allowed(self):
        return self.headers.get('Origin') is None or self.headers.get('Origin') in ALLOWED_ORIGINS

    def do_OPTIONS(self):
        if not self.allowed() or not self.origin_allowed():
            return self.send(403, {})
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', self.headers.get('Origin', ''))
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Duo-Token, X-Duo-Session')
        self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.send_header('Vary', 'Origin')
        self.end_headers()

    def do_GET(self):
        if not self.allowed() or not self.origin_allowed():
            return self.send(403, {'error': 'Accès local uniquement'})
        if self.path == '/launch' and HOSTED_URL:
            self.send_response(302)
            self.send_header('Location', HOSTED_URL.rstrip('/') + '/#bridge=' + TOKEN)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.end_headers()
            return
        if self.path == '/':
            return self.send(200, (ROOT / 'index.html').read_text().replace('__TOKEN__', TOKEN), 'text/html')
        if self.headers.get('X-Duo-Token') != TOKEN:
            return self.send(403, {'error': 'Accès refusé'})
        discussion = sessions.get(self.headers.get('X-Duo-Session'))
        if discussion is None:
            return self.send(410, {'error': 'Cette discussion a été effacée. Ouvre une nouvelle discussion.'})
        if self.path == '/state':
            return self.send(200, discussion.snapshot())
        if self.path == '/connections':
            return self.send(200, authentication())
        if self.path == '/attachments':
            return self.send(200, discussion.list_sources())
        if self.path.startswith('/project-manifest/'):
            with discussion.lock:
                source = discussion.sources.get(self.path.rsplit('/', 1)[-1])
                if not source or not source.get('is_project'):
                    return self.send(404, {'error': 'Projet introuvable'})
                return self.send(200, {'name': source['name'], 'origin': source['project_origin'], 'included': source['project_manifest'], 'excluded': source['project_excluded']})
        if self.path.startswith(('/download/', '/output/')):
            with discussion.lock:
                item = discussion.generated.get(self.path.rsplit('/', 1)[-1])
                if not item:
                    return self.send(404, {'error': 'Fichier introuvable'})
                if self.path.startswith('/download/'):
                    return self.send(200, item['raw'], item['mime'])
                return self.send(200, dict(discussion.output_metadata(item), text=item['review_text']))
        if self.path.startswith('/attachment/'):
            with discussion.lock:
                source = discussion.sources.get(self.path.rsplit('/', 1)[-1])
                if source:
                    return self.send(200, dict(discussion.source_metadata(source), text=source['text']))
            return self.send(404, {'error': 'Pièce introuvable'})
        if self.path == '/bundle':
            return self.send(200, discussion.bundle(), 'application/zip')
        self.send(404, {})

    def do_POST(self):
        if not self.allowed() or not self.origin_allowed():
            return self.send(403, {'error': 'Accès refusé'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            maximum = 44 * 1024 * 1024 if self.path == '/project-import' else MAX_FILE * 4 // 3 + 4096 if self.path == '/upload' else 60000
            if not 0 < size <= maximum:
                raise ValueError('Demande trop volumineuse.')
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict):
                raise ValueError('Demande invalide.')
            # sendBeacon on pagehide cannot set custom headers.
            token = data.get('token') if self.path == '/session/end' else self.headers.get('X-Duo-Token')
            if not isinstance(token, str) or not secrets.compare_digest(token, TOKEN):
                return self.send(403, {'error': 'Accès refusé'})
            if self.path == '/session/open':
                return self.send(200, {'session': sessions.open()})
            if self.path == '/session/end':
                sessions.end(data.get('session'))
                return self.send(200, {'ended': True})
            discussion = sessions.get(self.headers.get('X-Duo-Session'))
            if discussion is None:
                return self.send(410, {'error': 'Cette discussion a été effacée. Ouvre une nouvelle discussion.'})
            if self.path == '/start':
                discussion.start(data.get('topic'), data.get('rounds'), data.get('confirmed'), data.get('mode', 'discussion'), data.get('first', 'Codex'), data.get('sources', []), data.get('output_formats', []))
            elif self.path == '/followup':
                discussion.followup(data.get('note'), data.get('recipient'), data.get('confirmed'), data.get('output_formats', []), data.get('sources'))
            elif self.path == '/export-analysis':
                return self.send(200, discussion.export_analysis(data.get('id'), data.get('format')))
            elif self.path == '/upload':
                return self.send(200, discussion.upload(data))
            elif self.path == '/project-import':
                return self.send(200, discussion.add_project(data))
            elif self.path == '/project-github':
                return self.send(200, discussion.add_project(data, github=True))
            elif self.path == '/remove-source':
                discussion.remove_source(data.get('id'))
                return self.send(200, discussion.list_sources())
            elif self.path == '/stop':
                discussion.stop()
            else:
                return self.send(404, {})
            self.send(200, discussion.snapshot())
        except (ValueError, AttributeError) as error:
            self.send(400, {'error': str(error)})


if __name__ == '__main__':
    threading.Thread(target=sessions.reap, daemon=True).start()
    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    print('Duo est prêt : http://127.0.0.1:' + str(PORT), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sessions.close()
        server.server_close()

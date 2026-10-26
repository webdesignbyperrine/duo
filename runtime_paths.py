"""Chemins portables, profils personnels et processus sans fenêtre de terminal."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
DESKTOP = getattr(sys, 'frozen', False) or os.environ.get('DUO_DESKTOP') == '1'


def user_data():
    # Only a deliberate test override; installers never ship a prefilled profile.
    override = os.environ.get('DUO_DATA_DIR')
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == 'win32':
        return Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Duo'
    if sys.platform == 'darwin':
        return Path.home() / 'Library/Application Support/Duo'
    return Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'duo'


def private_directory(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name != 'nt':
        path.chmod(0o700)
    return path


def provider_environment():
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('ANTHROPIC_', 'OPENAI_', 'AZURE_OPENAI_', 'CLAUDE_CODE_USE_', 'CODEX_')) or key in ('CLAUDE_CODE_OAUTH_TOKEN', 'CLAUDECODE', 'CLAUDE_CONFIG_DIR'):
            env.pop(key, None)
    if DESKTOP:
        base = private_directory(user_data() / 'accounts')
        env['CODEX_HOME'] = str(private_directory(base / 'codex'))
        env['CLAUDE_CONFIG_DIR'] = str(private_directory(base / 'claude'))
        env['DISABLE_AUTOUPDATER'] = '1'
    return env


def provider_binary(name):
    if name not in ('codex', 'claude'):
        raise ValueError('Assistant inconnu.')
    if DESKTOP:
        if os.name=='nt' and name=='codex':
            packaged = user_data() / 'tools/codex-package/codex-x86_64-pc-windows-msvc.exe'
            if packaged.is_file():return str(packaged)
        path = user_data() / 'tools' / (name + ('.exe' if os.name == 'nt' else ''))
        if path.is_file():
            return str(path)
        raise RuntimeError('Installe ' + ('Codex' if name == 'codex' else 'Claude Code') + ' dans « Mes connexions ».')
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


def hidden_process():
    return {'creationflags': subprocess.CREATE_NO_WINDOW} if os.name == 'nt' else {}


def terminate_tree(process, force=False):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, **hidden_process())
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
        except ProcessLookupError:
            pass


def worker_command(kind, source, output):
    args = [kind, str(source), str(output)]
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--duo-worker'] + args
    return [sys.executable, str(ROOT / 'worker.py')] + args


def office_binary():
    options = [shutil.which('soffice'), '/Applications/LibreOffice.app/Contents/MacOS/soffice']
    if os.name == 'nt':
        options += [str(Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'LibreOffice/program/soffice.exe')]
    # Legacy local prototype only. Never a dependency of an installed Duo.
    if not DESKTOP:
        options.append(str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice'))
    return next((str(p) for p in options if p and Path(p).is_file()), None)


def font_path():
    import reportlab
    return str(Path(reportlab.__file__).resolve().parent / 'fonts/Vera.ttf')

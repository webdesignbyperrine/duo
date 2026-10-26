"""Application autonome sans console : ouvre directement l’interface locale de Duo."""
import os
import sys


def main():
    if '--duo-worker' in sys.argv:
        from worker import run
        index=sys.argv.index('--duo-worker')
        return run(*sys.argv[index+1:index+4])
    os.environ['DUO_DESKTOP']='1'
    import json
    from pathlib import Path
    import subprocess
    import threading
    import time
    from http.server import ThreadingHTTPServer
    import server
    from desktop_setup import setup
    from runtime_paths import provider_environment, hidden_process
    env=provider_environment()
    if '--self-test' in sys.argv:
        from file_factory import build_files
        from attachments import extract
        created,errors=build_files([{'name':'verification.pdf','format':'pdf','content':'# Duo\nApplication autonome.'}])
        if errors or len(created)!=1:raise RuntimeError('Le traitement documentaire autonome a échoué.')
        assert 'Duo' in extract(created[0]['name'],created[0]['raw'])['text']
        report={'ok':True,'isolated_profiles':env['CODEX_HOME']!=str(Path.home()/'.codex') and env['CLAUDE_CONFIG_DIR']!=str(Path.home()/'.claude'),'credentials_shipped':False,'pdf_roundtrip':True}
        if '--test-install' in sys.argv:
            for provider in ('codex','claude'):
                setup.run('install',provider)
                state=setup.snapshot()
                report[provider]={'ok':not bool(state['error']),'error':state['error'],'diagnostic':state.get('diagnostic','')}
                if state['error']:report['ok']=False
            if report['ok']:
                connections=server.authentication()
                report['empty_accounts']=all(c['installed'] and not c['ok'] for c in connections.values())
                report['ok']=report['ok'] and report['empty_accounts']
        if '--report' in sys.argv:Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps(report),encoding='utf-8')
        return 0 if report['ok'] else 1
    http=None
    for port in range(8787,8797):
        try:
            server.PORT=port
            http=ThreadingHTTPServer(('127.0.0.1',port),server.Handler)
            break
        except OSError:continue
    if http is None:return 1
    http.active_requests=0
    http.requests_lock=threading.Lock()
    local='http://127.0.0.1:'+str(server.PORT)
    server.ALLOWED_ORIGINS.update({local,'http://localhost:'+str(server.PORT)})
    threading.Thread(target=server.sessions.reap,daemon=True).start()
    def open_interface():
        if sys.platform=='darwin':subprocess.run(['/usr/bin/open',local+'/'],capture_output=True,timeout=20)
        elif os.name=='nt':os.startfile(local+'/')
        else:
            import webbrowser
            webbrowser.open(local+'/')
    threading.Thread(target=open_interface,daemon=True).start()
    def stop_when_unused():
        seen=False;idle=time.monotonic()
        while True:
            time.sleep(1)
            with server.sessions.lock:active=bool(server.sessions.items)
            if active or setup.snapshot()['busy'] or http.active_requests:
                seen=True;idle=time.monotonic()
            elif time.monotonic()-idle>(20 if seen else 180):
                http.shutdown();return
    threading.Thread(target=stop_when_unused,daemon=True).start()
    try:
        http.serve_forever()
    finally:
        server.sessions.close();setup.cancel()
        # Let cancelled workers and transient imports finish removing their temporary files.
        limit=time.monotonic()+240
        while http.active_requests and time.monotonic()<limit:time.sleep(.2)
        time.sleep(4)
        http.server_close()
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        if '--self-test' in sys.argv and '--report' in sys.argv:
            from pathlib import Path
            import json
            Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps({'ok':False,'error_type':type(error).__name__}),encoding='utf-8')
        raise SystemExit(1)

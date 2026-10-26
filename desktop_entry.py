"""Point d’entrée de l’application autonome Duo (aucune console utilisateur)."""
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
    import threading
    import webbrowser
    import tkinter as tk
    from tkinter import ttk
    from http.server import ThreadingHTTPServer
    import server
    from desktop_setup import setup
    from runtime_paths import provider_environment
    # Create only this user's empty app-specific account directories.
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
        if '--report' in sys.argv:Path(sys.argv[sys.argv.index('--report')+1]).write_text(json.dumps(report),encoding='utf-8')
        return 0
    root=tk.Tk();root.title('Duo');root.geometry('560x360');root.resizable(False,False)
    root.configure(bg='#f5f4ee')
    style=ttk.Style();style.configure('TButton',font=('Arial',12),padding=10)
    panel=tk.Frame(root,bg='#f5f4ee',padx=30,pady=25);panel.pack(fill='both',expand=True)
    tk.Label(panel,text='Duo',font=('Arial',30,'bold'),bg='#f5f4ee',fg='#23312d').pack(anchor='w')
    tk.Label(panel,text='Tes fichiers. Tes abonnements. Deux regards.',font=('Arial',13),bg='#f5f4ee',fg='#53635b').pack(anchor='w',pady=(8,12))
    http=None
    for port in range(8787,8797):
        try:
            server.PORT=port
            http=ThreadingHTTPServer(('127.0.0.1',port),server.Handler)
            break
        except OSError:continue
    if http is None:
        tk.Label(panel,text='Duo ne trouve pas de connexion locale libre. Ferme une autre\ninstance de Duo puis relance l’application.',bg='#f5f4ee',fg='#9a3029').pack();root.mainloop();return 1
    local='http://127.0.0.1:'+str(server.PORT)
    server.ALLOWED_ORIGINS.update({local,'http://localhost:'+str(server.PORT)})
    threading.Thread(target=http.serve_forever,daemon=True).start()
    threading.Thread(target=server.sessions.reap,daemon=True).start()
    ttk.Button(panel,text='Ouvrir Duo et mes connexions',command=lambda:webbrowser.open(local+'/')).pack(anchor='w',pady=8)
    tk.Label(panel,text='Le navigateur s’ouvre pour configurer tes comptes.\nAucun historique de discussion n’est enregistré.\nCette application reste ouverte pendant tes échanges.',justify='left',font=('Arial',11),bg='#f5f4ee',fg='#53635b').pack(anchor='w',pady=10)
    closing=False
    def close():
        nonlocal closing
        if closing:return
        closing=True
        server.sessions.close();setup.cancel();http.shutdown();http.server_close();root.destroy()
    ttk.Button(panel,text='Quitter Duo',command=close).pack(anchor='w',pady=8)
    root.protocol('WM_DELETE_WINDOW',close)
    if sys.platform=='darwin':root.createcommand('tk::mac::Quit',close)
    root.after(400,lambda:webbrowser.open(local+'/'))
    root.mainloop()
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        if '--self-test' in sys.argv:
            if '--report' in sys.argv:
                from pathlib import Path
                Path(sys.argv[sys.argv.index('--report')+1]).write_text('{"ok": false}',encoding='utf-8')
            raise SystemExit(1)
        # No diagnostic containing accounts or documents is persisted.
        try:
            import tkinter.messagebox as box
            box.showerror('Duo','Duo n’a pas pu démarrer. Ferme l’application puis réessaie.')
        except Exception:pass
        raise SystemExit(1)

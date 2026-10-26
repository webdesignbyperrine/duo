"""Traitement documentaire isolé ; protocole par fichiers, compatible applications sans console."""
import base64
import json
from pathlib import Path
import tempfile


def run(kind, source, output):
    try:
        if kind=='extract':
            from attachments import parse
            payload=parse(Path(source))
        elif kind=='build':
            from file_factory import compile_spec
            spec=json.loads(Path(source).read_text(encoding='utf-8'))
            with tempfile.TemporaryDirectory(prefix='duo-export-') as folder:
                payload=compile_spec(spec,Path(folder))
                payload['base64']=base64.b64encode(payload.pop('raw')).decode()
        else:
            raise ValueError('Traitement non reconnu.')
        Path(output).write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
        return 0
    except Exception as error:
        Path(output).write_text(json.dumps({'error':str(error)},ensure_ascii=False),encoding='utf-8')
        return 1


if __name__=='__main__':
    import sys
    sys.exit(run(*sys.argv[1:4]))

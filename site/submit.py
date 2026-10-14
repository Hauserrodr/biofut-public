"""Send a review item from this PC to the site's queue (biofut.h-brain.org/admin). Nothing goes live until Gab approves or 6 h pass.

  python submit.py sumula "Súmula 2026-10-08" sheet.json   # the OCR pipeline's JSON: {date, games: [...], notes}
  python submit.py wiki "Wiki: ..." item.json              # what wiki/bits.py update makes (it calls send() itself)
  python submit.py listas "Listas" data/listas.json         # what listas.py --send does
  python submit.py aviso "12 fotos legendadas"             # no review: straight to the BioFut Avisos group
Media the item needs (new chat photos) go first, then the item, written as .tmp and renamed so the server never reads half a file.
"""
import json, os, subprocess, sys, tempfile, time

KEY = os.environ.get('BIOFUT_SSH_KEY', '')
HOST = os.environ.get('BIOFUT_HOST', '')
ROOT = '/srv/biofut/data'
SSH = ['-o', 'BatchMode=yes', '-i', KEY]


def send(kind, title, payload, media=()):
    if media:
        subprocess.run(['scp', '-q', *SSH, *media, f'{HOST}:{ROOT}/wiki/media/'], check=True)
    name = f"{time.strftime('%Y%m%d-%H%M%S')}-{kind}"
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False, encoding='utf-8') as f:
        json.dump({'kind': kind, 'title': title, 'payload': payload}, f, ensure_ascii=False)
    try:
        subprocess.run(['ssh', *SSH, HOST, f'mkdir -p {ROOT}/review/inbox'], check=True)
        subprocess.run(['scp', '-q', *SSH, f.name, f'{HOST}:{ROOT}/review/inbox/{name}.tmp'], check=True)
        subprocess.run(['ssh', *SSH, HOST, f'mv {ROOT}/review/inbox/{name}.tmp {ROOT}/review/inbox/{name}.json'], check=True)
    finally:
        os.unlink(f.name)
    print('sent', name, '-', title)


def aviso(text):
    """Tell the Avisos group what a pipeline just ran. Never raises: a pipeline doesn't fail over a notice."""
    try:
        send('aviso', '', {'text': text})
    except Exception as e:
        print('aviso not sent:', e)


if __name__ == '__main__':
    if sys.argv[1] == 'aviso':
        aviso(sys.argv[2])
    else:
        kind, title, path = sys.argv[1:4]
        send(kind, title, json.load(open(path, encoding='utf-8')))

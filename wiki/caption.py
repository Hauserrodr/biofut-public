"""Caption and OCR every image of the BioFut chat with a local vision model (LM Studio, Qwen2.5-VL 7B).

For each image message: what kind of picture it is, the text in it, how many people, a one-line
caption. Appends to derived/images.jsonl and skips images already done, so it can be stopped and rerun.
Match summaries and team photos are what the site wants (scores, who played, player photos).

Usage: lms server start; lms load qwen/qwen2.5-vl-7b
       python caption.py [--limit N] [--selftest]
"""
import base64, bisect, datetime as dt, io, json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
HERE = os.environ.get('BIOFUT_CHAT', 'D:/dev/BDSMA/whatsapp')  # chat export + derived/ live here, never in git

SRC = os.path.join(HERE, 'out', 'biofut_messages.jsonl')
MEDIA = os.path.join(HERE, 'export', 'media')  # IMG-*.jpg unzipped from the export
RESULT = re.compile(r'tabela|placar|resultado|artilh|\b\d{1,2} ?x ?\d{1,2}\b', re.I)
DEEPSEEK = '--deepseek' in sys.argv  # paid: api.deepseek.com, DEEPSEEK_API_KEY; default is local LM Studio
API = 'https://api.deepseek.com/chat/completions' if DEEPSEEK else 'http://localhost:1234/v1/chat/completions'
MODEL = 'deepseek-flash' if DEEPSEEK else 'qwen/qwen2.5-vl-7b'
OUT = os.path.join(HERE, 'derived', 'images_deepseek.jsonl' if DEEPSEEK else 'images.jsonl')
USAGE = os.path.join(HERE, 'derived', 'usage.jsonl')  # token counts per paid call, to track spend
KINDS = ('match_summary', 'scoreboard', 'team_photo', 'person_photo', 'list_screenshot', 'chat_screenshot',
         'poster', 'meme', 'other')
PROMPT = ('This image was posted in a Brazilian amateur 7-a-side (society) football group chat. Reply with JSON only: '
          '{"kind": "<one of ' + '|'.join(KINDS) + '>", "people": <number of people visible>, '
          '"text": "<all readable text in the image, empty if none>", "caption": "<one short sentence in English>"}. '
          'match_summary = a graphic or note with a game result, goals or stats; team_photo = a group of players posing.')


def path(m):
    p = m['media_path']
    return p if os.path.isabs(p) else os.path.join(MEDIA, p)


def parse(reply):
    """Model reply -> dict; tolerates ```json fences and a missing field."""
    s = re.search(r'\{.*\}', reply, re.S)
    try:  # the 7B model often leaves the kind unquoted: {"kind": other, ...}
        d = json.loads(re.sub(r'("kind":\s*)([a-z_]+)', r'\1"\2"', s.group(0))) if s else {}
    except ValueError:
        d = {}
    kind = str(d.get('kind', '')).strip().lower()
    return {'kind': kind if kind in KINDS else 'other', 'people': int(d['people']) if str(d.get('people', '')).isdigit() else None,
            'text': str(d.get('text') or ''), 'caption': str(d.get('caption') or ('' if d else reply[:200]))}


def ask(file):
    from PIL import Image
    im = Image.open(file).convert('RGB')
    im.thumbnail((1024, 1024))  # ponytail: fixed downscale; small score text may blur, raise if OCR misses it
    buf = io.BytesIO()
    im.save(buf, 'JPEG', quality=85)
    body = {'model': MODEL, 'temperature': 0, 'max_tokens': 1500 if DEEPSEEK else 400, 'messages': [{'role': 'user', 'content': [
        {'type': 'text', 'text': PROMPT},
        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()}}]}]}
    if DEEPSEEK:  # with thinking on, a score table burns 3000+ reasoning tokens and returns nothing
        body['thinking'] = {'type': 'disabled'}
    head = {'Content-Type': 'application/json'}
    if DEEPSEEK:
        head['Authorization'] = 'Bearer ' + os.environ['DEEPSEEK_API_KEY']
    reply = json.load(urllib.request.urlopen(urllib.request.Request(API, json.dumps(body).encode(), head), timeout=180))
    if DEEPSEEK:
        with open(USAGE, 'a') as f:
            f.write(json.dumps({'file': os.path.basename(file), **reply.get('usage', {})}) + '\n')
    content = reply['choices'][0]['message']['content']
    if not content.strip():  # out of tokens mid-reasoning: a miss, not a result, so a rerun retries it
        raise ValueError('empty content, finish_reason=' + str(reply['choices'][0].get('finish_reason')))
    return content


def main():
    if '--selftest' in sys.argv:
        assert parse('```json\n{"kind": "Team_Photo", "people": 12, "text": "", "caption": "x"}\n```') == \
            {'kind': 'team_photo', 'people': 12, 'text': '', 'caption': 'x'}
        assert parse('{"kind": "selfie", "people": "two"}')['kind'] == 'other' and parse('no json')['caption'] == 'no json'
        assert parse('{"kind": person_photo, "people": 5, "text": "", "caption": "x"}')['kind'] == 'person_photo'
        return print('selftest ok')
    limit = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    done = {json.loads(l)['file'] for l in open(OUT, encoding='utf-8')} if os.path.exists(OUT) else set()
    msgs = [json.loads(l) for l in open(SRC, encoding='utf-8')]
    todo = [m for m in msgs if m.get('type') == 'image' and m.get('media_path')
            and os.path.basename(m['media_path']) not in done and os.path.exists(path(m))]
    todo = list({os.path.basename(m['media_path']): m for m in reversed(todo)}.values())[::-1]  # one file, several messages: first wins
    # Results and standings first: images posted within 10 min of a message about them.
    hot = [m['ts'] for m in msgs if RESULT.search(m.get('text') or '')]
    near = lambda ts: any(abs(ts - h) < 600 for h in hot[bisect.bisect_left(hot, ts - 600):][:50])
    todo = sorted(todo, key=lambda m: not near(m['ts']))[:limit]
    print(f'{len(done)} done, {len(todo)} to go')
    def one(m):
        try:
            return m, parse(ask(path(m)))
        except Exception as e:  # one bad image must not stop a 3-hour run
            print('skip', m['media_path'], e, flush=True)
            return m, None

    with open(OUT, 'a', encoding='utf-8') as f, ThreadPoolExecutor(12 if DEEPSEEK else 4) as pool:  # LM Studio serves 4 in parallel; the API is latency-bound
        for i, (m, r) in enumerate(pool.map(one, todo)):
            if not r:
                continue
            r.update(file=os.path.basename(m['media_path']), date=dt.date.fromtimestamp(m['ts']).isoformat(),
                     sender=m.get('sender_name') or m.get('sender'), msg=(m.get('text') or '')[:200])
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
            f.flush()
            if i % 50 == 0:
                print(i, r['date'], r['kind'], r['caption'][:80], flush=True)
    if todo:  # the captions feed the wiki (bits.py update --send), which goes through /admin; this only says it ran
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site'))
        from submit import aviso
        aviso(f"📷 caption.py ({MODEL}): {len(todo)} imagens novas legendadas; total {len(done) + len(todo)}")


if __name__ == '__main__':
    main()

"""BioFut Wiki: turn the group chat into a Desciclopédia-style wiki.

Steps (each resumable, outputs in derived/wiki/):
  chunks   chat + image captions -> conversation chunks (chunks.jsonl), names instead of phones; index with leviathan
  extract  DeepSeek Flash reads each day and lists its events: importance, funny, people, topics, characters, quotes
  canon    per year, events -> wiki pages (person, character, saga, meme...); the same page across years is merged by name
  profile  the group's humor profile, from the funniest events: a page plus a style guide for the writer
  write    one Desciclopédia-style article per page, from its events and leviathan search hits in the chat
  curate   per page: is it fine for the public wiki, and up to 3 real photos with a caption, picked from the image descriptions
  site     site/data/wiki/: member.json (all pages, chat refs, photos in media/) and public.json (public pages, no chats)
Usage: python wiki.py chunks|extract|canon|profile|write|curate|site|selftest [--limit N]
Paid steps log token counts to derived/wiki/usage.jsonl. Chat and outputs stay out of git: BIOFUT_CHAT is the export folder.
Image descriptions come from caption.py.
"""
import collections, datetime as dt, json, os, re, sys, urllib.request
from concurrent.futures import ThreadPoolExecutor
HERE = os.environ.get('BIOFUT_CHAT', 'D:/dev/BDSMA/whatsapp')  # chat export + derived/ live here, never in git

D = os.path.join(HERE, 'derived')
W = os.path.join(D, 'wiki')
MSGS = os.path.join(HERE, 'out', 'biofut_messages.jsonl')
SENDERS = os.path.join(D, 'senders.json')
CHUNKS = os.path.join(W, 'chunks.jsonl')
EVENTS = os.path.join(W, 'events.jsonl')
USAGE = os.path.join(W, 'usage.jsonl')  # own file: caption.py appends to derived/usage.jsonl at the same time
API = 'https://api.deepseek.com/chat/completions'
GAP = 45 * 60      # a silence this long starts a new conversation chunk
CHUNK_CHARS = 6000
BATCH_CHARS = 40000  # ~12k tokens of chat per extract call
ANON = re.compile(r'^\+?[\d\s()-]+$|@lid$|@s\.whatsapp')
ATTACHED = re.compile(r'‎?\S+\.\w{2,4} \(arquivo anexado\)')  # "STK-...webp (arquivo anexado)": the file name is noise
MEDIA = {'sticker': '[figurinha]', 'audio': '[áudio]', 'video': '[vídeo]', 'document': '[documento]'}


def names(login=True):
    """sender (contact name or lid) -> display name; never a phone number. login: the site login's map (phones.py writes
    derived/senders.json) over the chat miner's 10-06 draft, which had Leo Saul as Victor and Dan as Barp."""
    out = {}
    for p in json.load(open(os.path.join(D, 'people.json'), encoding='utf-8'))['people']:
        named = [s for s in p['senders'] if not ANON.search(s)]
        show = p.get('db_player') or (named[0] if named else p['aliases'][0].title() if p['aliases'] else 'Alguém')
        for s in p['senders']:
            out[s] = show
    if login and os.path.exists(SENDERS):
        out.update(json.load(open(SENDERS, encoding='utf-8')))
    return out


def who(m, nm):
    s = m.get('sender_name') or m.get('sender') or ''
    return nm.get(s) or nm.get(m.get('sender')) or ('Alguém' if ANON.search(s) or not s else s)


def line(m, nm, img):
    t = ATTACHED.sub('', m.get('text') or '').strip()
    kind = m.get('type')
    if kind == 'image':
        c = img.get(os.path.basename(m.get('media_path') or ''))
        pic = f"[foto: {c['caption']}" + (f" | texto na imagem: {c['text'][:300]}" if c and c['text'] else '') + ']' if c else '[foto]'
        t = (pic + ' ' + t).strip()
    elif kind in MEDIA:
        t = (MEDIA[kind] + ' ' + t).strip()
    if not t:
        return None
    t = re.sub(r'\+?55 ?\d{2} ?\d{4,5}-?\d{4}', '[tel]', t)  # numbers pasted in messages
    return f"{dt.datetime.fromtimestamp(m['ts']):%H:%M} {who(m, nm)}: {t}"


def scrub(t, nm):
    """For the site, after the fact so chunk ids stay put: @mentions carry a lid or phone, receipts carry account numbers."""
    t = re.sub(r'@(\d{6,})', lambda g: '@' + (nm.get(g[1] + '@lid') or 'alguém'), t)
    t = re.sub(r'(?<!\d)(\(?\d{2}\)?[\s.-]?)?9?\d{4}[\s.-]\d{4}(?!\d)', '…', t)  # written phones: (51) 90000-0003
    return re.sub(r'\d{8,}', '…', t)


def society(t):
    """BioFut is fut 7 society at Planet Ball, never futsal (Gab, 2026-10-09). Quotes («...», > lines) stay as said."""
    return re.sub(r'(?m)(«[^»]*»|^>.*$)|\bfutsal\b', lambda m: m[1] or 'fut 7', t, flags=re.I) if t else t


def tidy(md):
    """Writer slips: [[Categoria:...]] tags, bare {{BioFut}} templates, and a "Ver também" that pastes every title."""
    md = society(md)
    md = re.sub(r'(?m)^\s*(\[\[Categoria:[^\]]*\]\]|\{\{[^|{}]*\}\})\s*$\n?', '', md)
    md = re.sub(r'(?m)^(=+)\s*(.*?)\s*\1\s*$', lambda m: '#' * len(m[1]) + ' ' + m[2], md)  # some pages come back in MediaWiki syntax
    md = re.sub(r"'''(.+?)'''", r'**\1**', md)
    md = re.sub(r"''(.+?)''", r'*\1*', md)
    head, sep, tail = md.partition('## Ver também')
    if not sep:
        return md
    items = re.findall(r'(?m)^\s*[-*] .*$', tail)
    rest = re.sub(r'(?m)^\s*[-*] .*$\n?', '', tail).strip()
    return head + sep + '\n\n' + '\n'.join(items[:10]) + ('\n\n' + rest if rest else '') + '\n'


def chunks():
    nm, draft = names(), names(False)  # cut where the draft names cut: events, bits and pages cite chunk ids
    img = {}
    for f in ('images.jsonl', 'images_deepseek.jsonl'):  # DeepSeek captions win over the older Qwen pass
        p = os.path.join(D, f)
        if os.path.exists(p):
            img.update({r['file']: r for r in map(json.loads, open(p, encoding='utf-8'))})
    os.makedirs(W, exist_ok=True)
    out, cur, last = [], None, 0
    for l in open(MSGS, encoding='utf-8'):
        m = json.loads(l)
        s = line(m, nm, img)
        if not s:
            continue
        day = dt.date.fromtimestamp(m['ts']).isoformat()
        if not cur or m['ts'] - last > GAP or size > CHUNK_CHARS or cur['day'] != day:
            n = sum(1 for c in out if c['day'] == day) + 1
            cur = {'id': f'c{day}-{n:02d}', 'day': day, 'month': day[:7], 'date': dt.datetime.fromtimestamp(m['ts']).isoformat(),
                   'people': [], 'text': ''}
            out.append(cur)
            size = 0
        cur['text'] += s + '\n'
        size += len(line(m, draft, img)) + 1
        p = who(m, nm)
        if p not in cur['people'] and p not in ('Alguém', 'Meta AI'):
            cur['people'].append(p)
        last = m['ts']
    with open(CHUNKS, 'w', encoding='utf-8') as f:
        for c in out:
            c['title'] = c['text'].split('\n', 1)[0][:100]
            f.write(json.dumps(c, ensure_ascii=False) + '\n')
    print(len(out), 'chunks ->', CHUNKS)


PROMPT = """Você está lendo o histórico do grupo de WhatsApp "BioFut", um futebol 7 (society) amador de amigos, jogado no Planet Ball em Porto Alegre (desde 2019; o histórico aqui começa em 2022-08).
Vamos escrever uma wiki do grupo no estilo Desciclopédia. Leia as conversas abaixo (cada bloco começa com [id]) e liste os ACONTECIMENTOS que valem registro:
tretas, piadas que viraram bordão, apelidos nascendo, jogos memoráveis, polêmicas de lista/pagamento/arbitragem, enquetes, músicas, personagens fictícios, memes recorrentes, decisões da "diretoria", eventos (churrasco, copa, campeonato).
Ignore a rotina sem graça (só lista de presença, "vou", "tô dentro") a menos que algo aconteça nela.

Responda só com JSON: {"events": [{
 "title": "título curto e engraçado em português",
 "summary": "2 a 4 frases contando o que aconteceu, com o contexto necessário",
 "importance": 0-10 (o quanto isso é parte do 'cânone' do grupo, 10 = lenda que todo mundo cita),
 "funny": 0-10 (o quanto o grupo achou graça: kkkk, figurinhas, zoeira em cadeia),
 "people": ["nomes como aparecem"],
 "topics": ["temas curtos e reutilizáveis, ex.: 'arbitragem', 'pagamento', 'lista', 'copa biofut'"],
 "characters": ["personagens, personas e bordões recorrentes, ex.: 'BioFut King', 'Nego Dei', 'GabsIA'"],
 "quotes": [{"who": "nome", "text": "frase literal da conversa"}],
 "chunks": ["ids dos blocos de onde veio"]
}]}
No máximo 12 acontecimentos por resposta (os melhores), no máximo 3 citações cada. Lista vazia se nada valer. Use só o que está no texto; não invente. Nunca escreva números de telefone."""


def deepseek(system, user, max_tokens=8000):
    body = {'model': 'deepseek-flash', 'temperature': 0.3, 'max_tokens': max_tokens, 'thinking': {'type': 'disabled'},
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]}
    req = urllib.request.Request(API, json.dumps(body).encode(), {
        'Content-Type': 'application/json', 'Authorization': 'Bearer ' + os.environ['DEEPSEEK_API_KEY']})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    with open(USAGE, 'a') as f:
        f.write(json.dumps({'step': 'wiki', **r.get('usage', {})}) + '\n')
    if r['choices'][0].get('finish_reason') != 'stop':
        raise ValueError('finish_reason=' + str(r['choices'][0].get('finish_reason')))
    return json.loads(r['choices'][0]['message']['content'])


def batches():
    """Chunks packed into extract calls: whole days together, a long day split, never mixing two months."""
    cs = [json.loads(l) for l in open(CHUNKS, encoding='utf-8')]
    out, cur = [], []
    for c in cs:
        if cur and (sum(len(x['text']) for x in cur) + len(c['text']) > BATCH_CHARS or cur[0]['month'] != c['month']):
            out.append(cur)
            cur = []
        cur.append(c)
    return out + [cur] if cur else out


def extract(limit=None):
    done = {json.loads(l)['batch'] for l in open(EVENTS, encoding='utf-8')} if os.path.exists(EVENTS) else set()
    todo = [b for b in batches() if b[0]['id'] not in done][:limit]
    print(len(done), 'batches done,', len(todo), 'to go')

    def one(b):
        text = '\n'.join(f"[{c['id']}] ({c['date'][:10]})\n{c['text']}" for c in b)
        try:
            return b, deepseek(PROMPT, text).get('events', [])
        except Exception as e:  # skipped batches are retried on the next run
            print('skip', b[0]['id'], e, flush=True)
            return b, None

    with open(EVENTS, 'a', encoding='utf-8') as f, ThreadPoolExecutor(8) as pool:
        for i, (b, evs) in enumerate(pool.map(one, todo)):
            if evs is None:
                continue
            f.write(json.dumps({'batch': b[0]['id'], 'day': b[0]['day'], 'events': evs}, ensure_ascii=False) + '\n')
            f.flush()
            if i % 20 == 0:
                print(i, b[0]['day'], len(evs), 'events', (evs[0]['title'] if evs else ''), flush=True)


def num(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return 0


def all_events():
    out = []
    for r in map(json.loads, open(EVENTS, encoding='utf-8')):
        for i, e in enumerate(r['events']):
            e.update(id=f"{r['batch']}#{i}", day=r['day'], score=num(e.get('importance')) + num(e.get('funny')))
            out.append(e)
    return out


CANON = os.path.join(W, 'canon_years.json')
PAGES = os.path.join(W, 'pages.json')
CANON_PROMPT = """Abaixo estão os acontecimentos de um período do grupo de WhatsApp "BioFut" (futebol 7 society amador de amigos), já resumidos.
Cada linha: número | dia | nota (importância+graça, 0-20) | título | personagens | temas.
Agrupe-os em VERBETES de uma wiki estilo Desciclopédia. Tipos de verbete:
 pessoa (um membro do grupo), personagem (persona fictícia, alter ego, figura recorrente: ex. BioFut King), saga (história que se estende por vários dias: uma copa, uma treta longa),
 meme (bordão, piada interna, figurinha), tema (assunto recorrente: arbitragem, pagamento, lista), evento (um dia marcante), lugar.
Crie de 25 a 45 verbetes para o período (nunca mais de 45). Um acontecimento pode estar em vários verbetes (o da pessoa e o da saga).
Crie verbete de pessoa para quem aparece em muitos acontecimentos. Use o nome mais usado no grupo como título; apelidos vão em aliases.
Responda só com JSON: {"pages": [{"title": "...", "type": "pessoa|personagem|saga|meme|tema|evento|lugar", "aliases": ["..."], "pitch": "uma frase", "events": [números]}]}"""


# Same person or meme under two titles, checked in the chat ("caniva com 5 derrotas", "Doug Daronco", "Guiih emulando o Creed").
SAME = {'Caniva': 'Canova', 'Mappeli': 'Mapelli', 'Victor Cromer Vianna': 'Victor', 'Daronco': 'Douglas', 'Arthur Hanauer': 'Hanauer',
        'Creed': 'Guih', 'Lirionado': 'GOLIRIO', 'Naruto': 'Naruto Uzumaki', '17h99': '17:99'}


def norm(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s.lower()).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'\b(o|a|os|as|do|da|de|the)\b|[^a-z0-9 ]', ' ', s).split())


def canon():
    ev = all_events()
    done = json.load(open(CANON, encoding='utf-8')) if os.path.exists(CANON) else {}
    parts = {}  # a busy year overflows the 8k output, so cut it into periods of <=250 events: "2025.1", "2025.2", ...
    for year in sorted({e['day'][:4] for e in ev}):
        ys = sorted((e for e in ev if e['day'][:4] == year and e['score'] >= 13), key=lambda e: e['day'])  # ponytail: score cut, lower it if pages feel thin
        k = -(-len(ys) // 250)
        parts.update({year: ys} if k == 1 else {f'{year}.{j + 1}': ys[j * len(ys) // k:(j + 1) * len(ys) // k] for j in range(k)})
    def one(key):
        lines = [f"{n} | {e['day']} | {e['score']} | {e['title']} | {', '.join(e.get('characters') or [])} | {', '.join(e.get('topics') or [])}"
                 for n, e in enumerate(parts[key])]
        try:
            return key, deepseek(CANON_PROMPT, '\n'.join(lines), max_tokens=16000)
        except Exception as e:  # rerun canon to retry this period
            print('skip', key, e, flush=True)
            return key, None

    for key, r in ThreadPoolExecutor(8).map(one, sorted(set(parts) - set(done))):
        if not r:
            continue
        ys = parts[key]
        done[key] = [dict(p, events=[ys[n]['id'] for n in p.get('events', []) if isinstance(n, int) and n < len(ys)], year=key[:4])
                      for p in r.get('pages', [])]
        json.dump(done, open(CANON, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        print(key, len(ys), 'events ->', len(done[key]), "pages", flush=True)
    # Merge the same page across years: same normalized title or alias, same type family. Union-find over names.
    parent = {}
    find = lambda k: k if parent.setdefault(k, k) == k else find(parent[k])
    # the model sometimes ignores "max 45" and makes a page per event; keep each period's 45 biggest
    flat = [p for y in sorted(done) for p in sorted(done[y], key=lambda p: -len(p['events']))[:45]]
    # Only titles are join keys: alias-to-alias matches chained "Lista" into "BioFutBank" and "Andrei".
    # Through an alias a person never merges into a theme ("Lista" aka "Andrei"); the same title always merges (slugs must be unique).
    by_title = {}
    for i, p in enumerate(flat):
        by_title.setdefault(norm(p['title']), []).append(i)
    for i, p in enumerate(flat):
        for name in [p['title']] + list(p.get('aliases') or []) + [SAME.get(p['title'], '')]:
            for j in by_title.get(norm(name), []):
                if name in (p['title'], SAME.get(p['title'])) or (flat[j]['type'] == 'pessoa') == (p['type'] == 'pessoa'):
                    parent[find(i)] = find(j)
    groups = collections.defaultdict(list)
    for i, p in enumerate(flat):
        groups[find(i)].append(p)
    pages = []
    for g in groups.values():
        votes = collections.Counter(norm(p['title']) for p in g)  # the title most periods used, ties to the biggest page
        main = max(g, key=lambda p: (p['title'] in SAME.values(), votes[norm(p['title'])], len(p['events'])))
        pages.append({'title': main['title'], 'type': main['type'], 'pitch': main['pitch'],
                      'aliases': sorted({a for p in g for a in [p['title']] + list(p.get('aliases') or [])} - {main['title']}),
                      'years': sorted({p['year'] for p in g}), 'events': sorted({e for p in g for e in p['events']})})
    pages.sort(key=lambda p: -len(p['events']))
    json.dump(pages, open(PAGES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(len(flat), 'year pages ->', len(pages), 'pages ->', PAGES, collections.Counter(p['type'] for p in pages))


PROFILE = os.path.join(W, 'humor.json')
HUMOR = os.path.join(W, 'humor.md')  # the Humor BioFut page written by hand from counted, verified chat facts; wins over the profile's
PROFILE_PROMPT = """Estes são os acontecimentos mais engraçados do grupo de WhatsApp "BioFut" (futebol 7 society amador de amigos, Porto Alegre), com citações reais.
Escreva o PERFIL DE HUMOR do grupo: que tipo de piada funciona aqui, os mecanismos (zoeira em cadeia, apelidos, exagero épico de coisa banal, conspiração da diretoria,
figurinhas, enquetes, IA...), os alvos favoritos, os bordões, o que é sagrado, o que NÃO tem graça para eles, e o vocabulário típico.
Responda só com JSON: {"page": "verbete markdown 'Humor BioFut' no estilo Desciclopédia, 400-700 palavras, com exemplos reais",
"style": "guia de estilo compacto (150-250 palavras) para um redator escrever verbetes que esse grupo ache engraçados"}"""


def profile():
    ev = sorted(all_events(), key=lambda e: (-num(e.get('funny')), -e['score']))[:250]
    text = '\n'.join(f"- {e['day']} {e['title']}: {e['summary']} " + ' '.join(f'"{q.get("text")}" ({q.get("who")})' for q in (e.get('quotes') or [])[:2])
                     for e in ev)
    r = deepseek(PROFILE_PROMPT, text, max_tokens=6000)
    json.dump(r, open(PROFILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(r['style'])


ARTICLES = os.path.join(W, 'articles.jsonl')
WRITE_PROMPT = """Você escreve verbetes da "BioWiki", a Desciclopédia do grupo de futebol 7 (society) BioFut. Escreva em português, com o humor do grupo:
{style}

Regras:
- Comece com uma citação falsa no topo, estilo Desciclopédia (ex.: atribuída a Oscar Wilde, ao Galvão Bueno ou a alguém do grupo).
- Depois: introdução, seções (##), e no fim "## Ver também". No máximo uns 900 palavras.
- Os FATOS vêm só do material fornecido (datas, quem disse o quê, placares). O exagero e a zoeira ficam no tom, não em fatos inventados.
- Use as citações literais do material quando forem boas.
- Links internos: [[Título exato]] ou [[Título exato|texto]], só para títulos desta lista: {titles}
- Fontes: depois de cada fato, cite de onde veio com [ref:ID], usando os IDs entre colchetes do material (ex.: [ref:c2024-07-01-06]). Um ID por marcação. Não escreva seção de referências, ela é gerada sozinha.
- Zoeira de amigo: nada sobre saúde, família, trabalho ou dinheiro pessoal de verdade, nada de números de telefone.
Responda só com JSON: {{"markdown": "o verbete completo"}}"""


def lev_search(q, n=3):
    import subprocess
    try:
        out = subprocess.run(['D:/dev/tools/leviathan.exe', '--index', os.path.join(W, 'leviathan.db'), '--json', 'search', q, '-n', str(n)],
                             capture_output=True, text=True, encoding='utf-8', timeout=30).stdout
        return [r['id'] for r in json.loads(out).get('results', [])]
    except Exception:
        return []


def write(limit=None):
    pages = json.load(open(PAGES, encoding='utf-8'))
    style = json.load(open(PROFILE, encoding='utf-8'))['style']
    ev = {e['id']: e for e in all_events()}
    ch = {c['id']: c for c in map(json.loads, open(CHUNKS, encoding='utf-8'))}
    done = {json.loads(l)['title'] for l in open(ARTICLES, encoding='utf-8')} if os.path.exists(ARTICLES) else set()
    system = WRITE_PROMPT.format(style=style, titles='; '.join(p['title'] for p in pages))
    todo = [p for p in pages if p['title'] not in done][:limit]
    print(len(done), 'written,', len(todo), 'to go')

    def one(p):
        es = sorted(sorted((ev[i] for i in p['events'] if i in ev), key=lambda e: -e['score'])[:40], key=lambda e: e['day'])
        facts = '\n'.join(f"- {e['day']} " + ''.join(f'[ref:{c}]' for c in (e.get('chunks') or [])[:2] if c in ch) + f" — {e['title']}: {e['summary']} " + ' '.join(f'«{q.get("text")}» ({q.get("who")})' for q in (e.get('quotes') or []))
                          for e in es)
        ids = [c for e in sorted(es, key=lambda e: -e['score'])[:2] for c in (e.get('chunks') or [])[:1]]
        ids += [i for i in lev_search(' '.join([p['title']] + p['aliases'][:2])) if i not in ids][:3]
        raw = '\n\n'.join(f"[ref:{i}]\n{ch[i]['text'][:2500]}" for i in ids if i in ch)
        user = (f"Verbete: {p['title']} (tipo: {p['type']}; também chamado: {', '.join(p['aliases']) or '-'})\nResumo: {p['pitch']}\n\n"
                f"ACONTECIMENTOS:\n{facts}\n\nTRECHOS DA CONVERSA (busca no histórico):\n{raw}")
        try:
            return p, deepseek(system, user, max_tokens=12000)['markdown']
        except Exception as e:
            print('skip', p['title'], e, flush=True)
            return p, None

    with open(ARTICLES, 'a', encoding='utf-8') as f, ThreadPoolExecutor(8) as pool:
        for i, (p, md) in enumerate(pool.map(one, todo)):
            if md:
                f.write(json.dumps({'title': p['title'], 'markdown': md}, ensure_ascii=False) + '\n')
                f.flush()
            if i % 20 == 0:
                print(i, p['title'], flush=True)


SRC_IMG = {}  # image file name -> path on disk, filled by chunk_images()
MEDIA_DIR = os.path.join(HERE, 'export', 'media')
FOTO = re.compile(r'(?m)^\d\d:\d\d [^:\n]*: \[foto')


def chunk_images():
    """chunk id -> image files, in the order of its [foto] lines. Paired per day by order, because chunk ids are fixed
    and every image message makes exactly one [foto] line; a day whose counts disagree gets no photos."""
    by_day = collections.defaultdict(list)
    for m in map(json.loads, open(MSGS, encoding='utf-8')):
        if m.get('type') == 'image':
            mp = m.get('media_path') or ''
            SRC_IMG[os.path.basename(mp)] = mp if os.path.isabs(mp) else os.path.join(MEDIA_DIR, mp)
            by_day[dt.date.fromtimestamp(m['ts']).isoformat()].append(os.path.basename(mp))
    out, cs = {}, collections.defaultdict(list)
    for c in map(json.loads, open(CHUNKS, encoding='utf-8')):
        cs[c['day']].append(c)
    for day, cl in cs.items():
        ns = [len(FOTO.findall(c['text'])) for c in cl]
        if sum(ns) != len(by_day[day]):
            continue
        it = iter(by_day[day])
        out.update({c['id']: [next(it) for _ in range(n)] for c, n in zip(cl, ns) if n})
    return out


CURATE = os.path.join(W, 'curate.jsonl')
CURATE_PROMPT = """Você revisa um verbete da BioWiki (Desciclopédia do grupo de futebol 7 (society) amador BioFut) antes de publicar.
1. "public": o site tem uma versão PÚBLICA (qualquer pessoa na internet) e uma só para membros. Julgue só o TEXTO do verbete (fotos e conversas
   são só para membros). Zoeira de futebol, apelidos, atraso no Pix, pernas de pau e tretas de lista são normais e podem ser públicas.
   Marque false só se o texto tem algo pesado que prejudicaria alguém de verdade fora do grupo: piada sexual com pessoa real, drogas,
   doença, corpo, família, raça, religião, trabalho real, ou nome completo (nome + sobrenome real) de alguém. "why": motivo curto.
2. "photos": escolha até 3 fotos da lista que melhor ilustram o verbete (o momento, o meme, o placar, o time). Evite prints de lista,
   comprovantes e documentos. "legenda": uma frase curta e engraçada em português, no humor do grupo, sem inventar fatos.
Responda só com JSON: {"public": true, "why": "...", "photos": [{"file": "IMG-...jpg", "legenda": "..."}]}"""


def curate(limit=None):
    pages = json.load(open(PAGES, encoding='utf-8'))
    md = {a['title']: a['markdown'] for a in map(json.loads, open(ARTICLES, encoding='utf-8'))}
    ev = {e['id']: e for e in all_events()}
    imgs = chunk_images()
    cap = {r['file']: r for r in map(json.loads, open(os.path.join(D, 'images_deepseek.jsonl'), encoding='utf-8'))}
    done = {json.loads(l)['title'] for l in open(CURATE, encoding='utf-8')} if os.path.exists(CURATE) else set()
    todo = [p for p in pages if p['title'] in md and p['title'] not in done][:limit]
    print(len(done), 'curated,', len(todo), 'to go')

    def one(p):
        es = sorted((ev[i] for i in p['events'] if i in ev), key=lambda e: -e['score'])
        ids = list(dict.fromkeys(REF.findall(md[p['title']]) + [c for e in es for c in e.get('chunks') or []]))
        files = [f for c in ids for f in imgs.get(c, []) if f in cap and cap[f]['kind'] != 'list_screenshot']
        files = list(dict.fromkeys(files))[:60]  # ponytail: the page's best events first, cut at 60 photos
        user = (f"VERBETE: {p['title']}\n{md[p['title']][:9000]}\n\nFOTOS (arquivo | dia | tipo | descrição | texto na imagem):\n" +
                '\n'.join(f"{f} | {cap[f]['date']} | {cap[f]['kind']} | {cap[f]['caption']} | {cap[f]['text'][:120]}" for f in files))
        try:
            r = deepseek(CURATE_PROMPT, user, max_tokens=2000)
            r['photos'] = [x for x in r.get('photos') or [] if x.get('file') in files][:3]
            return p, r
        except Exception as e:
            print('skip', p['title'], e, flush=True)
            return p, None

    with open(CURATE, 'a', encoding='utf-8') as f, ThreadPoolExecutor(8) as pool:
        for i, (p, r) in enumerate(pool.map(one, todo)):
            if r:
                f.write(json.dumps({'title': p['title'], 'public': r.get('public') is not False, 'why': r.get('why', ''),
                                    'photos': r['photos']}, ensure_ascii=False) + '\n')
                f.flush()
            if i % 20 == 0:
                print(i, p['title'], r and r.get('public'), flush=True)


REVIEW = os.path.join(W, 'review.jsonl')  # review.py: Gemini's fact-check of the shown pages against the corrected chat; wins
SITE = os.path.join(W, 'site', 'index.html')
LINK = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')
REF = re.compile(r'(c\d{4}-\d\d-\d\d-\d\d)')  # inside [ref:...] markers; the writer sometimes packs several in one


def slug(s):
    return norm(s).replace(' ', '-') or 'x'


def autolink(md, names, me):
    """Links the first mention of each other page, as a wiki does (the polished leads come back with almost no links).
    names: proper name as written -> slug; case-sensitive, so 'lista' the word stays text; quotes and headings untouched."""
    low = {n.lower(): s for n, s in names.items()}
    done = {me} | {low.get(t.strip().lower()) for t in LINK.findall(md)}
    pat = re.compile(r'(?<!\w)(' + '|'.join(map(re.escape, sorted(names, key=len, reverse=True))) + r')(?!\w)')

    def sub(m):
        if names[m[1]] in done:
            return m[1]
        done.add(names[m[1]])
        return f'[[{m[1]}]]'
    return '\n'.join(l if l.lstrip().startswith(('>', '#')) else
                     ''.join(x if x.startswith('[[') else pat.sub(sub, x) for x in re.split(r'(\[\[[^\]]*\]\])', l)) for l in md.split('\n'))


OUT = os.environ.get('WIKI_OUT', os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site', 'data', 'wiki'))  # the site serves it from data/wiki (not in git)
# The curate model passes almost everything; these words keep a page members-only anyway.
HEAVY = re.compile(r'\b(maconh\w*|baseados?|drogas?|erótic\w*|sexua\w*|casadas?|idosas?|corno|gay|piranhas?|macaco|úlcera|depress\w*)\b', re.I)


def is_public(md, cur):
    return cur.get('public', False) and not HEAVY.search(md) and len(re.findall(r'\bgord[oa]s?\b', md, re.I)) < 3


def photo(f):
    """Resized copy for the site: 1280 px, JPEG 80; built once. None when the export lacks the file."""
    dst = os.path.join(OUT, 'media', f)
    if not os.path.exists(dst):
        from PIL import Image
        if not os.path.exists(SRC_IMG.get(f, '')):
            return None
        im = Image.open(SRC_IMG[f]).convert('RGB')
        im.thumbnail((1280, 1280))
        im.save(dst, 'JPEG', quality=80)
    return f


# Public photos: nobody in them (caption.py counts people), and nothing private in the picture or its text.
PUBLIC_KINDS = {'meme', 'poster', 'scoreboard', 'match_summary', 'other'}
PRIVATE_PIC = re.compile(r'receipt|comprovante|pix|bank|banc|transfer|payment|pagamento|pill|medic|rem[eé]dio|hospital|'
                         r'story|instagram|social media|@\w|phone|telefone|contato|contact|swastika|criminal|person|smok|tobacco|cigar|joint|drug|weed', re.I)


def public_photo(c):
    return bool(c) and c.get('people') == 0 and c.get('kind') in PUBLIC_KINDS and         not PRIVATE_PIC.search(f"{c.get('caption', '')} {c.get('text', '')}") and not re.search(r'\d{8,}', c.get('text') or '')


def site():
    pages = json.load(open(PAGES, encoding='utf-8'))
    md = {a['title']: tidy(a['markdown']) for a in map(json.loads, open(ARTICLES, encoding='utf-8'))}
    humor = open(HUMOR, encoding='utf-8').read() if os.path.exists(HUMOR) else json.load(open(PROFILE, encoding='utf-8'))['page']
    sel, bs = {}, {}
    if os.path.exists(os.path.join(W, 'leads.jsonl')):  # v2 (bits.py): short lead + the best-ranked bits, capped pages
        import bits as B
        sel, bs = json.load(open(B.SELECT, encoding='utf-8')), json.load(open(B.BITS, encoding='utf-8'))
        md = {a['title']: tidy(a['markdown']) for a in map(json.loads, open(B.LEADS, encoding='utf-8')) if a['title'] in sel}
    pages = [p for p in pages if p['title'] in md] + [{'title': 'Humor BioFut', 'type': 'tema', 'aliases': [], 'years': [], 'events': []}]
    md['Humor BioFut'] = society(re.sub(r'^\s*#+ *Humor BioFut *\n', '', humor))  # the page title is already the h1
    cur = {r['title']: r for r in map(json.loads, open(CURATE, encoding='utf-8'))} if os.path.exists(CURATE) else {}
    cur['Humor BioFut'] = {'public': True, 'photos': []}
    rv = {r['title']: r for r in map(json.loads, open(REVIEW, encoding='utf-8'))} if os.path.exists(REVIEW) else {}
    for p in pages:
        p['aliases'] = [a for a in p['aliases'] if a not in rv.get(p['title'], {}).get('aliases_drop', [])]
    sel = {t: [b for b in v if b not in rv.get(t, {}).get('bits_drop', [])] for t, v in sel.items()}
    cur |= {t: dict(cur.get(t, {}), photos=r['photos']) for t, r in rv.items()}
    name = {a.lower(): slug(p['title']) for p in pages for a in p['aliases']} | {p['title'].lower(): slug(p['title']) for p in pages}  # a title beats another page's alias ('Bruno M' vs BioFut King)
    ch = {c['id']: c for c in map(json.loads, open(CHUNKS, encoding='utf-8'))}
    ev = {e['id']: e for e in all_events()}
    nm = names()
    if sel:  # quotes as really said (bits.verify); Claude's leads and titles when bits.py polish ran; no invented lead quotes
        bs = B.verify(bs, ch)
        if os.path.exists(B.POLISH):
            first = {}
            for r in map(json.loads, open(B.POLISH, encoding='utf-8')):
                if r['title'] in md:
                    md[r['title']] = tidy(r['markdown'])
                first.update({i: t for i, t in r['titles'].items() if i not in first})  # a bit on two pages: the first page's title
            bs = {i: dict(b, title=first.get(i, b['title'])) for i, b in bs.items()}
        bs |= {i: dict(bs[i], title=t) for r in rv.values() for i, t in r.get('bit_titles', {}).items() if i in bs}
        said = ' '.join(B.fold(c['text']) for c in ch.values())
        md = {t: m if t == 'Humor BioFut' else B.honest(m, said) for t, m in md.items()}
        md |= {t: tidy(r['lead']) for t, r in rv.items() if r.get('lead') and t in md}
        proper = {n: slug(p['title']) for p in pages for n in p['aliases'] if n[:1].isupper() and (len(n) >= 3 or n.isupper())}
        proper |= {p['title']: slug(p['title']) for p in pages}  # titles last: they win
        md = {t: m if t == 'Humor BioFut' else autolink(m, proper, slug(t)) for t, m in md.items()}
    leg = {r['file']: r['legenda'] for r in map(json.loads, open(B.CAPTIONS, encoding='utf-8'))} if sel and os.path.exists(B.CAPTIONS) else {}  # bits.py captions
    leg |= {x['file']: '' for r in rv.values() for x in r['photos']}  # a reviewed photo never keeps the blind caption
    leg |= {x['file']: x['legenda'] for r in rv.values() for x in r['photos'] if x['legenda']}  # written looking at the image; the page's own review caption wins below (one file, two pages)
    out, edges, used = [], set(), set()
    for p in pages:
        s = slug(p['title'])
        ls = sorted({name[t.strip().lower()] for t in LINK.findall(md[p['title']]) if t.strip().lower() in name} - {s})
        edges |= {(s, t) for t in ls}  # directed for now
        pb = sel.get(p['title'], [])
        refs = [i for i in dict.fromkeys(REF.findall(md[p['title']]) + [bs[b]['ref'] for b in pb]) if i in ch]
        if not refs and not sel:  # the writer cited nothing: list the conversations behind the page's top events
            top = sorted((ev[i] for i in p['events'] if i in ev), key=lambda e: -e['score'])[:8]
            refs = list(dict.fromkeys(c for e in top for c in (e.get('chunks') or [])[:1] if c in ch))
        used |= set(refs)
        c = cur.get(p['title'], {})
        text = md[p['title']] + ''.join(f"\n{bs[b]['title']} {bs[b]['quote']}" for b in pb)
        out.append({'slug': s, 'title': p['title'], 'type': p['type'], 'aliases': p['aliases'], 'years': p['years'], 'md': scrub(md[p['title']], nm),
                    'links': ls, 'refs': refs, 'public': is_public(text, c), 'bits': pb,
                    'photos': [{'file': x['file'], 'legenda': society(scrub(p['title'] in rv and x.get('legenda') or leg.get(x['file'], x.get('legenda', '')), nm))} for x in c.get('photos', [])][:3 if sel else None]})
    pe = {slug(p['title']): set(p['events']) for p in pages}
    keys = sorted(pe)
    # The map shows mutual links and pages that share many events; one-way links (~18 a page) turn it into a hairball.
    edges = {tuple(sorted(e)) for e in edges if e[::-1] in edges}
    edges |= {(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]  # ponytail: O(n²) over ~300 pages, fine
              if len(pe[a] & pe[b]) >= 2 and len(pe[a] & pe[b]) / len(pe[a] | pe[b]) >= 0.15}
    days = sorted(c['day'] for c in ch.values())
    imgs = chunk_images()
    os.makedirs(os.path.join(OUT, 'media'), exist_ok=True)
    files = {x['file'] for p in out for x in p['photos']} | {f for i in used for f in imgs.get(i, [])}
    with ThreadPoolExecutor(8) as pool:
        have = set(filter(None, pool.map(photo, sorted(files))))
    for p in out:
        p['photos'] = [x for x in p['photos'] if x['file'] in have]
    imgs = {i: [f if f in have else '' for f in fs] for i, fs in imgs.items()}  # '' keeps the order: that [foto] shows its caption only
    span = f'{len(days)} conversas de {days[0][:7]} a {days[-1][:7]}'
    sb = B.site_bits(sel, bs, nm) if sel else {}
    member = {'member': True, 'pages': out, 'edges': sorted(edges), 'humor': slug('Humor BioFut'), 'span': span, 'bits': sb,
              'chats': {i: {'date': ch[i]['date'], 'text': scrub(ch[i]['text'], nm), 'imgs': imgs.get(i, [])} for i in sorted(used)}}
    # Public: open pages only, no chats, no footnotes, only photos with nobody in them; closed pages are listed by title so links show a lock.
    cap = {}
    for f in ('images.jsonl', 'images_deepseek.jsonl'):
        if os.path.exists(os.path.join(D, f)):
            cap.update({r['file']: r for r in map(json.loads, open(os.path.join(D, f), encoding='utf-8'))})
    pub = []
    for p in out:
        if p['public']:
            ph = [x for x in p['photos'] if public_photo(cap.get(x['file']))]
            if not ph:  # the curated photos all show people: take one from the page's best moments, no legenda (caption.py's is English)
                fs = [f for b in p['bits'] for f in imgs.get(bs[b]['ref'], []) if f and public_photo(cap.get(f))]
                f = min(fs, key=lambda f: ['meme', 'poster', 'other', 'scoreboard', 'match_summary'].index(cap[f]['kind'])) if fs else None
                ph = [{'file': f, 'legenda': ''}] if f else []
            pub.append(dict(p, md=re.sub(r' ?\[ref:[^\]]*\]', '', p['md']), refs=[], photos=ph))
    keep = {p['slug'] for p in pub}
    pb = {i: {k: v for k, v in b.items() if k != 'ref'} for i, b in sb.items() if any(i in p['bits'] for p in pub)}
    public = {'member': False, 'pages': pub, 'edges': [e for e in sorted(edges) if set(e) <= keep], 'humor': slug('Humor BioFut'), 'span': span, 'bits': pb,
              'chats': {}, 'media': sorted({x['file'] for p in pub for x in p['photos']}), 'locked': [{'slug': p['slug'], 'title': p['title'], 'aliases': p['aliases']} for p in out if not p['public']]}
    for name, d in (('member.json', member), ('public.json', public)):
        json.dump(d, open(os.path.join(OUT, name), 'w', encoding='utf-8'), ensure_ascii=False)
    print(len(out), 'pages,', len(pub), 'public,', len(edges), 'edges,', len(files), 'photos,', len(public['media']), 'public photos on',
          sum(bool(p['photos']) for p in pub), 'pages ->', OUT)


def selftest():
    assert autolink('> «O Dan falou» — Dan, 2024\n\nO Dan e o MK, com [[Victor]], o Victor e o Dan na Meta AI.', {'Dan': 'dan', 'MK': 'mk', 'Victor': 'victor', 'Meta AI': 'meta-ai', 'Meta': 'x'}, 'mk') == \
        '> «O Dan falou» — Dan, 2024\n\nO [[Dan]] e o MK, com [[Victor]], o Victor e o Dan na [[Meta AI]].'
    nm = {'11112222333344@lid': 'Canova'}
    m = {'ts': 1700000000, 'sender': '11112222333344@lid', 'type': 'text', 'text': 'liga pro +55 51 99999-1234'}
    assert line(m, nm, {}).endswith('Canova: liga pro [tel]'), line(m, nm, {})
    assert scrub('@11112222333344 e @5551999991234 bora, pix 1234512345', nm) == '@Canova e @alguém bora, pix …'
    assert who({'sender_name': '+55 51 0000-0000'}, {}) == 'Alguém' and who({'sender': '1@lid'}, {}) == 'Alguém'
    i = {'type': 'image', 'media_path': 'x/IMG-1.jpg', 'text': '', 'ts': 1700000000, 'sender_name': 'Dan'}
    assert '[foto: gol | texto na imagem: 3x2]' in line(i, {}, {'IMG-1.jpg': {'caption': 'gol', 'text': '3x2'}})
    assert norm('O Pacto com a Cleo Kühn!') == 'pacto com cleo kuhn' and slug('BioFut King') == 'biofut-king'
    assert public_photo({'people': 0, 'kind': 'meme', 'caption': 'RIP BIOFUT', 'text': ''})
    assert not public_photo({'people': 1, 'kind': 'meme', 'caption': 'x'}) and not public_photo({'people': 0, 'kind': 'person_photo'})
    assert not public_photo({'people': 0, 'kind': 'other', 'caption': 'A bank transfer receipt', 'text': ''})
    assert not public_photo({'people': 0, 'kind': 'other', 'caption': 'A rolled smoking item next to loose tobacco'})
    assert not public_photo({'people': 0, 'kind': 'other', 'caption': 'x', 'text': 'conta 0001234567'}) and not public_photo(None)
    assert ATTACHED.sub('', '‎STK-20240818-WA0009.webp (arquivo anexado)') == ''
    assert REF.findall('gol [ref:c2024-07-01-06] e [ref:c2024-07-01-07, c2023-01-02-11]') == ['c2024-07-01-06', 'c2024-07-01-07', 'c2023-01-02-11']
    t = tidy("x '''y'''\n== Ver também ==\n" +''.join(f'- [[P{i}]]\n' for i in range(30)) + '\n[[Categoria:Gordos]]\n{{BioFut}}\n\n*fim*')
    assert t.count('[[P') == 10 and 'Categoria' not in t and '{{' not in t and t.rstrip().endswith('*fim*'), t
    print('selftest ok')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'selftest'
    lim = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    {'chunks': chunks, 'extract': lambda: extract(lim), 'canon': canon, 'profile': profile, 'write': lambda: write(lim), 'site': site,
     'curate': lambda: curate(lim), 'selftest': selftest}[cmd]()

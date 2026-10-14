"""BioWiki v2: the wiki is its funniest bits, ranked by Claude, capped, and refreshed as the chat goes on.

A bit is one extracted event (wiki.py extract) worth a laugh: title, best quote, who, day, chat ref.
  bits     events with funny >= 8 -> bits.json, with "cited": other days the catchphrase came back in the chat
  rank     Claude Opus, low effort, minimal context (one line per bit + cited) scores each bit 1-10; resumable
  select   caps: PAGE_BITS per page, GLOBAL_BITS in the whole wiki, PAGES_MAX pages; ties go to the most cited
  short    DeepSeek rewrites each kept page as a short lead (fake quote + one paragraph) -> leads.jsonl
  polish   Claude Opus rewrites the leads and the bit titles (no puns, no invented quotes) -> polish.jsonl; site() prefers it
  captions Claude Opus rewrites the photo legendas from what the image shows -> captions.jsonl; site() prefers it, "" = no legenda
  update   new chat -> chunks -> extract -> bits -> rank (anchored on ranked bits) -> select -> review proposal:
           what enters and what leaves, sent to the site's review queue (released after 6 h if nobody acts)
Usage: python bits.py bits|rank|select|short|polish|captions|update [--send]|selftest   (--send: queue the proposal on the site via site/submit.py)
Claude calls run through the claude CLI (Gab's Claude Code plan); cost is logged to derived/wiki/usage.jsonl.
Quotes on the site are checked against the chat at build time (verify, honest): the extractor paraphrases about a third of them.
"""
import collections, difflib, json, os, random, re, shutil, subprocess, sys, unicodedata
from concurrent.futures import ThreadPoolExecutor
import wiki
from wiki import W, D, all_events, num, deepseek, slug, scrub, names

BITS = os.path.join(W, 'bits.json')
SELECT = os.path.join(W, 'select.json')
LEADS = os.path.join(W, 'leads.jsonl')
POLISH = os.path.join(W, 'polish.jsonl')
CAPTIONS = os.path.join(W, 'captions.jsonl')
SEEN = os.path.join(W, 'seen_chunks.json')
PAGE_BITS, GLOBAL_BITS, PAGES_MAX, BIT_PAGES = 6, 360, 90, 2  # a bit shows on at most BIT_PAGES pages
CLAUDE = os.environ.get('CLAUDE_CLI') or shutil.which('claude') or 'claude'  # on Windows the CLI is claude.cmd


def fold(s):
    s = unicodedata.normalize('NFKD', (s or '').lower()).encode('ascii', 'ignore').decode()
    return ' '.join(re.sub(r'[^a-z0-9]+', ' ', s).split())


def catchphrases(e, people):
    """What the chat would repeat if the joke stuck: its non-person characters and its short quotes."""
    ks = [c for c in e.get('characters') or [] if fold(c) not in people]
    ks += [q.get('text') for q in e.get('quotes') or [] if 8 <= len(q.get('text') or '') <= 60]
    return [k for k in dict.fromkeys(fold(k) for k in ks) if len(k) >= 6]


SAID = re.compile(r'(?m)^\d\d:\d\d ([^:\n]+): (.*)$')


def real_quote(quote, chats):
    """Where the quote was really said: (text, who, chat id), or None. chats: [(id, text)], the likeliest first.
    The extractor paraphrases about a third of its quotes and sometimes names the wrong person; the chat has the real ones."""
    q = fold(quote)
    if len(q) < 4:
        return None
    sm, best = difflib.SequenceMatcher(None, '', q), (0, None)
    for i, text in chats:
        rows = SAID.findall(text)
        rows += [(w, a + ' ' + b) for (w, a), (v, b) in zip(rows, rows[1:]) if w == v]  # one quote glued from two messages in a row
        for w, t in rows:
            f = fold(t)
            if q in f:
                return quote, w, i
            sm.set_seq1(f)
            if sm.real_quick_ratio() > best[0] and sm.quick_ratio() > best[0] and sm.ratio() > best[0]:
                best = (sm.ratio(), (t, w, i))
    return best[1] if best[0] >= .8 else None  # ponytail: .8 lets typos and emoji through, not paraphrases


def verify(bs, ch):
    """Bits as the site shows them: the quote as really written, its speaker and conversation; a quote the day's chats
    don't have is dropped (the bit keeps its title). ch: chunk id -> chunk."""
    days = collections.defaultdict(list)
    for i in ch:
        days[i[1:11]].append(i)
    out = {}
    for k, b in bs.items():
        ids = [b['ref']] + [i for i in days.get(b['ref'][1:11], []) if i != b['ref']]
        r = real_quote(b['quote'], [(i, ch[i]['text']) for i in ids if i in ch]) if b['quote'] else None
        out[k] = dict(b, quote=r[0], who=r[1], ref=r[2]) if r else dict(b, quote='', who='')
    return out


LEAD_QUOTE = re.compile(r'\s*>\s*«(.+?)»[^\n]*\n*')


def honest(md, said):
    """Drops a lead's top quote that nobody said: the writers invented them and signed them with real members' names.
    said: fold() of the whole chat."""
    m = LEAD_QUOTE.match(md)
    return md[m.end():] if m and fold(m[1]) not in said else md


def chat_days():
    days = collections.defaultdict(list)
    for c in map(json.loads, open(wiki.CHUNKS, encoding='utf-8')):
        days[c['day']].append(fold(re.sub(r'(?m)^\d\d:\d\d [^:\n]*: ', '', c['text'])))  # drop "hh:mm Name:" so names don't count
    return {d: ' '.join(t) for d, t in days.items()}


def make_bits(events, people, days):
    """events -> bits dict; cited = other days any catchphrase shows up (the bit's own day doesn't count)."""
    out, cache = {}, {}
    for e in events:
        if num(e.get('funny')) < 8:
            continue
        qs = [q for q in e.get('quotes') or [] if q.get('text')]
        q = max(qs, key=lambda q: (8 <= len(q['text']) <= 140, -abs(len(q['text']) - 50)), default={})
        hit = set()
        for k in catchphrases(e, people):
            if k not in cache:
                pat = re.compile(r'\b' + re.escape(k) + r'\b')
                cache[k] = {d for d, t in days.items() if k in t and pat.search(t)}
                if len(cache[k]) > len(days) / 10:  # "biofut", "lista", "diretoria": the group's vocabulary, not a joke coming back
                    cache[k] = set()
            hit |= cache[k]
        out[e['id']] = {'id': e['id'], 'day': e['day'], 'title': e['title'], 'quote': q.get('text', ''), 'who': q.get('who', ''),
                        'summary': e.get('summary', ''), 'ref': (e.get('chunks') or [''])[0], 'funny': num(e.get('funny')),
                        'cited': len(hit - {e['day']})}
    return out


def bits():
    people = {fold(s) for p in json.load(open(os.path.join(D, 'people.json'), encoding='utf-8'))['people']
              for s in [p.get('db_player') or ''] + p['aliases'] + p['senders']} - {''}
    old = json.load(open(BITS, encoding='utf-8')) if os.path.exists(BITS) else {}
    new = make_bits(all_events(), people, chat_days())
    for k, b in new.items():  # keep Claude's scores across rebuilds
        b.update({x: old[k][x] for x in ('score', 'ranked') if x in old.get(k, {})})
    json.dump(new, open(BITS, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(len(new), 'bits;', sum(b['cited'] > 0 for b in new.values()), 'cited at least once ->', BITS)


RANK_PROMPT = """Você é o juiz de humor da BioWiki, a Desciclopédia de um grupo de WhatsApp de futebol 7 (society) amador de amigos em Porto Alegre (BioFut).
Cada linha é uma piada/momento do grupo: número | título | citação (quem disse) | quantos outros dias o bordão voltou no chat.
Dê nota 1-10: o quanto isso faz rir quem lê a wiki (de preferência alguém do grupo). 10 = clássico que todo mundo ri; 1 = rotina sem graça.
Use a escala toda. Linhas "r" marcadas "ref=N" já têm nota N: use como régua, não dê nota a elas.
Responda só JSON: {"1": nota, ...}. Nada de texto fora do JSON."""


def line(b):
    q = f'"{b["quote"][:140]}" ({b["who"]})' if b['quote'] else b['summary'][:140]
    return f"{b['id']} | {b['title'][:90]} | {q} | citado {b['cited']}x"


def claude(prompt, text, effort='low', step='rank'):
    r = subprocess.run([CLAUDE, '-p', '--model', 'opus', '--effort', effort, '--output-format', 'json', '--system-prompt', prompt,
                        '--tools', '', '--no-session-persistence', '--strict-mcp-config', '--setting-sources', ''],
                       input=text, capture_output=True, text=True, encoding='utf-8', timeout=600)
    out = json.loads(r.stdout)
    with open(wiki.USAGE, 'a') as f:
        f.write(json.dumps({'step': step, 'model': 'claude-opus', 'usd': out.get('total_cost_usd'), **(out.get('usage') or {})}) + '\n')
    m = re.search(r'\{.*\}', out.get('result') or '', re.S)
    return json.loads(m[0]) if m else {}


def rank(only=None, batch=80):
    """Scores unranked bits (or the ids in only). Each batch carries 8 ranked anchors so new bits land on the same scale."""
    bs = json.load(open(BITS, encoding='utf-8'))
    todo = [b for b in bs.values() if 'score' not in b and (only is None or b['id'] in only)]
    random.Random(7).shuffle(todo)  # mixes years, so one batch isn't all 2023
    ranked = sorted((b for b in bs.values() if 'score' in b), key=lambda b: b['score'])
    print(len(todo), 'to rank,', len(ranked), 'ranked')

    def one(chunk):
        anchors = ranked[::max(1, len(ranked) // 8)][:8]
        nums = {str(i + 1): b['id'] for i, b in enumerate(chunk)}  # short numbers instead of ids: fewer tokens, no typos
        rows = [f"r | {line(a).split(' | ', 1)[1]} | ref={a['score']}" for a in anchors]
        rows += [f"{n} | {line(b).split(' | ', 1)[1]}" for n, b in zip(nums, chunk)]
        text = '\n'.join(rows) + '\n\nResponda APENAS o objeto JSON {"1": nota, "2": nota, ...}, uma nota por linha numerada, sem comentário.'
        try:
            r = claude(RANK_PROMPT, text)
            return chunk, {nums[k]: v for k, v in r.items() if k in nums}
        except Exception as e:  # rerun rank to retry
            print('skip batch', e, flush=True)
            return chunk, {}

    parts = [todo[i:i + batch] for i in range(0, len(todo), batch)]
    with ThreadPoolExecutor(3) as pool:
        for i, (chunk, r) in enumerate(pool.map(one, parts)):
            for b in chunk:
                if b['id'] in r and isinstance(r[b['id']], (int, float)):
                    bs[b['id']].update(score=max(1, min(10, int(r[b['id']]))), ranked=wiki.dt.date.today().isoformat())
            json.dump(bs, open(BITS, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
            print(i + 1, '/', len(parts), sum(b['id'] in r for b in chunk), 'scored', flush=True)


def key(b):
    return (b.get('score', 0), b['cited'], b['funny'])


def pick(pages, bs, page_bits=PAGE_BITS, global_bits=GLOBAL_BITS, pages_max=PAGES_MAX, bit_pages=BIT_PAGES):
    """Fill pages with their best bits under the caps. Every bit that gets in pushes out a weaker one once the wiki is full."""
    cand = sorted(((b, p['title']) for p in pages for b in (bs.get(i) for i in p['events']) if b and 'score' in b),
                  key=lambda x: key(x[0]), reverse=True)
    sel, used = collections.defaultdict(list), collections.Counter()
    for b, t in cand:
        if len(sel[t]) < page_bits and used[b['id']] < bit_pages and (used[b['id']] or len(used) < global_bits):
            sel[t].append(b['id'])
            used[b['id']] += 1
    keep = sorted(sel, key=lambda t: -sum(bs[i]['score'] for i in sel[t]))[:pages_max]
    return {t: sel[t] for t in keep}


def select():
    pages = json.load(open(wiki.PAGES, encoding='utf-8'))
    bs = json.load(open(BITS, encoding='utf-8'))
    s = pick(pages, bs)
    json.dump(s, open(SELECT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    ids = {i for v in s.values() for i in v}
    print(len(s), 'pages,', len(ids), 'bits, scores', collections.Counter(bs[i]['score'] for i in ids).most_common(), '->', SELECT)


SHORT_PROMPT = """Você escreve a abertura de um verbete da "BioWiki", a Desciclopédia do grupo de futebol 7 (society) BioFut. O grupo quer verbetes CURTOS e ENGRAÇADOS.
{style}
Escreva em markdown, no máximo 110 palavras no total:
1. Uma citação falsa no topo, estilo Desciclopédia, em uma linha (> «...» — autor).
2. Um parágrafo curto que define o verbete com zoeira, apoiado nos melhores momentos fornecidos (sem listá-los: eles aparecem logo abaixo).
Fatos só do material. Links internos só para estes títulos: [[Título]]: {titles}
Nada sobre saúde, família, trabalho ou dinheiro pessoal de verdade; nunca números de telefone.
Responda só JSON: {{"markdown": "..."}}"""


def short(limit=None):
    sel = json.load(open(SELECT, encoding='utf-8'))
    bs = json.load(open(BITS, encoding='utf-8'))
    pages = {p['title']: p for p in json.load(open(wiki.PAGES, encoding='utf-8'))}
    old = {a['title']: a['markdown'] for a in map(json.loads, open(wiki.ARTICLES, encoding='utf-8'))}
    done = {json.loads(l)['title'] for l in open(LEADS, encoding='utf-8')} if os.path.exists(LEADS) else set()
    style = json.load(open(wiki.PROFILE, encoding='utf-8'))['style']
    system = SHORT_PROMPT.format(style=style, titles='; '.join(sel))
    todo = [t for t in sel if t not in done][:limit]
    print(len(done), 'done,', len(todo), 'to go')

    def one(t):
        p = pages[t]
        top = '\n'.join(f"- {bs[i]['day']} {bs[i]['title']}: {bs[i]['summary']}" for i in sel[t])
        user = f"Verbete: {t} (tipo {p['type']}; aliases: {', '.join(p['aliases'][:8]) or '-'})\nResumo: {p['pitch']}\n\nMELHORES MOMENTOS:\n{top}\n\nVERBETE ANTIGO (longo demais, só para contexto):\n{old.get(t, '')[:2500]}"
        try:
            return t, deepseek(system, user, max_tokens=1500)['markdown']
        except Exception as e:
            print('skip', t, e, flush=True)
            return t, None

    with open(LEADS, 'a', encoding='utf-8') as f, ThreadPoolExecutor(8) as pool:
        for t, md in pool.map(one, todo):
            if md:
                f.write(json.dumps({'title': t, 'markdown': md}, ensure_ascii=False) + '\n')
    print('->', LEADS)


POLISH_PROMPT = """Você é o editor da BioWiki, a Desciclopédia de um grupo de WhatsApp de futebol 7 (society) amador de amigos em Porto Alegre (BioFut, desde 2019).
Os amigos acharam o texto atual fraco: humor de redação escolar, trocadilho, "épico", "lendário", "saga" e citações inventadas na boca deles.
Para cada verbete recebido, reescreva a abertura ("lead") e os títulos dos melhores momentos ("titles").

Responda só um objeto JSON, exatamente neste formato e com estas chaves em inglês:
{"<título do verbete, igual ao recebido>": {"lead": "<markdown>", "titles": ["<título do momento 1>", "<título do momento 2>"]}}
"titles" tem um título por momento, na ordem e na quantidade recebidas.

O que faz esse grupo rir:
- O fato específico contado com cara séria: data, placar, número, nome, o detalhe absurdo que de fato aconteceu.
- Tom de enciclopédia sóbria tratando assunto banal como assunto de Estado, sem avisar que é exagero.
- As palavras do próprio grupo: as falas reais e os bordões do material.
- Subentendido. Quem é do grupo completa a piada; não explique.

Proibido:
- Trocadilho, jogo de palavras com nome, rima.
- épico, lendário, histórico, saga, odisseia, transcende, mago, gênio, fenômeno, verdadeiro, simplesmente, "nada menos que", "o único ... que".
- Ponto de exclamação, emoji, pergunta retórica, moral da história, explicar a piada.
- Citação inventada atribuída a qualquer pessoa, do grupo ou famosa ("Oscar Wilde, provavelmente" e afins).
- Fato que não está no material. Nada sobre saúde, família, trabalho, dinheiro pessoal, drogas, sexo ou corpo de pessoas reais.

lead: markdown, no máximo 70 palavras no total.
1. Primeira linha: a fala REAL mais engraçada do material, copiada letra por letra de uma "fala real" ou de um trecho do chat: > «texto» — Nome, ano
   Se nenhuma for boa, comece direto pelo parágrafo.
2. Um parágrafo de duas a quatro frases curtas que define o verbete como uma enciclopédia definiria, com um ou dois detalhes concretos.
   Não liste os momentos: eles aparecem logo abaixo, com os títulos.
   Links internos só como [[Título]] e só para estes títulos: {titles}

titles: no máximo 7 palavras cada, sem dois-pontos e sem travessão. Uma frase seca dizendo o que aconteceu, ou um pedaço curto de uma fala real do momento.
   Bons: "MK nunca sente a pressão" | "A lista só sai depois de 150 brownies" | "Cadê a lista, Edu" | "Robert Renan e Alan Patrick na suplência"
   Ruins: "A novela da chuva e a decisão de MK" | "Liberados do Anti-Doping: até o diabo treme" | "Victor transcende a realidade material" | "A batalha épica de Victor contra Matte"
"""
BANNED = re.compile(r'\b(épic\w*|lendári\w*|históric\w*|saga|odisseia|transcend\w*|mago|gênio|fenômeno|simplesmente|provavelmente)\b|!', re.I)


def lint(lead, titles):
    """What the writer still got wrong; polish keeps only clean answers (rerun it for the rest)."""
    bad = [str(t) for t in titles if not isinstance(t, str) or ':' in t or ' — ' in t or len(t.split()) > 8 or BANNED.search(t)]
    words = len(re.sub(r'\[\[(?:[^\]|]*\|)?([^\]]*)\]\]', r'\1', lead).split())
    return bad + [f'lead: {words} palavras'] * (words > 85) + [f'lead: {m[0]}' for m in [BANNED.search(lead)] if m]


def context(text, quote, n=5):
    """The chat lines around a quote (the conversation's start when there is none)."""
    rows, q = text.split('\n'), fold(quote)
    k = next((j for j, r in enumerate(rows) if q and q in fold(r)), None)
    return '\n'.join('     ' + r[:220] for r in (rows[max(0, k - n):k + n + 1] if k is not None else rows[:12]))


def polish(limit=None, batch=2):
    """Claude rewrites each kept page's lead and its bits' titles; resumable. site() uses it over leads.jsonl."""
    sel = json.load(open(SELECT, encoding='utf-8'))
    ch = {c['id']: c for c in map(json.loads, open(wiki.CHUNKS, encoding='utf-8'))}
    bs = verify(json.load(open(BITS, encoding='utf-8')), ch)
    pages = {p['title']: p for p in json.load(open(wiki.PAGES, encoding='utf-8'))}
    done = {json.loads(l)['title'] for l in open(POLISH, encoding='utf-8')} if os.path.exists(POLISH) else set()
    nm = names()
    system = POLISH_PROMPT.replace('{titles}', '; '.join(sel))
    todo = [t for t in sel if t not in done][:limit]
    print(len(done), 'done,', len(todo), 'to go')

    def material(t):
        p, rows = pages[t], []
        for n, i in enumerate(sel[t], 1):
            b = bs[i]
            q = f'«{b["quote"]}» — {b["who"]}, {b["day"][:4]}' if b['quote'] else '(nenhuma verificada)'
            rows.append(f"{n}. {b['day']} | título atual: {b['title']}\n   resumo: {b['summary']}\n   citação real: {q}\n   trecho do chat:\n"
                        + scrub(context(ch.get(b['ref'], {}).get('text', ''), b['quote']), nm))
        return (f"=== VERBETE: {t} (tipo {p['type']}; apelidos: {', '.join(p['aliases'][:6]) or '-'})\n"
                f"MELHORES MOMENTOS ({len(sel[t])}):\n" + '\n'.join(rows))

    def ask(text):
        r = claude(system, text, effort='high', step='polish')
        return {t: {'lead': v.get('lead') or v.get('abertura'), 'titles': titles(v.get('titles') or v.get('titulos'))} for t, v in r.items() if isinstance(v, dict)}

    def titles(ts):  # sometimes [{"data": ..., "titulo": ...}]
        return [x.get('titulo') or x.get('title') if isinstance(x, dict) else x for x in ts] if isinstance(ts, list) else ts

    def check(ts, r):
        return {t: lint(r[t]['lead'], r[t]['titles']) if t in r and isinstance(r[t]['lead'], str) and isinstance(r[t]['titles'], list)
                and len(r[t]['titles']) == len(sel[t]) else [f'formato: {{"lead": "...", "titles": [{len(sel[t])} títulos]}}'] for t in ts}

    def one(ts):
        text = '\n\n'.join(map(material, ts)) + ('\n\nResponda APENAS o objeto JSON, uma chave por verbete acima. Antes de responder, confira: cada lead com '
                                                 'no máximo 70 palavras; cada título com no máximo 7 palavras, sem ":" e sem "!"; nenhuma palavra proibida.')
        try:
            r = ask(text)
            bad = {t: b for t, b in check(ts, r).items() if b}
            if bad:  # one repair round: the answer back, with what is wrong in it
                r.update(ask(text + '\n\nSua resposta anterior:\n' + json.dumps(r, ensure_ascii=False) + '\n\nProblemas:\n' +
                             '\n'.join(f'- {t}: ' + '; '.join(b) for t, b in bad.items()) + '\nCorrija e responda o JSON completo de novo.'))
            return ts, r, check(ts, r)
        except Exception as e:  # rerun polish to retry
            print('skip', ts, e, flush=True)
            return ts, {}, {t: ['erro'] for t in ts}

    with open(POLISH, 'a', encoding='utf-8') as f, ThreadPoolExecutor(6) as pool:
        for ts, r, bad in pool.map(one, [todo[i:i + batch] for i in range(0, len(todo), batch)]):
            for t in ts:
                if bad[t]:
                    print('rejected', t, bad[t], flush=True)
                else:
                    f.write(json.dumps({'title': t, 'markdown': r[t]['lead'], 'titles': dict(zip(sel[t], r[t]['titles']))}, ensure_ascii=False) + '\n')
                    f.flush()
            print(ts[0], '...', flush=True)
    print('->', POLISH)


CAPTION_PROMPT = """Você escreve as legendas das fotos da BioWiki, a enciclopédia de piada de um grupo de WhatsApp de futebol 7 (society) amador de amigos em Porto Alegre (BioFut).
As legendas atuais são humor de redação escolar: "baile histórico", ponto de exclamação, piada com o corpo, o dinheiro ou a vida amorosa das pessoas.
Para cada foto você recebe o verbete, a descrição da imagem (em inglês, feita por uma IA que viu a foto), o texto que aparece nela e a legenda antiga.

Escreva a legenda nova em português: no máximo 12 palavras, seca, como legenda de foto de enciclopédia. Diga o que a foto mostra.
Se houver um detalhe absurdo de verdade na descrição ou no texto da imagem (um número, uma frase escrita), use-o com cara séria.
Proibido: trocadilho, épico, lendário, histórico, saga, ponto de exclamação, emoji, pergunta, fato que a descrição não mostra,
qualquer coisa sobre corpo, roupa íntima, sexo, saúde, dinheiro ou família de pessoas reais.
Se a foto não render uma legenda boa, responda "" (texto vazio): melhor sem legenda do que legenda fraca.

Responda só um objeto JSON: {"<arquivo>": "<legenda>"}, uma chave por foto recebida."""
CAPTION_BAD = re.compile(r'\b(tanguinha|sunga|cueca|calcinha|pelad\w*|gord\w*|barrig\w*|careca|mulher\w*|sex\w*|bund\w*|pinto)\b|R\$', re.I)


def caption_ok(t):
    return isinstance(t, str) and len(t.split()) <= 14 and not BANNED.search(t) and not CAPTION_BAD.search(t)


def captions(batch=15):
    """Claude rewrites the photo legendas of the pages' first three curated photos (what the site shows); resumable."""
    cap = {}
    for f in ('images.jsonl', 'images_deepseek.jsonl'):
        if os.path.exists(os.path.join(D, f)):
            cap.update({r['file']: r for r in map(json.loads, open(os.path.join(D, f), encoding='utf-8'))})
    done = {json.loads(l)['file'] for l in open(CAPTIONS, encoding='utf-8')} if os.path.exists(CAPTIONS) else set()
    sel = json.load(open(SELECT, encoding='utf-8'))
    todo = [(r['title'], x) for r in map(json.loads, open(wiki.CURATE, encoding='utf-8')) if r['title'] in sel for x in r.get('photos', [])[:3] if x['file'] not in done]
    todo = list({x['file']: (t, x) for t, x in todo}.values())
    print(len(done), 'done,', len(todo), 'to go')

    def one(part):
        text = '\n\n'.join(f"arquivo: {x['file']}\nverbete: {t}\ndescrição: {cap.get(x['file'], {}).get('caption', '-')}\n"
                           f"texto na imagem: {cap.get(x['file'], {}).get('text') or '-'}\nlegenda antiga: {x.get('legenda', '')}" for t, x in part)
        text += '\n\nResponda APENAS o objeto JSON. Antes de responder, confira: no máximo 12 palavras por legenda, nada sobre corpo ou roupa, nenhuma palavra proibida.'
        try:
            r = claude(CAPTION_PROMPT, text, effort='high', step='captions')
            bad = [x['file'] for _, x in part if not caption_ok(r.get(x['file']))]
            if bad:  # one repair round, as in polish
                r.update(claude(CAPTION_PROMPT, text + '\n\nSua resposta anterior:\n' + json.dumps(r, ensure_ascii=False) + '\n\nEstas passaram de 12 palavras '
                                'ou usaram palavra proibida (corpo, roupa, épico, histórico, "!"): ' + ', '.join(bad) + '. Reescreva-as e responda o JSON completo.',
                                effort='high', step='captions'))
            return part, r
        except Exception as e:  # rerun captions to retry
            print('skip', e, flush=True)
            return part, None

    with open(CAPTIONS, 'a', encoding='utf-8') as f, ThreadPoolExecutor(6) as pool:
        for part, r in pool.map(one, [todo[i:i + batch] for i in range(0, len(todo), batch)]):
            if r is None:
                continue
            for t, x in part:
                new = r.get(x['file'])
                f.write(json.dumps({'file': x['file'], 'legenda': new if caption_ok(new) else '', 'was': x.get('legenda', '')}, ensure_ascii=False) + '\n')
            f.flush()
            print(part[0][0], '...', flush=True)
    print('->', CAPTIONS)


def site_bits(sel, bs, nm):
    """What the site needs per bit; the member site links the chat, the public one doesn't."""
    ids = {i for v in sel.values() for i in v}
    return {i: {'title': wiki.society(bs[i]['title']), 'quote': scrub(bs[i]['quote'], nm), 'who': bs[i]['who'], 'day': bs[i]['day'],
                'score': bs[i]['score'], 'cited': bs[i]['cited'], 'ref': bs[i]['ref']} for i in sorted(ids)}


def update():
    """The organic loop. Run after scrape_biofut.py refreshed out/biofut_messages.jsonl."""
    seen = set(json.load(open(SEEN))) if os.path.exists(SEEN) else {json.loads(l)['id'] for l in open(wiki.CHUNKS, encoding='utf-8')}
    wiki.chunks()
    cs = [json.loads(l) for l in open(wiki.CHUNKS, encoding='utf-8')]
    new = [c for c in cs if c['id'] not in seen]
    print(len(new), 'new chunks')
    pages = json.load(open(wiki.PAGES, encoding='utf-8'))
    parts, cur = [], []
    for c in new:  # extract batches, as in wiki.batches()
        if cur and sum(len(x['text']) for x in cur) + len(c['text']) > wiki.BATCH_CHARS:
            parts.append(cur)
            cur = []
        cur.append(c)
    for b in parts + [cur] * bool(cur):
        text = '\n'.join(f"[{c['id']}] ({c['date'][:10]})\n{c['text']}" for c in b)
        evs = deepseek(wiki.PROMPT, text).get('events', [])
        with open(wiki.EVENTS, 'a', encoding='utf-8') as f:
            f.write(json.dumps({'batch': b[0]['id'], 'day': b[0]['day'], 'events': evs}, ensure_ascii=False) + '\n')
        for j, e in enumerate(evs):  # a new event joins the pages whose title or alias it mentions
            blob = fold(' '.join([e.get('title', ''), e.get('summary', '')] + (e.get('characters') or []) + (e.get('people') or [])))
            for p in pages:
                if any(len(fold(a)) >= 3 and re.search(r'\b' + re.escape(fold(a)) + r'\b', blob) for a in [p['title']] + p['aliases']):
                    p['events'].append(f"{b[0]['id']}#{j}")
        seen |= {c['id'] for c in b}
        json.dump(pages, open(wiki.PAGES, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        json.dump(sorted(seen), open(SEEN, 'w'))
    before = json.load(open(SELECT, encoding='utf-8'))
    bits()
    rank()
    pages = [p for p in json.load(open(wiki.PAGES, encoding='utf-8')) if p['title'] in before]  # new pages wait for a full rebuild
    bs = json.load(open(BITS, encoding='utf-8'))
    after = pick(pages, bs)
    return proposal(before, after, bs)


def proposal(before, after, bs):
    """Review item for the site: bits in, bits out, per page. Nothing changes on the site until approved or 6 h pass."""
    nm = names()
    ops = []
    for t in after:
        add, drop = [i for i in after[t] if i not in before.get(t, [])], [i for i in before.get(t, []) if i not in after[t]]
        if add or drop:
            ops.append({'page': slug(t), 'title': t, 'add': add, 'drop': drop, 'order': after[t],
                        'drop_titles': {i: bs[i]['title'] for i in drop if i in bs}})
    if not ops:
        print('nothing changes')
        return None
    added = {i for o in ops for i in o['add']}
    ch = {c['id']: c for c in map(json.loads, open(wiki.CHUNKS, encoding='utf-8'))}
    bs = verify(bs, ch)
    imgs = wiki.chunk_images()
    chats = {bs[i]['ref']: {'date': ch[bs[i]['ref']]['date'], 'text': scrub(ch[bs[i]['ref']]['text'], nm),
                            'imgs': [f if wiki.photo(f) else '' for f in imgs.get(bs[i]['ref'], [])]}
             for i in added if bs[i]['ref'] in ch}
    item = {'kind': 'wiki', 'title': f"Wiki: {len(added)} piadas entram, {sum(len(o['drop']) for o in ops)} saem",
            'payload': {'ops': ops, 'bits': site_bits({'x': list(added)}, bs, nm), 'chats': chats}}
    json.dump(after, open(SELECT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)  # the next run diffs against this
    print(item['title'])
    return item


def selftest():
    people = {'dan', 'rafo'}
    e = {'id': 'c1#0', 'day': '2023-05-04', 'title': 'CALABOCADAN', 'funny': 10, 'chunks': ['c2023-05-04-04'],
         'characters': ['CALABOCADAN', 'Dan'], 'quotes': [{'who': 'Rafo', 'text': 'CALA BOCA DANIEL VAI TE FUDE'}]}
    days = {'2023-05-04': 'cala boca daniel vai te fude', '2023-06-01': 'kkk calabocadan', '2023-07-01': 'dan', '2023-08-01': 'calabocadanzinho'}
    days.update({f'2024-01-{i:02}': 'bora jogar' for i in range(1, 20)})  # filler, so the catchphrase isn't "group vocabulary"
    assert catchphrases(e, people) == ['calabocadan', 'cala boca daniel vai te fude']
    b = make_bits([e, dict(e, id='c1#1', funny=5)], people, days)
    assert list(b) == ['c1#0'] and b['c1#0']['cited'] == 1 and b['c1#0']['quote'].startswith('CALA'), b
    bs = {f'e{i}': {'id': f'e{i}', 'score': s, 'cited': c, 'funny': 8} for i, (s, c) in enumerate([(9, 0), (9, 5), (3, 0), (7, 1), (2, 0)])}
    pages = [{'title': 'A', 'events': ['e0', 'e1', 'e2']}, {'title': 'B', 'events': ['e1', 'e3', 'e4']}, {'title': 'C', 'events': ['e4']}]
    s = pick(pages, bs, page_bits=2, global_bits=3, pages_max=2, bit_pages=1)
    assert s == {'A': ['e1', 'e0'], 'B': ['e3']}, s  # tie on 9 goes to the cited bit; e4 doesn't fit the global cap
    ch = {'c2023-05-04-04': {'text': '20:01 Dan: alguém tem bola\n20:02 Rafo: CALA BOCA DANIEL\n20:02 Rafo: vai te fude'},
          'c2023-05-04-05': {'text': '21:00 Victor: o goleiro foi o que mais tocou na bola, buscando no fundo da rede'}}
    one = lambda q, who='Dan', ref='c2023-05-04-05': verify({'x': {'quote': q, 'who': who, 'ref': ref}}, ch)['x']
    assert one('Cala boca Daniel, vai te fude!') == {'quote': 'Cala boca Daniel, vai te fude!', 'who': 'Rafo', 'ref': 'c2023-05-04-04'}  # glued, other chat, real speaker
    assert one('O goleiro foi o que mais tocou na bola buscando no fundo da rede 😂')['who'] == 'Victor'  # same words
    assert one('o goleiro só buscou a bola no fundo')['quote'] == ''  # a paraphrase: dropped
    said = fold('20:02 Rafo: CALA BOCA DANIEL')
    assert honest('> «Cala boca, Daniel» — Rafo, 2023\n\nO Dan.', said) == '> «Cala boca, Daniel» — Rafo, 2023\n\nO Dan.'
    assert honest('> «Sou adestrador de cadela.» — Andrei, 2025\n\nO Matte.', said) == 'O Matte.'
    assert lint('> «Cala boca, Daniel» — Rafo, 2023\n\nO [[Dan|Dan]] fala.', ['MK nunca sente a pressão']) == []
    assert caption_ok('Placar de 5 a 2 na parede da Planet Ball') and not caption_ok('Victor de tanguinha') and not caption_ok('O baile histórico')
    assert lint('Uma lista épica!', ['Liberados: até o diabo treme', 'A saga', 'Ok']) == ['Liberados: até o diabo treme', 'A saga', 'lead: épica']
    print('selftest ok')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'selftest'
    if cmd == 'update' and '--send' in sys.argv:  # the organic loop: new jokes -> review queue on the site (Gab has 6 h to veto)
        item = update()
        if item:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'site'))
            from submit import send
            media = sorted({os.path.join(wiki.OUT, 'media', f) for c in item['payload']['chats'].values() for f in c['imgs'] if f})
            send('wiki', item['title'], item['payload'], media)
    else:
        lim = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
        {'bits': bits, 'rank': rank, 'select': select, 'short': short, 'polish': lambda: polish(lim), 'captions': captions, 'update': update, 'selftest': selftest}[cmd]()

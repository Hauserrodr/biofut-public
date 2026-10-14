"""Fact-check of the shown BioWiki against the chat, with Gemini. The pages were written from chunks where several members
had the wrong name (Leo Saul as Victor and as Matte, Dan as Barp, Rafael M as Rafo...); the chunks now carry the login's names.

  index   gemini-embedding-2 over every chunk, in windows of ~2500 chars -> derived/wiki/rag.npy + rag.jsonl (RAG); reruns
          embed only new windows
  run     per shown page (site/data/wiki/member.json): lead, aliases, bits and photos (the images themselves) against the
          page's chats, RAG hits per sentence, alias counts and the tabela -> derived/wiki/review.jsonl; wiki.site() applies it
  verify  second look at each cut and correction (the lines after the cited proof, the exact phrase) and at captions that name
          someone the chat never ties to the photo; undoes and recaptions in review.jsonl
  report  review.jsonl -> derived/wiki/review.md: every change with its proof, for Gab
Usage: python review.py index|run|verify|report|selftest [--limit N] [--only Title]   (GEMINI_API_KEY; tokens to derived/wiki/usage.jsonl)
"""
import base64, collections, hashlib, io, json, math, os, re, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import wiki
import bits as B

RAG = os.path.join(wiki.W, 'rag')  # rag.npy (float16 unit rows) + rag.jsonl (key, chunk id, first and last line)
REVIEW = wiki.REVIEW
REPORT = os.path.join(wiki.W, 'review.md')
TABELA = os.environ.get('BIOFUT_DATA', 'D:/dev/biofut-deploy/site/biofut.json')  # games: players are [name, goals, assists, ...]
EMBED, MODEL = 'gemini-embedding-2', 'gemini-3.1-pro-preview'
WIN = 2500
SAFETY = ('HARM_CATEGORY_HARASSMENT', 'HARM_CATEGORY_HATE_SPEECH', 'HARM_CATEGORY_SEXUALLY_EXPLICIT', 'HARM_CATEGORY_DANGEROUS_CONTENT')  # locker-room chat
SAID = re.compile(r'^(\d\d:\d\d) ([^:\n]{1,40}): (.*)$')
# Confirmed by Gab or by the chat itself, 2026-10-09/10; the reviewer gets them as facts.
FACTS = """- Victor, Matte, Barp, Rafo, Rafael M (Rafa GK), Leo Saul, Leonardo, Dan, Lucas P., Felipe P., Felps e Gabriel são pessoas
  diferentes e reais (veja a tabela). Lucas Fischer e Fischer são a mesma pessoa.
- "Guihnazu" / "guihñazu" (com h) é o Guih: é a assinatura dele na lista ("Minha assinatura"). O Leo Saul contou uma vez que
  "já fui chamado de guiñazú do biofut"; não é apelido dele no grupo.
- Perdigão (Perdigas) não é o Douglas. "Douglas Berto" e "Doug" são o Douglas.
- "Grandão" é o Lucas P. (Lucas Poletti); o Felipe P. (Felipe Poletti) é outra pessoa."""

PROMPT = """Você é o checador de fatos da BioWiki, a Desciclopédia do grupo de WhatsApp de futebol 7 (society) amador BioFut (Porto Alegre).
Os verbetes foram escritos por IA a partir do chat, mas numa versão em que vários membros apareciam com o nome errado: o Leo Saul
aparecia como "Victor" e como "Matte", o Dan como "Barp", o Rafael M (Rafa GK) como "Rafo", o Lucas P. como "Grandao", o Felps como
"Gabriel", o Ramos como "Gordo Ramos". Por isso há frases, apelidos, piadas e fotos ligados à pessoa errada.
Os trechos de chat abaixo já têm os nomes CERTOS (linhas "HH:MM Nome: mensagem", sob o [id da conversa]). Confie neles.

FATOS CONFIRMADOS:
""" + FACTS + """

Revise o verbete linha por linha contra as provas:
1. "lead": o texto do verbete corrigido. Cada afirmação precisa de apoio nas provas. Afirmação ligada à pessoa errada: troque
   para a pessoa certa ou corte. Afirmação que a prova desmente (diz o contrário, não só outra coisa): corrija. Fato
   específico (quem, quando, placar, número, evento) sem prova nenhuma, nem nas conversas citadas nem nas duas buscas: corte.
   Exagero e tom de piada sobre algo que aconteceu ficam. Não troque uma afirmação certa por outra que você achou. Mude o mínimo: mantenha o tom, o humor, o formato markdown,
   os [[links]] e os [ref:...]. Se o texto está certo, devolva "".
2. "lead_changes": cada mudança, com a linha do chat que prova ("[id] HH:MM Nome: ..."); "tipo": "pessoa errada", "contradito"
   (o chat diz outra coisa) ou "sem prova".
3. "aliases_drop": apelidos da lista que o grupo NÃO usa para este assunto: nome que ninguém escreveu (contagem 0, salvo variação
   trivial do nome), apelido de outra pessoa, descrição inventada, frase que não é nome. Fique com os que o chat usa de verdade.
4. "bits": para cada piada do verbete, "acao": "manter"; "titulo" (o título conta errado o que aconteceu: dê um novo, curto, seco e
   fiel ao chat, sem ponto de exclamação); ou "remover" (a piada não é sobre este assunto, ou não tem conserto).
5. "photos": olhe cada FOTO. Fique com até 3, das atuais e das candidatas, que mostram ou ilustram este assunto de verdade (o
   momento, a pessoa, o meme, o placar). Evite prints de lista, comprovantes e documentos. "legenda": no máximo 12 palavras em
   português, seca, como legenda de enciclopédia: diga o que está NA IMAGEM e, se o contexto mostra, o momento ("Imagem da Meta
   AI pedida pelo Victor: ele contra o Matte dinossauro", "O time do 4 a 3, com o placar ao fundo"). Sem trocadilho, sem ponto de exclamação, sem fato que
   a imagem e o contexto não mostram, sem nomear quem o contexto não identifica (quem MANDOU a foto, o nome antes dos dois
   pontos, não é sempre quem aparece; você não reconhece rostos), nada sobre corpo, roupa íntima, sexo, saúde,
   dinheiro ou família. Lista vazia se nenhuma foto serve.
6. "flags": o que você não resolve aqui (o verbete mistura duas pessoas, o título do verbete está errado, etc.).
Em dúvida, não mexa. Responda só com JSON:
{"lead": "...", "lead_changes": [{"antes": "...", "depois": "...", "tipo": "...", "prova": "...", "motivo": "..."}],
 "aliases_drop": [{"alias": "...", "motivo": "..."}], "bits": [{"id": "...", "acao": "manter|titulo|remover", "titulo": "...", "motivo": "..."}],
 "photos": [{"file": "...", "legenda": "...", "motivo": "..."}], "flags": ["..."]}"""


def gemini(model, method, body, tries=6):
    req = urllib.request.Request(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:{method}', json.dumps(body).encode(),
                                 {'Content-Type': 'application/json', 'x-goog-api-key': os.environ['GEMINI_API_KEY']})
    for i in range(tries):
        try:
            r = json.load(urllib.request.urlopen(req, timeout=900))
            with open(wiki.USAGE, 'a') as f:
                f.write(json.dumps({'step': 'review', 'model': model, **(r.get('usageMetadata') or {})}) + '\n')
            return r
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if getattr(e, 'code', 503) not in (429, 500, 503, 504) or i == tries - 1:
                raise
            time.sleep(10 * 2 ** i)


def windows(cs):
    """chunk -> pieces of <= WIN chars cut at line breaks: (key, chunk id, first line, end line, text with the day)."""
    for c in cs:
        ls, a = c['text'].splitlines(), 0
        while a < len(ls):
            b, n = a + 1, len(ls[a])
            while b < len(ls) and n + len(ls[b]) < WIN:
                n += len(ls[b]) + 1
                b += 1
            t = c['day'] + '\n' + '\n'.join(ls[a:b])
            yield hashlib.sha1(t.encode()).hexdigest()[:16], c['id'], a, b, t[:12000]  # one huge line: the model reads 8k tokens
            a = b


def unit(v):
    v = np.asarray(v, dtype=np.float32)
    return v / (np.linalg.norm(v) or 1)


def embed(texts, task):
    r = gemini(EMBED, 'batchEmbedContents', {'requests': [{'model': 'models/' + EMBED, 'content': {'parts': [{'text': t}]},
                                                           'taskType': task, 'outputDimensionality': 768} for t in texts]})
    return [unit(e['values']) for e in r['embeddings']]


def index():
    ws = list(windows(map(json.loads, open(wiki.CHUNKS, encoding='utf-8'))))
    have = {}
    if os.path.exists(RAG + '.npy'):
        have = dict(zip((json.loads(l)['k'] for l in open(RAG + '.jsonl', encoding='utf-8')), np.load(RAG + '.npy')))
    todo = [w for w in ws if w[0] not in have]
    print(len(ws), 'windows,', len(todo), 'to embed', flush=True)
    try:
        with ThreadPoolExecutor(4) as pool:
            parts = [todo[i:i + 100] for i in range(0, len(todo), 100)]
            for n, (part, vs) in enumerate(zip(parts, pool.map(lambda p: embed([w[4] for w in p], 'RETRIEVAL_DOCUMENT'), parts))):
                have.update({w[0]: v for w, v in zip(part, vs)})
                if n % 10 == 0:
                    print(n, '/', len(parts), flush=True)
    finally:  # a failed run keeps what it embedded
        done = [w for w in ws if w[0] in have]
        np.save(RAG + '.npy', np.array([have[w[0]] for w in done], dtype=np.float16))
        with open(RAG + '.jsonl', 'w', encoding='utf-8') as f:
            f.writelines(json.dumps({'k': w[0], 'id': w[1], 'a': w[2], 'b': w[3]}) + '\n' for w in done)
        print(len(done), 'windows in the index')


class Chat:
    """The corrected chat in memory: chunks, RAG, every line with its speaker, alias counts, the tabela."""

    def __init__(self):
        self.ch = {c['id']: c for c in map(json.loads, open(wiki.CHUNKS, encoding='utf-8'))}
        self.v = np.load(RAG + '.npy').astype(np.float32)
        self.meta = [json.loads(l) for l in open(RAG + '.jsonl', encoding='utf-8')]
        self.rows = []  # (chunk id, first line, speaker, folded message with its continuation lines)
        for c in self.ch.values():
            for l in c['text'].splitlines():
                m = SAID.match(l)
                if m:
                    self.rows.append((c['id'], l, m[2], ' ' + B.fold(m[3]) + ' '))
                elif self.rows and self.rows[-1][0] == c['id']:
                    self.rows[-1] = self.rows[-1][:3] + (self.rows[-1][3] + B.fold(l) + ' ',)
        self.said = collections.Counter(r[2] for r in self.rows)
        self.post = collections.defaultdict(list)  # word stem -> rows that use it: the keyword half of the search
        for n, r in enumerate(self.rows):
            for w in stems(r[3]):
                self.post[w].append(n)
        self.first = {}
        for r in self.rows:
            self.first.setdefault(r[2], r[0][1:11])
        self.last = {r[2]: r[0][1:11] for r in self.rows}
        games = json.load(open(TABELA, encoding='utf-8'))['games']
        self.tab = collections.defaultdict(lambda: [0, 0, 0, '9999', ''])  # games, goals, assists, first, last
        for g in games:
            for t in g['teams']:
                for p in t['players']:
                    s = self.tab[p[0]]
                    s[0] += 1
                    s[1] += p[1] or 0
                    s[2] += p[2] or 0
                    s[3], s[4] = min(s[3], g.get('date') or '9999'), max(s[4], g.get('date') or '')
        ids = sorted(self.ch)
        self.next = dict(zip(ids, ids[1:]))
        self.imgs = wiki.chunk_images()
        self.where = {f: (i, n) for i, fs in self.imgs.items() for n, f in enumerate(fs)}
        self.kind = {r['file']: r.get('kind') for r in map(json.loads, open(os.path.join(wiki.D, 'images_deepseek.jsonl'), encoding='utf-8'))}

    def rag(self, qs, k=4):
        q = np.array(embed(qs, 'RETRIEVAL_QUERY'))
        return [[self.meta[i] for i in np.argsort(-row)[:k]] for row in q @ self.v.T]

    def grep(self, s, skip, k=2):
        """Chat lines that share rare stems with a clause, scored by IDF (names of the subject left out): one word as rare as
        "BagreBet" (idf >= 8, under ~50 lines) or two less rare ones. Finds the line the embeddings miss."""
        n = len(self.rows)
        idf = {w: math.log(n / len(self.post[w])) for w in stems(s) - skip if 0 < len(self.post[w]) < n // 200}
        score = collections.Counter()
        for w, x in idf.items():
            for i in self.post[w]:
                score[i] += x
        return [self.rows[i] for i, c in score.most_common(k) if c >= 8]

    def phrase(self, s, k=6):
        """Lines with three words of s in a row: the exact turn of phrase that stems and embeddings miss ("11 de setembro do biofut")."""
        ws, score = B.fold(s).split(), collections.Counter()
        for g in zip(ws, ws[1:], ws[2:]):
            keys = [w[:6] for w in g if len(w) >= 5 and self.post.get(w[:6])]
            pat = ' ' + ' '.join(g) + ' '
            for i in min((self.post[w] for w in keys), key=len) if keys else ():
                if pat in self.rows[i][3]:
                    score[i] += 1
        return [self.rows[i] for i, _ in score.most_common(k)]

    def span(self, cid, hm, n=20):
        """The cited HH:MM line with what follows, how that chat ended and how the next one began: a fight can be 160 lines
        before someone actually leaves the group."""
        if cid not in self.ch:
            return ''
        ls = self.ch[cid]['text'].splitlines()
        i = next((k for k, l in enumerate(ls) if l.startswith(hm)), len(ls) // 2)
        t = f'[{cid}]\n' + '\n'.join(ls[max(0, i - 8):i + n])
        if i + n < len(ls):
            t += '\n(...)\n' + '\n'.join(ls[max(i + n, len(ls) - 12):])
        if cid in self.next:
            t += f'\n[{self.next[cid]}]\n' + '\n'.join(self.ch[self.next[cid]]['text'].splitlines()[:12])
        return t[:8000]

    def alias(self, a):
        """How the chat uses a name: messages that contain it, their top speakers, two sample lines."""
        f = ' ' + B.fold(a) + ' '
        hit = [r for r in self.rows if f in r[3]] if len(f) > 3 else []
        top = ', '.join(f'{w} {n}' for w, n in collections.Counter(r[2] for r in hit).most_common(3))
        return f'- "{a}": {len(hit)} mensagens' + (f' (quem escreve: {top})' + ''.join(f'\n    [{r[0]}] {r[1][:160]}' for r in hit[-2:]) if hit else '')

    def around(self, cid, i, n=6):
        ls = self.ch[cid]['text'].splitlines()
        return '\n'.join(ls[max(0, i - n):i + n + 1])

    def foto(self, f):
        """The image's chat context: the lines around its [foto] line."""
        if f not in self.where:
            return ''
        cid, n = self.where[f]
        i = [k for k, l in enumerate(self.ch[cid]['text'].splitlines()) if wiki.FOTO.match(l)][n]
        return f'[{cid}]\n' + self.around(cid, i, 5)

    def quote_at(self, cid, quote, n=6):
        ls, q = self.ch[cid]['text'].splitlines(), B.fold(quote)[:40]
        i = next((k for k, l in enumerate(ls) if q and q in B.fold(l)), len(ls) // 2)
        return self.around(cid, i, n)


def stems(s):
    return {w[:6] for w in B.fold(s).split() if len(w) >= 5}  # ponytail: 6-letter prefix as the stem (5 makes bagrebet a bagre); a real stemmer if recall matters more


def jpeg(f, side=768):
    from PIL import Image
    p = os.path.join(wiki.OUT, 'media', f)
    im = Image.open(p if os.path.exists(p) else wiki.SRC_IMG[f]).convert('RGB')
    im.thumbnail((side, side))
    b = io.BytesIO()
    im.save(b, 'JPEG', quality=75)
    return base64.b64encode(b.getvalue()).decode()


def evidence(p, m, C):
    """Text parts and image parts for one page."""
    lead = re.sub(r' ?\[ref:[^\]]*\]', '', p['md'])
    sents = [s for s in re.split(r'(?<=[.!?»])\s+|\n+', re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', lead)) if len(s) > 25]
    out = [f"VERBETE: {p['title']} (tipo: {p['type']})\n\nTEXTO:\n{p['md']}\n\nAPELIDOS ({len(p['aliases'])}), com quantas mensagens do chat usam cada um:"]
    out += [C.alias(a) for a in p['aliases']]
    out.append('\nPIADAS (bits): título, citação real, quem disse, e a conversa em volta:')
    for b in p['bits']:
        x = m['bits'][b]
        out.append(f"- id {b}: «{x['title']}» citação: «{x['quote']}» — {x['who'] or '?'}, {x['day']}\n[{x['ref']}]\n{C.quote_at(x['ref'], x['quote'])}")
    seen, budget = set(), 26000
    out.append('\nCONVERSAS CITADAS PELO VERBETE:')
    for i in dict.fromkeys(p['refs'] + [m['bits'][b]['ref'] for b in p['bits']]):
        t = C.ch[i]['text'][:6000]
        if i in seen or budget < len(t):
            continue
        seen.add(i)
        budget -= len(t)
        out.append(f'[{i}]\n{t}')
    out.append('\nBUSCA NO CHAT INTEIRO (as conversas mais parecidas com cada frase do texto):')
    budget = 22000
    for s, hits in zip(sents[:10], C.rag(sents[:10]) if sents else []):
        out.append(f'> frase: {s}')
        for h in hits:
            t = '\n'.join(C.ch[h['id']]['text'].splitlines()[h['a']:h['b']])[:3000]
            if (h['id'], h['a']) in seen or budget < len(t):
                continue
            seen.add((h['id'], h['a']))
            budget -= len(t)
            out.append(f"[{h['id']}]\n{t}")
    out.append('\nBUSCA POR PALAVRAS (linhas do chat com as palavras raras de cada frase):')
    skip = set().union(*map(stems, [p['title']] + p['aliases']))
    budget = 14000
    for s in [c for s in sents[:12] for c in re.split(r'[,;:]\s+', s) if len(c) >= 15]:  # per clause: a sentence holds several claims
        hits = [r for r in C.grep(s, skip) if (r[0], r[1]) not in seen]
        seen.update((r[0], r[1]) for r in hits)
        t = '\n'.join(f'[{r[0]}]\n' + C.quote_at(r[0], r[1][6:], 3) for r in hits)
        if hits and len(t) < budget:
            budget -= len(t)
            out.append(f'> trecho: {s}\n{t}')
    names = {p['title']} | set(p['aliases'])
    me = [f"{n}: {C.tab[n][0]} jogos ({C.tab[n][3]} a {C.tab[n][4]}), {C.tab[n][1]} gols, {C.tab[n][2]} assistências" for n in names if n in C.tab]
    me += [f"{n}: {C.said[n]} mensagens no chat ({C.first[n]} a {C.last[n]})" for n in names if n in C.said]
    out.append('\nTABELA E CHAT, este assunto:\n' + ('\n'.join(me) or '(nenhum nome deste verbete joga ou escreve no chat)'))
    out.append('\nTODOS OS JOGADORES DA TABELA (jogos): ' + ', '.join(f'{n} {s[0]}' for n, s in sorted(C.tab.items(), key=lambda x: -x[1][0])))
    out.append('QUEM ESCREVE NO CHAT (mensagens): ' + ', '.join(f'{n} {k}' for n, k in C.said.most_common() if k >= 20))
    cur = [x['file'] for x in p['photos']]
    cand = [f for i in dict.fromkeys(p['refs'] + [m['bits'][b]['ref'] for b in p['bits']]) for f in C.imgs.get(i, [])
            if f not in cur and C.kind.get(f) not in ('list_screenshot', 'chat_screenshot', None)]
    parts = [{'text': '\n'.join(out)}]
    for f, how in [(f, 'atual, legenda: «' + x['legenda'] + '»') for x in p['photos'] for f in [x['file']]] + [(f, 'candidata') for f in list(dict.fromkeys(cand))[:6]]:
        try:
            parts += [{'text': f'\nFOTO {f} ({how}). Contexto no chat:\n{C.foto(f)}'}, {'inlineData': {'mimeType': 'image/jpeg', 'data': jpeg(f)}}]
        except (OSError, KeyError, IndexError):  # the export lacks the file, or the day's [foto] count is off
            pass
    return parts


def clean(p, m, r, files):
    """The model's answer -> what wiki.site() applies; anything that names a file, bit or alias the page lacks is dropped."""
    bits = {x.get('id'): x for x in r.get('bits') or [] if x.get('id') in p['bits']}
    return {'title': p['title'],
            'lead': (r.get('lead') or '').strip(),
            'aliases_drop': [x['alias'] for x in r.get('aliases_drop') or [] if x.get('alias') in p['aliases']],
            'bits_drop': [i for i, x in bits.items() if x.get('acao') == 'remover'],
            'bit_titles': {i: x['titulo'] for i, x in bits.items() if x.get('acao') == 'titulo' and x.get('titulo')},
            'photos': [{'file': x['file'], 'legenda': x.get('legenda', '') if B.caption_ok(x.get('legenda', '')) else ''}
                       for x in r.get('photos') or [] if x.get('file') in files][:3],
            'raw': r}


def ask(system, parts):
    r = gemini(MODEL, 'generateContent', {'systemInstruction': {'parts': [{'text': system}]}, 'contents': [{'role': 'user', 'parts': parts}],
                                          'generationConfig': {'responseMimeType': 'application/json', 'maxOutputTokens': 32768},
                                          'safetySettings': [{'category': c, 'threshold': 'BLOCK_NONE'} for c in SAFETY]})
    j = json.loads(''.join(x.get('text', '') for x in r['candidates'][0]['content']['parts'] if not x.get('thought')))
    return j[0] if isinstance(j, list) and j else j  # the model sometimes wraps the object in a list


def run(limit=None, only=None):
    m = json.load(open(os.path.join(wiki.OUT, 'member.json'), encoding='utf-8'))
    done = {json.loads(l)['title'] for l in open(REVIEW, encoding='utf-8')} if os.path.exists(REVIEW) else set()
    todo = [p for p in m['pages'] if p['title'] not in done and (not only or p['title'] == only)][:limit]
    C = Chat()
    print(len(done), 'reviewed,', len(todo), 'to go', flush=True)

    def one(p):
        try:
            parts = evidence(p, m, C)
            files = {x['file'] for x in p['photos']} | {t.split()[1] for t in (x.get('text', '') for x in parts) if t.startswith('\nFOTO ')}
            return clean(p, m, ask(PROMPT, parts), files)
        except Exception as e:
            print('skip', p['title'], repr(e)[:300], flush=True)
            return None

    with open(REVIEW, 'a', encoding='utf-8') as f, ThreadPoolExecutor(4) as pool:
        for n, r in enumerate(pool.map(one, todo)):
            if r:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
                f.flush()
                print(n, r['title'], 'lead' if r['lead'] else '-', len(r['aliases_drop']), 'aliases,', len(r['bits_drop']), 'bits out,',
                      len(r['bit_titles']), 'retitled,', len(r['photos']), 'photos,', len(r['raw'].get('flags') or []), 'flags', flush=True)


VERIFY = """Você confere uma correção que o checador fez num verbete da BioWiki, a Desciclopédia do grupo de WhatsApp de futebol
amador BioFut. As linhas do chat ("HH:MM Nome: mensagem", sob o [id da conversa]) têm os nomes certos.

FATOS CONFIRMADOS:
""" + FACTS + """

O checador às vezes erra: corta um fato que está no chat porque não achou a linha, ou lê o começo de uma conversa e perde o
que veio logo depois. Leia todas as linhas e decida:
- "original": o chat mostra o texto original INTEIRO, cada parte dele (quem, o quê, quando, a causa), escrito por alguém ou
  confirmado por algo que aconteceu; exagero de piada sobre algo que aconteceu conta. A correção é desfeita.
- "correcao": o chat mostra a correção, mostra só uma parte do original (o apelido existe, mas a causa ou a data é outra ou
  não aparece), ou não mostra o original.
Confira a ordem das datas: uma causa que acontece depois do efeito não é a causa.
Responda só com JSON: {"fica": "original|correcao", "prova": "[id] HH:MM Nome: ...", "motivo": "..."}"""

PHOTO = """Legenda de foto da BioWiki, a Desciclopédia do grupo de futebol amador BioFut, no verbete «%s». A legenda atual nomeia
alguém que o chat em volta não liga à imagem, ou o chat em volta não cita a pessoa do verbete. Quem MANDOU a foto é o nome antes
dos dois pontos na linha [foto], e quem manda não é sempre quem aparece. Diga que uma pessoa está na imagem só se o chat diz (a
selfie de quem mandou, o story com o @ dela, alguém diz quem é); você não reconhece rostos. Legenda: até 12 palavras, seca, sem
trocadilho, sem ponto de exclamação, nada sobre corpo, sexo, saúde, dinheiro ou família. "serve": o chat liga a foto a este
verbete (mostra a pessoa, ou é sobre algo que ela fez, disse ou pediu)?
Responda só com JSON: {"legenda": "...", "serve": true}"""


def proof(C, c, skip):
    """What the verifier reads for one change: the cited lines with what came right after, and the lines that say the original."""
    a = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', c.get('antes', ''))
    out = [C.span(i, hm) for i, hm in list(dict.fromkeys(re.findall(r'\[(c\d{4}-\d\d-\d\d-\d\d)\]\s*(\d\d:\d\d)', c.get('prova', ''))))[:3]]
    out += [f'[{r[0]}]\n' + C.quote_at(r[0], r[1][6:], 4) for r in dict.fromkeys(C.phrase(a) + C.grep(a, skip, 6))]
    out += [f"[{h['id']}]\n" + '\n'.join(C.ch[h['id']]['text'].splitlines()[h['a']:h['b']])[:3000] for h in C.rag([a], 2)[0]] if a.strip() else []
    return '\n\n'.join(out)[:24000]


def undo(lead, c, orig):
    """The lead with the original text back: the correction swapped for it, or a plain cut re-inserted next to its old neighbour."""
    a, d = c.get('antes', ''), (c.get('depois') or '').strip()
    if d and d in lead:
        return lead.replace(d, a, 1)
    k = orig.find(a) if a else -1
    if d or k < 0:
        return None
    pre, post = orig[max(0, k - 40):k], orig[k + len(a):k + len(a) + 40]
    if pre and pre in lead:
        j = lead.index(pre) + len(pre)
    elif post and post in lead:
        j = lead.index(post)
    else:
        return None
    return lead[:j] + a + lead[j:]


def names(C):
    """Folded name -> people, and person -> folded names: who a caption puts in a photo ("Leo Saul" is also "saul")."""
    word, person = collections.defaultdict(set), collections.defaultdict(set)
    for n in {n for n, k in C.said.items() if k >= 20} | set(C.tab):
        f = B.fold(n).split()
        for w in {' '.join(f)} | ({f[-1]} if len(f) > 1 and len(f[-1]) >= 4 else set()):
            word[w].add(n)
            person[n].add(w)
    return word, person


def near(C, f):
    """The [foto] line and its neighbours (sender, text, the request before it), folded; '' if the photo is not in the chat."""
    if f not in C.where:
        return ''
    cid, n = C.where[f]
    ls = C.ch[cid]['text'].splitlines()
    i = [k for k, l in enumerate(ls) if wiki.FOTO.match(l)][n]
    return ' ' + B.fold(' '.join(ls[max(0, i - 2):i + 2])) + ' '


def stranger(word, person, nr, legenda):
    """A name in the caption that the lines around the photo never mention."""
    cap = ' ' + B.fold(legenda) + ' '
    return next((w for w, ps in word.items() if f' {w} ' in cap and not any(f' {x} ' in nr for p in ps for x in person[p])), None)


def subject(p, person):
    """Folded names a person page goes by: title, its last word, aliases, the chat names that share the title's words."""
    t = B.fold(p['title']).split()
    ws = {' '.join(t), *(t[-1:] if len(t[-1]) >= 4 else []), *(B.fold(a) for a in p['aliases'])}
    return {' '.join(t)} | {w for w in ws | {x for n, xs in person.items() if set(t) & set(B.fold(n).split()) for x in xs} if len(w) >= 3}


def verify():
    """Second look at every cut and correction, with the lines around the cited proof and the exact phrase; undoes the ones the
    chat backs. Recaptions the photos whose caption names someone the chat never ties to the image. Rewrites review.jsonl."""
    m = {p['title']: p for p in json.load(open(os.path.join(wiki.OUT, 'member.json'), encoding='utf-8'))['pages']}
    rs = [json.loads(l) for l in open(REVIEW, encoding='utf-8')]
    C = Chat()
    word, person = names(C)

    def one(r):
        if r['title'] not in m:
            return r
        p, v = m[r['title']], r.get('verify') or {'changes': [], 'photos': []}
        lead, photos, seen = r['lead'], [dict(x) for x in r['photos']], {x['file'] for x in v['photos']}
        me = subject(p, person) if p['type'] == 'pessoa' else set()
        try:
            skip = set().union(*map(stems, [p['title']] + p['aliases']))
            for c in [] if 'verify' in r else r['raw'].get('lead_changes') or []:  # a rerun only looks at photos not seen yet
                a = ask(VERIFY, [{'text': f"VERBETE: {p['title']}\nTEXTO ORIGINAL: «{c.get('antes', '')}»\nCORREÇÃO ({c.get('tipo', '?')}): "
                                          f"«{c.get('depois', '')}»\nMOTIVO DO CHECADOR: {c.get('motivo', '')}\nPROVA DO CHECADOR: "
                                          f"{c.get('prova', '')}\n\nLINHAS DO CHAT:\n{proof(C, c, skip)}"}])
                x = {'antes': c.get('antes', ''), 'fica': a.get('fica'), 'prova': a.get('prova', ''), 'motivo': a.get('motivo', '')}
                if x['fica'] == 'original' and lead:
                    new = undo(lead, c, p['md'])
                    x['desfeita'], lead = new is not None, new or lead
                v['changes'].append(x)
            for ph in photos:
                nr = near(C, ph['file'])
                if ph['file'] in seen or not nr:
                    continue
                w = stranger(word, person, nr, ph['legenda'])
                why = f'nomeia: {w}' if w else f"o chat em volta não cita {p['title']}" if me and not any(f' {x} ' in nr for x in me) else ''
                if why:
                    a = ask(PHOTO % p['title'], [{'text': f"LEGENDA ATUAL: «{ph['legenda']}» ({why})\nCHAT:\n{C.foto(ph['file'])}"},
                                                 {'inlineData': {'mimeType': 'image/jpeg', 'data': jpeg(ph['file'])}}])
                    v['photos'].append({'file': ph['file'], 'antes': ph['legenda'], 'legenda': a.get('legenda', ''), 'serve': a.get('serve', True) is not False})
                    ph['legenda'] = a.get('legenda', '') if B.caption_ok(a.get('legenda', '')) else ''
            out = [x['file'] for x in v['photos'] if not x['serve']]
            print(r['title'], sum(x['fica'] == 'original' for x in v['changes']), 'of', len(v['changes']), 'undone,',
                  len(v['photos']), 'recaptioned,', len(out), 'photos out', flush=True)
            return {**r, 'lead': lead, 'photos': [x for x in photos if x['file'] not in out], 'verify': v}
        except Exception as e:
            print('skip', r['title'], repr(e)[:300], flush=True)
            return r

    with ThreadPoolExecutor(4) as pool:
        rs = list(pool.map(one, rs))
    with open(REVIEW + '.tmp', 'w', encoding='utf-8') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rs)
    os.replace(REVIEW + '.tmp', REVIEW)


def report():
    m = {p['title']: p for p in json.load(open(os.path.join(wiki.OUT, 'member.json'), encoding='utf-8'))['pages']}
    out = ['# Revisão da BioWiki contra o chat\n', 'Cada mudança com a linha do chat que prova. Gerado por wiki/review.py.\n']
    for r in map(json.loads, open(REVIEW, encoding='utf-8')):
        raw, old = r['raw'], m.get(r['title'], {})
        out.append(f"\n## {r['title']}\n")
        v = r.get('verify') or {}
        ver = {x['antes']: x for x in v.get('changes', [])}
        for c in raw.get('lead_changes') or []:
            x = ver.get(c.get('antes', ''), {})
            back = f" **Desfeita na conferência**{'' if x.get('desfeita') else ' (não achei onde repor)'}: {x.get('motivo', '')} Prova: {x.get('prova', '')}"
            out.append(f"- Texto ({c.get('tipo', '?')}): «{c.get('antes', '')}» → «{c.get('depois', '')}». {c.get('motivo', '')} Prova: {c.get('prova', '')}"
                       + (back if x.get('fica') == 'original' else ''))
        for a in raw.get('aliases_drop') or []:
            if a.get('alias') in r['aliases_drop']:
                out.append(f"- Apelido removido: {a['alias']}. {a.get('motivo', '')}")
        for b in raw.get('bits') or []:
            if b.get('id') in r['bits_drop'] or b.get('id') in r['bit_titles']:
                out.append(f"- Piada {b['id']}: {b.get('acao')} {('→ «' + b['titulo'] + '»') if b.get('titulo') else ''}. {b.get('motivo', '')}")
        was = {x['file']: x['legenda'] for x in old.get('photos') or []}
        cap = {y['file']: y['legenda'] for y in r['photos']}
        fix = {x['file']: x for x in v.get('photos', [])}
        for x in raw.get('photos') or []:
            if x.get('file') in cap:
                out.append(f"- Foto {x['file']}: «{cap[x['file']]}»" + (f" (antes: «{was[x['file']]}»)" if x['file'] in was else ' (nova)') + f". {x.get('motivo', '')}"
                           + (f" Legenda refeita na conferência (era «{fix[x['file']]['antes']}»)." if x['file'] in fix else ''))
        out += [f"- Foto removida: {f} («{l}»)" for f, l in was.items() if f not in cap]
        out += [f"- Foto tirada na conferência: {f} («{x['antes']}»)" for f, x in fix.items() if not x['serve'] and f not in was]
        out += [f'- ⚠ {f}' for f in raw.get('flags') or []]
        out += [f'- Revisão manual: {x}' for x in r.get('manual') or []]  # a hand fix written into review.jsonl
    open(REPORT, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    print('->', REPORT)


def selftest():
    cs = [{'id': 'c2024-01-01-01', 'day': '2024-01-01', 'text': '\n'.join(f'10:{i:02d} Dan: ' + 'x' * 900 for i in range(7))}]
    ws = list(windows(cs))
    assert [(w[2], w[3]) for w in ws] == [(0, 2), (2, 4), (4, 6), (6, 7)] and ws[0][4].startswith('2024-01-01\n10:00 Dan'), [(w[2], w[3]) for w in ws]
    assert stems('Confeiteiro melhor que o organizador!') == {'confei', 'melhor', 'organi'}
    p = {'title': 'Dan', 'aliases': ['Danzinho', 'Barp'], 'bits': ['b1', 'b2']}
    r = clean(p, {}, {'lead': ' novo ', 'aliases_drop': [{'alias': 'Barp'}, {'alias': 'Zé'}], 'bits': [{'id': 'b1', 'acao': 'remover'},
              {'id': 'b2', 'acao': 'titulo', 'titulo': 'Dan e o pênalti'}, {'id': 'b9', 'acao': 'remover'}],
              'photos': [{'file': 'a.jpg', 'legenda': 'Placar de 7 a 6 na Planet'}, {'file': 'b.jpg', 'legenda': 'x!'}, {'file': 'z.jpg'}]}, {'a.jpg', 'b.jpg'})
    assert r['lead'] == 'novo' and r['aliases_drop'] == ['Barp'] and r['bits_drop'] == ['b1'] and r['bit_titles'] == {'b2': 'Dan e o pênalti'}, r
    assert r['photos'] == [{'file': 'a.jpg', 'legenda': 'Placar de 7 a 6 na Planet'}, {'file': 'b.jpg', 'legenda': ''}], r['photos']
    assert undo('Saiu do grupo. Fim.', {'antes': 'antes de sair do grupo', 'depois': 'antes de ameaçar sair'}, '') is None
    assert undo('Ele, antes de ameaçar sair, xingou. Fim.', {'antes': 'antes de sair', 'depois': 'antes de ameaçar sair'}, '') == 'Ele, antes de sair, xingou. Fim.'
    assert undo('Um. Três.', {'antes': 'Dois. ', 'depois': ''}, 'Um. Dois. Três.') == 'Um. Dois. Três.'
    word, person = {'saul': {'Leo Saul'}, 'leo saul': {'Leo Saul'}, 'dan': {'Dan'}}, {'Leo Saul': {'leo saul', 'saul'}, 'Dan': {'dan'}}
    assert stranger(word, person, ' 10 00 matte foto ', 'Dan bebendo') == 'dan' and stranger(word, person, ' 10 00 dan foto ', 'Dan bebendo') is None
    assert subject({'title': 'Saul', 'aliases': ['Bolsaulnaro']}, person) == {'saul', 'bolsaulnaro', 'leo saul'} and 'mk' in subject({'title': 'MK', 'aliases': []}, person)
    print('selftest ok')


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'selftest'
    lim = int(sys.argv[sys.argv.index('--limit') + 1]) if '--limit' in sys.argv else None
    only = sys.argv[sys.argv.index('--only') + 1] if '--only' in sys.argv else None
    {'index': index, 'run': lambda: run(lim, only), 'verify': verify, 'report': report, 'selftest': selftest}[cmd]()

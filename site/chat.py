"""ESQUIZOBOT talks: a member mentions the bot, answers one of its messages or sends an unknown "!" command in the group.

The bot posts {text, sender} to /api/chat. Small keyword retrieval picks the wiki pages and bits that share words with the
question (no embeddings, no new dependency), DeepSeek answers in the wiki's voice with only those in the prompt.
Daily cap: BIOFUT_CHAT_DAILY_USD (default 0.20) over today's "chat" rows in costs.jsonl; past it the bot answers a joke.
Self-check: python chat.py
"""
import datetime as dt, json, math, random, re, urllib.request

import canon, costs

CAP = 0.20
PROMPT = """Você é o ESQUIZOBOT, o robô do BioFut (grupo de WhatsApp de futebol 7 society amador, Porto Alegre).
Fale no tom da BioWiki (Desciclopédia: seco, irônico, enciclopédico, fingindo seriedade), em português do Brasil.
Resposta curta: 1 a 4 frases, sem markdown pesado. Use só os trechos da wiki abaixo como fatos sobre pessoas e histórias do grupo;
se a wiki não fala do assunto, zoe com elegância e diga que a wiki não registra. Nunca invente fatos sobre membros.
Nunca ofenda de verdade, nunca fale de política, religião ou aparência física de alguém."""
BROKE = ["O orçamento diário de inteligência acabou. Volto amanhã mais esperto, ou igual.",
         "Hoje já pensei demais. A diretoria cortou minha verba até amanhã.",
         "Sem crédito pra pensar. Pergunta pro BK, ele também não sabe."]
STOP = set("a o e de da do das dos que em um uma pra para por com no na nos nas os as se eu tu ele voce vc me te mas ou ja nao sim "
           "eh e foi ser ta to tem quem qual como onde quando porque pq oq q isso esse essa esse aqui la bot esquizobot".split())


def words(s):
    return [w for w in canon.slug(s).split("-") if len(w) > 1 and w not in STOP]


def docs(wiki):
    """The wiki -> [(label, text)]: one per page, one per bit."""
    out = [(p["title"], f'{p["title"]} ({", ".join(p.get("aliases", [])[:6])}): {p.get("md", "")}') for p in wiki["pages"]]
    bits = wiki.get("bits") or {}
    out += [(b.get("title", ""), f'"{b.get("quote", "")}" ({b.get("who", "")}, {b.get("day", "")}) {b.get("title", "")}')
            for b in (bits.values() if isinstance(bits, dict) else bits)]
    return out


def retrieve(q, wiki, k=6, chars=900):
    """BM25-lite: score = sum of IDF of the question's words found in the doc, title words count double."""
    # ponytail: rebuilt per question (~350 docs, ms); cache the index if the wiki grows 100x
    ds = docs(wiki)
    sets = [(set(words(t)), set(words(l))) for l, t in ds]
    qs = set(words(q))
    df = {w: sum(w in s for s, _ in sets) for w in qs}
    score = [sum(math.log(1 + len(ds) / df[w]) * (2 if w in tl else 1) for w in qs if df[w] and w in s) for s, tl in sets]
    top = sorted((i for i, x in enumerate(score) if x > 0), key=lambda i: -score[i])[:k]
    return [ds[i][1][:chars] for i in top]


def spent_today(ledger=None):
    ledger = ledger or costs.LEDGER
    day = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if not ledger.exists():
        return 0.0
    with costs.LOCK, ledger.open(encoding="utf-8") as f:
        return sum(r["usd"] for r in map(json.loads, f) if r["pipeline"] == "chat" and r["ts"][:10] == day)


def answer(text, sender, wiki, key, cap=CAP, ledger=None):
    if spent_today(ledger) >= cap:
        return random.choice(BROKE)
    ctx = "\n\n".join(retrieve(text, wiki)) or "(a wiki não fala disso)"
    body = {"model": canon.MODEL, "temperature": 0.9, "max_tokens": 300, "thinking": {"type": "disabled"},
            "messages": [{"role": "system", "content": PROMPT},
                         {"role": "user", "content": f"TRECHOS DA WIKI:\n{ctx}\n\n{sender or 'Alguém'} pergunta: {text[:600]}"}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", json.dumps(body).encode(), {
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    reply = json.load(urllib.request.urlopen(req, timeout=60))
    costs.log("chat", canon.MODEL, reply.get("usage") or {}, ledger)
    return reply["choices"][0]["message"]["content"].strip()[:1500]


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    wiki = {"pages": [{"title": "Copa BioFut", "aliases": ["Copa"], "md": "Torneio anual com pênaltis."},
                      {"title": "BK", "aliases": ["juiz"], "md": "O árbitro que ninguém viu."}],
            "bits": {"x": {"title": "Goleiro voador", "quote": "defendi com a cara", "who": "Edu", "day": "2026-11-01"}}}
    assert retrieve("quem ganhou a copa?", wiki)[0].startswith("Copa BioFut"), retrieve("quem ganhou a copa?", wiki)
    assert "BK" in retrieve("o bk apitou?", wiki)[0] and retrieve("xyzzy", wiki) == []
    assert "defendi" in retrieve("o goleiro", wiki)[0]
    f = Path(tempfile.mkdtemp()) / "c.jsonl"
    costs.log("chat", "m", {"prompt_tokens": 2_000_000}, f)  # 0.28 > cap
    costs.log("ocr", "m", {"prompt_tokens": 9_000_000}, f)
    assert abs(spent_today(f) - 0.28) < 1e-9
    assert answer("oi", "Edu", wiki, "no-key", ledger=f) in BROKE  # over the cap: no API call
    print("chat ok")

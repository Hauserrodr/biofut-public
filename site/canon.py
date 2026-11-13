"""!canon: the admin answers a group message with "!canon" and it becomes BioWiki lore.

The bot sends the quoted message here (server.py /api/canon). Every fact goes to data/wiki/canon.jsonl (the memory, append
only). DeepSeek then rewrites the one page the fact belongs to, or starts a new one, in the wiki's own voice, and the result
goes to data/wiki/canon.json (slug -> page). The site lays canon.json over member.json when it serves the wiki, so a wiki.py
rebuild never loses it. Canon pages are members only: they quote the chat.
Self-check: python canon.py
"""
import json, re, time, urllib.request

import costs

MODEL = "deepseek-flash"
TYPES = ("pessoa", "personagem", "saga", "meme", "lugar", "tema")
PROMPT = """Você escreve a BioWiki, a Desciclopédia do BioFut (grupo de WhatsApp de futebol 7 society amador, Porto Alegre).
O admin marcou uma mensagem do grupo como CÂNONE: a partir de agora ela é verdade oficial da wiki, mesmo que seja zoeira.
Escreva no tom da wiki (Desciclopédia: seco, irônico, enciclopédico, fingindo seriedade), em português do Brasil.
Embaixo vêm os fatos canônicos já registrados sobre o mesmo assunto e todas as páginas da wiki (slug, título, apelidos, texto).
Decida: o fato pertence a uma página que já existe (use o slug dela) ou merece uma página nova (slug null)?
Página existente: devolva o texto INTEIRO reescrito, com tudo o que já estava lá e o fato novo encaixado onde faz sentido.
Página nova: 2 a 4 parágrafos curtos. Nunca invente nomes de pessoas fora dos fatos e das páginas. Links: [[Título de outra página]].
Responda só JSON: {"slug": "slug-existente" ou null, "title": "...", "type": "%s", "aliases": ["..."], "md": "..."}""" % "|".join(TYPES)


def slug(s):
    s = re.sub(r"[àáâãä]", "a", s.lower()); s = re.sub(r"[èéêë]", "e", s); s = re.sub(r"[ìíîï]", "i", s)
    s = re.sub(r"[òóôõö]", "o", s); s = re.sub(r"[ùúûü]", "u", s); s = s.replace("ç", "c")
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60] or "canone"


def remember(f, fact):
    f.parent.mkdir(parents=True, exist_ok=True)
    with f.open("a", encoding="utf-8") as h:
        h.write(json.dumps(fact, ensure_ascii=False) + "\n")


def prompt_text(fact, pages, facts):
    said = f'{fact["author"]} disse: "{fact["quote"]}"' + (f'\nNota do admin: {fact["note"]}' if fact.get("note") else "")
    old = "\n".join(f'- {x["author"]}: "{x["quote"]}"' + (f' ({x["note"]})' if x.get("note") else "") for x in facts[-30:])
    wiki = "\n\n".join(f'[{p["slug"]}] {p["title"]} ({", ".join(p.get("aliases", [])[:8])})\n{p["md"]}' for p in pages)
    return f"FATO NOVO:\n{said}\n\nFATOS CANÔNICOS ANTERIORES:\n{old or '(nenhum)'}\n\nPÁGINAS DA WIKI:\n{wiki}"


def ask(user, key):
    body = {"model": MODEL, "temperature": 0.7, "max_tokens": 4000, "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"}, "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", json.dumps(body).encode(), {
        "Content-Type": "application/json", "Authorization": "Bearer " + key})
    reply = json.load(urllib.request.urlopen(req, timeout=180))
    costs.log("canon", MODEL, reply.get("usage") or {})
    return json.loads(re.search(r"\{.*\}", reply["choices"][0]["message"]["content"], re.S).group(0))


def page_of(r, pages):
    """The model's answer -> a page for canon.json. An unknown slug is a new page; the title can't be empty."""
    title = str(r.get("title") or "").strip()[:80]
    md = str(r.get("md") or "").strip()[:6000]
    if not title or not md:
        raise ValueError("resposta sem título ou texto")
    known = {p["slug"]: p for p in pages}
    s = r.get("slug") if r.get("slug") in known else slug(title)
    old = known.get(s, {})
    return s, {**old, "slug": s, "title": old.get("title", title), "type": r.get("type") if r.get("type") in TYPES else old.get("type", "tema"),
               "aliases": list(dict.fromkeys(list(old.get("aliases", [])) + [str(a)[:40] for a in r.get("aliases") or []]))[:30],
               "md": md, "public": False, "canon": True, "updated": time.strftime("%Y-%m-%d")}


def overlay(d, canon):
    """Canon pages over the wiki (member.json): replaced in place, new ones appended."""
    if not canon:
        return d
    have = {p["slug"]: i for i, p in enumerate(d["pages"])}
    for s, p in canon.items():
        if s in have:
            d["pages"][have[s]] = {**d["pages"][have[s]], **p}
        else:
            d["pages"].append({"links": [], "refs": [], "bits": [], "photos": [], "years": [], **p})
    return d


def run(fact, pages_file, canon_file, mem_file, key):
    """One !canon: remember the fact, write its page. -> (slug, title, new?)"""
    facts = [json.loads(x) for x in mem_file.read_text(encoding="utf-8").splitlines()] if mem_file.exists() else []
    remember(mem_file, fact)
    canon = json.loads(canon_file.read_text(encoding="utf-8")) if canon_file.exists() else {}
    pages = overlay(json.loads(pages_file.read_text(encoding="utf-8")), canon)["pages"]
    s, p = page_of(ask(prompt_text(fact, pages, facts), key), pages)
    new = s not in {x["slug"] for x in pages}
    canon[s] = p
    tmp = canon_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(canon, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(canon_file)
    return s, p["title"], new


if __name__ == "__main__":
    pages = [{"slug": "copa-biofut", "title": "Copa BioFut", "type": "saga", "aliases": ["Copa"], "md": "Torneio."}]
    s, p = page_of({"slug": "copa-biofut", "title": "x", "type": "saga", "aliases": ["BK"], "md": "Torneio. O BK apita."}, pages)
    assert s == "copa-biofut" and p["title"] == "Copa BioFut" and p["aliases"] == ["Copa", "BK"] and not p["public"], p
    s, p = page_of({"slug": "inventado", "title": "O BK", "type": "nada", "md": "Ninguém sabe."}, pages)
    assert s == "o-bk" and p["type"] == "tema" and p["canon"], (s, p)
    d = overlay({"pages": [dict(pages[0])]}, {"copa-biofut": {"md": "novo"}, "o-bk": p})
    assert d["pages"][0]["md"] == "novo" and d["pages"][0]["title"] == "Copa BioFut" and d["pages"][1]["slug"] == "o-bk" and d["pages"][1]["refs"] == []
    try:
        page_of({"title": "", "md": "x"}, pages); raise AssertionError("empty title must fail")
    except ValueError:
        pass
    assert "Nota do admin: é o juiz" in prompt_text({"author": "Edu", "quote": "Eu conheci o BK!", "note": "é o juiz"}, pages, [])
    print("canon ok")

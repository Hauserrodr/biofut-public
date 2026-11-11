"""Match-sheet photo -> DeepSeek Flash -> súmula payload for the /admin review queue. Stdlib only.

The group's súmulas are handwritten notepads: a team colour, the players, and Gols / Assist columns
filled with Brazilian box tallies. One call reads the photo and says whether it is a súmula at all,
so the bot can forward every image of the group and only real sheets reach the queue.

  python sumula.py photo.jpg [YYYY-MM-DD] [--send]   read one photo on this PC (--send: to the site's queue)
  python sumula.py --selftest                         offline checks
Env: DEEPSEEK_API_KEY, BIOFUT_OCR_DAILY_LIMIT (default 20 calls a day, failed calls count),
BIOFUT_OCR_READS (default 2: a sheet is read twice and the fields the reads disagree on go to staff as warnings).
The server (server.py /api/sumula_image) calls read() for each image the bot forwards.
"""
import base64, datetime as dt, difflib, hashlib, json, os, re, sys, urllib.request
from pathlib import Path

import costs

DAILY_LIMIT = int(os.environ.get("BIOFUT_OCR_DAILY_LIMIT", "20"))
MODEL = "deepseek-flash"
TRIES = 2  # a call that fails, times out or replies garbage is tried once more (each try takes a slot of the limit)
READS = int(os.environ.get("BIOFUT_OCR_READS", "2"))


class ReadError(RuntimeError):
    """Every try failed: the server queues the photo as "não lida" for the staff to type in, never drops it."""

PROMPT = """This photo was posted in the WhatsApp group of BioFut, a Brazilian amateur 5-a-side football group.
Is it a súmula (a match sheet: team names or colours, player names, goals/assists)? Reply with JSON only.
If not: {"is_sumula": false}
If yes:
{"is_sumula": true, "date": "YYYY-MM-DD or null", "games": [{"team_a": "...", "team_b": "...", "score_a": null, "score_b": null,
  "players_a": [{"name": "...", "goals": 0, "assists": 0, "own_goals": 0, "captain": false}], "players_b": [...]}],
 "notes": "anything unreadable or ambiguous, in Portuguese"}
How the sheets are written:
- Usually handwritten on a notepad: a team colour as header (PRETO, VERDE, ROXO, ROSA...), then its players, then the other team,
  or both teams side by side. Columns "Gols"/"G" and "Assist"/"A" (sometimes "G A G A" for two teams side by side).
- Counts are Brazilian box tallies: | = 1, two strokes forming a corner (Γ or ㄱ) = 2, three sides of a box (∏ or ⊓) = 3,
  a closed square □ = 4, a square with a diagonal = 5, more boxes add up. Digits may be used too.
- "(C)" or "(c)" marks the captain; "GK", "Gol" or "(Gol)" marks the goalkeeper, keep it out of the name.
- "Sombra" or "(sombra)" is a stand-in player, keep the name as written.
- A written final score goes in score_a/score_b; if there is none, leave them null.
- Dates are Brazilian (DD/MM or DD/MM/YY).
Write names as on the sheet, but when one clearly matches a known player below, use the known spelling.
List every player, also those with 0. Never invent names or numbers; say what you could not read in notes.
Known players: """


def scores(payload):
    """Fill missing scores from goals + the other side's own goals; flag a written score that disagrees."""
    for g in payload.get("games", []):
        for s, o in (("a", "b"), ("b", "a")):
            tally = sum(int(p.get("goals") or 0) for p in g[f"players_{s}"]) + sum(int(p.get("own_goals") or 0) for p in g[f"players_{o}"])
            if g.get(f"score_{s}") is None:
                g[f"score_{s}"] = tally
            elif int(g[f"score_{s}"]) != tally:
                payload.setdefault("warnings", []).append(f"Placar escrito de {g[f'team_{s}']} ({g[f'score_{s}']}) ≠ soma dos gols ({tally})")
    return payload


def ask(image, roster, temperature=0):
    """One DeepSeek Flash call. image: JPEG/PNG bytes. Returns the parsed JSON dict."""
    mime = "image/png" if image[:4] == b"\x89PNG" else "image/jpeg"
    body = {"model": MODEL, "temperature": temperature, "max_tokens": 2500, "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT + ", ".join(roster)},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}}]}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", json.dumps(body).encode(), {
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"]})
    reply = json.load(urllib.request.urlopen(req, timeout=120))
    costs.log("ocr", MODEL, reply.get("usage") or {})  # tokens and USD of every paid call: Transparência and Apoie show the totals
    text = reply["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def take_slot(budget_file, sha, today=None):
    """Hard daily limit, checked and reserved before the paid call, so failures count too.
    Returns None when the slot is taken, else why not (duplicate photo / limit reached). sha None: a retry, no dedupe."""
    today = today or dt.date.today().isoformat()
    b = json.loads(budget_file.read_text()) if budget_file.exists() else {}
    if sha and sha in b.get("seen", []):
        return "foto repetida"
    if b.get("day") != today:
        b = {"day": today, "used": 0, "seen": b.get("seen", [])[-500:]}
    if b["used"] >= DAILY_LIMIT:
        return f"limite diário de OCR atingido ({DAILY_LIMIT})"
    b["used"] += 1
    b["seen"] += [sha] if sha else []
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    budget_file.write_text(json.dumps(b))
    return None


def shape(d):
    """The reply as read() needs it, numbers as ints, or ValueError: a garbled reply is retried like a failed call."""
    if not isinstance(d, dict):
        raise ValueError("resposta não é um objeto JSON")
    if not d.get("is_sumula"):
        return d
    num = lambda v: 0 if v in (None, "") else int(v)
    for g in d.get("games") or []:
        for s in "ab":
            if g.get(f"score_{s}") not in (None, ""):
                g[f"score_{s}"] = num(g[f"score_{s}"])
            for p in g.setdefault(f"players_{s}", []):
                if not str(p.get("name") or "").strip():
                    raise ValueError("jogador sem nome")
                p.update({k: num(p.get(k)) for k in ("goals", "assists", "own_goals")}, name=str(p["name"]).strip())
    return d


def try_read(call, image, roster, budget_file, *extra):
    """call -> shaped reply, tried TRIES times; a retry takes one more slot of the limit. Raises ReadError."""
    err = None
    for i in range(TRIES):
        if i and take_slot(budget_file, None):
            break  # limit reached: what failed so far is the answer
        try:
            return shape(call(image, roster, *extra))
        except Exception as e:  # timeout, HTTP error, no JSON, bad numbers
            err = e
    raise ReadError(f"leitura falhou ({err})")


def finish(d, roster, listed):
    """Names -> the sheet's spelling (the written one kept for /admin)."""
    for g in d["games"]:
        for s in "ab":
            for p in g[f"players_{s}"]:
                written, p["name"] = p["name"], canon(p["name"], roster, listed)
                if written != p["name"]:
                    p["written"] = written  # shown in /admin next to the guess
    return d


def disagree(a, b):
    """Two reads of one photo -> what differs (a wrong digit, a missed tally), for staff to look at on the photo."""
    if len(a["games"]) != len(b["games"]):
        return [f"2ª leitura achou {len(b['games'])} jogo(s), a 1ª {len(a['games'])}"]
    out = []
    for g, h in zip(a["games"], b["games"]):
        for s in "ab":
            if g.get(f"score_{s}") != h.get(f"score_{s}"):
                out.append(f"placar de {g.get(f'team_{s}')}: {g.get(f'score_{s}')} ou {h.get(f'score_{s}')}?")
            pa, pb = ({p["name"]: p for p in x[f"players_{s}"]} for x in (g, h))
            for n in sorted(pa.keys() & pb.keys()):
                for k, lbl in (("goals", "gols"), ("assists", "assist."), ("own_goals", "gols contra")):
                    if pa[n].get(k, 0) != pb[n].get(k, 0):
                        out.append(f"{n} {lbl}: {pa[n].get(k, 0)} ou {pb[n].get(k, 0)}?")
                if bool(pa[n].get("captain")) != bool(pb[n].get("captain")):
                    out.append(f"{n}: capitão?")
            if only := sorted(pa.keys() ^ pb.keys()):
                out.append(f"só uma leitura viu: {', '.join(only)}")
    return ["Leituras diferentes: " + "; ".join(out)] if out else []


def checks(d, roster=(), date_hint=None):
    """Sanity checks on a read -> d["warnings"] for /admin. Nothing is blocked: staff decide with the photo."""
    w = d.setdefault("warnings", [])
    known = set(roster) | {"Sombra"}
    for i, g in enumerate(d.get("games", []), 1):
        tag = f"Jogo {i}: " if len(d["games"]) > 1 else ""
        side = {s: g.get(f"players_{s}") or [] for s in "ab"}
        if not all(str(g.get(f"team_{s}") or "").strip() for s in "ab"):
            w.append(tag + "time sem nome ou cor na súmula")
        elif str(g["team_a"]).casefold() == str(g["team_b"]).casefold():
            w.append(tag + f"os dois times se chamam {g['team_a']}")
        for s, ps in side.items():
            t = g.get(f"team_{s}") or s.upper()
            if not 5 <= len(ps) <= 12:
                w.append(tag + f"{t} com {len(ps)} jogadores (normal: 5 a 12)")
            if (c := sum(bool(p.get("captain")) for p in ps)) != 1:
                w.append(tag + f"{t} com {c} capitães")
            gl, ast = sum(p.get("goals") or 0 for p in ps), sum(p.get("assists") or 0 for p in ps)
            if ast > gl:
                w.append(tag + f"{t}: {ast} assistências para {gl} gols")
        seen = {}  # roster name -> the written names that became it, both teams (BRUNO and BRUNO M. -> Bruno M)
        for ps in side.values():
            for p in ps:
                if p["name"] != "Sombra":
                    seen.setdefault(p["name"], []).append(p.get("written") or p["name"])
        both = sorted({p["name"] for p in side["a"]} & {p["name"] for p in side["b"]} - {"Sombra"})
        for n, ws in seen.items():
            if len(ws) > 1 and n not in both:
                w.append(tag + f"{' e '.join(ws)} viraram o mesmo jogador: {n}")
        if both:
            w.append(tag + f"nos dois times: {', '.join(both)}")
        if roster:
            new = [p["name"] for ps in side.values() for p in ps if p["name"] not in known]
            near = lambda n: difflib.get_close_matches(n, roster, 1, 0.6)
            if new:
                w.append(tag + "fora do elenco: " + ", ".join(n + (f" (seria {near(n)[0]}?)" if near(n) else "") for n in new))
    try:
        if date_hint and not -3 <= (dt.date.fromisoformat(d["date"]) - dt.date.fromisoformat(date_hint)).days <= 1:
            w.append(f"data {d['date']} longe do dia da foto ({date_hint})")
    except (KeyError, TypeError, ValueError):
        w.append(f"data inválida: {d.get('date')}")
    return d


def read(image, roster, date_hint, budget_file, call=None, listed=()):
    """Photo -> súmula payload, or None when it isn't one. Raises ValueError when the budget says no, ReadError when
    every try failed. listed: that day's confirmed list; the model sees those names first and canon() prefers them.
    date_hint: the match day the photo belongs to (server.match_day: the day before for a photo after midnight).
    A sheet is read READS times (if the limit allows) and the fields the reads disagree on become warnings."""
    why = take_slot(budget_file, hashlib.sha256(image).hexdigest())
    if why:
        raise ValueError(why)
    roster = list(listed) + [r for r in roster if r not in listed]
    call = call or ask
    d = try_read(call, image, roster, budget_file)
    if not d.get("is_sumula") or not d.get("games"):
        return None
    warn = []
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", str(d.get("date"))):
        d["date"] = date_hint  # the match day; the game is usually that night
        warn.append(f"data não lida: usei {date_hint}")
    d.pop("is_sumula", None)
    finish(d, roster, listed)
    if READS > 1 and not take_slot(budget_file, None):
        try:
            d2 = try_read(call, image, roster, budget_file, 0.5)
            if d2.get("is_sumula") and d2.get("games"):
                warn += disagree(d, finish(d2, roster, listed))
        except ReadError as e:
            warn.append(f"2ª leitura falhou: {e}")
    d["warnings"] = warn
    return checks(scores(d), roster, date_hint)


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\bgoleiro\b|\bgol\b", "gk", re.sub(r"[^a-z ]+", " ", s)).split()


def _prefix(w, rw):
    return all(any(x.startswith(t) or (len(x) >= 3 and t.startswith(x)) for x in rw) for t in w)


def _near(w, rw):
    """One written word, 4+ letters, one letter off a word of the name, same first letter (RAFA -> Rafo)."""
    return len(w) == 1 and len(w[0]) >= 4 and any(
        len(x) == len(w[0]) and x[0] == w[0][0] and sum(a != b for a, b in zip(x, w[0])) == 1 for x in rw)


def canon(name, roster, listed=()):
    """Handwritten name -> the sheet's spelling. Exact match first, then every written word a prefix of a word of
    the sheet name (or the reverse: DANIEL -> Dan), earliest in roster wins (roster_of: most frequent first, so
    SAUL -> Leo Saul, GAB S. -> Gabi Steinhaus). listed (that day's confirmed list) goes ahead of the roster, and a
    listed name one letter off also beats a prefix of someone not listed (RAFA -> Rafo on the list, not Rafael M).
    ponytail: prefix heuristic; an alias file learned from Gab's edits if it keeps guessing wrong."""
    w = _norm(name)
    if "sombra" in w:  # the sheet books every stand-in as "Sombra"
        return "Sombra"
    if not w:
        return name
    for r in [*listed, *roster]:
        if _norm(r) == w:
            return r
    for r in listed:
        if _prefix(w, _norm(r)):
            return r
    for r in listed:
        if _near(w, _norm(r)):
            return r
    for r in roster:
        if _prefix(w, _norm(r)):
            return r
    return name


def roster_of(games, since="2025-01-01"):
    """Names seen in the sheet since `since`, most frequent first: the model maps handwriting onto these."""
    n = {}
    for g in games:
        if (g.get("date") or "") >= since:
            for t in g["teams"]:
                for p in t["players"]:
                    n[p[0]] = n.get(p[0], 0) + 1
    return sorted(n, key=lambda k: -n[k])


def selftest():
    import tempfile
    p = {"games": [{"team_a": "Preto", "team_b": "Verde", "score_a": None, "score_b": 3,
                    "players_a": [{"name": "Saul", "goals": 1}, {"name": "Matte", "goals": 1, "own_goals": 1}],
                    "players_b": [{"name": "Dan", "goals": 4}]}]}
    scores(p)
    g = p["games"][0]
    assert (g["score_a"], g["score_b"]) == (2, 3) and "≠ soma" in p["warnings"][0], p  # b wrote 3, tally is 4 + 1 own goal = 5
    f = Path(tempfile.mkdtemp()) / "ocr.json"
    assert take_slot(f, "x", "2026-10-08") is None and take_slot(f, "x", "2026-10-08") == "foto repetida"
    for i in range(DAILY_LIMIT - 1):
        assert take_slot(f, f"y{i}", "2026-10-08") is None
    assert "limite" in take_slot(f, "z", "2026-10-08") and take_slot(f, "z", "2026-10-09") is None  # new day resets
    calls = []
    fake = lambda img, r, *t: calls.append(1) or {"is_sumula": False}
    assert read(b"meme", [], "2026-10-08", f, fake) is None and calls == [1]
    fake = lambda img, r, *t: {"is_sumula": True, "date": None, "games": [{"team_a": "A", "team_b": "B", "score_a": None, "score_b": None,
                                                                         "players_a": [{"name": "X", "goals": 2}], "players_b": []}]}
    out = read(b"sheet", [], "2026-10-08", f, fake)
    assert out["date"] == "2026-10-08" and out["games"][0]["score_a"] == 2 and "is_sumula" not in out
    try:
        read(b"sheet", [], "2026-10-08", f, fake)
        raise AssertionError("duplicate photo was read twice")
    except ValueError:
        pass
    roster = ["Dan", "Leo Saul", "Marcelo Prof.", "Gabi Steinhaus", "Gui Goleiro", "Douglas", "Bruno M", "Leonardo", "Pedro GK"]
    want = {"SAUL": "Leo Saul", "MARCELO": "Marcelo Prof.", "Gab S.": "Gabi Steinhaus", "Gui GK": "Gui Goleiro", "DANIEL": "Dan",
            "Doug": "Douglas", "Bruno M.": "Bruno M", "Pedro (Gol)": "Pedro GK", "Leo Corecco": "Leo Corecco", "Nego Dei": "Nego Dei",
            "Victor (sombra)": "Sombra"}
    assert {k: canon(k, roster) for k in want} == want, {k: canon(k, roster) for k in want}
    roster = ["Rafael M", "Tavares", "Rafo", "Tato", "Leo Saul"]  # most frequent first
    assert canon("RAFA", roster) == "Rafael M" and canon("RAFA", roster, ["Rafo"]) == "Rafo"  # the day's list wins
    assert canon("TA", roster) == "Tavares" and canon("TA", roster, ["Tato", "Leo Saul"]) == "Tato"  # tie on a prefix
    assert canon("Tavares", roster, ["Tato"]) == "Tavares" and canon("RAFA", roster, ["Tato"]) == "Rafael M"  # not listed: as before
    assert canon("SAUL", roster, ["Rafo"]) == "Leo Saul" and canon("Rafael", roster, ["Rafo"]) == "Rafael M"
    seen = []
    fake = lambda img, r, *t: seen.append(r) or {"is_sumula": True, "date": "2026-10-22", "games": [{"team_a": "A", "team_b": "B",
        "score_a": None, "score_b": None, "players_a": [{"name": "RAFA", "goals": 1}], "players_b": [{"name": "Tavares", "goals": 0}]}]}
    out = read(b"listed", roster, "2026-10-22", f, fake, ["Rafo", "Tato"])
    assert seen[0][:3] == ["Rafo", "Tato", "Rafael M"] and len(seen[0]) == len(roster), seen  # listed first, nobody twice
    assert [p["name"] for s in "ab" for p in out["games"][0][f"players_{s}"]] == ["Rafo", "Tavares"], out
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    here = Path(__file__).parent
    import server  # roster from the cached sheet (data/sheet.csv); importing doesn't start the server
    games = server.sheet_games(server.SHEET_CACHE.read_text(encoding="utf-8")) if server.SHEET_CACHE.exists() else server.DATA["games"]
    out = read(Path(args[0]).read_bytes(), roster_of(games), args[1] if len(args) > 1 else dt.date.today().isoformat(),
               here / "data" / "ocr_budget_local.json")
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if out and "--send" in sys.argv:
        import submit
        submit.send("sumula", f"Súmula {out['date']} (foto)", out)

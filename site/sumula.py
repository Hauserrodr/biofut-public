"""Match-sheet photo -> DeepSeek Flash -> súmula payload for the /admin review queue. Stdlib only.

The group's súmulas are handwritten notepads: a team colour, the players, and Gols / Assist columns
filled with Brazilian box tallies. One call reads the photo and says whether it is a súmula at all,
so the bot can forward every image of the group and only real sheets reach the queue.

  python sumula.py photo.jpg [YYYY-MM-DD] [--send]   read one photo on this PC (--send: to the site's queue)
  python sumula.py --selftest                         offline checks
Env: DEEPSEEK_API_KEY, BIOFUT_OCR_DAILY_LIMIT (default 20 calls a day, failed calls count).
The server (server.py /api/sumula_image) calls read() for each image the bot forwards.
"""
import base64, datetime as dt, hashlib, json, os, re, sys, urllib.request
from pathlib import Path

import costs

DAILY_LIMIT = int(os.environ.get("BIOFUT_OCR_DAILY_LIMIT", "20"))
MODEL = "deepseek-flash"

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
                payload["notes"] = (payload.get("notes") or "") + f" Placar escrito de {g[f'team_{s}']} ({g[f'score_{s}']}) ≠ soma dos gols ({tally})."
    return payload


def ask(image, roster):
    """One DeepSeek Flash call. image: JPEG/PNG bytes. Returns the parsed JSON dict."""
    mime = "image/png" if image[:4] == b"\x89PNG" else "image/jpeg"
    body = {"model": MODEL, "temperature": 0, "max_tokens": 2500, "thinking": {"type": "disabled"},
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": PROMPT + ", ".join(roster)},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(image).decode()}"}}]}]}
    req = urllib.request.Request("https://api.deepseek.com/chat/completions", json.dumps(body).encode(), {
        "Content-Type": "application/json", "Authorization": "Bearer " + os.environ["DEEPSEEK_API_KEY"]})
    reply = json.load(urllib.request.urlopen(req, timeout=180))
    costs.log("ocr", MODEL, reply.get("usage") or {})  # tokens and USD of every paid call: Transparência and Apoie show the totals
    text = reply["choices"][0]["message"]["content"]
    return json.loads(re.search(r"\{.*\}", text, re.S).group(0))


def take_slot(budget_file, sha, today=None):
    """Hard daily limit, checked and reserved before the paid call, so failures count too.
    Returns None when the slot is taken, else why not (duplicate photo / limit reached)."""
    today = today or dt.date.today().isoformat()
    b = json.loads(budget_file.read_text()) if budget_file.exists() else {}
    if sha in b.get("seen", []):
        return "foto repetida"
    if b.get("day") != today:
        b = {"day": today, "used": 0, "seen": b.get("seen", [])[-500:]}
    if b["used"] >= DAILY_LIMIT:
        return f"limite diário de OCR atingido ({DAILY_LIMIT})"
    b["used"] += 1
    b["seen"].append(sha)
    budget_file.parent.mkdir(parents=True, exist_ok=True)
    budget_file.write_text(json.dumps(b))
    return None


def read(image, roster, date_hint, budget_file, call=None):
    """Photo -> súmula payload, or None when it isn't one. Raises ValueError when the budget says no."""
    why = take_slot(budget_file, hashlib.sha256(image).hexdigest())
    if why:
        raise ValueError(why)
    d = (call or ask)(image, roster)
    if not d.get("is_sumula") or not d.get("games"):
        return None
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", str(d.get("date"))):
        d["date"] = date_hint  # day it was posted; the game is usually that night
    d.pop("is_sumula", None)
    for g in d["games"]:
        for s in "ab":
            for p in g[f"players_{s}"]:
                written, p["name"] = p["name"], canon(p["name"], roster)
                if written != p["name"]:
                    p["written"] = written  # shown in /admin next to the guess
    return scores(d)


def _norm(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"\bgoleiro\b|\bgol\b", "gk", re.sub(r"[^a-z ]+", " ", s)).split()


def canon(name, roster):
    """Handwritten name -> the sheet's spelling. Exact match first, then every written word a prefix of a word of
    the sheet name (or the reverse: DANIEL -> Dan), most frequent player wins (SAUL -> Leo Saul, GAB S. -> Gabi Steinhaus).
    ponytail: prefix heuristic; an alias file learned from Gab's edits if it keeps guessing wrong."""
    w = _norm(name)
    if "sombra" in w:  # the sheet books every stand-in as "Sombra"
        return "Sombra"
    if not w:
        return name
    for r in roster:
        if _norm(r) == w:
            return r
    for r in roster:
        rw = _norm(r)
        if all(any(x.startswith(t) or (len(x) >= 3 and t.startswith(x)) for x in rw) for t in w):
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
    assert (g["score_a"], g["score_b"]) == (2, 3) and "≠ soma" in p["notes"], p  # b wrote 3, tally is 4 + 1 own goal = 5
    f = Path(tempfile.mkdtemp()) / "ocr.json"
    assert take_slot(f, "x", "2026-10-08") is None and take_slot(f, "x", "2026-10-08") == "foto repetida"
    for i in range(DAILY_LIMIT - 1):
        assert take_slot(f, f"y{i}", "2026-10-08") is None
    assert "limite" in take_slot(f, "z", "2026-10-08") and take_slot(f, "z", "2026-10-09") is None  # new day resets
    calls = []
    fake = lambda img, r: calls.append(1) or {"is_sumula": False}
    assert read(b"meme", [], "2026-10-08", f, fake) is None and calls == [1]
    fake = lambda img, r: {"is_sumula": True, "date": None, "games": [{"team_a": "A", "team_b": "B", "score_a": None, "score_b": None,
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

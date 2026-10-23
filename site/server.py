"""BioFut site: history, standings, player pages, weekly sign-up + draft, BioBet, resenha, Pix. Stdlib only.

Run: python server.py  ->  http://localhost:8765
Data (read-only): BIOFUT_DATA env or ./biofut.json (made by build_data.py). Games come live from the
group's Google Sheet (DATABASE tab, published CSV), re-read every 10 min; last good copy in data/sheet.csv.
Live state (sign-ups, draft, bets, games played on the site): data/state.json. Photos: data/photos/.
BioWiki at /wiki: data/wiki/public.json for everyone; member.json (chat references, photos in data/wiki/media/) after login
by WhatsApp number (/entrar). Both are built by wiki/wiki.py, outside git. Reports of wrong info: data/wiki/feedback.jsonl.
Review queue (/admin): everything the pipelines make waits for Gab (the Conselho too, for súmulas, tabela and listas) to
approve, edit or reject, and is released anyway after 6 h: wiki bits in/out, match sheets read by OCR (sumula) and list stats (listas) arrive in
data/review/inbox/*.json (scp from the PC, site/submit.py); changes in the Google Sheet (tabela) are queued by the sync
itself, so the site serves the last approved copy (data/sheet.csv) until then.
Every step, plus plain notices from the PC pipelines (aviso), is posted to the "BioFut Avisos" group through the bot
(BIOFUT_BOT_URL) and logged in data/avisos.jsonl.
Súmula photos: the bot forwards every image of the BioFut group to POST /api/sumula_image (BIOFUT_BOT_TOKEN); sumula.py
reads it with DeepSeek Flash (daily hard limit) and real match sheets join the review queue, photo attached (data/review/media/).
A released súmula is written into the group's sheet with the Sheets API as a service account (sheet.py: BIOFUT_SHEET_ID +
the key in BIOFUT_SHEET_KEY); the sheet sync then brings it back as a regular game.
Member page (/#/eu, logged in): own stats, nickname and status (data/profiles.json, shown to everyone) and ideas/bugs
for the site (data/feedback.jsonl, listed in /admin, Ideias;
each one becomes a GitHub issue when BIOFUT_GITHUB_TOKEN is set, data/feedback_issues.json). The tabela page lists the súmulas waiting in the queue (/api/fila).
/transparencia: list stats (data/listas.json from listas.py), the automation log, and "who am I" by phone
(data/phones.json from phones.py: salted PBKDF2 hashes, never the numbers).
Login (/entrar): a member types their WhatsApp number, the bot checks they are in the group and DMs them; they answer
"sim" and the browser gets a cookie bound to its IP. A new browser or a new IP logs in again. The cookie's name is the
tabela's (phones.json); a number no list knows gets "~" + its WhatsApp name (unverified: no stats, no role) until the
member claims a tabela name in #/eu and the staff confirms it. Roles: admin = whoever logs in with BIOFUT_ADMIN_PHONE (Gab),
conselho = CONSELHO by name (súmulas, tabela, listas, Pessoas); the old BIOFUT_ADMIN key header still works for scripts.
People (/admin, Pessoas; #/eu): names on lists that could be several people, spellings to merge, number switches, from
phones.py; the answers go to data/quem.json and every page applies them to the tabela (public_state: alias, quem).
Activity log (/admin, Atividade): every POST and how it went, plus page views and clicks from a beacon (POST /api/ev), in
data/events.jsonl. No IPs or numbers: a visitor is an HMAC of the IP that changes every day; members appear by name.
"""
import base64, calendar, csv, gzip, hashlib, hmac, io, json, math, os, random, re, secrets, threading, time, urllib.parse, urllib.request
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations
from pathlib import Path

import costs, lista, sheet, sumula
try:
    import push  # Web Push needs the cryptography package; without it the site runs and push is off
except ImportError:
    push = None

HERE = Path(__file__).parent
SRC = Path(os.environ.get("BIOFUT_DATA", HERE / "biofut.json"))
STATE = HERE / "data" / "state.json"
PHOTOS = HERE / "data" / "photos"
LOCK = threading.RLock()  # re-entrant: a queue release (LOCK held) swaps the games, which takes LOCK too. ponytail: one global lock + JSON file, fine for one group of ~40; SQLite if it grows
MAX_PHOTO = 1_500_000
PIN = os.environ.get("BIOFUT_PIN", "")  # set when public: every POST needs header X-BioFut-Pin
DECK, CARD_MIN = 5, 5  # a Duelo deck is 5 cards; the cheapest card costs 5
OWN_OFF = 0.3  # 30% off your own card (index.html mirrors it): the launch video promises it


def card_cost(prices, user, card):
    """What `user` pays for `card`: the list price, 30% off (rounded down) when it is their own card."""
    return int(prices[card] * (1 - OWN_OFF)) if card == user else prices[card]
BONUS, BONUS_WHY, BONUS_END = 25, "presente do lançamento", "2026-10-31"  # one gift per member, claimed on their first visit
COPA_TS = calendar.timegm((2026, 11, 21, 11, 30, 0))  # 21/11 8:30 Brasília, same as COPA_DAY in index.html and og_copa.py


def copa_page(now=None):
    """/copa: the link to paste in the group. Its preview is today's countdown (og/copa-<days>.jpg by og_copa.py); people land on #/copa."""
    days = max(0, math.ceil((COPA_TS - (now or time.time())) / 86400))
    img = f"og/copa-{days}.jpg" if (HERE / "og" / f"copa-{days}.jpg").exists() and (now or time.time()) < COPA_TS + 86400 else "og.png"
    title = "Copa BioFut: é hoje!" if not days else f"Copa BioFut: falta{'' if days == 1 else 'm'} {days} dia{'' if days == 1 else 's'}"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{title}</title>
<meta property="og:title" content="{title}"><meta property="og:description" content="5ª Copa BioFut, sábado 21/11 às 8:30. Garanta a vaga: quem jogar a Copa ganha 50 moedas no site.">
<meta property="og:image" content="https://biofut.h-brain.org/{img}"><meta property="og:image:width" content="1200"><meta property="og:image:height" content="630">
<meta property="og:url" content="https://biofut.h-brain.org/copa"><meta property="og:type" content="website"><meta name="twitter:card" content="summary_large_image">
<meta http-equiv="refresh" content="0;url=/#/copa"></head><body><script>location.replace("/#/copa")</script><a href="/#/copa">Ver a Copa</a></body></html>""".encode()
WELCOME = DECK * CARD_MIN  # coins everyone starts with: enough for a minimal deck (Gab, 2026-10-13), the stats coins come on top
DUEL_WIN = 0.0001  # coins per Duelo won (Gab: "0.0001 (yes)")
PLAY, LEAVE = 3, 1  # coins for playing a match, coins for leaving the list after confirming (Gab, 2026-10-14)
DRAFT_OPENS = "12:00"  # the draft of a game opens at noon of its day (Gab, 2026-10-14); "" = any time (tests)
SITE = "https://biofut.h-brain.org"
PICKS = ("A", "E", "B")
SHEET = os.environ.get("BIOFUT_SHEET", "https://docs.google.com/spreadsheets/d/e/2PACX-1vQFC91XL0I0-PVBWhirPeRgmbLEbYMgt"
                       "STozCRpSWj3ime_7LNGTpUJ2yF3TThVi_qAy3JP-RqB1NSx/pub?single=true&output=csv&gid=0")
SHEET_CACHE = HERE / "data" / "sheet.csv"
SYNC_EVERY = 600
WIKI = HERE / "data" / "wiki"
SESSION_DAYS = 180
STALE_BEFORE = 1791597600  # 2026-10-09 23:00 BRT: logins before it may carry a wrong name (see session)
FAILS = {}  # ip (or "tel:" + number) -> times of recent wrong PINs / login requests
LOGINS = {}  # id -> {phone, ip, code, exp}: waiting for the "sim" on WhatsApp. ponytail: in memory, a restart drops logins in flight
ADMIN = os.environ.get("BIOFUT_ADMIN", "")  # old admin key (header X-BioFut-Admin), for scripts; unset = none
ADMIN_PHONE = os.environ.get("BIOFUT_ADMIN_PHONE", "")  # Gab's WhatsApp: logging in with it = admin. Only in /etc/biofut.env
CONSELHO = ("Andrei", "Leo Saul", "Matte", "Dan")  # second in command: the data (DATA_KINDS, Pessoas), not wiki, ideas or the log
DATA_KINDS = ("sumula", "tabela", "listas", "foto", "jogo")  # jogo: "a súmula não bate com a tabela" (#34), nothing to release
QUEM = HERE / "data" / "quem.json"  # answers to phones.py's questions: answers, merges, asks (claims waiting), claims
REVIEW = HERE / "data" / "review.json"
INBOX = HERE / "data" / "review" / "inbox"
AVISOS = HERE / "data" / "avisos.jsonl"
EVENTS = HERE / "data" / "events.jsonl"
SAFE = ("name", "captains", "captain", "player", "bettor", "pick", "stake", "score", "date", "id", "action", "page", "ref", "kind", "side", "out", "p", "h", "n", "min")  # body fields the log keeps
PHONES = HERE / "data" / "phones.json"
RADIO = HERE / "data" / "radio"  # the BioFut songs (mp3, Gab picks them: deploy.ps1 -Data), members only: #/radio
# "BioFut Hits 2025/1" on SoundCloud (soundcloud.com/h-mind/sets/biofut-hits-2025-1): played through its widget, after the mp3s
SOUNDCLOUD = [
    {"t": "TMCHB - The Most Chaotic Day in the History of Biofut", "sc": "https://soundcloud.com/h-mind/tmchb-the-most-chaotic-day-in"},
    {"t": "Prisma Biofut", "sc": "https://soundcloud.com/h-mind/prisma-biofut"},
    {"t": "Nico Gol", "sc": "https://soundcloud.com/h-mind/nico-gol"},
    {"t": "Nego Dei", "sc": "https://soundcloud.com/h-mind/negodei"},
    {"t": "K9", "sc": "https://soundcloud.com/h-mind/k9"},
    {"t": "Goleiro Lendário Douglas", "sc": "https://soundcloud.com/h-mind/goleiro-lendario-douglas"},
    {"t": "Gol Minhoca", "sc": "https://soundcloud.com/h-mind/gol-minhoca"},
    {"t": "é!", "sc": "https://soundcloud.com/h-mind/e"},
    {"t": "é?", "sc": "https://soundcloud.com/h-mind/eh-question-mark"},
    {"t": "DAN DA DAN do a Sarrada", "sc": "https://soundcloud.com/h-mind/dan-da-dan-do-a-sarrada"},
    {"t": "BioFut Warrior", "sc": "https://soundcloud.com/h-mind/biofut-warrior"},
    {"t": "BioFut Rap", "sc": "https://soundcloud.com/h-mind/biofut-ra"},
    {"t": "Big Tico of The Doug 2", "sc": "https://soundcloud.com/h-mind/big-tico-of-the-doug-2"},
    {"t": "Big Tico of The Doug", "sc": "https://soundcloud.com/h-mind/ticao"},
    {"t": "3 é Demais", "sc": "https://soundcloud.com/h-mind/3demais"},
]
AVATARS = HERE / "data" / "avatars"  # slug.jpg: the member's WhatsApp profile photo (the bot, daily), members only, for cards without a photo
LISTAS = HERE / "data" / "listas.json"
COOLDOWN = 6 * 3600
BOT_URL = os.environ.get("BIOFUT_BOT_URL", "")  # e.g. http://127.0.0.1:8787/notify
BOT_TOKEN = os.environ.get("BIOFUT_BOT_TOKEN", "")  # shared with the bot, both ways
REVIEW_MEDIA = HERE / "data" / "review" / "media"
OCR_BUDGET = HERE / "data" / "ocr_budget.json"
PROFILES = HERE / "data" / "profiles.json"  # name -> {nick, status, hide}: each member edits only their own (#/eu, /transparencia)
PUSH_SUBS, VAPID = HERE / "data" / "push.json", HERE / "data" / "vapid.pem"  # the phones that said yes; the server's push key
PIX_BONUS = 10  # coins for paying the Pix on the game's night (Gab, 2026-10-20), staff marks who paid in /admin Avisos
VOTES = WIKI / "votes.json"  # "f:<feedback id>" -> {user: 1 | -1} (concordo / discordo), "b:<bit id>" -> {user: 1..5} (graça)
LEADS = WIKI / "leads.json"  # slug -> media file: the main photo a member proposed and staff approved (kind "foto")
HIDDEN = "esta pessoa escolheu não aparecer, respeitamos a privacidade de cada um"
MSGS = HERE / "data" / "mensagens.json"  # phones.py: each member's own group messages, served only to them (#/eu)
FEEDBACK = HERE / "data" / "feedback.jsonl"  # members' ideas and bug reports from #/eu; Gab reads them in /admin, Ideias
ISSUES = HERE / "data" / "feedback_issues.json"  # fid(row) -> GitHub issue URL: each idea becomes an issue on its own
GITHUB_TOKEN = os.environ.get("BIOFUT_GITHUB_TOKEN", "")  # fine-grained, Issues read/write on REPO only. Unset = /admin keeps "Virar issue"
REPO = "Hauserrodr/biofut-public"
ISSUE_LOCK = threading.Lock()


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "x"


def clean_name(name):
    name = str(name or "").strip()
    if not 1 <= len(name) <= 30:
        raise ValueError("nome inválido")
    return name


# --- Google Sheet -> games ------------------------------------------------------

def sheet_games(text):
    """DATABASE tab (one row per player per game) -> [{n, season, date, teams: [{name, gf, ga, res, players}]}]."""
    out = {}
    for r in list(csv.reader(io.StringIO(text)))[1:]:
        if len(r) < 18 or not r[13].strip() or not r[2].strip().isdigit():
            continue  # empty name = placeholder row for a future game
        n = int(r[2])
        m = re.match(r"(\d+)/(\d+)(?:/\d+)?$", r[11].strip())  # "27/05/2019" or "26/7"; cups have no date
        g = out.setdefault(n, {"n": n, "season": r[10].strip(), "date": f"{r[0]}-{int(m[2]):02}-{int(m[1]):02}" if m else None, "teams": []})
        name = r[12].strip()
        t = next((t for t in g["teams"] if t["name"] == name), None)
        if not t:
            t = {"name": name, "gf": int(r[6] or 0), "ga": int(r[7] or 0), "res": r[8].strip(), "players": []}
            g["teams"].append(t)
        num = lambda v: int(float(v)) if v.strip() else 0
        player = r[13].strip()
        t["players"].append(["Sombra" if player == "SOMBRA" else player, num(r[14]), num(r[15]), num(r[16]), int(bool(r[17].strip()))])
    games = []
    for g in out.values():
        if len(g["teams"]) > 2:  # stray copy-paste team, its goals cell holds a row number (game 261)
            g["teams"] = [t for t in g["teams"] if t["gf"] != 2959]
        if len(g["teams"]) != 2:
            continue
        for t, o in (g["teams"], g["teams"][::-1]):
            if t["gf"] > 40:  # bogus cell (game 1): recount from goals + the other side's own goals
                t["gf"] = sum(p[1] for p in t["players"]) + sum(p[3] for p in o["players"])
        for t, o in (g["teams"], g["teams"][::-1]):
            t["ga"] = o["gf"]
            t["res"] = "V" if t["gf"] > t["ga"] else "D" if t["gf"] < t["ga"] else "E"
        games.append(g)
    return sorted(games, key=lambda g: g["n"])


def use_games(games):
    global DATA, DATA_RAW
    data = {**DATA, "games": games}
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
    with LOCK:
        DATA, DATA_RAW = data, raw


def game_line(g):
    a, b = g["teams"]
    return f"#{g['n']} {g['date'] or 'sem data'} {a['name']} {a['gf']}x{b['gf']} {b['name']}"


def sheet_diff(old, new):
    """What a sheet change does to the served games, in lines Gab can read on /admin and in the Avisos group."""
    o, n = {g["n"]: g for g in old}, {g["n"]: g for g in new}
    return ([f"+ {game_line(g)}" for k, g in n.items() if k not in o] +
            [f"~ {game_line(g)}" for k, g in n.items() if k in o and o[k] != g] +
            [f"- {game_line(g)}" for k, g in o.items() if k not in n])


def propose_sheet(text, now=None):
    """A sheet that differs from what the site serves becomes one pending 'tabela' item (updated in place while it waits,
    so the 6 h clock doesn't restart on every edit). A copy Gab already rejected isn't proposed again."""
    games = sheet_games(text)
    if len(games) < len(DATA["games"]) - 5:  # ponytail: guards against a half-deleted sheet wiping history
        return None
    diff = sheet_diff(DATA["games"], games)
    if not diff:  # the sheet is back to what the site serves: a pending proposal is stale
        with LOCK:
            items = load_review()
            for it in items:
                if it["kind"] == "tabela" and it["status"] == "pending":
                    it.update(status="obsolete", decided=time.strftime("%Y-%m-%dT%H:%M:%S"), payload={"diff": it["payload"].get("diff")})
                    write_json(REVIEW, items, 1)
                    return f"🗑️ #{it['id']} {it['title']}: a planilha voltou ao que o site já mostra, proposta descartada"
        return None
    sha = hashlib.sha256(text.encode()).hexdigest()[:16]
    title = f"Planilha: {len(diff)} jogo(s) mudaram ({', '.join(d.split()[1] for d in diff[:5])}{'…' if len(diff) > 5 else ''})"
    with LOCK:
        items = load_review()
        if any(it["kind"] == "tabela" and it["payload"].get("sha") == sha for it in items if it["status"] in ("pending", "rejected")):
            return None
        it = next((x for x in items if x["kind"] == "tabela" and x["status"] == "pending"), None)
        if it:
            it.update(title=title, payload={"sha": sha, "diff": diff, "csv": text})
            note = f"✏️ #{it['id']} atualizado: {title}"
        else:
            it = {"id": max([x["id"] for x in items] + [0]) + 1, "kind": "tabela", "title": title, "created": now or time.time(),
                  "status": "pending", "payload": {"sha": sha, "diff": diff, "csv": text}}
            items.append(it)
            note = new_note(it)
        write_json(REVIEW, items, 1)
    return note + "\n" + "\n".join(diff[:10])


def sync_sheet():
    """Every SYNC_EVERY s: fetch the sheet; a change goes to the review queue, not straight to the site."""
    while True:
        try:
            note = propose_sheet(urllib.request.urlopen(SHEET, timeout=30).read().decode("utf-8"))
            if note:
                notify(note)
        except Exception as e:  # network blip or Google hiccup: serve the last approved copy
            print("sheet sync failed:", e, flush=True)
        time.sleep(SYNC_EVERY)


# --- BioBet: odds from the exported logistic model, coins from goals + assists --------------

def odds(model, a, b):
    """Fair decimal odds {A, E, B} for team a vs team b. Same math as biobet.Model.odds, no numpy."""
    idx = {p: i for i, p in enumerate(model["players"])}
    pairs, k = model["pairs"], model["shrink"]

    def chem(team):
        ps = list(combinations(sorted(set(team)), 2))
        if not ps:
            return 0.5
        return sum((w + .5 * k) / (n + k) for w, n in (pairs.get(f"{p}|{q}", (0, 0)) for p, q in ps)) / len(ps)

    c = 10 * (chem(a) - chem(b))
    z = [b0 + sum(w[idx[p]] for p in a if p in idx) - sum(w[idx[p]] for p in b if p in idx) + w[-1] * c
         for w, b0 in zip(model["coef"], model["intercept"])]
    e = [math.exp(v - max(z)) for v in z]
    return {cls: round(1 / max(v / sum(e), 0.02), 2) for cls, v in zip(model["classes"], e)}


HOUSE = 0.042  # the house (BioBet) keeps 4.2% of what is bet, in state["casa"]; what it does with it comes later


def take(coins):
    """The house's 4.2% of coins, to the nearest coin."""
    return int(coins * HOUSE + .5)


def offered(model, a, b):
    """The odds a member gets on the game: the model's fair odds less the house's 4.2%."""
    return {k: round(v * (1 - HOUSE), 2) for k, v in odds(model, a, b).items()}


def unsynced(played, games):
    """Games recorded on the site that the sheet doesn't have yet (the sheet wins once it has that date)."""
    dates = {g["date"] for g in games}
    return [g for g in played if g["date"] not in dates]


def sheet_rows(g):
    """A site game as the DATABASE tab's L..R cells (Data, Time, Nome, Gol, Assistência, Gol Contra, Capitão), zeros
    left blank, the same rows sheet.py writes. Pasted at column L of an empty game block, it is that game."""
    y, m, d = g["date"].split("-")
    return [[f"{int(d)}/{int(m)}/{y[2:]}", t["name"], p, *(str(v) if v else "" for v in (gl, ast, own)), "1" if cap else ""]
            for t in g["teams"] for p, gl, ast, own, cap in t["players"]]


def minted(games):
    """Coins per player before the bet ledger: WELCOME + 1 per goal/assist ever."""
    out = {}
    for g in games:
        for t in g["teams"]:
            for p, gl, ast, *_ in t["players"]:
                out[p] = out.get(p, WELCOME) + gl + ast
    return out


def balance(state, base, player):
    b = base.get(player, WELCOME) + sum(x["amount"] for x in state["ledger"] if x["player"] == player)
    v = state.get("duelo", {}).get(player, {}).get("v", 0)
    return round(b + v * DUEL_WIN, 4) if v else b


def card_prices(games):
    """#36: a card costs half the goals + assists its player ever made (at least 5), so the top scorers' cards cost the most
    and only someone with that many points buys them. Cards start at 10 games, names fixed as the site shows them."""
    alias, quem = name_fixes()
    seen = {}
    for g in games:
        for t in g["teams"]:
            for p, gl, ast, *_ in t["players"]:
                p = alias.get(p, p)
                p = quem.get(f"{g['date']}|{p}", p)
                j, pts = seen.get(p, (0, 0))
                seen[p] = (j + 1, pts + gl + ast)
    return {p: max(CARD_MIN, pts // 2) for p, (j, pts) in seen.items() if j >= 10 and p != "Sombra"}


STATS = ("GOL", "ASS", "VIT", "EXP", "CAP")  # the card attributes, as index.html cards() computes them


def first_buyers(state):
    """Card -> the member who bought it first (ledger order). They hold its cromada: the one copy with +1 on a stat they pick."""
    fb = {}
    for x in state["ledger"]:
        if x["reason"].startswith("carta "):
            fb.setdefault(x["reason"][6:], x["player"])
    return fb


def buy_card(state, base, prices, user, card, stat=""):
    """#36: points are coins (balance): a card leaves the wallet like a bet does and joins the member's deck (the Duelo).
    The first buyer gets the cromada and picks its +1 stat in the same buy."""
    deck = state.setdefault("cards", {}).get(user, [])
    first = card not in first_buyers(state)
    if card not in prices or card in deck:
        raise ValueError("essa carta não existe ou já é sua")
    if first and stat not in STATS:
        raise ValueError("escolha o atributo +1 da cromada")
    cost = card_cost(prices, user, card)
    if balance(state, base, user) < cost:
        raise ValueError(f"você tem {balance(state, base, user)} moedas, a carta custa {cost}")
    state["cards"][user] = deck + [card]
    state["ledger"].append({"player": user, "amount": -cost, "reason": f"carta {card}"})
    if first:
        state.setdefault("cromo", {})[card] = stat
    team = state.setdefault("deck", {}).setdefault(user, [])
    if len(team) < DECK:  # the first 5 cards bought make the deck by themselves; after that the member picks (set_deck)
        team.append(card)


def set_deck(state, user, names):
    """#/deck: the 5 cards of the member's collection they take to the Duelo."""
    if not user:
        raise ValueError("entre para montar o seu deck")
    own = state.get("cards", {}).get(user, [])
    if type(names) is not list or len(set(names)) != DECK or len(names) != DECK or not all(n in own for n in names):
        raise ValueError(f"escolha {DECK} cartas da sua coleção")
    state.setdefault("deck", {})[user] = names


def deck_of(state, user):
    """The member's 5 for the Duelo: the saved deck while all its cards are still theirs, else their first 5 cards."""
    own, team = state.get("cards", {}).get(user, []), state.get("deck", {}).get(user, [])
    return team if len(team) == DECK and all(n in own for n in team) else own[:DECK]


def claim_cromo(state, user, card, stat):
    """A cromada bought before 2026-10-10 has no stat yet: its first buyer picks it, once."""
    if not user or first_buyers(state).get(card) != user or card in state.get("cromo", {}):
        raise ValueError("a cromada desta carta não é sua")
    if stat not in STATS:
        raise ValueError("escolha o atributo +1 da cromada")
    state.setdefault("cromo", {})[card] = stat


def duel_cards(games):
    """index.html cards(agg(G)) in Python, the numbers the site shows: the server deals and judges the Duelo, so the
    ranking and the coins come from duels the browser cannot fake. ovr adds in a loop like the JS reduce: Python's
    sum() of floats rounds another way since 3.12, and one ulp moves a card across a tier line."""
    alias, quem = name_fixes()
    P = {}
    for g in sorted(games, key=lambda g: g["n"]):
        for t in g["teams"]:
            for p, gl, ast, _, cap in (x[:5] for x in t["players"]):
                p = quem.get(f"{g['date']}|{alias.get(p, p)}", alias.get(p, p))
                if p != "Sombra":
                    s = P.setdefault(p, {"name": p, "j": 0, "v": 0, "g": 0, "a": 0, "cap": 0})
                    s["j"], s["v"], s["g"], s["a"], s["cap"] = s["j"] + 1, s["v"] + (t["res"] == "V"), s["g"] + gl, s["a"] + ast, s["cap"] + cap
    regs = [s for s in P.values() if s["j"] >= 10]
    A = {"GOL": lambda s: s["g"] / s["j"], "ASS": lambda s: s["a"] / s["j"], "VIT": lambda s: s["v"] / s["j"],
         "EXP": lambda s: s["j"], "CAP": lambda s: s["cap"] / s["j"]}
    W = {"GOL": .3, "ASS": .25, "VIT": .3, "EXP": .1, "CAP": .05}
    vals = {k: [f(s) for s in regs] for k, f in A.items()}
    out = []
    for s in regs:
        at = {k: math.floor(40 + 59 * sum(v <= f(s) for v in vals[k]) / len(regs) + .5) for k, f in A.items()}
        ovr = 0
        for k, w in W.items():
            ovr += at[k] * w
        ovr = math.floor(ovr + .5)
        tier = "lenda" if s["j"] >= 100 and ovr >= 75 else "ouro" if ovr >= 80 else "prata" if ovr >= 68 else "bronze"
        out.append({"name": s["name"], "j": s["j"], "ovr": ovr, "tier": tier, "at": at})
    return sorted(out, key=lambda c: -c["ovr"])


def duel_deal(state, user, cards, mode, name, day):
    """index.html newDuel: the Duelo do dia deals the same cards to everyone (seeded by the day), a free duel starts with
    the card of the player in the link, the deck duel with 5 of the member's own cards (the cromada +1 counts)."""
    if len(cards) < 10:
        raise ValueError("poucas cartas para um duelo")
    r = random.Random(day) if mode == "dia" else random.SystemRandom()
    deck = cards[:]
    r.shuffle(deck)
    if mode == "deck":
        mine, crom, fb = deck_of(state, user), state.get("cromo", {}), first_buyers(state)
        own = [c for c in deck if c["name"] in mine]  # shuffled: the order of the 5 is luck, as in Super Trunfo
        if len(own) < DECK:
            raise ValueError(f"compre {DECK} cartas para jogar com o seu deck")
        deck = [{**c, "crom": k, "at": {**c["at"], k: c["at"][k] + 1}} if fb.get(c["name"]) == user and (k := crom.get(c["name"])) else c
                for c in own] + [c for c in deck if c not in own]
    elif mode == "livre":
        pick = next((c for c in cards if c["name"] == name), None) or r.choice(cards[:40])
        deck = [pick] + [c for c in deck if c is not pick]
    return {"mode": mode, "day": day, "ace": cards[0]["name"], "you": deck[:5], "cpu": deck[5:10], "log": []}


def duel_act(state, user, cards, body, day):
    """The Duelo of a logged-in member, best of 5: they pick the attribute in rounds 1, 3, 5, the machine its card's best
    in 2 and 4. One open duel each, so opening again returns it (no dealing again for a better hand), and the Duelo do
    dia once a day. A finished duel goes to the member's record (state duelo, public): wins (DUEL_WIN coins each), draws,
    losses, the run of wins now and the longest, the best score. The machine's cards stay hidden until played."""
    if not user:
        raise ValueError("entre para jogar o Duelo valendo")
    rec = state.setdefault("duelo", {}).setdefault(user, {"v": 0, "e": 0, "d": 0, "run": 0, "top": 0, "best": None, "dia": None})
    duels = state.setdefault("duelo_aberto", {})
    d, at = duels.get(user), body.get("at")
    if at is None:
        mode = body.get("mode") if body.get("mode") in ("livre", "deck") else "dia"
        if not d and mode == "dia" and (rec["dia"] or [""])[0] == day:
            return {"feito": rec["dia"][1]}
        d = duels[user] = d or duel_deal(state, user, cards, mode, str(body.get("name") or ""), day)
    else:
        if not d:
            raise ValueError("este duelo acabou: comece outro")
        i = len(d["log"])
        x, y = d["you"][i], d["cpu"][i]
        a = at if i % 2 == 0 else max(STATS, key=lambda k: y["at"][k])  # the JS reduce: the first best on a tie
        if a not in STATS:
            raise ValueError("escolha um atributo")
        w = ((-1 if y["tier"] == "bronze" else 1) if x["name"] == d["ace"] else  # Super Craque, except a bronze card
             (1 if x["tier"] == "bronze" else -1) if y["name"] == d["ace"] else (x["at"][a] > y["at"][a]) - (x["at"][a] < y["at"][a]))
        d["log"].append([a, w])
        if len(d["log"]) == 5:
            del duels[user]
            sc = [sum(w > 0 for _, w in d["log"]), sum(w < 0 for _, w in d["log"])]
            r = (sc[0] > sc[1]) - (sc[0] < sc[1])
            rec["ved"[1 - r]] += 1  # win, draw, loss
            rec["run"] = rec["run"] + 1 if r > 0 else 0
            rec["top"] = max(rec["top"], rec["run"])
            if not rec["best"] or (sc[0], -sc[1]) > (rec["best"][0], -rec["best"][1]):
                rec["best"] = sc
            if d["mode"] == "dia":
                rec["dia"] = [d["day"], sc]
    n = len(d["log"])
    return {**d, "cpu": d["cpu"][:n] + [None] * (5 - n)}


# --- BioTruco v0.2: Truco Gaúcho with the cards, against the machine (Gab, 2026-10-20) -------------------------------
# A hand is 3 rounds, best of 3 (the tie rules of the Truco Gaúcho), played with 3 of the member's 5 deck cards against
# 3 of the machine's. Higher OVR takes the round; the Super Craque beats everyone except a bronze card, as in the Duelo.
# Truco 2, retruco 3, vale quatro 4; "não quero" gives the caller the hand at its value before the call. New: "aposto
# que perco" before your first card of a hand. Refused, the hand goes on; accepted, losing the hand scores nobody and
# winning it scores double. A match goes to 13, 25 or 37. Envido and flor come later (Gab: "start with truco").
TRUCO_ALVOS = (13, 25, 37)
TRUCO_WIN = 0.001  # coins per match won (10 Duelos' worth: one match is ~10 hands)
TRUCO_V02, TRUCO_X10_END = "2026-10-22", "2026-10-28"  # launch week: x10 coins per win (Gab, 2026-10-20)
TRUCO_APOSTA = .8  # the machine takes "aposto que perco" only when it expects to win the hand anyway
TRUCO_BLEFE = .1  # how often it says truco on a weak hand, so a call does not always mean strength


def truco_round(ace, x, y):
    """0: your card x takes the round, 1: the machine's y, None: a tie (parda)."""
    if x["name"] == ace:
        return 1 if y["tier"] == "bronze" else 0
    if y["name"] == ace:
        return 0 if x["tier"] == "bronze" else 1
    return None if x["ovr"] == y["ovr"] else 0 if x["ovr"] > y["ovr"] else 1


def truco_hand_end(rw, mao):
    """Who takes the hand after these rounds (None: play on). Two rounds win it; a tie goes to whoever won the other
    round, or the first round won; all three tied go to the mão (who led the hand)."""
    a, b = rw.count(0), rw.count(1)
    if a >= 2 or b >= 2 or len(rw) == 2 and a + b == 1 or len(rw) == 3 and a != b:
        return 0 if a > b else 1
    if len(rw) == 3:
        return next((w for w in rw if w is not None), mao)
    return None


def truco_ev(t, k, **kw):
    """The replay list for #/truco: what just happened, with the table right after it (the machine's hand still hidden)."""
    v = truco_view(t)
    v.pop("ultima")
    t.setdefault("ev", []).append({"k": k, **kw, "v": json.loads(json.dumps(v))})


def truco_deal(t, cards, r):
    mine = {c["name"] for c in t["deck"]}
    lead = t["n"] % 2  # you are mão in the first hand, then it alternates
    lo, hi = min(c["ovr"] for c in t["deck"]), max(c["ovr"] for c in t["deck"])
    rest = [c for c in cards if c["name"] not in mine]
    band = [c for c in rest if lo <= c["ovr"] <= hi]  # the machine plays cards as good as your deck, not the whole pile
    t["h"] = {"you": r.sample(t["deck"], 3), "cpu": r.sample(band if len(band) >= 6 else rest, 3), "usou": [[], []],
              "mesa": [None, None], "jogadas": [], "rw": [], "mao": lead, "turn": lead, "val": 1, "call": None, "pode": None, "aposta": None}
    truco_ev(t, "da")


def truco_end_hand(t, w, fugiu=False):
    h, a = t["h"], t["h"]["aposta"]
    pts = h["val"] if not (a and a["ok"]) else 2 * h["val"] if w == a["by"] else 0
    t["pts"][w] += pts
    truco_ev(t, "mao", w=w, pts=pts, fugiu=fugiu)
    t["n"] += 1
    t["ultima"] = {"w": w, "pts": pts, "val": h["val"], "fugiu": fugiu, "aposta": a, "you": h["you"], "cpu": h["cpu"], "jogadas": h["jogadas"], "rw": h["rw"]}
    t["h"] = None


def truco_play(t, s, i):
    h = t["h"]
    if h["call"] or h["turn"] != s or type(i) is not int or not 0 <= i < 3 or i in h["usou"][s]:
        raise ValueError("essa carta não dá para jogar agora")
    h["usou"][s].append(i)
    h["mesa"][s] = i
    if h["mesa"][1 - s] is None:
        h["turn"] = 1 - s
        return truco_ev(t, "carta", s=s, i=i)
    truco_ev(t, "carta", s=s, i=i)
    w = truco_round(t["ace"], h["you"][h["mesa"][0]], h["cpu"][h["mesa"][1]])
    h["rw"].append(w)
    h["jogadas"].append(h["mesa"])
    h["mesa"] = [None, None]
    h["turn"] = w if w is not None else 1 - s  # the round's winner leads the next; after a tie, who led it leads again
    truco_ev(t, "rodada", w=w)
    end = truco_hand_end(h["rw"], h["mao"])
    if end is not None:
        truco_end_hand(t, end)


def truco_call(t, s):
    """Side s says truco (or raises the call made to it: retruco, vale quatro)."""
    h, c = t["h"], t["h"]["call"]
    if c and c["by"] != s and c["to"] < 4:
        h["val"], h["call"] = c["to"], {"by": s, "to": c["to"] + 1}
    elif not c and h["val"] < 4 and h["pode"] in (None, s) and h["turn"] == s:
        h["call"] = {"by": s, "to": h["val"] + 1}
    else:
        raise ValueError("agora não dá para pedir truco")
    truco_ev(t, "pede", s=s, to=h["call"]["to"])


def truco_answer(t, s, quero):
    h, c = t["h"], t["h"]["call"]
    if not c or c["by"] == s:
        raise ValueError("ninguém pediu truco")
    if not quero:
        truco_ev(t, "resp", s=s, quero=False, to=c["to"])
        return truco_end_hand(t, c["by"], fugiu=True)
    h["val"], h["pode"], h["call"] = c["to"], s, None  # who accepted is the one who may raise later
    truco_ev(t, "resp", s=s, quero=True, to=c["to"])


def truco_odds(t, h):
    """The machine's chance to take the hand, and per card it may play now, from what it may know: its own cards, the
    cards on the table and the member's deck (public in #/deck) minus the cards already played, never your hand. Each
    hand you could hold is played out with both sides picking their best cards (you knowing the machine's), averaged."""
    ace, M, usou = t["ace"], h["cpu"], h["usou"]
    seen = {h["you"][j]["name"] for j in usou[0]}
    Y = [c for c in t["deck"] if c["name"] not in seen]
    yon = None
    if h["mesa"][0] is not None:
        yon = len(Y)
        Y.append(h["you"][h["mesa"][0]])
    ml = frozenset(i for i in range(3) if i not in usou[1])
    W = {(a, b): truco_round(ace, Y[a], M[b]) for a in range(len(Y)) for b in range(3)}
    memo = {}

    def val(ys, ms, rw, yo, mo, turn):  # 1: the machine takes the hand with best play from here, 0: you do
        end = truco_hand_end(list(rw), h["mao"])
        if end is not None:
            return float(end)
        k = (ys, ms, rw, yo, mo, turn)
        if k not in memo:
            memo[k] = (max if turn else min)(move(ys, ms, rw, yo, mo, turn, x) for x in (ms if turn else ys))
        return memo[k]

    def move(ys, ms, rw, yo, mo, turn, x):
        if turn:
            if yo is None:
                return val(ys, ms - {x}, rw, None, x, 0)
            w = W[yo, x]
            return val(ys, ms - {x}, rw + (w,), None, None, 0 if w is None else w)
        if mo is None:
            return val(ys - {x}, ms, rw, x, None, 1)
        w = W[x, mo]
        return val(ys - {x}, ms, rw + (w,), None, None, 1 if w is None else w)

    hands = [frozenset(c) for c in combinations(range(len(Y) - (yon is not None)), 3 - len(usou[0]))]
    rw, mo = tuple(h["rw"]), h["mesa"][1]
    p = sum(val(ys, ml, rw, yon, mo, h["turn"]) for ys in hands) / len(hands)
    per = {x: sum(move(ys, ml, rw, yon, mo, 1, x) for ys in hands) / len(hands) for x in ml} if h["turn"] == 1 else {}
    return p, per


def truco_cpu(t, cards, r):
    """The machine's moves until it is your turn: answer a call, maybe call, play a card. It weighs its chance to take
    the hand (truco_odds) against the points at stake; a bet you accepted means it cannot score, so it never calls then."""
    rank = {c["name"]: i for i, c in enumerate(cards)}  # cards come strongest first
    rank[t["ace"]] = -1
    while t["h"]:
        h, c = t["h"], t["h"]["call"]
        safe = h["aposta"] and h["aposta"]["ok"]  # you bet you lose and it took the bet: you win double or nobody scores
        if c and c["by"] == 0:
            p, _ = truco_odds(t, h)
            v, to = h["val"], c["to"]
            if not safe and to < 4 and p > .78:
                truco_call(t, 1)
                return
            if safe:
                quero = (1 - p) * to <= v  # refusing hands you 2 x the value now; accepting risks 2 x the new one
            else:  # accept when the expected points beat giving you the hand now, or when refusing ends the match
                quero = p > (to - v) / (2 * to) + .1 or t["pts"][0] + v >= t["alvo"]
            truco_answer(t, 1, quero)
        elif not c and h["turn"] == 1:
            p, per = truco_odds(t, h)
            if not safe and h["val"] < 4 and h["pode"] in (None, 1) and (p > .66 or p < .35 and h["val"] == 1 and r.random() < TRUCO_BLEFE):
                truco_call(t, 1)
                return
            best = max(per.values())  # of the cards that do best, the weakest: strong cards stay for later
            truco_play(t, 1, max((x for x in per if per[x] > best - 1e-9), key=lambda x: rank.get(h["cpu"][x]["name"], len(cards))))
        else:
            return


def truco_view(t):
    h = t["h"]
    v = {k: t.get(k) for k in ("alvo", "pts", "n", "ace", "ultima", "fim", "x10", "deck_proprio")}
    if h:
        v["h"] = {**h, "cpu": [c if i in h["usou"][1] else None for i, c in enumerate(h["cpu"])]}
    return v


def truco_act(state, user, cards, body, day, r=random.SystemRandom()):
    """#/truco for a logged-in member. op: (none) the open match or None, "novo" {alvo}, "jogar" {i}, "truco", "quero",
    "nao", "aposta", "desisto". One open match each. A finished match goes to state truco (public): wins, losses, the run
    of wins and the longest; a win pays TRUCO_WIN coins (x10 in the launch week) through the ledger."""
    if not user:
        raise ValueError("entre para jogar o BioTruco")
    if len(cards) < 10:
        raise ValueError("poucas cartas para o BioTruco")
    t, op = state.get("truco_aberto", {}).get(user), body.get("op")
    if not op:
        return truco_view(t) if t else None
    if op == "novo" and not t:
        if body.get("alvo") not in TRUCO_ALVOS:
            raise ValueError("escolha 13, 25 ou 37 pontos")
        games = state.setdefault("truco_aberto", {})
        mine = deck_of(state, user)
        deck = [c for c in cards if c["name"] in mine]
        own = len(deck) == DECK
        t = games[user] = {"alvo": body["alvo"], "pts": [0, 0], "n": 0, "ace": cards[0]["name"], "ultima": None,
                           "deck": deck if own else r.sample(cards, DECK), "deck_proprio": own, "x10": TRUCO_V02 <= day <= TRUCO_X10_END}
        truco_deal(t, cards, r)
    elif not t:
        raise ValueError("esta partida acabou: comece outra")
    elif op == "desisto":
        t["pts"][1] = t["alvo"]
        truco_ev(t, "desisto")
    elif op != "novo":  # "novo" with a match open returns it: no dealing again for a better hand
        h = t["h"]
        if op == "jogar":
            truco_play(t, 0, body.get("i"))
        elif op == "truco":
            truco_call(t, 0)
        elif op in ("quero", "nao"):
            truco_answer(t, 0, op == "quero")
        elif op == "aposta":
            if h["aposta"] or h["usou"][0] or h["call"]:
                raise ValueError("a aposta é antes da sua primeira carta da mão")
            h["aposta"] = {"by": 0, "ok": truco_odds(t, h)[0] >= TRUCO_APOSTA}
            truco_ev(t, "aposta", ok=h["aposta"]["ok"])
        else:
            raise ValueError("jogada desconhecida")
    while max(t["pts"]) < t["alvo"]:
        if not t["h"]:
            truco_deal(t, cards, r)
        truco_cpu(t, cards, r)
        if t["h"]:
            break
    if max(t["pts"]) >= t["alvo"]:
        won = t["pts"][0] >= t["alvo"]
        rec = state.setdefault("truco", {}).setdefault(user, {"v": 0, "d": 0, "run": 0, "top": 0})
        rec["v" if won else "d"] += 1
        rec["run"] = rec["run"] + 1 if won else 0
        rec["top"] = max(rec["top"], rec["run"])
        coins = TRUCO_WIN * (10 if t["x10"] else 1) if won else 0
        if coins:
            state["ledger"].append({"player": user, "amount": coins, "reason": f"biotruco {day} {t['pts'][0]}x{t['pts'][1]}"})
        t["fim"], t["h"] = {"won": won, "coins": coins}, None
        truco_ev(t, "fim")
        del state["truco_aberto"][user]
    return {**truco_view(t), "ev": t.pop("ev", [])}


# --- match / draft state -------------------------------------------------------

def new_match(date=""):
    return {"date": date, "confirmed": [], "draft": None, "bets": []}


def new_state():
    return {"match": new_match(), "played": [], "ledger": [], "next_bet": 1}


def snake_turn(draft):
    n = sum(len(t) for t in draft["teams"].values()) - 2  # captains don't count as picks
    return draft["captains"][[0, 1, 1, 0][n % 4]]


def redraft(state, why):
    """Teams back to the captains only (the first picker stays); the bets, if any, go back. Leaves draft["redraft"] for the group."""
    mt, d = state["match"], state["match"]["draft"]
    if mt["bets"]:  # the BioBet history keeps them
        state.setdefault("cancelados", []).append({"date": mt["date"], "at": int(time.time()), "bets": mt["bets"]})
    for bet in mt["bets"]:
        state["ledger"].append({"player": bet["bettor"], "amount": bet["stake"], "reason": f"redraft {mt['date']}"})
    n, mt["bets"] = len(mt["bets"]), []
    d.update(teams={c: [c] for c in d["captains"]}, ok=[], votes={})
    d["redraft"] = why + (f". {n} aposta{'s' * (n != 1)} devolvida{'s' * (n != 1)}" if n else "")


def heads(mt):
    """Names on the list plus names waiting on the captains: what a sign-up grows."""
    return len(mt["confirmed"]) + len((mt["draft"] or {}).get("pending", {}))


def season_of(date):
    return f"{date[:4]}/{1 if int(date[5:7]) <= 6 else 2}"


def guard(mt, action, body, user, staff):
    """Who may do what (jarvis 2026-10-16): staff anything; a captain only as themself; nobody closes a match blind."""
    if staff:
        return
    caps = (mt["draft"] or {}).get("captains", [])
    if action in ("close_match", "draft_undo") and user not in caps:
        raise ValueError("só os capitães ou o conselho")
    if "captain" in body and clean_name(body.get("captain")) != user:
        raise ValueError("só o próprio capitão")
    if action == "unconfirm" and clean_name(body.get("name")) != user:
        body["free"] = True  # taking someone else off the list never costs them coins
    if action == "new_match" and not re.fullmatch(r"\d{4}-\d\d-\d\d", str(body.get("date", ""))):
        raise ValueError("data inválida")


def apply(state, action, body, data=None, base=None):
    """Mutates state for one POST action. Raises ValueError on bad input."""
    mt = state["match"]
    conf, draft = mt["confirmed"], mt["draft"]
    if action in ("unconfirm", "draft_start", "draft_pick", "draft_undo") and mt["bets"]:
        raise ValueError("já tem aposta neste jogo; o draft está travado")
    if action == "signup":
        name = clean_name(body.get("name"))
        if name.lower() in (c.lower() for c in conf + list((draft or {}).get("pending", {}))):
            pass
        elif draft:  # the draft is running: the name waits for both captains, then the draft restarts (Gab, 2026-10-14)
            draft.setdefault("pending", {})[name] = []
        else:
            conf.append(name)
    elif action == "unconfirm":
        name = clean_name(body.get("name"))
        if draft and any(name in t for t in draft["teams"].values()):
            raise ValueError("já escolhido no draft")
        if draft:
            draft.get("pending", {}).pop(name, None)
        if name in conf and not body.get("free"):
            state["ledger"].append({"player": name, "amount": -LEAVE, "reason": f"saiu da lista {mt['date']}"})
        mt["confirmed"] = [c for c in conf if c != name]
    elif action == "draft_start":
        caps = [clean_name(c) for c in body.get("captains", [])]
        if len(caps) != 2 or caps[0] == caps[1] or not all(c in conf for c in caps):
            raise ValueError("escolha 2 capitães diferentes entre os confirmados")
        bar = {b["who"] for m in state.get("mercados", []) if m["kind"] == "capitao" and m["status"] == "aberta"
               and m["date"] == mt["date"] and time.time() < m["kick"] - m["h"] * 3600 for b in m["bets"]} & set(caps)
        if bar:
            raise ValueError(f"{', '.join(sorted(bar))} apostou no prazo dos capitães: só pode ser capitão depois dele")
        if DRAFT_OPENS and mt["date"] and time.time() < kickoff(mt["date"], DRAFT_OPENS):
            raise ValueError(f"o draft abre ao meio-dia do dia do jogo ({mt['date'][8:10]}/{mt['date'][5:7]})")
        mt["draft"] = {"captains": caps, "teams": {c: [c] for c in caps}, "ok": [], "first": None, "flip": {}, "pending": {}, "votes": {}, "ditador": []}
        mt.setdefault("caps_at", int(time.time()))  # BioBet capitao: when the captains came out
    elif action == "draft_pick":
        if not draft or len(draft["ok"]) == 2:
            raise ValueError("sem draft aberto")
        if draft.get("first", "") is None:
            raise ValueError("decidam quem começa: moeda ou acordo")
        cap, player = clean_name(body.get("captain")), clean_name(body.get("player"))
        if cap != snake_turn(draft):
            raise ValueError(f"vez de {snake_turn(draft)}")
        if player not in conf or any(player in t for t in draft["teams"].values()):
            raise ValueError("jogador indisponível")
        draft["teams"][cap].append(player)
        draft["ok"] = []  # any change re-opens confirmation
    elif action == "draft_confirm":
        cap = clean_name(body.get("captain"))
        if not draft or cap not in draft["captains"]:
            raise ValueError("capitão inválido")
        if cap not in draft["ok"]:
            draft["ok"].append(cap)
    elif action == "draft_undo":
        if not draft or sum(len(t) for t in draft["teams"].values()) <= 2:
            raise ValueError("nada para desfazer")
        n = sum(len(t) for t in draft["teams"].values()) - 3
        draft["teams"][draft["captains"][[0, 1, 1, 0][n % 4]]].pop()
        draft["ok"] = []
    elif action == "draft_flip":  # who picks first: both call cara/coroa blind (a tie flips again), or both name the same captain
        cap, choice = clean_name(body.get("captain")), str(body.get("choice") or "").strip()
        if not draft or cap not in draft["captains"] or draft.get("first", "") is not None:
            raise ValueError("sem moeda para jogar")
        if choice not in ("cara", "coroa") and clean_name(choice) not in draft["captains"]:
            raise ValueError("escolha cara, coroa ou um capitão")
        flip = draft.setdefault("flip", {})
        flip[cap] = choice if choice in ("cara", "coroa") else clean_name(choice)
        draft.pop("note", None)
        if len(flip) == 2:
            a, b = (flip[c] for c in draft["captains"])
            coin = {a, b} <= {"cara", "coroa"}
            if coin and a != b:
                res = random.choice(["cara", "coroa"])
                draft["first"] = next(c for c in draft["captains"] if flip[c] == res)
                draft["coin"] = {"result": res, "sides": dict(flip), "at": int(time.time())}
            elif not coin and a == b:
                draft["first"] = a
            else:
                draft["note"] = f"Os dois disseram {a}. De novo!" if coin else f"Um disse {a}, outro {b}: só vale se os dois concordarem. Ou joguem a moeda."
                draft["flip"] = {}
        if draft.get("first"):
            draft["captains"].sort(key=lambda c: c != draft["first"])  # the first picker is team A
            draft["teams"] = {c: draft["teams"][c] for c in draft["captains"]}
    elif action == "draft_admit":  # a late name: each captain says yes (or no); both yes -> on the list, and the draft restarts
        cap, player, ok = clean_name(body.get("captain")), clean_name(body.get("player")), bool(body.get("ok", True))
        pend = (draft or {}).get("pending", {})
        if not draft or cap not in draft["captains"] or player not in pend:
            raise ValueError("ninguém esperando com esse nome")
        if not ok:
            pend.pop(player)
        elif cap not in pend[player]:
            pend[player].append(cap)
            if len(pend[player]) == 2:
                pend.pop(player)
                conf.append(player)
                redraft(state, f"{player} entrou e os dois capitães aceitaram")
    elif action == "redraft_vote":  # teams closed: a whole team plus half of the other asks -> the captains draft again. Secret ballot.
        voter, ok = clean_name(body.get("voter")), bool(body.get("ok"))
        if not draft or len(draft["ok"]) < 2:
            raise ValueError("o voto abre quando os dois capitães fecham os times")
        if len(draft.get("ditador", [])) == 2:
            raise ValueError("Modo Ditador: os capitães fecharam os times")
        team = next((c for c in draft["captains"] if voter in draft["teams"][c]), None)
        if not team or voter in draft["captains"]:
            raise ValueError("só quem está num time, e não é capitão, vota")
        votes = draft.setdefault("votes", {})
        votes[voter] = ok
        for c in draft["captains"]:
            o = next(x for x in draft["captains"] if x != c)
            mine, others = [p for p in draft["teams"][c] if p != c], [p for p in draft["teams"][o] if p != o]
            if mine and all(votes.get(p) for p in mine) and 2 * sum(bool(votes.get(p)) for p in others) >= len(others):
                redraft(state, f"o Time {c} inteiro e metade do Time {o} pediram")
                break
    elif action == "draft_ditador":  # both captains: the teams are final, no redraft vote
        cap, on = clean_name(body.get("captain")), bool(body.get("on", True))
        if not draft or cap not in draft["captains"]:
            raise ValueError("capitão inválido")
        dit = draft.setdefault("ditador", [])
        if on and cap not in dit:
            dit.append(cap)
        if not on and cap in dit:
            dit.remove(cap)
        if len(dit) == 2:
            draft["votes"] = {}
    elif action == "bet":
        if not draft or len(draft["ok"]) < 2:
            raise ValueError("apostas abrem quando os dois capitães confirmam os times")
        bettor, pick, stake = clean_name(body.get("bettor")), body.get("pick"), body.get("stake")
        if pick not in PICKS or type(stake) is not int or stake <= 0:
            raise ValueError("escolha A, E ou B e um valor inteiro positivo")
        if balance(state, base, bettor) < stake:
            raise ValueError(f"{bettor} tem {balance(state, base, bettor)} moedas")
        a, b = (draft["teams"][c] for c in draft["captains"])
        bid = state["next_bet"]
        mt["bets"].append({"id": bid, "bettor": bettor, "pick": pick, "stake": stake, "odds": offered(data["model"], a, b)[pick]})
        state["ledger"].append({"player": bettor, "amount": -stake, "reason": f"aposta {bid}"})
        state["next_bet"] += 1
    elif action == "close_match":
        if not draft or len(draft["ok"]) < 2 or not re.fullmatch(r"\d{4}-\d\d-\d\d", mt["date"]):
            raise ValueError("precisa de data e dos times confirmados")
        score = body.get("score")
        if not (type(score) is list and len(score) == 2 and all(type(x) is int and 0 <= x < 100 for x in score)):
            raise ValueError("placar inválido")
        stats = body.get("stats") or {}
        res = "A" if score[0] > score[1] else "B" if score[0] < score[1] else "E"
        game = {"n": 1001 + len(state["played"]), "season": season_of(mt["date"]), "date": mt["date"], "teams": []}
        for i, cap in enumerate(draft["captains"]):
            players = []
            for p in draft["teams"][cap]:
                raw = stats.get(p) if type(stats.get(p)) is list else [0, 0]
                gl, ast = (v if type(v) is int and 0 <= v < 50 else 0 for v in (raw + [0, 0])[:2])
                players.append([p, gl, ast, 0, int(p == cap)])  # G/A coins come via base_of(), not the ledger
                state["ledger"].append({"player": p, "amount": PLAY, "reason": f"jogou {mt['date']}"})
            gf, ga = score[i], score[1 - i]
            game["teams"].append({"name": f"Time {cap}", "gf": gf, "ga": ga,
                                  "res": "V" if gf > ga else "D" if gf < ga else "E", "players": players})
        for bet in mt["bets"]:
            bet["payout"] = int(bet["stake"] * bet["odds"]) if bet["pick"] == res else 0
            if bet["payout"]:
                state["ledger"].append({"player": bet["bettor"], "amount": bet["payout"], "reason": f"aposta {bet['id']} ganha"})
        state["casa"] = state.get("casa", 0) + take(sum(b["stake"] for b in mt["bets"]))
        game["bets"] = mt["bets"]
        state["played"].append(game)
        keep(state)
        state["match"] = new_match()
    elif action == "new_match":
        keep(state)
        if mt["bets"]:  # the BioBet history keeps them
            state.setdefault("cancelados", []).append({"date": mt["date"], "at": int(time.time()), "bets": mt["bets"]})
        for bet in mt["bets"]:  # abandoned match: give the stakes back
            state["ledger"].append({"player": bet["bettor"], "amount": bet["stake"], "reason": "jogo cancelado"})
        state["match"] = new_match(str(body.get("date", ""))[:10])
    else:
        raise ValueError("ação desconhecida")
    return state


# --- BioBet mercados: bets a member opens on a BioFut event; the losing side's coins go to the winning side -----------

KICKOFF = "18:30"  # what most list headers say; a list with its own time sets lista["hora"]
CLOSE_H = 24  # a mercado takes bets until this many hours before kickoff: later the group already knows
GRACE = 7 * 86400  # a game still missing from the tabela this long after its kickoff did not happen
SIDES = ("sim", "não")


def kickoff(date, hora=""):
    """'2026-10-15', '18:30' -> that moment in Brasília (UTC-3), epoch seconds."""
    return calendar.timegm(time.strptime(f"{date} {hora or KICKOFF}", "%Y-%m-%d %H:%M")) + 3 * 3600


def keep(state):
    """The match leaves (closed or replaced): what its mercados still need stays a few weeks."""
    mt = state["match"]
    if mt["date"]:
        f = state.setdefault("fechados", {})
        f[mt["date"]] = {"date": mt["date"], "confirmed": mt["confirmed"][:], "caps_at": mt.get("caps_at")}
        for d in sorted(f)[:-8]:
            del f[d]


def snap(state, date):
    """The match of that date: the live one, or what keep() saved of it."""
    mt = state["match"]
    return mt if mt["date"] == date else state.get("fechados", {}).get(date, {})


def mercado_text(m):
    d = "/".join(m["date"].split("-")[:0:-1])
    return {"jogo": f"O jogo de {d} vai acontecer", "lista": f"{m.get('p')} vai entrar na lista do jogo de {d}",
            "capitao": f"Os capitães do jogo de {d} saem até {m.get('h')} h antes do jogo",
            "jogadores": f"O jogo de {d} vai ter {m.get('n')} jogadores ou mais"}[m["kind"]]


def new_mercado(state, kind, by, body=None, now=None):
    """A mercado on this week's game -> it. kind: jogo, lista (body p: who), capitao (h: 24, 12 or 6), jogadores (n).
    Gab's rules: nobody opens one on their own name; who is in the list stays out of jogadores (bet_mercado)."""
    body, now, mt = body or {}, now or time.time(), state["match"]
    if not mt["date"]:
        raise ValueError("sem jogo marcado: as apostas abrem com a lista")
    m = {"id": len(state.setdefault("mercados", [])) + 1, "kind": kind, "date": mt["date"], "by": by, "at": int(now),
         "kick": kickoff(mt["date"], (mt.get("lista") or {}).get("hora")), "min": body.get("min", 1), "bets": [], "status": "aberta"}
    if kind == "lista":
        m["p"] = clean_name(body.get("p"))
        if m["p"] == by:
            raise ValueError("você não pode abrir uma aposta com o seu nome")
        if m["p"] in mt["confirmed"]:
            raise ValueError(f"{m['p']} já está na lista")
    elif kind == "capitao":
        m["h"] = body.get("h")
        if m["h"] not in (24, 12, 6):
            raise ValueError("prazo dos capitães: 24, 12 ou 6 h antes do jogo")
        if mt.get("caps_at"):
            raise ValueError("os capitães já saíram")
    elif kind == "jogadores":
        m["n"] = body.get("n")
        if type(m["n"]) is not int or not 2 <= m["n"] <= 40:
            raise ValueError("número de jogadores entre 2 e 40")
    elif kind != "jogo":
        raise ValueError("tipo de aposta desconhecido")
    if type(m["min"]) is not int or m["min"] < 1:
        raise ValueError("o mínimo para entrar é um número inteiro de moedas, 1 ou mais")
    m["fecha"], m["text"] = m["kick"] - CLOSE_H * 3600, mercado_text(m)
    if now >= m["fecha"]:
        raise ValueError(f"as apostas fecham {CLOSE_H} h antes do jogo")
    if any(x["text"] == m["text"] and x["status"] != "anulada" for x in state["mercados"]):
        raise ValueError("essa aposta já existe: entre nela")
    state["mercados"].append(m)
    return m


def bet_mercado(state, base, user, mid, side, stake, now=None):
    """user joins mercado mid on one side; the stake leaves the wallet now, like a game bet."""
    now = now or time.time()
    m = next((x for x in state.get("mercados", []) if x["id"] == mid), None)
    if not m or m["status"] != "aberta" or now >= m["fecha"]:
        raise ValueError("essa aposta já fechou")
    if side not in SIDES or type(stake) is not int or stake < m["min"]:
        raise ValueError(f"escolha sim ou não e aposte {m['min']} moedas ou mais")
    if any(b["who"] == user for b in m["bets"]):
        raise ValueError("você já está nessa aposta")
    if user == m.get("p"):
        raise ValueError("a aposta é sobre você: fica de fora")
    if m["kind"] == "jogadores" and user in snap(state, m["date"]).get("confirmed", []):
        raise ValueError("quem está na lista não aposta no número de jogadores")
    if balance(state, base, user) < stake:
        raise ValueError(f"você tem {balance(state, base, user)} moedas")
    tot = sum(b["stake"] for b in m["bets"]) + stake
    on = sum(b["stake"] for b in m["bets"] if b["side"] == side) + stake
    m["bets"].append({"who": user, "side": side, "stake": stake, "at": int(now),  # the pot's odds as they bet; it pays the final ones
                      "odds": round(tot * (1 - HOUSE) / on, 2) if tot > on else None})
    state["ledger"].append({"player": user, "amount": -stake, "reason": f"mercado {mid}"})


def pay(state, m, out, now, by="BioBet"):
    """Decides mercado m (out: sim, não or anular). One pot: the house takes its 4.2% (never more than the losers put in,
    so a winner never loses coins) and the rest of the losing side's coins go to the winners by stake, largest remainder
    first, so no other coin is lost. Nobody on one side, or anular: every stake goes back. -> the notice, or None."""
    win = [b for b in m["bets"] if b["side"] == out]
    tot, w = sum(b["stake"] for b in m["bets"]), sum(b["stake"] for b in win)
    back = out not in SIDES or not win or w == tot
    m["casa"] = 0 if back else min(take(tot), tot - w)
    pot = tot - w - m["casa"]
    state["casa"] = state.get("casa", 0) + m["casa"]
    for b in m["bets"]:
        b["pay"] = b["stake"] if back else 0
    if not back:
        cut = [pot * b["stake"] // w for b in win]
        for i in sorted(range(len(win)), key=lambda i: -(pot * win[i]["stake"] % w))[:pot - sum(cut)]:
            cut[i] += 1
        for b, c in zip(win, cut):
            b["pay"] = b["stake"] + c
    for b in m["bets"]:
        if b["pay"]:
            state["ledger"].append({"player": b["who"], "amount": b["pay"], "reason": f"mercado {m['id']} {'devolvido' if back else 'ganho'}"})
    m.update(status=out if out in SIDES else "anulada", done=int(now), end_by=by, back=back)
    if not m["bets"]:
        return None
    head = f"🎲 Aposta #{m['id']}: {m['text']}? "
    if out not in SIDES:
        return head + f"Anulada por {by}, as moedas voltaram."
    return head + out.upper() + (": ninguém do outro lado, as moedas voltaram." if back else
                                 f": {', '.join(b['who'] for b in win)} {'leva' if len(win) == 1 else 'levam'} {pot} moedas"
                                 + (f", a casa {m['casa']}." if m["casa"] else "."))


def settle(state, now=None):
    """Decides the open mercados whose answer is known -> one entry per decided mercado (its notice or None).
    jogo: sim once the game is in the tabela, não once a later game is (or GRACE passed). lista, jogadores: the list
    at kickoff. capitao: sim if the teams came out (site draft, or a list with times) by the deadline."""
    now = now or time.time()
    games = {g["date"] for g in DATA["games"] + state["played"] if g.get("date")}
    out = []
    for m in state.get("mercados", []):
        if m["status"] != "aberta":
            continue
        s, d, r = snap(state, m["date"]), m["date"], None
        if m["kind"] == "jogo":
            r = "sim" if d in games else "não" if max(games, default="") > d or now > m["kick"] + GRACE else None
        elif m["kind"] == "capitao":
            t, c = m["kick"] - m["h"] * 3600, s.get("caps_at")
            r = "sim" if c and c <= t else "não" if now >= t else None
        elif now >= m["kick"]:
            names = s.get("confirmed", [])
            r = SIDES[not (m["p"] in names if m["kind"] == "lista" else len(names) >= m["n"])]
        if r:
            out.append(pay(state, m, r, now))
    return out


MIN_PLAYERS = 10  # the smallest game in the tabela had 12: fewer than this at kickoff + 2 h = it did not happen


def cancel_match(st, why, now=None):
    """The game of the week is off: its bets go back (history keeps them), its mercado "jogo" pays "não". -> notice."""
    now, mt = now or time.time(), st["match"]
    date, n = mt["date"], len(mt["bets"])
    out = [pay(st, m, "não", now) for m in st.get("mercados", []) if m["kind"] == "jogo" and m["date"] == date and m["status"] == "aberta"]
    apply(st, "new_match", {})
    back = f"{n} aposta{'s' if n != 1 else ''} do draft devolvida{'s' if n != 1 else ''}. " if n else ""
    return f"❌ Jogo de {date[8:10]}/{date[5:7]} cancelado ({why}). " + back + " ".join(o for o in out if o)


def mercado_tick(now=None):
    """Every minute: decide what is known, and open the game's own mercado once its list is out -> the notices."""
    now = now or time.time()
    with LOCK:
        st = load_state()
        notes, mt = settle(st, now), st["match"]
        if mt["date"] and now > kickoff(mt["date"], (mt.get("lista") or {}).get("hora", "")) + 2 * 3600 and len(mt["confirmed"]) < MIN_PLAYERS:
            notes.append(cancel_match(st, f"só {len(mt['confirmed'])} na lista", now))
            mt = st["match"]
        if mt["date"] and not any(m["kind"] == "jogo" and m["date"] == mt["date"] for m in st.get("mercados", [])):
            try:
                m = new_mercado(st, "jogo", "BioBet", now=now)
                notes.append(f"🎲 Lista aberta, aposta aberta: {m['text']}? Sim ou não na BioBet, até {CLOSE_H} h antes do jogo. "
                             "https://biofut.h-brain.org/#/biobet")
            except ValueError:
                pass  # less than CLOSE_H before the game: no mercado this week
        if notes:
            save_state(st)
    return [n for n in notes if n]


def mercado_act(st, action, body, user, role, now=None):
    """POST mercado (open one with your own bet in it), mercado_bet (join one), mercado_fim (the Gab or the Conselho
    decide or void one; its opener voids it while alone in it) -> the notice for the group, or None."""
    if not user:
        raise ValueError("entre para apostar")
    base = base_of(st, DATA)
    if action == "mercado":
        m = new_mercado(st, str(body.get("kind")), user, body, now)
        bet_mercado(st, base, user, m["id"], body.get("side"), body.get("stake"), now)
        return f"🎲 {user} abriu uma aposta na BioBet: {m['text']}? Entra com {m['min']} moedas ou mais. https://biofut.h-brain.org/#/biobet"
    if action == "mercado_bet":
        return bet_mercado(st, base, user, body.get("id"), body.get("side"), body.get("stake"), now)
    m, out = next((x for x in st.get("mercados", []) if x["id"] == body.get("id")), None), body.get("out")
    if not m or m["status"] != "aberta" or out not in (*SIDES, "anular"):
        raise ValueError("aposta ou resultado inválido")
    if role not in ("admin", "conselho") and (out != "anular" or m["by"] != user or any(b["who"] != user for b in m["bets"])):
        raise ValueError("quem decide é o Gab ou o Conselho; quem abriu anula enquanto estiver sozinho nela")
    if out != "anular" and any(b["who"] == user for b in m["bets"]):
        raise ValueError("você está nessa aposta: outra pessoa do Conselho decide")
    return pay(st, m, out, now or time.time(), user)


def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE)  # atomic: a crash mid-write never eats the season


def load_state():
    if not STATE.exists():
        return new_state()
    st = json.loads(STATE.read_text(encoding="utf-8"))
    if "match" not in st:  # pre-2026-10-05 shape: just the match
        st = {**new_state(), "match": {**new_match(), **st}}
    return st


def base_of(st, data):
    return minted(data["games"] + unsynced(st["played"], data["games"]))


def public_state(st):
    d = st["match"]["draft"]
    base = base_of(st, DATA)
    out = {k: v for k, v in st.items() if k not in ("ledger", "owners", "cromo", "fechados", "duelo_aberto", "truco_aberto", "tour", "tour_truco")}  # owners hold phone_pk
    out["cromadas"] = {c: {"by": p, "stat": st.get("cromo", {}).get(c, "")} for c, p in first_buyers(st).items()}
    out["profiles"] = load_profiles()
    out["photos"] = sorted(p.stem for p in PHOTOS.glob("*.jpg")) if PHOTOS.exists() else []
    out["balances"] = {p: balance(st, base, p) for p in set(base) | {x["player"] for x in st["ledger"]} | set(st.get("duelo", {}))}
    out["prices"] = card_prices(DATA["games"] + unsynced(st["played"], DATA["games"]))
    out["alias"], out["quem"] = name_fixes()
    if d:
        out["match"] = {**st["match"], "draft": {**d, "flip": sorted(d.get("flip", {})), "votes": len(d.get("votes", {}))}}
        out["odds"] = offered(DATA["model"], *(d["teams"][c] for c in d["captains"]))
    return out


def jpeg(data_url):
    head = "data:image/jpeg;base64,"
    if not data_url.startswith(head):
        raise ValueError("foto deve ser JPEG")
    raw = base64.b64decode(data_url[len(head):], validate=True)
    if len(raw) > MAX_PHOTO or raw[:2] != b"\xff\xd8":
        raise ValueError("foto inválida ou grande demais")
    return raw


def save_photo(name, data_url):
    PHOTOS.mkdir(parents=True, exist_ok=True)
    (PHOTOS / f"{slug(name)}.jpg").write_bytes(jpeg(data_url))


# --- review queue: pipelines propose, Gab approves / edits / rejects, 6 h later it ships anyway ---------

def bot_post(route, obj):
    """POST to the bot's webhook (BOT_URL's host, any route) -> its JSON answer, or None. No-op without BOT_URL. Never raises."""
    if not BOT_URL:
        return None
    try:
        req = urllib.request.Request(BOT_URL.rsplit("/", 1)[0] + route, json.dumps(obj).encode(), {
            "Content-Type": "application/json", "X-BioFut-Token": os.environ.get("BIOFUT_BOT_TOKEN", "")})
        return json.loads(urllib.request.urlopen(req, timeout=10).read())
    except urllib.error.HTTPError as e:  # the bot says why (e.g. 404: not in the group)
        try:
            return json.loads(e.read())
        except ValueError:
            pass
    except Exception as e:
        print(f"bot {route} failed:", e, flush=True)
    return None


def notify(text, post=True):
    """Log it, and post it to the BioFut Avisos group when the bot is configured (post=False: the log only). Never raises."""
    AVISOS.parent.mkdir(exist_ok=True)
    with AVISOS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "text": text}, ensure_ascii=False) + "\n")
    if post:
        bot_post("/notify", {"text": text})


def join_ping(st, before, user=None):
    """A new name on the list -> the bot tells the draft captains (or all known captains before the draft). The member
    themself (user == the name) -> the bot also posts it in the group, then the list with the name, to copy-paste.
    -> True when the group got it."""
    mt = st["match"]
    if heads(mt) <= before:
        return False
    d = mt["draft"]
    pend = list((d or {}).get("pending", {}))
    waiting = bool(d)  # with a draft running, a new name waits on the captains
    name = pend[-1] if waiting else mt["confirmed"][-1]
    threading.Thread(target=bot_post, daemon=True, args=("/draft/join", {
        "player": name, "count": len(mt["confirmed"]), "captains": d["captains"] if d else (mt.get("lista") or {}).get("captains", []), **({"pending": True} if waiting else {})})).start()
    if waiting or not user or user.lower() != name.lower():
        return False
    msgs = [f"🤖 {name} disse no site que tá dentro no jogo de {mt['date'][8:10]}/{mt['date'][5:7]}."]
    ll = st.get("last_list") or {}
    if ll.get("date") == mt["date"]:  # ponytail: the group's last list + one line; a rebuilt list if people stop copying it
        msgs.append(ll["text"].rstrip() + f"\n{len(mt['confirmed'])}. [{name} 🤖]")
    for text in msgs:
        bot_post("/group", {"text": text})
    return True


def pick_ping(st, cap):
    """A site draft pick -> the bot DMs the other captain the board: teams so far, who is still free, whose turn."""
    mt, d = st["match"], st["match"]["draft"]
    taken = {p for t in d["teams"].values() for p in t}
    threading.Thread(target=bot_post, daemon=True, args=("/draft/pick", {
        "captain": cap, "player": d["teams"][cap][-1], "turn": snake_turn(d), "teams": d["teams"],
        "available": [p for p in mt["confirmed"] if p not in taken]})).start()
    left = len(mt["confirmed"]) - len(taken)
    group_post(f"{cap} escolheu {d['teams'][cap][-1]}. " + (f"Vez de {snake_turn(d)}. Sobram {left}." if left else "Acabou! Capitães, confirmem os times."))


def group_post(text):
    """The site tells the BioFut group; the 🤖 makes the bot tag it. Never blocks the request."""
    threading.Thread(target=bot_post, daemon=True, args=("/group", {"text": "🤖 " + text})).start()


def draft_news(st, action, d0):
    """What the group hears after a draft action (d0: the draft before it). -> text or None."""
    mt, d = st["match"], st["match"]["draft"]
    url = f"{SITE}/#/jogo"
    if action == "draft_start":
        return f"Draft começou! Capitães: {d['captains'][0]} x {d['captains'][1]}. Acompanha ao vivo: {url}"
    if action == "draft_flip" and d.get("first") and not (d0 or {}).get("first"):
        c = d.get("coin")
        return (f"Moeda no ar... deu {c['result']}! {d['first']} escolhe primeiro." if c else f"Capitães combinaram: {d['first']} escolhe primeiro.") + f" {url}"
    if action == "draft_confirm" and len(d["ok"]) == 2 and len((d0 or {}).get("ok", [])) < 2:
        o = offered(DATA["model"], *(d["teams"][c] for c in d["captains"]))
        inv = {k: 1 / v for k, v in o.items()}
        pct = {k: round(100 * v / sum(inv.values())) for k, v in inv.items()}
        teams = "\n".join(f"Time {c}: {', '.join(d['teams'][c])}" for c in d["captains"])
        return f"Times fechados!\n{teams}\n\nBioBet: {d['captains'][0]} {pct['A']}% · empate {pct['E']}% · {d['captains'][1]} {pct['B']}%. Apostas abertas: {url}"
    if (why := d.pop("redraft", None)):
        return f"🔁 Redraft: {why}. Capitães, de novo: {url}"
    if action == "draft_ditador" and len(d.get("ditador", [])) == 2:
        return f"👑 Modo Ditador: os dois capitães fecharam os times. Sem redraft."
    return None


def match_news(game):
    """The group hears the final score once the site closes the game."""
    a, b = game["teams"]
    goals = sorted(((p[0], p[1]) for t in game["teams"] for p in t["players"] if p[1]), key=lambda x: -x[1])
    g = ", ".join(f"{n} {k}" for n, k in goals)
    bets = [x for x in game.get("bets", []) if x.get("payout")]
    return f"Fim de jogo: {a['name']} {a['gf']} × {b['gf']} {b['name']}." + (f" Gols: {g}." if g else "") + \
        (f" BioBet pagou {len(bets)} aposta{'s' * (len(bets) != 1)}." if game.get("bets") else "")


def my_messages(name, _cache={}):
    """#/eu: a member's own messages in the group, oldest first, spellings merged since the phones.py build included."""
    if not MSGS.exists():
        return []
    t = MSGS.stat().st_mtime
    if _cache.get("t") != t:
        _cache.update(t=t, all=json.loads(MSGS.read_text(encoding="utf-8")))  # ponytail: ~10 MB held in memory, fine on the A1
    alias = name_fixes()[0]
    return sorted(m for k, v in _cache["all"].items() if alias.get(k, k) == name for m in v)


def wa_check(poster, wa, roster):
    """The number map's name vs the poster's own WhatsApp name -> a warning when the WhatsApp name points at another
    tabela player (a stale phones.json named Leo Saul's number "Victor"), else None. Only a hint: anyone picks their
    WhatsApp name, so it never overrides the map."""
    alias = name_fixes()[0]
    n = sumula.canon(wa, roster) if wa and not poster.startswith("~") else ""
    return f"o número diz {poster}, o WhatsApp diz {wa} ({n})" if n in roster and alias.get(n, n) != alias.get(poster, poster) else None


def sync_list(st, text, ts, poster, pk="", wa=""):
    """A sign-up list posted in the group -> Jogo da semana. Its names join the confirmed list as the tabela spells them,
    names taken off it leave (unless drafted or bet on), names that signed up on the site stay. A list for a later date
    starts that match once this one's day has come (and, on the day itself, no draft is open), or at once when this one has
    no draft and no bets (rescheduled: its site sign-ups are dropped, they were for another date). Nobody is pinged: they
    are all in the group. The list belongs to whoever posted its first copy (pk: phone_pk of their number, wa: their
    WhatsApp name). -> what changed, or None."""
    seen = st["last_list"] = {"text": text[:2000], "at": int(ts), "by": poster, "date": None, "why": "não é uma lista"}  # what the bot sent last, shown on Jogo da semana
    if check := wa_check(poster, wa, sumula.roster_of(DATA["games"], "")):
        seen["check"] = check
    lst = lista.parse_list(text, ts)
    if not lst:
        return None
    seen["date"] = lst["date"]
    owners = st.setdefault("owners", {})
    o = owners.setdefault(lst["date"], [poster, pk])
    if isinstance(o, str):  # saved before 2026-10-10 as a bare name
        o = owners[lst["date"]] = [o, ""]
    if pk and o[1] == pk:
        o[0] = poster  # the opener posts again: their name as today's number map has it, so a fixed phones.json heals it
    for d in sorted(owners)[:-8]:
        del owners[d]  # a few weeks of who opened which list is plenty
    mt, today = st["match"], time.strftime("%Y-%m-%d", time.gmtime(ts - 3 * 3600))  # the group's day (Brasília, see log_event)
    if lst["date"] < mt["date"] or lst["date"] > mt["date"] and mt["date"] and (mt["draft"] or mt["bets"]) and (mt["date"] > today or mt["date"] == today and mt["draft"]):  # no draft and no bets yet: the game moved (list reset, new date), so the new list replaces it
        seen["why"] = "lista de um jogo antigo" if lst["date"] < mt["date"] else f"próximo jogo: espera o de {mt['date']}"
        return None  # an old list reposted, or next week's list before this week's game
    if lst["date"] != mt["date"]:
        if mt["date"]:
            apply(st, "new_match", {"date": lst["date"]})  # bets on a game nobody closed here go back
        mt = st["match"]
        mt["date"] = lst["date"]
    recent, alias, names, caps = sumula.roster_of(DATA["games"]), name_fixes()[0], [], []
    roster = recent + [n for n in sumula.roster_of(DATA["games"], "") if n not in recent]  # then old-timers coming back
    k = len(lst["goalies"]) + len(lst["players"])
    for i, e in enumerate(lst["goalies"] + lst["players"] + [e for t in lst["teams"] for e in t["players"]]):  # 'Time MK': its players are in
        n = sumula.canon(e["name"], mt["confirmed"])  # someone already in (signed up on the site as "Leo Saul": "Saul")
        if n not in mt["confirmed"]:
            n = sumula.canon(e["name"], roster)
            n = alias.get(n, n)
        if i >= k and n in names:  # the teams repeat the numbered list's names
            caps += [n] * e["captain"]
            continue
        names.append(e["name"] if n in names else n)  # two list names on one tabela name: the second stays as written
        if e["captain"]:
            caps.append(names[-1])  # 'Fulano (C)': the players pick the captains on the list, close to the game (Gab)
    names = list(dict.fromkeys(names))
    prev = (mt.get("lista") or {}).get("names", [])
    gone = [n for n in prev if n not in names]
    reset = len(gone) if len(gone) > lista.RESET else 0
    if reset:  # a reset or a truncated copy: nobody leaves, the full list comes back on the next repost
        names, gone = prev + [n for n in names if n not in prev], []
    drafted = {p for t in (mt["draft"] or {"teams": {}})["teams"].values() for p in t}
    removed = [] if mt["bets"] else [n for n in gone if n in mt["confirmed"] and n not in drafted]
    have = {c.lower() for c in mt["confirmed"]}
    added = [n for n in names if n.lower() not in have]
    mt["confirmed"] = [c for c in mt["confirmed"] if c not in removed] + added
    mt["lista"] = {"owner": o[0], "by": poster, "at": int(ts), "names": names, "hora": lst["hora"],
                   "waiting": [e["name"] for e in lst["waiting"]], "captains": list(dict.fromkeys(caps))}
    if lst["teams"]:
        mt.setdefault("caps_at", int(ts))  # the teams are out, so the captains are (BioBet capitao)
    seen["why"] = f"aplicada: +{len(added)} -{len(removed)}" + (f", ninguém saiu ({reset} nomes sumiram: lista cortada?)" if reset else "")
    return {"date": lst["date"], "added": added, "removed": removed}


def load_profiles():
    return json.loads(PROFILES.read_text(encoding="utf-8")) if PROFILES.exists() else {}


def set_profile(user, body):
    """Only the logged-in name's own entry; fields sent replace the old ones, empty ones drop out."""
    p = {k: re.sub(r"\s+", " ", str(body.get(k) or "")).strip()[:n] for k, n in (("nick", 30), ("status", 80)) if k in body}
    if "hide" in body:
        p["hide"] = bool(body["hide"])
    with LOCK:
        profs = load_profiles()
        profs[user] = {k: v for k, v in {**profs.get(user, {}), **p}.items() if v}
        if not profs[user]:
            del profs[user]
        write_json(PROFILES, profs, 1)
    return profs.get(user, {})


def read_jsonl(f):
    return [json.loads(l) for l in f.open(encoding="utf-8")] if f.exists() else []


def fila(items, now=None):
    """Súmulas read by OCR for the tabela page: pending ones (and when they go in alone) plus the last few decided. No photo."""
    now = now or time.time()
    out = []
    for it in items[::-1]:
        if it["kind"] != "sumula" or it["status"] != "pending" and now - it["created"] > 7 * 86400:
            continue
        p = it.get("payload", {})
        games = [{"teams": [{"name": g.get(f"team_{x}"), "gf": g.get(f"score_{x}"),
                             "players": [[q.get("name"), q.get("goals") or 0, q.get("assists") or 0] for q in g.get(f"players_{x}", [])]}
                            for x in "ab"]} for g in p.get("games", [])]
        out.append({"id": it["id"], "title": it["title"], "status": it["status"], "date": p.get("date"),
                    "release": None if held(it) else it["created"] + COOLDOWN, "games": games})
    return out[:10]


def load_review():
    return json.loads(REVIEW.read_text(encoding="utf-8")) if REVIEW.exists() else []


def write_json(path, obj, indent=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=indent), encoding="utf-8")
    tmp.replace(path)


_public_media = (None, set())


def public_media():
    """Photos the public wiki shows (public.json "media": nobody in them), cached until wiki.py or a deploy rewrites the file."""
    global _public_media
    f = WIKI / "public.json"
    t = f.stat().st_mtime if f.exists() else None
    if t != _public_media[0]:
        _public_media = (t, set(json.loads(f.read_text(encoding="utf-8")).get("media", [])) if t else set())
    return _public_media[1]


def wiki_bytes(f, member, _cache={}):
    """/api/wiki: (json, gzipped json) of that file with the leads in, rebuilt when either file changes. member.json is
    1.5 MB: parsing it per request and sending it raw was what made the wiki slow on a phone."""
    key = (f.name, f.stat().st_mtime, LEADS.stat().st_mtime if LEADS.exists() else 0)
    if _cache.get("key") != key:
        raw = json.dumps(with_leads(json.loads(f.read_bytes()), member), ensure_ascii=False).encode() if LEADS.exists() else f.read_bytes()
        _cache.update(key=key, val=(raw, gzip.compress(raw, 6)))
    return _cache["val"]


def with_leads(d, member):
    """Main photos staff approved (kind foto) go first on their page, so they survive a wiki rebuild. The public only gets public media."""
    leads = json.loads(LEADS.read_text(encoding="utf-8"))
    for p in d["pages"]:
        f, ps = leads.get(p["slug"]), p.get("photos") or []
        if f and (member or f in public_media()):
            p["photos"] = [next((x for x in ps if x["file"] == f), {"file": f, "legenda": ""})] + [x for x in ps if x["file"] != f]
    return d


def fid(row):  # a wiki report's id, for the votes: rows written before ids existed get the same one
    return hashlib.sha1(f"{row['ts']}|{row['user']}|{row['text']}".encode()).hexdigest()[:10]


def file_issues(post=None):
    """Open a GitHub issue for every idea that has none yet (new ones, old ones, earlier failures). Never raises."""
    if not GITHUB_TOKEN or not ISSUE_LOCK.acquire(blocking=False):
        return  # ponytail: a sweep already running misses this row; the next POST or restart files it
    try:
        done = json.loads(ISSUES.read_text(encoding="utf-8")) if ISSUES.exists() else {}
        for r in read_jsonl(FEEDBACK):
            if fid(r) in done:
                continue
            body = {"title": f"[{r['kind']}] {r['text'][:70]}", "body": f"{r['text']}\n\nDe {r['user']} no site, {r['ts']}.", "labels": [r["kind"]]}
            try:
                url = json.loads((post or gh_post)(f"/repos/{REPO}/issues", body))["html_url"]
            except Exception as e:  # down, rate-limited, bad token: try again on the next idea or restart
                print("issue:", e)
                return
            done[fid(r)] = url
            ISSUES.write_text(json.dumps(done, indent=1), encoding="utf-8")
    finally:
        ISSUE_LOCK.release()


def gh_post(route, obj):
    req = urllib.request.Request("https://api.github.com" + route, json.dumps(obj).encode(), {
        "Authorization": "Bearer " + GITHUB_TOKEN, "Accept": "application/vnd.github+json", "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=20).read()


def load_votes():
    return json.loads(VOTES.read_text(encoding="utf-8")) if VOTES.exists() else {}


def retry_list(st, now=None):
    """A list that waited for this week's game ("próximo jogo: espera...") is read again once nothing holds it (the day
    came, the bets went back, a deploy changed the rule), without anyone reposting it. -> what changed, or None."""
    seen = st.get("last_list") or {}
    if not str(seen.get("why", "")).startswith("próximo jogo"):
        return None
    at, now = seen["at"], max(now or time.time(), seen["at"])
    out = sync_list(st, seen["text"], now, seen["by"])
    st["last_list"]["at"] = at  # still the bot's message time, not ours
    return out


def hide_names(listas, hidden):
    """Transparência opt-out: the numbers stay, the name goes (None; the page says why on hover)."""
    h = lambda n: None if n in hidden else n
    listas["people"] = [{**p, "name": h(p["name"])} for p in listas.get("people", [])]
    listas["trophies"] = {t: [{**x, "name": h(x["name"])} for x in xs] for t, xs in listas.get("trophies", {}).items()}
    for g in listas.get("games", []):
        if "eventos" in g:
            g["eventos"] = [[t, h(n), op] for t, n, op in g["eventos"]]
    return listas


def apply_wiki(payload, member, public):
    """Bits in and out per page, on both site files. Bits no page uses are dropped, so the wiki stays capped."""
    for d in (member, public):
        bits = d.setdefault("bits", {})
        for i, b in payload.get("bits", {}).items():
            bits[i] = {k: v for k, v in b.items() if not (d is public and k == "ref")}  # refs point into the chat: members only
        pages = {p["slug"]: p for p in d["pages"]}
        for op in payload.get("ops", []):
            if op["page"] in pages:
                pages[op["page"]]["bits"] = [i for i in op["order"] if i in bits]
        used = {i for p in d["pages"] for i in p.get("bits", [])}
        d["bits"] = {i: b for i, b in bits.items() if i in used}
    member.setdefault("chats", {}).update(payload.get("chats", {}))


def sumula_games(payload, n0):
    """OCR'd match sheet {date, games: [{team_a, score_a, players_a: [{name, goals, assists, own_goals}], ...}]} -> site games."""
    if not re.fullmatch(r"\d{4}-\d\d-\d\d", str(payload.get("date"))):
        raise ValueError("súmula sem data")
    out = []
    for i, g in enumerate(payload["games"]):
        sa, sb = int(g["score_a"]), int(g["score_b"])
        teams = []
        for side, gf, ga in (("a", sa, sb), ("b", sb, sa)):
            ps = [[clean_name(p["name"]), int(p.get("goals") or 0), int(p.get("assists") or 0), int(p.get("own_goals") or 0),
                   int(bool(p.get("captain")))]
                  for p in g[f"players_{side}"]]
            teams.append({"name": str(g[f"team_{side}"])[:40], "gf": gf, "ga": ga,
                          "res": "V" if gf > ga else "D" if gf < ga else "E", "players": ps})
        out.append({"n": n0 + i, "season": season_of(payload["date"]), "date": payload["date"], "teams": teams, "source": "súmula"})
    return out


def night_photos():
    f = WIKI / "jogos.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def held(item):
    """A súmula without a single goal is a lineup photo or tallies the OCR missed (a 0 x 0 went in alone on 9 Oct 2026):
    it never ships on its own, someone has to approve, edit or reject it. Same for a new photo of someone (kind foto) and a report
    that a game is wrong (kind jogo: approving only marks it checked, the fix goes into the sheet)."""
    return item["kind"] in ("foto", "jogo") or item["kind"] == "sumula" and not any(g.get("score_a") or g.get("score_b") for g in item["payload"].get("games", []))


def new_note(item):
    if held(item):
        return f"🆕 #{item['id']} {item['title']}. {'Sem nenhum gol: f' if item['kind'] == 'sumula' else 'F'}ica parada até alguém aprovar, editar ou rejeitar: https://biofut.h-brain.org/admin"
    at = time.strftime('%H:%M', time.localtime(item["created"] + COOLDOWN))
    return (f"🆕 #{item['id']} {item['title']}. Sai sozinho às {at} se ninguém aprovar, editar ou rejeitar: "
            "https://biofut.h-brain.org/admin")


def release(item, how):
    """Ship one item. Called with LOCK held."""
    if item["kind"] == "wiki":
        member, public = (json.loads((WIKI / f).read_text(encoding="utf-8")) for f in ("member.json", "public.json"))
        apply_wiki(item["payload"], member, public)
        write_json(WIKI / "member.json", member)
        write_json(WIKI / "public.json", public)
    elif item["kind"] == "sumula":
        st = load_state()
        games = sumula_games(item["payload"], 1001 + len(st["played"]))
        img = item["payload"].get("image")
        if img and (REVIEW_MEDIA / img).exists():  # #34: the open game shows the photo its score came from (members, /wiki/media)
            (WIKI / "media").mkdir(parents=True, exist_ok=True)
            (WIKI / "media" / img).write_bytes((REVIEW_MEDIA / img).read_bytes())
            for g in games:
                g["sumula"] = img
        st["played"] += games
        save_state(st)
        item["sheet"] = push_sheet(games) if sheet.ID else "só no site: copie para a planilha em https://biofut.h-brain.org/#/planilha"
    elif item["kind"] == "tabela":
        text = item["payload"]["csv"]
        use_games(sheet_games(text))
        SHEET_CACHE.parent.mkdir(exist_ok=True)
        SHEET_CACHE.write_text(text, encoding="utf-8")
        item["payload"] = {k: v for k, v in item["payload"].items() if k != "csv"}  # 430 KB each; the diff stays for the log
    elif item["kind"] == "listas":
        if not isinstance(item["payload"].get("people"), list):
            raise ValueError("listas sem people")
        write_json(LISTAS, item["payload"], 1)
    elif item["kind"] == "foto":  # {page, file, player}: the page's main photo, and the player's photo on the site
        p = item["payload"]
        f = WIKI / "media" / p["file"]
        if not re.fullmatch(r"[\w-]+\.jpg", p["file"]) or not f.exists():
            raise ValueError("foto sumiu")
        leads = json.loads(LEADS.read_text(encoding="utf-8")) if LEADS.exists() else {}
        write_json(LEADS, {**leads, p["page"]: p["file"]}, 1)
        if p.get("player"):
            PHOTOS.mkdir(parents=True, exist_ok=True)
            (PHOTOS / f"{slug(p['player'])}.jpg").write_bytes(f.read_bytes())
    item.update(status=how, decided=time.strftime("%Y-%m-%dT%H:%M:%S"))


def push_sheet(games):
    """Append released games to the group's sheet (sheet.py fills the next empty game rows). Never raises:
    the game is already on the site, so a failure is reported, not lost."""
    try:
        return f"ok: jogo {', '.join(map(str, sheet.push(games)))}"
    except Exception as e:
        notify(f"⚠️ súmula liberada no site, mas a planilha não foi atualizada: {e}")
        return f"falhou: {e}"


def ocr_photo(image, date, sender):
    """Bot -> here, in a thread: read the photo, queue it if it is a súmula. Every outcome goes to the log."""
    try:
        payload = sumula.read(image, sumula.roster_of(DATA["games"]), date, OCR_BUDGET)
    except Exception as e:
        print("ocr failed:", e, flush=True)
        if "repetida" not in str(e):
            notify(f"⚠️ OCR da foto de {sender} não rodou: {e}")
        return
    if not payload:
        return  # a meme, a selfie: nothing to review
    name = hashlib.sha256(image).hexdigest()[:16] + ".jpg"
    REVIEW_MEDIA.mkdir(parents=True, exist_ok=True)
    (REVIEW_MEDIA / name).write_bytes(image)
    payload["image"] = name
    write_json(INBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-{name[:8]}.json",
               {"kind": "sumula", "title": f"Súmula {payload['date']} (foto de {sender})", "payload": payload})


def review_tick(now=None):
    """Pick up new items from the inbox, release what waited COOLDOWN. Returns the notices to send."""
    now = now or time.time()
    notes = []
    with LOCK:
        items = load_review()
        for f in sorted(INBOX.glob("*.json")) if INBOX.exists() else []:
            try:
                new = json.loads(f.read_text(encoding="utf-8"))
                if new.get("kind") not in ("wiki", "sumula", "listas", "aviso", "foto", "jogo") or not isinstance(new.get("payload"), dict):
                    raise ValueError("tipo desconhecido")
                if new["kind"] == "aviso":  # a pipeline saying what it ran: nothing to release, straight to the group
                    notes.append(f"🤖 {str(new['payload'].get('text', ''))[:1500]}")
                else:
                    item = {"id": max([x["id"] for x in items] + [0]) + 1, "kind": new["kind"], "title": str(new.get("title", ""))[:200],
                            "created": now, "status": "pending", "payload": new["payload"]}
                    items.append(item)
                    notes.append(new_note(item))
            except Exception as e:
                notes.append(f"⚠️ item inválido na fila ({f.name}): {e}")
            f.unlink()
        for it in items:
            if it["status"] == "pending" and now - it["created"] >= COOLDOWN and not held(it):
                try:
                    release(it, "auto")
                    notes.append(f"⏱️ #{it['id']} {it['title']}: liberado sozinho depois de 6 h")
                except Exception as e:
                    it["status"] = "failed"
                    notes.append(f"❌ #{it['id']} falhou ao liberar: {e}")
        write_json(REVIEW, items, 1)
    return notes


def review_loop():
    while True:
        for tick in (review_tick, mercado_tick):
            try:
                for n in tick():
                    notify(n)
            except Exception as e:
                print(f"{tick.__name__} failed:", e, flush=True)
        time.sleep(60)


def review_act(item_id, action, payload=None, kinds=None, by=""):
    """A staff decision: approve (ship now), edit (new payload, ship now) or reject. kinds: what this person may decide (None: all)."""
    with LOCK:
        items = load_review()
        it = next((x for x in items if x["id"] == item_id), None)
        if not it or it["status"] != "pending":
            raise ValueError("item não está pendente")
        if kinds and it["kind"] not in kinds:
            raise ValueError("esse item é só para o Gab")
        if action == "reject":
            it.update(status="rejected", decided=time.strftime("%Y-%m-%dT%H:%M:%S"))
            it["payload"].pop("csv", None)  # the sha is enough to not propose this sheet again
        elif action in ("approve", "edit"):
            if action == "edit":
                if not isinstance(payload, dict):
                    raise ValueError("payload inválido")
                it["payload"], it["edited"] = payload, True
            try:
                release(it, "approved")
            except (KeyError, TypeError) as e:
                raise ValueError(f"payload inválido: {e}")
        else:
            raise ValueError("ação desconhecida")
        write_json(REVIEW, items, 1)
    verb = {"reject": "❌ rejeitado", "approve": "✅ aprovado", "edit": "✏️ editado e liberado"}[action]
    notify(f"{verb}{' por ' + by if by else ''}: #{it['id']} {it['title']}")
    return {k: v for k, v in it.items() if k != "payload"}


def visitor(ip, day=None):
    """Same IP on the same day -> same 8 hex chars. The IP itself is never written, and the id changes every day."""
    return hmac.new(KEY, f"{day or time.strftime('%Y-%m-%d')}|{ip}".encode(), hashlib.sha256).hexdigest()[:8]


def log_event(ev, user, ip, mobile=False, **extra):
    """One line in data/events.jsonl. Never raises: a full disk must not break a sign-up."""
    now = time.gmtime(time.time() - 3 * 3600)  # ponytail: Brasília time (no DST since 2019): the group's day, whatever the server's TZ
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", now), "ev": ev, "user": user, "vid": visitor(ip, time.strftime("%Y-%m-%d", now)),
           **({"mob": 1} if mobile else {}),
           **{k: v for k, v in extra.items() if v not in (None, "", {})}}
    try:
        EVENTS.parent.mkdir(exist_ok=True)
        if EVENTS.exists() and EVENTS.stat().st_size > 20_000_000:  # ponytail: keeps one old file; a real log store if 20 MB ever fills fast
            EVENTS.replace(EVENTS.with_suffix(".1.jsonl"))
        with EVENTS.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as e:
        print("event log failed:", e, flush=True)


def recent_events(n=5000):
    out = []
    for line in (EVENTS.read_text(encoding="utf-8").splitlines()[-n:] if EVENTS.exists() else []):
        try:
            out.append(json.loads(line))
        except ValueError:  # a line cut by a full disk
            pass
    return out


def log_view():
    """Transparency: what the automation did and who decided, without payloads."""
    return [{k: it.get(k) for k in ("id", "kind", "title", "created", "status", "decided", "edited")} for it in load_review()][::-1][:200]


# --- phone -> who you are (no numbers stored: salted PBKDF2 of the last 8 digits) --------------

def phone_key(phone, salt):
    digits = re.sub(r"\D", "", str(phone or ""))[-8:]  # last 8: with or without +55, area code and the extra 9 all agree
    if len(digits) < 8:
        return None
    return hashlib.pbkdf2_hmac("sha256", digits.encode(), bytes.fromhex(salt), 200_000).hex()


def load_phones():
    return json.loads(PHONES.read_text(encoding="utf-8")) if PHONES.exists() else {}


def phone_lookup(phone):
    """-> (name, how) or (None, None); how: nome / lista / frequencia / contato (see phones.py)."""
    t = load_phones()
    k = phone_key(phone, t["salt"]) if t else None
    return (t["map"].get(k), t.get("how", {}).get(k)) if k and k in t["map"] else (None, None)


def phone_name(phone):
    return phone_lookup(phone)[0]


def member_of(phone):
    """A WhatsApp number -> its tabela name or None: phones.json's "me" for BIOFUT_ADMIN_PHONE (Gab: his export has no
    number of his), else phones.py's, else a claim the staff confirmed."""
    pk = phone_pk(phone)
    return (role_of(None, pk) == "admin" and load_phones().get("me")) or phone_name(phone) or load_quem()["claims"].get(pk, {}).get("name")


# --- login: WhatsApp number -> bot DM -> "sim" -> a signed cookie with the member's name and IP ----------

def valid_phone(raw):
    """Strict: a Brazilian mobile (+55 optional, DDD, 9 + 8 digits) or + country code and 8-15 digits.
    -> digits with country code, or None. Same rule as entrar.html."""
    d = re.sub(r"[\s().-]", "", str(raw or ""))
    m = re.fullmatch(r"(?:\+?55)?([1-9]{2}9\d{8})", d)
    if m:
        return "55" + m[1]
    return d[1:] if re.fullmatch(r"\+(?!55)[1-9]\d{7,14}", d) else None


def session_key():
    f = HERE / "data" / "secret"
    if not f.exists():
        f.parent.mkdir(exist_ok=True)
        f.write_text(secrets.token_hex(32))
    return f.read_text().strip().encode()


def phone_pk(phone):
    """A number as the cookie and data/quem.json hold it: an HMAC of its last 8 digits with KEY. No number at rest."""
    d = re.sub(r"\D", "", str(phone or ""))[-8:]
    return hmac.new(KEY, b"tel:" + d.encode(), hashlib.sha256).hexdigest()[:24] if len(d) == 8 else ""


def sign(name, ip, pk="", now=None):
    body = base64.urlsafe_b64encode(json.dumps([name, int((now or time.time()) + SESSION_DAYS * 86400), ip, pk]).encode()).decode()
    return body + "." + hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest()


def session(token, now=None):
    """-> (name, ip, pk) of a valid cookie, or None. Older cookies (no number: the name + PIN login, and logins from before
    the "~" rule, whose name could be anyone's WhatsApp name) count as logged out."""
    body, _, mac = (token or "").partition(".")
    if not hmac.compare_digest(mac.encode(), hmac.new(KEY, body.encode(), hashlib.sha256).hexdigest().encode()):
        return None
    try:
        name, exp, ip, pk = json.loads(base64.urlsafe_b64decode(body))
    except ValueError:
        return None
    if exp - SESSION_DAYS * 86400 < STALE_BEFORE:
        return None  # signed while a stale phones.json named people wrong (Dan came in as "Barp"): log in again
    return (name, ip, pk) if exp > (now or time.time()) else None


def signed(token, ip, now=None):
    """-> (name, pk) of a valid cookie from this IP, else (None, ""). A "~name" whose number the staff tied to a tabela
    name since the login gets that name."""
    s = session(token, now)
    if not s or s[1] not in (ip, "*"):  # "*": the member asked to stay in when the IP changes (own phone or PC)
        return None, ""
    name, _, pk = s
    if name.startswith("~"):
        name = load_quem()["claims"].get(pk, {}).get("name") or name
    return name_fixes()[0].get(name, name), pk  # a spelling merged into another since the login: that one


def keep_token(token, ip, now=None):
    """The member said yes to "stay in on this browser when the IP changes", after the login: the same session, signed for
    any IP and a fresh SESSION_DAYS. -> the new token, or None if this cookie isn't a valid one from this IP."""
    s = session(token, now)
    return sign(s[0], "*", s[2], now) if s and s[1] in (ip, "*") else None


def signed_name(token, ip, now=None):
    return signed(token, ip, now)[0]


def role_of(name, pk):
    """admin: logged in with BIOFUT_ADMIN_PHONE (Gab); conselho: a CONSELHO name (never a "~" one); membro; or None."""
    if pk and ADMIN_PHONE and hmac.compare_digest(pk, phone_pk(ADMIN_PHONE)):
        return "admin"
    return "conselho" if name in CONSELHO else "membro" if name else None


def too_many_fails(key, failed=False, limit=10):
    """10 wrong PINs / login requests an hour per IP, so the PIN can't be guessed and the bot can't be used to spam."""
    now = time.time()
    FAILS[key] = [t for t in FAILS.get(key, []) if now - t < 3600] + ([now] if failed else [])
    return len(FAILS[key]) >= limit


def login_start(phone, ip, now=None):
    """-> (answer, http code). The bot checks the number is in the group and DMs it the code."""
    now = now or time.time()
    phone = valid_phone(phone)
    if not phone:
        return {"error": "número inválido: (DDD) 9XXXX-XXXX, ou + código do país para número de fora"}, 400
    if too_many_fails("tel:" + phone, failed=True, limit=4):  # 3 an hour per number: nobody floods a member's WhatsApp
        return {"error": "já mandamos 3 pedidos para esse número nesta hora, espere um pouco"}, 429
    for k in [k for k, v in list(LOGINS.items()) if v["exp"] < now]:
        LOGINS.pop(k, None)
    lid, code = secrets.token_urlsafe(18), f"{secrets.randbelow(10000):04d}"
    r = bot_post("/login", {"id": lid, "phone": phone, "code": code})
    if not (r and r.get("ok")):
        return {"error": (r or {}).get("error") or "o bot do WhatsApp não respondeu, tente de novo daqui a pouco"}, 502
    LOGINS[lid] = {"phone": phone, "ip": ip, "code": code, "exp": now + 600}
    return {"id": lid}, 200  # never the code: only the WhatsApp message has it, that's the proof


def login_code(lid, ip, code):
    """The member typed the code from the WhatsApp message in the browser: the proof they hold that number. 3 tries."""
    p = LOGINS.get(str(lid or ""))
    if not p or p["ip"] != ip:
        return {"error": "o pedido expirou, comece de novo"}, 404
    if hmac.compare_digest(p["code"], str(code or "").strip()):
        p["ok"] = True
        return {"ok": True}, 200
    p["tries"] = p.get("tries", 0) + 1
    if p["tries"] >= 3:
        LOGINS.pop(lid, None)
        return {"error": "código errado 3 vezes, comece de novo"}, 404
    return {"error": "código errado"}, 400


def login_status(lid, ip, now=None):
    """-> (name or None, error or None, pk), once login_code() took the right code. The name: member_of() the number,
    else "~Tel" + its last 4 digits (no stats and no role)."""
    p = LOGINS.get(str(lid or ""))
    if not p or p["exp"] < (now or time.time()) or p["ip"] != ip:
        return None, "o pedido expirou, comece de novo", ""
    if not p.get("ok"):
        return None, None, ""
    if LOGINS.pop(lid, None) is None:  # two polls raced; the other one got the cookie
        return None, "o pedido expirou, comece de novo", ""
    pk = phone_pk(p["phone"])
    name = member_of(p["phone"]) or "~Tel " + p["phone"][-4:]
    (HERE / "data").mkdir(exist_ok=True)
    with (HERE / "data" / "logins.jsonl").open("a", encoding="utf-8") as f:  # who and when; the number stays out, like phones.json
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": name}, ensure_ascii=False) + "\n")
    return name, None, pk


# --- who is who: phones.py asks (dubious list names, merges), members and staff answer -> data/quem.json ----------

def load_quem():
    q = json.loads(QUEM.read_text(encoding="utf-8")) if QUEM.exists() else {}
    return {k: q.get(k, {}) for k in ("answers", "merges", "asks", "claims")}


def name_fixes():
    """The tabela as every page shows it: alias (spellings of one person: phones.py's + merges the staff confirmed) and
    per-day answers {"date|name": who it was}, "Sombra" for a guest. The sheet itself stays as typed."""
    t, q = load_phones(), load_quem()
    alias = {**t.get("alias", {}), **{k: m["to"] for k, m in q["merges"].items() if m["ok"]}}
    alias = {k: alias.get(v, v) for k, v in alias.items()}  # ponytail: one hop (a merge onto an alias), deeper chains stop there
    return alias, {f"{a['date']}|{alias.get(a['name'], a['name'])}": alias.get(a["choice"], a["choice"]) for a in q["answers"].values()}


def tabela_names():
    return {p[0] for g in DATA["games"] for t in g["teams"] for p in t["players"]} - {"Sombra"}


def quem_view(user, pk, role):
    """#/eu: the doubtful names this member put on lists, and their pending claim. Staff: every doubtful name, merges and
    claims to confirm; Gab also the number switches (last 4 digits only)."""
    t, q, staff = load_phones(), load_quem(), role in ("admin", "conselho")
    known = set(t.get("map", {}).values())
    alias = name_fixes()[0]
    items = [{**it, "by": alias.get(it["by"], it["by"]), "answer": q["answers"].get(it["id"])} for it in t.get("dubious", [])]
    out = {"items": [it for it in items if staff or it["by"] == user],
           "asked": q["asks"].get(pk, {}).get("name")}
    if staff:
        out["suggest"] = [{"name": a, "to": b, "answer": q["merges"].get(a)} for a, b in t.get("suggest", [])]
        out["asks"] = [{"pk": k, **v, "known": v["name"] in known} for k, v in q["asks"].items()]
    if role == "admin":
        out["switches"] = t.get("switches", [])
    return out


def quem_act(user, pk, staff, body):
    """One answer -> data/quem.json; -> the line for the Avisos group. ValueError when it isn't theirs to give."""
    now = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LOCK:
        t, q = load_phones(), load_quem()
        if "id" in body:  # who the name on that day's list was: the member who wrote it, or the staff
            it = next((x for x in t.get("dubious", []) if x["id"] == body["id"]), None)
            if not it or not (staff or name_fixes()[0].get(it["by"], it["by"]) == user):
                raise ValueError("essa pergunta não é sua")
            if body.get("choice") not in it["options"]:
                raise ValueError("escolha uma das opções")
            q["answers"][it["id"]] = {"date": it["date"], "name": it["name"], "choice": body["choice"], "by": user, "ts": now}
            note = f"🧾 {user}: o “{it['name']}” de {it['date']} era {body['choice']}"
        elif "merge" in body and staff:  # two spellings, one person (or not)
            if [body["merge"], body.get("to")] not in t.get("suggest", []):
                raise ValueError("sugestão desconhecida")
            q["merges"][body["merge"]] = {"to": body["to"], "ok": bool(body.get("ok")), "by": user, "ts": now}
            note = f"🧾 {user}: {body['merge']} {'é' if body.get('ok') else 'não é'} {body['to']}"
        elif "claim" in body:  # a number no list knows: "that tabela name is me", for the staff to confirm
            if not str(user).startswith("~") or not pk:
                raise ValueError("seu número já tem nome na tabela")
            claim = str(body["claim"])
            if claim not in tabela_names():
                raise ValueError("esse nome não está na tabela")
            q["asks"][pk] = {"login": user, "name": claim, "ts": now}
            note = f"🙋 {user} diz que é {claim} na tabela: confirme em /admin, Pessoas"
        elif "ask" in body and staff:
            a = q["asks"].pop(str(body["ask"]), None)
            if not a:
                raise ValueError("pedido não encontrado")
            if body.get("ok"):
                q["claims"][str(body["ask"])] = {"name": a["name"], "by": user, "ts": now}
            note = f"🧾 {user}: {a['login']} {'é' if body.get('ok') else 'não é'} {a['name']}"
        else:
            raise ValueError("só o Gab ou o Conselho")
        write_json(QUEM, q, 1)
    return note


def pin_ok(pin):
    return not PIN or hmac.compare_digest(str(pin or "").encode(), PIN.encode())


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(HERE), **kw)

    def send_json(self, obj, code=200, raw=None, extra=()):
        body = raw or json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store" if raw is None else "public, max-age=300")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
        if self.command == "POST":
            self.track(obj, code)

    def track(self, obj, code):
        """Every POST and how it went -> the activity log. Login polls, the beacon and the bot's photos log themselves or not at all."""
        action = self.path.removeprefix("/api/")
        obj = obj if isinstance(obj, dict) else {}
        if action in ("ev", "sumula_image") or action == "login/status" and code == 200 and not obj.get("approved"):
            return
        body = {} if action.startswith("login/") or action == "whoami" else self.body  # never the phone number
        log_event(action[:30], self.user() or (obj.get("user") if action == "login/status" else None), self.ip(), self.mobile(),
                  code=None if code == 200 else code, err=obj.get("error"),
                  d={k: v if type(v) is int else str(v)[:60] for k, v in body.items() if k in SAFE})

    def mobile(self):
        return "Mobi" in self.headers.get("User-Agent", "")

    def end_headers(self):
        if self.path == "/" or self.path.endswith((".html", ".css", ".js")):  # pages and site.css/js change on deploys
            self.send_header("Cache-Control", "no-cache")  # revalidate (304) instead of Cloudflare/browser guessing
        super().end_headers()

    def cookie(self):
        c = SimpleCookie(self.headers.get("Cookie", ""))
        return c["biofut"].value if "biofut" in c else ""

    def user(self):
        return signed_name(self.cookie(), self.ip())

    def role(self):
        if ADMIN and hmac.compare_digest(self.headers.get("X-BioFut-Admin", "").encode(), ADMIN.encode()):
            return "admin"
        return role_of(*signed(self.cookie(), self.ip()))

    def admin(self):
        return self.role() == "admin"

    def ip(self):  # nginx and Cloudflare are in front; the server itself listens on 127.0.0.1
        return self.headers.get("CF-Connecting-IP") or self.client_address[0]

    def send_private(self, body, ctype, cache="private, max-age=300", extra=()):
        self.send_response(200)
        for k, v in extra:
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("Vary", "Cookie")
        self.end_headers()
        self.wfile.write(body)

    def send_range(self, f, ctype):
        """A file with HTTP Range, so <audio> can seek. ponytail: one range, whole read; fine for 7 MB songs."""
        size = f.stat().st_size
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
        start, end = 0, size - 1
        if m and (m[1] or m[2]):
            start = int(m[1]) if m[1] else max(0, size - int(m[2]))
            end = min(int(m[2]), end) if m[1] and m[2] else end
        with f.open("rb") as fh:
            fh.seek(start)
            body = fh.read(end - start + 1)
        self.send_response(206 if m else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Accept-Ranges", "bytes")
        if m:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=86400")
        self.send_header("Vary", "Cookie")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        user = self.user()
        if path == "/api/me":  # why "ip": a valid cookie from another IP, so the site can say why you are out
            return self.send_json({"user": user, "role": self.role(), "why": "ip" if not user and session(self.cookie()) else None,
                                   "tour": bool(user) and user not in load_state().get("tour", {}),  # the TCG tour: once per member, from its deploy on
                                   "truco_tour": bool(user) and user not in load_state().get("tour_truco", {})})  # the BioTruco popup + tutorial, same
        if path == "/wiki":
            self.path = "/wiki.html"
            return super().do_GET()
        if path == "/copa":
            return self.send_private(copa_page(), "text/html; charset=utf-8", "public, max-age=3600")  # the countdown changes once a day
        if path == "/api/wiki":
            f = WIKI / ("member.json" if user else "public.json")
            if not f.exists():
                return self.send_error(404)
            raw, gz = wiki_bytes(f, bool(user))
            if "gzip" in self.headers.get("Accept-Encoding", ""):
                return self.send_private(gz, "application/json; charset=utf-8", extra=[("Content-Encoding", "gzip")])
            return self.send_private(raw, "application/json; charset=utf-8")
        m = re.fullmatch(r"/api/avatar/([\w-]+)\.jpg", path)
        if path == "/api/avatars" or m:  # WhatsApp profile photos: members only (nobody posted them to the site)
            if not user:
                return self.send_json({"error": "só para membros"}, 403)
            if not m:
                return self.send_json(sorted(p.stem for p in AVATARS.glob("*.jpg")) if AVATARS.exists() else [])
            f = AVATARS / f"{m[1]}.jpg"
            return self.send_private(f.read_bytes(), "image/jpeg", "private, max-age=86400") if f.exists() else self.send_error(404)
        m = re.fullmatch(r"/data/radio/([^/]+\.mp3)", path)
        if path == "/api/radio" or m:  # #/radio: the group's songs, members only
            if not user:
                return self.send_json({"error": "só para membros"}, 403)
            if not m:
                return self.send_json((sorted(p.stem for p in RADIO.glob("*.mp3")) if RADIO.exists() else []) + SOUNDCLOUD)
            f = RADIO / urllib.parse.unquote(m[1])
            return self.send_range(f, "audio/mpeg") if ".." not in f.name and f.exists() else self.send_error(404)
        if path == "/api/jogos":  # #34: the group's photos of each game night (wiki/jogos.py), members only
            if not user:
                return self.send_json({"error": "só para membros"}, 403)
            return self.send_json(night_photos())
        if path in ("/api/wiki_feedback", "/api/votes"):
            if not user:
                return self.send_json({"error": "só para membros"}, 403)
            if path == "/api/votes":  # key -> [sum, how many, yours]
                return self.send_json({k: [*(list(v.values()).count(i) for i in (1, 2, 3)), v.get(user, 0)] if k[0] == "c" else  # Copa ideas: Top / Vai dar ruim / Que merda
                                       [sum(v.values()), len(v), v.get(user, 0)] for k, v in load_votes().items() if v})
            return self.send_json([{**r, "id": fid(r)} for r in read_jsonl(WIKI / "feedback.jsonl")])
        m = re.fullmatch(r"/wiki/media/([\w-]+\.jpg)", path)
        if m:
            f = WIKI / "media" / m[1]
            if not f.exists() or not (user or m[1] in public_media()):
                return self.send_error(404)
            return self.send_private(f.read_bytes(), "image/jpeg", "private, max-age=604800")
        if path in ("/admin", "/transparencia", "/entrar"):
            self.path = path + ".html"
            return super().do_GET()
        if path == "/api/admin/events":
            if not self.admin():
                return self.send_json({"error": "chave de admin errada"}, 403)
            return self.send_json(recent_events())
        if path == "/api/fila":
            with LOCK:
                return self.send_json(fila(load_review()))
        if path == "/api/mensagens":  # your own messages only, and only for a number the group knows
            if not user or user.startswith("~"):
                return self.send_json({"error": "entre com o número que você usa no grupo"}, 403)
            return self.send_json(my_messages(user))
        if path == "/api/feedback":  # members see their own, Gab (admin key) sees everyone's
            if not (user or self.admin()):
                return self.send_json({"error": "entre primeiro"}, 403)
            done = json.loads(ISSUES.read_text(encoding="utf-8")) if ISSUES.exists() else {}
            rows = [{**r, "issue": done.get(fid(r))} for r in read_jsonl(FEEDBACK)]
            return self.send_json(rows if self.admin() else [r for r in rows if r["user"] == user])
        if path == "/api/review":
            role = self.role()
            if role not in ("admin", "conselho"):
                return self.send_json({"error": "só o Gab e o Conselho"}, 403)
            with LOCK:
                return self.send_json([{**it, "held": held(it)} for it in load_review()[::-1] if role == "admin" or it["kind"] in DATA_KINDS])
        if path == "/api/quem":
            if not self.role():
                return self.send_json({"error": "entre primeiro"}, 403)
            return self.send_json(quem_view(*signed(self.cookie(), self.ip()), self.role()))
        m = re.fullmatch(r"/api/review_media/([0-9a-f]{16}\.jpg)", path)
        if m:
            f = REVIEW_MEDIA / m[1]
            if self.role() not in ("admin", "conselho") or not f.exists():
                return self.send_error(404)
            return self.send_private(f.read_bytes(), "image/jpeg")
        if path == "/api/transparencia":
            f = LISTAS
            listas = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
            profs = load_profiles()
            hidden = {n for n, p in profs.items() if p.get("hide") and n != user}
            if hidden:
                hide_names(listas, hidden)
            if not user:  # the public sees the flake rate and the trophies, members see everyone's numbers and timelines
                listas.pop("people", None)
                for g in listas.get("games", []):
                    g.pop("eventos", None)
            avisos = [json.loads(l) for l in AVISOS.open(encoding="utf-8")][-50:][::-1] if AVISOS.exists() else []
            return self.send_json({"user": user, "hide": bool(profs.get(user, {}).get("hide")), "listas": listas, "log": log_view(), "avisos": avisos if user else [],
                                   "pix": DATA.get("pix", {}).get("key"), "custos": costs.totals()})
        if path == "/api/push/key":  # the applicationServerKey a phone subscribes with (null: push off)
            return self.send_json({"key": push.public_key(push.vapid(VAPID)) if push else None})
        if path == "/api/custos":  # what the AI calls cost, public: the Apoie page shows it next to the Pix
            return self.send_json(costs.totals())
        if path == "/api/planilha":  # games the sheet lacks, ready to paste (#/planilha): no Gmail, no Apps Script
            with LOCK:
                games = unsynced(load_state()["played"], DATA["games"])
            return self.send_json([{"n": g["n"], "line": game_line(g), "tsv": "\n".join("\t".join(r) for r in sheet_rows(g))}
                                   for g in games])
        if path == "/api/data":
            with LOCK:
                raw = DATA_RAW
            return self.send_json(None, raw=raw)
        if path == "/api/state":
            with LOCK:
                st = load_state()
                if retry_list(st):
                    save_state(st)
                return self.send_json(public_state(st))
        if not (path in ("/", "/index.html", "/site.css", "/site.js", "/og.png", "/logo.png", "/robots.txt", "/sitemap.xml", "/sw.js") or re.fullmatch(r"/og/copa-\d{1,3}\.jpg", path) or path.startswith("/data/photos/") and ".." not in path):
            return self.send_error(404)
        self.path = path
        return super().do_GET()

    def do_POST(self):
        action = self.path.removeprefix("/api/")
        user = self.user()
        self.body = {}
        if not user and too_many_fails(self.ip()):
            return self.send_json({"error": "muitas tentativas, tente de novo em uma hora"}, 429)
        if action in ("sumula_image", "lista", "avatar", "nomes") and not (
                BOT_TOKEN and hmac.compare_digest(self.headers.get("X-BioFut-Token", "").encode(), BOT_TOKEN.encode())):
            return self.send_json({"error": "token errado"}, 401)
        if action == "lista":  # the bot: a group text that looks like the sign-up list. The number only finds the name.
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 20000)))
                text, ts = str(body["text"])[:8000], float(body.get("ts") or time.time())
            except (ValueError, KeyError, TypeError) as e:
                return self.send_json({"error": f"corpo inválido: {e}"}, 400)
            poster = member_of(body.get("phone")) or "~" + (str(body.get("sender") or "").strip()[:30] or "?")
            with LOCK:
                st = load_state()
                out = sync_list(st, text, ts, poster, phone_pk(body.get("phone")), str(body.get("sender") or "").strip()[:30])
                save_state(st)  # last_list too, when nothing changed
            return self.send_json(out or {"ok": False})
        if action == "cancelado":  # the bot: a member wrote "cancelado" in the group on the game's day or the one before
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 2000)) or b"{}")
            who = member_of(body.get("phone") if isinstance(body, dict) else None)
            if not who:
                return self.send_json({"ok": False, "why": "não é membro"})
            today = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 3600))
            with LOCK:
                st = load_state()
                d = st["match"]["date"]
                if not d or not 0 <= (kickoff(d) - kickoff(today)) // 86400 <= 1:
                    return self.send_json({"ok": False, "why": "sem jogo hoje ou amanhã"})
                note = cancel_match(st, f"{who} avisou no grupo")
                save_state(st)
            threading.Thread(target=notify, args=(note,), daemon=True).start()
            return self.send_json({"ok": True})
        if action == "nomes":  # the bot: {phones: [group members' numbers]} -> {names: {phone: name}}, to DM the captains. Nothing kept.
            try:
                phones = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 20000)))["phones"][:300]
            except (ValueError, KeyError, TypeError) as e:
                return self.send_json({"error": f"corpo inválido: {e}"}, 400)
            names = {str(p): n for p in phones if (n := member_of(p)) and not n.startswith("~")}
            return self.send_json({"names": names})
        if action == "avatar":  # the bot: {phone, image (base64 JPEG)}. A number nobody knows is dropped.
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 3_000_000)))
                raw = base64.b64decode(body["image"], validate=True)
            except (ValueError, KeyError, TypeError) as e:
                return self.send_json({"error": f"corpo inválido: {e}"}, 400)
            name = member_of(body.get("phone"))
            if not name or name.startswith("~") or len(raw) > MAX_PHOTO or raw[:2] != b"\xff\xd8":
                return self.send_json({"ok": False})
            AVATARS.mkdir(parents=True, exist_ok=True)
            (AVATARS / f"{slug(name)}.jpg").write_bytes(raw)
            return self.send_json({"ok": True})
        if action == "sumula_image":
            length = int(self.headers.get("Content-Length", 0))
            if length > 12_000_000:
                return self.send_json({"error": "imagem grande demais"}, 413)
            try:
                body = json.loads(self.rfile.read(length))
                image = base64.b64decode(body["image"], validate=True)
                date = str(body.get("date") or time.strftime("%Y-%m-%d"))[:10]
            except (ValueError, KeyError, TypeError) as e:
                return self.send_json({"error": f"corpo inválido: {e}"}, 400)
            threading.Thread(target=ocr_photo, args=(image, date, str(body.get("sender") or "?")[:40]), daemon=True).start()
            return self.send_json({"ok": True}, 202)
        if action == "login/keep":
            tok = keep_token(self.cookie(), self.ip())
            if not tok:
                return self.send_json({"error": "entre de novo"}, 403)
            secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            return self.send_json({"ok": True}, extra=[("Set-Cookie", f"biofut={tok}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; SameSite=Lax{secure}")])
        if action == "logout":
            return self.send_json({"user": None}, extra=[("Set-Cookie", "biofut=; Path=/; Max-Age=0")])
        if action == "ev":  # page beacon (views, clicks): no PIN, visitors have none; 300 an hour per IP
            try:
                b = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4000)) or b"{}")
            except ValueError:
                b = {}
            b = b if isinstance(b, dict) else {}
            if re.fullmatch(r"[a-z_]{1,24}", str(b.get("e"))) and not too_many_fails("ev:" + self.ip(), failed=True, limit=300):
                log_event(b["e"], user, self.ip(), self.mobile(), p=str(b.get("p") or "")[:120], d=str(b.get("d") or "")[:120])
            return self.send_json({})
        if not action.startswith("login/") and not user and not self.admin() and not pin_ok(self.headers.get("X-BioFut-Pin")):
            too_many_fails(self.ip(), failed=True)
            return self.send_json({"error": "PIN do grupo errado"}, 403)
        try:
            length = int(self.headers.get("Content-Length", 0))
            if length > MAX_PHOTO * 2:
                raise ValueError("payload grande demais")
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                return self.send_json({"error": "corpo deve ser um objeto JSON"}, 400)
            self.body = body
            if action == "login/start":
                too_many_fails(self.ip(), failed=True)  # every request counts: 10 an hour per IP
                out, code = login_start(body.get("phone"), self.ip())  # no LOCK: the bot can take 10 s, sign-ups must not wait
                return self.send_json(out, code)
            if action == "login/code":
                out, code = login_code(body.get("id"), self.ip(), body.get("code"))
                return self.send_json(out, code)
            if action == "login/status":
                name, err, pk = login_status(body.get("id"), self.ip())
                if err:
                    return self.send_json({"error": err}, 404)
                if not name:
                    return self.send_json({"approved": False})
                secure = "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
                cookie = f"biofut={sign(name, '*' if body.get('keep') else self.ip(), pk)}; Path=/; Max-Age={SESSION_DAYS * 86400}; HttpOnly; SameSite=Lax{secure}"
                return self.send_json({"approved": True, "user": name}, extra=[("Set-Cookie", cookie)])
            if action == "review":
                role = self.role()
                if role not in ("admin", "conselho"):
                    too_many_fails(self.ip(), failed=True)
                    return self.send_json({"error": "só o Gab e o Conselho"}, 403)
                return self.send_json(review_act(int(body.get("id") or 0), body.get("action"), body.get("payload"),
                                                 None if role == "admin" else DATA_KINDS, user or role))
            if action == "quem":
                role = self.role()
                if not role:
                    raise ValueError("entre primeiro")
                name, pk = signed(self.cookie(), self.ip())
                # answers only go to the log (transparência): years of old lists answered in a row would flood the group
                notify(quem_act(name or role, pk, role in ("admin", "conselho"), body), post="claim" in body)
                return self.send_json(quem_view(name, pk, role))
            if action == "whoami":
                if not user:
                    raise ValueError("entre primeiro")
                name, how = phone_lookup(body.get("phone"))
                if not name:
                    too_many_fails(self.ip(), failed=True)  # misses count like wrong PINs: no walking the group's numbers
                    return self.send_json({"error": "não achei esse número no histórico do grupo"}, 404)
                return self.send_json({"user": name, "how": how})  # only tells; who you are is proven by the WhatsApp login
            if action == "profile":
                if not user:
                    raise ValueError("entre primeiro")
                return self.send_json({"user": user, "profile": set_profile(user, body)})
            if action == "feedback":
                text = str(body.get("text") or "").strip()[:2000]
                if not user or not text:
                    raise ValueError("entre e escreva a sua ideia")
                row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": user, "kind": body.get("kind") if body.get("kind") in ("bug", "empresa") else "ideia", "text": text}
                with LOCK:
                    FEEDBACK.parent.mkdir(exist_ok=True)
                    with FEEDBACK.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                notify(f"💡 {user} mandou {row['kind']}: {text[:300]}")
                threading.Thread(target=file_issues, daemon=True).start()
                return self.send_json({"ok": True})
            if action == "wiki_feedback":  # "algo errado" on a wiki page or a site item (page "site:resenha"), or a better photo
                text = str(body.get("text") or "").strip()[:2000]
                photo, file = body.get("photo") or "", str(body.get("file") or "")  # an upload, or a photo the wiki already has
                if not user or not (text or photo or file):
                    raise ValueError("entre com seu nome e escreva o que está errado")
                row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "user": user, "page": str(body.get("page") or "")[:80],
                       "ref": str(body.get("ref") or "")[:60], "text": text}
                if photo:
                    raw = jpeg(str(photo))
                    file = "u" + hashlib.sha256(raw).hexdigest()[:15] + ".jpg"
                    (WIKI / "media").mkdir(parents=True, exist_ok=True)
                    (WIKI / "media" / file).write_bytes(raw)
                elif file and not (re.fullmatch(r"[\w-]+\.jpg", file) and (WIKI / "media" / file).exists()):
                    raise ValueError("essa foto não existe")
                with LOCK:
                    WIKI.mkdir(parents=True, exist_ok=True)
                    with (WIKI / "feedback.jsonl").open("a", encoding="utf-8") as f:
                        f.write(json.dumps({**row, **({"file": file} if file else {})}, ensure_ascii=False) + "\n")
                if file:  # held in the review queue until the Gab or the Conselho approves (review_tick announces it)
                    write_json(INBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-{file[:8]}.json", {"kind": "foto",
                               "title": f"Foto principal de {str(body.get('title') or row['page'])[:60]} (de {user})",
                               "payload": {"page": row["page"], "file": file, "player": clean_name(body.get("player")) if body.get("player") else ""}})
                else:
                    notify(f"⚑ {user} reportou em {row['page']}{' · ' + row['ref'] if row['ref'] else ''}: {text[:300]}")
                return self.send_json({"ok": True, "id": fid(row)})
            if action == "jogo_errado":  # #34: "a súmula não bate com a tabela" -> the review queue, held for the Gab and the Conselho
                g = next((g for g in DATA["games"] + load_state()["played"] if g["n"] == body.get("n")), None)
                if not user or not g:
                    raise ValueError("entre e abra um jogo")
                a, b = g["teams"]
                fotos = ([g["sumula"]] if g.get("sumula") else []) + [x["file"] for x in night_photos().get(g["date"], [])
                                                                     if x["kind"] in ("match_summary", "scoreboard")]
                write_json(INBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-jogo{g['n']}.json", {"kind": "jogo",
                           "title": f"Súmula não bate: jogo {g['n']} de {g['date']} (de {user})",
                           "payload": {"n": g["n"], "date": g["date"], "placar": f"{a['name']} {a['gf']} × {b['gf']} {b['name']}",
                                       "text": str(body.get("text") or "").strip()[:1000], "user": user, "fotos": fotos}})
                return self.send_json({"ok": True})
            if action == "vote":  # concordo/discordo on a report ("f:<id>", ±1), how funny a wiki bit is ("b:<id>", 1-5), a Copa idea ("c:<n>", 1-3); 0 takes it back
                key, v = str(body.get("key") or ""), body.get("v")
                if not user or not re.fullmatch(r"[fbc]:[\w#.-]{1,60}", key) or type(v) is not int or not (
                        -1 <= v <= 1 if key[0] == "f" else 0 <= v <= (3 if key[0] == "c" else 5)):
                    raise ValueError("voto inválido")
                with LOCK:
                    votes = load_votes()
                    k = votes.setdefault(key, {})
                    k.pop(user, None)
                    if v:
                        k[user] = v
                    write_json(VOTES, votes)
                return self.send_json({"key": key, "votes": [sum(k.values()), len(k), v]})
            if action == "push_sub":  # a phone said yes to notifications ({sub}: its PushSubscription) or no ({sub, off})
                sub = body.get("sub") if isinstance(body.get("sub"), dict) else {}
                ep, k = str(sub.get("endpoint") or ""), sub.get("keys") if isinstance(sub.get("keys"), dict) else {}
                if not ep.startswith("https://") or len(ep) > 1000 or not body.get("off") and not all(type(k.get(x)) is str for x in ("p256dh", "auth")):
                    raise ValueError("inscrição inválida")
                with LOCK:
                    subs = json.loads(PUSH_SUBS.read_text(encoding="utf-8")) if PUSH_SUBS.exists() else {}
                    subs.pop(ep, None)
                    if not body.get("off"):
                        subs[ep] = {"keys": {"p256dh": k["p256dh"][:200], "auth": k["auth"][:100]}, "user": user, "at": int(time.time())}
                    write_json(PUSH_SUBS, subs)
                return self.send_json({"ok": True})
            if action == "push_send":  # Gab: {title, body, url, to?} to every phone that said yes (or only to's); the ones that left are dropped
                if not self.admin() or not push:
                    raise ValueError("só o Gab manda notificação" if push else "push desligado: falta o pacote cryptography")
                url = str(body.get("url") or "/")
                msg = {"title": str(body.get("title") or "BioFut")[:80], "body": str(body.get("body") or "").strip()[:300], "url": url if url.startswith("/") else "/"}
                if not msg["body"]:
                    raise ValueError("escreva a notificação")
                with LOCK:
                    subs = json.loads(PUSH_SUBS.read_text(encoding="utf-8")) if PUSH_SUBS.exists() else {}
                to = clean_name(body.get("to")) if body.get("to") else None
                if to:
                    subs = {ep: x for ep, x in subs.items() if x["user"] == to}
                    if not subs:
                        raise ValueError(f"{to} não ativou as notificações")
                key = push.vapid(VAPID)
                codes = {ep: push.send(key, {"endpoint": ep, **x}, msg) for ep, x in subs.items()}  # ponytail: one by one, fine for ~70 phones
                with LOCK:
                    subs = json.loads(PUSH_SUBS.read_text(encoding="utf-8")) if PUSH_SUBS.exists() else {}
                    for ep in [ep for ep, c in codes.items() if c in (404, 410)]:
                        subs.pop(ep, None)
                    write_json(PUSH_SUBS, subs)
                notify(f"🔔 {to + ': ' if to else ''}{msg['body']}", post=False)
                ok, gone = sum(200 <= c < 300 for c in codes.values()), sum(c in (404, 410) for c in codes.values())
                return self.send_json({"sent": ok, "gone": gone, "failed": len(codes) - ok - gone})
            with LOCK:
                st = load_state()
                if action == "photo":
                    save_photo(clean_name(body.get("name")), body.get("photo", ""))
                elif action == "buy_card":  # #36: the logged-in member buys for themself, never a name from the body
                    if not user:
                        raise ValueError("entre para comprar")
                    buy_card(st, base_of(st, DATA), card_prices(DATA["games"] + unsynced(st["played"], DATA["games"])),
                             user, clean_name(body.get("card")), str(body.get("stat") or ""))
                    save_state(st)
                elif action == "deck":
                    set_deck(st, user, [clean_name(n) for n in body.get("cards") or []][:DECK + 1])
                    save_state(st)
                elif action == "bonus":  # launch gift (Gab, 2026-10-16): BONUS coins once per member until BONUS_END
                    if not user:
                        raise ValueError("entre primeiro")
                    got = time.strftime("%Y-%m-%d") <= BONUS_END and not any(x["player"] == user and x["reason"] == BONUS_WHY for x in st["ledger"])
                    if got:
                        st["ledger"].append({"player": user, "amount": BONUS, "reason": BONUS_WHY})
                        save_state(st)
                    return self.send_json({"bonus": BONUS if got else 0})
                elif action == "tour":  # the member saw (or skipped) the first-login tour
                    if not user:
                        raise ValueError("entre primeiro")
                    if body.get("which") == "truco":  # {which, done, step}: done stays true once the member went through it all
                        old = st.setdefault("tour_truco", {}).get(user, {})
                        st["tour_truco"][user] = {"at": time.strftime("%Y-%m-%d"), "done": bool(old.get("done") or body.get("done")), "step": int(body.get("step") or 0)}
                    else:
                        st.setdefault("tour", {})[user] = time.strftime("%Y-%m-%d")
                    save_state(st)
                elif action == "cromo":
                    claim_cromo(st, user, clean_name(body.get("card")), str(body.get("stat") or ""))
                    save_state(st)
                elif action == "duelo":  # the server deals and judges: the ranking and the coins are real
                    duel = duel_act(st, user, duel_cards(DATA["games"] + unsynced(st["played"], DATA["games"])), body,
                                    time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 3600)))  # the group's day
                    save_state(st)
                    return self.send_json({**public_state(st), "duel": duel})
                elif action == "pix_bonus":  # staff: who paid the Pix on the game's night, {names, date}: PIX_BONUS coins once per game
                    if self.role() not in ("admin", "conselho"):
                        raise ValueError("só o Gab e o Conselho")
                    date = str(body.get("date") or st["match"]["date"] or time.strftime("%Y-%m-%d"))[:10]
                    why = f"pix em dia {date}"
                    got = [n for n in dict.fromkeys(clean_name(x) for x in (body.get("names") or [])[:40] if str(x).strip())
                           if not any(x["player"] == n and x["reason"] == why for x in st["ledger"])]
                    st["ledger"] += [{"player": n, "amount": PIX_BONUS, "reason": why} for n in got]
                    save_state(st)
                    return self.send_json({**public_state(st), "pix_bonus": got})
                elif action == "admin_give":  # Gab, on a member's page: {name, coins?, reason?, card?} coins (+ or -) and/or a card as a gift
                    if not self.admin():
                        raise ValueError("só o Gab")
                    name, card = clean_name(body.get("name")), clean_name(body.get("card")) if body.get("card") else ""
                    try:
                        coins = round(float(body.get("coins") or 0), 4)
                    except (TypeError, ValueError):
                        raise ValueError("moedas: um número")
                    if not name or not coins and not card or abs(coins) > 1000:
                        raise ValueError("diga quem, e moedas (até 1000) ou uma carta")
                    deck = st.setdefault("cards", {}).get(name, [])
                    if card and (card not in card_prices(DATA["games"] + unsynced(st["played"], DATA["games"])) or card in deck):
                        raise ValueError(f"{name} já tem essa carta, ou ela não existe")
                    if coins:
                        st["ledger"].append({"player": name, "amount": coins, "reason": "Gab: " + (str(body.get("reason") or "").strip()[:80] or "presente")})
                    if card:  # a gift is not a buy: no cromada, no ledger line (first_buyers reads "carta ..." reasons)
                        st["cards"][name] = deck + [card]
                        team = st.setdefault("deck", {}).setdefault(name, [])
                        if len(team) < DECK:
                            team.append(card)
                    save_state(st)
                    notify(f"🎁 {name}: {f'{coins:+g} moedas ' if coins else ''}{'carta ' + card if card else ''}", post=False)
                    return self.send_json(public_state(st))
                elif action == "truco":  # BioTruco v0.2: the server deals, plays the machine and judges
                    truco = truco_act(st, user, duel_cards(DATA["games"] + unsynced(st["played"], DATA["games"])), body,
                                      time.strftime("%Y-%m-%d", time.gmtime(time.time() - 3 * 3600)))
                    if body.get("op"):  # the view alone changes nothing
                        save_state(st)
                    return self.send_json({**public_state(st), "jogo_truco": truco})  # "truco" is the public ranking
                elif action in ("mercado", "mercado_bet", "mercado_fim"):  # BioBet mercados: the logged-in member's own coins
                    note = mercado_act(st, action, body, user, self.role())
                    save_state(st)
                    if note:
                        threading.Thread(target=notify, args=(note,), daemon=True).start()
                else:
                    if action == "bet":  # the coins are the logged-in member's own, never a name from the body
                        if not user:
                            raise ValueError("entre para apostar")
                        body["bettor"] = user
                    if action == "redraft_vote":  # the ballot is the logged-in member's own
                        if not user:
                            raise ValueError("entre para votar")
                        body["voter"] = user
                    guard(st["match"], action, body, user, self.role() in ("admin", "conselho"))
                    before, d0 = heads(st["match"]), json.loads(json.dumps(st["match"]["draft"]))
                    apply(st, action, body, DATA, base_of(st, DATA))
                    news = match_news(st["played"][-1]) if action == "close_match" else draft_news(st, action, d0) if st["match"]["draft"] else None
                    save_state(st)
                    if news:
                        group_post(news)
                    if action == "signup":
                        posted = join_ping(st, before, user)
                        return self.send_json({**public_state(st), "posted": posted})
                    if action == "draft_pick":
                        pick_ping(st, clean_name(body.get("captain")))
                self.send_json(public_state(st))
        except (ValueError, json.JSONDecodeError) as e:
            self.send_json({"error": str(e)}, 400)


KEY = session_key()
DATA_RAW = SRC.read_bytes()
DATA = json.loads(DATA_RAW)

if __name__ == "__main__":
    if SHEET_CACHE.exists():
        use_games(sheet_games(SHEET_CACHE.read_text(encoding="utf-8")))
    threading.Thread(target=sync_sheet, daemon=True).start()
    threading.Thread(target=review_loop, daemon=True).start()
    threading.Thread(target=file_issues, daemon=True).start()  # ideas sent while the token was unset or GitHub down
    port = int(os.environ.get("PORT", 8765))
    print(f"BioFut on http://localhost:{port}  ({len(DATA['games'])} jogos)")
    ThreadingHTTPServer((os.environ.get("HOST", "0.0.0.0"), port), Handler).serve_forever()

"""Self-check: python test_site.py  (needs biofut.json; the odds parity check also needs numpy + sklearn)"""
import sys

import server
from server import DATA, sign, signed_name, too_many_fails, WELCOME, apply, balance, minted, new_state, odds, sheet_games, unsynced
import tempfile
from pathlib import Path
PHONES0, HERE0, BOT_POST0 = server.PHONES, server.HERE, server.bot_post
server.DRAFT_OPENS = ""  # the noon gate is checked once below; the rest of the file drafts whenever

BASE = minted(DATA["games"])

# Draft: snake order A, B, B, A; undo; both captains confirm.
st = new_state()
st["match"]["date"] = "2026-10-08"
for n in ["Victor", "Canova", "c", "d", "e", "f"]:
    apply(st, "signup", {"name": n})
apply(st, "signup", {"name": "victor"})  # case-insensitive dedupe
assert len(st["match"]["confirmed"]) == 6
apply(st, "signup", {"name": "g"}); apply(st, "unconfirm", {"name": "g"}); apply(st, "unconfirm", {"name": "nobody"})  # leaving costs LEAVE, once
assert balance(st, BASE, "g") == WELCOME - server.LEAVE and balance(st, BASE, "nobody") == WELCOME and len(st["match"]["confirmed"]) == 6
server.DRAFT_OPENS, st["match"]["date"] = "12:00", "2099-10-08"
try:
    apply(st, "draft_start", {"captains": ["Victor", "Canova"]}); raise AssertionError("a draft before noon of its day must wait")
except ValueError as e:
    assert "meio-dia" in str(e) and "08/10" in str(e), e
server.DRAFT_OPENS, st["match"]["date"] = "", "2026-10-08"
apply(st, "draft_start", {"captains": ["Victor", "Canova"]})
d = st["match"]["draft"]
try:
    apply(st, "draft_pick", {"captain": "Victor", "player": "c"}); raise AssertionError("no pick before the coin")
except ValueError:
    pass
# Who starts: coin (blind, a tie flips again) or both naming the same captain; a disagreement is a note, not a start.
apply(st, "draft_flip", {"captain": "Victor", "choice": "cara"}); apply(st, "draft_flip", {"captain": "Canova", "choice": "cara"})
assert d["first"] is None and d["flip"] == {} and "De novo" in d["note"], d
apply(st, "draft_flip", {"captain": "Victor", "choice": "Victor"}); apply(st, "draft_flip", {"captain": "Canova", "choice": "cara"})
assert d["first"] is None and "concordarem" in d["note"], d
apply(st, "draft_flip", {"captain": "Canova", "choice": "coroa"}); apply(st, "draft_flip", {"captain": "Victor", "choice": "cara"})
assert d["first"] == {"cara": "Victor", "coroa": "Canova"}[d["coin"]["result"]] and d["captains"][0] == d["first"] and "note" not in d, d
pub = server.public_state(st)["match"]["draft"]
assert pub["flip"] == ["Canova", "Victor"] and pub["votes"] == 0 and pub["first"] == d["first"], "the choices and the ballots stay on the server"
d["first"] = d["captains"][0] = "Victor"; d["captains"][1] = "Canova"; d["teams"] = {"Victor": ["Victor"], "Canova": ["Canova"]}  # a known order for the rest
for p in ["c", "d", "e", "f"]:
    apply(st, "draft_pick", {"captain": "Victor" if p in ("c", "f") else "Canova", "player": p})
apply(st, "draft_undo", {})
assert st["match"]["draft"]["teams"]["Victor"] == ["Victor", "c"]
apply(st, "draft_pick", {"captain": "Victor", "player": "f"})
for cap in ("Victor", "Canova"):
    apply(st, "draft_confirm", {"captain": cap})
# Redraft vote: a whole team plus half of the other; captains don't vote; Modo Ditador (both) closes the vote.
import copy
v = copy.deepcopy(st)
for bad in ({"voter": "Victor", "ok": True}, {"voter": "nobody", "ok": True}):
    try:
        apply(v, "redraft_vote", bad); raise AssertionError(bad)
    except ValueError:
        pass
apply(v, "redraft_vote", {"voter": "c", "ok": True}); apply(v, "redraft_vote", {"voter": "d", "ok": False})
assert v["match"]["draft"]["ok"] == ["Victor", "Canova"], "c + f is not the whole Time Victor yet"
apply(v, "redraft_vote", {"voter": "f", "ok": True})  # Time Victor (c, f) whole; Time Canova (d, e): d no -> 0 of 2 < half
assert v["match"]["draft"]["ok"] == ["Victor", "Canova"]
apply(v, "redraft_vote", {"voter": "e", "ok": True})  # 1 of 2 = half
dv = v["match"]["draft"]
assert dv["ok"] == [] and dv["teams"] == {"Victor": ["Victor"], "Canova": ["Canova"]} and dv["votes"] == {} and dv["first"] == "Victor" and "Time Victor inteiro" in dv["redraft"], dv
v = copy.deepcopy(st)
apply(v, "draft_ditador", {"captain": "Victor"}); apply(v, "redraft_vote", {"voter": "c", "ok": True})
apply(v, "draft_ditador", {"captain": "Canova"})
assert v["match"]["draft"]["ditador"] == ["Victor", "Canova"] and v["match"]["draft"]["votes"] == {}
try:
    apply(v, "redraft_vote", {"voter": "c", "ok": True}); raise AssertionError("ditador")
except ValueError:
    pass
apply(v, "draft_ditador", {"captain": "Canova", "on": False}); apply(v, "redraft_vote", {"voter": "c", "ok": True})
assert v["match"]["draft"]["votes"] == {"c": True}

# BioBet: stake leaves the wallet, the draft locks, a winning bet pays floor(stake * odds).
assert balance(st, BASE, "c") == WELCOME and BASE["Victor"] == WELCOME + 174 + 125
apply(st, "bet", {"bettor": "c", "pick": "A", "stake": 4}, DATA, BASE)
apply(st, "bet", {"bettor": "d", "pick": "B", "stake": 10}, DATA, BASE)
for bad in ({"bettor": "e", "pick": "A", "stake": WELCOME + 1}, {"bettor": "e", "pick": "X", "stake": 1}, {"bettor": "e", "pick": "A", "stake": 1.5}):
    try:
        apply(st, "bet", bad, DATA, BASE); raise AssertionError(bad)
    except ValueError:
        pass
try:
    apply(st, "draft_undo", {}); raise AssertionError("draft must lock after a bet")
except ValueError:
    pass
odd_a = st["match"]["bets"][0]["odds"]
apply(st, "close_match", {"score": [5, 3], "stats": {"c": [2, 1], "Victor": [3, 0]}}, DATA, BASE)
g = st["played"][0]
assert g["season"] == "2026/2" and [t["res"] for t in g["teams"]] == ["V", "D"] and g["teams"][0]["players"][1] == ["c", 2, 1, 0, 0]
assert balance(st, BASE, "c") == WELCOME - 4 + int(4 * odd_a) + server.PLAY and minted([g])["c"] == WELCOME + 3 and balance(st, BASE, "d") == WELCOME - 10 + server.PLAY
assert st["match"]["confirmed"] == [] and st["casa"] == 1, "the house keeps 4.2% of the 14 coins bet"
assert server.card_prices(DATA["games"])["Victor"] == (174 + 125) // 2  # #36: half the career goals + assists

# Cancelled match refunds open bets.
st2 = new_state()
st2["match"] = {"date": "", "confirmed": ["x", "y"], "draft": {"captains": ["x", "y"], "teams": {"x": ["x"], "y": ["y"]}, "ok": ["x", "y"]}, "bets": []}
apply(st2, "bet", {"bettor": "x", "pick": "E", "stake": 7}, DATA, BASE)
apply(st2, "new_match", {"date": "2026-10-15"})
assert balance(st2, BASE, "x") == WELCOME and st2["match"]["date"] == "2026-10-15"
assert st2["cancelados"][0]["bets"][0]["bettor"] == "x", "the BioBet history keeps a cancelled game's bets"

# BioBet mercados: the losing side's coins go to the winners by stake and no coin is lost; the list, the tabela and the
# draft decide; nobody bets on their own name, the list stays out of jogadores, a capitao bettor can't captain early.
import datetime as _dt
from server import kickoff, new_mercado, bet_mercado, pay, settle
D15 = "2026-10-15"
K = kickoff(D15)
assert K == _dt.datetime(2026, 10, 15, 21, 30, tzinfo=_dt.timezone.utc).timestamp() and kickoff(D15, "20:00") == K + 5400
t0, cash = K - 3 * 86400, {n: 50 for n in "abcdef"} | {"pobre": 2}
st3 = new_state()
st3["match"].update(date=D15, confirmed=["Zé", "e"])
for kind, by, body, now in (("lista", "Zé", {"p": "Zé"}, t0), ("lista", "a", {"p": "Zé"}, t0), ("capitao", "a", {"h": 8}, t0),
                            ("jogadores", "a", {"n": 1}, t0), ("x", "a", {}, t0), ("lista", "a", {"p": "Rafo", "min": 0}, t0),
                            ("jogo", "a", {}, K - 86400)):
    try:
        new_mercado(st3, kind, by, body, now); raise AssertionError((kind, body))
    except ValueError:
        pass
m1 = new_mercado(st3, "lista", "a", {"p": "Rafo", "min": 3}, t0)
assert m1["text"] == "Rafo vai entrar na lista do jogo de 15/10" and m1["fecha"] == K - 86400
try:
    new_mercado(st3, "lista", "b", {"p": "Rafo"}, t0); raise AssertionError("same bet twice")
except ValueError:
    pass
for who, side, stake in (("a", "sim", 5), ("d", "sim", 3), ("b", "não", 3), ("c", "não", 4)):
    bet_mercado(st3, cash, who, 1, side, stake, t0)
for who, side, stake, now in (("e", "sim", 2, t0), ("e", "talvez", 5, t0), ("a", "não", 5, t0), ("Rafo", "sim", 5, t0),
                              ("pobre", "sim", 3, t0), ("e", "sim", 5, K - 86400), ("e", "sim", 3.5, t0)):
    try:
        bet_mercado(st3, cash, who, 1, side, stake, now); raise AssertionError((who, side, stake))
    except ValueError:
        pass
assert balance(st3, cash, "a") == 45
assert [b["odds"] for b in m1["bets"]] == [None, None, 3.51, 2.05], "the pot's odds when each one bet"
note = pay(st3, m1, "sim", t0)  # pot 15: the house 1, the losers' other 6 to stakes 5 and 3 (3.75, 2.25), the extra coin to a
assert [b["pay"] for b in m1["bets"]] == [9, 5, 0, 0] and sum(x["amount"] for x in st3["ledger"]) == -1 == -st3["casa"], m1["bets"]
assert m1["status"] == "sim" and m1["casa"] == 1 and "a, d levam 6 moedas, a casa 1." in note
s8 = new_state()  # the house never takes more than the losers put in
m8 = {"id": 8, "text": "x", "bets": [{"who": "a", "side": "sim", "stake": 39}, {"who": "b", "side": "não", "stake": 1}]}
pay(s8, m8, "sim", t0)
assert [b["pay"] for b in m8["bets"]] == [39, 0] and s8["casa"] == 1
m2 = new_mercado(st3, "jogadores", "a", {"n": 3}, t0)
try:
    bet_mercado(st3, cash, "e", m2["id"], "sim", 1, t0); raise AssertionError("on the list")
except ValueError:
    pass
bet_mercado(st3, cash, "a", m2["id"], "sim", 2, t0)
m3 = new_mercado(st3, "capitao", "b", {"h": 6}, t0)
m4 = new_mercado(st3, "capitao", "b", {"h": 24}, t0)
m5 = new_mercado(st3, "jogo", "b", {}, t0)
bet_mercado(st3, cash, "b", m5["id"], "não", 2, t0)
assert settle(st3, t0) == [] and m2["status"] == "aberta"
assert settle(st3, K - 86400) == [None] and (m3["status"], m4["status"]) == ("aberta", "não"), "24 h before: no captains yet"
st3["match"]["caps_at"] = K - 10 * 3600
st3["match"]["confirmed"].append("Rafo")
settle(st3, K)
assert (m2["status"], m3["status"], m5["status"]) == ("sim", "sim", "aberta") and m2["back"] and balance(st3, cash, "a") == 54
st3["played"].append({"date": D15})
settle(st3, K + 3600)
assert m5["status"] == "sim" and m5["back"] and balance(st3, cash, "b") == 47
m6 = {"id": 9, "kind": "jogo", "date": "2026-10-22", "kick": kickoff("2026-10-22"), "bets": [], "status": "aberta"}
st3["mercados"].append(m6)
settle(st3, m6["kick"] + 86400)
assert m6["status"] == "aberta" and settle(st3, m6["kick"] + server.GRACE + 1) == [None] and m6["status"] == "não"
st4 = new_state()  # far in the future, so the real clock is before the captains' deadline
st4["match"].update(date="2099-10-15", confirmed=["a", "b", "c"])
m7 = new_mercado(st4, "capitao", "c", {"h": 12})
bet_mercado(st4, cash, "a", m7["id"], "não", 1)
try:
    apply(st4, "draft_start", {"captains": ["a", "b"]}); raise AssertionError("a bet on the captains' deadline")
except ValueError as e:
    assert "a apostou" in str(e)
apply(st4, "draft_start", {"captains": ["b", "c"]})
assert st4["match"]["caps_at"]
apply(st4, "new_match", {"date": "2099-10-22"})
assert server.snap(st4, "2099-10-15")["caps_at"] and server.snap(st4, "2099-10-15")["confirmed"] == ["a", "b", "c"]

# Sheet rows -> games: d/m dates, cup without date, stray 3rd team, bogus score cell, SOMBRA.
row = lambda ano, n, gf, ga, res, season, data, team, name, gl="", ast="", og="", cap="": \
    [ano, "", str(n), "", "", "", str(gf), str(ga), res, "", season, data, team, name, gl, ast, og, cap]
csv_text = "\n".join(",".join(r) for r in [row("Ano", "x", "", "", "", "", "", "", "")] + [
    row("2026", 300, 2, 1, "V", "2026/2", "1/10", "AXOLOTES", "Victor", "2", "", "", "1"),
    row("2026", 300, 1, 2, "D", "2026/2", "1/10", "Time B", "SOMBRA", "", "", "1"),
    row("2026", 300, 2959, 0, "V", "2026/2", "1/10", "lixo", "Ghost", "9"),
    row("2019", 1, 99, 6, "V", "2019/1", "27/05/2019", "PAVÕES", "Bruno", "3"),
    row("2019", 1, 6, 99, "D", "2019/1", "27/05/2019", "PAPAGAIOS", "Dan", "6"),
    row("2025", 280, 0, 0, "E", "IV COPA", "", "LOBOS", "Matte"),
    row("2025", 280, 0, 0, "E", "IV COPA", "", "URSOS", "Guih"),
    row("1899", 301, 0, 0, "", "", "", "", ""),
])
sg = sheet_games(csv_text)
assert [g["n"] for g in sg] == [1, 280, 300], sg
assert sg[0]["date"] == "2019-05-27" and [(t["gf"], t["ga"], t["res"]) for t in sg[0]["teams"]] == [(3, 6, "D"), (6, 3, "V")]
assert sg[1]["date"] is None and sg[1]["season"] == "IV COPA"
assert sg[2]["date"] == "2026-10-01" and [t["name"] for t in sg[2]["teams"]] == ["AXOLOTES", "Time B"]
assert sg[2]["teams"][0]["players"] == [["Victor", 2, 0, 0, 1]] and sg[2]["teams"][1]["players"][0][0] == "Sombra"

# Once the sheet has a site-recorded game's date, the sheet's copy wins (no double goals/coins).
assert unsynced(st["played"], sg) == st["played"]
assert unsynced(st["played"], sg + [{**g, "n": 302}]) == []

# Odds match the original numpy/sklearn BioBet model.
try:
    sys.path.insert(0, "L:/GAB/Agents/Handoffs/claude-biobet/2026-10-03")
    import biobet
    m = biobet.Model().fit(biobet.load_games())
    a, b = ["Victor", "Regio", "Dan", "Matte", "Rafo"], ["Canova", "Guih", "Andrei", "Fachel", "Douglas"]
    ref, got = m.odds(a, b), odds(DATA["model"], a, b)
    assert all(abs(ref[k] - got[k]) < 0.03 for k in "AEB"), (ref, got)
except ImportError:
    print("(skipped odds parity: no numpy/sklearn)")

# login cookie: round trip, tamper, expiry, bound to the IP; PIN lockout
assert server.session(sign("Dan", "1.1.1.1", now=server.STALE_BEFORE - 1)) is None, "signed under the stale phones.json"
server.STALE_BEFORE = 0
t = sign("Gab", "1.1.1.1", now=1000)
assert signed_name(t, "1.1.1.1", now=1001) == "Gab"
assert signed_name(t, "2.2.2.2", now=1001) is None and server.session(t, now=1001) == ("Gab", "1.1.1.1", ""), "new IP: log in again"
assert signed_name(t[:-1] + ("0" if t[-1] != "0" else "1"), "1.1.1.1", now=1001) is None
assert signed_name(sign("Dan", "1.1.1.1", now=1000).split(".")[0] + "." + t.split(".")[1], "1.1.1.1", now=1001) is None
assert signed_name(t, "1.1.1.1", now=1000 + server.SESSION_DAYS * 86400 + 1) is None
assert signed_name("", "", now=1) is None and signed_name("lixo", "", now=1) is None
import base64 as _b64, hashlib as _hl, hmac as _hm, json as _js  # an old name + PIN cookie (no IP) is logged out
_old = _b64.urlsafe_b64encode(_js.dumps(["Gab", 9e9]).encode()).decode()
assert server.session(_old + "." + _hm.new(server.KEY, _old.encode(), _hl.sha256).hexdigest()) is None
_mid = _b64.urlsafe_b64encode(_js.dumps(["Zé Zap", 9e9, "1.1.1.1"]).encode()).decode()  # nor one from before the "~" rule (no number)
assert server.session(_mid + "." + _hm.new(server.KEY, _mid.encode(), _hl.sha256).hexdigest()) is None

# "stay in when the IP changes", asked after the login: only a valid cookie from this IP turns into an any-IP one
t = server.sign("Fischer", "1.1.1.1", "pk1")
k = server.keep_token(t, "1.1.1.1")
assert server.signed(k, "8.8.8.8") == server.signed(t, "1.1.1.1"), "same member, now from any IP"
assert server.keep_token(t, "9.9.9.9") is None, "a cookie stolen to another IP can't be widened"
assert server.keep_token(t[:-1] + ("1" if t[-1] == "0" else "0"), "1.1.1.1") is None and server.keep_token("", "1.1.1.1") is None

# WhatsApp login: strict numbers, the bot's answers, the per-number limit
vp = server.valid_phone
assert vp("(51) 90000-0003") == vp("+55 51 90000-0003") == vp("5551900000003") == "5551900000003"
assert vp("90000-0003") is None and vp("51 0000-0003") is None and vp("(01) 90000-0003") is None, "no DDD / no 9 / bad DDD"
assert vp("+1 415 555 2671") == "14155552671" and vp("+351912345678") == "351912345678"
assert vp("51900000003a") is None and vp("+5551 0000 0003") is None and vp("") is None and vp("+1234") is None
bot = {"/login": {"ok": True}}
server.bot_post = lambda route, obj: bot[route]
out, code = server.login_start("(51) 90000-0003", "1.1.1.1", now=100)
assert code == 200 and set(out) == {"id"} and server.LOGINS[out["id"]]["phone"] == "5551900000003", "the code never reaches the page"
real = server.LOGINS[out["id"]]["code"]
assert server.login_status(out["id"], "1.1.1.1", now=101) == (None, None, ""), "waiting for the code"
assert server.login_code(out["id"], "1.1.1.1", "x" + real)[1] == 400 and server.login_status(out["id"], "1.1.1.1", now=101)[0] is None
assert server.login_code(out["id"], "9.9.9.9", real)[1] == 404, "another IP can't type it"
assert server.login_code(out["id"], "1.1.1.1", real) == ({"ok": True}, 200)
assert server.login_status(out["id"], "9.9.9.9", now=101)[1], "another IP can't pick it up"
assert server.login_status(out["id"], "1.1.1.1", now=100 + 601)[1], "expired"
QUEM0, server.PHONES, server.HERE, server.QUEM = server.QUEM, Path(tempfile.mkdtemp()) / "none.json", Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp()) / "q.json"
assert server.login_status(out["id"], "1.1.1.1", now=101) == ("~Tel 0003", None, server.phone_pk("5551900000003")), "a number no list knows: unverified"
assert server.login_status(out["id"], "1.1.1.1", now=101)[1], "used once"
bot["/login"] = {"ok": False, "error": "esse número não está no grupo do BioFut"}
assert server.login_start("+1 415 555 2671", "1.1.1.1") == ({"error": bot["/login"]["error"]}, 502)
assert [server.login_start("51900000003", "1.1.1.1")[1] for _ in range(3)] == [502, 502, 429], "3 an hour per number"
assert server.login_start("51 9", "1.1.1.1")[1] == 400
server.PHONES, server.HERE, server.bot_post, server.QUEM = PHONES0, HERE0, BOT_POST0, QUEM0
assert not any(too_many_fails("1.2.3.4", failed=True) for _ in range(9)) and too_many_fails("1.2.3.4", failed=True)
assert not too_many_fails("5.6.7.8")

# Review queue, in a temp dir: inbox -> pending -> approve / reject / auto-release after 6 h.
import json, tempfile, time
from pathlib import Path
tmp = Path(tempfile.mkdtemp())
server.REVIEW, server.INBOX, server.AVISOS, server.STATE, server.WIKI = tmp / "review.json", tmp / "inbox", tmp / "avisos.jsonl", tmp / "state.json", tmp / "wiki"
server.INBOX.mkdir(); server.WIKI.mkdir()
for f in ("member.json", "public.json"):
    (server.WIKI / f).write_text(json.dumps({"pages": [{"slug": "p", "bits": ["old", "keep"]}], "bits": {"old": {"title": "o"}, "keep": {"title": "k"}}, "chats": {}}))
wiki_item = {"kind": "wiki", "title": "Wiki: 1 entra, 1 sai", "payload": {
    "ops": [{"page": "p", "order": ["new", "keep"]}], "bits": {"new": {"title": "n", "ref": "c1"}}, "chats": {"c1": [["10:00", "Dan", "kkk"]]}}}
sumula = {"kind": "sumula", "title": "Súmula 2026-10-08", "payload": {"date": "2026-10-08", "games": [{"team_a": "A", "team_b": "B", "score_a": 2, "score_b": 1,
          "players_a": [{"name": "Victor", "goals": 2, "assists": 0, "own_goals": 0}], "players_b": [{"name": "Dan", "goals": 0, "assists": 1, "own_goals": 1}]}]}}
for i, it in enumerate((wiki_item, sumula, {"kind": "lixo"})):
    (server.INBOX / f"{i}.json").write_text(json.dumps(it))
notes = server.review_tick(now=1000)
assert len(notes) == 3 and "inválido" in notes[2] and not list(server.INBOX.iterdir())
assert [x["status"] for x in server.load_review()] == ["pending", "pending"]
server.review_act(1, "approve")
m, p = (json.loads((server.WIKI / f).read_text()) for f in ("member.json", "public.json"))
assert m["pages"][0]["bits"] == ["new", "keep"] and set(m["bits"]) == {"new", "keep"} and m["bits"]["new"]["ref"] == "c1" and "c1" in m["chats"]
assert "ref" not in p["bits"]["new"] and "old" not in p["bits"]
try:
    server.review_act(1, "reject"); raise AssertionError("decided twice")
except ValueError:
    pass
assert server.review_tick(now=1000 + server.COOLDOWN - 1) == []
assert "6 h" in server.review_tick(now=1000 + server.COOLDOWN)[0]
g = server.load_state()["played"][0]
assert g["date"] == "2026-10-08" and g["teams"][1]["players"] == [["Dan", 0, 1, 1, 0]] and [t["res"] for t in g["teams"]] == ["V", "D"]
assert [x["status"] for x in server.load_review()] == ["approved", "auto"] and "payload" not in server.log_view()[0]

# Listas and plain avisos through the inbox: listas waits like the rest, an aviso only goes to the group.
(server.INBOX / "a.json").write_text(json.dumps({"kind": "aviso", "title": "", "payload": {"text": "12 fotos legendadas"}}))
(server.INBOX / "b.json").write_text(json.dumps({"kind": "listas", "title": "Listas", "payload": {"people": [], "flake": 0.3}}))
server.LISTAS = tmp / "listas.json"
notes = server.review_tick(now=5000)
assert notes[0] == "🤖 12 fotos legendadas" and "#3 Listas" in notes[1] and len(server.load_review()) == 3
server.review_act(3, "approve")
assert json.loads(server.LISTAS.read_text())["flake"] == 0.3

# Google Sheet changes wait in the queue: one pending item updated in place, approve swaps the games, reject sticks.
server.SHEET_CACHE = tmp / "sheet.csv"
server.use_games(sg)
assert server.propose_sheet(csv_text) is None  # same games: nothing to review
csv2 = csv_text.replace(",".join(row("2026", 300, 2, 1, "V", "2026/2", "1/10", "AXOLOTES", "Victor", "2", "", "", "1")),
                        ",".join(row("2026", 300, 2, 1, "V", "2026/2", "1/10", "AXOLOTES", "Victor", "3", "", "", "1")))
csv3 = csv2 + "\n" + "\n".join(",".join(r) for r in [row("2026", 302, 1, 0, "V", "2026/2", "8/10", "A", "Dan", "1"),
                                                     row("2026", 302, 0, 1, "D", "2026/2", "8/10", "B", "Guih")])
note = server.propose_sheet(csv2, now=9000)
assert "#4" in note and "~ #300 2026-10-01 AXOLOTES 2x1 Time B" in note, note
assert server.propose_sheet(csv2) is None  # already waiting
assert "atualizado" in server.propose_sheet(csv3) and "+ #302" in server.load_review()[-1]["payload"]["diff"][0]
assert len(server.load_review()) == 4 and server.load_review()[-1]["created"] == 9000  # the 6 h clock didn't restart
assert server.DATA["games"][2]["teams"][0]["players"][0][1] == 2  # nothing live yet
server.review_act(4, "approve")
assert [g["n"] for g in server.DATA["games"]] == [1, 280, 300, 302] and server.DATA["games"][2]["teams"][0]["players"][0][1] == 3
assert server.SHEET_CACHE.read_text() == csv3 and "csv" not in server.load_review()[-1]["payload"]
assert server.propose_sheet(csv3) is None
assert "#5" in server.propose_sheet(csv2)  # someone deletes game 302 again
server.review_act(5, "reject")
assert server.propose_sheet(csv2) is None and len(server.load_review()) == 5  # a rejected copy isn't proposed again
assert "#6" in server.propose_sheet(csv_text)
assert "descartada" in server.propose_sheet(csv3) and server.load_review()[-1]["status"] == "obsolete"
assert "#7" in server.propose_sheet(csv_text, now=1)
assert "6 h" in server.review_tick(now=1 + server.COOLDOWN)[0] and len(server.DATA["games"]) == 3  # unreviewed: ships itself

# Súmula photo from the bot: a meme is dropped, a match sheet joins the queue with its photo; release pushes it to the sheet hook.
import http.server, threading, sumula
server.REVIEW_MEDIA, server.OCR_BUDGET = tmp / "media", tmp / "ocr.json"
fake = {"is_sumula": True, "date": None, "games": [{"team_a": "Preto", "team_b": "Verde", "score_a": None, "score_b": None,
        "players_a": [{"name": "VICTOR", "goals": 4, "captain": True}], "players_b": [{"name": "Hanauer", "goals": 1}]}]}
sumula.ask = lambda img, roster: fake if img == b"sheet" else {"is_sumula": False}
server.ocr_photo(b"meme", "2026-10-09", "Fulano")
assert not list(server.INBOX.glob("*.json"))
server.ocr_photo(b"sheet", "2026-10-09", "Fulano")
server.review_tick(now=5000)
it = server.load_review()[-1]
p = it["payload"]
assert it["kind"] == "sumula" and p["date"] == "2026-10-09" and (server.REVIEW_MEDIA / p["image"]).exists(), it
assert p["games"][0]["score_a"] == 4 and p["games"][0]["players_a"][0]["written"] == "VICTOR" and p["games"][0]["players_a"][0]["name"] == "Victor", p  # name mapped to the sheet's spelling
got = []
real_push, server.sheet.ID = server.sheet.push, "fake-id"
server.sheet.push = lambda games: got.append(games) or [300]
server.review_act(it["id"], "approve")
it = server.load_review()[-1]
assert it["sheet"] == "ok: jogo 300" and got[0][0]["teams"][0]["players"][0][4] == 1, (it, got)  # captain flag reaches the sheet
assert server.load_state()["played"][-1]["sumula"] == p["image"] and (server.WIKI / "media" / p["image"]).exists()  # #34: the open game shows it
server.sheet.push = lambda games: (_ for _ in ()).throw(ValueError("Sheets API 400"))  # the game stays on the site, the failure is reported
assert server.push_sheet([]).startswith("falhou") and "planilha não foi atualizada" in server.AVISOS.read_text(encoding="utf-8")
server.ocr_photo(b"sheet", "2026-10-09", "Fulano")  # same photo again: refused by the budget, no queue item
assert not list(server.INBOX.glob("*.json"))
server.sheet.push, server.sheet.ID = real_push, ""
# Public photos: only what public.json lists; the cache follows the file.
assert server.public_media() == set()
(server.WIKI / "public.json").write_text(json.dumps({"media": ["IMG-1.jpg"]}))
import os; os.utime(server.WIKI / "public.json", (1, 1))
assert server.public_media() == {"IMG-1.jpg"}

# Phone -> name: hashed, any format of the same number matches, other numbers don't.
salt = "00" * 16
server.PHONES = tmp / "phones.json"
server.PHONES.write_text(json.dumps({"salt": salt, "map": {server.phone_key("+55 51 99876-5432", salt): "Dan"}}))
assert server.phone_name("(51) 99876-5432") == "Dan" and server.phone_name("9876-5432") == "Dan"
assert server.phone_name("51 99876-5433") is None and server.phone_name("123") is None
assert server.phone_lookup("(51) 99876-5432") == ("Dan", None)  # older phones.json without "how"
k = server.phone_key("51 99876-5432", salt)
server.PHONES.write_text(json.dumps({"salt": salt, "map": {k: "Dan"}, "how": {k: "contato"}}))
assert server.phone_lookup("99876-5432") == ("Dan", "contato") and server.phone_lookup("99876-0000") == (None, None)
# Roles: Gab by his number (his own export has no number of his, so his name is phones.json's "me"), the Conselho by name,
# "~" for a number no list knows. Who-is-who: a doubtful list name is answered by whoever wrote it or by the staff, a merge only
# by the staff, a "~" member claims a tabela name and the staff confirms it; the cookie then carries that name.
server.ADMIN_PHONE, server.QUEM, server.HERE = "+55 51 91234-5678", tmp / "quem.json", tmp
gab, ze = server.phone_pk("51 91234-5678"), server.phone_pk("(51) 98888-7777")
assert gab and gab != ze and server.phone_pk("123") == ""
assert server.role_of("Gabi Steinhaus", gab) == "admin" and server.role_of("Leo Saul", ze) == "conselho"
assert server.role_of("~Leo Saul", ze) == "membro" and server.role_of(None, "") is None
server.PHONES.write_text(json.dumps({"salt": salt, "map": {k: "Dan"}, "me": "Gabi Steinhaus", "alias": {"Mk": "MK"}, "suggest": [["Fischer", "Lucas Fischer"]],
    "switches": [{"name": "Dan", "old": "1111", "new": "2222", "date": "2024-01-01", "at_once": False}],
    "dubious": [{"id": "2026-10-01:victor", "date": "2026-10-01", "name": "Victor", "wrote": "vitinho", "by": "Dan", "options": ["Victor", "Guih", "Sombra"]}]}))
bot = {"/login": {"ok": True}}
server.bot_post = lambda route, obj: bot[route]
lid = server.login_start("+55 51 91234-5678", "1.1.1.1")[0]["id"]
server.login_code(lid, "1.1.1.1", server.LOGINS[lid]["code"])
assert server.login_status(lid, "1.1.1.1") == ("Gabi Steinhaus", None, gab), "Gab gets his tabela name"
assert [x["id"] for x in server.quem_view("Dan", "", "membro")["items"]] == ["2026-10-01:victor"] and server.quem_view("Guih", "", "membro")["items"] == []
assert "switches" not in server.quem_view("Andrei", "", "conselho") and server.quem_view("Gabi Steinhaus", gab, "admin")["switches"][0]["old"] == "1111"
for who, body in (("Guih", {"id": "2026-10-01:victor", "choice": "Guih"}), ("Dan", {"id": "2026-10-01:victor", "choice": "Fulano"}),
                  ("Dan", {"merge": "Fischer", "to": "Lucas Fischer", "ok": True}), ("Dan", {"claim": "Victor"}), ("~Zé", {"claim": "Ninguém"}),
                  ("~Zé", {"claim": ["Victor"]}), ("~Zé", {"ask": ze, "ok": True})):
    try:
        server.quem_act(who, ze if who[0] == "~" else "", False, body); raise AssertionError((who, body))
    except ValueError:
        pass
server.quem_act("Dan", "", False, {"id": "2026-10-01:victor", "choice": "Sombra"})
server.quem_act("Andrei", "", True, {"merge": "Fischer", "to": "Lucas Fischer", "ok": True})
assert server.name_fixes() == ({"Mk": "MK", "Fischer": "Lucas Fischer"}, {"2026-10-01|Victor": "Sombra"})
assert server.signed(server.sign("Fischer", "1.1.1.1", ze), "1.1.1.1")[0] == "Lucas Fischer", "merged after the login: the new name"
tok = server.sign("~Zé", "1.1.1.1", ze)
assert server.signed(tok, "1.1.1.1") == ("~Zé", ze) and "Victor" in server.quem_act("~Zé", ze, False, {"claim": "Victor"})
assert server.quem_view("~Zé", ze, "membro")["asked"] == "Victor" and server.quem_view("Andrei", "", "conselho")["asks"][0]["known"] is False
server.quem_act("Andrei", "", True, {"ask": ze, "ok": True})
assert server.signed(tok, "1.1.1.1") == ("Victor", ze) and server.quem_view("Victor", ze, "membro")["asked"] is None, "confirmed: same cookie, tabela name"
server.ADMIN_PHONE, server.HERE = "", HERE0
# Site sign-up -> bot /draft/join with the draft's captains; a repeat sign-up sends nothing.
sent = []
server.bot_post = lambda route, obj: sent.append((route, obj))
st = new_state()
for n in ["Victor", "Canova", "Zé"]:
    before = server.heads(st["match"]); apply(st, "signup", {"name": n}); server.join_ping(st, before)
apply(st, "draft_start", {"captains": ["Victor", "Canova"]})
# A late name while the draft runs waits on both captains; a repeat sign-up sends nothing; both yes -> on the list, draft restarts.
before = server.heads(st["match"]); apply(st, "signup", {"name": "Bia"}); server.join_ping(st, before)
before = server.heads(st["match"]); apply(st, "signup", {"name": "bia"}); server.join_ping(st, before)
time.sleep(0.2)
assert sent[0] == ("/draft/join", {"player": "Victor", "count": 1, "captains": []}), sent
assert sent[3] == ("/draft/join", {"player": "Bia", "count": 3, "captains": ["Victor", "Canova"], "pending": True}) and len(sent) == 4, sent
d = st["match"]["draft"]; d["first"] = "Victor"
apply(st, "draft_pick", {"captain": "Victor", "player": "Zé"}); server.pick_ping(st, "Victor")
time.sleep(0.2)
assert sent[4] == ("/draft/pick", {"captain": "Victor", "player": "Zé", "turn": "Canova", "teams": {"Victor": ["Victor", "Zé"], "Canova": ["Canova"]}, "available": []}), sent[4]
assert sent[5][0] == "/group" and "Victor escolheu Zé" in sent[5][1]["text"], sent[5]
apply(st, "draft_admit", {"captain": "Victor", "player": "Bia", "ok": False})
assert d["pending"] == {} and "Bia" not in st["match"]["confirmed"]
apply(st, "signup", {"name": "Bia"}); apply(st, "draft_admit", {"captain": "Victor", "player": "Bia"}); apply(st, "draft_admit", {"captain": "Victor", "player": "Bia"})
assert d["pending"] == {"Bia": ["Victor"]} and d["teams"]["Victor"] == ["Victor", "Zé"], "one captain is not enough"
apply(st, "draft_admit", {"captain": "Canova", "player": "Bia"})
assert "Bia" in st["match"]["confirmed"] and d["teams"] == {"Victor": ["Victor"], "Canova": ["Canova"]} and d["first"] == "Victor" and "Bia entrou" in d["redraft"], d
assert "Redraft" in server.draft_news(st, "draft_admit", None) and "redraft" not in d

# Activity log: the IP never reaches the file, the visitor id holds for a day and changes the next, a login's phone is not logged.
server.EVENTS = tmp / "events.jsonl"
server.log_event("view", None, "203.0.113.9", True, p="/#/tabela", d="")
assert "203.0.113.9" not in server.EVENTS.read_text(encoding="utf-8")
e = server.recent_events()[-1]
assert e["ev"] == "view" and e["mob"] == 1 and e["p"] == "/#/tabela" and "d" not in e, e
assert server.visitor("203.0.113.9", "2026-10-08") == server.visitor("203.0.113.9", "2026-10-08") != server.visitor("203.0.113.9", "2026-10-09")
class Req:  # just enough of a handler for track()
    path, body, headers = "/api/login/start", {"phone": "(51) 99876-5432"}, {"User-Agent": "Mobile"}
    user = lambda self: None
    ip = lambda self: "203.0.113.9"
    mobile = server.Handler.mobile
server.Handler.track(Req(), {"ok": True}, 200)
assert "99876" not in server.EVENTS.read_text(encoding="utf-8") and server.recent_events()[-1]["ev"] == "login/start"
# Sheet copy page (#/planilha): a site game as the DATABASE tab's L..R cells, zeros blank.
g = {"date": "2026-10-01", "teams": [{"name": "Azul", "players": [["Victor", 2, 0, 0, 1], ["Dan", 0, 1, 1, 0]]}]}
assert server.sheet_rows(g) == [["1/10/26", "Azul", "Victor", "2", "", "", "1"], ["1/10/26", "Azul", "Dan", "", "1", "1", ""]]
# Member page: a profile is trimmed and only the given name's; the tabela queue shows pending súmulas without the photo.
server.PROFILES = tmp / "profiles.json"
assert server.set_profile("Victor", {"nick": "  O   Mito ", "status": "x" * 200}) == {"nick": "O Mito", "status": "x" * 80}
assert server.set_profile("Victor", {"hide": 1}) == {"nick": "O Mito", "status": "x" * 80, "hide": True}, "only the fields sent"
assert server.set_profile("Victor", {"nick": "", "status": "", "hide": False}) == {} and server.load_profiles() == {}
item = {"id": 7, "kind": "sumula", "title": "Súmula", "status": "pending", "created": 1000.0,
        "payload": {"date": "2026-10-08", "image": "a.jpg", "games": [{"team_a": "Azul", "score_a": 2, "team_b": "Rosa", "score_b": 1,
                    "players_a": [{"name": "Victor", "goals": 2}], "players_b": [{"name": "Dan", "assists": 1}]}]}}
f = server.fila([item, {**item, "id": 8, "kind": "wiki"}, {**item, "id": 9, "status": "approved", "created": 0.0}], now=1000.0 + 8 * 86400)
assert [x["id"] for x in f] == [7] and f[0]["games"][0]["teams"][1] == {"name": "Rosa", "gf": 1, "players": [["Dan", 0, 1]]}, f
assert "image" not in str(f) and f[0]["release"] == 1000.0 + server.COOLDOWN
# A súmula without a single goal (a lineup photo: the OCR fills null scores from the tallies, so 0 x 0) never ships on its own.
lineup = {"kind": "sumula", "title": "Escalação", "payload": {"date": "2026-10-08", "games": [
    {"team_a": "Azul", "score_a": 0, "team_b": "Rosa", "score_b": 0, "players_a": [{"name": "Victor"}], "players_b": [{"name": "Dan"}]}]}}
(server.INBOX / "d.json").write_text(json.dumps(lineup))
assert any("Sem nenhum gol" in n for n in server.review_tick(now=1000))
server.review_tick(now=9e9)
it = next(x for x in server.load_review() if x["title"] == "Escalação")
assert it["status"] == "pending" and server.fila([it], now=2000)[0]["release"] is None and server.held(it)
assert not server.held(item), "2 x 1: the 6 h clock as before"
# The Conselho decides data (súmulas, tabela, listas), not the wiki.
(server.INBOX / "c.json").write_text(json.dumps(wiki_item))
server.review_tick(now=9e9)
try:
    server.review_act(server.load_review()[-1]["id"], "approve", kinds=server.DATA_KINDS); raise AssertionError("the Conselho decided a wiki item")
except ValueError as e:
    assert "Gab" in str(e)
# The group's sign-up list fills Jogo da semana: tabela spellings (and aliases), site sign-ups stay, the first copy's
# poster owns the list, a truncated copy removes nobody, next week's list waits for this week's game.
import datetime as _dt
brt = lambda m, d: _dt.datetime(2026, m, d, 12, tzinfo=_dt.timezone(_dt.timedelta(hours=-3))).timestamp()
lst = lambda date, *ns: f"🚨 [QUINTA - {date} 18:30]🚨\n\nGoleiro 1 - {ns[0] if ns else ''}\nGoleiro 2 -\n\n" + \
    "".join(f"{i} - {n}\n" for i, n in enumerate([*ns[1:], *[""] * 8], 1)) + "\nSuplência:\n- Vavá\n"
G0 = server.DATA["games"]
server.use_games([{"n": 1, "season": "2026/2", "date": "2026-10-01", "teams": [
    {"name": "A", "gf": 1, "ga": 0, "res": "V", "players": [["Leo Saul", 1, 0, 0, 1], ["Mk", 0, 0, 0, 0]]},
    {"name": "B", "gf": 0, "ga": 1, "res": "D", "players": [["Dan", 0, 0, 0, 1], ["Tito", 0, 0, 0, 0]]}]}])
st = new_state()
st["match"].update(date="2026-10-08", confirmed=["Victor"])  # last week's, never closed here
assert server.sync_list(st, "oi", brt(10, 9), "Andrei") is None and st["last_list"]["why"] == "não é uma lista"
assert server.sync_list(st, lst("15/10"), brt(10, 9), "Andrei") == {"date": "2026-10-15", "added": [], "removed": []}
assert st["match"]["lista"]["hora"] == "18:30" and server.lista.parse_list(lst("15/10").replace(" 18:30", ""), brt(10, 9))["hora"] == ""
assert st["match"]["confirmed"] == [] and st["match"]["lista"]["owner"] == "Andrei"
apply(st, "signup", {"name": "Leo Saul"})
r = server.sync_list(st, lst("15/10", "Zeca", "Saul", "dan", "mk", "Fulano", "tito"), brt(10, 10), "Rafo")
assert r["added"] == ["Zeca", "Dan", "MK", "Fulano", "Tito"] and st["match"]["confirmed"][0] == "Leo Saul", r
import copy as _copy  # '(C)' on the list: the players' captains, preselected on the draft and DM'd by the bot
c = _copy.deepcopy(st); server.sync_list(c, lst("15/10", "Zeca", "Saul (C)", "dan", "mk (c)", "Fulano", "tito"), brt(10, 10), "Rafo")
assert c["match"]["lista"]["captains"] == ["Leo Saul", "MK"], c["match"]["lista"]
assert st["match"]["lista"]["owner"] == "Andrei" and st["match"]["lista"]["by"] == "Rafo" and st["match"]["lista"]["waiting"] == ["Vavá"]
assert server.sync_list(st, lst("15/10", "Zeca", "Saul", "dan", "mk", "tito"), brt(10, 11), "Rafo")["removed"] == ["Fulano"]
r = server.sync_list(st, lst("15/10", "Zeca", "Novo"), brt(10, 11), "Rafo")
assert r == {"date": "2026-10-15", "added": ["Novo"], "removed": []} and "Dan" in st["match"]["confirmed"], "a truncated copy"
assert st["last_list"]["why"].startswith("aplicada: +1 -0, ninguém saiu (4 nomes"), st["last_list"]
assert server.sync_list(st, lst("08/10", "Zeca"), brt(10, 12), "Rafo") is None and st["last_list"]["why"] == "lista de um jogo antigo", "an old list"
resched = _copy.deepcopy(st)  # no draft, no bets: the game was rescheduled (new date, list reset), so the new list replaces it
server.sync_list(resched, lst("17/10", "Zeca", "Nando"), brt(10, 14), "Dan")
assert resched["match"]["date"] == "2026-10-17" and resched["match"]["confirmed"] == ["Zeca", "Nando"], "rescheduled"
st["match"]["bets"].append({"id": "b1", "bettor": "Dan", "pick": "A", "stake": 1, "odds": 2})  # with a bet the game stands
assert server.sync_list(st, lst("22/10", "Zeca"), brt(10, 14), "Dan") is None and st["match"]["date"] == "2026-10-15", "game not played yet"
assert st["last_list"] == {"text": lst("22/10", "Zeca"), "at": int(brt(10, 14)), "by": "Dan", "date": "2026-10-22", "why": "próximo jogo: espera o de 2026-10-15"}
assert server.retry_list(st, brt(10, 14)) is None and st["match"]["date"] == "2026-10-15", "still held"
st["match"]["bets"].clear()
w = _copy.deepcopy(st)  # the hold cleared: the waiting list applies on the next read, nobody reposts
assert server.retry_list(w, brt(10, 14)) and w["match"]["date"] == "2026-10-22" and w["last_list"]["at"] == int(brt(10, 14))
assert server.retry_list(w, brt(10, 14)) is None, "applied once"
server.sync_list(st, lst("22/10", "Zeca", "dan", "tito"), brt(10, 16), "Rafo")
assert st["match"]["date"] == "2026-10-22" and st["match"]["confirmed"] == ["Zeca", "Dan", "Tito"] and st["match"]["lista"]["owner"] == "Dan"
apply(st, "draft_start", {"captains": ["Zeca", "Dan"]})
assert server.sync_list(st, lst("22/10", "Zeca"), brt(10, 17), "Rafo")["removed"] == ["Tito"], "drafted names stay"
# A stale number map (Leo Saul's number read "Victor"): the WhatsApp name flags it, and the owner heals when the opener
# posts again under the fixed map. An owner saved as a bare name (before 2026-10-10) has no number to match.
st = new_state()
server.sync_list(st, lst("29/10", "Zeca"), brt(10, 20), "Victor", "pk1", "Leonardo Saul")
assert st["match"]["lista"]["owner"] == "Victor" and st["last_list"]["check"] == "o número diz Victor, o WhatsApp diz Leonardo Saul (Leo Saul)"
server.sync_list(st, lst("29/10", "Zeca"), brt(10, 21), "Dan", "pk2", "Daniel")
assert st["match"]["lista"]["owner"] == "Victor" and "check" not in st["last_list"], "Daniel is Dan"
server.sync_list(st, lst("29/10", "Zeca"), brt(10, 21), "Leo Saul", "pk1", "Leonardo Saul")
assert st["match"]["lista"]["owner"] == "Leo Saul" and "check" not in st["last_list"] and st["owners"]["2026-10-29"] == ["Leo Saul", "pk1"]
st["owners"]["2026-10-29"] = "Victor"
server.sync_list(st, lst("29/10", "Zeca"), brt(10, 21), "Leo Saul", "pk1")
assert st["match"]["lista"]["owner"] == "Victor" and st["owners"]["2026-10-29"] == ["Victor", ""]
assert server.wa_check("~Fulano", "Leonardo Saul", ["Leo Saul"]) is None and server.wa_check("Dan", "", ["Leo Saul"]) is None
server.use_games(G0)
# #/eu: a member reads their own messages only, with a spelling merged since the phones.py build
server.MSGS = tmp / "mensagens.json"
assert server.my_messages("Rafo") == [] and server.name_fixes()[0].get("Mk") == "MK"
server.MSGS.write_text(json.dumps({"Rafo": [[2, "b"], [1, "a"]], "Mk": [[5, "x"]], "MK": [[3, "y"]]}), encoding="utf-8")
assert server.my_messages("Rafo") == [[1, "a"], [2, "b"]] and server.my_messages("MK") == [[3, "y"], [5, "x"]] and server.my_messages("Mk") == []
# A better photo (kind foto): held, then the page's lead for members only (not public media) and the player's site photo.
server.LEADS, server.PHOTOS = server.WIKI / "leads.json", tmp / "photos"
(server.WIKI / "media").mkdir(parents=True, exist_ok=True)
(server.WIKI / "media" / "u1.jpg").write_bytes(b"\xff\xd8x")
(server.INBOX / "f.json").write_text(json.dumps({"kind": "foto", "title": "Foto", "payload": {"page": "victor", "file": "u1.jpg", "player": "Victor"}}))
server.review_tick(now=9e9)
it = server.load_review()[-1]
assert it["status"] == "pending" and server.held(it)
server.review_act(it["id"], "approve", kinds=server.DATA_KINDS)
wd = lambda: {"pages": [{"slug": "victor", "photos": [{"file": "a.jpg", "legenda": "x"}]}]}
assert [x["file"] for x in server.with_leads(wd(), "Dan")["pages"][0]["photos"]] == ["u1.jpg", "a.jpg"]
assert server.with_leads(wd(), None)["pages"][0]["photos"] == wd()["pages"][0]["photos"] and (server.PHOTOS / "victor.jpg").exists()
# Transparência opt-out: the name goes, the numbers stay.
ls = server.hide_names({"people": [{"name": "Dan", "n": 3}], "trophies": {"x": [{"name": "Dan", "n": 1}]}, "games": [{"eventos": [["t", "Dan", "+"]]}]}, {"Dan"})
assert ls == {"people": [{"name": None, "n": 3}], "trophies": {"x": [{"name": None, "n": 1}]}, "games": [{"eventos": [["t", None, "+"]]}]}
# WhatsApp profile photos (#35): the bot's token, a number the site can name, a JPEG; members only.
import threading, urllib.request, base64 as b64
from http.server import ThreadingHTTPServer
server.AVATARS, server.BOT_TOKEN = tmp / "avatars", "tok"
httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{httpd.server_port}"
def call(path, body=None, token="tok", cookie=""):
    rq = urllib.request.Request(url + path, json.dumps(body).encode() if body is not None else None,
                                {"Content-Type": "application/json", "X-BioFut-Token": token, "Cookie": cookie})
    try:
        with urllib.request.urlopen(rq) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
jpg = b64.b64encode(b"\xff\xd8 face").decode()
for junk in (b"null", b"42", b"[1]", b'"x"'):  # #10: a JSON body that isn't an object is a 400, not a dropped connection
    for path, ck in (("/api/vote", "biofut=" + server.sign("Dan", "127.0.0.1")), ("/api/cancelado", "")):
        try: urllib.request.urlopen(urllib.request.Request(url + path, junk, {"X-BioFut-Token": "tok", "Cookie": ck})); code = 200
        except urllib.error.HTTPError as e: code = e.code
        assert code == (400 if "vote" in path else 200), (path, junk, code)
assert call("/api/avatar", {"phone": "5551998765432", "image": jpg}, token="no")[0] == 401
assert json.loads(call("/api/avatar", {"phone": "5551900000000", "image": jpg})[1]) == {"ok": False}, "nobody's number"
assert json.loads(call("/api/avatar", {"phone": "5551998765432", "image": jpg})[1]) == {"ok": True}
assert (server.AVATARS / "dan.jpg").read_bytes() == b"\xff\xd8 face"
assert b"Disallow: /api/" in call("/robots.txt")[1] and b"/wiki</loc>" in call("/sitemap.xml")[1]  # SEO: Google reads both
c = server.COPA_TS  # /copa: the countdown preview, then on to #/copa
assert b"faltam 2 dias" in server.copa_page(c - 86400 - 60) and b"falta 1 dia<" in server.copa_page(c - 60) and b"hoje" in server.copa_page(c + 60)
assert b"/og.png" in server.copa_page(c + 2 * 86400) and b'location.replace("/#/copa")' in call("/copa")[1]
assert call("/api/avatars")[0] == 403 and call("/api/avatar/dan.jpg")[0] == 403
me = "biofut=" + server.sign("Dan", "127.0.0.1")
assert json.loads(call("/api/avatars", cookie=me)[1]) == ["dan"] and call("/api/avatar/dan.jpg", cookie=me)[1] == b"\xff\xd8 face"
# #34: the night's photos are members only; "a súmula não bate" waits in the queue with the súmula photos until someone decides.
g = server.load_state()["played"][-1]
assert json.loads(call("/api/me", cookie=me)[1])["tour"] and not json.loads(call("/api/me")[1])["tour"]
assert "tour" not in json.loads(call("/api/tour", {}, cookie=me)[1]) and not json.loads(call("/api/me", cookie=me)[1])["tour"]
assert call("/api/jogos")[0] == 403 and json.loads(call("/api/jogos", cookie=me)[1]) == {}
assert json.loads(call("/api/jogo_errado", {"n": g["n"], "text": "o Victor fez 3"}, cookie=me)[1]) == {"ok": True}
server.review_tick(now=9e9)
it = server.load_review()[-1]
assert it["kind"] == "jogo" and it["status"] == "pending" and server.held(it) and it["payload"]["fotos"] == [g["sumula"]], it
assert "error" in json.loads(call("/api/jogo_errado", {"n": 1}, cookie="")[1])
# #36: a member buys a card with their points; it joins their deck once, and only for whoever is logged in.
server.card_prices = lambda games: {"Victor": 7, "Regio": 5}  # the few test games here give nobody 10 jogos
s0 = json.loads(call("/api/state")[1])
price = s0["prices"]["Victor"]
# The first buyer gets the cromada and must pick its +1 stat; the stat map stays private, the holder is public.
assert "cromada" in json.loads(call("/api/buy_card", {"card": "Victor"}, cookie=me)[1])["error"]
s1 = json.loads(call("/api/buy_card", {"card": "Victor", "stat": "VIT"}, cookie=me)[1])
assert s1["cards"]["Dan"] == ["Victor"] and s1["balances"]["Dan"] == s0["balances"]["Dan"] - price, s1.get("error")
assert s1["cromadas"] == {"Victor": {"by": "Dan", "stat": "VIT"}} and "cromo" not in s1, s1["cromadas"]
for bad, ck in (({"card": "Victor"}, me), ({"card": "Ninguém", "stat": "GOL"}, me), ({"card": "Regio", "stat": "GOL"}, "")):
    assert "error" in json.loads(call("/api/buy_card", bad, cookie=ck)[1]), bad
for bad, ck in (({"card": "Victor", "stat": "GOL"}, me), ({"card": "Regio", "stat": "GOL"}, "")):  # already picked; nobody's card
    assert "error" in json.loads(call("/api/cromo", bad, cookie=ck)[1]), bad
# A later buyer gets a plain copy; a card bought before cromadas existed lets its first buyer pick the stat once.
st = {"ledger": [{"player": "Ana", "amount": -5, "reason": "carta Regio"}], "cards": {"Ana": ["Regio"]}}
server.buy_card(st, {"Bia": 20}, {"Regio": 5}, "Bia", "Regio")
assert server.card_cost({"Bia": 10, "Regio": 5}, "Bia", "Bia") == 7 and server.card_cost({"Bia": 10}, "Regio", "Bia") == 10  # 30% off your own card
assert st["cards"]["Bia"] == ["Regio"] and "cromo" not in st and server.first_buyers(st) == {"Regio": "Ana"}
for who, stat in (("Bia", "GOL"), (None, "GOL"), ("Ana", "XYZ")):
    try:
        server.claim_cromo(st, who, "Regio", stat)
        raise AssertionError((who, stat))
    except ValueError:
        pass
server.claim_cromo(st, "Ana", "Regio", "GOL")
assert st["cromo"] == {"Regio": "GOL"}
# BioBet mercados over HTTP: the list opens the game's own, a member opens and joins with their own coins, staff decide.
st = server.load_state()
st["match"] = {"date": "2099-10-15", "confirmed": ["Dan", "Victor"], "bets": [],
               "draft": {"captains": ["Dan", "Victor"], "teams": {"Dan": ["Dan"], "Victor": ["Victor"]}, "ok": ["Dan", "Victor"]}}
server.save_state(st)
assert len(server.mercado_tick(server.kickoff("2099-10-15") - 3 * 86400)) == 1 and server.mercado_tick() == []
ana, andrei = ("biofut=" + server.sign(n, "127.0.0.1") for n in ("Ana", "Andrei"))
s0 = json.loads(call("/api/state")[1])
assert "error" in json.loads(call("/api/mercado", {"kind": "lista", "p": "Regio", "side": "sim", "stake": 3})[1])
assert "error" in json.loads(call("/api/mercado", {"kind": "jogadores", "n": 9, "side": "sim", "stake": 1}, cookie=me)[1]), "Dan is on the list"
s1 = json.loads(call("/api/mercado", {"kind": "lista", "p": "Regio", "min": 2, "side": "sim", "stake": 3}, cookie=me)[1])
mid = s1["mercados"][-1]["id"]
assert s1["mercados"][-1]["bets"][0]["who"] == "Dan" and s1["balances"]["Dan"] == s0["balances"]["Dan"] - 3 and "fechados" not in s1
assert "error" not in json.loads(call("/api/mercado_bet", {"id": mid, "side": "não", "stake": 2}, cookie=ana)[1])
for ck, out in ((me, "sim"), (ana, "não"), (ana, "anular")):  # Dan is in it; Ana is no staff and not alone
    assert "error" in json.loads(call("/api/mercado_fim", {"id": mid, "out": out}, cookie=ck)[1]), (ck, out)
s2 = json.loads(call("/api/mercado_fim", {"id": mid, "out": "sim"}, cookie=andrei)[1])
assert s2["mercados"][-1]["status"] == "sim" and s2["balances"]["Dan"] == s0["balances"]["Dan"] + 2 and s2["balances"].get("Ana", WELCOME - 2) == WELCOME - 2
s3 = json.loads(call("/api/bet", {"bettor": "Victor", "pick": "A", "stake": 1}, cookie=me)[1])
assert s3["match"]["bets"][-1]["bettor"] == "Dan", "the logged-in member bets, never the name in the body"
assert "error" in json.loads(call("/api/bet", {"bettor": "Victor", "pick": "A", "stake": 1})[1])
# Ideas become GitHub issues on their own: a failure is retried on the next sweep, nothing is filed twice.
server.FEEDBACK, server.ISSUES, server.GITHUB_TOKEN = tmp / "feedback.jsonl", tmp / "issues.json", ""  # the POST's own sweep stays off; the test drives it
issued = []
def gh(route, obj):
    issued.append(obj)
    if len(issued) == 1:
        raise OSError("down")
    return json.dumps({"html_url": f"https://github.com/x/issues/{len(issued)}"})
assert json.loads(call("/api/feedback", {"text": "placar ao vivo", "kind": "bug"}, cookie=me)[1]) == {"ok": True}
server.GITHUB_TOKEN = "t"
server.file_issues(gh)
assert not server.ISSUES.exists() and issued[0]["title"] == "[bug] placar ao vivo" and issued[0]["labels"] == ["bug"]
server.file_issues(gh); server.file_issues(gh)
assert len(issued) == 2 and json.loads(call("/api/feedback", cookie=me)[1])[0]["issue"] == "https://github.com/x/issues/2"
# Duelo: the server deals and judges. The daily deal is the same for everyone and once a day, one open duel each
# (opening again resumes it), the machine's cards stay hidden until played, a win pays DUEL_WIN coins and counts.
dc = server.duel_cards(DATA["games"])  # the real cards (biofut.json): the test games here give nobody 10 jogos
assert "poucas" in json.loads(call("/api/duelo", {}, cookie=me)[1])["error"]
server.duel_cards = lambda games: dc
o = json.loads(call("/api/duelo", {}, cookie=me)[1])
bal0 = o["balances"]["Dan"]
assert o["duel"]["cpu"] == [None] * 5 and len(o["duel"]["you"]) == 5 and "duelo_aberto" not in o, o.get("error")
assert "error" in json.loads(call("/api/duelo", {}, cookie="")[1])
assert json.loads(call("/api/duelo", {"mode": "livre", "name": "Victor"}, cookie=me)[1])["duel"] == o["duel"]
for i in range(5):
    o = json.loads(call("/api/duelo", {"at": "GOL"}, cookie=me)[1])
    assert len(o["duel"]["log"]) == i + 1 and None not in o["duel"]["cpu"][:i + 1] and o["duel"]["cpu"][i + 1:] == [None] * (4 - i)
r = o["duelo"]["Dan"]
assert r["v"] + r["e"] + r["d"] == 1 and r["dia"][1] == r["best"] and o["balances"]["Dan"] == round(bal0 + r["v"] * server.DUEL_WIN, 4)
assert json.loads(call("/api/duelo", {}, cookie=me)[1])["duel"] == {"feito": r["best"]} and "error" in json.loads(call("/api/duelo", {"at": "GOL"}, cookie=me)[1])
assert server.duel_act({}, "Ana", dc, {}, "2026-10-11")["you"] == server.duel_act({}, "Bia", dc, {}, "2026-10-11")["you"] != server.duel_act({}, "Ana", dc, {}, "2026-10-12")["you"]
assert server.duel_act({}, "Ana", dc, {"mode": "livre", "name": "Victor"}, "x")["you"][0]["name"] == "Victor"
st = {"cards": {"Ana": [c["name"] for c in dc[10:14]]}, "ledger": [{"player": "Ana", "amount": -5, "reason": f"carta {dc[20]['name']}"}], "cromo": {dc[20]["name"]: "CAP"}}
try:
    server.duel_act(st, "Ana", dc, {"mode": "deck"}, "x")
    raise AssertionError("a deck needs 5 cards")
except ValueError:
    pass
st["cards"]["Ana"].append(dc[20]["name"])
y = server.duel_act(st, "Ana", dc, {"mode": "deck"}, "x")["you"]
assert {c["name"] for c in y} == set(st["cards"]["Ana"]) and [c for c in y if c.get("crom")] == [{**dc[20], "crom": "CAP", "at": {**dc[20]["at"], "CAP": dc[20]["at"]["CAP"] + 1}}]
# #/deck: the first 5 cards bought make the deck; then the member picks any 5 of the collection, and the duel plays those.
st = {"ledger": [], "cards": {}}
names = [c["name"] for c in dc[:7]]
for n in names:
    server.buy_card(st, {"Ana": 999}, dict.fromkeys(names, 5), "Ana", n, "GOL")
assert st["deck"]["Ana"] == names[:5] and server.deck_of(st, "Ana") == names[:5]
for bad in (names[:4], names[:4] + names[:1], names[1:5] + ["Ninguém"], "abcde", None):
    try:
        server.set_deck(st, "Ana", bad)
        raise AssertionError(bad)
    except ValueError:
        pass
server.set_deck(st, "Ana", names[2:])
assert {c["name"] for c in server.duel_act(st, "Ana", dc, {"mode": "deck"}, "x")["you"]} == set(names[2:])
st["cards"]["Ana"].remove(names[6])  # a deck card no longer theirs: back to the first 5 of the collection
assert server.deck_of(st, "Ana") == names[:5]
card = lambda n, v, tier="prata", **at: {"name": n, "tier": tier, "at": {**dict.fromkeys(server.STATS, v), **at}}
def duel(st, you, cpu, picks="GOL" * 5):
    st.setdefault("duelo_aberto", {})["Eve"] = {"mode": "livre", "day": "x", "ace": "ace", "you": you, "cpu": cpu, "log": []}
    for a in [picks[k:k + 3] for k in range(0, 15, 3)]:
        v = server.duel_act(st, "Eve", dc, {"at": a}, "x")
    return [w for _, w in v["log"]], v["log"]
st = {"ledger": []}
assert duel(st, [card(f"y{i}", 90) for i in range(5)], [card("c0", 50), card("c1", 50, CAP=99)] + [card(f"c{i}", 50) for i in range(2, 5)]) == (
    [1, -1, 1, 1, 1], [["GOL", 1], ["CAP", -1], ["GOL", 1], ["GOL", 1], ["GOL", 1]])  # the machine plays its card's best
assert duel(st, [card("ace", 10)] + [card(f"y{i}", 90) for i in range(4)], [card("c0", 90)] + [card(f"c{i}", 50) for i in range(4)])[0] == [1] * 5  # Super Craque
assert duel(st, [card("ace", 99)] + [card(f"y{i}", 10) for i in range(4)], [card("z", 1, "bronze")] + [card(f"c{i}", 50) for i in range(4)])[0] == [-1] * 5  # zebra
assert duel(st, [card("y", 50, "bronze")] + [card(f"y{i}", 50) for i in range(4)], [card("ace", 99)] + [card(f"c{i}", 50) for i in range(4)])[0] == [1, 0, 0, 0, 0]  # zebra too
r = st["duelo"]["Eve"]
assert (r["v"], r["e"], r["d"], r["run"], r["top"], r["best"], r["dia"]) == (3, 0, 1, 1, 2, [5, 0], None) and not st["duelo_aberto"], r
assert balance(st, {}, "Eve") == WELCOME + 0.0003 and balance(st, {}, "Bob") == WELCOME and type(balance(st, {}, "Bob")) is int
for body, who in (({"at": "XYZ"}, "Eve"), ({}, None)):
    st["duelo_aberto"]["Eve"] = {"mode": "livre", "day": "x", "ace": "ace", "you": [card("y", 50)] * 5, "cpu": [card("c", 50)] * 5, "log": []}
    try:
        server.duel_act(st, who, dc, body, "x")
        raise AssertionError(body)
    except ValueError:
        pass
httpd.shutdown()
print("ok")

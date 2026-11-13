"""Writes released súmulas into the group's sheet (DATABASE tab, gid=0) with the Google Sheets API, as a service account.

The sheet is shared with the service account's email as Editor; its JSON key lives on the server (BIOFUT_SHEET_KEY,
default /etc/biofut-sheet.json, mode 600) and BIOFUT_SHEET_ID is the id in the sheet's /edit link.

For each game it fills the next block of empty game rows (the lowest "Jogo Total" whose rows all have no Nome, after the
last filled game) with Data, Time, Nome, Gol, Assistência, Gol Contra, Capitão (columns L-R). Formula columns (A-K) are
never touched. It refuses a date that already has players, cells holding a formula, and values the sheet's own
dropdowns reject (a nickname, a typo, a new name: the API would write them anyway).
Safety (the sheet is years of hand-kept history): one push at a time; the header (C1 + L1:R1) must be the expected
layout; the whole batch is planned and checked before the first write (all games or none); each target block is
re-read right before and must still be that game's empty rows; the whole A:R (formulas too) is saved to
data/sheet-backups/ first (last KEEP kept); every write is read back and compared, and logged in
data/sheet-writes.jsonl (who, when, range, rows, snapshot). Nothing is cleared, deleted or resized; a write that fails
half-way puts the snapshot's own cells back in the ranges this call wrote, and nowhere else.
Self-check: python sheet.py [data/sheet.csv]
"""
import base64, json, os, re, sys, threading, time, urllib.parse, urllib.request

KEY = os.environ.get("BIOFUT_SHEET_KEY", "/etc/biofut-sheet.json")
ID = os.environ.get("BIOFUT_SHEET_ID", "")
API = "https://sheets.googleapis.com/v4/spreadsheets/"
JOGO, DATA, NOME = 2, 11, 13  # 0-based: C, L, N; writes L..R (7 columns)
_token = {"exp": 0}
HEAD = ["Data", "Time", "Nome", "Gol", "Assistência", "Gol Contra", "Capitão"]  # L1:R1, with C1 = Jogo Total
BACKUPS = os.environ.get("BIOFUT_SHEET_BACKUPS", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "sheet-backups"))
KEEP = int(os.environ.get("BIOFUT_SHEET_KEEP", "30"))
_write = threading.Lock()  # two presses (or a press and a released súmula) never interleave their read and write


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def token():
    """OAuth access token for the service account (signed JWT grant), cached until 5 min before it expires."""
    if _token["exp"] > time.time() + 300:
        return _token["value"]
    from cryptography.hazmat.primitives import hashes, serialization  # ponytail: Ubuntu's python3-cryptography, already on the A1
    from cryptography.hazmat.primitives.asymmetric import padding
    k = json.loads(open(KEY, encoding="utf-8").read())
    now = int(time.time())
    claims = {"iss": k["client_email"], "scope": "https://www.googleapis.com/auth/spreadsheets",
              "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}
    msg = b64(b'{"alg":"RS256","typ":"JWT"}') + "." + b64(json.dumps(claims).encode())
    sig = serialization.load_pem_private_key(k["private_key"].encode(), None).sign(msg.encode(), padding.PKCS1v15(), hashes.SHA256())
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": msg + "." + b64(sig)}).encode()
    r = json.load(urllib.request.urlopen("https://oauth2.googleapis.com/token", body, timeout=30))
    _token.update(value=r["access_token"], exp=now + r["expires_in"])
    return r["access_token"]


def api(path, body=None, method=None):
    req = urllib.request.Request(API + ID + path, json.dumps(body).encode() if body is not None else None,
                                 {"Authorization": "Bearer " + token(), "Content-Type": "application/json"}, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise ValueError(f"Sheets API {e.code}: {e.read().decode(errors='replace')[:300]}") from None


def values(rng, render="FORMATTED_VALUE"):
    return api(f"/values/{urllib.parse.quote(rng, safe='')}?valueRenderOption={render}").get("values", [])


def tab():
    """Title of the tab the site reads (published gid=0, the DATABASE tab)."""
    sheets = api("?fields=sheets.properties(sheetId,title)")["sheets"]
    return next(s["properties"]["title"] for s in sheets if s["properties"]["sheetId"] == 0)


def short_date(iso):  # as the sheet shows it: 1/10/26
    y, m, d = iso.split("-")
    return f"{int(d)}/{int(m)}/{y[2:]}"


def same_day(cell, iso):
    """Does a Data cell ('8/10/26', '08/10/2026', '8/10') show the day iso (2026-10-08)?"""
    y, mo, d = map(int, iso.split("-"))
    m = re.match(r"\s*(\d+)/(\d+)(?:/(\d+))?\s*$", str(cell))
    return bool(m) and (int(m[1]), int(m[2])) == (d, mo) and (not m[3] or int(m[3]) % 100 == y % 100) or str(cell).strip() == iso


def plan(vals, g, mine=()):
    """Pure part. vals: display values of A..N from row 2; mine: rows of vals this same call fills (two games on one
    date: the second must not see the first as a duplicate). Returns (jogo, row 0-based in vals, rows L..R)."""
    day, last, blocks = short_date(g["date"]), -1, {}
    for i, r in enumerate(vals):
        r = list(r) + [""] * (NOME + 1 - len(r))  # the API drops trailing empty cells
        j = int(r[JOGO]) if str(r[JOGO]).strip().isdigit() else 0
        if not j:
            continue
        named = str(r[NOME]).strip() != ""
        if named:
            last = max(last, j)
            if i not in mine and same_day(r[DATA], g["date"]):  # idempotent: a double press or a retry finds its rows
                raise ValueError("a planilha já tem jogo em " + day)
        b = blocks.setdefault(j, {"start": i, "n": 0, "named": False})
        b["n"] += 1
        b["named"] = b["named"] or named
    free = sorted(j for j, b in blocks.items() if j > last and not b["named"])
    if not free:
        raise ValueError("sem linhas vazias para um jogo novo; crie mais na planilha")
    b = blocks[free[0]]
    rows = [[g["date"], t["name"], p[0], p[1] or "", p[2] or "", p[3] or "", 1 if p[4] else ""]  # [name, goals, assists, own goals, captain]
            for t in g["teams"] for p in t["players"]]
    if len(rows) > b["n"]:
        raise ValueError(f"o jogo {free[0]} tem {b['n']} linhas e a súmula tem {len(rows)} jogadores")
    return free[0], b["start"], rows


def filled_formulas(formulas, shown, first):
    """Cells of an L..R range (first = its sheet row) whose formula shows something: those the writer must not
    overwrite. A formula that shows nothing (a blank-looking template cell) is fair game, as when pasting by hand."""
    cell = lambda rows, i, j: str(rows[i][j]) if i < len(rows) and j < len(rows[i]) else ""
    return [f"{'LMNOPQR'[j]}{first + i}" for i in range(len(formulas)) for j in range(len(formulas[i]))
            if cell(formulas, i, j).startswith("=") and cell(shown, i, j).strip()]


def rules(rng):
    """The sheet's own dropdowns on rng: {column offset in rng: [allowed values]}, from each column's first cell with a
    list rule. ponytail: one rule per column, as the sheet has it."""
    r = api("?" + urllib.parse.urlencode({"ranges": rng, "includeGridData": "true", "fields": "sheets.data.rowData.values.dataValidation"}))
    out = {}
    for row in r["sheets"][0]["data"][0].get("rowData", []):
        for j, c in enumerate(row.get("values", [])):
            cond = c.get("dataValidation", {}).get("condition", {})
            if j in out or cond.get("type") not in ("ONE_OF_LIST", "ONE_OF_RANGE"):
                continue
            vs = [v.get("userEnteredValue", "") for v in cond.get("values", [])]
            if cond["type"] == "ONE_OF_RANGE":
                vs = [x for line in values(vs[0].lstrip("=")) for x in line]
            out[j] = [str(v).strip() for v in vs if str(v).strip()]
    return out


def off_list(rows, allowed, first):
    """Cells of rows (L..R values, first = sheet row) the dropdowns reject, as 'N4901 Bruney'. A case slip is no
    mistake: it gets the list's spelling in place (andrei -> Andrei)."""
    bad = []
    for i, r in enumerate(rows):
        for j, ok in allowed.items():
            v = str(r[j]).strip() if j < len(r) else ""
            hit = next((a for a in ok if a.casefold() == v.casefold()), None)
            if v and hit is None:
                bad.append(f"{'LMNOPQR'[j]}{first + i} {v}")
            elif v and isinstance(r[j], str):
                r[j] = hit
    return bad


_names = {"at": 0, "v": []}


def names():
    """The names the Nome column takes (its dropdown), for #/planilha. Cached 10 min; [] when it has no list.
    Read on the last rows with a Jogo number (the empty blocks the next games go to): the old rows have no dropdown."""
    if time.time() - _names["at"] > 600:
        t = "'" + tab().replace("'", "''") + "'"
        end = len(values(f"{t}!C2:C")) + 1
        _names.update(at=time.time(), v=sorted(rules(f"{t}!N{max(2, end - 200)}:N{end}").get(0, []), key=str.casefold))
    return _names["v"]


def snapshot(t):
    """The whole A:R as typed (formulas, not their results) -> a timestamped JSON in BACKUPS; keeps the last KEEP.
    Undo by hand = paste a range's old cells back from it (sheet-writes.jsonl names the range)."""
    os.makedirs(BACKUPS, exist_ok=True)
    path = os.path.join(BACKUPS, time.strftime("sheet-%Y%m%d-%H%M%S-") + f"{time.time() % 1:.6f}"[2:] + ".json")
    vals = values(f"{t}!A1:R", "FORMULA")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "tab": t, "range": "A1:R", "values": vals}, f, ensure_ascii=False)
    for old in sorted(x for x in os.listdir(BACKUPS) if x.startswith("sheet-") and x.endswith(".json"))[:-KEEP]:
        os.remove(os.path.join(BACKUPS, old))
    return path, vals


def audit(**line):
    """One line per write in sheet-writes.jsonl, next to the backups folder."""
    with open(os.path.join(os.path.dirname(BACKUPS), "sheet-writes.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), **line}, ensure_ascii=False) + "\n")


def mismatch(back, rows, iso, first):
    """Cells of a written L..R range whose read-back differs from what was sent, as "N4901 'Bruno' != 'Bruney'"."""
    def norm(v):
        v = {"TRUE": "1", "FALSE": ""}.get(str(v).strip().upper(), str(v).strip())
        try:
            return str(float(v)) if v else ""
        except ValueError:
            return v
    out = []
    for i, r in enumerate(rows):
        b = (list(back[i]) if i < len(back) else []) + [""] * 7
        if not same_day(b[0], iso):
            out.append(f"L{first + i} {b[0]!r} != {iso}")
        out += [f"{'LMNOPQR'[j]}{first + i} {b[j]!r} != {r[j]!r}" for j in range(1, 7) if norm(b[j]) != norm(r[j])]
    return out


def check(t, jogo, row, rows):
    """Right before writing game jogo's rows (row 0-based from row 2): fresh read of its block. Refuses rows that are
    no longer this game's (a sort, a filter, an inserted row) or that hold anything, and names off the dropdown."""
    first, last = row + 2, row + 1 + len(rows)
    cur = values(f"{t}!A{first}:R{last}")
    cur = [(list(cur[i]) if i < len(cur) else []) + [""] * 18 for i in range(len(rows))]
    moved = [first + i for i, r in enumerate(cur) if str(r[JOGO]).strip() != str(jogo)]
    if moved:
        raise ValueError(f"as linhas {moved[0]}..{moved[-1]} não são mais do jogo {jogo} (planilha ordenada ou editada?)")
    busy = [f"{'LMNOPQR'[j]}{first + i}" for i, r in enumerate(cur) for j in range(7) if str(r[DATA + j]).strip()]
    if busy:
        raise ValueError(f"as linhas do jogo {jogo} não estão vazias em {', '.join(busy[:3])}")
    rng = f"{t}!L{first}:R{last}"
    allowed = rules(rng)
    if 2 not in allowed:  # no dropdown to check against: refuse rather than write unchecked names
        raise ValueError(f"as linhas do jogo {jogo} não têm a lista de nomes (validação da coluna Nome); confira a planilha")
    bad = off_list(rows, allowed, first)
    if bad:
        raise ValueError(f"fora da lista da planilha: {', '.join(bad[:6])}. Use o nome da lista; quem não está nela vira SOMBRA")
    return rng


def put(rng, rows):
    # USER_ENTERED: the ISO date becomes a real date cell, numbers stay numbers
    api(f"/values/{urllib.parse.quote(rng, safe='')}?valueInputOption=USER_ENTERED", {"values": rows}, "PUT")


def push(games, who="site"):
    """Writes the games into the sheet, all or none; returns the "Jogo Total" numbers used. Raises on any refusal,
    before writing anything."""
    if not ID:
        raise ValueError("BIOFUT_SHEET_ID não configurado")
    with _write:
        t = "'" + tab().replace("'", "''") + "'"
        shown = values(f"{t}!A1:R")
        head = [str(x).strip() for x in (list(shown[0]) if shown else []) + [""] * 18]
        if head[JOGO] != "Jogo Total" or head[DATA:DATA + 7] != HEAD:  # a column a human inserted or moved
            raise ValueError(f"a aba gid=0 mudou de colunas (C1 {head[JOGO]!r}, L1:R1 {head[DATA:DATA + 7]}); "
                             f"esperado Jogo Total e {', '.join(HEAD)}; nada foi escrito")
        vals, mine, todo = [list(r) for r in shown[1:]], set(), []
        for g in games:  # plan and check the whole batch first: a refusal writes nothing
            jogo, row, rows = plan(vals, g, mine)
            todo.append((g, jogo, row, rows, check(t, jogo, row, rows)))
            for i, r in enumerate(rows):  # the next game in this call sees these rows as filled
                vals[row + i] = list(vals[row + i]) + [""] * 18
                vals[row + i][NOME], vals[row + i][DATA] = r[2], short_date(g["date"])
                mine.add(row + i)
        snap, before = snapshot(t)
        written = []
        try:
            for g, jogo, row, rows, rng in todo:
                put(rng, rows)
                written.append((row, rows, rng))
                bad = mismatch(values(rng), rows, g["date"], row + 2)
                audit(who=who, range=rng, jogo=jogo, date=g["date"], rows=rows, snapshot=snap, ok=not bad, mismatch=bad[:20])
                if bad:
                    print(f"SHEET WRITE MISMATCH {rng}: {bad[:6]} snapshot {snap}", file=sys.stderr, flush=True)
                    raise ValueError(f"a planilha não confere depois da escrita em {rng} ({', '.join(bad[:3])})")
        except Exception as e:
            undo = []
            for row, rows, rng in written:  # only the ranges this call wrote get their old cells (formulas) back
                old = [((list(before[row + 1 + i]) if row + 1 + i < len(before) else []) + [""] * 18)[DATA:DATA + 7] for i in range(len(rows))]
                try:
                    put(rng, old)
                    undo.append(rng)
                except Exception as e2:
                    print(f"SHEET UNDO FAILED {rng}: {e2}", file=sys.stderr, flush=True)
            audit(who=who, error=str(e), undone=undo, snapshot=snap)
            raise ValueError(f"{e}; desfeito: {', '.join(undo) or 'nada'}; cópia de antes: {snap}") from None
    return [jogo for _, jogo, *_ in todo]


def rows_of(jogo):
    """Read back game jogo's rows as the sheet shows them: [[sheet row, Data, Time, Nome, Gol, Assist., Gol Contra, Capitão]]."""
    t = "'" + tab().replace("'", "''") + "'"
    return [[i + 2, *(list(r[11:18]) + [""] * 7)[:7]] for i, r in enumerate(values(f"{t}!A2:R"))
            if len(r) > JOGO and str(r[JOGO]).strip() == str(jogo)]


if __name__ == "__main__":
    csv = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__) or ".", "data", "sheet.csv")
    rows = ([l.split(",")[:14] for l in open(csv, encoding="utf-8").read().strip().split("\n")[1:]] if os.path.exists(csv) else
            [["", "", "299"] + [""] * 8 + ["1/10/26", "BAGRES", "Dan"], ["", "", "300"], ["", "", "300"] + [""] * 11])
    game = lambda date, n: {"date": date, "teams": [{"name": "PRETO", "players": [["Dan", 4, 0, 0, 1]]},
                                                   {"name": "VERDE", "players": [[f"P{i}", 0, 1, 0, 0] for i in range(n - 1)]}]}
    assert short_date("2026-10-08") == "8/10/26"
    d, m, y = [r for r in rows if len(r) > 13 and r[13].strip()][-1][11].split("/")
    taken = f"20{y}-{int(m):02}-{int(d):02}"  # the last game already in the sheet
    jogo, row, out = plan(rows, game("2030-01-08", 2))
    nxt = max(int(r[2]) for r in rows if len(r) > 13 and r[13].strip()) + 1
    assert jogo == nxt and int(rows[row][2]) == nxt and all(int(r[2] or 0) < nxt for r in rows[:row])  # block starts at its first row
    assert out == [["2030-01-08", "PRETO", "Dan", 4, "", "", 1], ["2030-01-08", "VERDE", "P0", "", 1, "", ""]], out
    for date, n, err in ((taken, 2, "já tem jogo"), ("2030-01-08", 40, "linhas")):
        try:
            plan(rows, game(date, n)); raise AssertionError(err)
        except ValueError as e:
            assert err in str(e), e
    assert filled_formulas([["=A1", "", "=B1"], [], ["x"]], [["", "", "Ze"]], 10) == ["N10"]  # blank-looking formulas get overwritten
    out = [["2030-01-08", "PRETO", "andrei", 1, "", "", 1], ["2030-01-08", "PRETO", "Neco Dei", "", "", "", ""]]
    assert off_list(out, {2: ["Andrei", "SOMBRA"]}, 4899) == ["N4900 Neco Dei"] and out[0][2] == "Andrei"  # nickname refused, case fixed
    asked = []
    globals()["api"] = lambda p, *a: asked.append(p) or {}
    values("'TABELA 26/2'!$B$2:$B$51")
    assert "26%2F2" in asked.pop(), "a / in a tab name must not split the URL path"
    rule = {"dataValidation": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": "=Jogadores!A2:A"}]}}}
    globals().update(tab=lambda: "DATABASE", api=lambda p: asked.append(urllib.parse.unquote(p)) or {"sheets": [{"data": [{"rowData": [{}, {"values": [rule]}]}]}]},
                     values=lambda rng, render=None: [["301"]] * 4999 if rng.endswith("!C2:C") else [["SOMBRA"], ["andrei"]])
    assert names() == ["andrei", "SOMBRA"] and "'DATABASE'!N4800:N5000" in asked[0], asked  # the dropdown of the last rows, not the old ones
    print("sheet ok: next game", jogo, "at sheet row", row + 2)

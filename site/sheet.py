"""Writes released súmulas into the group's sheet (DATABASE tab, gid=0) with the Google Sheets API, as a service account.

The sheet is shared with the service account's email as Editor; its JSON key lives on the server (BIOFUT_SHEET_KEY,
default /etc/biofut-sheet.json, mode 600) and BIOFUT_SHEET_ID is the id in the sheet's /edit link.

For each game it fills the next block of empty game rows (the lowest "Jogo Total" whose rows all have no Nome, after the
last filled game) with Data, Time, Nome, Gol, Assistência, Gol Contra, Capitão (columns L-R). Formula columns (A-K) are
never touched. It refuses a date that already has players, cells holding a formula, and values the sheet's own
dropdowns reject (a nickname, a typo, a new name: the API would write them anyway).
Self-check: python sheet.py [data/sheet.csv]
"""
import base64, json, os, sys, time, urllib.parse, urllib.request

KEY = os.environ.get("BIOFUT_SHEET_KEY", "/etc/biofut-sheet.json")
ID = os.environ.get("BIOFUT_SHEET_ID", "")
API = "https://sheets.googleapis.com/v4/spreadsheets/"
JOGO, DATA, NOME = 2, 11, 13  # 0-based: C, L, N; writes L..R (7 columns)
_token = {"exp": 0}


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
    return api(f"/values/{urllib.parse.quote(rng)}?valueRenderOption={render}").get("values", [])


def tab():
    """Title of the tab the site reads (published gid=0, the DATABASE tab)."""
    sheets = api("?fields=sheets.properties(sheetId,title)")["sheets"]
    return next(s["properties"]["title"] for s in sheets if s["properties"]["sheetId"] == 0)


def short_date(iso):  # as the sheet shows it: 1/10/26
    y, m, d = iso.split("-")
    return f"{int(d)}/{int(m)}/{y[2:]}"


def plan(vals, g):
    """Pure part. vals: display values of A..N from row 2. Returns (jogo, row 0-based in vals, rows L..R)."""
    day, last, blocks = short_date(g["date"]), -1, {}
    for i, r in enumerate(vals):
        r = list(r) + [""] * (NOME + 1 - len(r))  # the API drops trailing empty cells
        j = int(r[JOGO]) if str(r[JOGO]).strip().isdigit() else 0
        if not j:
            continue
        named = str(r[NOME]).strip() != ""
        if named:
            last = max(last, j)
            if r[DATA] == day:
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


def push(games):
    """Writes each game into the sheet; returns the "Jogo Total" numbers used. Raises on any refusal."""
    if not ID:
        raise ValueError("BIOFUT_SHEET_ID não configurado")
    t = "'" + tab().replace("'", "''") + "'"
    head = values(f"{t}!N1:N1")
    if head != [["Nome"]]:
        raise ValueError("a aba gid=0 não parece a DATABASE (N1 não é Nome)")
    vals, done = values(f"{t}!A2:N"), []
    for g in games:
        jogo, row, rows = plan(vals, g)
        rng = f"{t}!L{row + 2}:R{row + 1 + len(rows)}"
        busy = filled_formulas(values(rng, "FORMULA"), values(rng), row + 2)
        if busy:
            raise ValueError(f"as linhas do jogo {jogo} têm fórmula com valor em {', '.join(busy[:3])}")
        allowed = rules(rng)
        if 2 not in allowed:  # no dropdown to check against: refuse rather than write unchecked names
            raise ValueError(f"as linhas do jogo {jogo} não têm a lista de nomes (validação da coluna Nome); confira a planilha")
        bad = off_list(rows, allowed, row + 2)
        if bad:
            raise ValueError(f"fora da lista da planilha: {', '.join(bad[:6])}. Use o nome da lista; quem não está nela vira SOMBRA")
        # USER_ENTERED: the ISO date becomes a real date cell, numbers stay numbers
        api(f"/values/{urllib.parse.quote(rng)}?valueInputOption=USER_ENTERED", {"values": rows}, "PUT")
        for i, r in enumerate(rows):  # the next game in this call sees these rows as filled
            vals[row + i] = (list(vals[row + i]) + [""] * 14)[:14]
            vals[row + i][NOME], vals[row + i][DATA] = r[2], short_date(g["date"])
        done.append(jogo)
    return done


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
    asked, rule = [], {"dataValidation": {"condition": {"type": "ONE_OF_RANGE", "values": [{"userEnteredValue": "=Jogadores!A2:A"}]}}}
    globals().update(tab=lambda: "DATABASE", api=lambda p: asked.append(urllib.parse.unquote(p)) or {"sheets": [{"data": [{"rowData": [{}, {"values": [rule]}]}]}]},
                     values=lambda rng, render=None: [["301"]] * 4999 if rng.endswith("!C2:C") else [["SOMBRA"], ["andrei"]])
    assert names() == ["andrei", "SOMBRA"] and "'DATABASE'!N4800:N5000" in asked[0], asked  # the dropdown of the last rows, not the old ones
    print("sheet ok: next game", jogo, "at sheet row", row + 2)

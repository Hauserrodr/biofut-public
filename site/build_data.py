"""Build site/biofut.json: full match history, BioBet model coefficients, lexicon, Pix payload.

Run locally (needs numpy + sklearn for the odds model; the server itself is stdlib only):
    python build_data.py
Sources (read-only): the other agents' handoffs from 2026-10-03.
Refit only the model (no handoffs needed), on the games of one or more JSON files ({"games": [...]} like biofut.json
or a saved /api/data, or a plain list of games), a later file's game winning on the same date:
    python build_data.py --refit biofut.json [more_games.json ...]   -> rewrites biofut.json's "model" only
"""
import json, sqlite3, sys
from pathlib import Path

H = Path("L:/GAB/Agents/Handoffs")
DB = H / "claude-biofut-data/2026-10-03/biofut.db"
TERMS = H / "claude-biofut-data/2026-10-03/terms.csv"
sys.path.insert(0, str(Path(__file__).parent))
import glm, pix  # noqa: E402

PIX_KEY = "biofutufrgs@gmail.com"  # the group's own payment key, posted in every weekly list
OUT = Path(__file__).parent / "biofut.json"


def games():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    for n, season, date, team, gf, ga, res in c.execute(
            "select game_no, season, date, team, goals_for, goals_against, result from games order by game_no, rowid"):
        g = out.setdefault(n, {"n": n, "season": season, "date": date, "teams": []})
        g["teams"].append({"name": team, "gf": gf, "ga": ga, "res": res, "players": []})
    for n, team, player, gl, ast, og, cap in c.execute("select * from player_games order by rowid"):
        t = next(t for t in out[n]["teams"] if t["name"] == team)
        t["players"].append([player, gl or 0, ast or 0, og or 0, cap or 0])
    return list(out.values())


def fit(games, alpha=1.0, skip=20):
    """Poisson GLM (glm.py) on `games` in play order -> the "model" block of biofut.json. Each game from the 21st on is
    a row twice, A scoring on B and B on A, with the table of the games before it. Same fit as backtest.py."""
    import numpy as np
    from sklearn.linear_model import PoissonRegressor
    X, y = [], []
    for i in range(skip, len(games)):
        tab, mean = glm.player_table(games[:i])
        a, b = games[i]["teams"]
        for s, o in ((a, b), (b, a)):
            X.append(glm.match_x(tab, mean, [p[0] for p in s["players"]], [p[0] for p in o["players"]])); y.append(s["gf"])
    X, y = np.array(X, float), np.array(y, float)
    mu, sd = X.mean(0), X.std(0) + 1e-9
    m = PoissonRegressor(alpha=alpha, max_iter=1000).fit((X - mu) / sd, y)
    r = lambda v: [round(float(x), 6) for x in v]
    return {"kind": "poisson_glm", "games": len(games), "shrink": glm.SHRINK, "alpha": alpha, "features": glm.FEATURES,
            "mu": r(mu), "sd": r(sd), "coef": r(m.coef_), "intercept": round(float(m.intercept_), 6)}


def merged_games(paths):
    """Games of every file, later files winning on the same date (a site-closed game vs the sheet's copy), in n order."""
    out = {}
    for path in paths:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        for g in d["games"] if isinstance(d, dict) else d:
            out[g.get("date") or f"n{g['n']}"] = g
    return sorted(out.values(), key=lambda g: g["n"])


def refit(out, *more):
    data = json.loads(Path(out).read_text(encoding="utf-8"))
    gs = merged_games([out, *more])
    data["model"] = fit(gs)
    Path(out).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{out}: model refit on {len(gs)} games (intercept {data['model']['intercept']})")


# Portuguese version of the curated parts of lexicon.md (the vault copy stays English).
NICKNAMES = [
    ["Mattebol", "Matte, o mestre das jogadas de minhoca"],
    ["Gui Goleiro, Gui GK", "o Gui do gol"],
    ["Guihñazu", "Guih, a assinatura dele na lista (\"sem o h no fim a gente esquece\"). O Leo Saul diz que já foi chamado de guiñazú do biofut"],
    ["Nego Dei, Nego Dola", "Andrei, um nome, muitas versões"],
    ["Doga", "Douglas. \"Nego dola vs Doga bola\""],
    ["Grandão", "Lucas Poletti"],
    ["Bruney", "Bruno"],
    ["Felps", "o Felps, que não é o Felipe"],
    ["Perdigas", "Perdigão"],
    ["Presidente Dola", "Andrei, presidente por uma semana em julho de 2026"],
    ["João Estratégico", "o João estagiário, promovido por erro de leitura"],
    ["GabsIA", "Gab. Já teve enquete para banir"],
]
GLOSSARY = [
    ["Esquizofut", "o nome que o grupo dá a si mesmo. \"Hoje é dia de ESQUIZOFUT\""],
    ["Planet Ball", "a casa. Quase sempre Quadra 4 ou 5"],
    ["Quinta 18:30", "o horário sagrado desde 2025. Antes: segunda e quinta às 18h"],
    ["Lista, lista dupla", "o post semanal de inscrição"],
    ["Suplência", "a lista de espera"],
    ["Sombra", "convidado trazido por alguém: (sombra X) na lista"],
    ["Nota N", "a avaliação do convidado, quase sempre injusta"],
    ["(C)", "capitão. Capitães fazem o draft"],
    ["Mensalista", "o grupo é mensalista da Planet nas quintas 18h30"],
    ["Pilas", "reais. 10 pilas o jogo até 2025, 12 desde então"],
    ["Devedores", "quem deve mais de R$60 não entra na lista"],
    ["Grenal", "jogo temático Grêmio x Inter"],
    ["Ultra-temporada 26/1", "a temporada \"até o Canova perder\""],
    ["R.I.P. Season", "\"o biofut está morto\", temporada 2026/2"],
    ["Copa BioFut", "o mata-mata"],
    ["Bolão", "aposta no placar ou na Copa"],
    ["Diretoria", "o conselho, o presidente, a burocracia fictícia"],
    ["Corneta", "o esporte principal do grupo"],
    ["Resenha", "o pós-jogo"],
    ["Ceva", "a moeda real das apostas"],
    ["Verde / Preto", "as cores dos coletes"],
]
SONGS = [
    ["BioFut Rap", "o hino"], ["BioFut Warrior", ""], ["Prisma Biofut", ""],
    ["DAN DA DAN do a Sarrada", "Dan, na abertura de Dandadan"], ["TMCHB", "o dia mais caótico da história do BioFut"],
    ["EsquizoFut", ""], ["Gol Minhoca", "para o Matte"],
    ["Goleiro Lendário Douglas", "para o Douglas"], ["Nego Dei", "para o Andrei"], ["Nico Gol", ""],
    ["K9", "para o Canova"], ["é!", ""], ["é?", ""], ["Big Tico of The Doug", ""], ["Big Tico of The Doug 2", ""],
    ["3 é Demais", ""],
]
SONGS_URL = "https://soundcloud.com/h-mind/sets/biofut-hits-2025-1"


def main():
    gs = games()
    terms = [l.split(",") for l in TERMS.read_text(encoding="utf-8").splitlines()[1:121]]
    data = {
        "games": gs,
        "model": fit(sorted(gs, key=lambda g: g["n"])),
        "terms": [[t, int(c)] for t, c in terms],
        "nicknames": NICKNAMES, "glossary": GLOSSARY, "songs": SONGS, "songs_url": SONGS_URL,
        "pix": {"key": PIX_KEY, "payload": pix.payload(PIX_KEY, "BIOFUT", "PORTO ALEGRE", "APOIESITE", "Apoio pelo site BioFut, aba Apoie")},
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT}: {len(gs)} games, model on {data['model']['games']}, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if sys.argv[1:2] == ["--refit"] and len(sys.argv) > 2:
        refit(*sys.argv[2:])
    else:
        main()

"""Build site/biofut.json: full match history, BioBet model weights, lexicon, Pix payload.

Run locally (needs numpy + sklearn for the odds model; the server itself is stdlib only):
    python build_data.py
Sources (read-only): the other agents' handoffs from 2026-10-03.
"""
import json, sqlite3, sys
from pathlib import Path

H = Path("L:/GAB/Agents/Handoffs")
DB = H / "claude-biofut-data/2026-10-03/biofut.db"
TERMS = H / "claude-biofut-data/2026-10-03/terms.csv"
sys.path[:0] = [str(Path(__file__).parent), str(H / "claude-biobet/2026-10-03"), str(H / "claude-code-biofoot-community/2026-10-03/repo/site")]
import biobet, pix  # noqa: E402

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


def model():
    gs = biobet.load_games()
    m = biobet.Model().fit(gs)
    return {"games": len(gs), "classes": [str(k) for k in m.clf.classes_], "coef": m.clf.coef_.round(5).tolist(),
            "intercept": m.clf.intercept_.round(5).tolist(), "players": m.players, "shrink": m.SHRINK,
            "pairs": {f"{p}|{q}": v for (p, q), v in m.pair.items() if v[1]}}


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
        "model": model(),
        "terms": [[t, int(c)] for t, c in terms],
        "nicknames": NICKNAMES, "glossary": GLOSSARY, "songs": SONGS, "songs_url": SONGS_URL,
        "pix": {"key": PIX_KEY, "payload": pix.payload(PIX_KEY, "BIOFUT", "PORTO ALEGRE", "APOIESITE", "Apoio pelo site BioFut, aba Apoie")},
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{OUT}: {len(gs)} games, {len(data['model']['players'])} model players, {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()

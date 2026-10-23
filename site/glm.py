"""BioBet model: a Poisson GLM on the table stats of the players on each team. Stdlib only.

Each player's per-game stats come from the games before the match (the table the site shows), shrunk toward the
league mean with SHRINK pseudo-games. A team is the sums and means of its players' stats; a match is team A, team B
and A - B. The GLM gives A's goal rate; swapping the teams gives B's. Two independent Poisson goal counts give the
win / draw / loss odds and the expected score.
Fit by build_data.py (fit, needs numpy + sklearn), evaluated here by server.py, chosen by backtest.py (walk-forward).
"""
import math

SHRINK = 5  # pseudo-games at the league mean added to every player's rates
MAX_GOALS = 40  # Poisson tail cut for the outcome odds: P(more) is ~0 at the rates this league plays
TEAM = ("gpg", "apg", "win", "pts", "tgf", "tga", "form", "n", "heads", "new")
FEATURES = [f"{s}_{k}" for s in ("a", "b", "d") for k in TEAM]  # a, b, a - b


def player_table(games, k=SHRINK):
    """name -> per-game stats from `games` (in play order), plus the league mean row for names it has not seen."""
    acc = {}
    for g in games:
        for t in g["teams"]:
            w, pts = {"V": (1, 3), "E": (.5, 1), "D": (0, 0)}.get(t.get("res"), (.5, 1))
            for p, gl, ast, *_ in t["players"]:
                s = acc.setdefault(p, {"n": 0, "g": 0, "a": 0, "w": 0, "pts": 0, "gf": 0, "ga": 0, "last": []})
                s["n"] += 1; s["g"] += gl or 0; s["a"] += ast or 0; s["gf"] += t["gf"]; s["ga"] += t["ga"]
                s["w"] += w; s["pts"] += pts; s["last"] = (s["last"] + [w])[-10:]
    n = sum(s["n"] for s in acc.values()) or 1
    mean = {"gpg": sum(s["g"] for s in acc.values()) / n, "apg": sum(s["a"] for s in acc.values()) / n, "win": .5,
            "pts": sum(s["pts"] for s in acc.values()) / n, "tgf": sum(s["gf"] for s in acc.values()) / n,
            "tga": sum(s["ga"] for s in acc.values()) / n}
    tab = {}
    for p, s in acc.items():
        f = lambda tot, m: (tot + k * m) / (s["n"] + k)
        tab[p] = {"gpg": f(s["g"], mean["gpg"]), "apg": f(s["a"], mean["apg"]), "win": f(s["w"], .5),
                  "pts": f(s["pts"], mean["pts"]), "tgf": f(s["gf"], mean["tgf"]), "tga": f(s["ga"], mean["tga"]),
                  "form": (sum(s["last"]) + 2 * .5) / (len(s["last"]) + 2), "n": math.log1p(s["n"])}
    return tab, {**mean, "form": .5, "n": 0.0}


def team_vec(tab, mean, names):
    rows = [tab.get(p, mean) for p in names] or [mean]
    v = [sum(r[k] for r in rows) for k in ("gpg", "apg")]  # attack scales with heads
    v += [sum(r[k] for r in rows) / len(rows) for k in ("win", "pts", "tgf", "tga", "form", "n")]
    return v + [len(names), sum(p not in tab for p in names)]


def match_x(tab, mean, a, b):
    """Features of team a scoring against team b (FEATURES order)."""
    va, vb = team_vec(tab, mean, a), team_vec(tab, mean, b)
    return va + vb + [x - y for x, y in zip(va, vb)]


def rate(model, x):
    """Expected goals for the row x."""
    z = model["intercept"] + sum(c * (v - m) / s for c, v, m, s in zip(model["coef"], x, model["mu"], model["sd"]))
    return math.exp(min(z, 5))  # exp(5) ~ 150 goals: a cap against a broken row, never reached by real teams


def outcome(la, lb):
    """Independent Poisson goals with rates la, lb -> P(a wins), P(draw), P(b wins)."""
    def pmf(lam):
        p, out = math.exp(-lam), []
        for k in range(MAX_GOALS):
            out.append(p); p *= lam / (k + 1)
        return out
    pa, pb = pmf(la), pmf(lb)
    cb = [0.0]  # cb[k] = P(b < k)
    for p in pb:
        cb.append(cb[-1] + p)
    win = sum(p * cb[k] for k, p in enumerate(pa))
    draw = sum(p * q for p, q in zip(pa, pb))
    tot = sum(pa) * sum(pb)
    return win / tot, draw / tot, (tot - win - draw) / tot


def predict(model, games, a, b):
    """Team a vs team b from the table of `games` -> (P(A), P(E), P(B), goals a, goals b)."""
    tab, mean = player_table(games, model.get("shrink", SHRINK))
    la, lb = rate(model, match_x(tab, mean, a, b)), rate(model, match_x(tab, mean, b, a))
    return (*outcome(la, lb), la, lb)

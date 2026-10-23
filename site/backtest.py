"""Walk-forward backtest of the BioBet model: the shipped Poisson GLM (glm.py + build_data.fit) against base rates,
xgboost on the same inputs and, when the data still carries it, the logistic BioBet used before 2026-10-23.
Usage: python backtest.py data.json [extra_games.json]   (data.json: a saved https://biofut.h-brain.org/api/data;
extra: games the sheet does not have yet, a list, appended after it). Needs numpy, scipy, sklearn, xgboost.
Test = games after the logistic's training cut (n > 216). Every test game is predicted from earlier games only;
the models are refit every 10 test games. Re-run it each month: xgboost is the challenger."""
import json, math, sys
from itertools import combinations
import numpy as np
from scipy.stats import poisson
import xgboost as xgb

import glm
from build_data import fit

D = json.load(open(sys.argv[1], encoding="utf-8"))
G = sorted(D["games"], key=lambda g: g["n"])
if len(sys.argv) > 2:
    G += json.load(open(sys.argv[2], encoding="utf-8"))
CUT = 216  # the logistic's training games: the test starts after them


def logistic_odds(model, a, b):
    """The pre-GLM BioBet: players one-hot + pair chemistry (the server's odds() until 2026-10-23)."""
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
    return {cls: v / sum(e) for cls, v in zip(model["classes"], e)}


def names(t):
    return [p[0] for p in t["players"]]


def res_idx(g):
    return {"V": 0, "E": 1, "D": 2}[g["teams"][0]["res"]]


def xgb_fit(hist):
    X, y = [], []
    for i in range(20, len(hist)):
        tab, mean = glm.player_table(hist[:i])
        a, b = hist[i]["teams"]
        for s, o in ((a, b), (b, a)):
            X.append(glm.match_x(tab, mean, names(s), names(o))); y.append(s["gf"])
    return xgb.XGBRegressor(objective="count:poisson", n_estimators=150, max_depth=2, learning_rate=0.05,
                            subsample=0.8, colsample_bytree=0.8, min_child_weight=5).fit(np.array(X), np.array(y))


def outcome_probs(la, lb):
    k = np.arange(25)
    m = np.outer(poisson.pmf(k, la), poisson.pmf(k, lb))
    return [np.tril(m, -1).sum(), np.trace(m), np.triu(m, 1).sum()]


old = D["model"] if "pairs" in D.get("model", {}) else None
test = [g for g in G if g["n"] > CUT]
kinds = (["logistic"] if old else []) + ["base", "glm", "xgb"]
res = {k: {"ll": [], "acc": [], "mae": []} for k in kinds}
base_rates = np.bincount([res_idx(g) for g in G if g["n"] <= CUT], minlength=3) / CUT
avg_goals = np.mean([t["gf"] for g in G if g["n"] <= CUT for t in g["teams"]])
preds = []
for j, g in enumerate(test):
    hist = G[:G.index(g)]
    if j % 10 == 0:
        model, xg = fit(hist), xgb_fit(hist)
    a, b = g["teams"]
    i = res_idx(g)
    out = {"base": (list(base_rates), (avg_goals, avg_goals))}
    if old:
        o = logistic_odds(old, names(a), names(b))
        out["logistic"] = ([o["A"], o["E"], o["B"]], None)
    pa, pe, pb, la, lb = glm.predict(model, hist, names(a), names(b))
    out["glm"] = ([pa, pe, pb], (la, lb))
    tab, mean = glm.player_table(hist)
    la, lb = (xg.predict(np.array([glm.match_x(tab, mean, names(s), names(o))]))[0] for s, o in ((a, b), (b, a)))
    out["xgb"] = (outcome_probs(la, lb), (la, lb))
    for k, (p, gl) in out.items():
        res[k]["ll"].append(-math.log(max(p[i], 1e-9))); res[k]["acc"].append(int(np.argmax(p) == i))
        if gl:
            res[k]["mae"].append((abs(gl[0] - a["gf"]) + abs(gl[1] - b["gf"])) / 2)
    preds.append((g, out))

print(f"test games: {len(test)} (n {test[0]['n']}..{test[-1]['n']}), draws {sum(res_idx(g) == 1 for g in test)}")
print("| Model | Log loss | Accuracy | Goals per team, MAE |\n|---|---|---|---|")
for k in kinds:
    r = res[k]
    print(f"| {k} | {np.mean(r['ll']):.3f} | {np.mean(r['acc']):.2f} | " + (f"{np.mean(r['mae']):.2f} |" if r["mae"] else "none |"))
g, out = preds[-1]
a, b = g["teams"]
print(f"\nlast: {g['date']} {a['name']} {a['gf']} x {b['gf']} {b['name']}")
for k in kinds:
    p, gl = out[k]
    print(f"  {k:9s} A {p[0]:.0%} E {p[1]:.0%} B {p[2]:.0%}" + (f"  goals {gl[0]:.1f} x {gl[1]:.1f}" if gl else ""))

# per-player goals: team's predicted goals x the player's share of the team's goals per game (GLM, test games)
err_m, err_b = [], []
for g, out in preds:
    tab, mean = glm.player_table(G[:G.index(g)])
    for t, lam in zip(g["teams"], out["glm"][1]):
        r = [tab.get(p, mean)["gpg"] for p in names(t)]
        for (p, gl, *_), ri in zip(t["players"], r):
            err_m.append(abs(lam * ri / sum(r) - gl)); err_b.append(abs(avg_goals / len(r) - gl))
print(f"\nplayer goals MAE: model {np.mean(err_m):.3f} vs flat share {np.mean(err_b):.3f}")

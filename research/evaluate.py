"""Choose each rule's window on the design period, then score P1 to P3 on validation.

Writes research/results/portfolio.json.
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import PERIODS, cut, sharpe_diff_test, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk.weights import RULES  # noqa: E402

B = pickle.load(open("research/results/backtest.pkl", "rb"))
rf = B["rf"]
res = B["results"]
chosen, design_grid = {}, {}
for rule in RULES:
    opts = {w: summary(cut(v["daily"], "design"), rf)["sharpe"] for (r, w), v in res.items() if r == rule}
    design_grid[rule] = opts
    chosen[rule] = max(opts, key=opts.get)

daily = {r: res[(r, w)]["daily"] for r, w in chosen.items()}
daily["STX40"] = B["stx40"]
out = {"chosen_window": chosen, "design_grid": design_grid, "rules": {}}
for name, d in daily.items():
    out["rules"][name] = {p: summary(cut(d, p), rf) for p in PERIODS if len(cut(d, p)) > 2}
    if name in chosen:
        t = res[(name, chosen[name])]["turnover"]
        out["rules"][name]["turnover_per_month"] = float(np.mean(t[1:]))

val = {k: cut(v, "validation") for k, v in daily.items()}
vs = lambda k: out["rules"][k]["validation"]
p1 = vs("R3")["vol"] < min(vs("R1")["vol"], vs("STX40")["vol"])
p2 = {k: sharpe_diff_test(val[k], val["R1"], rf) for k in ("R3", "R4", "R5")}
p3 = sharpe_diff_test(val["R0"], val["R1"], rf)
out["tests"] = {
    "P1": {"passed": bool(p1), "vol": {k: vs(k)["vol"] for k in ("R3", "R1", "STX40")}},
    "P2": {"passed": bool(any(vs(k)["sharpe"] > vs("R1")["sharpe"] for k in p2)), "vs_R1": p2},
    "P3": {"passed": bool(vs("R0")["sharpe"] > vs("R1")["sharpe"]), "vs_R1": p3},
    "vs_STX40": {k: sharpe_diff_test(val[k], val["STX40"], rf) for k in chosen},
}
json.dump(out, open("research/results/portfolio.json", "w"), indent=1)

print("windows", chosen)
print(f"{'rule':6} {'CAGR':>7} {'vol':>6} {'Sharpe':>7} {'MDD':>7}  | design Sharpe")
for k in daily:
    v, d = vs(k), out["rules"][k]["design"]
    print(f"{k:6} {v['cagr']:7.1%} {v['vol']:6.1%} {v['sharpe']:7.2f} {v['mdd']:7.1%}  | {d['sharpe']:.2f}")
print(json.dumps(out["tests"], indent=1))

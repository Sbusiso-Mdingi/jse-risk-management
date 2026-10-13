"""Stress the latest portfolio of each rule (first: the 30 September 2026 freeze). Writes research/results/stress.json."""
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import data, stress  # noqa: E402

RAW = Path("data/raw")
B = pickle.load(open("research/results/backtest.pkl", "rb"))
P = json.load(open("research/results/portfolio.json"))
cal = B["calendar"]
freeze = B["month_ends"][-1]
names = sorted(set().union(*(B["results"][(k, w)]["book"][-1]["weights"].index for k, w in P["chosen_window"].items())))
prices = data.panel(RAW, names, cal)["adjusted"].ffill()
prices = prices[prices.index <= freeze]
j200 = data.series(RAW, "_J200.JO.csv", cal)
zar = data.series(RAW, "ZAR_X.csv", cal)
j200, zar = j200[j200.index <= freeze], zar[zar.index <= freeze]
out = {}
for k, w in P["chosen_window"].items():
    book = B["results"][(k, w)]["book"][-1]
    wt = book["weights"][book["weights"] > 1e-6]
    out[k] = {"historical": stress.historical(wt, prices, j200), "hypothetical": stress.hypothetical(wt, prices, zar)}
    print(k, [f"{s['key']} {s['portfolio_return']:+.1%} (idx {s['index_return']:+.1%}, proxied {s['proxied_weight']:.0%})" for s in out[k]["historical"]])
    print("  ", [(s["key"], round(s.get("portfolio_return", s.get("var99_after", 0)), 4)) for s in out[k]["hypothetical"]])
json.dump(out, open("research/results/stress.json", "w"), indent=1)

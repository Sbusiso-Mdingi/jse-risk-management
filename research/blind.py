"""The dashboard's blind month: for every month end, what each rule held and how it did the month after.

Writes data/blind.json. Only derived results are stored (the 40 names, each rule's weights and its daily
returns before costs); share prices are fetched by the service at run time and not redistributed.
"""
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import weights  # noqa: E402

B = pickle.load(open("research/results/backtest.pkl", "rb"))
P = json.load(open("research/results/portfolio.json"))
names = json.load(open("data/raw/names.json"))
cal, ends, stx = B["calendar"], B["month_ends"], B["stx40"]
r5 = lambda x: round(float(x), 5)
START = pd.Timestamp("2008-12-31")  # the Satrix 40 series is usable from January 2009

books = {}
for rule, w in P["chosen_window"].items():
    res = B["results"][(rule, w)]
    books[rule] = {b["date"]: b for b in res["book"]}
    books[rule]["_daily"] = res["daily"]

months = []
for m, nxt in zip(ends[:-1], ends[1:]):
    if m < START or nxt > cal[-1]:
        continue
    days = cal[(cal > m) & (cal <= nxt)]
    uni = B["universe"][m]
    rules = {}
    for rule in P["chosen_window"]:
        b = books[rule][m]
        d = books[rule]["_daily"].reindex(days).fillna(0.0).copy()
        d.iloc[0] += b["cost"]  # before costs, so a fresh portfolio and a rebalanced one compare alike
        wt = b["weights"].reindex(uni).fillna(0.0)
        rules[rule] = {"w": [r5(x) for x in wt], "r": [r5(x) for x in d]}
    months.append({
        "date": str(m.date()),
        "next": str(nxt.date()),
        "days": [str(x.date()) for x in days],
        "tickers": list(uni),
        "rules": rules,
        "stx40": [r5(x) for x in stx.reindex(days).fillna(0.0)],
    })

out = {
    "labels": {k: weights.RULES[k][0] for k in P["chosen_window"]},
    "names": {t: names.get(t, t) for m in months for t in m["tickers"]},
    "months": months,
}
Path("data/blind.json").write_text(json.dumps(out, separators=(",", ":")))
print(f"data/blind.json {Path('data/blind.json').stat().st_size / 1e3:.0f} kB, {len(months)} months, "
      f"{months[0]['date']} to {months[-1]['date']}")

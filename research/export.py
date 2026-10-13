"""Collect the research results into data/research.json for the dashboard and the service."""
import json
import pickle
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import BUY_COST, FREEZE, SELL_COST, risk, weights  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import PERIODS  # noqa: E402

B = pickle.load(open("research/results/backtest.pkl", "rb"))
P = json.load(open("research/results/portfolio.json"))
V = json.load(open("research/results/var.json"))
VS = pickle.load(open("research/results/var_series.pkl", "rb"))
S = json.load(open("research/results/stress.json"))
names = json.load(open("data/raw/names.json"))
r4 = lambda x: round(float(x), 6)

daily = {k: B["results"][(k, w)]["daily"] for k, w in P["chosen_window"].items()}
daily["STX40"] = B["stx40"]
cal = B["calendar"]
start = pd.Timestamp("2008-01-02")
wk = [d for d, n in zip(cal[:-1], cal[1:]) if d >= start and (n - d).days > 1 and n.weekday() < d.weekday()] + [cal[-1]]
curves = {"date": [str(d.date()) for d in wk]}
for k, d in daily.items():
    g = (1 + d[d.index >= start]).cumprod()
    curves[k] = [round(float(x), 5) for x in g.reindex(wk)]


def verdict(passed: bool, t: float | None) -> str:
    if not passed:
        return "Failed"
    return "Passed, within noise" if t is not None and abs(t) < 2 else "Passed"


T = P["tests"]
best = max(("R3", "R4", "R5"), key=lambda k: P["rules"][k]["validation"]["sharpe"])
tests = [
    {"id": "P1", "claim": "Minimum variance has lower volatility than equal weight and the Satrix 40",
     "verdict": "Passed" if T["P1"]["passed"] else "Failed", "detail": T["P1"]["vol"]},
    {"id": "P2", "claim": "An optimised rule (R3, R4 or R5) has a higher Sharpe ratio than equal weight",
     "verdict": verdict(T["P2"]["passed"], T["P2"]["vs_R1"][best]["t_stat"]), "best": best, "detail": T["P2"]["vs_R1"]},
    {"id": "P3", "claim": "The original app's method has a higher Sharpe ratio than equal weight",
     "verdict": verdict(T["P3"]["passed"], T["P3"]["vs_R1"]["t_stat"]), "detail": T["P3"]["vs_R1"]},
]

books = {}
for k, w in P["chosen_window"].items():
    bk = B["results"][(k, w)]["book"]
    books[k] = [{"date": str(b["date"].date()), "cost": r4(b["cost"]),
                 "weights": {t: r4(x) for t, x in b["weights"].items() if x > 1e-6}}
                for b in bk if str(b["date"].date()) >= FREEZE]

# The service recomputes these from live prices; tests/test_parity.py checks it matches.
live_daily = {k: {str(i.date()): r4(x) for i, x in d[d.index > pd.Timestamp(FREEZE)].items()} for k, d in daily.items()}

var = {}
for name, d in VS.items():
    var[name] = {"date": [str(x.date()) for x in d["date"]], "r": [r4(x) for x in d["r"]],
                 **{m: [r4(x) for x in d[f"{m}_0.99"][:, 0]] for m in risk.LABELS},
                 "tests": V[name]["models"]}

latest = B["month_ends"][-1]
out = {
    "generated": date.today().isoformat(),
    "freeze": FREEZE,
    "data_end": str(cal[-1].date()),
    "latest_rebalance": str(latest.date()),
    "periods": PERIODS,
    "costs": {"buy": BUY_COST, "sell": SELL_COST},
    "rules": {k: {"label": weights.RULES[k][0], "window": P["chosen_window"][k],
                  "design_grid": P["design_grid"][k], **P["rules"][k]} for k in P["chosen_window"]}
    | {"STX40": {"label": "Satrix 40 ETF", **P["rules"]["STX40"]}},
    "tests": tests,
    "vs_stx40": T["vs_STX40"],
    "curves": curves,
    "var": var,
    "var_labels": risk.LABELS,
    "stress": S,
    "books": books,
    "live_daily": live_daily,
    "universe": [{"ticker": t, "name": names.get(t, t)} for t in B["universe"][latest]],
    "all_tickers": [{"ticker": t, "name": names.get(t, t)} for t in sorted(names) if t.endswith(".JO") and not t.startswith("^") and t != "STX40.JO"],
}
Path("data/research.json").write_text(json.dumps(out, separators=(",", ":")))
print(f"data/research.json {Path('data/research.json').stat().st_size / 1e3:.0f} kB; latest rebalance {latest.date()}")

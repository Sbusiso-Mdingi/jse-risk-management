"""Walk-forward backtest of rules R0 to R5 (research/PROTOCOL.md).

At each month end: pick the 40 most traded eligible names, set weights from data up to that
close, then hold (weights drift) to the next month end. Writes research/results/backtest.pkl.
"""
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import data, weights  # noqa: E402
from jserisk.book import hold, trade_cost  # noqa: E402

RAW = Path("data/raw")
OUT = Path("research/results")
OUT.mkdir(parents=True, exist_ok=True)
N, HIST, LIQ = 40, 504, 63
MISSING = 0.10
WINDOWS = [252, 504]
from jserisk import BUY_COST, SELL_COST  # noqa: E402
START = "2007-12-31"  # first rebalance; the last is the latest complete month

tickers = [t.strip() for t in open("research/universe.txt") if t.strip()]
bench = data.read(RAW / "_J200.JO.csv")
calendar = bench.index[bench.index <= pd.Timestamp.today().normalize() - pd.Timedelta(days=1)]
P = data.panel(RAW, tickers, calendar)
adj = P["adjusted"]
filled = adj.ffill()
ret = filled.pct_change(fill_method=None)            # accounting: a gap's move lands on the next trade
est = ret.where(adj.notna())                          # estimation: missing days stay missing
value = (P["close"] * P["volume"]).where(adj.notna())
first = adj.apply(lambda s: s.first_valid_index())
rf_annual = data.tbill(RAW, calendar)
stx = data.series(RAW, "STX40.JO.csv", calendar)

month_ends = [d for d, nxt in zip(calendar[:-1], calendar[1:]) if d.month != nxt.month]
month_ends = [d for d in month_ends if str(d.date()) >= START]
pos = {d: i for i, d in enumerate(calendar)}


def eligible(i: int) -> list[str]:
    hist = est.iloc[max(0, i - HIST + 1): i + 1]
    ok = [t for t in adj.columns
          if pd.notna(first[t]) and pos[first[t]] <= i - HIST and hist[t].isna().mean() <= MISSING
          and pd.notna(adj[t].iloc[i])]
    liq = value[ok].iloc[i - LIQ + 1: i + 1].median()
    return list(liq.sort_values(ascending=False).index[:N])


def weekly(names: list[str], i: int) -> np.ndarray:
    """The app's input: Wednesday closes, log returns, rows with any gap dropped (156 weeks)."""
    px = filled[names].iloc[: i + 1]
    wed = px[px.index.weekday == 2].iloc[-157:]
    return np.log(wed).diff().iloc[1:].to_numpy()


def target(rule: str, names: list[str], i: int, window: int) -> np.ndarray:
    if rule == "R0":
        return weights.original(weekly(names, i), seed=i)
    r = est[names].iloc[i - window + 1: i + 1].to_numpy()
    fn = weights.RULES[rule][1]
    return fn(r, rf=rf_annual.iloc[i] / 252)


def run(rule: str, window: int) -> dict:
    daily = pd.Series(0.0, index=calendar)
    book, turnover = [], []
    held = pd.Series(dtype=float)  # current drifted weights
    for k, m in enumerate(month_ends):
        i = pos[m]
        names = universe[m]
        w = pd.Series(target(rule, names, i, window), index=names)
        cost, turn = trade_cost(w, held, BUY_COST, SELL_COST)
        turnover.append(turn)
        book.append({"date": m, "weights": w, "cost": cost})
        j_end = pos[month_ends[k + 1]] if k + 1 < len(month_ends) else len(calendar) - 1
        d, held = hold(w, cost, ret.iloc[i + 1: j_end + 1])
        daily.iloc[i + 1: j_end + 1] = d.to_numpy()
    return {"daily": daily, "book": book, "turnover": turnover}


t0 = time.time()
universe = {m: eligible(pos[m]) for m in month_ends}
print(f"universe built in {time.time() - t0:.0f}s; names ever held: {len(set().union(*universe.values()))}")
results = {}
for rule in weights.RULES:
    for window in ([156] if rule == "R0" else WINDOWS):
        t0 = time.time()
        results[(rule, window)] = run(rule, window)
        print(rule, window, f"{time.time() - t0:.0f}s")

pickle.dump({"calendar": calendar, "month_ends": month_ends, "universe": universe, "results": results,
             "stx40": stx.pct_change(fill_method=None).fillna(0.0), "j200": bench["adjusted"].reindex(calendar).pct_change(fill_method=None).fillna(0.0),
             "rf": rf_annual / 252}, open(OUT / "backtest.pkl", "wb"))

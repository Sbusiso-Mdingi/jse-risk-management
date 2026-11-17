"""The rules under a JSE cost schedule, beside the flat costs fixed in the protocol.

The protocol charges 10 bps a side plus 0.25% securities transfer tax on purchases. That is about right
for an institution with a low-touch desk and too low for a retail account. This script re-prices every
rebalance under two schedules and reports the validation figures. Reporting only: the verdicts were set
on the protocol's costs and stand.

Per execution: brokerage (plus 15% VAT), half the bid-ask spread, and Strate settlement with the investor
protection levy. On every purchase: securities transfer tax of 0.25% of value.

Sources: SARS, securities transfer tax 0.25% on transfers of listed securities (sars.gov.za); EasyEquities
commission 0.25% (easyequities.co.za/pricing); Standard Bank AutoShare Invest brokerage 0.15%
(standardbank.co.za). VAT 15% by statute. Strate and the levy are about 1 bp per execution at retail size
and less at institutional size. The half-spread is an assumption for the 40 most traded JSE shares and is
varied below.

Writes research/results/costs.json.
"""
import json
import pickle
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import cut, sharpe_diff_test, summary  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import BUY_COST, SELL_COST  # noqa: E402

STT, VAT = 25.0, 0.15
TIERS = {
    "protocol": dict(label="Protocol: 10 bps a side, flat", brokerage=10.0, vat=False, spread=0.0, strate=0.0),
    "institutional": dict(label="JSE, institutional", brokerage=10.0, vat=True, spread=5.0, strate=0.3),
    "retail": dict(label="JSE, retail brokerage", brokerage=25.0, vat=True, spread=5.0, strate=1.0),
    "retail_wide": dict(label="JSE, retail, wider spreads", brokerage=25.0, vat=True, spread=15.0, strate=1.0),
}


def side(t):
    """Cost of one execution, as a fraction of value traded (before transfer tax)."""
    return (t["brokerage"] * (1 + VAT if t["vat"] else 1) + t["spread"] + t["strate"]) / 1e4


def repriced(res, t):
    """Daily returns with each rebalance charged under schedule t instead of the protocol's costs."""
    daily = res["daily"].copy()
    s = side(t)
    buy_rate, sell_rate = s + STT / 1e4, s
    for b, turn in zip(res["book"], res["turnover"]):
        # The book stores cost and one-way turnover; buys + sells = 2 × turnover recovers each side.
        bought = (b["cost"] - 2 * turn * SELL_COST) / (BUY_COST - SELL_COST)
        sold = 2 * turn - bought
        first = daily.index[daily.index > b["date"]]
        if len(first):
            daily[first[0]] += b["cost"] - (bought * buy_rate + sold * sell_rate)
    return daily


B = pickle.load(open("research/results/backtest.pkl", "rb"))
P = json.load(open("research/results/portfolio.json"))
rf, stx = B["rf"], cut(B["stx40"], "validation")
out = {"tiers": {k: {**v, "per_side_bps": side(v) * 1e4, "round_trip_bps": 2 * side(v) * 1e4 + STT}
                 for k, v in TIERS.items()}, "rules": {}}
for rule, w in P["chosen_window"].items():
    res = B["results"][(rule, w)]
    row = {"turnover_per_month": P["rules"][rule]["turnover_per_month"]}
    eq = None
    for k, t in TIERS.items():
        v = cut(repriced(res, t), "validation")
        s = summary(v, rf)
        if k == "protocol":
            gap = (v - cut(res["daily"], "validation")).abs().max()
            assert gap < 1e-12, f"{rule}: protocol re-pricing does not reproduce the backtest ({gap})"
        row[k] = {"cagr": s["cagr"], "sharpe": s["sharpe"], "vs_stx40": sharpe_diff_test(v, stx, rf)}
    out["rules"][rule] = row

# P2 and P3 compare rules with equal weight: does either verdict change under the JSE schedules?
for k in TIERS:
    sh = {r: out["rules"][r][k]["sharpe"] for r in out["rules"]}
    out.setdefault("verdicts", {})[k] = {
        "P2": any(sh[r] > sh["R1"] for r in ("R3", "R4", "R5")),
        "P3": sh["R0"] > sh["R1"],
        "best_vs_stx40": max(sh, key=sh.get),
    }
json.dump(out, open("research/results/costs.json", "w"), indent=1)

print(pd.DataFrame({k: [f"{v['per_side_bps']:.1f}", f"{v['round_trip_bps']:.1f}"] for k, v in out["tiers"].items()},
                   index=["bps a side", "round trip"]).to_string())
print()
rows = {r: {f"{k} CAGR": f"{d[k]['cagr']:.1%}" for k in TIERS} | {f"{k} SR": f"{d[k]['sharpe']:.2f}" for k in TIERS}
        for r, d in out["rules"].items()}
print(pd.DataFrame(rows).T.to_string())
print(json.dumps(out["verdicts"], indent=1))

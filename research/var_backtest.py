"""Daily VaR and ES forecasts for R1, R3 and the Satrix 40 over validation, and their backtests.

Writes research/results/var.json (summary) and var_series.pkl (daily forecasts for the charts).
"""
import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from jserisk import risk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stats import PERIODS  # noqa: E402

B = pickle.load(open("research/results/backtest.pkl", "rb"))
P = json.load(open("research/results/portfolio.json"))
series = {k: B["results"][(k, P["chosen_window"][k])]["daily"] for k in ("R1", "R3")}
stx = B["stx40"]
series["STX40"] = stx[stx.index >= "2009-01-06"]  # first full session of the ETF in the data
LEVELS = [0.99, 0.975]
a, b = PERIODS["validation"]

summary, daily = {}, {}
for name, s in series.items():
    s = s[s.index >= "2008-01-02"] if name != "STX40" else s
    r = s.to_numpy()
    idx = s.index
    test = np.where((idx >= a) & (idx <= b))[0]
    f = {(m, lv): np.empty((len(test), 2)) for m in list(risk.MODELS) + ["fhs"] for lv in LEVELS}
    for k, t in enumerate(test):
        past = r[:t]
        for m, fn in risk.MODELS.items():
            for lv in LEVELS:
                f[(m, lv)][k] = fn(past, lv)
        if k == 0 or idx[t].month != idx[t - 1].month:  # refit on data up to each month end
            g = risk.GJR(past)
        for lv in LEVELS:
            f[("fhs", lv)][k] = g.var_es(lv)
        g.update(r[t])
    real = r[test]
    out = {}
    for m in list(risk.MODELS) + ["fhs"]:
        v99, v975, es975 = f[(m, 0.99)][:, 0], f[(m, 0.975)][:, 0], f[(m, 0.975)][:, 1]
        h99, h975 = real < -v99, real < -v975
        out[m] = {
            "var99": {**risk.kupiec(h99, 0.01), **risk.christoffersen(h99, 0.01)},
            "var975": {**risk.kupiec(h975, 0.025), **risk.christoffersen(h975, 0.025)},
            "traffic_light": risk.traffic_light(h99),
            "es975_z2": risk.acerbi_szekely_z2(real, v975, es975),
            "mean_var99": float(v99.mean()),
        }
        out[m]["passed"] = bool(out[m]["var99"]["p_cc"] > 0.05 and out[m]["var975"]["p_cc"] > 0.05
                                and out[m]["es975_z2"] > -0.70)
    summary[name] = {"sessions": len(test), "models": out}
    daily[name] = {"date": idx[test], "r": real, **{f"{m}_{lv}": f[(m, lv)] for (m, lv) in f}}
    print(name, len(test))
    for m, o in out.items():
        print(f"  {m:10} 99%: {o['var99']['exceedances']:3d}/{o['var99']['expected']:.0f} p_cc={o['var99']['p_cc']:.3f}"
              f"  97.5%: {o['var975']['exceedances']:3d}/{o['var975']['expected']:.0f} p_cc={o['var975']['p_cc']:.3f}"
              f"  Z2={o['es975_z2']:+.2f}  red={o['traffic_light']['red']:.0%}  {'PASS' if o['passed'] else 'fail'}")

json.dump(summary, open("research/results/var.json", "w"), indent=1)
pickle.dump(daily, open("research/results/var_series.pkl", "wb"))

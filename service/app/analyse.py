"""Live calculations: a user's portfolio and the record of the frozen rules since 1 October 2026."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from jserisk import book, data, risk, stress, weights

MISSING = 0.10
FHS_MIN = 500


def calendar(j200: pd.DataFrame) -> pd.DatetimeIndex:
    return j200.dropna(subset=["adjusted"]).index  # the research calendar


def _target(rule: str, r: np.ndarray, weekly: np.ndarray, rf_daily: float, cap: float) -> np.ndarray:
    if rule == "R0":
        return weights.original(weekly, seed=0)
    return weights.RULES[rule][1](r, rf=rf_daily, cap=cap)


def portfolio(tickers: list[str], rule: str, window: int, frames: dict[str, pd.DataFrame],
              j200: pd.DataFrame, usdzar: pd.DataFrame, rf: float, cap: float = weights.CAP) -> dict:
    cal = calendar(j200)
    P = data.frames_to_panel({t: frames[t] for t in tickers if t in frames}, cal)
    adj = P["adjusted"]
    filled = adj.ffill()
    acc = filled.pct_change(fill_method=None)
    est = acc.where(adj.notna())
    recent = est.iloc[-window:]
    excluded = {t: "no data" for t in tickers if t not in adj.columns}
    names = []
    for t in adj.columns:
        if recent[t].isna().mean() > MISSING:
            excluded[t] = f"fewer than {int(window * (1 - MISSING))} sessions in the last {window}"
        elif adj[t].iloc[-5:].isna().all():
            excluded[t] = "no trade in the last five sessions"
        else:
            names.append(t)
    if len(names) < 2:
        return {"error": "Need at least two shares with enough history.", "excluded": excluded}

    r = recent[names].to_numpy()
    wed = filled[names][filled.index.weekday == 2].iloc[-157:]
    w = pd.Series(_target(rule, r, np.log(wed).diff().iloc[1:].to_numpy(), rf / 252, cap), index=names)
    S = weights.shrunk_cov(r)
    mu = np.nanmean(r, axis=0)
    wv = w.to_numpy()
    exp_ret, vol = float(wv @ mu * 252), float(math.sqrt(wv @ S @ wv * 252))

    hist = acc[names].iloc[-risk.FHS_WINDOW:].dropna() @ wv
    h = hist.to_numpy()
    var = {}
    for m, fn in risk.MODELS.items():
        var[m] = {"var99": fn(h, 0.99)[0], "var975": fn(h, 0.975)[0], "es975": fn(h, 0.975)[1]}
    if len(h) >= FHS_MIN:
        g = risk.GJR(h)
        var["fhs"] = {"var99": g.var_es(0.99)[0], "var975": g.var_es(0.975)[0], "es975": g.var_es(0.975)[1]}
    held = w[w > 1e-6]
    prices = filled[held.index]
    fx = data.drop_bad_prints(usdzar["adjusted"])
    fx = fx.reindex(cal.union(fx.index)).ffill().reindex(cal)
    idx = j200["adjusted"].reindex(cal)
    return {
        "as_of": str(cal[-1].date()),
        "rule": rule, "window": window, "rf": rf, "cap": cap,
        "weights": [{"ticker": t, "weight": float(x), "risk": float(c),
                     "ret": float(m * 252), "vol": float(math.sqrt(s * 252))}
                    for t, x, c, m, s in zip(names, wv, weights.risk_contributions(wv, S), mu, np.diag(S))],
        "excluded": excluded,
        "expected_return": exp_ret, "vol": vol, "sharpe": (exp_ret - rf) / vol,
        "frontier": weights.frontier(r, rf / 252, cap),
        "history_sessions": len(h),
        "var": var,
        "stress": {"historical": stress.historical(held, prices, idx),
                   "hypothetical": stress.hypothetical(held, prices, fx)},
    }


def live(books: dict[str, list[dict]], frames: dict[str, pd.DataFrame], j200: pd.DataFrame, freeze: str) -> dict:
    """Daily net returns of each frozen rule after the freeze, from its monthly books."""
    cal = calendar(j200)
    names = sorted({t for bks in books.values() for b in bks for t in b["weights"]})
    P = data.frames_to_panel({t: frames[t] for t in names if t in frames}, cal)
    acc = P["adjusted"].ffill().pct_change(fill_method=None)
    out = {}
    for rule, bks in books.items():
        parts = []
        for k, b in enumerate(bks):
            a = pd.Timestamp(b["date"])
            z = pd.Timestamp(bks[k + 1]["date"]) if k + 1 < len(bks) else cal[-1]
            rets = acc[(acc.index > a) & (acc.index <= z)]
            w = pd.Series(b["weights"])
            missing = [t for t in w.index if t not in rets.columns]
            if missing:
                raise KeyError(f"{rule}: no prices for {missing}")
            parts.append(book.hold(w, b["cost"], rets)[0])
        out[rule] = pd.concat(parts) if parts else pd.Series(dtype=float)
    stx = frames["STX40.JO"]
    s = data.drop_bad_prints(stx["adjusted"])
    s = s.reindex(cal.union(s.index)).ffill().reindex(cal).pct_change(fill_method=None)
    out["STX40"] = s[s.index > pd.Timestamp(freeze)]
    return out

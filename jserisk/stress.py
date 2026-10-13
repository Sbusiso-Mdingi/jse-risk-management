"""Historical and hypothetical stress scenarios for a set of weights."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

HISTORICAL = [
    ("gfc", "2008 financial crisis", "2008-05-01", "2009-03-31"),
    ("nenegate", "Finance minister change, Dec 2015", "2015-12-08", "2015-12-11"),
    ("covid", "Covid crash, 2020", "2020-02-01", "2020-03-31"),
    ("tariffs", "US tariff shock, Apr 2025", "2025-04-01", "2025-04-30"),
]
BETA_WINDOW = 504
FX_WEEKS = 104
Z99 = stats.norm.ppf(0.99)


def peak_to_trough(index: pd.Series, a: str, b: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """The Top 40's largest fall within [a, b]: the peak before the trough, both inside the window."""
    s = index[(index.index >= a) & (index.index <= b)].dropna()
    dd = s / s.cummax() - 1
    trough = dd.idxmin()
    peak = s[:trough].idxmax()
    # A window that is itself the event (Dec 2015) starts at the close before it.
    if peak == s.index[0] and a == b:
        peak = index.index[index.index.get_loc(peak) - 1]
    return peak, trough


def beta(y: pd.Series, x: pd.Series) -> float:
    d = pd.concat([y, x], axis=1).dropna()
    if len(d) < 60:
        return 1.0
    c = np.cov(d.iloc[:, 0], d.iloc[:, 1])
    return float(c[0, 1] / c[1, 1])


def historical(w: pd.Series, prices: pd.DataFrame, index: pd.Series) -> list[dict]:
    """Each holding takes its own return from peak to trough; without prices, beta × index return."""
    rets = prices[w.index].pct_change(fill_method=None)
    ir = index.pct_change(fill_method=None)
    out = []
    for key, label, a, b in HISTORICAL:
        p0, p1 = peak_to_trough(index, a, b)
        idx_ret = float(index[p1] / index[p0] - 1)
        hold, proxied = {}, []
        for t in w.index:
            x0, x1 = prices[t].get(p0), prices[t].get(p1)
            if pd.notna(x0) and pd.notna(x1):
                hold[t] = float(x1 / x0 - 1)
            else:
                b_ = beta(rets[t].iloc[-BETA_WINDOW:], ir.iloc[-BETA_WINDOW:])
                hold[t] = b_ * idx_ret
                proxied.append(t)
        pr = float(sum(w[t] * hold[t] for t in w.index))
        out.append({"key": key, "label": label, "start": str(p0.date()), "end": str(p1.date()),
                    "index_return": idx_ret, "portfolio_return": pr, "proxied": proxied,
                    "proxied_weight": float(w[proxied].sum()) if proxied else 0.0,
                    "worst": sorted(({"ticker": t, "return": hold[t], "contribution": float(w[t] * hold[t])}
                                     for t in w.index), key=lambda d: d["contribution"])[:5]})
    return out


def hypothetical(w: pd.Series, prices: pd.DataFrame, usdzar: pd.Series) -> list[dict]:
    r = np.log(prices[w.index]).diff().iloc[-BETA_WINDOW:]
    S = r.cov().to_numpy()
    sd = np.sqrt(np.diag(S))
    wv = w.to_numpy()
    base = Z99 * np.sqrt(wv @ S @ wv)
    C = np.full_like(S, 0.9)
    np.fill_diagonal(C, 1.0)
    corr = Z99 * np.sqrt(wv @ (np.outer(sd, sd) * C) @ wv)
    # Weekly: Yahoo's daily USD/ZAR close is not taken at the JSE close, which hides the link.
    wk = lambda s: np.log(s.resample("W-WED").last()).diff().iloc[-FX_WEEKS:]
    fx = wk(usdzar)
    betas = pd.Series({t: beta(wk(prices[t]), fx) for t in w.index})
    rand = float((w * betas).sum() * np.log(1.25))
    top = w.idxmax()
    return [
        {"key": "corr", "label": "Every correlation at 0.9", "var99_before": float(base), "var99_after": float(corr)},
        {"key": "vol", "label": "Volatilities doubled", "var99_before": float(base), "var99_after": float(2 * base)},
        {"key": "rand", "label": "Rand falls 20% against the dollar", "portfolio_return": rand,
         "rand_beta": float((w * betas).sum())},
        {"key": "default", "label": f"Largest holding ({top}) goes to zero", "portfolio_return": float(-w[top])},
    ]

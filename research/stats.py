"""Performance statistics and the Ledoit-Wolf (2008) test of a Sharpe ratio difference."""
import math

import numpy as np
import pandas as pd

PERIODS = {
    "design": ("2008-01-01", "2016-12-31"),
    "validation": ("2017-01-01", "2026-09-30"),
    "live": ("2026-10-01", "2100-01-01"),
}


def cut(s: pd.Series, period: str) -> pd.Series:
    a, b = PERIODS[period]
    return s[(s.index >= a) & (s.index <= b)]


def summary(r: pd.Series, rf: pd.Series) -> dict:
    ex = r - rf.reindex(r.index).fillna(0.0)
    eq = (1 + r).cumprod()
    years = len(r) / 252
    sd = r.std(ddof=1)
    return {
        "start": str(r.index[0].date()), "end": str(r.index[-1].date()), "sessions": len(r),
        "cagr": float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else None,
        "vol": float(sd * math.sqrt(252)),
        "sharpe": float(ex.mean() / ex.std(ddof=1) * math.sqrt(252)) if len(r) > 2 else None,
        "mdd": float((eq / eq.cummax() - 1).min()),
    }


def sharpe_diff_test(a: pd.Series, b: pd.Series, rf: pd.Series) -> dict:
    """HAC test that two Sharpe ratios are equal (Ledoit and Wolf 2008, delta method, Bartlett kernel)."""
    x = np.column_stack([a - rf, b - rf])
    x = x[~np.isnan(x).any(axis=1)]
    T = len(x)
    mu = x.mean(0)
    m2 = (x ** 2).mean(0)
    sr = mu / np.sqrt(m2 - mu ** 2)
    y = np.column_stack([x - mu, x ** 2 - m2])
    lags = int(4 * (T / 100) ** (2 / 9))
    psi = y.T @ y / T
    for L in range(1, lags + 1):
        g = y[L:].T @ y[:-L] / T
        psi += (1 - L / (lags + 1)) * (g + g.T)
    grad = np.array([
        m2[0] / (m2[0] - mu[0] ** 2) ** 1.5, -m2[1] / (m2[1] - mu[1] ** 2) ** 1.5,
        -0.5 * mu[0] / (m2[0] - mu[0] ** 2) ** 1.5, 0.5 * mu[1] / (m2[1] - mu[1] ** 2) ** 1.5,
    ])
    # y columns are (x1, x2, x1², x2²); grad is ordered to match.
    se = math.sqrt(grad @ psi @ grad / T)
    d = sr[0] - sr[1]
    return {"diff_annual": float(d * math.sqrt(252)), "t_stat": float(d / se)}

"""One-day value at risk and expected shortfall, and their backtests.

VaR and ES are reported as positive losses (fractions of portfolio value).
"""
from __future__ import annotations

import math

import numpy as np
from arch import arch_model
from scipy import stats

HS_WINDOW, FHS_WINDOW, LAMBDA = 250, 1000, 0.94


def historical(r: np.ndarray, alpha: float) -> tuple[float, float]:
    x = r[-HS_WINDOW:]
    q = np.quantile(x, 1 - alpha)
    return -q, -x[x <= q].mean()


def normal(r: np.ndarray, alpha: float) -> tuple[float, float]:
    x = r[-HS_WINDOW:]
    mu, sd = x.mean(), x.std(ddof=1)
    z = stats.norm.ppf(1 - alpha)
    return -(mu + sd * z), -(mu - sd * stats.norm.pdf(z) / (1 - alpha))


def ewma_sigma(r: np.ndarray) -> np.ndarray:
    """RiskMetrics variance path; entry t is the forecast for day t from data before it."""
    s2 = np.empty(len(r) + 1)
    s2[0] = np.var(r[:HS_WINDOW])
    for t, x in enumerate(r):
        s2[t + 1] = LAMBDA * s2[t] + (1 - LAMBDA) * x * x
    return np.sqrt(s2)


def ewma(r: np.ndarray, alpha: float) -> tuple[float, float]:
    sd = ewma_sigma(r)[-1]
    z = stats.norm.ppf(1 - alpha)
    return -sd * z, sd * stats.norm.pdf(z) / (1 - alpha)


class GJR:
    """GJR-GARCH(1,1) with Student t innovations, fitted once and then filtered forward."""

    def __init__(self, r: np.ndarray):
        x = 100 * r[-FHS_WINDOW:]
        res = arch_model(x, mean="Constant", vol="GARCH", p=1, o=1, q=1, dist="t").fit(disp="off")
        p = res.params
        self.mu, self.omega = p["mu"] / 100, p["omega"] / 1e4
        self.a, self.g, self.b = p["alpha[1]"], p["gamma[1]"], p["beta[1]"]
        self.z = np.asarray(res.std_resid)
        self.z = self.z[~np.isnan(self.z)]
        sig = np.asarray(res.conditional_volatility)[-1] / 100
        self.last_eps, self.last_s2 = r[-1] - self.mu, sig ** 2

    def step(self) -> float:
        """Volatility forecast for the next day."""
        e = self.last_eps
        return math.sqrt(self.omega + (self.a + self.g * (e < 0)) * e * e + self.b * self.last_s2)

    def update(self, r: float) -> None:
        s = self.step()
        self.last_eps, self.last_s2 = r - self.mu, s * s

    def var_es(self, alpha: float) -> tuple[float, float]:
        s = self.step()
        q = np.quantile(self.z, 1 - alpha)
        return -(self.mu + s * q), -(self.mu + s * self.z[self.z <= q].mean())


MODELS = {"historical": historical, "normal": normal, "ewma": ewma}
LABELS = {"historical": "Historical simulation", "normal": "Normal", "ewma": "EWMA (RiskMetrics)",
          "fhs": "Filtered historical (GJR-GARCH-t)"}


# ---- backtests ------------------------------------------------------------------------------

def kupiec(hits: np.ndarray, p: float) -> dict:
    T, x = len(hits), int(hits.sum())
    phat = x / T
    ll0 = (T - x) * math.log(1 - p) + x * math.log(p)
    ll1 = (T - x) * math.log(1 - phat) + x * math.log(phat) if 0 < x < T else 0.0
    lr = -2 * (ll0 - ll1)
    return {"exceedances": x, "expected": T * p, "lr": lr, "p_value": float(stats.chi2.sf(lr, 1))}


def christoffersen(hits: np.ndarray, p: float) -> dict:
    h = hits.astype(int)
    a, b = h[:-1], h[1:]
    n00, n01 = int(((a == 0) & (b == 0)).sum()), int(((a == 0) & (b == 1)).sum())
    n10, n11 = int(((a == 1) & (b == 0)).sum()), int(((a == 1) & (b == 1)).sum())
    pi0 = n01 / max(n00 + n01, 1)
    pi1 = n11 / max(n10 + n11, 1)
    pi = (n01 + n11) / max(n00 + n01 + n10 + n11, 1)
    L = lambda k, q: k * math.log(q) if k else 0.0
    ll_null = L(n00 + n10, 1 - pi) + L(n01 + n11, pi)
    ll_alt = L(n00, 1 - pi0) + L(n01, pi0) + L(n10, 1 - pi1) + L(n11, pi1)
    ind = -2 * (ll_null - ll_alt)
    cc = kupiec(hits, p)["lr"] + ind
    return {"lr_ind": ind, "p_ind": float(stats.chi2.sf(ind, 1)), "lr_cc": cc, "p_cc": float(stats.chi2.sf(cc, 2)),
            "clustered": n11}


def traffic_light(hits99: np.ndarray, window: int = 250) -> dict:
    """Basel zones for 99% VaR over every 250-day window: green up to 4 exceedances, red from 10."""
    c = np.convolve(hits99.astype(int), np.ones(window, int), "valid")
    zone = np.where(c <= 4, "green", np.where(c <= 9, "yellow", "red"))
    return {k: float((zone == k).mean()) for k in ("green", "yellow", "red")} | {"latest": int(c[-1]), "latest_zone": str(zone[-1])}


def acerbi_szekely_z2(r: np.ndarray, var: np.ndarray, es: np.ndarray, alpha: float = 0.975) -> float:
    """Z2 = Σ r_t 1{r_t < −VaR_t} / (T (1 − α) ES_t) + 1; about zero if ES is right, negative if too low."""
    hit = r < -var
    return float(np.sum(r * hit / es) / (len(r) * (1 - alpha)) + 1)

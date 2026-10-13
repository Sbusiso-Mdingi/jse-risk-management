"""Long-only portfolio rules. Every function takes a returns window (sessions by assets) only."""
from __future__ import annotations

import numpy as np
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf

CAP = 0.10


def shrunk_cov(r: np.ndarray) -> np.ndarray:
    """Ledoit-Wolf covariance of daily returns, with missing days filled by the asset mean."""
    x = np.where(np.isnan(r), np.nanmean(r, axis=0), r)
    return LedoitWolf().fit(x).covariance_


def equal(r: np.ndarray, **_) -> np.ndarray:
    return np.full(r.shape[1], 1 / r.shape[1])


def inverse_vol(r: np.ndarray, **_) -> np.ndarray:
    w = 1 / np.nanstd(r, axis=0, ddof=1)
    return w / w.sum()


def _solve(obj, n: int, cap: float, x0=None) -> np.ndarray:
    cap = max(cap, 1 / n)
    x0 = np.full(n, 1 / n) if x0 is None else x0
    res = minimize(obj, x0, method="SLSQP", bounds=[(0, cap)] * n,
                   constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1}],
                   options={"maxiter": 500, "ftol": 1e-12})
    w = np.clip(res.x, 0, None)
    return w / w.sum()


def min_variance(r: np.ndarray, cap: float = CAP, cov: np.ndarray | None = None, **_) -> np.ndarray:
    S = shrunk_cov(r) if cov is None else cov
    k = 1 / np.mean(np.diag(S))  # rescale so the solver sees numbers near one
    return _solve(lambda w: k * w @ S @ w, len(S), cap)


def risk_parity(r: np.ndarray, cov: np.ndarray | None = None, **_) -> np.ndarray:
    """Equal risk contribution through Spinu's convex problem: min ½y'Σy − Σ log(y) / n."""
    S = shrunk_cov(r) if cov is None else cov
    S = S / np.mean(np.diag(S))
    n = len(S)
    res = minimize(lambda y: 0.5 * y @ S @ y - np.log(y).sum() / n, np.full(n, 1.0),
                   jac=lambda y: S @ y - 1 / (n * y), method="L-BFGS-B", bounds=[(1e-9, None)] * n)
    return res.x / res.x.sum()


def max_sharpe(r: np.ndarray, rf: float = 0.0, cap: float = CAP, cov: np.ndarray | None = None, **_) -> np.ndarray:
    """Tangency portfolio with sample means; rf is the daily risk-free rate."""
    S = shrunk_cov(r) if cov is None else cov
    mu = np.nanmean(r, axis=0) - rf
    k = 1 / np.sqrt(np.mean(np.diag(S)))
    obj = lambda w: -(w @ mu) * k / np.sqrt(w @ S @ w)
    # Start from the best asset mix SLSQP can reach from equal weights and from min variance.
    starts = [np.full(len(S), 1 / len(S)), min_variance(r, cap, cov=S)]
    sols = [_solve(obj, len(S), cap, x0) for x0 in starts]
    return min(sols, key=obj)


def original(r_weekly: np.ndarray, sims: int = 5000, seed: int = 0, **_) -> np.ndarray:
    """The 2024 app: uniform random weights normalised to one, best mean / volatility, no risk-free rate."""
    rng = np.random.default_rng(seed)
    x = r_weekly[~np.isnan(r_weekly).any(axis=1)]
    mu, S = x.mean(axis=0), np.cov(x, rowvar=False)
    W = rng.uniform(size=(sims, x.shape[1]))
    W /= W.sum(axis=1, keepdims=True)
    ratio = (W @ mu) / np.sqrt(np.einsum("ij,jk,ik->i", W, S, W))
    return W[np.argmax(ratio)]


RULES = {
    "R0": ("Original app", original),
    "R1": ("Equal weight", equal),
    "R2": ("Inverse volatility", inverse_vol),
    "R3": ("Minimum variance", min_variance),
    "R4": ("Equal risk contribution", risk_parity),
    "R5": ("Maximum Sharpe", max_sharpe),
}


def risk_contributions(w: np.ndarray, S: np.ndarray) -> np.ndarray:
    m = S @ w
    return w * m / (w @ m)


def frontier(r: np.ndarray, rf: float, cap: float = CAP, points: int = 25) -> list[dict]:
    """Long-only efficient frontier (annualised) from sample means and the shrunk covariance."""
    S = shrunk_cov(r)
    mu = np.nanmean(r, axis=0)
    n = len(S)
    wmin = min_variance(r, cap, cov=S)
    lo = wmin @ mu
    hi = np.sort(mu)[::-1][: int(np.ceil(1 / max(cap, 1 / n)))].mean()  # best mean reachable under the cap
    out = []
    k = 1 / np.mean(np.diag(S))
    for target in np.linspace(lo, hi, points):
        res = minimize(lambda w: k * w @ S @ w, wmin, method="SLSQP", bounds=[(0, max(cap, 1 / n))] * n,
                       constraints=[{"type": "eq", "fun": lambda w: w.sum() - 1},
                                    {"type": "ineq", "fun": lambda w, t=target: w @ mu - t}],
                       options={"maxiter": 500, "ftol": 1e-12})
        if res.success:
            w = res.x
            out.append({"ret": float(w @ mu * 252), "vol": float(np.sqrt(w @ S @ w * 252))})
    return out

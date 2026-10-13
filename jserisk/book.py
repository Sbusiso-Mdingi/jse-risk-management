"""Holding a set of target weights between rebalances."""
from __future__ import annotations

import numpy as np
import pandas as pd


def hold(w: pd.Series, cost: float, rets: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Daily net returns of weights w bought at the close before rets starts, left to drift.

    Missing returns count as zero; the move is caught up on the next trade, because rets comes
    from prices carried forward. The rebalancing cost is charged on the first day.
    """
    r = rets[w.index].fillna(0.0).to_numpy()
    cur = w.to_numpy(dtype=float).copy()
    out = np.empty(len(r))
    for j, x in enumerate(r):
        g = float(cur @ x)
        out[j] = g
        cur = cur * (1 + x) / (1 + g)
    if len(out):
        out[0] -= cost
    return pd.Series(out, index=rets.index), pd.Series(cur, index=w.index)


def trade_cost(target: pd.Series, held: pd.Series, buy: float, sell: float) -> tuple[float, float]:
    """Cost of moving from drifted weights to target, and one-way turnover."""
    delta = target.sub(held, fill_value=0.0)
    cost = delta.clip(lower=0).sum() * buy + (-delta.clip(upper=0)).sum() * sell
    return float(cost), float(delta.abs().sum() / 2)

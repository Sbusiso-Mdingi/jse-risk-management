"""The blind month: set weights at a past month end, get the next day's loss forecast, then see the month.

The rules' weights and paths come from data/blind.json (research output). The visitor's own portfolio is
priced from Yahoo at run time, with the same GJR-GARCH-t filtered historical simulation that passed the
backtests: fitted on the 1,000 sessions to the month end and filtered forward one day at a time.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from jserisk import data, risk

ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parents[2]))
BLIND = json.loads((ROOT / "data" / "blind.json").read_text())
MONTHS = {m["date"]: m for m in BLIND["months"]}
MIN_HISTORY = 500


def index() -> dict:
    return {"labels": BLIND["labels"], "months": [{"date": m["date"], "next": m["next"]} for m in BLIND["months"]]}


def _panel(m: dict, frames: dict[str, pd.DataFrame], j200: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    cal = j200.dropna(subset=["adjusted"]).index  # the research calendar
    P = data.frames_to_panel({t: frames[t] for t in m["tickers"] if t in frames}, cal)
    adj = P["adjusted"]
    rets = adj.ffill().pct_change(fill_method=None).where(adj.notna())
    return rets, cal


def month(date: str, frames: dict[str, pd.DataFrame], j200: pd.DataFrame) -> dict:
    """The 40 shares on offer at the month end, each rule's weights, and what each share did in the year to then."""
    m = MONTHS[date]
    rets, _ = _panel(m, frames, j200)
    past = rets[rets.index <= pd.Timestamp(date)].iloc[-252:]
    shares = []
    for i, t in enumerate(m["tickers"]):
        x = past[t].dropna() if t in past else pd.Series(dtype=float)
        shares.append({
            "ticker": t,
            "name": BLIND["names"].get(t, t),
            "w": {k: r["w"][i] for k, r in m["rules"].items()},
            "ret1y": float((1 + x).prod() - 1) if len(x) > 150 else None,
            "vol1y": float(x.std() * math.sqrt(252)) if len(x) > 150 else None,
        })
    return {"date": m["date"], "next": m["next"], "sessions": len(m["days"]), "labels": BLIND["labels"], "shares": shares}


def play(date: str, w: dict[str, float], frames: dict[str, pd.DataFrame], j200: pd.DataFrame) -> dict:
    """The visitor's forecast for the first day, then the month day by day against the forecast."""
    m = MONTHS[date]
    rets, _ = _panel(m, frames, j200)
    names = [t for t in m["tickers"] if w.get(t, 0) > 0 and t in rets]
    wv = np.array([w[t] for t in names], dtype=float)
    wv = wv / wv.sum()
    end = pd.Timestamp(date)
    hist = rets.loc[rets.index <= end, names].iloc[-risk.FHS_WINDOW:].fillna(0.0) @ wv
    h = hist.to_numpy()
    if len(h) < MIN_HISTORY:
        return {"error": "Not enough price history for these shares at this date."}
    g = risk.GJR(h)
    v0, e0 = g.var_es(0.99)
    days = pd.DatetimeIndex(pd.to_datetime(m["days"]))
    nxt = rets.reindex(days)[names].fillna(0.0).to_numpy()
    cur, path, var = wv.copy(), [], []
    for x in nxt:
        v, _ = g.var_es(0.99)
        r = float(cur @ x)
        var.append(float(v))
        path.append(r)
        g.update(r)
        cur = cur * (1 + x) / (1 + r)
    path_a = np.array(path)
    hits = [i for i, (r, v) in enumerate(zip(path, var)) if r < -v]
    return {
        "date": m["date"], "next": m["next"], "days": m["days"],
        "weights": {t: float(x) for t, x in zip(names, wv)},
        "forecast": {"var99": float(v0), "es99": float(e0), "sessions": int(len(h))},
        "you": path, "var99": var, "hits": hits,
        "month_return": float(np.prod(1 + path_a) - 1),
        "rules": {k: r["r"] for k, r in m["rules"].items()},
        "stx40": m["stx40"],
        "labels": BLIND["labels"],
    }

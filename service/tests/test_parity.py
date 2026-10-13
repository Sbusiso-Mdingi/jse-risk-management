"""The service must reproduce the research record from the same prices."""
import json
from pathlib import Path

import pandas as pd
import pytest

from app import analyse
from jserisk import data

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
R = json.loads((ROOT / "data" / "research.json").read_text())
pytestmark = pytest.mark.skipif(not (RAW / "_J200.JO.csv").exists(), reason="run research/fetch.py first")


def frames(tickers):
    out = {}
    for t in tickers:
        f = RAW / f"{t.replace('^', '_').replace('=', '_')}.csv"
        if f.exists():
            out[t] = data.read(f)
    return out


def test_live_record_matches_research():
    names = sorted({t for bks in R["books"].values() for b in bks for t in b["weights"]})
    fr = frames(names + ["^J200.JO", "STX40.JO"])
    j200 = fr["^J200.JO"]
    j200 = j200[j200.index <= pd.Timestamp(R["data_end"])]
    rec = analyse.live(R["books"], fr, j200, R["freeze"])
    for rule, expected in R["live_daily"].items():
        got = rec[rule]
        assert len(got) == len(expected) > 0, rule
        for d, x in expected.items():
            assert got[pd.Timestamp(d)] == pytest.approx(x, abs=2e-6), (rule, d)


def test_portfolio_runs_on_the_frozen_universe():
    names = [u["ticker"] for u in R["universe"]][:15]
    fr = frames(names + ["^J200.JO", "ZAR=X"])
    for rule in ("R0", "R1", "R3", "R4", "R5"):
        out = analyse.portfolio(names, rule, 252, fr, fr["^J200.JO"], fr["ZAR=X"], 0.07)
        w = sum(x["weight"] for x in out["weights"])
        assert w == pytest.approx(1, abs=1e-6)
        assert all(x["weight"] <= 0.10 + 1e-6 for x in out["weights"]) or rule in ("R0", "R1", "R4")
        assert out["var"]["fhs"]["var99"] > out["var"]["fhs"]["var975"] > 0
        assert len(out["stress"]["historical"]) == 4

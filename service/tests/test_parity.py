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


def test_total_return_series():
    """Prices are total returns built from the close and Yahoo's dividend events (research/PROTOCOL.md, amendment
    of 12 November 2026): an ex-dividend session earns (close + dividend) / previous close, units fixed when an
    amount is 100 times too large, repeated listings counted once, preference shares left on Yahoo's own series."""
    import numpy as np

    idx = pd.to_datetime(["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-02-20", "2026-03-02"])
    df = pd.DataFrame({"adjusted": [100.0, 98.0, 99.0, 99.0, 99.0, 99.0], "close": [100.0, 98.0, 99.0, 99.0, 99.0, 99.0],
                       "volume": 1.0, "dividend": [0.0, 3.0, 0.0, 300.0, 2.0, 2.0]}, index=idx)
    out = data.with_dividends(df, "XYZ.JO")
    r = out["adjusted"].pct_change().to_numpy()
    assert r[1] == pytest.approx((98 + 3) / 100 - 1)          # a 3c dividend on a 100c share
    assert r[3] == pytest.approx(3 / 99)                       # 300 is 100 times too large: 3c
    assert r[4] == pytest.approx(0.0) and r[5] == pytest.approx(2 / 99)  # one dividend listed twice counts once, last
    assert out["adjusted"].iloc[-1] == pytest.approx(99.0)
    assert np.allclose(out["adjusted_yahoo"], df["adjusted"])
    assert data.with_dividends(df, "NPKP.JO")["adjusted"].equals(df["adjusted"])
    sbk = data.read(RAW / "SBK.JO.csv")
    sbk = sbk[(sbk.index >= "2017-01-01") & (sbk.index <= "2026-09-30")]
    extra = (np.log(sbk["adjusted"].iloc[-1] / sbk["adjusted"].iloc[0]) - np.log(sbk["adjusted_yahoo"].iloc[-1] / sbk["adjusted_yahoo"].iloc[0])) / (len(sbk) / 252)
    assert 0.04 < extra < 0.09                                 # Standard Bank's dividends: about 6% a year

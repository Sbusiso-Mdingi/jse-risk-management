"""Load and clean daily prices into aligned panels."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

JUMP = 0.4
# A single dividend above this share of the previous close is treated as a data error and ignored.
MAX_YIELD = 0.25
# "yahoo" reproduces the record before the dividend correction of 12 November 2026 (research/PROTOCOL.md).
PRICES = os.environ.get("JSERISK_PRICES", "total_return")
# Preference shares keep Yahoo's adjusted close: their dividend amounts and even their prices switch between rand
# and cents on Yahoo, and Yahoo's one-hundredth adjustment happens to fit most of their amounts. Not checked further.
PREFERENCE = {"AFEP.JO", "CATP.JO", "CPIP.JO", "DSBP.JO", "GNDP.JO", "INPPR.JO", "INPR.JO", "NPKP.JO", "NTCP.JO",
              "SBKP.JO", "SBPP.JO", "TFGP.JO"}


def dedupe(div: pd.Series, days: int = 45) -> pd.Series:
    """Yahoo sometimes lists one dividend two or three times (for example on the quarter end and again on the ex-date,
    as for the Satrix 40 to 2024). The same amount (within 0.5%) within `days` of the next listing counts once, on
    its last listing."""
    ev = div[div > 0]
    keep = div.copy()
    for (t0, a0), (t1, a1) in zip(ev.items(), list(ev.items())[1:]):
        if (t1 - t0).days <= days and abs(a1 / a0 - 1) <= 0.005:
            keep[t0] = 0.0
    return keep


def with_dividends(df: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
    """Replace "adjusted" with a total-return series built from the close and the dividend paid on each session.

    Yahoo's adjusted close for JSE shares carries only about a hundredth of each dividend (the dividend in cents
    treated as rand), so its returns are close to price returns. Here the return on an ex-dividend session is
    (close + dividend) / previous close, and the series is scaled to end at the last close. Yahoo's dividend amounts
    are mostly in cents but sometimes 100 times too large (most preference shares, and some events elsewhere): a
    dividend above MAX_YIELD of the previous close is divided by 100, one between 10% and MAX_YIELD takes whichever
    unit the ex-date price drop fits better, and one still above MAX_YIELD is ignored. Yahoo's own column is kept
    as "adjusted_yahoo". Frames without a dividend column (older downloads, FX, indices) are returned unchanged.
    """
    if "dividend" not in df.columns or PRICES == "yahoo" or ticker in PREFERENCE:
        return df
    df = df.copy()
    df["adjusted_yahoo"] = df["adjusted"]
    c = df["close"].astype(float)
    ok = c.notna() & (c > 0)
    cc = c[ok]
    d = dedupe(df.loc[ok, "dividend"].fillna(0.0).astype(float))
    prev = cc.shift(1)
    y = (d / prev).fillna(0.0)
    y = y.where(y <= MAX_YIELD, y / 100)                       # Yahoo's amounts are sometimes 100 times too large
    r = np.log(cc / prev).fillna(0.0)
    ambiguous = (y > 0.10) & (y <= MAX_YIELD)
    y = y.where(~ambiguous | ((r + y).abs() <= (r + y / 100).abs()), y / 100)  # pick the unit the ex-date drop fits
    y = y.where((y >= 0) & (y <= MAX_YIELD), 0.0)              # anything still implausible is a data error
    gross = (cc / prev + y).fillna(1.0)
    tr = gross.cumprod()
    df["adjusted"] = np.nan
    df.loc[ok, "adjusted"] = tr / tr.iloc[-1] * cc.iloc[-1]
    return df


def drop_bad_prints(px: pd.Series) -> pd.Series:
    """Drop single days whose price jumps by more than 40% and reverses the next day.

    Same rule as the stat-arb project (for example a quote in rand rather than cents).
    """
    px = px[px > 0].dropna()
    lim = np.log(1 + JUMP)
    while len(px) > 2:
        r = np.diff(np.log(px.to_numpy()))
        a, b = r[:-1], r[1:]
        bad = np.where((np.abs(a) > lim) & (np.sign(a) != np.sign(b)) & (np.abs(a + b) < lim / 4))[0] + 1
        if not len(bad):
            break
        px = px.drop(px.index[bad])
    return px


def read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["date"])
    # FX quotes can carry two rows for one date; keep the last complete one.
    df = df.dropna(subset=["adjusted"]).drop_duplicates("date", keep="last").set_index("date").sort_index()
    return with_dividends(df, path.stem.replace("_", "^", 1) if path.stem.startswith("_") else path.stem)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop no-trade days (zero volume and an unchanged close) and bad prints.

    A stale quote must never count as a return of zero.
    """
    stale = (df["volume"].fillna(0) <= 0) & (df["close"].diff() == 0)
    df = df[~stale]
    return df.loc[drop_bad_prints(df["adjusted"]).index]


def frames_to_panel(frames: dict[str, pd.DataFrame], calendar: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    """Adjusted prices, closes and volumes on the JSE calendar, from raw frames per ticker."""
    cleaned = {t: clean(df) for t, df in frames.items()}
    return {k: pd.DataFrame({t: df[k] for t, df in cleaned.items()}, columns=list(cleaned)).reindex(calendar)
            for k in ("adjusted", "close", "volume")}


def panel(raw: Path, tickers: list[str], calendar: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
    frames = {t: read(raw / f"{t}.csv") for t in tickers if (raw / f"{t}.csv").exists()}
    return frames_to_panel(frames, calendar)


def series(raw: Path, name: str, calendar: pd.DatetimeIndex) -> pd.Series:
    """A benchmark or FX series on the JSE calendar, carried forward over gaps."""
    df = read(raw / name)
    return drop_bad_prints(df["adjusted"]).reindex(calendar.union(df.index)).ffill().reindex(calendar)


def tbill(raw: Path, calendar: pd.DatetimeIndex) -> pd.Series:
    """Annual 91-day T-bill rate as a decimal, carried forward from each monthly print.

    Each month's average is known only once the month ends, so it applies from the next month.
    """
    df = pd.read_csv(raw / "tbill.csv", parse_dates=["observation_date"]).dropna()
    s = pd.Series(df.iloc[:, 1].astype(float).to_numpy() / 100, index=df["observation_date"] + pd.offsets.MonthBegin(1))
    return s.reindex(calendar.union(s.index)).ffill().reindex(calendar)

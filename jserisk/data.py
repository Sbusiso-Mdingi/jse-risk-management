"""Load and clean daily prices into aligned panels."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

JUMP = 0.4


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
    return df


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

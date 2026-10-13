"""Daily prices from Yahoo Finance and the T-bill rate from FRED, cached in memory."""
from __future__ import annotations

import concurrent.futures as cf
import io
import logging
import threading
import time
from datetime import datetime, timezone

import httpx
import pandas as pd

log = logging.getLogger("risk")
UA = {"User-Agent": "Mozilla/5.0"}
TTL = 6 * 3600
_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def _download(sym: str) -> pd.DataFrame:
    params = {"period1": int(datetime(2005, 1, 1, tzinfo=timezone.utc).timestamp()),
              "period2": int(time.time()), "interval": "1d", "events": "div,split"}
    last: Exception | None = None
    for attempt in range(3):
        try:
            r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params=params,
                          headers=UA, timeout=30)
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            dates = [datetime.fromtimestamp(t + 7200, timezone.utc).date() for t in res["timestamp"]]
            df = pd.DataFrame({"date": pd.to_datetime(dates), "adjusted": adj, "close": q["close"], "volume": q["volume"]})
            df = df.dropna(subset=["adjusted"]).drop_duplicates("date", keep="last").set_index("date").sort_index()
            return df.astype(float)
        except Exception as exc:  # Yahoo resets connections under load
            last = exc
            time.sleep(1 + 2 * attempt)
    raise RuntimeError(f"{sym}: {last}")


def prices(symbols: list[str]) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """Frames for each symbol (cached for six hours) and the errors for those that failed."""
    now = time.time()
    with _lock:
        need = [s for s in symbols if s not in _cache or now - _cache[s][0] > TTL]
    errors: dict[str, str] = {}
    if need:
        with cf.ThreadPoolExecutor(8) as ex:
            futs = {ex.submit(_download, s): s for s in need}
            for f in cf.as_completed(futs):
                s = futs[f]
                try:
                    df = f.result()
                    with _lock:
                        _cache[s] = (time.time(), df)
                except Exception as exc:
                    log.warning("price fetch failed: %s", exc)
                    errors[s] = str(exc)
    with _lock:
        # A stale copy beats nothing if a refresh failed.
        return {s: _cache[s][1] for s in symbols if s in _cache}, errors


_rf: tuple[float, float] | None = None


def tbill(fallback: float) -> float:
    """Latest SA 91-day T-bill rate (annual, decimal), refreshed daily."""
    global _rf
    if _rf and time.time() - _rf[0] < 86400:
        return _rf[1]
    try:
        r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": "INTGSTZAM193N"}, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text)).dropna()
        _rf = (time.time(), float(df.iloc[-1, 1]) / 100)
        return _rf[1]
    except Exception as exc:
        log.warning("T-bill fetch failed: %s", exc)
        return _rf[1] if _rf else fallback

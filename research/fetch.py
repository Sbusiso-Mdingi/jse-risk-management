"""Download daily prices for the universe, the Top 40 benchmarks, USD/ZAR and the SA T-bill rate.

Yahoo Finance data is for personal research and is not redistributed: everything lands in
data/raw/, which git ignores.
"""
import concurrent.futures as cf
import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

RAW = Path("data/raw")
RAW.mkdir(parents=True, exist_ok=True)
EXTRA = ["STX40.JO", "^J200.JO", "ZAR=X"]
TICKERS = [t.strip() for t in open("research/universe.txt") if t.strip()] + EXTRA
UA = {"User-Agent": "Mozilla/5.0"}
names: dict[str, str] = {}


def path(sym: str) -> Path:
    return RAW / f"{sym.replace('^', '_').replace('=', '_')}.csv"


def fetch(sym: str):
    params = {"period1": int(datetime(2005, 1, 1, tzinfo=timezone.utc).timestamp()),
              "period2": int(time.time()), "interval": "1d", "events": "div,split"}
    for attempt in range(4):
        try:
            r = httpx.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}", params=params,
                          headers=UA, timeout=40)
            if r.status_code == 404:
                return sym, "not found"
            r.raise_for_status()
            res = r.json()["chart"]["result"][0]
            names[sym] = res["meta"].get("longName") or res["meta"].get("shortName") or sym
            ts = res.get("timestamp") or []
            q = res["indicators"]["quote"][0]
            adj = (res["indicators"].get("adjclose") or [{}])[0].get("adjclose") or q["close"]
            with open(path(sym), "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["date", "adjusted", "close", "volume"])
                for t, a, c, v in zip(ts, adj, q["close"], q["volume"]):
                    # JSE sessions close at 17:00 SAST; the timestamp is the session open.
                    w.writerow([datetime.fromtimestamp(t + 7200, timezone.utc).date().isoformat(), a, c, v])
            return sym, len(ts)
        except Exception as exc:  # retried: Yahoo resets connections under load
            err = exc
            time.sleep(2 + attempt * 3)
    return sym, f"failed: {err}"


def tbill():
    r = httpx.get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": "INTGSTZAM193N"}, timeout=40)
    r.raise_for_status()
    (RAW / "tbill.csv").write_text(r.text)


if __name__ == "__main__":
    tbill()
    with cf.ThreadPoolExecutor(6) as ex:
        res = dict(ex.map(fetch, TICKERS))
    (RAW / "names.json").write_text(json.dumps(names, indent=0, sort_keys=True))
    bad = {k: v for k, v in res.items() if not isinstance(v, int)}
    print(f"{len(res) - len(bad)} downloaded; not available: {bad}")

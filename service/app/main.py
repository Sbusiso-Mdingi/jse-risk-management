"""HTTP service for the JSE portfolio risk dashboard."""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from jserisk.weights import RULES

from . import analyse, blind, market

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("risk")
ROOT = Path(os.environ.get("APP_ROOT", Path(__file__).resolve().parents[2]))
STATIC = ROOT / "dashboard" / "dist"
REFRESH_SECONDS = int(os.environ.get("REFRESH_SECONDS", "1800"))
ALLOWED_ORIGINS = ["https://mdingi.co.za", "https://www.mdingi.co.za", "http://localhost:3000",
                   "http://localhost:4321", "http://localhost:5173"]
FRAME_ANCESTORS = "'self' https://mdingi.co.za https://www.mdingi.co.za http://localhost:*"
MAX_TICKERS = 40
WINDOWS = (252, 504)
CAPS = (0.10, 0.20, 0.35, 1.0)

RESEARCH_BYTES = (ROOT / "data" / "research.json").read_bytes()
RESEARCH = json.loads(RESEARCH_BYTES)
TICKERS = {t["ticker"] for t in RESEARCH["all_tickers"]}
BOOK_NAMES = sorted({t for bks in RESEARCH["books"].values() for b in bks for t in b["weights"]})
BENCH = ["^J200.JO", "STX40.JO", "ZAR=X"]


def _clean(x):
    if isinstance(x, (float, np.floating)):
        x = float(x)
        return None if math.isnan(x) or math.isinf(x) else x
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    return x


class Live:
    """The frozen rules' record since the freeze, refreshed from live prices."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.payload: dict | None = None
        self.fetched_at = 0.0
        self.error: str | None = None

    def get(self) -> dict | None:
        if time.time() - self.fetched_at > REFRESH_SECONDS and self.lock.acquire(blocking=False):
            try:
                frames, errors = market.prices(BOOK_NAMES + BENCH)
                rec = analyse.live(RESEARCH["books"], frames, frames["^J200.JO"], RESEARCH["freeze"])
                dates = sorted(set().union(*(s.index for s in rec.values())))
                self.payload = {
                    "date": [str(d.date()) for d in dates],
                    "growth": {k: list((1 + s.reindex(dates).fillna(0.0)).cumprod()) for k, s in rec.items()},
                    "missing": sorted(errors),
                }
                self.error = None
            except Exception as exc:  # keep serving the last good record
                log.warning("live refresh failed: %s", exc)
                self.error = str(exc)
            finally:
                self.fetched_at = time.time()
                self.lock.release()
        return self.payload


live = Live()


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=live.get, daemon=True).start()  # warm the live record
    yield


app = FastAPI(title="JSE portfolio risk", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = f"frame-ancestors {FRAME_ANCESTORS}"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "public, max-age=300"
    return response


@app.get("/api/health")
def health():
    return {"ok": True, "live": live.payload is not None, "error": live.error}


@app.get("/api/research")
def research():
    return Response(RESEARCH_BYTES, media_type="application/json")


@app.get("/api/live")
def live_record():
    p = live.get()
    if p is None:
        raise HTTPException(503, "Live prices are still loading.")
    return JSONResponse(_clean({**p, "freeze": RESEARCH["freeze"], "error": live.error}))


@app.get("/api/portfolio")
def portfolio(tickers: str = Query(..., description="Comma-separated JSE tickers, e.g. NPN.JO,SBK.JO"),
              rule: str = "R3", window: int = 252, cap: float = 0.10):
    names = list(dict.fromkeys(t.strip().upper() for t in tickers.split(",") if t.strip()))
    if rule not in RULES:
        raise HTTPException(400, f"rule must be one of {sorted(RULES)}")
    if window not in WINDOWS:
        raise HTTPException(400, f"window must be one of {WINDOWS}")
    if cap not in CAPS:
        raise HTTPException(400, f"cap must be one of {CAPS}")
    unknown = [t for t in names if t not in TICKERS]
    if unknown or not 2 <= len(names) <= MAX_TICKERS:
        raise HTTPException(400, f"Choose 2 to {MAX_TICKERS} tickers from the universe. Unknown: {unknown}")
    frames, errors = market.prices(names + BENCH)
    if "^J200.JO" not in frames or "ZAR=X" not in frames:
        raise HTTPException(503, "Benchmark prices are unavailable right now.")
    rf = market.tbill(fallback=0.07)
    out = analyse.portfolio(names, rule, window, frames, frames["^J200.JO"], frames["ZAR=X"], rf, cap)
    out["fetch_errors"] = errors
    return JSONResponse(_clean(out))


@app.get("/api/blind/months")
def blind_months():
    return blind.index()


def _blind_frames(date: str):
    if date not in blind.MONTHS:
        raise HTTPException(400, "date must be one of the month ends in /api/blind/months")
    frames, errors = market.prices(blind.MONTHS[date]["tickers"] + ["^J200.JO"])
    if "^J200.JO" not in frames:
        raise HTTPException(503, "Index prices are unavailable right now.")
    return frames


@app.get("/api/blind/month")
def blind_month(date: str):
    frames = _blind_frames(date)
    return JSONResponse(_clean(blind.month(date, frames, frames["^J200.JO"])))


@app.get("/api/blind/play")
def blind_play(date: str, w: str = Query(..., description="Comma-separated TICKER:weight pairs, e.g. NPN.JO:0.5,SBK.JO:0.5")):
    frames = _blind_frames(date)
    weights_in: dict[str, float] = {}
    try:
        for part in w.split(","):
            t, x = part.split(":")
            weights_in[t.strip().upper()] = float(x)
    except ValueError:
        raise HTTPException(400, "w must be TICKER:weight pairs")
    allowed = set(blind.MONTHS[date]["tickers"])
    if any(t not in allowed for t in weights_in) or any(x < 0 or not math.isfinite(x) for x in weights_in.values()):
        raise HTTPException(400, "Weights must be non-negative and on that month's 40 shares.")
    if sum(1 for x in weights_in.values() if x > 0) < 1 or sum(weights_in.values()) <= 0:
        raise HTTPException(400, "Give at least one share a weight.")
    out = blind.play(date, weights_in, frames, frames["^J200.JO"])
    if "error" in out:
        raise HTTPException(422, out["error"])
    return JSONResponse(_clean(out))


if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if path and f.is_file() else STATIC / "index.html")

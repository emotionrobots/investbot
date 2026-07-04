"""Real market data via yfinance, with a short in-process cache so a single
trading cycle doesn't hammer the API."""
from __future__ import annotations

import time
from functools import lru_cache

import pandas as pd

try:
    import yfinance as yf
except Exception:  # pragma: no cover
    yf = None

_PRICE_CACHE: dict[str, tuple[float, float]] = {}   # ticker -> (ts, price)
_CACHE_TTL = 120  # seconds


def get_history(tickers: list[str], period: str = "6mo") -> pd.DataFrame:
    """Daily close prices; columns=tickers. Falls back to a synthetic random
    walk if yfinance is unavailable (keeps the sim runnable offline)."""
    if yf is not None:
        try:
            data = yf.download(
                tickers, period=period, interval="1d",
                auto_adjust=True, progress=False, threads=True,
            )
            close = data["Close"] if "Close" in data else data
            if isinstance(close, pd.Series):
                close = close.to_frame(name=tickers[0])
            close = close.dropna(how="all").ffill()
            if not close.empty:
                return close
        except Exception:
            pass
    return _synthetic_history(tickers)


def latest_prices(tickers: list[str]) -> dict[str, float]:
    now = time.time()
    out: dict[str, float] = {}
    missing = []
    for t in tickers:
        cached = _PRICE_CACHE.get(t)
        if cached and now - cached[0] < _CACHE_TTL:
            out[t] = cached[1]
        else:
            missing.append(t)
    if missing:
        hist = get_history(missing, period="5d")
        last = hist.ffill().iloc[-1]
        for t in missing:
            try:
                price = float(last[t]) if t in last else float(last.iloc[0])
            except Exception:
                price = 100.0
            _PRICE_CACHE[t] = (now, price)
            out[t] = price
    return out


def feature_frame(tickers: list[str]) -> pd.DataFrame:
    """Per-ticker technical/quant features the agents (and mock heuristics) use."""
    hist = get_history(tickers, period="6mo").ffill()
    rows = []
    for t in tickers:
        if t not in hist:
            continue
        s = hist[t].dropna()
        if len(s) < 25:
            continue
        ret_1m = s.iloc[-1] / s.iloc[-21] - 1 if len(s) > 21 else 0.0
        ret_3m = s.iloc[-1] / s.iloc[-63] - 1 if len(s) > 63 else ret_1m
        vol = s.pct_change().tail(21).std() * (252 ** 0.5)
        sma50 = s.tail(50).mean()
        above_sma = s.iloc[-1] > sma50
        rows.append(dict(
            ticker=t, price=float(s.iloc[-1]),
            ret_1m=float(ret_1m), ret_3m=float(ret_3m),
            vol=float(vol), above_sma=bool(above_sma),
        ))
    return pd.DataFrame(rows).set_index("ticker")


@lru_cache(maxsize=1)
def _seed_prices(tickers: tuple[str, ...]) -> dict[str, float]:
    import random
    rng = random.Random(42)
    return {t: rng.uniform(80, 400) for t in tickers}


def _synthetic_history(tickers: list[str]) -> pd.DataFrame:
    import numpy as np
    seeds = _seed_prices(tuple(tickers))
    days = 130
    idx = pd.date_range(end=pd.Timestamp.today().normalize(), periods=days, freq="B")
    rng = __import__("numpy").random.default_rng(7)
    cols = {}
    for t in tickers:
        steps = rng.normal(0.0005, 0.02, days)
        path = seeds[t] * np.exp(np.cumsum(steps))
        cols[t] = path
    return pd.DataFrame(cols, index=idx)

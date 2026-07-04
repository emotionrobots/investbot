"""Paper broker: fake capital, fills at real prices. Also marks NAV and tracks
the 'real portfolio' benchmark (buy-and-hold) for comparison
(spec/execution-trader.md, spec/performance-attribution-analyst.md)."""
from __future__ import annotations

import datetime as dt

from . import db
from .config import CONFIG
from .market_data import latest_prices
from .schemas import GateVerdict


def portfolio_value(prices: dict[str, float]) -> float:
    cash = db.get_cash()
    pos = db.get_positions()
    mv = sum(p["shares"] * prices.get(t, p["avg_cost"]) for t, p in pos.items())
    return cash + mv


def current_weights(prices: dict[str, float]) -> dict[str, float]:
    total = portfolio_value(prices) or 1.0
    pos = db.get_positions()
    return {t: (p["shares"] * prices.get(t, p["avg_cost"])) / total
            for t, p in pos.items()}


def execute(verdicts: list[GateVerdict], prices: dict[str, float],
            ts: str | None = None) -> list[dict]:
    """Work each APPROVED target weight into fills at the latest price."""
    ts = ts or dt.datetime.utcnow().isoformat()
    nav = portfolio_value(prices)
    fills: list[dict] = []
    for v in verdicts:
        if v.decision == "veto":
            continue
        price = prices.get(v.ticker)
        if not price:
            continue
        pos = db.get_positions().get(v.ticker, {"shares": 0.0, "avg_cost": price})
        target_val = v.approved_weight * nav
        target_shares = target_val / price
        delta = target_shares - pos["shares"]
        if abs(delta * price) < max(1.0, 0.002 * nav):  # ignore dust
            continue
        side = "BUY" if delta > 0 else "SELL"
        cash = db.get_cash()
        if side == "BUY":
            cost = delta * price
            if cost > cash:  # never go negative cash
                delta = cash / price
                cost = delta * price
            new_shares = pos["shares"] + delta
            new_cost = ((pos["shares"] * pos["avg_cost"]) + cost) / max(new_shares, 1e-9)
            db.set_cash(cash - cost)
            db.upsert_position(v.ticker, new_shares, new_cost)
        else:
            new_shares = pos["shares"] + delta  # delta negative
            proceeds = -delta * price
            db.set_cash(cash + proceeds)
            db.upsert_position(v.ticker, new_shares, pos["avg_cost"])
        db.record_trade(ts, v.ticker, side, abs(delta), price, v.reason)
        fill = dict(ts=ts, ticker=v.ticker, side=side, shares=round(abs(delta), 4),
                    price=round(price, 2), weight=v.approved_weight, reason=v.reason)
        fills.append(fill)
        db.journal(ts, "fill", fill, ticker=v.ticker)
    return fills


# --- Benchmark: the "real portfolio" (equal-weight buy-and-hold of a proxy) --
def _benchmark_units(prices: dict[str, float]) -> float:
    """Units of the benchmark ticker bought once with the full initial capital."""
    units = db.get_meta("benchmark_units")
    if units is not None:
        return float(units)
    b = CONFIG.benchmark
    price = latest_prices([b]).get(b, 100.0)
    u = db.initial_capital() / price
    db.set_meta("benchmark_units", u)
    db.set_meta("benchmark_ticker", b)
    return u


def benchmark_value() -> float:
    b = CONFIG.benchmark
    units = _benchmark_units({})
    price = latest_prices([b]).get(b, 100.0)
    return units * price


def mark_to_market(ts: str | None = None) -> dict:
    """Snapshot NAV (fake vs benchmark) into the DB and return it."""
    ts = ts or dt.datetime.utcnow().isoformat()
    prices = latest_prices(CONFIG.universe)
    fake = portfolio_value(prices)
    bench = benchmark_value()
    cash = db.get_cash()
    db.record_nav(ts, fake, bench, cash)
    init = db.initial_capital()
    snap = dict(ts=ts, fake_nav=round(fake, 2), benchmark_nav=round(bench, 2),
                cash=round(cash, 2),
                fake_roi=round((fake / init - 1) * 100, 3),
                benchmark_roi=round((bench / init - 1) * 100, 3),
                alpha=round((fake - bench) / init * 100, 3))
    return snap

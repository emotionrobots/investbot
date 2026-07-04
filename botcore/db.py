"""SQLite persistence: the append-only Decision Journal plus portfolio state,
NAV history, and per-agent trust weights (see spec/decision-journal-memory.md)."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable

from .config import CONFIG

_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
    ticker TEXT PRIMARY KEY,
    shares REAL NOT NULL DEFAULT 0,
    avg_cost REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS cash (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    amount REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS nav (
    ts TEXT NOT NULL,
    fake_nav REAL NOT NULL,
    benchmark_nav REAL NOT NULL,
    cash REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS trades (
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    shares REAL NOT NULL,
    price REAL NOT NULL,
    rationale TEXT
);
CREATE TABLE IF NOT EXISTS journal (
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,      -- signal | consensus | proposal | verdict | fill | report | note
    ticker TEXT,
    agent TEXT,
    payload TEXT NOT NULL    -- JSON snapshot
);
CREATE TABLE IF NOT EXISTS weights (
    agent TEXT PRIMARY KEY,
    weight REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

RESEARCH_AGENTS = [
    "fundamental-analyst",
    "quantitative-factor-analyst",
    "technical-analyst",
    "sentiment-news-analyst",
    "macro-sector-strategist",
    "alternative-data-analyst",
]


@contextmanager
def connect():
    con = sqlite3.connect(CONFIG.db_path, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db(capital: float | None = None) -> None:
    capital = CONFIG.capital if capital is None else capital
    with connect() as con:
        con.executescript(_SCHEMA)
        cur = con.execute("SELECT amount FROM cash WHERE id=1").fetchone()
        if cur is None:
            con.execute("INSERT INTO cash (id, amount) VALUES (1, ?)", (capital,))
            con.execute("INSERT OR REPLACE INTO meta VALUES ('initial_capital', ?)",
                        (str(capital),))
        for a in RESEARCH_AGENTS + ["red-team-devils-advocate"]:
            con.execute("INSERT OR IGNORE INTO weights (agent, weight) VALUES (?, 1.0)", (a,))


# --- portfolio state ---
def get_cash() -> float:
    with connect() as con:
        row = con.execute("SELECT amount FROM cash WHERE id=1").fetchone()
        return float(row["amount"]) if row else 0.0


def set_cash(amount: float) -> None:
    with connect() as con:
        con.execute("UPDATE cash SET amount=? WHERE id=1", (amount,))


def get_positions() -> dict[str, dict[str, float]]:
    with connect() as con:
        rows = con.execute("SELECT ticker, shares, avg_cost FROM positions").fetchall()
    return {r["ticker"]: {"shares": r["shares"], "avg_cost": r["avg_cost"]}
            for r in rows if abs(r["shares"]) > 1e-9}


def upsert_position(ticker: str, shares: float, avg_cost: float) -> None:
    with connect() as con:
        if abs(shares) < 1e-9:
            con.execute("DELETE FROM positions WHERE ticker=?", (ticker,))
        else:
            con.execute(
                "INSERT INTO positions (ticker, shares, avg_cost) VALUES (?,?,?) "
                "ON CONFLICT(ticker) DO UPDATE SET shares=?, avg_cost=?",
                (ticker, shares, avg_cost, shares, avg_cost),
            )


def record_trade(ts, ticker, side, shares, price, rationale="") -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO trades VALUES (?,?,?,?,?,?)",
            (ts, ticker, side, shares, price, rationale),
        )


def record_nav(ts, fake_nav, benchmark_nav, cash) -> None:
    with connect() as con:
        con.execute("INSERT INTO nav VALUES (?,?,?,?)", (ts, fake_nav, benchmark_nav, cash))


def journal(ts, kind, payload: Any, ticker=None, agent=None) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO journal VALUES (?,?,?,?,?)",
            (ts, kind, ticker, agent, json.dumps(payload, default=str)),
        )


def journal_many(rows: Iterable[tuple]) -> None:
    with connect() as con:
        con.executemany("INSERT INTO journal VALUES (?,?,?,?,?)", rows)


# --- learning ---
def get_weights() -> dict[str, float]:
    with connect() as con:
        rows = con.execute("SELECT agent, weight FROM weights").fetchall()
    return {r["agent"]: float(r["weight"]) for r in rows}


def set_weight(agent: str, weight: float) -> None:
    with connect() as con:
        con.execute(
            "INSERT INTO weights (agent, weight) VALUES (?,?) "
            "ON CONFLICT(agent) DO UPDATE SET weight=?",
            (agent, weight, weight),
        )


def get_meta(key: str, default=None):
    with connect() as con:
        row = con.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(key: str, value) -> None:
    with connect() as con:
        con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, str(value)))


def initial_capital() -> float:
    return float(get_meta("initial_capital", CONFIG.capital))

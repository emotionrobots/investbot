"""Chatbox backend: answer questions about the portfolio and the agents'
decisions. Uses Claude when available, grounded in live DB context; falls back
to a deterministic responder in mock mode."""
from __future__ import annotations

import json

from . import db, reporting
from .config import CONFIG
from .llm import get_llm


def _context() -> str:
    summ = reporting.performance_summary()
    pos = reporting.positions_table()
    weights = reporting.agent_weights_table()
    trades = reporting.trades_frame(10)
    with db.connect() as con:
        notes = con.execute(
            "SELECT ts, kind, agent, payload FROM journal "
            "WHERE kind IN ('note','verdict','consensus') ORDER BY ts DESC LIMIT 8"
        ).fetchall()
    ctx = {
        "performance": summ,
        "positions": pos.to_dict("records") if not pos.empty else [],
        "agent_trust_weights": weights.to_dict("records"),
        "recent_trades": trades.to_dict("records") if not trades.empty else [],
        "recent_decisions": [
            {"ts": n["ts"], "kind": n["kind"], "agent": n["agent"],
             "payload": json.loads(n["payload"])[:3] if n["payload"].startswith("[")
             else json.loads(n["payload"])}
            for n in notes
        ],
    }
    return json.dumps(ctx, default=str, indent=2)


SYSTEM = (
    "You are the InvestBot analyst assistant. You answer the operator's questions "
    "about a multi-agent paper-trading portfolio that trades a tech universe with "
    "FAKE capital and is benchmarked against a real buy-and-hold portfolio. Be "
    "concise and specific, cite numbers from the provided context, and never give "
    "personalized financial advice — this is a simulation."
)


def answer(question: str, history: list[dict] | None = None) -> str:
    llm = get_llm()
    ctx = _context()
    if llm is None:
        return _mock_answer(question)
    msgs = [("system", SYSTEM + "\n\nLIVE CONTEXT (JSON):\n" + ctx)]
    for turn in (history or [])[-6:]:
        msgs.append((turn["role"], turn["content"]))
    msgs.append(("human", question))
    try:
        return llm.invoke(msgs).content
    except Exception as e:
        return f"(LLM error: {e})\n\n" + _mock_answer(question)


def _mock_answer(q: str) -> str:
    ql = q.lower()
    summ = reporting.performance_summary()
    if any(k in ql for k in ("roi", "return", "perform", "doing", "alpha", "beat")):
        return (f"Fake-capital ROI is {summ['fake_roi']:+.2f}% vs the "
                f"{CONFIG.benchmark} benchmark's {summ['benchmark_roi']:+.2f}% — "
                f"alpha of {summ['alpha']:+.2f}pp. NAV ${summ['fake_nav']:,.0f}, "
                f"cash ${summ['cash']:,.0f}, {summ['positions']} positions, "
                f"Sharpe {summ.get('sharpe_annualized','n/a')}.")
    if any(k in ql for k in ("position", "hold", "own", "portfolio")):
        pos = reporting.positions_table()
        if pos.empty:
            return "The book is currently flat (all cash)."
        top = "; ".join(f"{r.ticker} {r.weight_pct:.1f}%" for r in pos.itertuples())
        return f"Current positions ({summ['positions']}): {top}."
    if any(k in ql for k in ("agent", "weight", "trust", "learn")):
        w = reporting.agent_weights_table()
        return "Agent trust weights (higher = more sizing influence):\n" + \
               "\n".join(f"- {r.agent}: {r.trust_weight:.2f}" for r in w.itertuples())
    if "trade" in ql:
        tr = reporting.trades_frame(5)
        if tr.empty:
            return "No trades yet."
        return "Recent trades:\n" + "\n".join(
            f"- {r.ts[:16]} {r.side} {r.shares:.1f} {r.ticker} @ ${r.price:.2f}"
            for r in tr.itertuples())
    return ("Ask me about performance/ROI, positions, recent trades, or agent "
            "trust weights. (Running in mock mode — set ANTHROPIC_API_KEY for the "
            "full Claude-powered assistant.)")

"""LangGraph wiring of the whole workflow — the topology from spec/agents.md:

  ingest → [6 research analysts] → red-team → PM
         → risk gate → compliance gate → execution → attribution/learning

Research generates signals; the gate can veto/resize but never originates; only
gate-approved targets reach execution."""
from __future__ import annotations

import datetime as dt
import json
import operator
from typing import Annotated, Any, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from . import agents, broker, db, learning
from .config import CONFIG
from .gates import compliance_gate, risk_gate
from .market_data import feature_frame, latest_prices

RESEARCH = db.RESEARCH_AGENTS


class TradingState(TypedDict, total=False):
    ts: str
    features: Any                       # pd.DataFrame
    prices: dict[str, float]
    current: dict[str, float]           # current weights
    weights: dict[str, float]           # per-agent trust weights
    signals: Annotated[list, operator.add]
    dissent: dict[str, str]
    consensus: list
    proposals: list
    verdicts: list
    fills: list
    snapshot: dict


# --- nodes -----------------------------------------------------------------
def ingest(state: TradingState) -> TradingState:
    ts = dt.datetime.utcnow().isoformat()
    feats = feature_frame(CONFIG.universe)
    prices = latest_prices(CONFIG.universe)
    return {
        "ts": ts, "features": feats, "prices": prices,
        "current": broker.current_weights(prices),
        "weights": db.get_weights(), "signals": [],
    }


def _make_research_node(slug: str):
    def node(state: TradingState) -> TradingState:
        sigs = agents.run_research_agent(slug, state["features"])
        rows = [(state["ts"], "signal", s.ticker, slug, json.dumps(s.model_dump()))
                for s in sigs]
        db.journal_many(rows)
        return {"signals": sigs}
    node.__name__ = f"research_{slug.replace('-', '_')}"
    return node


def red_team(state: TradingState) -> TradingState:
    dissent = agents.run_red_team(state["signals"])
    db.journal(state["ts"], "note", {"red_team": dissent}, agent="red-team-devils-advocate")
    return {"dissent": dissent}


def portfolio_manager(state: TradingState) -> TradingState:
    views = agents.aggregate(state["signals"], state["weights"], state["dissent"])
    proposals = agents.target_weights(
        views, state["current"], CONFIG.action_threshold,
        CONFIG.max_trade_weight_step, CONFIG.max_position_weight)
    db.journal(state["ts"], "consensus", [v.model_dump() for v in views])
    db.journal(state["ts"], "proposal", [p.model_dump() for p in proposals])
    return {"consensus": views, "proposals": proposals}


def risk_node(state: TradingState) -> TradingState:
    cash_weight = db.get_cash() / (broker.portfolio_value(state["prices"]) or 1.0)
    verdicts = risk_gate(state["proposals"], state["current"], cash_weight)
    db.journal(state["ts"], "verdict", [v.model_dump() for v in verdicts], agent="risk-manager")
    return {"verdicts": verdicts}


def compliance_node(state: TradingState) -> TradingState:
    verdicts = compliance_gate(state["verdicts"], state["current"])
    db.journal(state["ts"], "verdict", [v.model_dump() for v in verdicts],
               agent="compliance-guardrail")
    return {"verdicts": verdicts}


def execution_node(state: TradingState) -> TradingState:
    fills = broker.execute(state["verdicts"], state["prices"], ts=state["ts"])
    return {"fills": fills}


def attribution_learning(state: TradingState) -> TradingState:
    learning.update_trust_weights(state["consensus"])
    snapshot = broker.mark_to_market(ts=state["ts"])
    db.journal(state["ts"], "report", snapshot)
    return {"snapshot": snapshot}


# --- graph -----------------------------------------------------------------
def build_graph():
    g = StateGraph(TradingState)
    g.add_node("ingest", ingest)
    g.add_edge(START, "ingest")

    for slug in RESEARCH:
        name = f"research_{slug.replace('-', '_')}"
        g.add_node(name, _make_research_node(slug))
        g.add_edge("ingest", name)          # fan-out
        g.add_edge(name, "red_team")        # fan-in (red_team waits for all)

    g.add_node("red_team", red_team)
    g.add_node("pm", portfolio_manager)
    g.add_node("risk", risk_node)
    g.add_node("compliance", compliance_node)
    g.add_node("execution", execution_node)
    g.add_node("learn", attribution_learning)

    g.add_edge("red_team", "pm")
    g.add_edge("pm", "risk")
    g.add_edge("risk", "compliance")
    g.add_edge("compliance", "execution")
    g.add_edge("execution", "learn")
    g.add_edge("learn", END)
    return g.compile()


_GRAPH = None


def run_cycle() -> dict:
    """Execute one full perceive→reason→gate→execute→learn cycle."""
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = build_graph()
    db.init_db()
    final = _GRAPH.invoke({})
    return final.get("snapshot", {})

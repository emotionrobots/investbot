"""The mandatory risk-and-compliance gate. Deterministic — no LLM originates or
approves trades here (spec/risk-manager.md, spec/compliance-guardrail.md).

Every proposed trade must clear BOTH gates. Either can veto or resize; neither
can originate."""
from __future__ import annotations

import datetime as dt

from .config import CONFIG
from .db import connect
from .schemas import GateVerdict, ProposedTrade


def risk_gate(proposals: list[ProposedTrade], current: dict[str, float],
              cash_weight: float) -> list[GateVerdict]:
    """Enforce single-name cap, gross-exposure cap, and cash floor. Resizes down
    before vetoing when a smaller position would be compliant."""
    verdicts: list[GateVerdict] = []
    gross = sum(abs(w) for w in current.values())
    for p in proposals:
        approved = p.target_weight
        reason = "within risk budget"
        decision = "approve"

        # Single-name concentration cap.
        if approved > CONFIG.max_position_weight:
            approved = CONFIG.max_position_weight
            decision, reason = "resize", (
                f"single-name cap {CONFIG.max_position_weight:.0%}")

        # Gross-exposure cap (approximate marginal check).
        marginal = approved - current.get(p.ticker, 0.0)
        if marginal > 0 and gross + marginal > CONFIG.max_gross_exposure:
            room = max(0.0, CONFIG.max_gross_exposure - gross)
            approved = current.get(p.ticker, 0.0) + room
            decision = "resize" if approved > current.get(p.ticker, 0.0) else "veto"
            reason = f"gross-exposure cap {CONFIG.max_gross_exposure:.0%}"

        # Cash floor: don't deploy below the minimum cash buffer.
        if marginal > 0 and cash_weight - marginal < CONFIG.min_cash_weight:
            room = max(0.0, cash_weight - CONFIG.min_cash_weight)
            approved = current.get(p.ticker, 0.0) + room
            decision = "resize" if approved > current.get(p.ticker, 0.0) else "veto"
            reason = f"cash floor {CONFIG.min_cash_weight:.0%}"

        if abs(approved - current.get(p.ticker, 0.0)) < 0.005:
            decision, reason = "veto", f"{reason}: no compliant room"

        gross += max(0.0, approved - current.get(p.ticker, 0.0))
        verdicts.append(GateVerdict(
            ticker=p.ticker, decision=decision,
            approved_weight=round(approved, 4), reason=reason, gate="risk"))
    return verdicts


def _recent_loss_sale(ticker: str, days: int = 30) -> bool:
    """Very simplified wash-sale guard: was this name SOLD in the last `days`?"""
    cutoff = (dt.datetime.utcnow() - dt.timedelta(days=days)).isoformat()
    with connect() as con:
        row = con.execute(
            "SELECT COUNT(*) c FROM trades WHERE ticker=? AND side='SELL' AND ts>=?",
            (ticker, cutoff),
        ).fetchone()
    return bool(row["c"])


def compliance_gate(verdicts: list[GateVerdict],
                    current: dict[str, float]) -> list[GateVerdict]:
    """Deterministic hard rules: restricted list + wash-sale-style block on
    re-buying a recently sold name. Runs AFTER the risk gate."""
    out: list[GateVerdict] = []
    for v in verdicts:
        if v.decision == "veto":
            out.append(v)
            continue
        if v.ticker in CONFIG.restricted:
            out.append(GateVerdict(ticker=v.ticker, decision="veto",
                                   approved_weight=current.get(v.ticker, 0.0),
                                   reason="restricted list", gate="compliance"))
            continue
        buying = v.approved_weight > current.get(v.ticker, 0.0)
        if buying and _recent_loss_sale(v.ticker):
            out.append(GateVerdict(ticker=v.ticker, decision="veto",
                                   approved_weight=current.get(v.ticker, 0.0),
                                   reason="wash-sale window (sold <30d ago)",
                                   gate="compliance"))
            continue
        out.append(v)  # passes compliance; carry the risk verdict forward
    return out

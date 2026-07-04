"""Continuous learning: adjust per-agent trust weights from realized results,
so agents whose signals precede profitable moves earn more sizing influence over
time (the flywheel — spec/performance-attribution-analyst.md,
spec/decision-journal-memory.md).

This is a deliberately simple, transparent scheme: each cycle we compare each
consensus view's direction against the name's realized next-cycle return and
nudge the contributing agents' weights via an EMA."""
from __future__ import annotations

import json

from . import db
from .config import CONFIG
from .market_data import latest_prices

_LR = 0.05          # learning rate
_MIN_W, _MAX_W = 0.3, 2.5


def update_trust_weights(consensus: list) -> None:
    """Grade the PREVIOUS cycle's consensus against realized moves, then update.

    We stash the latest consensus + prices; on the next call we mark realized
    returns and reward/penalize the agents that contributed."""
    prices_now = latest_prices(CONFIG.universe)

    prev_raw = db.get_meta("pending_grade")
    if prev_raw:
        try:
            prev = json.loads(prev_raw)
            weights = db.get_weights()
            for item in prev["views"]:
                t = item["ticker"]
                if t not in prices_now or t not in prev["prices"]:
                    continue
                realized = prices_now[t] / prev["prices"][t] - 1.0
                # Reward a contributor when its signed contribution matched the move.
                for agent, contrib in item["contributors"].items():
                    aligned = contrib * realized            # >0 = correct call
                    delta = _LR * (1.0 if aligned > 0 else -1.0) * min(1.0, abs(realized) * 20)
                    w = weights.get(agent, 1.0) + delta * abs(contrib)
                    weights[agent] = max(_MIN_W, min(_MAX_W, w))
            for agent, w in weights.items():
                db.set_weight(agent, round(w, 4))
        except Exception as e:
            print(f"[learning] grade skipped: {e}")

    # Stash the current views to grade next cycle.
    payload = {
        "prices": {t: prices_now[t] for t in prices_now},
        "views": [
            {"ticker": v.ticker, "contributors": v.contributors}
            for v in consensus
        ],
    }
    db.set_meta("pending_grade", json.dumps(payload))

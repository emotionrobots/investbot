"""The agent pod. Each research analyst emits confidence-weighted Signals
(spec/*.md). Real mode calls Claude with a persona + structured output; mock
mode derives deterministic signals from market features so the sim runs free."""
from __future__ import annotations

import hashlib

import pandas as pd

from .llm import get_llm
from .schemas import AgentSignals, ConsensusView, ProposedTrade, Signal

# --- Personas (condensed from spec/*.md) -----------------------------------
PERSONAS: dict[str, str] = {
    "fundamental-analyst":
        "You are a Fundamental Analyst on a tech-focused desk. Judge earnings "
        "quality, revenue-growth durability, gross-margin trajectory, and SaaS "
        "unit economics. Emit confidence-weighted signals, never orders.",
    "quantitative-factor-analyst":
        "You are a Quant/Factor Analyst. Keep factor loadings intentional "
        "(momentum, quality, value, low-vol). Ground signals in cross-sectional "
        "evidence; prefer signals that would survive out-of-sample.",
    "technical-analyst":
        "You are a Technical Analyst. Read trend, momentum, support/resistance "
        "and volume for entry/exit TIMING, not the core thesis. Tag horizon as "
        "intraday or swing honestly.",
    "sentiment-news-analyst":
        "You are a Sentiment & News Analyst. Detect narrative shifts, guidance "
        "changes and tone from news/filings/transcripts. Tech moves on forward "
        "guidance. Separate hype from signal.",
    "macro-sector-strategist":
        "You are a Macro & Sector Strategist. Tech is long-duration and "
        "rate-sensitive. Set a risk-on/risk-off posture from rates, liquidity, "
        "the semi cycle and AI-capex cycle.",
    "alternative-data-analyst":
        "You are an Alt-Data Analyst. Read app/web/hiring/patent/commit/"
        "supply-chain signals for an edge over consensus, especially where "
        "alt-data diverges from the fundamental view.",
}


def _system(slug: str) -> str:
    return (
        f"{PERSONAS[slug]}\n\n"
        "For EACH ticker you have a view on, output a signal with: agent "
        f"(='{slug}'), ticker, direction (long/short/neutral), conviction "
        "(0..1, calibrated), time_horizon (intraday/swing/core), a <=3 sentence "
        "rationale, and a concrete invalidation condition. Only include tickers "
        "with a real view."
    )


def _features_prompt(features: pd.DataFrame) -> str:
    lines = ["ticker, price, 1m_return, 3m_return, ann_vol, above_50dma"]
    for t, r in features.iterrows():
        lines.append(
            f"{t}, {r.price:.2f}, {r.ret_1m:+.1%}, {r.ret_3m:+.1%}, "
            f"{r.vol:.0%}, {r.above_sma}"
        )
    return "\n".join(lines)


def run_research_agent(slug: str, features: pd.DataFrame) -> list[Signal]:
    llm = get_llm()
    if llm is None:
        return _mock_signals(slug, features)
    try:
        structured = llm.with_structured_output(AgentSignals)
        msg = [
            ("system", _system(slug)),
            ("human",
             "Latest features for the tech universe:\n\n"
             + _features_prompt(features)
             + "\n\nEmit your signals now."),
        ]
        result: AgentSignals = structured.invoke(msg)
        for s in result.signals:
            s.agent = slug
        return result.signals
    except Exception as e:  # never let one agent crash the cycle
        print(f"[{slug}] LLM error ({e}); falling back to heuristic")
        return _mock_signals(slug, features)


# --- Deterministic heuristic agents (mock mode) ----------------------------
def _agent_bias(slug: str, ticker: str) -> float:
    """Stable per-(agent,ticker) tilt so agents disagree like a real pod."""
    h = hashlib.sha256(f"{slug}:{ticker}".encode()).hexdigest()
    return (int(h[:8], 16) / 0xFFFFFFFF) - 0.5  # [-0.5, 0.5]


def _mock_signals(slug: str, features: pd.DataFrame) -> list[Signal]:
    out: list[Signal] = []
    for t, r in features.iterrows():
        # Different agents weight the same evidence differently.
        if slug == "fundamental-analyst":
            score = 0.6 * r.ret_3m + 0.2 * _agent_bias(slug, t)
        elif slug == "quantitative-factor-analyst":
            score = 0.5 * r.ret_1m + 0.5 * r.ret_3m - 0.3 * (r.vol - 0.3)
        elif slug == "technical-analyst":
            score = (0.4 if r.above_sma else -0.4) + 0.5 * r.ret_1m
        elif slug == "sentiment-news-analyst":
            score = 0.4 * r.ret_1m + 0.6 * _agent_bias(slug, t)
        elif slug == "macro-sector-strategist":
            score = 0.3 * r.ret_3m - 0.4 * (r.vol - 0.3) + 0.2 * _agent_bias(slug, t)
        else:  # alt-data
            score = 0.5 * _agent_bias(slug, t) + 0.3 * r.ret_1m
        conv = max(0.0, min(1.0, abs(score) * 3))
        if conv < 0.1:
            continue
        horizon = "swing" if slug == "technical-analyst" else "core"
        direction = "long" if score > 0 else "short"
        out.append(Signal(
            agent=slug, ticker=t, direction=direction, conviction=round(conv, 2),
            time_horizon=horizon,
            rationale=f"{slug}: composite score {score:+.2f} from momentum/quality mix.",
            invalidation=f"Thesis void if {t} reverses its 3m trend or vol spikes >60%.",
        ))
    return out


# --- Red-Team (spec/red-team-devils-advocate.md) ---------------------------
def run_red_team(signals: list[Signal]) -> dict[str, str]:
    """Bear case for the highest-conviction consensus names. Returns ticker->dissent."""
    by_ticker: dict[str, float] = {}
    for s in signals:
        by_ticker[s.ticker] = by_ticker.get(s.ticker, 0.0) + s.signed()
    ranked = sorted(by_ticker.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    llm = get_llm()
    dissent: dict[str, str] = {}
    for ticker, net in ranked:
        side = "long" if net > 0 else "short"
        if llm is None:
            dissent[ticker] = (
                f"Bear case vs the {side} consensus on {ticker}: crowded positioning "
                f"and rate sensitivity could unwind the move; watch for guidance cuts."
            )
        else:
            try:
                msg = [
                    ("system",
                     "You are the Red-Team / Devil's Advocate. In 2 sentences, argue "
                     "the strongest case AGAINST the pod's consensus and state what "
                     "would have to be true for the thesis to be wrong."),
                    ("human", f"Consensus is {side} {ticker} (net {net:+.2f}). Refute it."),
                ]
                dissent[ticker] = llm.invoke(msg).content.strip()
            except Exception:
                dissent[ticker] = f"Bear case on {ticker}: consensus may be crowded."
    return dissent


# --- Portfolio Manager: aggregate -> consensus -> target weights -----------
def aggregate(signals: list[Signal], weights: dict[str, float],
              dissent: dict[str, str]) -> list[ConsensusView]:
    buckets: dict[str, list[Signal]] = {}
    for s in signals:
        buckets.setdefault(s.ticker, []).append(s)
    views: list[ConsensusView] = []
    for ticker, sigs in buckets.items():
        contributors: dict[str, float] = {}
        net_w = 0.0
        tot_w = 0.0
        for s in sigs:
            w = weights.get(s.agent, 1.0)
            contrib = w * s.signed()
            contributors[s.agent] = round(contrib, 3)
            net_w += contrib
            tot_w += w
        net = net_w / tot_w if tot_w else 0.0
        # Red-team haircut: a dissented name loses conviction.
        if ticker in dissent:
            net *= 0.7
        views.append(ConsensusView(
            ticker=ticker, net_direction=round(net, 3),
            conviction=round(abs(net), 3), contributors=contributors,
            dissent=dissent.get(ticker),
            invalidations=[s.invalidation for s in sigs][:3],
        ))
    return views


def target_weights(views: list[ConsensusView], current: dict[str, float],
                   action_threshold: float, max_step: float,
                   max_pos: float) -> list[ProposedTrade]:
    """Long-only target weights sized to conviction, capped and rate-limited."""
    desired: dict[str, float] = {}
    for v in views:
        if v.net_direction > action_threshold:      # long-only book
            desired[v.ticker] = min(max_pos, v.net_direction)
        else:
            desired[v.ticker] = 0.0
    # Normalize to <=100% gross.
    total = sum(desired.values())
    if total > 1.0:
        desired = {k: v / total for k, v in desired.items()}

    proposals: list[ProposedTrade] = []
    tickers = set(desired) | set(current)
    for t in sorted(tickers):
        cur = current.get(t, 0.0)
        tgt = desired.get(t, 0.0)
        # Rate-limit the move per cycle (conviction vs. turnover trade-off).
        step = max(-max_step, min(max_step, tgt - cur))
        new_target = cur + step
        if abs(new_target - cur) < 0.01:
            continue
        v = next((x for x in views if x.ticker == t), None)
        proposals.append(ProposedTrade(
            ticker=t, target_weight=round(new_target, 4),
            current_weight=round(cur, 4), delta_weight=round(new_target - cur, 4),
            rationale=(f"net {v.net_direction:+.2f}" if v else "reduce to target"),
            invalidation=(v.invalidations[0] if v and v.invalidations else ""),
        ))
    return proposals

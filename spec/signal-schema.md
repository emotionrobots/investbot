---
type: reference
name: Structured Signal Schema
version: 0.1
consumed_by: [portfolio-manager, cio-portfolio-orchestrator, risk-manager, decision-journal-memory, performance-attribution-analyst]
emitted_by: [fundamental-analyst, quantitative-factor-analyst, technical-analyst, sentiment-news-analyst, macro-sector-strategist, alternative-data-analyst, red-team-devils-advocate]
---

# Structured Signal Schema

The linchpin contract of the system. Every research/analyst agent emits a
**confidence-weighted signal object** — never a raw buy/sell recommendation.
This lets the orchestrator do principled aggregation (weighted-ensemble or
Bayesian blend) and lets the Performance Attribution agent trace P&L back to the
originating agent later.

## Signal object

```json
{
  "signal_id": "uuid",
  "agent": "fundamental-analyst",
  "ticker": "NVDA",
  "asset_class": "equity",
  "direction": "long",            // long | short | neutral | add | trim | hold | exit
  "conviction": 0.72,             // 0.0–1.0, calibrated (see below)
  "time_horizon": "core",         // intraday | swing | core  (see horizons)
  "target_return": 0.18,          // optional, expected return over horizon
  "rationale": "≤3 sentences, plain language, the 'why now'",
  "key_drivers": ["NRR 128%", "gross margin +240bps QoQ", "backlog +40% YoY"],
  "invalidation": "Thesis is wrong if NRR falls below 115% or gross margin compresses two consecutive quarters.",
  "data_asof": "2026-07-03T20:00:00Z",
  "data_quality": "high",         // high | medium | low
  "confidence_basis": "8 quarters of statements + 2 alt-data corroborations",
  "tags": ["semis", "ai-capex", "long-duration"]
}
```

## Field rules

- **conviction** — Must be *calibrated*, not a vibe. Agents should reserve
  >0.8 for cases where the invalidation condition is concrete and unlikely.
  The Decision Journal tracks realized outcomes vs. stated conviction to detect
  systematic over/under-confidence per agent.
- **direction** — Signal, not order. `long/short/neutral` for new theses;
  `add/trim/hold/exit` when commenting on an existing position.
- **time_horizon** — `intraday` (hours), `swing` (days–weeks),
  `core` (months–quarters). Horizon mismatch is a common aggregation error;
  the PM must not blend an intraday technical signal with a core fundamental
  one as if they were the same bet.
- **invalidation** — Required. A signal with no falsification condition is
  rejected by the PM. This is what makes the Red-Team's job possible.
- **rationale** — Terse. The full analysis lives in the agent's working notes;
  the signal carries only the decision-relevant summary.

## Aggregation contract (for the PM / orchestrator)

Signals are combined per-ticker into a **consensus view** carrying: net
direction, ensemble conviction, contributing agents with weights, dissent
(the Red-Team seat), and the union of invalidation conditions. The consensus
view — not individual signals — is what enters the risk-and-compliance gate.

## Invariants

1. No research agent ever emits an *order*. It emits a signal.
2. Every signal is logged verbatim by the Decision Journal before aggregation.
3. Conviction and invalidation are mandatory; a signal missing either is invalid.

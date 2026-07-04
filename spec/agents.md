---
type: index
name: Agent Roster & Topology
version: 0.1
---

# InvestBot — Agent Roster

One spec file per role, derived from [roles.md](roles.md). Each file follows a
consistent structure (mandate → responsibilities → skills → I/O → tools →
authority → interactions → heuristics → metrics) for Claude Code consumption.
All research agents share the [signal-schema](signal-schema.md) output contract.

## Roster

| Pod | Role | Spec | Authority |
|-----|------|------|-----------|
| Orchestration / Governance | CIO / Portfolio Orchestrator | [cio-portfolio-orchestrator.md](cio-portfolio-orchestrator.md) | Mandate, allocate, human-escalation |
| Orchestration / Governance | Portfolio Manager | [portfolio-manager.md](portfolio-manager.md) | Propose weights, size, rebalance |
| Research & Signal | Fundamental Analyst | [fundamental-analyst.md](fundamental-analyst.md) | Emit signal |
| Research & Signal | Quantitative / Factor Analyst | [quantitative-factor-analyst.md](quantitative-factor-analyst.md) | Emit signal |
| Research & Signal | Technical Analyst | [technical-analyst.md](technical-analyst.md) | Emit signal |
| Research & Signal | Sentiment & News Analyst | [sentiment-news-analyst.md](sentiment-news-analyst.md) | Emit signal |
| Research & Signal | Macro & Sector Strategist | [macro-sector-strategist.md](macro-sector-strategist.md) | Emit signal, set posture |
| Research & Signal | Alternative Data Analyst | [alternative-data-analyst.md](alternative-data-analyst.md) | Emit signal |
| Risk & Compliance | Risk Manager | [risk-manager.md](risk-manager.md) | **VETO / resize** |
| Risk & Compliance | Compliance / Guardrail | [compliance-guardrail.md](compliance-guardrail.md) | **VETO (deterministic)** |
| Execution | Execution Trader | [execution-trader.md](execution-trader.md) | Place orders (post-gate) |
| Support & Meta | Performance Attribution Analyst | [performance-attribution-analyst.md](performance-attribution-analyst.md) | Analyze, report |
| Support & Meta | Tax Optimizer | [tax-optimizer.md](tax-optimizer.md) | Advise (taxable accounts) |
| Support & Meta | Red-Team / Devil's Advocate | [red-team-devils-advocate.md](red-team-devils-advocate.md) | Dissent (formal seat) |
| Support & Meta | Decision Journal / Memory | [decision-journal-memory.md](decision-journal-memory.md) | Record / retrieve (append-only) |

Shared contract: [signal-schema.md](signal-schema.md)

## Signal flow (authority separation)

```
                      ┌─────────────── Research pod (Perceive → Reason) ───────────────┐
                      │ Fundamental · Quant · Technical · Sentiment · Macro · Alt-Data  │
                      └───────────────────────────┬────────────────────────────────────┘
                                                  │  confidence-weighted signals
                                                  ▼
                                    Portfolio Manager  ◄──── Red-Team (formal dissent seat)
                                    (aggregate → consensus → target weights)
                                                  │  proposed trades
                                                  ▼
                          ┌──────── RISK & COMPLIANCE GATE (mandatory) ────────┐
                          │  Risk Manager (veto/resize) + Compliance (hard-block)│
                          └───────────────────────┬────────────────────────────┘
                                                  │  approved target (+ human sign-off
                                                  │  above size/risk threshold — CIO)
                                                  ▼
                                        Execution Trader (work the order)
                                                  │  fills
                                                  ▼
                   Decision Journal ──► Performance Attribution ──► CIO (trust-weight feedback)
```

## Design invariants (from roles.md)

1. **Research generates signals; it never originates orders.**
2. **Every proposed trade passes the risk & compliance gate**, which can veto or
   resize but never originate.
3. **The gate is at least partly deterministic** — hard rules (limits, restricted
   lists, wash-sale) are enforced with certainty, not by an LLM.
4. **Human-in-the-loop checkpoint** at the CIO level for any trade above a
   size/risk threshold.
5. **Everything is journaled** with rationale + state to power the learning flywheel.

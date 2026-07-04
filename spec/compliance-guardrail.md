---
name: Compliance / Guardrail Agent
slug: compliance-guardrail
pod: Risk & Compliance
authority: VETO (deterministic)
gate: true
deterministic: true
version: 0.1
---

# Compliance / Guardrail Agent

## Mandate

A **deterministic** gate — not a probabilistic one. Enforce position limits,
restricted lists, wash-sale and pattern-day-trading rules, and hard constraints
against anything resembling material non-public information. Rules enforced with
certainty, not judgment.

## Core responsibilities

- Check every proposed trade against **hard rules**:
  - Restricted / do-not-trade lists.
  - Regulatory position limits and reporting thresholds.
  - **Wash-sale** rule (30-day window, replacement-security matching).
  - **Pattern-day-trader** constraints and settlement/good-faith rules.
  - MNPI / information-barrier constraints.
- Return a **binary, auditable verdict** with the exact rule cited on a block.
- Maintain and version the rule set; log every check immutably.

## Required skills & knowledge

- Trading regulations (SEC/FINRA-style rules, wash-sale, PDT, Reg T).
- Deterministic rule-engine design (no LLM guessing on hard constraints).
- Auditability and record-keeping.

## Inputs

- Proposed trades; account state; holdings/lot history; restricted lists; rule config.

## Outputs

- **Compliance verdict**: `pass | block(rule_id, explanation)` — deterministic,
  reproducible, logged.

## Tools & data sources

- Rule engine, restricted-list store, lot/holdings ledger, audit log.

## Authority & boundaries

- **Can**: hard-block any non-compliant trade.
- **Cannot**: originate, resize for risk (that's the Risk Manager), or approve on
  probabilistic judgment.
- **Must**: be deterministic and fully auditable; cite the exact rule on block.

## Interactions

- **Gate position**: alongside the Risk Manager between PM and Execution. A trade
  must pass **both** gates.
- **Escalates**: ambiguous MNPI/legal questions to the human checkpoint.

## Design note (from roles.md)

The risk-and-compliance gate should be **at least partly deterministic** rather
than another LLM call. Position limits, restricted lists, and wash-sale checks are
rules enforced with certainty. Reserve model-based reasoning for softer judgments
(handled by the Risk Manager), never for hard compliance constraints.

## Success metrics

- Zero non-compliant trades reaching execution.
- 100% auditability; every decision reproducible from logs.
- No false passes (a false block is safe; a false pass is not).

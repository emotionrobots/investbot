# InvestBot — User Guide

A continuously-running, multi-agent paper-trading system built on **LangGraph**
and **Claude**. It implements the roster and topology in [`spec/`](spec/):
a research pod emits confidence-weighted signals, a Red-Team argues the bear
case, a Portfolio Manager sizes positions, a **deterministic risk + compliance
gate** can veto or resize (but never originates), and an execution layer trades
with **fake capital** at **real market prices**. Performance is measured against
a **real buy-and-hold benchmark**, and per-agent **trust weights adapt** from
realized results to push ROI up over time.

> ⚠️ This is a **simulation and an architecture demo**, not investment advice.
> It trades fake money. Do not point it at a real brokerage.

---

## 1. What it does each cycle

```
ingest market data (yfinance)
        │
        ▼
┌─────────────── research pod (LangGraph fan-out, runs in parallel) ───────────────┐
│ fundamental · quant/factor · technical · sentiment · macro · alt-data            │
└───────────────────────────────┬──────────────────────────────────────────────────┘
                                │  confidence-weighted signals
                                ▼
                        Red-Team (bear case, conviction haircut)
                                ▼
                     Portfolio Manager  (aggregate → target weights,
                                         sized by per-agent trust weights)
                                ▼
        RISK GATE (veto/resize: caps, cash floor)  →  COMPLIANCE GATE (restricted list,
                                                        wash-sale window)  [deterministic]
                                ▼
                        Execution (paper broker, fills at real prices)
                                ▼
        Attribution + Learning (update trust weights) → mark NAV vs benchmark → journal
```

Every step is logged to an append-only **decision journal** in SQLite.

---

## 2. Install

Requires Python 3.9+.

```bash
cd investbot
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure

```bash
cp .env.example .env
```

Key settings (all optional — sensible defaults):

| Variable | Meaning | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Enables **real Claude agents**. Unset → mock mode. | *(unset)* |
| `INVESTBOT_MOCK` | Force heuristic agents even with a key (free back-runs). | `0` |
| `INVESTBOT_MODEL` | Agent model. `claude-opus-4-8` (best) or `claude-sonnet-5` (cheaper). | `claude-opus-4-8` |
| `INVESTBOT_CAPITAL` | Fake starting capital. | `100000` |
| `INVESTBOT_UNIVERSE` | Comma-separated tickers. | 10 mega-cap tech names |
| `INVESTBOT_BENCHMARK` | The "real portfolio" comparison (buy-and-hold). | `QQQ` |
| `INVESTBOT_INTERVAL_MIN` | Minutes between cycles in continuous mode. | `60` |

**Modes:**
- **Mock mode** (no key, or `INVESTBOT_MOCK=1`): agents are deterministic
  heuristics over real price features. Zero API cost — ideal for testing and
  long simulations.
- **Live mode** (key set): each research analyst is a Claude agent with a persona
  from `spec/`, emitting structured signals. If any single agent errors, it
  falls back to its heuristic so the cycle never crashes.

---

## 4. Run it

### One-shot / fast-forward (great first run)

```bash
python run_cycle.py            # a single trading cycle
python run_cycle.py -n 20 -r   # 20 cycles, then write a daily report
```

### Continuous (the real thing)

```bash
python run_engine.py             # cycle every INVESTBOT_INTERVAL_MIN
python run_engine.py --interval 5   # cycle every 5 minutes
```

It trades on each tick, marks NAV vs. the benchmark, and writes a fresh daily
report (tables + charts) once per calendar day. Ctrl-C to stop; state persists
in `investbot.db`, so you can stop and resume anytime.

### Dashboard + chatbox

In a second terminal (same venv):

```bash
streamlit run dashboard.py
```

Opens a browser dashboard with:
- **Performance** — bot vs. benchmark cumulative return + alpha charts
- **Positions**, **Trades**, **Agents** (live trust weights) tables
- **💬 Chat** — ask questions in natural language, e.g.
  *"How are we doing vs the benchmark?"*, *"What do we hold and why?"*,
  *"Which agent has earned the most trust?"*
- Sidebar buttons to **run a cycle** or **fast-forward N cycles** on demand.

Run the dashboard and the engine together (they share `investbot.db`), or just
use the dashboard's "Run cycle" buttons.

---

## 5. Reading performance

Reports land in `reports/`:
- `report-YYYY-MM-DD.md` — tables (performance, positions, trust weights)
- `dashboard.png` — 4-panel chart (NAV vs benchmark, alpha, positions, weights)

Key metrics:
- **Fake ROI** vs **Benchmark ROI** → the whole point: is the bot beating a
  passive real portfolio?
- **Alpha (pp)** — outperformance in percentage points of initial capital.
- **Sharpe**, **max drawdown** — risk-adjusted quality.

> Meaningful ROI/alpha curves accrue **across days** as real prices move. Running
> many cycles within the same minute (or same trading day) shows ~flat lines
> because prices haven't changed — that's expected. Let the engine run over
> multiple sessions, or run `run_cycle.py -n N` daily.

---

## 6. Continuous learning (the flywheel)

After each cycle, [`learning.py`](botcore/learning.py) grades the **previous**
cycle's consensus views against realized price moves and nudges each contributing
agent's **trust weight** (EMA, bounded `0.3–2.5`). Agents whose signals precede
profitable moves gain sizing influence; the PM weights their signals more next
time. Watch the **Agents** tab / the trust-weight chart evolve as the sim runs.

---

## 7. Project layout

```
investbot/
├── spec/                     # role & skill specifications (the design)
├── botcore/
│   ├── config.py             # env-driven settings + risk limits
│   ├── schemas.py            # Signal / ConsensusView / ProposedTrade / GateVerdict
│   ├── market_data.py        # yfinance prices + features (offline fallback)
│   ├── llm.py                # Claude factory (langchain-anthropic)
│   ├── agents.py             # research pod + Red-Team + PM aggregation
│   ├── gates.py              # deterministic risk + compliance gate
│   ├── broker.py             # paper broker, NAV, benchmark
│   ├── learning.py           # trust-weight updates
│   ├── graph.py              # LangGraph wiring of the whole topology
│   ├── reporting.py          # tables + matplotlib charts + daily report
│   ├── engine.py             # continuous scheduler (CIO loop)
│   ├── chat.py               # chatbox backend (Claude, grounded in the DB)
│   └── db.py                 # SQLite decision journal + portfolio state
├── run_cycle.py              # run N cycles (CLI)
├── run_engine.py             # run forever (CLI)
├── dashboard.py              # Streamlit dashboard + chat
└── reports/                  # generated md + png
```

---

## 8. Extending

- **Add a real signal source**: give a research agent a tool (news API, alt-data
  feed) and richer context in `agents.py`.
- **Tighten the gate**: `config.py` holds the limits; `gates.py` is fully
  deterministic by design (see `spec/compliance-guardrail.md`).
- **Swap the benchmark**: set `INVESTBOT_BENCHMARK` to any ticker, or change
  `broker.benchmark_value()` to an equal-weight basket of your universe.
- **Reset the sim**: delete `investbot.db` (and `reports/`).

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| Flat performance lines | Run more cycles across different days; prices must move. |
| `yfinance` errors / offline | Falls back to a synthetic random walk automatically. |
| Want zero API cost | `INVESTBOT_MOCK=1` (or just leave `ANTHROPIC_API_KEY` unset). |
| Rate limits / cost in live mode | Use `INVESTBOT_MODEL=claude-sonnet-5` and a larger `INVESTBOT_INTERVAL_MIN`. |
| Start over | `rm investbot.db && rm -rf reports/` |

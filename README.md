# investbot

A continuously-running, **multi-agent paper-trading system** built on
[LangGraph](https://langchain-ai.github.io/langgraph/) and Claude. A research pod
emits confidence-weighted signals, a Red-Team argues the bear case, a Portfolio
Manager sizes positions, and a **deterministic risk + compliance gate** vets every
trade before an execution layer trades **fake capital** at **real prices** —
measured against a real buy-and-hold benchmark, with per-agent **trust weights
that learn** from realized results.

- **Design / roster:** [`spec/`](spec/) (one file per agent role) + [`spec/agents.md`](spec/agents.md)
- **How to run:** [`USER_GUIDE.md`](USER_GUIDE.md)
- **Implementation:** [`botcore/`](botcore/)

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python run_cycle.py -n 20 -r      # 20 trading cycles + a daily report (no API key needed)
streamlit run dashboard.py        # dashboard: charts, tables, and a chatbox
python run_engine.py --interval 5 # run continuously
```

Runs free out-of-the-box in **mock mode** (deterministic heuristic agents over
real prices). Set `ANTHROPIC_API_KEY` to run the agents as real Claude models.
See [`USER_GUIDE.md`](USER_GUIDE.md) for everything.

> ⚠️ Simulation only — fake capital, not investment advice.

#!/usr/bin/env python3
"""Streamlit dashboard: daily performance (tables + charts) and a chatbox.

    streamlit run dashboard.py

Reads the same SQLite DB the engine writes to, so run the engine (or run_cycle)
alongside it. A "Run cycle now" button lets you trade on demand."""
import streamlit as st

from botcore import chat, db, engine, reporting
from botcore.config import CONFIG

st.set_page_config(page_title="InvestBot", page_icon="📈", layout="wide")
db.init_db()

st.title("📈 InvestBot — multi-agent paper trading")
st.caption(f"Trading **{len(CONFIG.universe)}** tech names with fake capital "
           f"vs. **{CONFIG.benchmark}** (real buy-and-hold). "
           f"Mode: {'🧪 mock (no API)' if CONFIG.mock else '🤖 Claude ' + CONFIG.model}")

with st.sidebar:
    st.header("Controls")
    if st.button("▶️ Run trading cycle now", use_container_width=True):
        with st.spinner("Running perceive → reason → gate → execute → learn…"):
            engine.one_cycle(verbose=False)
        st.success("Cycle complete.")
    n = st.number_input("Fast-forward cycles", 1, 100, 5)
    if st.button("⏩ Run N cycles", use_container_width=True):
        prog = st.progress(0.0)
        for i in range(int(n)):
            engine.one_cycle(verbose=False)
            prog.progress((i + 1) / n)
        st.success(f"Ran {int(n)} cycles.")
    st.divider()
    st.caption("Refresh the page to update tables/charts after a cycle.")

summary = reporting.performance_summary()
c1, c2, c3, c4 = st.columns(4)
c1.metric("Fake NAV", f"${summary['fake_nav']:,.0f}", f"{summary['fake_roi']:+.2f}%")
c2.metric(f"Benchmark {CONFIG.benchmark}", f"${summary['benchmark_nav']:,.0f}",
          f"{summary['benchmark_roi']:+.2f}%")
c3.metric("Alpha", f"{summary['alpha']:+.2f} pp")
c4.metric("Sharpe (ann.)", summary.get("sharpe_annualized", "n/a"),
          f"maxDD {summary.get('max_drawdown_pct', 'n/a')}%")

tab_perf, tab_pos, tab_agents, tab_trades, tab_chat = st.tabs(
    ["📊 Performance", "💼 Positions", "🧠 Agents", "🧾 Trades", "💬 Chat"])

with tab_perf:
    df = reporting.nav_frame()
    if df.empty:
        st.info("No history yet — run a cycle from the sidebar.")
    else:
        init = db.initial_capital()
        idx = df.set_index("ts")[["fake_nav", "benchmark_nav"]] / init * 100
        idx.columns = ["InvestBot", f"{CONFIG.benchmark} (buy&hold)"]
        st.line_chart(idx, height=320)
        st.caption("Indexed to 100 at inception. InvestBot = fake capital; benchmark = real portfolio.")
        alpha = ((df.set_index("ts")["fake_nav"] - df.set_index("ts")["benchmark_nav"])
                 / init * 100)
        st.area_chart(alpha.rename("alpha (pp)"), height=200)

with tab_pos:
    pos = reporting.positions_table()
    st.dataframe(pos, use_container_width=True) if not pos.empty else st.info("Book is flat.")

with tab_agents:
    st.caption("Trust weights adapt from realized results — the learning flywheel.")
    w = reporting.agent_weights_table()
    st.bar_chart(w.set_index("agent"), height=300)
    st.dataframe(w, use_container_width=True)

with tab_trades:
    tr = reporting.trades_frame(200)
    st.dataframe(tr, use_container_width=True) if not tr.empty else st.info("No trades yet.")

with tab_chat:
    st.caption("Ask about performance, positions, trades, or why an agent is weighted as it is.")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    for m in st.session_state.chat_history:
        st.chat_message(m["role"]).write(m["content"])
    if prompt := st.chat_input("e.g. How are we doing vs the benchmark?"):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        st.chat_message("user").write(prompt)
        with st.spinner("Thinking…"):
            reply = chat.answer(prompt, st.session_state.chat_history)
        st.session_state.chat_history.append({"role": "assistant", "content": reply})
        st.chat_message("assistant").write(reply)

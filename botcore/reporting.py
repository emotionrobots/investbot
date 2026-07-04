"""Daily performance reporting: tables + charts (spec/performance-attribution)."""
from __future__ import annotations

import datetime as dt
import os

import numpy as np
import pandas as pd

from . import broker, db
from .config import CONFIG
from .market_data import latest_prices


def nav_frame() -> pd.DataFrame:
    with db.connect() as con:
        df = pd.read_sql_query("SELECT * FROM nav ORDER BY ts", con)
    if not df.empty:
        df["ts"] = pd.to_datetime(df["ts"])
    return df


def trades_frame(limit: int = 200) -> pd.DataFrame:
    with db.connect() as con:
        return pd.read_sql_query(
            "SELECT * FROM trades ORDER BY ts DESC LIMIT ?", con, params=(limit,))


def positions_table() -> pd.DataFrame:
    prices = latest_prices(CONFIG.universe)
    pos = db.get_positions()
    nav = broker.portfolio_value(prices) or 1.0
    rows = []
    for t, p in pos.items():
        px = prices.get(t, p["avg_cost"])
        mv = p["shares"] * px
        rows.append(dict(
            ticker=t, shares=round(p["shares"], 2), avg_cost=round(p["avg_cost"], 2),
            price=round(px, 2), market_value=round(mv, 2),
            weight_pct=round(mv / nav * 100, 2),
            unrealized_pct=round((px / p["avg_cost"] - 1) * 100, 2) if p["avg_cost"] else 0.0,
        ))
    df = pd.DataFrame(rows)
    return df.sort_values("market_value", ascending=False) if not df.empty else df


def performance_summary() -> dict:
    snap = broker.mark_to_market()
    df = nav_frame()
    metrics = dict(snap)
    if len(df) > 2:
        rets = df["fake_nav"].pct_change().dropna()
        if rets.std() > 0:
            metrics["sharpe_annualized"] = round(
                float(rets.mean() / rets.std() * np.sqrt(252)), 2)
        peak = df["fake_nav"].cummax()
        dd = (df["fake_nav"] - peak) / peak
        metrics["max_drawdown_pct"] = round(float(dd.min()) * 100, 2)
    metrics["positions"] = len(db.get_positions())
    metrics["trades_total"] = int(trades_frame(100000).shape[0])
    return metrics


def agent_weights_table() -> pd.DataFrame:
    w = db.get_weights()
    return pd.DataFrame(sorted(w.items(), key=lambda kv: -kv[1]),
                        columns=["agent", "trust_weight"])


# --- charts ----------------------------------------------------------------
def _fig_nav(ax, df: pd.DataFrame):
    if df.empty:
        ax.text(0.5, 0.5, "no NAV history yet", ha="center"); return
    init = db.initial_capital()
    ax.plot(df["ts"], df["fake_nav"] / init * 100, label="InvestBot (fake capital)", lw=2)
    ax.plot(df["ts"], df["benchmark_nav"] / init * 100,
            label=f"Benchmark {CONFIG.benchmark} (buy & hold)", lw=2, ls="--")
    ax.axhline(100, color="gray", lw=0.8, alpha=0.5)
    ax.set_title("Cumulative return — bot vs. real portfolio"); ax.set_ylabel("Indexed = 100")
    ax.legend(); ax.grid(alpha=0.3)


def _fig_alpha(ax, df: pd.DataFrame):
    if df.empty:
        ax.text(0.5, 0.5, "no data", ha="center"); return
    init = db.initial_capital()
    alpha = (df["fake_nav"] - df["benchmark_nav"]) / init * 100
    ax.fill_between(df["ts"], alpha, 0, where=alpha >= 0, color="green", alpha=0.4)
    ax.fill_between(df["ts"], alpha, 0, where=alpha < 0, color="red", alpha=0.4)
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title("Alpha vs benchmark (pp of initial capital)"); ax.grid(alpha=0.3)


def _fig_positions(ax, pos: pd.DataFrame):
    if pos.empty:
        ax.text(0.5, 0.5, "no open positions", ha="center"); return
    ax.barh(pos["ticker"], pos["weight_pct"], color="steelblue")
    ax.invert_yaxis(); ax.set_title("Current positions (% of NAV)"); ax.grid(alpha=0.3, axis="x")


def _fig_weights(ax, w: pd.DataFrame):
    if w.empty:
        ax.text(0.5, 0.5, "no weights", ha="center"); return
    ax.barh(w["agent"].str.replace("-", "\n"), w["trust_weight"], color="darkorange")
    ax.invert_yaxis(); ax.axvline(1.0, color="gray", ls="--", lw=0.8)
    ax.set_title("Agent trust weights (learning)"); ax.grid(alpha=0.3, axis="x")


def render_charts(path: str | None = None) -> str:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    os.makedirs(CONFIG.reports_dir, exist_ok=True)
    path = path or os.path.join(CONFIG.reports_dir, "dashboard.png")
    df, pos, w = nav_frame(), positions_table(), agent_weights_table()
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    _fig_nav(axes[0, 0], df)
    _fig_alpha(axes[0, 1], df)
    _fig_positions(axes[1, 0], pos)
    _fig_weights(axes[1, 1], w)
    fig.suptitle(f"InvestBot daily performance — {dt.date.today()}", fontsize=14)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path


def generate_daily_report() -> dict:
    """Write a markdown report + PNG dashboard; return the summary + paths."""
    os.makedirs(CONFIG.reports_dir, exist_ok=True)
    summary = performance_summary()
    png = render_charts()
    pos = positions_table()
    md_path = os.path.join(CONFIG.reports_dir, f"report-{dt.date.today()}.md")
    lines = [
        f"# InvestBot Daily Report — {dt.date.today()}", "",
        "## Performance (fake capital vs. real portfolio benchmark)", "",
        f"- Fake NAV: **${summary['fake_nav']:,.2f}**  (ROI **{summary['fake_roi']:+.2f}%**)",
        f"- Benchmark {CONFIG.benchmark} NAV: ${summary['benchmark_nav']:,.2f}  "
        f"(ROI {summary['benchmark_roi']:+.2f}%)",
        f"- **Alpha: {summary['alpha']:+.2f} pp**",
        f"- Sharpe (ann.): {summary.get('sharpe_annualized', 'n/a')}  |  "
        f"Max drawdown: {summary.get('max_drawdown_pct', 'n/a')}%",
        f"- Cash: ${summary['cash']:,.2f}  |  Open positions: {summary['positions']}  |  "
        f"Trades to date: {summary['trades_total']}", "",
        "## Positions", "",
        pos.to_markdown(index=False) if not pos.empty else "_flat_", "",
        "## Agent trust weights", "",
        agent_weights_table().to_markdown(index=False), "",
        f"![dashboard]({os.path.basename(png)})", "",
    ]
    with open(md_path, "w") as f:
        f.write("\n".join(lines))
    summary["report_md"] = md_path
    summary["report_png"] = png
    return summary

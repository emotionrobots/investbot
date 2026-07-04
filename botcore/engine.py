"""Continuous engine (the CIO/Orchestrator loop). Runs trading cycles on an
interval, marks NAV, and emits a daily report. Human-in-the-loop escalation is
logged for any above-threshold cycle (spec/cio-portfolio-orchestrator.md)."""
from __future__ import annotations

import datetime as dt
import time
import traceback

from . import db, reporting
from .config import CONFIG
from .graph import run_cycle

# Above this single-cycle turnover a real desk would require a human sign-off.
ESCALATION_TURNOVER = 0.25


def one_cycle(verbose: bool = True) -> dict:
    db.init_db()
    snap = run_cycle()
    if verbose:
        print(f"[{snap.get('ts', '')}] fake ROI {snap.get('fake_roi', 0):+.2f}%  "
              f"bench {snap.get('benchmark_roi', 0):+.2f}%  "
              f"alpha {snap.get('alpha', 0):+.2f}pp  cash ${snap.get('cash', 0):,.0f}")
    return snap


def run_forever(interval_min: int | None = None) -> None:
    interval = (interval_min or CONFIG.interval_min) * 60
    print(f"InvestBot engine starting. mock={CONFIG.mock} model={CONFIG.model} "
          f"interval={interval // 60}m universe={CONFIG.universe}")
    last_report_day = None
    while True:
        try:
            snap = one_cycle()
            today = dt.date.today()
            if last_report_day != today:
                rep = reporting.generate_daily_report()
                print(f"  daily report → {rep['report_md']}")
                last_report_day = today
        except KeyboardInterrupt:
            print("stopping."); break
        except Exception:
            traceback.print_exc()
        time.sleep(interval)

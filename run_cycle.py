#!/usr/bin/env python3
"""Run one or more trading cycles, then print a report. Good for testing and
for fast-forwarding the simulation.

    python run_cycle.py            # one cycle
    python run_cycle.py -n 20      # twenty cycles
    python run_cycle.py -n 5 -r    # five cycles + daily report (tables/charts)
"""
import argparse

from botcore import db, engine, reporting


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--cycles", type=int, default=1)
    ap.add_argument("-r", "--report", action="store_true", help="write daily report")
    args = ap.parse_args()

    db.init_db()
    for i in range(args.cycles):
        engine.one_cycle()
    if args.report or args.cycles > 1:
        rep = reporting.generate_daily_report()
        print(f"\nReport written: {rep['report_md']}")
        print(f"Dashboard PNG:  {rep['report_png']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run the InvestBot engine continuously (trading cycles on an interval + a
daily report). Ctrl-C to stop.

    python run_engine.py                 # uses INVESTBOT_INTERVAL_MIN (default 60)
    python run_engine.py --interval 5    # a cycle every 5 minutes
"""
import argparse

from botcore import db, engine


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=None, help="minutes between cycles")
    args = ap.parse_args()
    db.init_db()
    engine.run_forever(interval_min=args.interval)


if __name__ == "__main__":
    main()

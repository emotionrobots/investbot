"""Central configuration, loaded from environment / .env."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv optional
    pass

ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    model: str = os.getenv("INVESTBOT_MODEL", "claude-opus-4-8")
    capital: float = float(os.getenv("INVESTBOT_CAPITAL", "100000"))
    benchmark: str = os.getenv("INVESTBOT_BENCHMARK", "QQQ")
    interval_min: int = int(os.getenv("INVESTBOT_INTERVAL_MIN", "60"))
    db_path: str = str(ROOT / os.getenv("INVESTBOT_DB", "investbot.db"))
    reports_dir: str = str(ROOT / os.getenv("INVESTBOT_REPORTS", "reports"))
    universe: list[str] = field(
        default_factory=lambda: [
            t.strip().upper()
            for t in os.getenv(
                "INVESTBOT_UNIVERSE",
                "AAPL,MSFT,NVDA,GOOGL,AMZN,META,AVGO,TSLA,AMD,CRM",
            ).split(",")
            if t.strip()
        ]
    )

    # Risk & compliance limits (deterministic gate — see spec/risk-manager.md,
    # spec/compliance-guardrail.md)
    max_position_weight: float = 0.20      # single-name cap
    max_sector_weight: float = 1.00        # all tech here; kept for completeness
    max_gross_exposure: float = 1.00       # no leverage
    min_cash_weight: float = 0.02
    action_threshold: float = 0.15         # min |conviction*direction| to trade
    max_trade_weight_step: float = 0.10    # cap per-cycle move per name
    restricted: tuple[str, ...] = ()       # do-not-trade list

    @property
    def mock(self) -> bool:
        """Heuristic agents when forced, or when no API key is available."""
        if _bool("INVESTBOT_MOCK", False):
            return True
        return not os.getenv("ANTHROPIC_API_KEY")


CONFIG = Config()

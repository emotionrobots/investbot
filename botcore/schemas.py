"""Typed contracts. The Signal object is the linchpin (see spec/signal-schema.md)."""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Direction = Literal["long", "short", "neutral", "add", "trim", "hold", "exit"]
Horizon = Literal["intraday", "swing", "core"]


class Signal(BaseModel):
    """A single confidence-weighted signal emitted by a research agent."""

    agent: str = Field(description="slug of the emitting agent")
    ticker: str
    direction: Direction
    conviction: float = Field(ge=0.0, le=1.0, description="calibrated 0..1")
    time_horizon: Horizon = "core"
    rationale: str = Field(description="<= 3 sentences, the 'why now'")
    invalidation: str = Field(description="what would falsify the thesis (required)")

    def signed(self) -> float:
        """Net directional strength in [-1, 1]."""
        sign = {"long": 1, "add": 1, "short": -1, "exit": -1, "trim": -0.5}.get(
            self.direction, 0.0
        )
        return sign * self.conviction


class AgentSignals(BaseModel):
    """Structured-output container: one call returns many signals."""

    signals: list[Signal]


class ConsensusView(BaseModel):
    ticker: str
    net_direction: float          # ensemble signed conviction in [-1, 1]
    conviction: float             # magnitude 0..1
    contributors: dict[str, float]  # agent -> weighted contribution
    dissent: Optional[str] = None   # red-team bear case
    invalidations: list[str] = Field(default_factory=list)


class ProposedTrade(BaseModel):
    ticker: str
    target_weight: float
    current_weight: float
    delta_weight: float
    rationale: str
    invalidation: str = ""


class GateVerdict(BaseModel):
    ticker: str
    decision: Literal["approve", "resize", "veto"]
    approved_weight: float
    reason: str
    gate: Literal["risk", "compliance"]

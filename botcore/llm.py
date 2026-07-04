"""LLM factory. Uses Claude via langchain-anthropic when a key is present,
otherwise callers fall back to heuristic agents (see config.mock)."""
from __future__ import annotations

from functools import lru_cache

from .config import CONFIG


@lru_cache(maxsize=1)
def get_llm():
    """Return a ChatAnthropic instance, or None in mock mode."""
    if CONFIG.mock:
        return None
    from langchain_anthropic import ChatAnthropic

    # Opus 4.8: adaptive thinking only; structured output uses tool calling.
    return ChatAnthropic(model=CONFIG.model, max_tokens=4096, timeout=120)

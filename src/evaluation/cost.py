"""Cost of the model calls: tokens counted around a client, priced with the OpenAI price list.

`TokenMeter` wraps a datapizza client (its `invoke` and `structured_response`), so every call is
counted: the agent's steps, the rewrite of the output guardrail, the judges. `estimate_cost`
turns the counts into USD with `PRICES`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

# USD per 1M tokens (input, output), OpenAI price list: update it if prices change.
PRICES = {
    "gpt-4o-mini": {"in": 0.15, "out": 0.60},
    "gpt-4.1-mini": {"in": 0.40, "out": 1.60},
    "gpt-4.1": {"in": 2.00, "out": 8.00},
    "gpt-4o": {"in": 2.50, "out": 10.00},
    "text-embedding-3-small": {"in": 0.02, "out": 0.0},
}


def estimate_cost(prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o-mini") -> float:
    """Cost in USD of some calls, from their tokens and PRICES (0.0 for a model not in the list)."""
    p = PRICES.get(model)
    return (prompt_tokens * p["in"] + completion_tokens * p["out"]) / 1_000_000 if p else 0.0


class TokenMeter:
    """Counts the tokens of every call made through `client`; `take()` returns the counts and
    starts again from zero."""

    def __init__(self, client: Any) -> None:
        self.prompt = self.completion = 0
        for name in ("invoke", "structured_response"):
            original = getattr(client, name)

            def counted(*args: Any, _original: Callable = original, **kwargs: Any) -> Any:
                response = _original(*args, **kwargs)
                self.prompt += response.prompt_tokens_used or 0
                self.completion += response.completion_tokens_used or 0
                return response

            setattr(client, name, counted)

    def take(self) -> tuple[int, int]:
        counts = (self.prompt, self.completion)
        self.prompt = self.completion = 0
        return counts

"""Backend of the Streamlit app: one conversation with the agent, and one answer with the numbers
the app shows next to it (latency, tokens, cost, searches, guardrails).

Kept out of app.py so it can be tested offline: the app only renders what `Conversation.ask()`
returns. `make_client()` returns None in the app (MatchAnalyst then builds the OpenAI client);
tests replace it with a fake model.
"""

from __future__ import annotations

import time
from typing import Any

from src.agent.analyst_agent import MatchAnalyst, build_retriever
from src.core.config import load_settings
from src.evaluation.cost import TokenMeter, estimate_cost
from src.observability.tracing import flush, setup_tracing
from src.rag.retrieval import Retriever

MODELS = ("gpt-4o-mini", "gpt-4.1-mini")

__all__ = ["MODELS", "Conversation", "build_retriever", "make_client", "phoenix_url", "start_tracing"]


def make_client(model: str) -> Any | None:
    """The chat client for `model`; None lets MatchAnalyst build the OpenAI one."""
    return None


def start_tracing() -> str:
    """Connect to Phoenix if it is running; returns the status line to show."""
    settings = load_settings()
    return setup_tracing(settings.phoenix_endpoint, settings.phoenix_project)


def phoenix_url() -> str:
    return load_settings().phoenix_endpoint.split("/v1/")[0]


class Conversation:
    """One chat: the agent with its memory (follow-up questions work) and the token meter of its client."""

    def __init__(self, model: str, guardrails: bool, retriever: Retriever) -> None:
        self.model = model
        self.guardrails = guardrails
        self.analyst = MatchAnalyst(client=make_client(model), retriever=retriever, model=model,
                                    guardrails=guardrails, stateless=False)
        self.meter = TokenMeter(self.analyst.client)

    def ask(self, question: str) -> dict[str, Any]:
        """The assistant message for `question`: answer, consulted cards, searches, guardrails, meta."""
        t0 = time.perf_counter()
        answer = self.analyst.analyze(question)
        latency = time.perf_counter() - t0
        prompt, completion = self.meter.take()
        flush()   # the trace reaches Phoenix now, not at the next batch
        return {
            "role": "assistant",
            "content": answer,
            "consulted": list(self.analyst.consulted_cards),
            "calls": [dict(c) for c in self.analyst.corpus_tools.calls],
            "guard": dict(self.analyst.last_guard),
            "guard_note": self.analyst.guard_note,
            "meta": {"latency_s": latency, "prompt_tokens": prompt, "completion_tokens": completion,
                     "cost_usd": estimate_cost(prompt, completion, self.model), "model": self.model},
        }

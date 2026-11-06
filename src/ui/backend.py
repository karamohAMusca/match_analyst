"""Backend of the Streamlit app: one conversation with the agent, and one answer with the numbers
the app shows next to it (latency, tokens, cost, searches, guardrails). Every answer is also saved
to the chat's file in `chats/` (see `chat_log.py`).

Kept out of app.py so it can be tested offline: the app only renders what `Conversation.ask()`
returns. `make_client()` and `make_verifier()` return None in the app (MatchAnalyst then builds the
OpenAI clients); tests replace them with fakes. The cost of an answer includes the verifier's calls,
priced with the verifier's model.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from src.agent.analyst_agent import MatchAnalyst, build_retriever
from src.core.config import load_settings
from src.evaluation.cost import TokenMeter, estimate_cost
from src.observability.tracing import flush, setup_tracing
from src.rag.retrieval import Retriever
from src.ui.chat_log import ChatLog

logger = logging.getLogger(__name__)

MODELS = ("gpt-4o-mini", "gpt-4.1-mini")

__all__ = ["MODELS", "Conversation", "build_retriever", "make_client", "phoenix_url", "start_tracing"]


def make_client(model: str) -> Any | None:
    """The chat client for `model`; None lets MatchAnalyst build the OpenAI one."""
    return None


def make_verifier() -> Any | None:
    """The verifier's client; None lets MatchAnalyst build the default one (with the default client)."""
    return None


def start_tracing() -> str:
    """Connect to Phoenix if it is running; returns the status line to show."""
    settings = load_settings()
    status = setup_tracing(settings.phoenix_endpoint, settings.phoenix_project)
    logger.info(status)
    return status


def phoenix_url() -> str:
    return load_settings().phoenix_endpoint.split("/v1/")[0]


class Conversation:
    """One chat: the agent with its memory (follow-up questions work), the token meter of its client
    and the file the chat is saved to."""

    def __init__(self, model: str, guardrails: bool, retriever: Retriever, log: ChatLog | None = None) -> None:
        self.model = model
        self.guardrails = guardrails
        self.analyst = MatchAnalyst(client=make_client(model), retriever=retriever, model=model,
                                    guardrails=guardrails, stateless=False, verifier=make_verifier())
        self.meter = TokenMeter(self.analyst.client)
        verifier = self.analyst.verifier
        self.verifier_meter = TokenMeter(verifier) if verifier is not None else None
        self.log = log or ChatLog()
        logger.info("new conversation: %s, guardrails %s, saved to chats/%s",
                    model, "on" if guardrails else "off", self.log.path.name)

    def ask(self, question: str) -> dict[str, Any]:
        """The assistant message for `question`: answer, consulted cards, searches, guardrails, meta."""
        logger.info("question received (%d characters)", len(question))
        t0 = time.perf_counter()
        try:
            answer = self.analyst.analyze(question)
        except Exception:   # the app shows the short message; the log keeps the stack trace
            logger.exception("question failed after %.1f s", time.perf_counter() - t0)
            raise
        latency = time.perf_counter() - t0
        prompt, completion = self.meter.take()
        checked = self.verifier_meter.take() if self.verifier_meter else (0, 0)
        verifier_model = self.analyst.verifier_model
        cost = estimate_cost(prompt, completion, self.model) + estimate_cost(*checked, verifier_model or "")
        flush()   # the trace reaches Phoenix now, not at the next batch
        message = {
            "role": "assistant",
            "content": answer,
            "consulted": list(self.analyst.consulted_cards),
            "calls": [dict(c) for c in self.analyst.corpus_tools.calls],
            "guard": dict(self.analyst.last_guard),
            "guard_note": self.analyst.guard_note,
            "meta": {"latency_s": latency, "prompt_tokens": prompt, "completion_tokens": completion,
                     "cost_usd": cost, "model": self.model,
                     "verifier_model": verifier_model, "verifier_tokens": sum(checked),
                     "build": self.analyst.build},   # what the answer was made with (src/core/build_info.py)
        }
        logger.info("answer: %.1f s, %d+%d tokens, %.4f $, %d searches, cards %s",
                    latency, prompt, completion, message["meta"]["cost_usd"], len(message["calls"]),
                    message["consulted"])
        try:
            self.log.append(question, message, self.analyst.last_turns)
        except (OSError, TypeError, ValueError) as e:   # the answer is shown anyway, with the reason
            message["log_error"] = str(e)
            logger.warning("chat not saved to %s: %s", self.log.path.name, e)
        return message

"""The assistant coach agent (datapizza-ai `Agent` with the corpus tools), wrapped by the guardrails:

    question -> input guard -> agent (search, read, answer) -> output guard -> (one rewrite) -> answer

The input guard stops injection attempts, off-topic questions and oversized inputs before any
model call; the output guard checks language, grounding and citations and, on a problem, asks
the model for one rewrite. What the guards did is in `last_guard` and `guard_note`: a silent
guardrail is indistinguishable from a broken one.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient
from datapizza.core.clients.client import Client

from src.agent.prompts import MATCH_ANALYST_SYSTEM_PROMPT, REWRITE_REQUEST
from src.core.config import load_settings, require_openai_key
from src.guardrails.input_guard import check_question
from src.guardrails.output_guard import Issue, review_answer
from src.observability.tracing import set_output, span
from src.rag.embedding_cache import CachedEmbedder
from src.rag.retrieval import Retriever
from src.rag.store import make_embedder, make_vector_store
from src.tools.corpus_tools import CorpusTools, card_context

INPUT_NOTES = {
    "off_topic": "domanda fuori tema, fermata prima del modello",
    "injection": "tentativo di cambiare le istruzioni, fermato prima del modello",
    "too_long": "domanda troppo lunga, fermata prima del modello",
}
ISSUE_NOTES = {
    "language": "lingua della risposta",
    "ungrounded": "nomi o numeri non presenti nelle schede",
    "unknown_citation": "citazioni di schede non consultate",
    "no_citation": "nessuna scheda citata",
}


def build_retriever() -> Retriever:
    """Retriever on the Qdrant index, with cached query embeddings (the same text is paid once)."""
    settings = load_settings()
    embedder = CachedEmbedder(make_embedder(settings), settings.embedding_model)
    return Retriever(make_vector_store(settings), embedder, settings.qdrant_collection)


class MatchAnalyst:
    """Answers match-preparation and in-game questions from the card corpus, with citations."""

    def __init__(
        self,
        client: Client | None = None,
        retriever: Retriever | None = None,
        temperature: float = 0.1,
        max_steps: int = 6,
        stateless: bool = True,
        k: int = 5,
        model: str | None = None,
        guardrails: bool = True,
    ) -> None:
        """Create the agent.

        Args:
            client: LLM client; defaults to OpenAI with OPENAI_CHAT_MODEL (tests pass a mock).
            retriever: corpus search; defaults to the Qdrant index (tests pass an in-memory one).
            temperature: low, for consistent and grounded answers.
            max_steps: model/tool steps per question (searches, card reads, final answer).
            stateless: True answers every question on its own (evaluation); False keeps the
                conversation, so follow-ups like "e se invece ci pressano alti?" work (chat).
            k: passages returned by each search.
            model: OpenAI chat model; defaults to OPENAI_CHAT_MODEL (unused when `client` is given).
            guardrails: False runs the bare agent (to measure what the guardrails change).

        Raises:
            ValueError: if the OpenAI client is needed and OPENAI_API_KEY is not configured.
            RuntimeError: if the default retriever cannot reach Qdrant.
        """
        if client is None:
            model = model or load_settings().chat_model
            client = OpenAIClient(api_key=require_openai_key(), model=model, temperature=temperature)
        self.model = model
        self.client = client
        self.guardrails = guardrails
        self.stateless = stateless
        self.last_guard: dict[str, Any] = {}
        self.session_id = uuid.uuid4().hex   # one per conversation: Phoenix groups its traces
        self.corpus_tools = CorpusTools(retriever or build_retriever(), k=k)
        self.agent = Agent(
            name="match_analyst",
            client=client,
            system_prompt=MATCH_ANALYST_SYSTEM_PROMPT,
            tools=self.corpus_tools.tools(),
            max_steps=max_steps,
            terminate_on_text=True,
            stateless=stateless,
        )

    def analyze(self, question: str) -> str:
        """Answer one question; the cards used are then in `consulted_cards`, the guards' work in `last_guard`.

        With tracing on (src/observability), the question is one trace: this span, with the
        guardrails, the agent's steps, the searches and the model calls inside it.
        """
        with span("match_analyst", "CHAIN", question, **{"session.id": self.session_id}) as root:
            answer = self._answer(question)
            set_output(root, answer)
            root.set_attribute("metadata", json.dumps(
                {"model": self.model, "consulted_cards": self.consulted_cards, "guardrails": self.last_guard},
                ensure_ascii=False))
        return answer

    def _answer(self, question: str) -> str:
        self.corpus_tools.calls.clear()
        self.last_guard = {"input": None, "issues": [], "rewritten": False, "remaining": []}
        if self.guardrails:
            in_conversation = not self.stateless and len(self.agent._memory) > 0
            with span("input_guard", "GUARDRAIL", question) as guard:
                verdict = check_question(question, in_conversation=in_conversation)
                set_output(guard, verdict.reason if verdict.allowed else f"{verdict.reason}: {verdict.reply}")
            self.last_guard["input"] = verdict.reason
            if not verdict.allowed:
                return verdict.reply or ""
        response = self.agent.run(question)
        answer = response.text if hasattr(response, "text") else str(response)
        if not self.guardrails:
            return answer
        with span("output_guard", "GUARDRAIL", answer) as guard:
            final = self._review(question, answer)
            set_output(guard, json.dumps(self.last_guard, ensure_ascii=False))
        return final

    def _review(self, question: str, answer: str) -> str:
        """Output guard: check the answer; on problems, one rewrite, kept unless it is worse."""
        consulted = self.consulted_cards
        cards = {c: self.corpus_tools.retriever.card_text(c) or "" for c in consulted}
        source_text = "\n".join(cards.values())
        issues = review_answer(answer, question, consulted, source_text)
        self.last_guard["issues"] = [i.describe() for i in issues]
        self.last_guard["remaining"] = list(self.last_guard["issues"])
        if not issues:
            return answer
        try:
            rewritten = self._rewrite(question, answer, issues, cards)
        except Exception as e:  # network/API error: keep the first answer, say it in the report
            self.last_guard["error"] = f"{type(e).__name__}: {e}"
            return answer
        remaining = review_answer(rewritten, question, consulted, source_text) if rewritten else issues
        if not rewritten or len(remaining) > len(issues):
            return answer
        self.last_guard["rewritten"] = True
        self.last_guard["remaining"] = [i.describe() for i in remaining]
        return rewritten

    def _rewrite(self, question: str, answer: str, issues: list[Issue], cards: dict[str, str]) -> str:
        """One rewrite: rules + context in the system prompt, the request in the input."""
        problems = "\n".join(f"- {issue.instruction}" for issue in issues)
        request = REWRITE_REQUEST.format(question=question, answer=answer, problems=problems)
        system_prompt = MATCH_ANALYST_SYSTEM_PROMPT + "\n\nContext:\n" + card_context(cards)
        # The trace shows what the model read: the request, then the context it was given.
        with span("rewrite", "CHAIN", f"{request}\n\n--- context ---\n{card_context(cards)}") as current:
            rewritten = self.client.invoke(input=request, system_prompt=system_prompt).text.strip()
            set_output(current, rewritten)
        return rewritten

    @property
    def consulted_cards(self) -> list[str]:
        """Cards returned by searches or read in full while answering the last question."""
        return self.corpus_tools.consulted_cards()

    @property
    def guard_note(self) -> str | None:
        """One line on what the guardrails did for the last question (Italian, for the user), or None."""
        guard = self.last_guard
        if guard.get("input") in INPUT_NOTES:
            return f"Guardrail: {INPUT_NOTES[guard['input']]}."
        notes = []
        if guard.get("rewritten"):
            fixed = [ISSUE_NOTES[i.split(":")[0]] for i in guard["issues"]]
            notes.append("risposta corretta automaticamente (" + ", ".join(fixed) + ")")
        if guard.get("remaining"):
            notes.append("da verificare: " + "; ".join(guard["remaining"]))
        if guard.get("error"):
            notes.append("controllo di uscita non completato")
        return ("Guardrail: " + ". ".join(notes) + ".") if notes else None

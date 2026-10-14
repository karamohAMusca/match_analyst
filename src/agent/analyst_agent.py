"""The assistant coach agent (datapizza-ai `Agent` with the corpus tools), wrapped by the guardrails:

    question -> input guard -> agent (search, read, answer) -> real case from the card
             -> output guard (+ fact checks, + optional verifier) -> (one rewrite) -> wrong facts removed -> answer

The input guard stops injection attempts, off-topic questions and oversized inputs before any
model call; the output guard checks language, grounding and citations, and the verifier (a second
model, src/guardrails/verifier.py) checks every statement against the consulted cards. On a
problem, the model rewrites the answer once. The real case of an advice answer is written by code
from the card (src/guardrails/facts.py): the model only picks the match. Coach-team pairs and
thresholds are checked by rules (same module); a wrong fact still there after the rewrite is removed. What the guards did is in `last_guard` and
`guard_note`: a silent guardrail is indistinguishable from a broken one.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from datapizza.agents import Agent
from datapizza.clients import ClientFactory
from datapizza.core.clients.client import Client
from datapizza.type import ROLE, TextBlock

from src.agent.prompts import MATCH_ANALYST_SYSTEM_PROMPT, REWRITE_REQUEST
from src.core.config import LLM_PROVIDER, load_settings, require_api_key
from src.guardrails.facts import (FACT_KINDS, collapse_real_cases, expand_real_cases, fact_issues, man_down_answer,
                                  perspective_issues, premise_issues, remove_sentences, writes_man_down)
from src.guardrails.language import detect_language
from src.guardrails.input_guard import check_question
from src.evaluation.judge import JUDGE_MAX_RETRIES, JUDGE_TEMPERATURE, JUDGE_TIMEOUT_S
from src.guardrails.output_guard import Issue, review_answer
from src.guardrails.verifier import VERIFIER_MODEL, verify_answer
from src.observability.tracing import set_output, span
from src.rag.embedding_cache import CachedEmbedder
from src.rag.retrieval import Retriever
from src.rag.store import make_embedder, make_vector_store
from src.tools.corpus_tools import CorpusTools, card_context

log = logging.getLogger(__name__)

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
    "unsupported": "affermazioni non confermate dalle schede",
    "coach_team": "allenatore abbinato a una squadra che le schede non gli danno",
    "threshold": "soglia che le schede non indicano",
    "perspective": "consigli della situazione opposta (ad esempio superiorità invece di inferiorità)",
    "premise": "risultato dato per scontato (ad esempio un vantaggio mai detto)",
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
        verifier: Client | None = None,
        verify: bool | None = None,
    ) -> None:
        """Create the agent.

        Args:
            client: LLM client; defaults to the one datapizza's ClientFactory builds for LLM_PROVIDER
                (OpenAI) and OPENAI_CHAT_MODEL (tests pass a mock).
            retriever: corpus search; defaults to the Qdrant index (tests pass an in-memory one).
            temperature: low, for consistent and grounded answers.
            max_steps: model/tool steps per question (searches, card reads, final answer).
            stateless: True answers every question on its own (evaluation); False keeps the
                conversation, so follow-ups like "e se invece ci pressano alti?" work (chat).
            k: passages returned by each search.
            model: OpenAI chat model; defaults to OPENAI_CHAT_MODEL (unused when `client` is given).
            guardrails: False runs the bare agent (to measure what the guardrails change).
            verifier: client of the verifier; defaults to VERIFIER_MODEL, built only together with
                the default `client` (tests that pass a mock pass a fake verifier to test it).
            verify: True adds the verifier (off by default: in gold runs 114805 vs 112356 it gave
                +0.025 faithfulness for 5x the cost and 4x the latency, under the acceptance gate);
                None = on only when a `verifier` client is given; False = off.

        Raises:
            ValueError: if the OpenAI client is needed and OPENAI_API_KEY is not configured.
            RuntimeError: if the default retriever cannot reach Qdrant.
        """
        default_clients = client is None
        if client is None:
            model = model or load_settings().chat_model
            client = ClientFactory.create(provider=LLM_PROVIDER, api_key=require_api_key(LLM_PROVIDER),
                                          model=model, temperature=temperature)
        verify = (verifier is not None if verify is None else verify) and guardrails
        if verify and verifier is None and default_clients:
            verifier = ClientFactory.create(provider=LLM_PROVIDER, api_key=require_api_key(LLM_PROVIDER),
                                            model=VERIFIER_MODEL, temperature=JUDGE_TEMPERATURE,
                                            timeout=JUDGE_TIMEOUT_S, max_retries=JUDGE_MAX_RETRIES)
        self.model = model
        self.client = client
        self.verifier = verifier if verify else None
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
                {"model": self.model, "verifier": self.verifier_model, "consulted_cards": self.consulted_cards,
                 "guardrails": self.last_guard},
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
                if verdict.reason in INPUT_NOTES:   # off topic, injection, too long
                    log.warning("input guard: question stopped (%s), no model call", verdict.reason)
                else:                               # greeting, thanks, empty
                    log.info("input guard: %s, fixed reply without the model", verdict.reason)
                return verdict.reply or ""
            log.info("input guard: %s", verdict.reason)
            if writes_man_down(question, "\n".join(self.coach_questions)):   # the memory: earlier questions only
                composed = self._answer_man_down(question)
                if composed:
                    return composed
        response = self.agent.run(question)
        draft = response.text if hasattr(response, "text") else str(response)
        answer = self._compose(draft)
        if self.guardrails:
            with span("output_guard", "GUARDRAIL", answer) as guard:
                answer = self._review(question, answer)
                set_output(guard, json.dumps(self.last_guard, ensure_ascii=False))
        if answer != draft:
            self._remember(answer)
        return answer

    def _answer_man_down(self, question: str) -> str | None:
        """A man down has no card of its own: the answer is written by code from the cards
        (src/guardrails/facts.py, `man_down_answer`), without a model call, and kept in the memory."""
        retriever = self.corpus_tools.retriever
        card_ids = list(dict.fromkeys(c.metadata["document_id"] for c in retriever.chunks))
        composed = man_down_answer(card_ids, retriever.card_text, english=detect_language(question) == "en")
        if composed is None:
            return None
        answer, used = composed
        self.corpus_tools.calls.extend({"tool": "read_card", "document_id": c, "found": True} for c in used)
        self.last_guard["composed"] = "a man down"
        if not self.stateless:
            self.agent._memory.add_turn([TextBlock(content=question)], ROLE.USER)
            self.agent._memory.add_turn([TextBlock(content=answer)], ROLE.ASSISTANT)
        log.info("a man down: answer written from the cards %s, no model call", used)
        return answer

    def _compose(self, answer: str) -> str:
        """The real-case line written with the card's own sentence (src/guardrails/facts.py)."""
        return expand_real_cases(answer, self.consulted_cards, self.corpus_tools.retriever.card_text)

    @property
    def coach_questions(self) -> list[str]:
        """The coach's questions of this conversation so far, read from datapizza's memory (its USER
        turns): only the ones that reached the agent, as a question stopped by the input guard never
        enters the memory. Empty for a stateless agent, which forgets after every question."""
        return [block.content for turn in self.agent._memory if turn.role == ROLE.USER
                for block in turn if isinstance(block, TextBlock)]

    def _review(self, question: str, answer: str) -> str:
        """Output guard: check the answer; on problems, one rewrite, kept unless it is worse (more
        problems under the same checks). In a chat, the coach's earlier questions count as known
        text (the opponent named in turn 1 is not an invention in turn 2)."""
        consulted = self.consulted_cards
        cards = {c: self.corpus_tools.retriever.card_text(c) or "" for c in consulted}
        source_text, context = "\n".join(cards.values()), card_context(cards)
        earlier = "\n".join(self.coach_questions[:-1])   # the memory already holds the current question
        # Checks and rewrite see the real-case line as the model is asked to write it (label and id):
        # the card's sentence is not the model's to check or to rewrite.
        issues = self._check(collapse_real_cases(answer), question, consulted, source_text, context, earlier)
        self.last_guard["issues"] = [i.describe() for i in issues]
        self.last_guard["remaining"] = list(self.last_guard["issues"])
        if not issues:
            log.info("output guard: no problem")
            return answer
        log.info("output guard: %d problems, one rewrite: %s", len(issues), self.last_guard["issues"])
        try:
            rewritten = self._rewrite(question, collapse_real_cases(answer), issues, context)
        except Exception as e:  # network/API error: keep the first answer, say it in the report
            self.last_guard["error"] = f"{type(e).__name__}: {e}"
            log.warning("output guard: rewrite failed, first answer kept", exc_info=True)
            return self._drop_wrong_facts(answer, issues)
        rewritten = self._compose(rewritten) if rewritten else rewritten
        remaining = (self._check(collapse_real_cases(rewritten), question, consulted, source_text, context, earlier)
                     if rewritten else issues)
        if not rewritten or len(remaining) > len(issues):
            log.warning("output guard: rewrite discarded (%d problems left instead of %d)", len(remaining), len(issues))
            return self._drop_wrong_facts(answer, issues)
        log.info("output guard: rewrite kept, %d problems left", len(remaining))
        self.last_guard["rewritten"] = True
        self.last_guard["remaining"] = [i.describe() for i in remaining]
        return self._drop_wrong_facts(rewritten, remaining)

    def _drop_wrong_facts(self, answer: str, issues: list[Issue]) -> str:
        """Remove the sentences with a wrong fact (coach-team pair, threshold) still there after the
        rewrite, or when there was no rewrite: a wrong fact found never reaches the coach."""
        wrong = [i for i in issues if i.kind in FACT_KINDS]
        if not wrong:
            return answer
        self.last_guard["removed"] = [i.detail for i in wrong]
        self.last_guard["remaining"] = [d for d in self.last_guard.get("remaining", [])
                                        if not d.startswith(FACT_KINDS)]
        log.warning("output guard: %d sentences with a wrong fact removed", len(wrong))
        return remove_sentences(answer, self.last_guard["removed"])

    def _check(self, answer: str, question: str, consulted: list[str], source_text: str, context: str,
               earlier: str) -> list[Issue]:
        """The deterministic checks, then the verifier (only when the answer rests on cards)."""
        issues = review_answer(answer, question, consulted, source_text, earlier)
        if consulted:
            issues += (fact_issues(answer, source_text) + perspective_issues(answer, question, earlier)
                       + premise_issues(answer, f"{question}\n{earlier}"))
        if self.verifier is None or not consulted:
            return issues
        with span("verifier", "GUARDRAIL", answer) as current:
            unsupported, error = verify_answer(self.verifier, answer, question, context, earlier)
            set_output(current, error or json.dumps([i.detail for i in unsupported], ensure_ascii=False))
        if error:   # never blocks the answer: reported, as a guardrail must not be silent
            self.last_guard["verifier_error"] = error
            log.warning("verifier: not completed (%s)", error)
        else:
            log.info("verifier: %d statements not supported by the cards", len(unsupported))
        return issues + unsupported

    def _remember(self, answer: str) -> None:
        """In a chat, make datapizza's memory hold the answer the coach saw: the agent stored its
        draft before the output guard rewrote it, and the next turn would build on the draft."""
        if self.stateless:
            return
        for turn in reversed(self.agent._memory.memory):
            if turn.role == ROLE.ASSISTANT:
                for i, block in enumerate(turn):
                    if isinstance(block, TextBlock):
                        turn[i] = TextBlock(content=answer)
                        return
                return

    def _rewrite(self, question: str, answer: str, issues: list[Issue], context: str) -> str:
        """One rewrite: rules + context (the consulted cards) in the system prompt, the request in the input."""
        problems = "\n".join(f"- {issue.instruction}" for issue in issues)
        request = REWRITE_REQUEST.format(question=question, answer=answer, problems=problems)
        system_prompt = MATCH_ANALYST_SYSTEM_PROMPT + "\n\nContext:\n" + context
        # The trace shows what the model read: the request, then the context it was given.
        with span("rewrite", "CHAIN", f"{request}\n\n--- context ---\n{context}") as current:
            rewritten = self.client.invoke(input=request, system_prompt=system_prompt).text.strip()
            set_output(current, rewritten)
        return rewritten

    @property
    def verifier_model(self) -> str | None:
        """The verifier's model, or None when the answers are not verified."""
        return getattr(self.verifier, "model_name", None) if self.verifier is not None else None

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
        if guard.get("composed") == "a man down":
            return ("Guardrail: nessuna scheda per chi gioca con un uomo in meno: risposta composta con le "
                    "schede, cosa farà l'avversario.")
        notes = []
        if guard.get("rewritten"):
            fixed = dict.fromkeys(ISSUE_NOTES[i.split(":")[0]] for i in guard["issues"])
            notes.append("risposta corretta automaticamente (" + ", ".join(fixed) + ")")
        if guard.get("removed"):
            notes.append(f"{len(guard['removed'])} frasi tolte perché le schede dicono altro")
        if guard.get("remaining"):
            notes.append("da verificare: " + "; ".join(guard["remaining"]))
        if guard.get("error"):
            notes.append("controllo di uscita non completato")
        if guard.get("verifier_error"):
            notes.append("verifica delle affermazioni non completata")
        return ("Guardrail: " + ". ".join(notes) + ".") if notes else None

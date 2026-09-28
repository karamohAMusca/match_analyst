"""The assistant coach agent (datapizza-ai `Agent` with the corpus tools)."""

from __future__ import annotations

from datapizza.agents import Agent
from datapizza.clients.openai import OpenAIClient
from datapizza.core.clients.client import Client

from src.agent.prompts import MATCH_ANALYST_SYSTEM_PROMPT
from src.core.config import load_settings, require_openai_key
from src.rag.embedding_cache import CachedEmbedder
from src.rag.retrieval import Retriever
from src.rag.store import make_embedder, make_vector_store
from src.tools.corpus_tools import CorpusTools


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

        Raises:
            ValueError: if the OpenAI client is needed and OPENAI_API_KEY is not configured.
            RuntimeError: if the default retriever cannot reach Qdrant.
        """
        if client is None:
            model = model or load_settings().chat_model
            client = OpenAIClient(api_key=require_openai_key(), model=model, temperature=temperature)
        self.model = model
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
        """Answer one question; the cards used are then in `consulted_cards`."""
        self.corpus_tools.calls.clear()
        response = self.agent.run(question)
        return response.text if hasattr(response, "text") else str(response)

    @property
    def consulted_cards(self) -> list[str]:
        """Cards returned by searches or read in full while answering the last question."""
        return self.corpus_tools.consulted_cards()

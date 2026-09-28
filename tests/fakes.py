"""Test doubles: a deterministic embedder and a scripted LLM, so tests need no API key and no network."""

from __future__ import annotations

import hashlib
import math
import re

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.core.embedder import BaseEmbedder
from datapizza.type import FunctionCallBlock, FunctionCallResultBlock, TextBlock

DIM = 64
MODEL = "fake-embedding"
COLLECTION = "test_cards"


class FakeEmbedder(BaseEmbedder):
    """Bag-of-words vectors: texts sharing words are close, which is enough to test search."""

    def __init__(self) -> None:
        self.model_name = MODEL
        self.calls = 0

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed(self, text, model_name=None):
        self.calls += 1
        return self._vector(text) if isinstance(text, str) else [self._vector(t) for t in text]


class ScriptedLLM(MockClient):
    """Fake chat model with the agent's expected behaviour, to test the loop without the API:
    a greeting is answered directly; any other question triggers search_cards with the question,
    and the final answer quotes the passages the tool returned.
    """

    def __init__(self) -> None:
        super().__init__(model_name="scripted-llm")
        self.system_prompts: list[str | None] = []

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs):
        self.system_prompts.append(system_prompt)
        if memory and isinstance(memory[-1].blocks[-1], FunctionCallResultBlock):
            return ClientResponse(content=[TextBlock(content="Dalle schede:\n" + memory[-1].blocks[-1].result)])
        question = next((b.content for b in input if isinstance(b, TextBlock)), "")
        if question.lower().startswith("ciao"):
            return ClientResponse(content=[TextBlock(content="Ciao! Sono il tuo assistente allenatore.")])
        search = next(t for t in tools or [] if t.name == "search_cards")
        return ClientResponse(
            content=[FunctionCallBlock(id="call-1", name=search.name, arguments={"query": question}, tool=search)]
        )

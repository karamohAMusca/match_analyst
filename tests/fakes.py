"""Test doubles: a deterministic embedder and a scripted LLM, so tests need no API key and no network."""

from __future__ import annotations

import hashlib
import math
import re

from datapizza.clients.mock_client import MockClient
from datapizza.core.clients import ClientResponse
from datapizza.core.clients.models import TokenUsage
from datapizza.core.embedder import BaseEmbedder
from datapizza.type import FunctionCallBlock, FunctionCallResultBlock, StructuredBlock, TextBlock

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
    and the final answer quotes the passages the tool returned (so it is in Italian, like the cards).
    A call without tools is the output guardrail asking for a rewrite: it returns `rewrite`, or
    fails like a network error when no rewrite is scripted.
    """

    def __init__(self, rewrite: str | None = None) -> None:
        super().__init__(model_name="scripted-llm")
        self.system_prompts: list[str | None] = []
        self.rewrite = rewrite
        self.rewrite_requests: list[str] = []
        self.seen: list[tuple[str, int]] = []   # (question, turns already in memory) for every call

    def _invoke(self, input, tools=None, memory=None, system_prompt=None, **kwargs):
        self.system_prompts.append(system_prompt)
        self.seen.append((next((b.content for b in input if isinstance(b, TextBlock)), ""), len(memory or [])))
        if not tools:
            self.rewrite_requests.append(next((b.content for b in input if isinstance(b, TextBlock)), ""))
            if self.rewrite is None:
                raise ConnectionError("no rewrite scripted")
            return ClientResponse(content=[TextBlock(content=self.rewrite)])
        if memory and isinstance(memory[-1].blocks[-1], FunctionCallResultBlock):
            return ClientResponse(content=[TextBlock(content="Dalle schede:\n" + memory[-1].blocks[-1].result)])
        question = next((b.content for b in input if isinstance(b, TextBlock)), "")
        if question.lower().startswith("ciao"):
            return ClientResponse(content=[TextBlock(content="Ciao! Sono il tuo assistente allenatore.")])
        search = next(t for t in tools or [] if t.name == "search_cards")
        return ClientResponse(
            content=[FunctionCallBlock(id="call-1", name=search.name, arguments={"query": question}, tool=search)]
        )


class FakeJudge(MockClient):
    """Fake LLM judge, 100 + 20 tokens per call; `fail=True` makes every judgement raise.

    - one-score judges (`Verdict`): `faithfulness` or `relevancy`, chosen by the system prompt;
    - claim-by-claim faithfulness: the answer is split into sentences (the statements), and a
      statement is supported unless it contains one of the `unsupported` markers.
    """

    def __init__(self, faithfulness: float = 0.9, relevancy: float = 0.8, fail: bool = False,
                 unsupported: tuple[str, ...] = ()) -> None:
        super().__init__(model_name="fake-judge")
        self.scores = {"FAITHFULNESS": faithfulness, "RELEVANCY": relevancy}
        self.fail = fail
        self.unsupported = unsupported
        self.inputs: list[str] = []
        self.temperatures: list[float | None] = []
        self.max_tokens: list[int | None] = []

    def _structured_response(self, input, output_cls, memory=None, temperature=None, max_tokens=None,
                             system_prompt=None, tools=None, tool_choice="auto", **kwargs):
        text = input[0].content
        self.inputs.append(text)
        self.temperatures.append(temperature)
        self.max_tokens.append(max_tokens)
        if self.fail:
            raise TimeoutError("judge unavailable")
        if output_cls.__name__ == "Statements":
            answer = re.sub(r"\[[^\]]*\]", "", text.split("ANSWER:\n", 1)[1])
            sentences = [s.strip(" .") for s in re.split(r"(?<=\.)\s+|\n+", answer)]
            content = output_cls(statements=[s for s in sentences if s and not s.lower().startswith("non lo so")])
        elif output_cls.__name__ in ("StatementVerdicts", "RoleCheckedVerdicts"):   # RoleChecked: the verifier
            statements = re.findall(r"^\d+\. (.+)$", text.split("STATEMENTS:\n", 1)[1], re.M)
            roles = ({"roles_in_statement": "scripted", "roles_in_evidence": "scripted"}
                     if output_cls.__name__ == "RoleCheckedVerdicts" else {})
            content = output_cls(verdicts=[
                {"statement": s, "supported": not any(m in s for m in self.unsupported),
                 "evidence": "not in the context" if any(m in s for m in self.unsupported) else "scripted", **roles}
                for s in statements])
        else:
            score = next(v for key, v in self.scores.items() if key in (system_prompt or ""))
            content = output_cls(score=score, reason="scripted")
        return ClientResponse(content=[StructuredBlock(content=content)],
                              usage=TokenUsage(prompt_tokens=100, completion_tokens=20))

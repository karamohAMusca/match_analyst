"""Tracing (offline): the spans Phoenix would receive, captured by an in-memory exporter."""

from __future__ import annotations

import json

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from src.agent.analyst_agent import MatchAnalyst
from src.observability import tracing
from src.observability.tracing import phoenix_is_up, setup_tracing, translate
from tests.fakes import ScriptedLLM

PROJECT = "match_analyst_test"
ENGLISH_QUESTION = "In Pioli's thesis, how does the 4-4-2 press on the flanks?"
ENGLISH_REWRITE = "The thesis describes the zonal 4-4-2 of Chievo's youth team [coach_pioli]."


def test_generation_span_is_translated_to_an_llm_span():
    attrs = {"type": "generation", "model_name": "gpt-4o-mini", "prompt_tokens_used": 1200,
             "completion_tokens_used": 150, "output": "Risposta [coach_pioli].",
             "input": json.dumps([{"type": "text", "content": "Come si attacca un 4-4-2?"}]),
             "memory": json.dumps([{"role": "user", "blocks": [{"type": "text", "content": "Ciao"}]}])}
    out = translate(attrs)
    assert out["openinference.span.kind"] == "LLM" and out["llm.model_name"] == "gpt-4o-mini"
    assert (out["llm.token_count.prompt"], out["llm.token_count.completion"]) == (1200, 150)
    assert out["llm.input_messages.0.message.content"] == "Ciao"                  # memory first...
    assert out["llm.input_messages.1.message.content"] == "Come si attacca un 4-4-2?"   # ...then the input
    assert out["llm.output_messages.0.message.content"] == "Risposta [coach_pioli]."
    assert out["type"] == "generation"                                           # originals kept


def test_tool_span_and_json_only_when_it_is_json():
    out = translate({"type": "tool", "tool_arguments": '{"query": "blocco basso"}', "tool_result": "[coach_x] testo"})
    assert out["openinference.span.kind"] == "TOOL" and out["tool.parameters"] == '{"query": "blocco basso"}'
    assert out["output.value"] == "[coach_x] testo" and "output.mime_type" not in out   # "[" but not JSON


def test_phoenix_down_switches_tracing_off_and_says_so():
    endpoint = "http://localhost:9/v1/traces"          # nothing listens on port 9
    assert not phoenix_is_up(endpoint, timeout=0.2)
    if tracing._active["provider"] is None:
        assert "non raggiungibile" in setup_tracing(endpoint, PROJECT)
        assert tracing._active["provider"] is None


@pytest.fixture(scope="module")
def exported(retriever):
    """Two questions traced into memory: one answered (with a rewrite), one stopped at the input."""
    exporter = InMemorySpanExporter()
    status = setup_tracing("http://unused/v1/traces", PROJECT, exporter=exporter)
    if "già attivo" in status:
        pytest.skip("a tracer provider was already configured in this test session")
    MatchAnalyst(client=ScriptedLLM(rewrite=ENGLISH_REWRITE), retriever=retriever).analyze(ENGLISH_QUESTION)
    MatchAnalyst(client=ScriptedLLM(), retriever=retriever).analyze("Mi scrivi la ricetta della carbonara?")
    tracing.flush()
    return exporter.get_finished_spans()


def _trace_of(spans, question):
    root = next(s for s in spans if s.name == "match_analyst" and s.attributes["input.value"] == question)
    return root, [s for s in spans if s.context.trace_id == root.context.trace_id]


def test_one_trace_per_question_with_every_step(exported):
    root, spans = _trace_of(exported, ENGLISH_QUESTION)
    names = {s.name for s in spans}
    assert {"input_guard", "Agent match_analyst", "Tool search_cards", "retrieve", "client.invoke",
            "output_guard", "rewrite"} <= names
    assert root.attributes["openinference.span.kind"] == "CHAIN"
    assert root.attributes["output.value"] == ENGLISH_REWRITE and root.attributes["session.id"]
    assert json.loads(root.attributes["metadata"])["guardrails"]["rewritten"] is True
    assert all(s.resource.attributes[tracing.PROJECT_KEY] == PROJECT for s in spans)


def test_llm_and_retrieval_spans_carry_what_phoenix_shows(exported):
    _, spans = _trace_of(exported, ENGLISH_QUESTION)
    llm = [s for s in spans if s.name == "client.invoke"]
    assert all(s.attributes["openinference.span.kind"] == "LLM" for s in llm)
    assert all(s.attributes["llm.model_name"] == "scripted-llm" for s in llm)
    assert any("llm.input_messages.0.message.content" in s.attributes for s in llm)
    retrieve = next(s for s in spans if s.name == "retrieve")
    assert retrieve.attributes["openinference.span.kind"] == "RETRIEVER"
    assert retrieve.attributes["input.value"].startswith(ENGLISH_QUESTION)   # the fake model searches with its input
    assert retrieve.attributes["retrieval.documents.0.document.id"]
    rewrite = next(s for s in spans if s.name == "rewrite")
    assert "--- context ---\n[" in rewrite.attributes["input.value"]              # the cards the model read


def test_blocked_question_never_reaches_the_model(exported):
    _, spans = _trace_of(exported, "Mi scrivi la ricetta della carbonara?")
    assert {s.name for s in spans} == {"match_analyst", "input_guard"}
    guard = next(s for s in spans if s.name == "input_guard")
    assert guard.attributes["openinference.span.kind"] == "GUARDRAIL"
    assert guard.attributes["output.value"].startswith("off_topic")

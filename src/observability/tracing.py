"""Tracing to Arize Phoenix with OpenTelemetry: every question becomes one trace.

datapizza-ai already emits OpenTelemetry spans (agent, tool, generation) but with attribute
names of its own (`type`, `model_name`, `prompt_tokens_used`, `input`, `output`, `tool_result`).
Phoenix reads the OpenInference conventions (`openinference.span.kind`, `llm.model_name`,
`llm.token_count.prompt`, `input.value`, ...): without a translation the spans arrive, but
Phoenix shows neither prompts, answers nor token counts. `OpenInferenceExporter` translates
each span right before it is sent.
Our own spans (the whole question, guardrails, retrieval with its documents) are written
directly in OpenInference by `span()` and `record_documents()`.

Three details that silently produce empty traces if missed:
- the exporter is OTLP over HTTP: http://localhost:6006/v1/traces (not the gRPC port 4317);
- DATAPIZZA_TRACE_CLIENT_IO=true, or datapizza does not put prompts and answers on its spans;
- the global tracer provider can be set only once: if one exists, we attach to it.
Phoenix down is not an error: tracing is switched off and the caller is told so.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter, SpanExportResult

PROJECT_KEY = "openinference.project.name"   # Phoenix groups traces by project
MAX_CHARS = 20000                            # long card contexts are cut in the UI, not in the run
KIND = {"agent": "AGENT", "generation": "LLM", "tool": "TOOL"}
ATTRIBUTES = {   # datapizza attribute -> OpenInference attribute
    "model_name": "llm.model_name",
    "prompt_tokens_used": "llm.token_count.prompt",
    "completion_tokens_used": "llm.token_count.completion",
    "cached_tokens_used": "llm.token_count.prompt_details.cache_read",
    "input": "input.value",
    "output": "output.value",
    "tool_arguments": "tool.parameters",
    "tool_result": "output.value",
}
_tracer = trace.get_tracer("match_analyst")
_active: dict[str, Any] = {"provider": None}


def _blocks_text(blocks: list) -> str:
    return "\n".join(str(b.get("content") or b.get("result") or b.get("arguments") or b)
                     if isinstance(b, dict) else str(b) for b in blocks)


def _messages(attrs: dict) -> list[tuple[str, str]]:
    """The conversation an LLM span received: memory turns, then the new input."""
    messages: list[tuple[str, str]] = []
    for key in ("memory", "input"):
        try:
            value = json.loads(attrs.get(key) or "null")
        except (TypeError, ValueError):
            continue
        if not isinstance(value, list) or not value:
            continue
        if key == "memory":
            messages += [(str(t.get("role", "user")), _blocks_text(t.get("blocks", []))) for t in value if isinstance(t, dict)]
        else:
            messages.append(("user", _blocks_text(value)))
    return messages


def translate(attrs: dict, name: str = "") -> dict:
    """datapizza span attributes plus their OpenInference equivalents (originals are kept)."""
    out = dict(attrs)
    kind = KIND.get(attrs.get("type"))
    if kind and "openinference.span.kind" not in attrs:
        out["openinference.span.kind"] = kind
    for source, target in ATTRIBUTES.items():
        if source in attrs and target not in attrs:
            out[target] = attrs[source]
    if attrs.get("type") == "generation":
        for i, (role, content) in enumerate(_messages(attrs)):
            out[f"llm.input_messages.{i}.message.role"] = role
            out[f"llm.input_messages.{i}.message.content"] = content[:MAX_CHARS]
        if attrs.get("output"):
            out["llm.output_messages.0.message.role"] = "assistant"
            out["llm.output_messages.0.message.content"] = str(attrs["output"])[:MAX_CHARS]
    for key in ("input.value", "output.value"):   # declare JSON only when it really is JSON
        value = out.get(key)
        if isinstance(value, str) and value[:1] in "[{":
            try:
                json.loads(value)
            except ValueError:
                continue
            out[key.replace(".value", ".mime_type")] = "application/json"
    return out


class OpenInferenceExporter(SpanExporter):
    """Wraps an exporter: translates datapizza attributes and labels the Phoenix project."""

    def __init__(self, inner: SpanExporter, project: str) -> None:
        self._inner = inner
        self._project = Resource({PROJECT_KEY: project})

    def export(self, spans) -> SpanExportResult:
        return self._inner.export([
            ReadableSpan(
                name=s.name, context=s.context, parent=s.parent,
                resource=s.resource.merge(self._project),
                attributes=translate(dict(s.attributes or {}), s.name or ""),
                events=s.events, links=s.links, status=s.status, kind=s.kind,
                start_time=s.start_time, end_time=s.end_time,
                instrumentation_scope=s.instrumentation_scope,
            )
            for s in spans
        ])

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self._inner.force_flush(timeout_millis)


def phoenix_is_up(endpoint: str, timeout: float = 1.0) -> bool:
    """True if the Phoenix server answers (its UI is on the same host and port as the collector)."""
    base = endpoint.split("/v1/")[0]
    try:
        with urllib.request.urlopen(base, timeout=timeout):
            return True
    except OSError:
        return False


def setup_tracing(endpoint: str, project: str, exporter: SpanExporter | None = None) -> str:
    """Send the spans to Phoenix; call once, before any model call. Returns a one-line status.

    `exporter`: tests pass an in-memory one (then Phoenix is not needed).
    """
    if _active["provider"] is not None:
        return "Tracing già attivo."
    if exporter is None:
        if not phoenix_is_up(endpoint):
            return f"Phoenix non raggiungibile ({endpoint.split('/v1/')[0]}): tracing spento."
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        exporter = OTLPSpanExporter(endpoint=endpoint)
    os.environ["DATAPIZZA_TRACE_CLIENT_IO"] = "true"   # prompts and answers on datapizza's spans
    processor = BatchSpanProcessor(OpenInferenceExporter(exporter, project))
    provider = trace.get_tracer_provider()
    if not hasattr(provider, "add_span_processor"):     # no SDK provider yet: create ours
        provider = TracerProvider(resource=Resource.create({"service.name": project}))
        trace.set_tracer_provider(provider)
    provider.add_span_processor(processor)
    _active["provider"] = provider
    return f"Tracing attivo: {endpoint.split('/v1/')[0]} (progetto {project})."


def flush() -> None:
    """Send the spans still buffered (the CLI calls it before exiting)."""
    if _active["provider"] is not None:
        _active["provider"].force_flush()


@contextmanager
def span(name: str, kind: str, input_value: str = "", **attributes: Any) -> Iterator[Any]:
    """A span written directly in OpenInference; a no-op when tracing is off."""
    with _tracer.start_as_current_span(name) as current:
        current.set_attribute("openinference.span.kind", kind)
        if input_value:
            current.set_attribute("input.value", input_value[:MAX_CHARS])
        for key, value in attributes.items():
            if value is not None:
                current.set_attribute(key, value)
        yield current


def tag_run(name: str) -> Any:
    """One span around a whole gold run, so in Phoenix each run is one comparable trace
    (the questions are inside it) instead of being mixed with the others."""
    return span(f"gold_run {name}", "CHAIN", **{"run.tag": name})


def set_output(current: Any, value: str) -> None:
    current.set_attribute("output.value", value[:MAX_CHARS])


def record_documents(current: Any, chunks: list, max_chars: int = 2000) -> None:
    """Retrieved chunks as OpenInference documents: Phoenix lists them with id, score and text."""
    for i, chunk in enumerate(chunks):
        base = f"retrieval.documents.{i}.document"
        md = chunk.metadata
        current.set_attribute(f"{base}.id", str(md.get("document_id", chunk.id)))
        current.set_attribute(f"{base}.content", chunk.text[:max_chars])
        if isinstance(md.get("score"), (int, float)):
            current.set_attribute(f"{base}.score", float(md["score"]))
        current.set_attribute(f"{base}.metadata", json.dumps(
            {k: md[k] for k in ("title", "category", "section", "dense_score", "bm25_score") if k in md},
            ensure_ascii=False))

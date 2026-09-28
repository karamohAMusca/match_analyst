# AGENTS.md — Project Instructions for Match Analyst AI

This document defines the architectural rules, coding standards, and operational guidelines for AI coding agents working on the `match_analyst` project.

---

## 1. Project Mission

`match_analyst` is an assistant coach built as an agentic RAG application:
- The user DESCRIBES their own team and the opponent (no live team data) and asks for match preparation or in-game advice.
- The agent retrieves cited knowledge from a curated card corpus (`corpus/`) stored in a vector store (`Qdrant`).
- Advice must be grounded in retrieved sources, with priority on recent (2022–2026) winning tactics.
- When the corpus does not contain the answer, the agent says so ("Non lo so") instead of inventing facts.

---

## 2. Core Tech Stack & Constraints

- **Framework**: `datapizza-ai v0.1.0` (core, clients-openai, embedders-openai, vectorstores-qdrant).
- **Language**: Python 3.10+ with strict type hints.
- **Language Convention**: All code, comments, docstrings, prompts, and documentation MUST BE IN ENGLISH.
  Exceptions: the corpus cards (`corpus/`) and the answers shown to the user are in Italian (the users are Italian coaches); English questions are supported.
- **Vector Store**: Qdrant running locally via Docker (`docker-compose.yml`) on port `6337` (collection: `match_analyst_tactics`, named vector `content_embedding`).
- **Embeddings**: `text-embedding-3-small`.
- **LLM Engine**: `gpt-4o-mini`.
- **Observability**: OpenTelemetry bridge exporting traces to Arize Phoenix on `http://localhost:6006/v1/traces`.
- **Frontend**: Streamlit.
- **Secrets**: read the API key only through `src.core.config.require_openai_key()`, right before the call that needs it. Never load `.env` files outside the project root.

---

## 3. Architecture & Conventions

- **Separation of Concerns**:
  - One folder per responsibility, no loose modules in `src/`:
  - `src/core/`: paths and settings (`config.py`).
  - `src/corpus/`: reading cards and manifest, splitting cards into chunks. Offline only: no API keys, no network.
  - `src/rag/`: Qdrant store, embeddings, search, and ingestion. Ingest only the cards listed in `corpus/manifest.json`; the YAML front matter goes into the payload, not into the embedded text.
  - `src/evaluation/`: measuring the system against `eval/gold_set.json` (frozen): retrieval metrics, deterministic answer checks, LLM judge, gold run, cost. Two entry points: `scripts/eval_agent.py` (fast deterministic checks, guardrail questions included) and `scripts/gold_run.py` (all metrics with the LLM judge; `--rejudge` re-judges a saved run). Runs are saved in `eval/runs/` and listed in `eval/runs/README.md`.
  - `src/agent/`: Only agent initialization, loop orchestration, and system prompts.
  - `src/tools/`: Clean, typed `@tool` functions with explicit docstrings explaining inputs and outputs.
  - `src/guardrails/`: Strict input/output validation; non-football queries MUST be intercepted before reaching the LLM.
  - `src/observability/`: tracing to Arize Phoenix (OpenTelemetry spans translated to OpenInference); optional at runtime.
  - `scripts/`: maintenance scripts, run as `python -m scripts.<name>`.
  - `tests/`: offline tests (no API keys, no network), run with `python -m pytest`.
- **Error Handling**: Tools must handle network/API errors gracefully and return structured failure explanations instead of crashing.
- **No Hallucinations Rule**: every claim in an answer must be supported by a retrieved card and cite its `document_id`.

---

## 4. Corpus Rules

- Cards follow the writing rules in `references/SOURCES.md` (facts only from cited sources, verbatim quotes, labelled interpretation).
- After editing a card: `python -m scripts.build_manifest`, then `python -m pytest` and `python -m scripts.check_corpus`, then re-sync the index with `python -m scripts.ingest` (only changed cards are embedded).
- `eval/gold_set.json` is the evaluation yardstick: do not edit it while tuning prompts or retrieval.

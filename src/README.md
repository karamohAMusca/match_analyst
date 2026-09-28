# `src/` — what each file does

```
corpus/*.md ──► corpus/cards.py ──► corpus/chunking.py ──► rag/ingest.py ──► Qdrant
  (cards)        read cards          one chunk per ##       embed + store     (Docker)
                                                                                 │
user question ──► agent/analyst_agent.py ──► tools/corpus_tools.py ──► rag/retrieval.py
                  (Agent + prompts.py)        search_cards, read_card    Retriever ◄─────┘
                                                                 (dense + BM25 → fusion → max 1 per card)
```

| File | What it does | Needs |
|---|---|---|
| `core/config.py` | Project paths and settings from `.env` (models, Qdrant host/port/collection). The API key is read only by `require_openai_key()`, right before a call. | — |
| `corpus/cards.py` | Reads a card: YAML front matter → `metadata`, Markdown → `body`. Loads all cards or only those in `manifest.json`; `stale_cards()` tells which cards changed since the last manifest build. | — |
| `corpus/chunking.py` | Splits a card into chunks, one per `##` section, each starting with the card title. Front matter goes into the chunk payload, not into the text. Fixed chunk ids (no duplicates on re-ingestion). | — |
| `rag/store.py` | Connects to Qdrant (Docker), creates the collection, builds the OpenAI embedder. `search_vector()` is the dense search: nearest chunks with their similarity score, optionally only from some card categories. | Docker, key |
| `rag/ingest.py` | `sync_corpus()`: puts the cards into Qdrant with a datapizza `IngestionPipeline`. Incremental: embeds only new or changed cards, removes deleted ones. | Docker, key |
| `rag/retrieval.py` | `Retriever`: the search used by the app. Hybrid as in the course: dense (Qdrant) + BM25 keywords, fused by interleaving (1st dense, 1st BM25, 2nd dense, ...; the course's RRF is kept for comparison), then at most 1 chunk per card (`DEFAULT_MAX_PER_CARD`). Modes `dense`, `bm25`, `hybrid` for comparisons. | Docker, key (not for BM25) |
| `rag/embedding_cache.py` | `CachedEmbedder`: saves embeddings in `.cache/` so the same text is never paid twice; works offline on cached texts. | key only for new texts |
| `evaluation/retrieval_metrics.py` | Retrieval metrics on the gold set: recall@1, recall@5, MRR@10 (course definitions) plus multi-card checks. Used by `scripts/eval_retrieval.py`. | — |
| `evaluation/answer_checks.py` | Automatic checks on agent answers: citations only to consulted cards, no card-internal author references as citations, tool use, "Non lo so", answer language, required facts, length of advice. Used by `scripts/eval_agent.py`. | — |
| `evaluation/grounding.py` | Grounding check: every proper noun and number of an answer must appear in the consulted cards (catches facts from the model's memory). Candidate for the output guardrail. | — |
| `tools/corpus_tools.py` | The agent's tools. `search_cards`: up to 5 results, one per card, each headed by its `[document_id]` (the only bracketed text: card-internal references become parentheses); the first 2 are whole cards; an optional card-type filter is a preference (the best overall result is always kept). `read_card`: a whole card. Errors come back as text, never as exceptions. The descriptions state what the corpus covers. | as the Retriever |
| `agent/analyst_agent.py` | `MatchAnalyst`: the datapizza `Agent` (gpt-4o-mini, or the model passed as `model`) with the two tools. `stateless=False` keeps the conversation (chat); `consulted_cards` lists the cards used for the last answer. Client and retriever can be injected (tests use a scripted fake LLM). | key, Docker |
| `agent/prompts.py` | System prompt: greetings without tools; football questions always searched; answers only from passages, each claim cited with `[document_id]`; conflicts reported; "Non lo so" when the cards do not cover it. | — |

`corpus/` and `evaluation/` work on files only (no network); `rag/`, `tools/` and `agent/` talk to external services.
Commands that use these modules are in `scripts/` (see the main README).

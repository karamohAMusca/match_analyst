# `src/` — what each file does

```
corpus/*.md ──► corpus/cards.py ──► corpus/chunking.py ──► rag/ingest.py ──► Qdrant
  (cards)        read cards          one chunk per ##       embed + store     (Docker)
                                                                                 │
user question ──► agent/analyst_agent.py ──► rag/retrieval.py: Retriever ◄───────┘
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
| `agent/analyst_agent.py` | The datapizza `Agent` (gpt-4o-mini) that answers the coach. Retrieval tool not connected yet. | key |
| `agent/prompts.py` | System prompt of the agent. **Outdated: to be rewritten together with the retrieval tool.** | — |

`corpus/` and `evaluation/` work on files only (no network); `rag/` and `agent/` talk to external services.
Commands that use these modules are in `scripts/` (see the main README).

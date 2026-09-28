"""Ingest the card corpus into Qdrant (Docker) with OpenAI embeddings.

    python -m scripts.ingest --dry-run          # offline preview: chunks and cost estimate
    python -m scripts.ingest                    # sync: embed only new or changed cards
    python -m scripts.ingest --reset            # drop the collection and rebuild it
    python -m scripts.ingest --query "..."      # after the sync, run one retrieval check

Needs Qdrant running (`docker compose up -d`) and OPENAI_API_KEY in .env, except with --dry-run.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from src.core.config import load_settings
from src.corpus.cards import load_manifest_cards, stale_cards
from src.corpus.chunking import chunk_card
from src.rag.ingest import sync_corpus
from src.rag.retrieval import Retriever
from src.rag.store import embedding_dimensions, make_embedder, make_vector_store

PRICE_PER_MILLION_TOKENS = 0.02  # text-embedding-3-small, USD (course price list, Aug 2026)


def preview(cards) -> None:
    chunks = [chunk for card in cards for chunk in chunk_card(card)]
    chars = sum(len(c.text) for c in chunks)
    tokens = chars / 4  # rough estimate for Italian text
    per_category = Counter(c.metadata["category"] for c in chunks)
    print(f"{len(cards)} cards -> {len(chunks)} chunks, {chars} characters (~{tokens:,.0f} tokens)")
    for category, n in sorted(per_category.items()):
        print(f"  {category:15} {n:3} chunks")
    print(f"  longest chunk: {max(len(c.text) for c in chunks)} chars, "
          f"shortest: {min(len(c.text) for c in chunks)} chars")
    print(f"Estimated embedding cost for a full ingestion: ~${tokens / 1e6 * PRICE_PER_MILLION_TOKENS:.4f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="preview chunks only (no API key, no Qdrant)")
    parser.add_argument("--reset", action="store_true", help="drop and rebuild the collection")
    parser.add_argument("--query", help="retrieval check after the sync")
    parser.add_argument("--k", type=int, default=5, help="chunks returned by --query (default 5)")
    args = parser.parse_args()

    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    cards = load_manifest_cards()
    stale = stale_cards(cards)
    if stale:
        print(f"The manifest is out of date for {stale}. Run: python -m scripts.build_manifest")
        return 1

    preview(cards)
    if args.dry_run:
        return 0

    settings = load_settings()
    try:
        store = make_vector_store(settings)
        embedder = make_embedder(settings)
    except (RuntimeError, ValueError) as e:
        print(f"\n{e}")
        return 1

    print(f"\nSyncing into Qdrant {settings.qdrant_host}:{settings.qdrant_port}, "
          f"collection '{settings.qdrant_collection}', model {settings.embedding_model} ...")
    report = sync_corpus(
        store,
        embedder,
        cards,
        collection=settings.qdrant_collection,
        dimensions=embedding_dimensions(settings.embedding_model),
        embedding_model=settings.embedding_model,
        reset=args.reset,
    )
    print(f"  added: {len(report.added)}  updated: {len(report.updated)}  "
          f"removed: {len(report.removed)}  unchanged: {len(report.unchanged)}")
    print(f"  chunks embedded now: {report.embedded_chunks}  points in the collection: {report.total_points}")

    if args.query:
        print(f"\nTop {args.k} chunks for: {args.query}  (hybrid: dense + BM25)")
        retriever = Retriever(store, embedder, settings.qdrant_collection)
        for i, chunk in enumerate(retriever.retrieve(args.query, k=args.k), 1):
            md = chunk.metadata
            print(f"  {i}. {md['document_id']}  [{md['section']}]  "
                  f"dense {md.get('dense_score', 0):.3f}  bm25 {md.get('bm25_score', 0):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

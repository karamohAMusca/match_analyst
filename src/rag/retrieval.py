"""Hybrid retrieval: dense (Qdrant) + lexical (BM25), fused into one ranking.

Same architecture as the course (lesson 9, "Hybrid Search"): dense search understands
paraphrases and English questions; BM25 catches exact terms ("falso terzino", "palla coperta",
"4-4-2") that dense embeddings blur.

Fusion: the default is `interleave` (1st dense, 1st BM25, 2nd dense, ...), not the course's RRF.
Measured on the gold set (eval/runs/retrieval_20260928-154042.json): RRF rewards chunks found by
both searches and buries a chunk that only one search ranks first ("falso terzino": BM25 1st,
8th after RRF). Interleave keeps the best hit of each search and has no parameter to tune:
recall@5 0.95 vs 0.90, MRR@10 0.84 vs 0.80. RRF stays available for comparison.
After fusion, at most `max_per_card` chunks per card are kept, so one card cannot fill the context.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from datapizza.core.embedder import BaseEmbedder
from datapizza.type import Chunk
from datapizza.vectorstores.qdrant import QdrantVectorstore
from rank_bm25 import BM25Okapi

from src.rag.store import search_vector

Mode = Literal["dense", "bm25", "hybrid"]
Fusion = Literal["rrf", "interleave"]

# At most this many chunks from the same card in one result list, so one card cannot fill the
# context. Measured on the gold set (eval/runs/retrieval_20260928-153546.json and -154042.json):
# with hybrid retrieval, 1 per card beats 2 per card on every metric.
DEFAULT_MAX_PER_CARD = 1
RRF_K0 = 60   # standard RRF constant, as in the course
POOL = 20     # candidates taken from each ranking before fusion

# Words present in almost every chunk: they add noise to BM25 without discriminating.
STOPWORDS = frozenset(
    """il lo la i gli le un uno una di a da in con su per tra fra e o ma se che chi cui non si ci
    ne del dello della dei degli delle al allo alla ai agli alle dal dallo dalla dai dagli dalle
    nel nello nella nei negli nelle sul sullo sulla sui sugli sulle come cosa quale quali quando
    dove perche piu anche sono ha hanno essere questo questa quello quella the an of to and in is
    are does do which what how my our with it for on by""".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase, strip accents, keep tokens like 4-4-2 or 3+1 pieces; drop stopwords."""
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return [t for t in re.findall(r"[a-z0-9][a-z0-9\-_/.]*", text) if t not in STOPWORDS]


def diversify(chunks: list[Chunk], k: int, max_per_card: int | None) -> list[Chunk]:
    """Keep the ranking order but at most `max_per_card` chunks per card; `None` = no limit."""
    if not max_per_card:
        return chunks[:k]
    kept: list[Chunk] = []
    per_card: dict[str, int] = {}
    for chunk in chunks:
        card = chunk.metadata["document_id"]
        if per_card.get(card, 0) < max_per_card:
            kept.append(chunk)
            per_card[card] = per_card.get(card, 0) + 1
            if len(kept) == k:
                break
    return kept


class Retriever:
    """Search the card corpus. Build once (it loads the chunks from Qdrant for BM25), then reuse."""

    def __init__(self, store: QdrantVectorstore, embedder: BaseEmbedder, collection: str) -> None:
        self.store = store
        self.embedder = embedder
        self.collection = collection
        self.chunks = [
            Chunk(id=str(c.id), text=c.text, metadata={k: v for k, v in c.metadata.items() if k != "text"})
            for c in store.dump_collection(collection)
        ]
        self.bm25 = BM25Okapi([tokenize(c.text) for c in self.chunks]) if self.chunks else None

    def card_text(self, document_id: str) -> str | None:
        """Whole card rebuilt from its chunks (title once, sections in order); None if unknown."""
        parts = sorted(
            (c for c in self.chunks if c.metadata["document_id"] == document_id),
            key=lambda c: c.metadata["chunk_index"],
        )
        if not parts:
            return None
        title = parts[0].metadata["title"]
        sections = [c.text.removeprefix(f"{title}\n\n") for c in parts]
        return f"{title}\n\n" + "\n\n".join(sections)

    def lexical(self, query: str, pool: int = POOL, categories: list[str] | None = None) -> list[Chunk]:
        """BM25 ranking over the chunks (category filter applied in Python)."""
        if not self.bm25:
            return []
        scores = self.bm25.get_scores(tokenize(query))
        order = sorted(range(len(self.chunks)), key=lambda i: scores[i], reverse=True)
        hits = []
        for i in order:
            if scores[i] <= 0:
                break
            chunk = self.chunks[i]
            if categories and chunk.metadata["category"] not in categories:
                continue
            hits.append(Chunk(id=chunk.id, text=chunk.text, metadata={**chunk.metadata, "bm25_score": float(scores[i])}))
            if len(hits) == pool:
                break
        return hits

    def retrieve(
        self,
        query: str,
        k: int = 5,
        mode: Mode = "hybrid",
        categories: list[str] | None = None,
        max_per_card: int | None = DEFAULT_MAX_PER_CARD,
        vector: list[float] | None = None,
        fusion: Fusion = "interleave",
    ) -> list[Chunk]:
        """Top-k chunks for `query`; `metadata["score"]` is the score used for the ranking.

        `vector` lets the caller pass an already-computed query embedding (e.g. batch evaluation).
        `fusion` only matters in hybrid mode (compared in scripts/eval_retrieval.py).
        """
        dense: list[Chunk] = []
        if mode in ("dense", "hybrid"):
            vector = vector if vector is not None else self.embedder.embed(query)
            dense = search_vector(self.store, vector, self.collection, k=POOL, categories=categories)
            for chunk in dense:
                chunk.metadata["dense_score"] = chunk.metadata["score"]
        lexical = self.lexical(query, POOL, categories) if mode in ("bm25", "hybrid") else []

        if mode == "dense":
            ranked = dense
        elif mode == "bm25":
            ranked = [Chunk(id=c.id, text=c.text, metadata={**c.metadata, "score": c.metadata["bm25_score"]})
                      for c in lexical]
        elif fusion == "interleave":
            ranked = interleave([dense, lexical])
        else:
            ranked = rrf_fuse([dense, lexical])
        return diversify(ranked, k, max_per_card)


def interleave(rankings: list[list[Chunk]]) -> list[Chunk]:
    """Alternate the rankings (1st dense, 1st BM25, 2nd dense, ...), skipping repeats.

    Unlike RRF, the best hit of each search is always kept, even when the other search misses it.
    """
    merged: dict[str, Chunk] = {}
    for position in range(max((len(r) for r in rankings), default=0)):
        for ranking in rankings:
            if position < len(ranking):
                chunk = ranking[position]
                if chunk.id in merged:
                    merged[chunk.id].metadata.update(chunk.metadata)
                else:
                    merged[chunk.id] = Chunk(id=chunk.id, text=chunk.text, metadata=dict(chunk.metadata))
    ordered = list(merged.values())
    for rank, chunk in enumerate(ordered):
        chunk.metadata["score"] = 1.0 / (rank + 1)
    return ordered


def rrf_fuse(rankings: list[list[Chunk]], k0: int = RRF_K0) -> list[Chunk]:
    """Reciprocal Rank Fusion: score(chunk) = sum over rankings of 1 / (k0 + rank)."""
    fused: dict[str, float] = {}
    merged: dict[str, Chunk] = {}
    for ranking in rankings:
        for rank, chunk in enumerate(ranking):
            fused[chunk.id] = fused.get(chunk.id, 0.0) + 1.0 / (k0 + rank)
            if chunk.id in merged:
                merged[chunk.id].metadata.update(chunk.metadata)   # keep dense_score and bm25_score
            else:
                merged[chunk.id] = Chunk(id=chunk.id, text=chunk.text, metadata=dict(chunk.metadata))
    order = sorted(fused, key=fused.get, reverse=True)
    for chunk_id in order:
        merged[chunk_id].metadata["score"] = fused[chunk_id]
    return [merged[chunk_id] for chunk_id in order]

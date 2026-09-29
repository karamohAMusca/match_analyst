"""Hybrid retrieval: dense (Qdrant) + lexical (BM25), fused into one ranking.

Hybrid search: dense search understands
paraphrases and English questions; BM25 catches exact terms ("falso terzino", "palla coperta",
"4-4-2") that dense embeddings blur.

Fusion: the default is `interleave` (1st dense, 1st BM25, 2nd dense, ...), not RRF.
Measured on the gold set (eval/runs/retrieval_20260928-154042.json): RRF rewards chunks found by
both searches and buries a chunk that only one search ranks first ("falso terzino": BM25 1st,
8th after RRF). Interleave keeps the best hit of each search and has no parameter to tune:
recall@5 0.95 vs 0.90, MRR@10 0.84 vs 0.80. RRF stays available for comparison.
After fusion, at most `max_per_card` chunks per card are kept, so one card cannot fill the context.

The steps are nodes of a datapizza `DagPipeline`, one pipeline per mode, built once:

    hybrid:  embedder -> dense --\
                                  +-> fusion -> diversify
             bm25 ---------------/
    dense:   embedder -> dense -> diversify
    bm25:    bm25 -> diversify

With a query vector already computed, the pipeline starts at `dense` (no embedder node).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

from datapizza.core.embedder import BaseEmbedder
from datapizza.pipeline import DagPipeline
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
RRF_K0 = 60   # standard RRF constant
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
        self.pipelines: dict[tuple[Mode, bool], DagPipeline] = {}

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
        """BM25 ranking over the chunks (category filter applied in Python); the `bm25` node."""
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
            score = float(scores[i])
            hits.append(Chunk(id=chunk.id, text=chunk.text,
                              metadata={**chunk.metadata, "bm25_score": score, "score": score}))
            if len(hits) == pool:
                break
        return hits

    def dense(self, vector: list[float], pool: int = POOL, categories: list[str] | None = None) -> list[Chunk]:
        """Dense ranking from Qdrant, with the similarity also kept as `dense_score`; the `dense` node."""
        hits = search_vector(self.store, vector, self.collection, k=pool, categories=categories)
        for chunk in hits:
            chunk.metadata["dense_score"] = chunk.metadata["score"]
        return hits

    def pipeline(self, mode: Mode, embed: bool = True) -> DagPipeline:
        """The retrieval DAG of `mode` (see the module docstring), built on first use.
        `embed=False`: no embedder node, the query vector is given to `dense`."""
        key = (mode, embed)
        if key in self.pipelines:
            return self.pipelines[key]
        dag = DagPipeline()
        if mode in ("dense", "hybrid"):
            if embed:
                dag.add_module("embedder", self.embedder)
                dag.connect("embedder", "dense", target_key="vector")
            dag.add_module("dense", self.dense)
        if mode in ("bm25", "hybrid"):
            dag.add_module("bm25", self.lexical)
        dag.add_module("diversify", diversify)
        if mode == "hybrid":
            dag.add_module("fusion", fuse)
            dag.connect("dense", "fusion", target_key="dense")
            dag.connect("bm25", "fusion", target_key="lexical")
            dag.connect("fusion", "diversify", target_key="chunks")
        else:
            dag.connect("dense" if mode == "dense" else "bm25", "diversify", target_key="chunks")
        self.pipelines[key] = dag
        return dag

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
        inputs: dict[str, dict] = {
            "dense": {"categories": categories} | ({} if vector is None else {"vector": vector}),
            "bm25": {"query": query, "categories": categories},
            "embedder": {"text": query},
            "fusion": {"method": fusion},
            "diversify": {"k": k, "max_per_card": max_per_card},
        }
        return self.pipeline(mode, embed=vector is None).run(inputs)["diversify"]


def fuse(dense: list[Chunk], lexical: list[Chunk], method: Fusion = "interleave") -> list[Chunk]:
    """The `fusion` node of the hybrid pipeline: the dense and BM25 rankings merged into one."""
    return interleave([dense, lexical]) if method == "interleave" else rrf_fuse([dense, lexical])


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

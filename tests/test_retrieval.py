"""Retrieval (dense, BM25, hybrid RRF, per-card limit) and retrieval metrics — offline."""

from __future__ import annotations

from collections import Counter

import pytest
from datapizza.type import Chunk
from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.cards import load_cards
from src.evaluation.retrieval_metrics import load_retrieval_cases, question_metrics, summarize
from src.rag.embedding_cache import CachedEmbedder
from src.rag.ingest import sync_corpus
from src.rag.retrieval import Retriever, diversify, interleave, rrf_fuse, tokenize
from tests.fakes import COLLECTION, DIM, MODEL, FakeEmbedder

QUERY = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


@pytest.fixture(scope="module")
def retriever():
    store = QdrantVectorstore(location=":memory:")
    embedder = FakeEmbedder()
    sync_corpus(store, embedder, load_cards(), COLLECTION, DIM, MODEL)
    return Retriever(store, embedder, COLLECTION)


def test_bm25_index_covers_every_chunk(retriever):
    assert len(retriever.chunks) == retriever.store.get_client().count(COLLECTION).count
    assert all("text" not in c.metadata for c in retriever.chunks)


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_modes_find_the_right_card(retriever, mode):
    hits = retriever.retrieve(QUERY, k=5, mode=mode)
    assert hits[0].metadata["document_id"] == "coach_pioli"
    scores = [h.metadata["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_bm25_catches_exact_terms(retriever):
    hits = retriever.retrieve("falso terzino Lahm", k=3, mode="bm25")
    assert hits[0].metadata["document_id"] == "coach_guardiola"


def test_hybrid_keeps_both_scores(retriever):
    hits = retriever.retrieve(QUERY, k=5, mode="hybrid")
    top = hits[0].metadata
    assert "dense_score" in top and "bm25_score" in top


@pytest.mark.parametrize("max_per_card", [1, 2, 3])
def test_per_card_limit(retriever, max_per_card):
    hits = retriever.retrieve(QUERY, k=10, max_per_card=max_per_card)
    assert len(hits) == 10
    assert max(Counter(h.metadata["document_id"] for h in hits).values()) <= max_per_card


@pytest.mark.parametrize("mode", ["dense", "bm25", "hybrid"])
def test_category_filter(retriever, mode):
    hits = retriever.retrieve("pressing alto e contropiede nella finale", k=5, mode=mode, categories=["match_case"])
    assert hits and all(h.metadata["category"] == "match_case" for h in hits)


def test_bm25_returns_nothing_without_common_words(retriever):
    # Keyword search must not invent matches: no match card talks about the Chievo youth team.
    assert retriever.retrieve(QUERY, k=5, mode="bm25", categories=["match_case"]) == []


def test_precomputed_vector_skips_embedding(retriever):
    vector = retriever.embedder.embed(QUERY)
    calls = retriever.embedder.calls
    retriever.retrieve(QUERY, k=5, vector=vector)
    assert retriever.embedder.calls == calls


def test_tokenize():
    assert tokenize("La superiorità numerica nel 4-4-2 del Chievo") == ["superiorita", "numerica", "4-4-2", "chievo"]


def chunk(chunk_id: str, card: str) -> Chunk:
    return Chunk(id=chunk_id, text="", metadata={"document_id": card})


def test_rrf_rewards_agreement():
    dense = [chunk("a", "A"), chunk("b", "B"), chunk("c", "C")]
    lexical = [chunk("c", "C"), chunk("b", "B"), chunk("d", "D")]
    fused = rrf_fuse([dense, lexical])
    assert {c.id for c in fused[:2]} == {"b", "c"}      # found by both searches -> first
    assert {c.id for c in fused} == {"a", "b", "c", "d"}


def test_rrf_buries_a_hit_found_by_one_search_only():
    # Why interleave is the default: with RRF (k0=60) a chunk 3rd in both searches beats
    # the chunk that one search ranks 1st; interleave keeps both first places.
    dense = [chunk("x", "X"), chunk("y", "Y"), chunk("a", "A")]
    lexical = [chunk("t", "T"), chunk("z", "Z"), chunk("a", "A")]
    assert rrf_fuse([dense, lexical])[0].id == "a"
    assert [c.id for c in interleave([dense, lexical])][:2] == ["x", "t"]


def test_interleave_keeps_the_best_of_each_search():
    dense = [chunk("a", "A"), chunk("b", "B"), chunk("c", "C")]
    lexical = [chunk("t", "T"), chunk("a", "A"), chunk("d", "D")]
    assert [c.id for c in interleave([dense, lexical])] == ["a", "t", "b", "c", "d"]


@pytest.mark.parametrize("fusion", ["interleave", "rrf"])
def test_hybrid_fusions_run(retriever, fusion):
    hits = retriever.retrieve(QUERY, k=5, fusion=fusion)
    assert len(hits) == 5 and hits[0].metadata["document_id"] == "coach_pioli"


def test_embedding_cache(tmp_path):
    inner = FakeEmbedder()
    cache = CachedEmbedder(inner, MODEL, tmp_path / "cache.json")
    first = cache.embed(["uno", "due", "uno"])
    assert inner.calls == 1 and cache.new_texts == 2          # one call, duplicates embedded once
    assert cache.embed("due") == first[1] and inner.calls == 1  # served from memory
    offline = CachedEmbedder(None, MODEL, tmp_path / "cache.json")
    assert offline.embed(["uno", "due"]) == first[:2]           # served from disk, no embedder
    with pytest.raises(LookupError):
        offline.embed("tre")


def test_diversify_keeps_order():
    chunks = [chunk(str(i), d) for i, d in enumerate("AAABBC")]
    assert [c.id for c in diversify(chunks, k=4, max_per_card=2)] == ["0", "1", "3", "4"]


CASE = {"relevant_sources": ["a", "b"], "distractor_sources": ["x"]}


def test_metrics_first_relevant_card():
    m = question_metrics(["c", "a", "a", "x", "d", "b"], CASE)
    assert m["rank"] == 2 and not m["hit@1"] and m["hit@5"]
    assert m["reciprocal_rank"] == 0.5
    assert not m["all_relevant@5"] and m["relevant_found@5"] == 0.5   # "b" is 6th
    assert m["distractor@5"] is True
    assert m["cards@5"] == 4


def test_metrics_miss_and_summary():
    miss = question_metrics(["c", "d"], CASE)
    assert miss["rank"] is None and miss["reciprocal_rank"] == 0.0
    s = summarize([miss, question_metrics(["a", "b"], CASE)])
    assert s["recall@1"] == 0.5 and s["MRR@10"] == 0.5 and s["all_relevant@5"] == 0.5


def test_retrieval_cases_are_the_answerable_gold_questions():
    cases = load_retrieval_cases()
    assert cases and all(c["relevant_sources"] for c in cases)
    assert not {c["type"] for c in cases} & {"off_topic", "chitchat"}

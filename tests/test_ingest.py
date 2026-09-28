"""Incremental ingestion and search, with an in-memory Qdrant and a fake embedder.

No API key, no Docker, no network: the fake embedder turns text into a deterministic
bag-of-words vector, enough to test the sync logic and the category filter.
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil

import pytest
from datapizza.core.embedder import BaseEmbedder
from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.chunking import chunk_card
from src.corpus.cards import load_cards, parse_card
from src.rag.ingest import sync_corpus
from src.rag.store import ensure_collection, search

DIM = 64
MODEL = "fake-embedding"
COLLECTION = "test_cards"


class FakeEmbedder(BaseEmbedder):
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


def sync(store, embedder, cards, **kwargs):
    return sync_corpus(store, embedder, cards, COLLECTION, DIM, MODEL, **kwargs)


@pytest.fixture
def store():
    return QdrantVectorstore(location=":memory:")


def test_full_corpus_ingestion(store):
    cards = load_cards()
    report = sync(store, FakeEmbedder(), cards)
    expected = sum(len(chunk_card(card)) for card in cards)
    assert len(report.added) == len(cards)
    assert report.embedded_chunks == report.total_points == expected


def test_second_run_embeds_nothing(store):
    cards = load_cards()
    sync(store, FakeEmbedder(), cards)
    embedder = FakeEmbedder()
    report = sync(store, embedder, cards)
    assert len(report.unchanged) == len(cards)
    assert report.embedded_chunks == 0 and embedder.calls == 0


def test_changed_and_removed_cards(store, tmp_path):
    originals = [c for c in load_cards() if c.document_id in {"coach_conte", "coach_pioli", "glossary_moduli"}]
    paths = []
    for card in originals:
        target = tmp_path / card.path.name
        shutil.copy(card.path, target)
        paths.append(target)
    cards = [parse_card(p) for p in paths]
    sync(store, FakeEmbedder(), cards)

    # Edit one card and drop another.
    conte = tmp_path / "conte.md"
    conte.write_text(
        conte.read_text(encoding="utf-8") + "\n## Nuova sezione di prova\n" + "testo aggiunto " * 20 + "\n",
        encoding="utf-8",
    )
    cards = [parse_card(conte), parse_card(tmp_path / "pioli.md")]
    report = sync(store, FakeEmbedder(), cards)

    assert report.updated == ["coach_conte"]
    assert report.removed == ["glossary_moduli"]
    assert report.unchanged == ["coach_pioli"]
    stored = list(store.dump_collection(COLLECTION))
    assert {c.metadata["document_id"] for c in stored} == {"coach_conte", "coach_pioli"}
    assert report.total_points == sum(len(chunk_card(c)) for c in cards)
    assert any("Nuova sezione di prova" in c.text for c in stored)


def test_reset_rebuilds_everything(store):
    cards = load_cards()[:3]
    sync(store, FakeEmbedder(), cards)
    report = sync(store, FakeEmbedder(), cards, reset=True)
    assert len(report.added) == 3 and not report.unchanged


def test_model_change_triggers_reembedding(store):
    cards = load_cards()[:2]
    sync(store, FakeEmbedder(), cards)
    report = sync_corpus(store, FakeEmbedder(), cards, COLLECTION, DIM, "another-model")
    assert len(report.updated) == 2


def test_dimension_mismatch_is_refused(store):
    ensure_collection(store, COLLECTION, DIM)
    with pytest.raises(RuntimeError, match="--reset"):
        ensure_collection(store, COLLECTION, DIM * 2)


def test_search_and_category_filter(store):
    embedder = FakeEmbedder()
    sync(store, embedder, load_cards())
    query = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"
    hits = search(store, embedder, query, COLLECTION, k=3)
    assert hits and hits[0].metadata["document_id"] == "coach_pioli"
    only_cases = search(store, embedder, query, COLLECTION, k=5, categories=["match_case"])
    assert only_cases and all(h.metadata["category"] == "match_case" for h in only_cases)

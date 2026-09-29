"""Incremental ingestion into an in-memory Qdrant with a fake embedder (no key, no network)."""

from __future__ import annotations

import shutil

import pytest
from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.cards import load_cards, parse_card
from src.corpus.chunking import chunk_card
from src.rag.ingest import stored_versions, sync_corpus
from src.rag.store import ensure_collection
from tests.fakes import COLLECTION, DIM, MODEL, FakeEmbedder


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


def test_versions_of_a_missing_collection_are_empty(store):
    assert stored_versions(store, "no_such_collection") == {}   # first sync: everything is new

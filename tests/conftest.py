"""Shared fixtures: the whole card corpus indexed in an in-memory Qdrant with a fake embedder."""

from __future__ import annotations

import pytest
from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.cards import load_cards
from src.rag.ingest import sync_corpus
from src.rag.retrieval import Retriever
from tests.fakes import COLLECTION, DIM, MODEL, FakeEmbedder


@pytest.fixture(scope="session")
def retriever() -> Retriever:
    store = QdrantVectorstore(location=":memory:")
    embedder = FakeEmbedder()
    sync_corpus(store, embedder, load_cards(), COLLECTION, DIM, MODEL)
    return Retriever(store, embedder, COLLECTION)

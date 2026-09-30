"""Shared fixtures: the whole card corpus indexed in an in-memory Qdrant with a fake embedder; the
chats and the log written by the tests in temporary folders."""

from __future__ import annotations

import logging

import pytest
from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.cards import load_cards
from src.observability.logs import CONSOLE_HANDLER, FILE_HANDLER
from src.rag.ingest import sync_corpus
from src.rag.retrieval import Retriever
from tests.fakes import COLLECTION, DIM, MODEL, FakeEmbedder


@pytest.fixture(autouse=True)
def chats_dir(tmp_path, monkeypatch):
    """Chats saved by the tests go to a temporary folder, never to the project's chats/."""
    folder = tmp_path / "chats"
    monkeypatch.setattr("src.core.config.CHATS_DIR", folder)
    return folder


@pytest.fixture(autouse=True)
def logs_dir(tmp_path, monkeypatch):
    """The project's log written by the tests goes to a temporary folder, never to logs/."""
    folder = tmp_path / "logs"
    monkeypatch.setattr("src.core.config.LOGS_DIR", folder)
    yield folder
    logger = logging.getLogger("src")
    for handler in [h for h in logger.handlers if h.get_name() in (FILE_HANDLER, CONSOLE_HANDLER)]:
        logger.removeHandler(handler)
        handler.close()


@pytest.fixture(scope="session")
def retriever() -> Retriever:
    store = QdrantVectorstore(location=":memory:")
    embedder = FakeEmbedder()
    sync_corpus(store, embedder, load_cards(), COLLECTION, DIM, MODEL)
    return Retriever(store, embedder, COLLECTION)

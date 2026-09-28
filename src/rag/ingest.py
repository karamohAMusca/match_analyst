"""Sync the card corpus into Qdrant with a datapizza IngestionPipeline.

Pipeline: CardChunker (card -> section chunks) -> ChunkEmbedder -> QdrantVectorstore.

The sync is incremental: every chunk stores the SHA-256 of its card and the embedding model,
so only new or changed cards are embedded again, and chunks of deleted cards are removed.
`reset=True` drops the collection and rebuilds it from scratch.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from datapizza.core.embedder import BaseEmbedder
from datapizza.embedders import ChunkEmbedder
from datapizza.pipeline import IngestionPipeline
from datapizza.vectorstores.qdrant import QdrantVectorstore
from qdrant_client import models

from src.corpus.cards import Card
from src.corpus.chunking import CardChunker, chunk_card
from src.rag.store import EMBEDDING_NAME, ensure_collection


@dataclass
class IngestReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    embedded_chunks: int = 0
    total_points: int = 0


def stored_versions(store: QdrantVectorstore, collection: str) -> dict[str, set[tuple[str, str]]]:
    """document_id -> {(card_sha256, embedding_model)} for the chunks already in the collection."""
    versions: dict[str, set[tuple[str, str]]] = defaultdict(set)
    if not store.get_client().collection_exists(collection):
        return versions
    for chunk in store.dump_collection(collection):
        md = chunk.metadata
        versions[md["document_id"]].add((md.get("card_sha256"), md.get("embedding_model")))
    return versions


def delete_documents(store: QdrantVectorstore, collection: str, document_ids: list[str]) -> None:
    if not document_ids:
        return
    store.get_client().delete(
        collection_name=collection,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[models.FieldCondition(key="document_id", match=models.MatchAny(any=document_ids))]
            )
        ),
    )


def sync_corpus(
    store: QdrantVectorstore,
    embedder: BaseEmbedder,
    cards: list[Card],
    collection: str,
    dimensions: int,
    embedding_model: str,
    reset: bool = False,
) -> IngestReport:
    """Make the collection match `cards`, embedding only what changed."""
    client = store.get_client()
    if reset and client.collection_exists(collection):
        store.delete_collection(collection)
    ensure_collection(store, collection, dimensions)

    stored = stored_versions(store, collection)
    current = {card.document_id for card in cards}
    report = IngestReport()

    to_embed: list[Card] = []
    for card in cards:
        if stored.get(card.document_id) == {(card.sha256, embedding_model)}:
            report.unchanged.append(card.document_id)
        else:
            (report.updated if card.document_id in stored else report.added).append(card.document_id)
            to_embed.append(card)
    report.removed = sorted(d for d in stored if d not in current)

    # Old chunks of changed cards go too: a card may now have fewer sections than before.
    delete_documents(store, collection, report.removed + report.updated)

    if to_embed:
        pipeline = IngestionPipeline(
            modules=[CardChunker(), ChunkEmbedder(client=embedder, embedding_name=EMBEDDING_NAME)],
            vector_store=store,
            collection_name=collection,
        )
        pipeline.run(
            file_path=[str(card.path) for card in to_embed],
            metadata={"embedding_model": embedding_model},
        )
        report.embedded_chunks = sum(len(chunk_card(card)) for card in to_embed)

    report.total_points = client.count(collection_name=collection, exact=True).count
    return report

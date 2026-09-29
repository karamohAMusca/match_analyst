"""Qdrant vector store, OpenAI embedder and similarity search (datapizza-ai components).

Qdrant runs as a Docker service (see docker-compose.yml): the index survives
restarts, so the corpus is ingested once and re-synced only when cards change.
"""

from __future__ import annotations

from datapizza.core.vectorstore import VectorConfig
from datapizza.embedders.openai import OpenAIEmbedder
from datapizza.type import Chunk
from datapizza.vectorstores.qdrant import QdrantVectorstore
from qdrant_client import models

from src.core.config import Settings, load_settings, require_api_key

EMBEDDING_NAME = "content_embedding"   # must match in VectorConfig, ChunkEmbedder and search
EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def embedding_dimensions(model: str) -> int:
    try:
        return EMBEDDING_DIMENSIONS[model]
    except KeyError:
        raise ValueError(
            f"Unknown embedding model '{model}': add its vector size to EMBEDDING_DIMENSIONS."
        ) from None


def make_vector_store(settings: Settings | None = None) -> QdrantVectorstore:
    """Connect to the Qdrant Docker service and fail fast with a clear message if it is down."""
    settings = settings or load_settings()
    # The Qdrant server is pinned at v1.11 while the installed client is newer: the calls
    # used here (collections, upsert, query_points, scroll, delete by filter) all exist in v1.11,
    # so the client's version warning is disabled instead of being printed at every run.
    store = QdrantVectorstore(
        host=settings.qdrant_host, port=settings.qdrant_port, check_compatibility=False
    )
    try:
        store.get_client().get_collections()
    except Exception as e:  # connection refused, timeout, ...
        raise RuntimeError(
            f"Qdrant is not reachable on {settings.qdrant_host}:{settings.qdrant_port}. "
            "Start it from the project root with: docker compose up -d"
        ) from e
    return store


def make_embedder(settings: Settings | None = None) -> OpenAIEmbedder:
    """OpenAI embedder; reads the API key only here, right before it is needed."""
    settings = settings or load_settings()
    return OpenAIEmbedder(api_key=require_api_key("openai"), model_name=settings.embedding_model)


def ensure_collection(store: QdrantVectorstore, collection: str, dimensions: int) -> None:
    """Create the collection if missing; refuse to reuse one built with another vector size."""
    client = store.get_client()
    if client.collection_exists(collection):
        vectors = client.get_collection(collection).config.params.vectors
        size = vectors[EMBEDDING_NAME].size if isinstance(vectors, dict) and EMBEDDING_NAME in vectors else None
        if size != dimensions:
            raise RuntimeError(
                f"Collection '{collection}' has vector size {size}, expected {dimensions}: "
                "the embedding model changed. Rebuild it with: python -m scripts.ingest --reset"
            )
        return
    store.create_collection(
        collection_name=collection,
        vector_config=[VectorConfig(name=EMBEDDING_NAME, dimensions=dimensions)],
    )


def category_filter(categories: list[str] | None) -> models.Filter | None:
    if not categories:
        return None
    return models.Filter(
        must=[models.FieldCondition(key="category", match=models.MatchAny(any=categories))]
    )


def search_vector(
    store: QdrantVectorstore,
    vector: list[float],
    collection: str,
    k: int = 5,
    categories: list[str] | None = None,
) -> list[Chunk]:
    """Dense search: the `k` chunks nearest to an embedded query, similarity in `metadata["score"]`.

    Queries Qdrant directly instead of `QdrantVectorstore.search`, which drops the score: the
    score is needed to inspect retrieval and is what Phoenix shows for retrieved documents.
    Full retrieval (dense + BM25 + per-card limit) is in `src/rag/retrieval.py`.
    """
    response = store.get_client().query_points(
        collection_name=collection,
        query=vector,
        using=EMBEDDING_NAME,
        limit=k,
        query_filter=category_filter(categories),
        with_payload=True,
    )
    return [
        Chunk(
            id=str(point.id),
            text=point.payload["text"],
            metadata={**{key: v for key, v in point.payload.items() if key != "text"}, "score": point.score},
        )
        for point in response.points
    ]

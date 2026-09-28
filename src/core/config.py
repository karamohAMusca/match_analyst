"""Project configuration: paths and runtime settings read from the environment."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]   # src/core/config.py -> project root
CORPUS_DIR = PROJECT_ROOT / "corpus"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
REFERENCES_DIR = PROJECT_ROOT / "references"
GOLD_SET_PATH = PROJECT_ROOT / "eval" / "gold_set.json"


@dataclass(frozen=True)
class Settings:
    """Runtime settings. Secrets are never read at import time."""

    chat_model: str
    embedding_model: str
    qdrant_host: str
    qdrant_port: int
    qdrant_collection: str
    phoenix_endpoint: str
    phoenix_project: str


def load_settings() -> Settings:
    """Load settings from the project's own `.env` file (never from parent folders)."""
    load_dotenv(PROJECT_ROOT / ".env")
    return Settings(
        chat_model=os.getenv("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        qdrant_host=os.getenv("QDRANT_HOST", "localhost"),
        qdrant_port=int(os.getenv("QDRANT_PORT", "6337")),
        qdrant_collection=os.getenv("QDRANT_COLLECTION", "match_analyst_tactics"),
        phoenix_endpoint=os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006/v1/traces"),
        phoenix_project=os.getenv("PHOENIX_PROJECT_NAME", "match_analyst"),
    )


def require_openai_key() -> str:
    """Return the OpenAI API key, raising a clear error if it is not configured.

    Call this only right before an operation that needs the key (LLM call, embeddings).
    """
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env in the project root and add your key."
        )
    return api_key

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
CACHE_DIR = PROJECT_ROOT / ".cache"   # git-ignored: embeddings and judge verdicts already paid for

# Provider of the agent's model, for datapizza's ClientFactory. The measurements, the price list
# (src/evaluation/cost.py) and the models offered by the app are OpenAI's.
LLM_PROVIDER = "openai"


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


def require_api_key(provider: str) -> str:
    """Return the API key of `provider` (OPENAI_API_KEY for "openai", ANTHROPIC_API_KEY for
    "anthropic", ...), raising a clear error if it is not configured.

    Call this only right before an operation that needs the key (LLM call, embeddings).
    """
    load_dotenv(PROJECT_ROOT / ".env")
    name = f"{provider.upper()}_API_KEY"
    api_key = os.getenv(name)
    if not api_key:
        raise ValueError(f"{name} is not set. Copy .env.example to .env in the project root and add your key.")
    return api_key

"""Read the card corpus: front matter, body and manifest.

Every card in `corpus/<folder>/*.md` starts with a YAML front matter block delimited by `---`.
The front matter holds the metadata (stored as payload in the vector store); the body is the text
that gets embedded.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.config import CORPUS_DIR, MANIFEST_PATH, PROJECT_ROOT

# Folder order used for the manifest (and therefore for document order everywhere).
CARD_FOLDERS: tuple[str, ...] = (
    "match_cases",
    "game_situations",
    "coach_profiles",
    "thesis_notes",
    "glossary",
)
ID_PREFIXES: tuple[str, ...] = ("case_", "situation_", "coach_", "note_", "glossary_")
REQUIRED_FIELDS: tuple[str, ...] = (
    "document_id",
    "title",
    "category",
    "origin_type",
    "modality",
    "reliability",
    "sources",
)
# Card ids referenced inside a body, e.g. "case_2026_wc_final_spain_argentina".
CARD_LINK_RE = re.compile(r"\b(?:case|situation|coach|note|glossary)_[a-z0-9_]+")


@dataclass
class Card:
    """One corpus card."""

    path: Path
    metadata: dict[str, Any]
    body: str
    raw: bytes = field(repr=False)

    @property
    def document_id(self) -> str:
        return self.metadata["document_id"]

    @property
    def relative_path(self) -> str:
        return self.path.relative_to(PROJECT_ROOT).as_posix()

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    def links(self) -> set[str]:
        """Card ids mentioned in the body (cross-references to other cards)."""
        return {ref for ref in CARD_LINK_RE.findall(self.body) if ref != self.document_id}


def _json_safe(value: Any) -> Any:
    """YAML turns `2022-12-18` into a date: keep every value JSON-serialisable."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def parse_card(path: Path) -> Card:
    """Split a card into YAML metadata and Markdown body."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    if not text.startswith("---"):
        raise ValueError(f"{path}: missing front matter")
    _, front_matter, body = text.split("---", 2)
    metadata = _json_safe(yaml.safe_load(front_matter) or {})
    missing = [f for f in REQUIRED_FIELDS if f not in metadata]
    if missing:
        raise ValueError(f"{path}: missing front matter fields {missing}")
    return Card(path=path, metadata=metadata, body=body.strip() + "\n", raw=raw)


def load_cards(corpus_dir: Path = CORPUS_DIR) -> list[Card]:
    """Load every card, in manifest order (folder order, then file name)."""
    cards: list[Card] = []
    for folder in CARD_FOLDERS:
        cards.extend(parse_card(p) for p in sorted((corpus_dir / folder).glob("*.md")))
    return cards


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_manifest_cards(path: Path = MANIFEST_PATH) -> list[Card]:
    """Load only the cards listed in the manifest (the ingestion whitelist)."""
    manifest = load_manifest(path)
    return [
        parse_card(PROJECT_ROOT / record["path"])
        for doc in manifest["documents"]
        for record in doc["file_records"]
    ]

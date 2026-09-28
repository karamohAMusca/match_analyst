"""Split cards into retrieval chunks, one per `##` section.

Cards are short and already structured by topic, so a section is the natural retrieval unit.
Rules:
- the YAML front matter never enters the text: it becomes the chunk payload (metadata);
- every chunk starts with the card title, so a chunk read on its own is still understandable
  ("Profilo allenatore: Antonio Conte — Senza palla ...");
- very short sections are merged into the previous chunk, very long ones are split by paragraph;
- chunk ids are deterministic (same card + same position = same id), so re-ingesting a card
  overwrites its points instead of creating duplicates.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from datapizza.core.models import PipelineComponent
from datapizza.type import Chunk

from src.corpus.cards import Card, parse_card

MIN_SECTION_CHARS = 200    # shorter sections are merged into the previous chunk
MAX_SECTION_CHARS = 1500   # longer sections are split by paragraph
ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "match-analyst/corpus")
INTRO_SECTION = "In breve"

_H1_RE = re.compile(r"\A#\s+[^\n]*\n+")
_H2_RE = re.compile(r"^##\s+(.*)$", re.M)
_CITATION_RE = re.compile(r"\s*\[[^\]]*\]")


def chunk_id(document_id: str, index: int) -> str:
    """Deterministic UUID for the `index`-th chunk of a card (Qdrant accepts UUID strings)."""
    return str(uuid.uuid5(ID_NAMESPACE, f"{document_id}#{index}"))


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Return (section name, section text) pairs; the text keeps its `##` heading line."""
    body = _H1_RE.sub("", body.strip() + "\n", count=1)
    matches = list(_H2_RE.finditer(body))
    sections: list[tuple[str, str]] = []
    intro = body[: matches[0].start()] if matches else body
    if intro.strip():
        sections.append((INTRO_SECTION, intro.strip()))
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        name = _CITATION_RE.sub("", m.group(1)).strip()
        sections.append((name, body[m.start():end].strip()))
    return sections


def _merge_short(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    merged: list[tuple[str, str]] = []
    for name, text in sections:
        if merged and len(text) < MIN_SECTION_CHARS:
            prev_name, prev_text = merged[-1]
            merged[-1] = (prev_name, f"{prev_text}\n\n{text}")
        else:
            merged.append((name, text))
    # A short intro ("Quando capita: ...") says little on its own: attach it to the next section.
    if len(merged) > 1 and len(merged[0][1]) < MIN_SECTION_CHARS:
        (_, intro), (name, text) = merged[0], merged[1]
        merged[:2] = [(name, f"{intro}\n\n{text}")]
    return merged


def _split_long(name: str, text: str) -> list[tuple[str, str]]:
    if len(text) <= MAX_SECTION_CHARS:
        return [(name, text)]
    heading, _, rest = text.partition("\n")
    if not heading.startswith("##"):          # intro section: no heading to repeat
        heading, rest = "", text
    parts: list[str] = []
    current = ""
    for block in re.split(r"\n(?=- |\d+\. |\n)", rest.strip()):
        if current and len(current) + len(block) > MAX_SECTION_CHARS:
            parts.append(current.strip())
            current = ""
        current += "\n" + block
    if current.strip():
        parts.append(current.strip())
    return [(name, f"{heading}\n{part}".strip()) for part in parts]


def _payload(card: Card) -> dict:
    """Metadata stored with every chunk of the card (flat, JSON-safe, filterable)."""
    m = card.metadata
    coaches = [m["coach"]] if m.get("coach") else list((m.get("coaches") or {}).values())
    payload = {
        "document_id": card.document_id,
        "title": m["title"],
        "category": m["category"],
        "source_file": card.relative_path,
        "card_sha256": card.sha256,
        "themes": m.get("themes") or [],
        "coaches": coaches,
    }
    for key in ("phase", "winner", "date"):
        if m.get(key):
            payload[key] = str(m[key])
    return payload


def chunk_card(card: Card) -> list[Chunk]:
    """Split one card into chunks with text, deterministic id and metadata."""
    title = card.metadata["title"]
    base = _payload(card)
    pieces = [p for name, text in _merge_short(_split_sections(card.body)) for p in _split_long(name, text)]
    return [
        Chunk(
            id=chunk_id(card.document_id, i),
            text=f"{title}\n\n{text}",
            metadata={**base, "section": name, "chunk_index": i, "chunk_count": len(pieces)},
        )
        for i, (name, text) in enumerate(pieces)
    ]


class CardChunker(PipelineComponent):
    """datapizza pipeline module: card file path -> list of chunks.

    Replaces the parser + splitter pair of a generic ingestion pipeline: cards are already
    structured, and their front matter must go into the payload, not into the embedded text.
    """

    def _run(self, file_path: str) -> list[Chunk]:
        return chunk_card(parse_card(Path(file_path)))

    async def _a_run(self, file_path: str) -> list[Chunk]:
        return self._run(file_path)

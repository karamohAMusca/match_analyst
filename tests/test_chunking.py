"""Chunking of cards into retrieval units (offline, no API keys)."""

from __future__ import annotations

import pytest

from src.corpus.chunking import MAX_SECTION_CHARS, _split_long, chunk_card, chunk_id
from src.corpus.cards import load_cards, parse_card

CARDS = load_cards()
CHUNKS = {card.document_id: chunk_card(card) for card in CARDS}


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_chunks_start_with_title_and_skip_front_matter(card):
    for chunk in CHUNKS[card.document_id]:
        assert chunk.text.startswith(card.metadata["title"])
        assert "document_id:" not in chunk.text
        assert "reliability:" not in chunk.text


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_no_content_is_lost(card):
    joined = "\n".join(chunk.text for chunk in CHUNKS[card.document_id])
    body_lines = [line.strip() for line in card.body.splitlines()[1:] if line.strip()]  # skip the H1
    missing = [line for line in body_lines if line not in joined]
    assert not missing, missing[:3]


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_chunk_size_is_bounded(card):
    limit = len(card.metadata["title"]) + MAX_SECTION_CHARS + 400  # title + section + merged tail
    for chunk in CHUNKS[card.document_id]:
        assert len(chunk.text) <= limit, (chunk.metadata["section"], len(chunk.text))


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_metadata(card):
    chunks = CHUNKS[card.document_id]
    for i, chunk in enumerate(chunks):
        md = chunk.metadata
        assert md["document_id"] == card.document_id
        assert md["category"] == card.metadata["category"]
        assert md["card_sha256"] == card.sha256
        assert md["source_file"] == card.relative_path
        assert md["chunk_index"] == i and md["chunk_count"] == len(chunks)
        assert md["section"]


def test_ids_are_unique_and_deterministic():
    ids = [chunk.id for chunks in CHUNKS.values() for chunk in chunks]
    assert len(ids) == len(set(ids))
    again = [chunk.id for card in CARDS for chunk in chunk_card(card)]
    assert again == ids
    assert chunk_id("coach_conte", 0) == chunk_id("coach_conte", 0) != chunk_id("coach_conte", 1)


def test_coach_payload():
    conte = CHUNKS["coach_conte"][0].metadata
    assert conte["coaches"] == ["Antonio Conte"]
    final = CHUNKS["case_2026_wc_final_spain_argentina"][0].metadata
    assert "Lionel Scaloni" in final["coaches"]


CARD_TEMPLATE = """---
document_id: note_test
title: "Nota di prova"
category: thesis_note
origin_type: derived
modality: text
reliability: project_synthesis_cited
sources:
  - "Fonte di prova"
---

# Nota di prova

**In breve:** testo introduttivo abbastanza lungo da restare un chunk a sé, perché supera la soglia minima di duecento caratteri prevista per le sezioni che non vengono unite alla precedente [Fonte].

## Sezione corta [Fonte]
Due righe.

{long_section}
"""


def test_short_sections_are_merged_and_long_ones_split(tmp_path):
    bullets = "\n".join(f"- punto numero {i}: " + "parola " * 30 for i in range(20))
    path = tmp_path / "note_test.md"
    path.write_text(CARD_TEMPLATE.format(long_section=f"## Sezione lunga\n{bullets}"), encoding="utf-8")
    chunks = chunk_card(parse_card(path))

    sections = [c.metadata["section"] for c in chunks]
    assert "Sezione corta" not in sections            # merged into the intro chunk
    assert "Due righe." in chunks[0].text
    long_parts = [c for c in chunks if c.metadata["section"] == "Sezione lunga"]
    assert len(long_parts) > 1                         # split by paragraph
    assert all("## Sezione lunga" in c.text for c in long_parts)
    assert all(len(c.text) <= len("Nota di prova") + MAX_SECTION_CHARS + 50 for c in long_parts)


def test_section_at_the_limit_is_kept_whole():
    # A boundary value: a section of exactly MAX_SECTION_CHARS is one chunk, untouched.
    exact = "## Sezione\n" + "a" * (MAX_SECTION_CHARS - len("## Sezione\n"))
    assert len(exact) == MAX_SECTION_CHARS and _split_long("s", exact) == [("s", exact)]


def test_long_intro_without_heading_is_split_without_inventing_one():
    intro = "a" * 1000 + "\n\n" + "b" * 1000               # the text before the first ## heading
    assert _split_long("intro", intro) == [("intro", "a" * 1000), ("intro", "b" * 1000)]

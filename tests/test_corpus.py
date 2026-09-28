"""Structural checks on the card corpus and its manifest (offline, no API keys)."""

from __future__ import annotations

import re

import pytest

from src.core.config import PROJECT_ROOT
from src.corpus.cards import ID_PREFIXES, load_cards, load_manifest, stale_cards

CARDS = load_cards()
MANIFEST = load_manifest()
IDS = {card.document_id for card in CARDS}


def test_document_ids_are_unique():
    ids = [card.document_id for card in CARDS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_id_prefix_matches_category(card):
    prefix_by_category = {
        "match_case": "case_",
        "game_situation": "situation_",
        "coach_profile": "coach_",
        "thesis_note": "note_",
        "glossary": "glossary_",
    }
    assert card.document_id.startswith(ID_PREFIXES)
    assert card.document_id.startswith(prefix_by_category[card.metadata["category"]])


def test_manifest_lists_exactly_the_cards():
    listed = {doc["document_id"] for doc in MANIFEST["documents"]}
    assert listed == IDS, "run `python -m scripts.build_manifest` after adding or removing cards"


def test_manifest_is_up_to_date():
    stale = stale_cards(CARDS)
    assert not stale, f"cards changed since the last manifest build: {stale}"


def test_manifest_paths_exist():
    for doc in MANIFEST["documents"]:
        for rec in doc["file_records"]:
            assert (PROJECT_ROOT / rec["path"]).is_file(), rec["path"]


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_cross_links_resolve(card):
    broken = card.links() - IDS
    assert not broken, f"links to unknown cards: {sorted(broken)}"


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_card_has_sources_and_inline_citations(card):
    assert card.metadata["sources"], "empty sources list"
    assert re.search(r"\[[^\]]+\]", card.body), "no inline citation in the body"


@pytest.mark.parametrize("card", CARDS, ids=lambda c: c.document_id)
def test_card_is_short(card):
    # Single-topic cards: keep them small so one retrieved chunk stays on one subject.
    assert len(card.body) < 4000, f"{len(card.body)} characters: split the card"


def test_psg_coach_is_never_named():
    # No source used by the corpus names the PSG coach: gold question Q21 tests the abstention.
    for card in CARDS:
        assert "luis enrique" not in card.body.lower(), card.document_id

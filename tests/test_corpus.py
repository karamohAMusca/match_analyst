"""Structural checks on the card corpus and its manifest (offline, no API keys)."""

from __future__ import annotations

import re

import pytest

from src.core.config import PROJECT_ROOT
from src.corpus.cards import ID_PREFIXES, load_cards, load_manifest, parse_card, stale_cards

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


def test_cards_have_lf_line_endings():
    # The manifest hashes each card's bytes, and git stores cards with LF (.gitattributes): a card
    # saved with Windows line endings (CRLF, the default of many editors for new files) gets another
    # hash in every clone. Two cards were in this state until the first clean-install check.
    crlf = [c.relative_path for c in CARDS if b"\r\n" in c.raw]
    assert not crlf, f"save these cards with LF line endings, then run python -m scripts.build_manifest: {crlf}"


def test_malformed_card_is_refused_with_a_clear_error(tmp_path):
    no_front_matter = tmp_path / "no_front_matter.md"
    no_front_matter.write_text("# Titolo\n\nTesto.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing front matter$"):
        parse_card(no_front_matter)
    missing_fields = tmp_path / "missing_fields.md"
    missing_fields.write_text("---\ntitle: Titolo\n---\n# Titolo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing front matter fields"):
        parse_card(missing_fields)


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


# ---------------------------------------------------------------- the timeline of a final (front matter)
TITLE_RE = re.compile(r"^Finale [^:]+: (?P<home>.+?) (?P<h>\d+)-(?P<a>\d+) (?P<away>[^(]+?)"
                      r"(?: \((?:(?P<sh>\d+)-(?P<sa>\d+) d\.c\.r\.|d\.t\.s\.)\))?$")
KINDS = {"goal", "penalty", "save", "post", "red", "sub", "shootout"}


@pytest.mark.parametrize("card", [c for c in load_cards() if c.metadata["category"] == "match_case"],
                         ids=lambda c: c.document_id)
def test_the_timeline_is_in_the_card_s_own_words(card):
    """Every event of a final's timeline (drawn under an answer that cites the final) comes from the
    card: its quote is in the text, its names too, its minute is written there (or reached from a
    minute written there: "un minuto dopo", "a tre minuti dalla fine"); the goals add up to the title."""
    timeline = card.metadata.get("timeline")
    assert timeline, "a match card needs its timeline"
    body = re.sub(r"\s+", " ", card.body.replace("**", ""))
    title = TITLE_RE.match(card.metadata["title"])
    assert title, card.metadata["title"]
    home, away = title["home"], title["away"]
    score = [0, 0]
    for event in timeline:
        assert event["kind"] in KINDS and event["team"] in (home, away), event
        assert event["quote"] in body, f"quote not in the card: {event['quote']}"
        for name in filter(None, str(event.get("who", "")).split(", ")):
            assert name in body, f"name not in the card: {name}"
        if event["kind"] == "shootout":
            assert event["score"] == f"{title['sh']}-{title['sa']}", event
            continue
        assert ("minute" in event) != ("period" in event), event   # a minute, or the period when there is none
        if "minute" in event:
            written = re.findall(r"\d+'(?:\+\d+')?", event["quote"])
            shown = event.get("shown", f"{event['minute']}'")
            assert shown in written or not written and re.search(r"dopo|dalla fine|recupero|intervallo", event["quote"]), event
        if event["kind"] in ("goal", "penalty"):
            score[0 if event["team"] == home else 1] += 1
            assert event["score"] == f"{score[0]}-{score[1]}", event        # the score after each goal
    assert score == [int(title["h"]), int(title["a"])], "the goals do not add up to the title"

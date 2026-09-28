"""Consistency of eval/gold_set.json with the card corpus (offline, no API keys)."""

from __future__ import annotations

import json
import re
import unicodedata

import pytest

from src.core.config import GOLD_SET_PATH
from src.corpus.cards import load_cards

TEXT_BY_ID = {card.document_id: card.body for card in load_cards()}
GOLD = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))
QUESTIONS = GOLD["questions"]
SOURCE_FIELDS = ("relevant_sources", "acceptable_sources", "distractor_sources")


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower())


def test_question_ids_are_unique():
    ids = [q["question_id"] for q in QUESTIONS]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["question_id"])
def test_source_ids_exist(q):
    unknown = {s for f in SOURCE_FIELDS for s in q[f]} - TEXT_BY_ID.keys()
    assert not unknown, f"unknown document ids: {sorted(unknown)}"


@pytest.mark.parametrize(
    "q", [q for q in QUESTIONS if q["required_facts"]], ids=lambda q: q["question_id"]
)
def test_required_facts_are_in_relevant_cards(q):
    text = normalize(" ".join(TEXT_BY_ID[s] for s in q["relevant_sources"]))
    missing = [group for group in q["required_facts"] if not any(normalize(a) in text for a in group)]
    assert not missing, f"facts not found in {q['relevant_sources']}: {missing}"


@pytest.mark.parametrize(
    "q", [q for q in QUESTIONS if q.get("paired_with")], ids=lambda q: q["question_id"]
)
def test_paired_question_exists(q):
    assert q["paired_with"] in {x["question_id"] for x in QUESTIONS}


@pytest.mark.parametrize("q", QUESTIONS, ids=lambda q: q["question_id"])
def test_tool_use_matches_type(q):
    no_retrieval = {"off_topic", "chitchat"}
    expected = "none" if q["type"] in no_retrieval else "retrieval"
    assert q["expected_tool_use"] == expected

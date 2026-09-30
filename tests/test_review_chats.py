"""scripts/review_chats.py end to end, offline: a chat made with the scripted fake model and saved
by the app's backend, then checked from its file (no key, no Qdrant)."""

from __future__ import annotations

import json

import pytest

import scripts.review_chats as review_chats
import src.ui.backend as backend
from src.corpus.cards import load_manifest_cards
from tests.fakes import ScriptedLLM

QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


@pytest.fixture
def chat(retriever, monkeypatch):
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    conversation = backend.Conversation("gpt-4o-mini", True, retriever)
    conversation.ask(QUESTION)
    conversation.ask("Mi scrivi la ricetta della carbonara?")
    return conversation.log.path


def test_card_texts_are_the_ones_the_agent_reads(retriever):
    texts = review_chats.card_texts()
    assert len(texts) == len(load_manifest_cards())
    assert all(texts[c] == retriever.card_text(c) for c in texts)


def test_the_last_chat_is_checked_answer_by_answer(chat, capsys):
    assert review_chats.main([]) == 0
    out = capsys.readouterr().out
    assert out.startswith(f"== {chat.name}: 2 answers")
    assert "#1 " in out and "cards: coach_pioli" in out and "#2  OK" in out
    assert "stopped (off_topic)" in out and "Totals: 1 flagged, 1 stopped by the input guard" in out


def test_a_wrong_answer_is_flagged(chat, capsys):
    answers = [json.loads(line) for line in chat.read_text(encoding="utf-8").splitlines()]
    answers[0]["content"] = "Il Real Madrid vinse 7-4 nel 1987 [coach_pioli] [coach_klopp]."   # invented facts
    chat.write_text("".join(json.dumps(a, ensure_ascii=False) + "\n" for a in answers), encoding="utf-8")
    review_chats.main([str(chat)])
    out = capsys.readouterr().out
    assert "#1  CHECK" in out and "cites cards it did not consult: ['coach_klopp']" in out
    assert "names/numbers not in the consulted cards" in out and "Totals: 1 flagged" in out


def test_no_chat_saved_yet(capsys):
    assert review_chats.main(["--all"]) == 1
    assert "No chat saved" in capsys.readouterr().out

"""Saving the app's conversations (chats/): one file per chat, one line per answer, the agent's
memory rebuilt from the file. Offline: the scripted fake model, the chats in a temporary folder."""

from __future__ import annotations

from datetime import datetime

import pytest
from datapizza.type import ROLE

import src.ui.backend as backend
from src.ui.chat_log import ChatLog, load_chat, load_memory
from tests.fakes import ScriptedLLM

QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


@pytest.fixture
def conversation(retriever, monkeypatch):
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    return backend.Conversation("gpt-4o-mini", True, retriever)


def test_every_answer_is_saved_with_what_the_app_showed(conversation, chats_dir):
    first = conversation.ask(QUESTION)
    conversation.ask("Mi scrivi la ricetta della carbonara?")               # blocked: saved too
    assert conversation.log.path.parent == chats_dir
    answers = load_chat(conversation.log.path)
    assert [a["question"] for a in answers] == [QUESTION, "Mi scrivi la ricetta della carbonara?"]
    assert answers[0]["content"] == first["content"] and answers[0]["consulted"] == first["consulted"]
    assert answers[0]["calls"][0]["tool"] == "search_cards" and answers[0]["meta"]["model"] == "gpt-4o-mini"
    assert answers[1]["guard"]["input"] == "off_topic" and "role" not in answers[0]


def test_the_memory_of_the_chat_is_rebuilt_with_tool_calls(conversation):
    conversation.ask(QUESTION)
    conversation.ask("E perché?")
    answers = load_chat(conversation.log.path)
    live = conversation.analyst.agent._memory
    assert [t.role for t in live] == [ROLE.USER, ROLE.ASSISTANT] * 2         # live: questions and answers only
    memory = load_memory(answers)
    assert len(memory) == 8 and memory[0].role == ROLE.USER                    # saved: every turn, twice 4
    call = memory[1].blocks[0]                                                # the search, with its arguments
    assert call.name == "search_cards" and call.arguments == {"query": QUESTION}
    assert [t.to_dict() for t in memory if t.role in (ROLE.USER, ROLE.ASSISTANT) and len(t) == 1
            and t.blocks[0].__class__.__name__ == "TextBlock"] == live.to_dict()   # the same questions and answers


def test_a_new_conversation_gets_its_own_file(chats_dir):
    started = datetime(2026, 9, 30, 15, 30, 12)
    first = ChatLog(started=started)
    first.path.parent.mkdir(parents=True)
    first.path.write_text("", encoding="utf-8")
    assert first.path.name == "2026-09-30_153012.jsonl"
    assert ChatLog(started=started).path.name == "2026-09-30_153012-2.jsonl"  # same second, other file


def test_a_failed_save_does_not_lose_the_answer(conversation, monkeypatch):
    def full_disk(*args):
        raise OSError("disk full")
    monkeypatch.setattr(conversation.log, "append", full_disk)
    message = conversation.ask(QUESTION)
    assert message["consulted"] and message["log_error"] == "disk full"

"""The configuration frozen into every saved answer and run (src/core/build_info.py), offline: the fingerprints
change with the files and only with them, git missing is not an error, and the version reaches the chat's file."""

from __future__ import annotations

import subprocess

import pytest

import src.core.build_info as build_info
import src.ui.backend as backend
from src.agent.analyst_agent import MatchAnalyst
from src.core.build_info import code_version, fingerprint
from src.ui.chat_log import load_chat
from tests.fakes import ScriptedLLM

FIELDS = {"commit", "uncommitted_changes", "prompts", "guardrails_code", "corpus"}


def test_a_fingerprint_changes_with_the_text_and_not_with_the_line_endings(tmp_path):
    prompt = tmp_path / "prompts.py"
    prompt.write_bytes(b"SYSTEM = 'cite the cards'\n")
    first = fingerprint([prompt])
    prompt.write_bytes(b"SYSTEM = 'cite the cards'\r\n")
    assert fingerprint([prompt]) == first and len(first) == 12          # the same on Windows and Linux
    prompt.write_bytes(b"SYSTEM = 'cite the cards, always'\n")
    assert fingerprint([prompt]) != first
    assert fingerprint([tmp_path / "missing.py"]) == "missing"


def test_the_order_of_the_files_does_not_matter(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("x = 1\n", encoding="utf-8")
    b.write_text("y = 2\n", encoding="utf-8")
    assert fingerprint([a, b]) == fingerprint([b, a]) != fingerprint([a])


def test_the_version_of_this_checkout():
    version = code_version()
    assert set(version) == FIELDS
    assert version["prompts"] == fingerprint([build_info.PROMPTS]) != "missing"
    assert version["corpus"] != "missing" and version["guardrails_code"] != "missing"


def test_without_git_the_commit_is_unknown(monkeypatch):
    def no_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", no_git)
    code_version.cache_clear()
    try:
        version = code_version()
        assert version["commit"] == "unknown" and version["uncommitted_changes"] is None
        assert version["prompts"] != "missing"                          # the fingerprints need no git
    finally:
        code_version.cache_clear()


def test_the_agent_adds_its_own_settings(retriever):
    analyst = MatchAnalyst(client=ScriptedLLM(), retriever=retriever, model="gpt-4o-mini", guardrails=False)
    build = analyst.build
    assert FIELDS <= set(build)
    assert build["model"] == "gpt-4o-mini" and build["guardrails"] is False and build["verifier"] is None
    assert build["compact_memory"] is True


@pytest.fixture
def conversation(retriever, monkeypatch):
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    return backend.Conversation("gpt-4o-mini", True, retriever)


def test_every_saved_answer_says_what_it_was_made_with(conversation, chats_dir):
    message = conversation.ask("Come difendo un 1-0 negli ultimi minuti?")
    conversation.ask("Mi scrivi la ricetta della carbonara?")           # stopped: its version is saved too
    assert message["meta"]["build"] == conversation.analyst.build
    saved = load_chat(conversation.log.path)
    assert [a["meta"]["build"]["prompts"] for a in saved] == [code_version()["prompts"]] * 2
    assert saved[0]["meta"]["build"]["guardrails"] is True and saved[0]["meta"]["build"]["model"] == "gpt-4o-mini"

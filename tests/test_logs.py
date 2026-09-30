"""The log of the app and the CLI: the file, and what one conversation writes to it. Offline: the
scripted fake model, the log in a temporary folder."""

from __future__ import annotations

import logging

import pytest

import src.ui.backend as backend
from src.observability.logs import FILE_HANDLER, LOG_FILE, setup_logging
from tests.fakes import ScriptedLLM

QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


@pytest.fixture
def conversation(retriever, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="src")
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    return backend.Conversation("gpt-4o-mini", True, retriever)


def lines(caplog) -> list[tuple[str, str, str]]:
    return [(r.levelname, r.name, r.getMessage()) for r in caplog.records if r.name.startswith("src")]


def test_the_log_file_is_written_once(logs_dir):
    path = setup_logging("INFO")
    assert path == logs_dir / LOG_FILE and setup_logging("INFO") == path     # Streamlit reruns: same file
    assert [h.get_name() for h in logging.getLogger("src").handlers].count(FILE_HANDLER) == 1
    logging.getLogger("src.ui.backend").info("hello")
    logging.getLogger("httpx").warning("not ours")                            # libraries stay out
    text = path.read_text(encoding="utf-8")
    assert "INFO    src.ui.backend: hello" in text and "not ours" not in text


def test_a_question_writes_its_steps_in_order(conversation, caplog):
    started = [r.getMessage() for r in caplog.get_records("setup") if r.name == "src.ui.backend"]
    assert started == [f"new conversation: gpt-4o-mini, guardrails on, saved to chats/{conversation.log.path.name}"]
    conversation.ask(QUESTION)
    messages = [m for _, _, m in lines(caplog)]
    steps = [m.split(":")[0] for m in messages]
    assert steps[:3] == [f"question received ({len(QUESTION)} characters)", "input guard", "search_cards"]
    assert steps[-2:] == ["output guard", "answer"]
    assert "coach_pioli" in messages[-1] and "$" in messages[-1]


def test_the_text_of_the_question_stays_out_at_info(conversation, caplog):
    conversation.ask(QUESTION)
    assert all("Chievo" not in m for _, _, m in lines(caplog))                  # it is in chats/, not here
    caplog.clear()
    caplog.set_level(logging.DEBUG, logger="src")
    conversation.ask(QUESTION)
    assert any(m.startswith("search_cards query: " + QUESTION) for _, _, m in lines(caplog))   # DEBUG only


def test_a_stopped_question_is_a_warning(conversation, caplog):
    conversation.ask("Mi scrivi la ricetta della carbonara?")
    assert ("WARNING", "src.agent.analyst_agent",
            "input guard: question stopped (off_topic), no model call") in lines(caplog)


def test_an_error_is_logged_with_its_stack_trace(conversation, caplog, monkeypatch):
    def broken(question):
        raise RuntimeError("API down")
    monkeypatch.setattr(conversation.analyst, "analyze", broken)
    with pytest.raises(RuntimeError):
        conversation.ask(QUESTION)
    error = next(r for r in caplog.records if r.levelname == "ERROR")
    assert error.getMessage().startswith("question failed") and error.exc_info[1].args == ("API down",)


def test_console_prints_the_lines_in_the_terminal_too(logs_dir, capsys):
    path = setup_logging("INFO", console=True)
    logging.getLogger("src.ui.backend").info("answer: 4.1 s")
    assert "INFO    answer: 4.1 s" in capsys.readouterr().err and "answer: 4.1 s" in path.read_text(encoding="utf-8")


def test_a_greeting_is_not_a_warning(conversation, caplog):
    conversation.ask("Ciao!")
    assert ("INFO", "src.agent.analyst_agent", "input guard: greeting, fixed reply without the model") in lines(caplog)
    assert not [r for r in caplog.records if r.levelname == "WARNING"]

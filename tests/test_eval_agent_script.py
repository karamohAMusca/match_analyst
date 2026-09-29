"""scripts/eval_agent.py --follow-up end to end, offline: the follow-up question is asked right
after its previous turn, in the same conversation (fake model, in-memory index, no key)."""

from __future__ import annotations

import json
import sys
import threading
from types import SimpleNamespace

import datapizza.clients.openai as openai_clients
import pytest

import scripts.eval_agent as eval_agent
import src.agent.analyst_agent as analyst_module
from tests.fakes import ScriptedLLM

FOLLOW_UP = "E se invece ci pressano alti a uomo?"


@pytest.fixture
def run_script(retriever, monkeypatch, tmp_path):
    """Runs the script with `args`; returns (saved run, the fake clients in creation order)."""
    clients: list[ScriptedLLM] = []
    monkeypatch.setattr(openai_clients, "OpenAIClient", lambda **kw: clients.append(ScriptedLLM()) or clients[-1])
    monkeypatch.setattr(analyst_module, "require_api_key", lambda provider: "test-key")
    monkeypatch.setattr(analyst_module, "load_settings", lambda: SimpleNamespace(chat_model="gpt-4o-mini"))
    monkeypatch.setattr(analyst_module, "build_retriever", lambda: retriever)
    # Like the real Qdrant client: a lock, which a deep copy of the conversation memory cannot copy.
    monkeypatch.setattr(retriever, "lock", threading.RLock(), raising=False)
    monkeypatch.setattr(eval_agent, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(eval_agent, "PROJECT_ROOT", tmp_path.parent)

    def run(*args: str):
        monkeypatch.setattr(sys, "argv", ["eval_agent", "--no-trace", *args])
        assert eval_agent.main() == 0
        saved = sorted(tmp_path.glob("agent_*.json"))[-1]
        data = json.loads(saved.read_text(encoding="utf-8"))
        saved.unlink()
        return data, clients

    return run


def test_follow_up_is_asked_after_its_previous_turn_in_the_same_conversation(run_script):
    data, clients = run_script("--follow-up")
    [row] = data["questions"]
    assert row["question_id"] == "Q37" and row["previous_turn"] == "Q13"
    assert row["previous_question"].startswith("Domenica affrontiamo") and row["previous_answer"]
    assert row["guard"]["input"] == "football" and row["check"]["expected_sources"] == ["situation_uscire_dal_pressing_alto"]
    conversation = clients[-1]                                   # the client of the two-turn conversation
    first_call_of_turn_2 = next(turns for question, turns in conversation.seen if question == FOLLOW_UP)
    assert first_call_of_turn_2 > 0                              # turn 1 was in memory when turn 2 started


def test_follow_up_is_added_to_the_other_questions(run_script):
    data, _ = run_script("--ids", "Q24", "--follow-up")
    assert [r["question_id"] for r in data["questions"]] == ["Q24", "Q37"]

"""The agent loop end to end — agent -> tool -> retriever -> answer — with a scripted LLM (offline)."""

from __future__ import annotations

from types import SimpleNamespace

import src.agent.analyst_agent as analyst_module
from src.agent.analyst_agent import MatchAnalyst
from src.agent.prompts import MATCH_ANALYST_SYSTEM_PROMPT
from tests.fakes import ScriptedLLM

QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


def test_question_goes_through_search_and_answer_cites_cards(retriever):
    analyst = MatchAnalyst(client=ScriptedLLM(), retriever=retriever)
    answer = analyst.analyze(QUESTION)
    assert "[coach_pioli] Profilo allenatore: Stefano Pioli" in answer   # passages reached the answer
    assert analyst.consulted_cards[0] == "coach_pioli"
    assert analyst.corpus_tools.calls[0]["query"] == QUESTION


def test_greeting_needs_no_tool(retriever):
    analyst = MatchAnalyst(client=ScriptedLLM(), retriever=retriever)
    assert analyst.analyze("Ciao, chi sei?").startswith("Ciao!")
    assert analyst.consulted_cards == []


def test_consulted_cards_reset_between_questions(retriever):
    analyst = MatchAnalyst(client=ScriptedLLM(), retriever=retriever)
    analyst.analyze(QUESTION)
    analyst.analyze("Ciao!")
    assert analyst.consulted_cards == []


def test_system_prompt_reaches_the_model(retriever):
    llm = ScriptedLLM()
    MatchAnalyst(client=llm, retriever=retriever).analyze(QUESTION)
    assert llm.system_prompts and all(p == MATCH_ANALYST_SYSTEM_PROMPT for p in llm.system_prompts)


def test_conversation_memory_only_when_stateful(retriever):
    chat = MatchAnalyst(client=ScriptedLLM(), retriever=retriever, stateless=False)
    chat.analyze(QUESTION)
    assert len(chat.agent._memory) > 0                     # kept for follow-up questions
    single = MatchAnalyst(client=ScriptedLLM(), retriever=retriever)
    single.analyze(QUESTION)
    assert len(single.agent._memory) == 0                  # every question on its own


def test_prompt_rules():
    p = MATCH_ANALYST_SYSTEM_PROMPT
    assert "without tools" in p                            # greetings: no search (course S11)
    assert "call search_cards before answering" in p
    assert "Those ids are the only valid citations" in p and "Never write a list of sources" in p
    assert 'begin with the exact words "Non lo so."' in p and "not \"non ho trovato informazioni\"" in p
    assert "at most 150 words" in p and "No sub-bullets" in p
    assert "Never connect a card to teams, seasons or events it does not mention" in p
    assert "must appear in the tool results" in p and "Never add them from your own knowledge" in p
    assert "do not attribute to one coach a trait taken from another coach's card" in p
    assert "include a real case" in p
    assert "attaccare_un_blocco_basso" not in p      # no gold answer leaked into the prompt
    assert 'categories ["coach_profile"]' in p and "first search that coach's profile" in p
    assert "does not describe the ideas of another coach" in p
    assert "Do not write interpretations of your own" in p
    assert "Write the whole answer in the language of the question" in p and "Italian coaching terms" not in p
    assert "[coach_pioli, p. 4]" in p and "Never cite with parentheses alone" in p
    assert "report every value with its source" in p
    assert "Never turn an example into a general rule, threshold or ranking" in p


def test_model_option_overrides_the_default(retriever, monkeypatch):
    # No key and no .env: settings, key and OpenAI client are replaced by stand-ins.
    created = []
    monkeypatch.setattr(analyst_module, "load_settings", lambda: SimpleNamespace(chat_model="gpt-4o-mini"))
    monkeypatch.setattr(analyst_module, "require_openai_key", lambda: "test-key")
    monkeypatch.setattr(analyst_module, "OpenAIClient", lambda **kw: created.append(kw) or ScriptedLLM())
    assert MatchAnalyst(retriever=retriever).model == "gpt-4o-mini"
    assert MatchAnalyst(retriever=retriever, model="gpt-4.1-mini").model == "gpt-4.1-mini"
    assert [c["model"] for c in created] == ["gpt-4o-mini", "gpt-4.1-mini"]

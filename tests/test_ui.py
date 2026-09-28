"""Front end logic (offline, no Streamlit needed): formatting of answers and cards, saved runs,
and the conversation backend with a scripted fake model."""

from __future__ import annotations

import pytest

import src.ui.backend as backend
from src.core.config import PROJECT_ROOT
from src.ui import view
from tests.fakes import ScriptedLLM

CARDS = view.load_card_index()
QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


def test_card_index_and_titles():
    assert len(CARDS) == 31
    assert view.short_title(CARDS["case_2026_wc_final_spain_argentina"]) == "Finale Mondiale 2026"
    assert view.short_title(CARDS["coach_pioli"]) == "Stefano Pioli"
    long_title = view.short_title(CARDS["situation_uscire_dal_pressing_alto"])   # seen in the app: "…marcat…"
    assert long_title.endswith("…") and len(long_title) <= 40 and not long_title[:-1].endswith(" ")
    assert long_title[:-1] in CARDS["situation_uscire_dal_pressing_alto"]["title"]   # whole words only
    assert not view.card_body(CARDS["coach_pioli"]).startswith("# ")          # title shown in the header
    head = view.card_header_html(CARDS["case_2026_wc_final_spain_argentina"])
    assert "Finale Mondiale 2026" in head and "🏅 Spagna" in head and "📋 Argentina: 4-4-2" in head


def test_citations_become_badges_and_text_is_escaped():
    answer = ("Vince la Spagna [case_2026_wc_final_spain_argentina]. <script>x</script> "
              "Catene laterali [coach_pioli, p. 4]. Riferimento interno [Pioli, p. 4].")
    out = view.cite_badges(answer, CARDS)
    assert '<span class="ma-cite" title="Finale Mondiale 2026: Spagna 1-0 Argentina (d.t.s.)">🏆 Finale Mondiale 2026</span>' in out
    assert "🧑‍🏫 Stefano Pioli · p. 4</span>" in out
    assert "&lt;script&gt;" in out and "<script>" not in out               # model output cannot inject HTML
    assert "[Pioli, p. 4]" in out                                           # not a card id: left as it is


def test_cards_of_an_answer_cited_first():
    message = {"content": "A [coach_pioli]. B [note_x_missing].", "consulted": ["coach_klopp", "coach_pioli"]}
    assert view.ordered_cards(message, CARDS) == ["coach_pioli", "coach_klopp"]


def test_details_and_searches():
    message = {"consulted": ["coach_pioli"], "calls": [
        {"tool": "search_cards", "query": "catene laterali", "categories": ["coach_profile"], "cards": ["coach_pioli"]},
        {"tool": "read_card", "document_id": "coach_pioli", "found": True}],
        "guard": {"input": "football", "issues": ["language: it instead of en"], "rewritten": True},
        "meta": {"latency_s": 4.25, "prompt_tokens": 5005, "completion_tokens": 230, "cost_usd": 0.0009, "model": "gpt-4o-mini"}}
    details = view.details_markdown(message)
    assert "4.2 s" in details or "4.3 s" in details
    assert "5.235 (letti 5.005, scritti 230)" in details and "0.0009 $ (gpt-4o-mini)" in details
    assert "**Ricerche:** 1" in details and "risposta riscritta (language)" in details
    searches = view.searches_markdown(message["calls"], CARDS)
    assert "«catene laterali»" in searches and "preferendo: coach_profile" in searches and "letta per intero" in searches


def test_saved_runs_summary():
    runs = view.run_summaries(PROJECT_ROOT / "eval" / "runs")
    assert len(runs["agent"]) == 5 and all(r["domande"] == 44 for r in runs["agent"])
    assert runs["agent"][-1]["run"] == "gpt-4.1-mini + guardrail (18:07)"
    assert runs["gold_live"]["file"] == "gold_20260928-215839.json"
    chosen = next(r for r in runs["retrieval"] if r["metodo"] == "ibrida interleave (scelta)")
    assert round(chosen["recall@5"], 2) == 0.95


@pytest.fixture
def conversation(retriever, monkeypatch):
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    return backend.Conversation("gpt-4o-mini", True, retriever)


def test_conversation_answer_with_its_numbers(conversation):
    message = conversation.ask(QUESTION)
    assert message["role"] == "assistant" and message["consulted"][0] == "coach_pioli"
    assert message["calls"][0]["tool"] == "search_cards" and message["guard"]["input"] == "football"
    assert message["meta"]["model"] == "gpt-4o-mini" and message["meta"]["latency_s"] >= 0


def test_conversation_keeps_memory_and_guardrails(conversation):
    conversation.ask(QUESTION)
    assert conversation.ask("E perché?")["guard"]["input"] == "follow_up"          # memory: follow-ups go through
    blocked = conversation.ask("Mi scrivi la ricetta della carbonara?")
    assert blocked["calls"] == [] and "fuori tema" in blocked["guard_note"]

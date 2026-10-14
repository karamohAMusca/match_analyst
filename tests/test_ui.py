"""Front end logic (offline, no Streamlit needed): formatting of answers and cards, saved runs,
and the conversation backend with a scripted fake model."""

from __future__ import annotations

import pytest

import src.ui.backend as backend
from src.core.config import PROJECT_ROOT
from src.evaluation.cost import estimate_cost
from src.ui import view
from tests.fakes import FakeJudge, ScriptedLLM

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
    assert ('<span class="ma-cite" title="Finale Mondiale 2026: Spagna 1-0 Argentina (d.t.s.)">'
            '<span class="n">1</span>🏆 Finale Mondiale 2026</span>') in out
    assert '<span class="n">2</span>🧑‍🏫 Stefano Pioli · p. 4</span>' in out
    assert "&lt;script&gt;" in out and "<script>" not in out               # model output cannot inject HTML
    assert "[Pioli, p. 4]" in out                                           # not a card id: left as it is


def test_citation_numbers_link_the_badges_to_the_card_next_to_the_answer():
    answer = "A [coach_pioli]. B [coach_klopp, coach_pioli]. C [not_a_card]."
    assert view.citation_numbers(answer, CARDS) == {"coach_pioli": 1, "coach_klopp": 2}   # first cited, first number
    out = view.cite_badges(answer, CARDS)
    assert out.count('<span class="n">1</span>') == 2 and out.count('<span class="n">2</span>') == 1
    assert '<span class="n">2</span></div>' in view.card_header_html(CARDS["coach_klopp"], 2)
    assert 'class="n"' not in view.card_header_html(CARDS["coach_klopp"])        # browsing the cards: no number


def test_masthead_and_welcome_tiles_follow_the_design():
    head = view.header_html(CARDS)
    assert head.startswith('<header class="ma-hero"><div class="top"><span>Coverciano · Finali 2022–2026</span>')
    assert '<div class="ma-chips"><span class="label">Nell\'archivio</span>' in head and "🏆 7 finali" in head
    tile = view.feature_html("🔎", "Solo fonti <citate>", "Testo")
    assert tile == '<div class="ma-feature"><div class="t">🔎 Solo fonti &lt;citate&gt;</div><div class="d">Testo</div></div>'


def test_answer_without_a_source_is_boxed():
    answer = "Il PSG ha vinto ai rigori [case_2026_ucl_final_psg_arsenal].\n\nNon lo so riguardo alla panchina del PSG."
    out = view.answer_html(answer, CARDS)
    first, second = out.split("\n\n")
    assert "ma-unknown" not in first and 'class="ma-cite"' in first
    assert second == ('<div class="ma-unknown"><span class="k">Senza fonte</span>'
                      "<p>Non lo so riguardo alla panchina del PSG.</p></div>")
    assert "ma-unknown" in view.answer_html("I don't know. The cards do not cover it.", CARDS)


def test_guardrail_box_marks_the_questions_that_never_reached_the_model():
    stopped = {"guard_note": "Guardrail: domanda fuori tema, fermata prima del modello.", "guard": {"input": "off_topic"}}
    assert view.guard_html(stopped) == ('<div class="ma-guard blocked"><span class="k">Guardrail</span>'
                                        "domanda fuori tema, fermata prima del modello</div>")
    fixed = {"guard_note": "Guardrail: risposta corretta automaticamente (lingua della risposta).",
             "guard": {"input": "football", "rewritten": True}}
    assert view.guard_html(fixed).startswith('<div class="ma-guard"><span class="k">Guardrail</span>risposta corretta')
    assert view.guard_html({"guard": {"input": "football"}}) == ""              # nothing to report


def test_cards_of_an_answer_cited_first():
    message = {"content": "A [coach_pioli]. B [note_x_missing].", "consulted": ["coach_klopp", "coach_pioli"]}
    assert view.ordered_cards(message, CARDS) == ["coach_pioli", "coach_klopp"]


def test_details_say_when_guardrails_are_off_or_the_rewrite_was_not_kept():
    assert "guardrail spenti" in view.details_markdown({"guard": {"input": None}, "meta": {}})
    not_kept = {"input": "football", "issues": ["language: it instead of en"], "rewritten": False}
    assert "problemi trovati, riscrittura non tenuta" in view.details_markdown({"guard": not_kept, "meta": {}})


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
    assert len(runs["agent"]) == 6 and [r["domande"] for r in runs["agent"]] == [44] * 5 + [45]   # + two turns
    assert runs["agent"][-2]["run"] == "gpt-4.1-mini + guardrail (18:07)"
    assert runs["agent"][-1]["run"] == "gpt-4o-mini + guardrail (11:20)" and runs["agent"][-1]["passano"] == 34
    live = runs["gold_live"]                     # the latest live run of the app's configuration
    assert live["file"] >= "gold_20261009-112356.json" and not live["verifier"]   # not -114805: it used the verifier
    final = {r["agente"]: r for r in runs["final"]}                     # the numbers of the README
    assert round(final["gpt-4o-mini"]["fedeltà"], 3) == 0.910 and round(final["gpt-4.1-mini"]["pertinenza"], 2) == 0.98
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


def test_the_verifier_is_in_the_cost_and_in_the_details(retriever, monkeypatch):
    judge = FakeJudge()                                        # 100 + 20 tokens per call
    judge.model_name = "gpt-4.1-mini"                          # priced like the real verifier
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    monkeypatch.setattr(backend, "make_verifier", lambda: judge)
    conversation = backend.Conversation("gpt-4o-mini", True, retriever)
    meta = conversation.ask(QUESTION)["meta"]
    assert meta["verifier_model"] == "gpt-4.1-mini" and meta["verifier_tokens"] == 240   # statements + verdicts
    agent = estimate_cost(meta["prompt_tokens"], meta["completion_tokens"], "gpt-4o-mini")
    assert meta["cost_usd"] == pytest.approx(agent + estimate_cost(200, 40, "gpt-4.1-mini"))
    assert "+ verifica gpt-4.1-mini, 240 token" in view.details_markdown({"meta": meta})


def test_conversation_keeps_memory_and_guardrails(conversation):
    conversation.ask(QUESTION)
    assert conversation.ask("E perché?")["guard"]["input"] == "follow_up"          # memory: follow-ups go through
    blocked = conversation.ask("Mi scrivi la ricetta della carbonara?")
    assert blocked["calls"] == [] and "fuori tema" in blocked["guard_note"]

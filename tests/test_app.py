"""The Streamlit page end to end, offline: Streamlit's AppTest runs app.py with the in-memory index
and the scripted fake model (no key, no browser). Skipped if Streamlit is not installed."""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import src.ui.backend as backend  # noqa: E402
from src.core.config import PROJECT_ROOT  # noqa: E402
from tests.fakes import ScriptedLLM  # noqa: E402

QUESTION = "Primavera del Chievo: si gioca alla domenica come ci si allena durante la settimana"


@pytest.fixture
def app(retriever, monkeypatch):
    monkeypatch.setattr(backend, "build_retriever", lambda: retriever)
    monkeypatch.setattr(backend, "make_client", lambda model: ScriptedLLM())
    monkeypatch.setattr(backend, "start_tracing", lambda: "Tracing spento (test).")
    return AppTest.from_file(str(PROJECT_ROOT / "app.py"), default_timeout=60).run()


def test_page_renders_tabs_welcome_and_examples(app):
    assert not app.exception
    assert [t.label for t in app.tabs] == ["💬 Chat", "📚 Schede", "📈 Valutazione"]
    assert any("ma-hero" in m.value for m in app.markdown)                    # header
    assert any("Prepara la partita" in m.value for m in app.markdown)          # welcome, no messages yet
    labels = [b.label for b in app.sidebar.button]
    assert "🆕 Nuova conversazione" in labels and "🛡️ Fuori tema (guardrail)" in labels


def test_question_gets_an_answer_with_badges_and_cards(app):
    app.chat_input[0].set_value(QUESTION).run()
    assert not app.exception
    assert [m.name for m in app.chat_message] == ["user", "assistant"]
    assert any('class="ma-cite"' in m.value for m in app.markdown)            # citations as badges
    assert app.selectbox(key="answer_card_2").value == "coach_pioli"           # the cards of the answer
    assert [e.label for e in app.expander][:2] == ["📊 Dettagli della risposta", "🔎 Cosa ha cercato l'assistente"]


def test_off_topic_example_is_stopped_and_explained(app):
    app.chat_input[0].set_value(QUESTION).run()                                # a conversation is going on
    next(b for b in app.sidebar.button if b.label.startswith("🛡️")).click().run()
    assert not app.exception
    answer = app.chat_message[-1]
    assert answer.name == "assistant" and "Posso aiutarti solo" in answer.markdown[0].value
    assert any('class="ma-guard blocked"' in m.value and "fuori tema" in m.value
               for m in answer.markdown)                                       # the guardrail box


def test_new_conversation_and_other_tabs(app):
    app.chat_input[0].set_value(QUESTION).run()
    next(b for b in app.sidebar.button if b.label.startswith("🆕")).click().run()
    assert not app.chat_message                                                # cleared
    assert app.radio(key="browse_category").value == "match_case"             # cards tab ready
    assert any(m.label == "recall@5" for m in app.metric)                      # evaluation tab from saved runs


def test_the_formations_of_the_question_are_drawn_under_the_answer(app):
    app.chat_input[0].set_value("Domenica affrontiamo una squadra che si chiude in un 4-4-2 basso. "
                                "Noi giochiamo 4-3-3. Come la prepariamo?").run()
    assert not app.exception
    figures = [m.value for m in app.chat_message[-1].markdown if 'class="ma-figure"' in m.value]
    assert len(figures) == 1 and "VOI · 4-3-3" in figures[0] and "AVVERSARIO · 4-4-2" in figures[0]
    app.chat_input[0].set_value(QUESTION).run()                                # no formation: no pitch
    assert not any('class="ma-figure"' in m.value for m in app.chat_message[-1].markdown)
    first = [m.value for m in app.chat_message[1].markdown if 'class="ma-figure"' in m.value][0]
    assert "@keyframes" not in first                                           # the older one is drawn still


def test_a_final_in_the_cards_tab_shows_its_timeline(app):
    assert app.radio(key="browse_category").value == "match_case"             # a final is shown first
    timelines = [m.value for m in app.markdown if "ma-timeline" in m.value]
    assert timelines and "@keyframes" not in timelines[0]                      # drawn still, from the card


def test_a_final_with_statsbomb_data_plays_a_goal_in_the_cards_tab(app):
    from src.ui.graphics import goal_actions
    if not goal_actions():
        pytest.skip("the derived StatsBomb goal actions are not on this computer")
    app.radio(key="browse_card_match_case").set_value("case_2022_wc_final_argentina_france").run()
    assert not app.exception
    pick = app.segmented_control[0]
    assert pick.key == "goal_case_2022_wc_final_argentina_france_560" and pick.value == 4   # the longest action
    assert any("ma-goal" in m.value and "3-2 Messi" in m.value for m in app.markdown)
    pick.set_value(1).run()                                                    # another goal
    assert any("ma-goal" in m.value and "36' 2-0 Di María" in m.value for m in app.markdown)


def test_the_graphics_preview_page_runs_without_the_model():
    page = AppTest.from_file(str(PROJECT_ROOT / "scripts" / "preview_graphics.py"), default_timeout=60).run()
    assert not page.exception
    assert sum("ma-timeline" in m.value for m in page.markdown) >= 7               # every final's timeline
    assert any('aria-label="Voi 4-3-3 · Avversario 4-4-2"' in m.value for m in page.markdown)

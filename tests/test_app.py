"""The Streamlit page end to end, offline: Streamlit's AppTest runs app.py with the in-memory index
and the scripted fake model (no key, no browser). Skipped if Streamlit is not installed."""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

import src.ui.backend as backend  # noqa: E402
from src.ui import view  # noqa: E402
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
    assert app.selectbox(key="answer_card_1_2").value == "coach_pioli"         # the cards of the answer
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
    timelines = [m.value for m in app.markdown if 'class="ma-figure ma-timeline"' in m.value]
    assert timelines and "@keyframes" not in timelines[0]                      # drawn still, from the card


def test_a_final_with_statsbomb_data_plays_a_goal_in_the_cards_tab(app):
    from src.ui.graphics import goal_actions
    if not goal_actions():
        pytest.skip("the derived StatsBomb goal actions are not on this computer")
    app.radio(key="browse_card_match_case").set_value("case_2022_wc_final_argentina_france").run()
    assert not app.exception
    pick = app.segmented_control[0]
    assert pick.key == "goal_case_2022_wc_final_argentina_france_560" and pick.value == 4   # the longest action
    assert any('class="ma-figure ma-goal"' in m.value and "3-2 Messi" in m.value for m in app.markdown)
    pick.set_value(1).run()                                                    # another goal
    assert any('class="ma-figure ma-goal"' in m.value and "36' 2-0 Di María" in m.value for m in app.markdown)


def test_the_cards_tab_shows_a_final_s_numbers_and_a_coach_s_change_of_shape(app):
    app.radio(key="browse_card_match_case").set_value("case_2024_euro_final_spain_england").run()
    numbers = [m.value for m in app.markdown if 'class="ma-figure ma-numbers"' in m.value]
    assert numbers and "@keyframes" not in numbers[0] and "PPDA" in numbers[0]   # drawn still, from the card's table
    app.radio(key="browse_category").set_value("coach_profile").run()
    app.radio(key="browse_card_coach_profile").set_value("coach_inzaghi").run()
    assert not app.exception
    shapes = [m.value for m in app.markdown if 'class="ma-figure ma-shape"' in m.value]
    assert len(shapes) == 1 and "3-5-2 → 5-3-2" in shapes[0] and "@keyframes" not in shapes[0]


def test_a_final_with_statsbomb_data_shows_its_shots_in_the_cards_tab(app):
    from src.ui.graphics import match_shots
    if not match_shots():
        pytest.skip("the derived StatsBomb shots are not on this computer")
    app.radio(key="browse_card_match_case").set_value("case_2024_euro_final_spain_england").run()
    assert not app.exception
    shots = [m.value for m in app.markdown if 'class="ma-figure ma-shots"' in m.value]
    assert len(shots) == 1 and "16 tiri (6 in porta) · xG 1.79" in shots[0] and "@keyframes" not in shots[0]
    app.radio(key="browse_card_match_case").set_value("case_2026_wc_final_spain_argentina").run()
    assert not any('class="ma-figure ma-shots"' in m.value for m in app.markdown)                # no StatsBomb data for this final


def test_the_graphics_preview_page_runs_without_the_model():
    page = AppTest.from_file(str(PROJECT_ROOT / "scripts" / "preview_graphics.py"), default_timeout=60).run()
    assert not page.exception
    assert sum('class="ma-figure ma-timeline"' in m.value for m in page.markdown) >= 7               # every final's timeline
    assert sum('class="ma-figure ma-numbers"' in m.value for m in page.markdown) >= 3                # the finals with a numbers table
    assert sum('class="ma-figure ma-shape"' in m.value for m in page.markdown) >= 4                  # under an answer, and every change
    assert any('aria-label="Voi 4-3-3 · Avversario 4-4-2"' in m.value for m in page.markdown)


def test_the_coach_can_pick_the_goal_to_play_under_an_answer(app):
    from src.ui.graphics import goal_actions
    if not goal_actions():
        pytest.skip("the derived StatsBomb goal actions are not on this computer")
    line = "Caso reale: Southgate inserisce Watkins e Palmer, e Palmer pareggia [case_2024_euro_final_spain_england]."
    app.session_state["messages"] = [
        {"role": "user", "content": "Come rimontiamo?"},
        {"role": "assistant", "content": "Cambiate presto [situation_rimontare_uno_svantaggio].\n\n" + line,
         "guard": {"input": "football"}}]
    app.run()
    assert not app.exception
    pick = app.segmented_control(key="goal_chat_1_case_2024_euro_final_spain_england")
    assert pick.value == 1                                                    # Palmer: the goal the line points to
    goals = [m.value for m in app.chat_message[-1].markdown if 'class="ma-figure ma-goal"' in m.value]
    assert len(goals) == 1 and "73' 1-1 Palmer" in goals[0] and "@keyframes" in goals[0]   # the newest answer moves
    pick.set_value(2).run()                                                   # another goal, from the chat
    goals = [m.value for m in app.chat_message[-1].markdown if 'class="ma-figure ma-goal"' in m.value]
    assert len(goals) == 1 and "86' 2-1 Oyarzabal" in goals[0]


def test_several_figures_under_an_answer_go_in_tabs_and_one_figure_does_not(app):
    final = "case_2026_wc_final_spain_argentina"
    answer = f"Decise un cambio offensivo [situation_attaccare_un_blocco_basso].\n\nCaso reale: la Spagna batte il 4-4-2 [{final}]."
    chat = [{"role": "user", "content": "Quanto possesso ha avuto la Spagna? Noi giochiamo 4-3-3 contro un 4-4-2."},
            {"role": "assistant", "content": answer, "guard": {"input": "football"}}]
    app.session_state["messages"] = chat
    app.run()
    assert not app.exception
    # the page's tabs, and inside the chat the tabs of the answer's figures: the pitch, then the final's
    assert [t.label for t in app.tabs] == ["💬 Chat", "Campo", "Linea del tempo", "Numeri", "📚 Schede", "📈 Valutazione"]
    shown = [m.value for m in app.chat_message[-1].markdown if 'class="ma-figure' in m.value]
    assert len(shown) == 3 and "@keyframes" in shown[0]                       # the newest answer moves
    chat[0]["content"] = "Come si difende un vantaggio?"                       # no formation, no number: one figure
    app.session_state["messages"] = chat
    app.run()
    assert [t.label for t in app.tabs] == ["💬 Chat", "📚 Schede", "📈 Valutazione"]   # a single figure: no tabs
    assert sum('class="ma-figure ma-timeline"' in m.value for m in app.chat_message[-1].markdown) == 1


def test_the_cards_panel_next_to_the_chat_can_be_turned_off(app):
    assert any("Schede della risposta" in m.value for m in app.markdown)
    app.toggle(key="cards_panel").set_value(False).run()
    assert not app.exception
    assert not any("Schede della risposta" in m.value for m in app.markdown)   # the chat takes the whole width
    app.toggle(key="cards_panel").set_value(True).run()
    assert any("Schede della risposta" in m.value for m in app.markdown)


def test_the_cards_panel_says_which_answer_it_is_of_and_follows_the_coach_s_pick(app):
    answer = lambda card: {"role": "assistant", "content": f"Risposta [{card}].", "guard": {"input": "football"},
                           "consulted": [card]}
    app.session_state["messages"] = [
        {"role": "user", "content": "Come difende l'Inter di Inzaghi senza palla?"}, answer("coach_inzaghi"),
        {"role": "user", "content": "E il Pioli della tesi come pressa sulle fasce, in una domanda lunga abbastanza da essere tagliata?"},
        answer("coach_pioli")]
    app.run()
    assert not app.exception
    notes = [m.value for m in app.markdown if '<div class="ma-panel-note">' in m.value]
    assert len(notes) == 1 and "E il Pioli della tesi come pressa sulle fasce" in notes[0] and "…" in notes[0]   # the newest
    assert app.button(key="panel_3").disabled and not app.button(key="panel_1").disabled   # the shown one is marked
    assert app.button(key="panel_3").label == "📄 Schede a destra"
    app.button(key="panel_1").click().run()                                      # the coach picks the first answer
    notes = [m.value for m in app.markdown if '<div class="ma-panel-note">' in m.value]
    assert len(notes) == 1 and "Come difende l&#x27;Inter di Inzaghi senza palla?" in notes[0]
    assert app.selectbox(key="answer_card_1_4").value == "coach_inzaghi"
    app.toggle(key="cards_panel").set_value(False).run()                          # no panel: no buttons either
    assert not any(b.key and b.key.startswith("panel_") for b in app.button)


def test_the_coach_is_told_the_answers_come_from_an_ai_and_where_the_questions_go(app):
    # AI Act art. 50(1): always on screen, before the first question and after it
    notice = [c.value for c in app.sidebar.caption if "intelligenza artificiale" in c.value]
    assert notice == [view.AI_NOTICE] and "OpenAI" in notice[0] and "chats/" in notice[0]
    app.chat_input[0].set_value("Come difendo un 1-0 negli ultimi minuti?").run()
    assert [c.value for c in app.sidebar.caption if "intelligenza artificiale" in c.value] == [view.AI_NOTICE]


def test_streamlit_sends_no_usage_statistics():
    import tomllib
    config = tomllib.loads((PROJECT_ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8"))
    assert config["browser"]["gatherUsageStats"] is False

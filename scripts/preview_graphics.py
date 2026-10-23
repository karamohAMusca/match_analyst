"""A page to look at the graphics under a chat answer without the model or the API key: the real
functions of src/ui/graphics/ with the app's CSS, on a written conversation, every coach's change of
shape, every final's timeline and numbers and, when the derived StatsBomb file is on this computer,
the action of every goal.

    streamlit run scripts/preview_graphics.py

Check it in the light and the dark theme (Streamlit's menu, Settings), on a wide and a narrow window.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # run as a file by streamlit, not as a module
from src.ui import graphics, view  # noqa: E402

st.set_page_config(page_title="Anteprima dei grafici", layout="wide")
st.markdown(view.CSS, unsafe_allow_html=True)
cards = view.load_card_index()
answer = ("Contro un 4-4-2 basso col tuo 4-3-3 attacca le zone intermedie [situation_attaccare_un_blocco_basso].\n\n"
          "Caso reale: Mondiale 2026: la Spagna batte il 4-4-2 basso argentino con possesso che avanza "
          "[case_2026_wc_final_spain_argentina].")
chat = [{"role": "user", "content": "Domenica affrontiamo una squadra che si chiude in un 4-4-2 basso. Noi giochiamo 4-3-3."},
        {"role": "assistant", "content": answer, "guard": {"input": "football"}},
        {"role": "user", "content": "Come difende l'Inter di Inzaghi senza palla?"},
        {"role": "assistant", "content": "Il 3-5-2 fluido diventa un 5-3-2 senza palla, con i terzini che tornano in "
                                         "difesa [coach_inzaghi].", "guard": {"input": "football"}},
        {"role": "user", "content": "Siamo sotto 1-0 e vogliamo rimontare: come ci muoviamo?"},
        {"role": "assistant", "content": "Cambiate presto, se la partita non gira [situation_rimontare_uno_svantaggio].\n\n"
                                         "Caso reale: Southgate inserisce Watkins e Palmer, e Palmer pareggia "
                                         "[case_2024_euro_final_spain_england].", "guard": {"input": "football"}}]

st.markdown("### Sotto una risposta")
for i, message in enumerate(chat):
    with st.chat_message(message["role"], avatar="🧑‍🏫" if message["role"] == "user" else "⚽"):
        if message["role"] == "user":
            st.markdown(message["content"])
            continue
        st.markdown(view.answer_html(message["content"], cards), unsafe_allow_html=True)
        for figure in graphics.answer_figures(chat, i, cards, goals=False):
            st.markdown(figure, unsafe_allow_html=True)
        for case_id, goals, default, english in graphics.answer_goals(chat, i, cards):   # as in app.py
            pick = st.segmented_control("L'azione di un gol (StatsBomb)", list(range(len(goals))), default=default,
                                        key=f"goal_chat_{i}_{case_id}",
                                        format_func=lambda n, goals=goals: graphics.goal_label(goals[n], english))
            if pick is not None:
                st.markdown(graphics.goal_svg(goals[pick], cards[case_id], english=english), unsafe_allow_html=True)

st.markdown("### I cambi di modulo delle schede")
for card in (c for c in cards.values() if c["shape_changes"]):
    for change in card["shape_changes"]:
        st.markdown(graphics.shape_svg(card, change), unsafe_allow_html=True)

st.markdown("### Le linee del tempo e i numeri delle finali")
for case_id in sorted(i for i in cards if i.startswith("case_")):
    st.markdown(graphics.timeline_svg(cards[case_id], animate=False), unsafe_allow_html=True)
    if numbers := graphics.numbers_svg(cards[case_id], animate=False):
        st.markdown(numbers, unsafe_allow_html=True)
    if shots := graphics.match_shots().get(case_id):
        st.markdown(graphics.shots_svg(shots, cards[case_id]), unsafe_allow_html=True)

st.markdown("### Le azioni dei gol (StatsBomb)")
actions = graphics.goal_actions()
if not actions:
    st.info("File derivato assente: python -m scripts.build_goal_actions (servono gli eventi StatsBomb in references/).")
for case_id, goals in actions.items():
    pick = st.segmented_control(cards[case_id]["title"], list(range(len(goals))), default=0,
                                format_func=lambda i, goals=goals: graphics.goal_label(goals[i]), key=f"preview_{case_id}")
    if pick is not None:
        st.markdown(graphics.goal_svg(goals[pick], cards[case_id]), unsafe_allow_html=True)

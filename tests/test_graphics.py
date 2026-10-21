"""Graphics under a chat answer (src/ui/graphics.py), offline: the formations read from the coach's
questions, the places of the players, the SVG and the answer it is drawn under."""

from __future__ import annotations

import re

import pytest

from src.ui.graphics import answer_figure, coach_formations, formation_places, formations_in, formations_svg

DEMO = "Domenica affrontiamo una squadra che si chiude in un 4-4-2 basso. Noi giochiamo 4-3-3. Come la prepariamo?"


@pytest.mark.parametrize("question, expected", [
    (DEMO, {"ours": "4-3-3", "theirs": "4-4-2"}),
    ("sto giocando 352 e devo affrontare 433 cosa faccio?", {"ours": "3-5-2", "theirs": "4-3-3"}),   # E11
    ("La mia squadra gioca 4-2-3-1 contro un 3-5-2", {"ours": "4-2-3-1", "theirs": "3-5-2"}),
    ("On Sunday we face a team sitting in a deep 4-4-2 block. We play 4-3-3.", {"ours": "4-3-3", "theirs": "4-4-2"}),
    ("Il loro 4-1-2-1-2 a rombo, noi col 3-4-3", {"ours": "3-4-3", "theirs": "4-1-2-1-2"}),
    ("Come si attacca un 4-4-2 basso?", {"theirs": "4-4-2"}),
    ("Abbiamo vinto 1-0 e 2-1, nel 2024 giocavamo 4–3–3", {"ours": "4-3-3"}),   # a score, a year, an en dash
    ("Il Sassuolo di De Zerbi in 4-3-3 contro due punte", {}),     # not the coach's: no side, no pitch
    ("Che modulo usa Gasperini? 3-4-2-1", {}),
    ("Noi giochiamo 4-4-4", {}),                                    # 12 players: not a formation
])
def test_formations_and_their_side(question, expected):
    assert formations_in(question) == expected


def test_a_later_question_completes_or_overrides_the_sides():
    assert coach_formations(["Noi giochiamo 4-3-3", "E se loro passano al 3-5-2?"]) == {"ours": "4-3-3", "theirs": "3-5-2"}
    assert coach_formations(["Noi giochiamo 4-3-3", "Ora noi giochiamo 3-5-2"]) == {"ours": "3-5-2"}


@pytest.mark.parametrize("formation", ["4-3-3", "4-4-2", "4-2-3-1", "3-5-2", "4-1-2-1-2"])
def test_eleven_places_in_the_own_half(formation):
    places = formation_places(formation)
    assert len(places) == 11 and places[0][2] == "portiere"
    assert all(0 < x < 60 and 0 < y < 80 for x, y, _ in places)
    assert len({(x, y) for x, y, _ in places}) == 11                      # nobody on top of another


def test_the_pitch_svg():
    svg = formations_svg({"ours": "4-3-3", "theirs": "4-4-2"})
    assert svg.count('fill="var(--ma-red,#B3122B)" stroke=') == 11      # the coach's team: red, filled
    assert svg.count('stroke="var(--ma-ink,#111)" stroke-width="0.9"') == 11   # the opponent: hollow, in ink
    assert "VOI · 4-3-3" in svg and "AVVERSARIO · 4-4-2" in svg          # direct labels, not colour alone
    assert svg.count("<title>") == 22 and "<title>Voi · 4-3-3 · difesa</title>" in svg   # a tooltip per player
    assert 'aria-label="Voi 4-3-3 · Avversario 4-4-2"' in svg
    assert "le posizioni non vengono dalle schede" in svg
    assert "@keyframes" in svg and "prefers-reduced-motion" in svg
    assert "<script" not in svg
    still = formations_svg({"ours": "4-3-3"}, english=True, animate=False)
    assert "@keyframes" not in still and "YOU · 4-3-3" in still and "AVVERSARIO" not in still
    assert "they do not come from the cards" in still
    assert formations_svg({}) == ""


def test_keyframe_names_differ_between_figures():
    names = lambda svg: set(re.findall(r"@keyframes (ma-\w+-ours-0)", svg))   # noqa: E731
    assert names(formations_svg({"ours": "4-3-3"})) != names(formations_svg({"ours": "3-5-2"}))


def _chat(*turns: tuple[str, str]) -> list[dict]:
    messages = []
    for question, verdict in turns:
        messages += [{"role": "user", "content": question},
                     {"role": "assistant", "content": "Risposta [x_y].", "guard": {"input": verdict}}]
    return messages


def test_the_answer_the_pitch_is_drawn_under():
    chat = _chat((DEMO, "football"), ("E se restassimo in 10 al 90'?", "follow_up"),
                 ("E se loro passano al 3-5-2?", "follow_up"), ("Chi ha vinto Sanremo? 4-3-3 noi", "off_topic"))
    assert "VOI · 4-3-3" in answer_figure(chat, 1) and "AVVERSARIO · 4-4-2" in answer_figure(chat, 1)
    assert answer_figure(chat, 3) == ""                           # its question names no formation
    third = answer_figure(chat, 5)
    assert "VOI · 4-3-3" in third and "AVVERSARIO · 3-5-2" in third   # our side from the first question
    assert answer_figure(chat, 7) == ""                           # stopped by the input guard
    assert answer_figure(chat, 0) == ""                           # a question, not an answer
    assert "@keyframes" not in answer_figure(chat, 1, animate=False)

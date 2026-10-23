"""The figure of a coach's team changing shape (src/ui/graphics/shape.py), offline: the changes read
from the cards, who goes where, the SVG and the answers it is drawn under."""

from __future__ import annotations

import itertools
import random
import re
from collections import Counter

import pytest

from src.ui.graphics.shape import cited_shape_changes, least_movement, shape_moves, shape_svg
from src.ui.view import load_card_index

CARDS = load_card_index()
INZAGHI = CARDS["coach_inzaghi"]
CHANGE = INZAGHI["shape_changes"][0]
SHAPES = {"coach_inzaghi": ("3-5-2", "5-3-2"), "coach_pioli": ("4-4-2", "3-4-3"), "coach_guardiola": ("3-2-5", "2-3-5")}


def _classes(svg: str) -> set[str]:
    return set(re.findall(r'class="(ma-[0-9a-f]{6}-[\w-]+)"', svg))   # the animated parts, not ma-figure


def test_the_shape_changes_read_from_the_cards():
    found = {i: [(c["from"], c["to"]) for c in card["shape_changes"]] for i, card in CARDS.items() if card["shape_changes"]}
    assert found == {i: [shape] for i, shape in SHAPES.items()}
    assert CHANGE["when"] == "senza palla" and CHANGE["quote"] == "3-5-2 fluido, che diventa 5-3-2 senza palla"
    pioli = CARDS["coach_pioli"]["shape_changes"][0]
    assert pioli["team"] == "Primavera del Chievo" and "la tesi descrive il 4-4-2" in pioli["note"]   # not his later teams
    assert CARDS["coach_guardiola"]["shape_changes"][0]["team"] == "City"
    assert CARDS["coach_conte"]["shape_changes"] == []     # "linea a cinque": the card never writes the formation


# ---------------------------------------------------------------- who goes where
@pytest.mark.parametrize("seed", range(40))
def test_the_least_movement_is_the_least_of_every_order(seed):
    rng = random.Random(seed)
    n = rng.randint(1, 7)
    cost = [[(rng.randint(0, 30), rng.randint(0, 3)) for _ in range(n)] for _ in range(n)]
    order = least_movement(cost)
    assert sorted(order) == list(range(n))                          # a permutation: every place taken once

    def total(p: tuple[int, ...]) -> tuple[int, ...]:
        return tuple(map(sum, zip(*(cost[i][j] for i, j in enumerate(p)))))

    assert total(tuple(order)) == min(total(p) for p in itertools.permutations(range(n)))   # brute force
    assert least_movement(cost) == order                            # the same costs, the same moves


def test_no_players_no_moves():
    assert least_movement([]) == []


@pytest.mark.parametrize("first, second", [*SHAPES.values(), ("4-2-3-1", "4-4-2"), ("4-3-3", "4-3-3")])
def test_the_goalkeeper_stays_and_every_place_is_taken_once(first, second):
    moves = shape_moves(first, second)
    assert len(moves) == 11 and moves[0][0] == moves[0][1] and moves[0][0][2] == "portiere"
    assert all(start[2] != "portiere" and end[2] != "portiere" for start, end in moves[1:])
    ends = [end for _, end in moves]
    assert len(set(ends)) == 11                                     # nobody on top of another
    for formation, places in ((first, [start for start, _ in moves]), (second, ends)):
        lines = [int(n) for n in formation.split("-")]
        xs = sorted({x for x, _, line in places if line != "portiere"})
        assert [Counter(x for x, _, _ in places)[x] for x in xs] == lines   # the lines of the formation
        assert xs[0] == 18 and xs[-1] == 90                         # spread over the pitch: one team, no opponent
    if first == second:
        assert all(start == end for start, end in moves)            # the same shape: nobody moves


def test_from_3_5_2_to_5_3_2_the_wing_backs_drop_into_the_back_five():
    # Four choices tie on the squared lengths (a wing-back or the midfielder inside him drops, on each
    # side): of equal choices, the wide players change line.
    changed = [(start, end) for start, end in shape_moves("3-5-2", "5-3-2") if start[2] != end[2]]
    assert [(start[1], end[1]) for start, end in changed] == [(13.3, 13.3), (66.7, 66.7)]
    assert all(start[2] == "centrocampo" and end[2] == "difesa" for start, end in changed)


def test_two_players_step_up_a_line_rather_than_one_running_the_pitch():
    # With a plain sum of lengths, from 4-4-2 to 3-4-3 a centre-back would become the third forward.
    pioli = [(start[2], end[2]) for start, end in shape_moves("4-4-2", "3-4-3") if start[2] != end[2]]
    assert sorted(pioli) == [("centrocampo", "attacco"), ("difesa", "centrocampo")]
    guardiola = [(start[2], end[2]) for start, end in shape_moves("3-2-5", "2-3-5") if start[2] != end[2]]
    assert guardiola == [("difesa", "centrocampo")]


def test_the_players_who_change_line_are_the_wide_ones_as_the_cards_say():
    # The changes of the cards are made along the flanks: in the pressing the winger and the full-back
    # of one side step up (Pioli), the false full-back joins the midfield (Guardiola); not centre-backs.
    def changed(first: str, second: str) -> list[tuple[float, str, str]]:
        return [(start[1], start[2], end[2]) for start, end in shape_moves(first, second) if start[2] != end[2]]

    assert changed("4-4-2", "3-4-3") == [(16.0, "difesa", "centrocampo"), (16.0, "centrocampo", "attacco")]
    assert changed("3-2-5", "2-3-5") == [(20.0, "difesa", "centrocampo")]
    assert changed("3-5-2", "5-3-2") == [(13.3, "centrocampo", "difesa"), (66.7, "centrocampo", "difesa")]


# ---------------------------------------------------------------- the figure
def test_the_figure_of_a_shape_change():
    svg = shape_svg(INZAGHI, CHANGE)
    assert svg.count('r="2.3" fill="var(--ma-red,#B3122B)"') == 11          # the team: red, filled
    assert svg.count('r="2" fill="none" stroke="var(--ma-ink,#111)" stroke-width="0.5" opacity="0.45"') == 11   # its first places
    assert svg.count("<title>") == 12                                       # every player, and the header
    assert svg.count("<title>centrocampo nel 3-5-2 → difesa nel 5-3-2</title>") == 2   # the wing-backs
    assert "<title>portiere nel 3-5-2 → portiere nel 5-3-2</title>" in svg
    assert ">COME CAMBIA IL MODULO · SIMONE INZAGHI</text>" in svg           # direct labels, not colour alone
    assert ">3-5-2 → 5-3-2<tspan" in svg and "> · senza palla</tspan>" in svg
    assert "<title>«3-5-2 fluido, che diventa 5-3-2 senza palla»</title>" in svg   # the card's own words
    caption = re.search(r"<figcaption[^>]*>(.*)</figcaption>", svg).group(1)
    assert "Dalla scheda coach_inzaghi: «3-5-2 fluido, che diventa 5-3-2 senza palla»." in caption
    assert "○ dove partono (3-5-2) · ● dove arrivano (5-3-2)." in caption
    assert "Posizioni indicative; chi va dove non viene dalla scheda: è lo spostamento più corto, più facile lungo le fasce." in caption
    assert 'aria-label="Come cambia il modulo: Simone Inzaghi, 3-5-2 → 5-3-2 · senza palla"' in svg
    assert "@keyframes" in svg and "<script" not in svg
    assert shape_svg(INZAGHI, CHANGE) == svg                                # the same figure every time


def test_the_figure_in_english_keeps_the_card_s_words():
    svg = shape_svg(INZAGHI, CHANGE, english=True)
    assert ">HOW THE SHAPE CHANGES · SIMONE INZAGHI</text>" in svg
    assert svg.count("<title>midfield in the 3-5-2 → defence in the 5-3-2</title>") == 2
    assert "> · senza palla</tspan>" in svg
    assert "From the card coach_inzaghi: «3-5-2 fluido, che diventa 5-3-2 senza palla»." in svg
    assert "Indicative positions; who goes where does not come from the card: the shortest movement, easier along the flanks." in svg


def test_pioli_s_figure_says_it_is_the_4_4_2_of_his_thesis():
    pioli = CARDS["coach_pioli"]
    svg = shape_svg(pioli, pioli["shape_changes"][0])
    assert ">COME CAMBIA IL MODULO · STEFANO PIOLI</text>" in svg
    assert ">4-4-2 → 3-4-3<tspan" in svg and "> · Pressing sulle fasce · Primavera del Chievo</tspan>" in svg
    assert ("Dalla scheda coach_pioli: «l'esterno parte in pressione durante il passaggio, terzino e mediano scalano "
            "in avanti; la squadra diventa di fatto un 3-4-3». "
            "«Attenzione: la tesi descrive il 4-4-2 a zona usato con la Primavera del Chievo, non le sue squadre "
            "successive».") in svg
    guardiola = CARDS["coach_guardiola"]
    svg = shape_svg(guardiola, guardiola["shape_changes"][0])
    assert ">3-2-5 → 2-3-5<tspan" in svg and "> · Falso terzino · City</tspan>" in svg


def test_the_still_figure_shows_the_change_without_motion():
    still = shape_svg(INZAGHI, CHANGE, animate=False)
    assert "@keyframes" not in still and "<style>" not in still
    moves = [(start, end) for start, end in shape_moves("3-5-2", "5-3-2") if start != end]
    trails = re.findall(r'<line x1="([\d.]+)" y1="([\d.]+)" x2="([\d.]+)" y2="([\d.]+)" stroke="var\(--ma-red', still)
    assert trails == [(f"{a[0]:.1f}", f"{a[1]:.1f}", f"{b[0]:.1f}", f"{b[1]:.1f}") for a, b in moves]   # first place to second
    players = set(re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="2.3"', still))
    assert players == {(f"{x:.1f}", f"{y:.1f}") for _, (x, y, _) in shape_moves("3-5-2", "5-3-2")}   # in the second shape
    assert "○ dove partono (3-5-2)" in still


def test_the_animated_figure_and_reduced_motion():
    svg = shape_svg(INZAGHI, CHANGE)
    key = re.search(r'\[class\^="(ma-[0-9a-f]{6}-)"\] \{ animation: none !important; \}', svg).group(1)
    assert "@media (prefers-reduced-motion: reduce)" in svg
    assert all(name.startswith(key) for name in re.findall(r"@keyframes (\S+)", svg))   # all stopped by the rule
    assert all(name.startswith(key) for name in _classes(svg))
    assert svg.count(f"@keyframes {key}p") == 6                             # every outfield player who moves
    assert "40%, 65% { transform: translate(0, 0); }" in svg and "ease-in-out infinite" in svg   # held, then back
    # moving, the trails are hidden; with reduced motion (no animation) the figure is the still one
    assert svg.count(f'<line class="{key}trail"') == 6 and f"@keyframes {key}trail {{ from, to {{ opacity: 0; }} }}" in svg


def test_a_still_figure_never_shares_class_names_with_an_animated_one():
    assert not _classes(shape_svg(INZAGHI, CHANGE)) & _classes(shape_svg(INZAGHI, CHANGE, animate=False))
    assert not _classes(shape_svg(INZAGHI, CHANGE)) & _classes(shape_svg(INZAGHI, CHANGE, english=True))
    pioli = CARDS["coach_pioli"]
    assert not _classes(shape_svg(INZAGHI, CHANGE)) & _classes(shape_svg(pioli, pioli["shape_changes"][0]))


@pytest.mark.parametrize("english", [False, True])
@pytest.mark.parametrize("card_id", sorted(SHAPES))
def test_the_header_lines_are_readable_and_apart(card_id, english):
    card = CARDS[card_id]
    svg = shape_svg(card, card["shape_changes"][0], english=english)
    top = float(re.search(r'viewBox="-2 (-?[\d.]+) ', svg).group(1))
    assert min(float(s) for s in re.findall(r'font-size="([\d.]+)"', svg)) >= 3   # about 10 px on a phone
    kicker = re.search(r'<text x="0" y="(-?[\d.]+)" [^>]*font-size="([\d.]+)"[^>]*letter-spacing="([\d.]+)"[^>]*>'
                       r'([^<]+)</text>', svg)
    big = re.search(r'<text x="0" y="(-?[\d.]+)" [^>]*font-size="([\d.]+)"[^>]*>([^<]+)<tspan[^>]*font-size="([\d.]+)">'
                    r'([^<]+)</tspan>', svg)
    y_kicker, kicker_size, spacing = map(float, kicker.group(1, 2, 3))
    y_big, big_size, cue_size = float(big[1]), float(big[2]), float(big[4])
    assert top < y_kicker - kicker_size < y_kicker + 0.3 * kicker_size < y_big - big_size < y_big + 0.3 * big_size < 0
    # within the width of the pitch, reckoned generously: capitals at 0.6 of the size, the rest at 0.5
    assert len(kicker[4]) * (0.6 * kicker_size + spacing) <= 120, kicker[4]
    assert len(big[3]) * 0.5 * big_size + len(big[5]) * 0.5 * cue_size <= 120, big[3] + big[5]


def test_the_card_s_words_are_escaped():
    card = {"id": "coach_x", "title": "Profilo allenatore: A & B <C>"}
    change = {"from": "4-4-2", "to": "4-3-3", "when": 'con "palla" & <altro>', "team": "R&D",
              "quote": 'il 4-4-2 <diventa> un 4-3-3 & "altro"', "note": "<b>nota</b>"}
    svg = shape_svg(card, change)
    assert "A &amp; B &lt;C&gt;" in svg and "&lt;diventa&gt;" in svg and "&quot;altro&quot;" in svg
    assert "R&amp;D" in svg and "&lt;b&gt;nota&lt;/b&gt;" in svg and "&quot;palla&quot; &amp; &lt;altro&gt;" in svg
    assert "<C>" not in svg and "<diventa>" not in svg and "<b>" not in svg and "R&D" not in svg


def test_nothing_to_draw():
    assert shape_svg(INZAGHI, {}) == ""
    assert shape_svg(INZAGHI, {"from": "3-5-2", "to": "3-5-2", "quote": "x"}) == ""   # no change
    assert shape_svg(INZAGHI, {"from": "3-5-2", "to": "4-4-4", "quote": "x"}) == ""   # 12 players
    assert shape_svg(INZAGHI, {"from": "3-5-2", "to": "5-3-2"}) == ""                 # not the card's words


# ---------------------------------------------------------------- under an answer
@pytest.mark.parametrize("written", ["5-3-2", "5–3–2", "5 - 3 - 2", "532"])
def test_a_line_citing_the_card_and_writing_the_shape_it_becomes_draws_the_figure(written):
    answer = f"Senza palla l'Inter di Inzaghi si dispone col {written} [coach_inzaghi]."
    assert cited_shape_changes(answer, CARDS) == [("coach_inzaghi", CHANGE)]


def test_the_changes_drawn_under_an_answer():
    assert cited_shape_changes("Inzaghi ha esterni che attaccano [coach_inzaghi].", CARDS) == []   # cited, no formation
    assert cited_shape_changes("Inzaghi parte dal 3-5-2 [coach_inzaghi].", CARDS) == []   # the first shape only
    # the shape it becomes on a line citing another card: that card's, not this change
    assert cited_shape_changes("Un 5-3-2 basso protegge [situation_difendere_un_vantaggio].\n\n"
                               "Inzaghi usa gli esterni [coach_inzaghi].", CARDS) == []
    # an opening line with no citation, as the model writes it (the app, 2026-10-21)
    opening = ("L'Inter di Inzaghi difende senza palla principalmente in un 5-3-2, con i terzini che tornano in difesa.\n\n"
               "- **Fluidità tattica**: Il sistema è fluido [coach_inzaghi].")
    assert cited_shape_changes(opening, CARDS) == [("coach_inzaghi", CHANGE)]
    assert cited_shape_changes("Contro un 4-4-2 alzate il blocco.\n\nPioli: terzini nell'azione [coach_pioli].", CARDS) == []
    assert cited_shape_changes("Guardiola usa il 4-3-3 senza centravanti [coach_guardiola].", CARDS) == []   # another formation
    assert cited_shape_changes("Un 5-3-2 basso protegge il vantaggio [situation_difendere_un_vantaggio].", CARDS) == []   # not cited
    assert cited_shape_changes("Inzaghi passa al 5-3-2 senza palla.", CARDS) == []    # named, not cited
    english = "Without the ball Inzaghi's 3-5-2 becomes a 5-3-2 [coach_inzaghi]."
    assert cited_shape_changes(english, CARDS) == [("coach_inzaghi", CHANGE)]
    answer = ("Nella tesi il 4-4-2 diventa un 3-4-3 [coach_pioli, pp. 8-11]; al City si passa al 2-3-5 "
              "[coach_guardiola]; di nuovo il 4-4-2 [coach_pioli].")
    assert [i for i, _ in cited_shape_changes(answer, CARDS)] == ["coach_pioli", "coach_guardiola"]   # in order, once
    assert cited_shape_changes("Il 3-5-2 [coach_sconosciuto].", CARDS) == []        # a card that is not there

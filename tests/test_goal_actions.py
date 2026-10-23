"""The actions of the goals derived from StatsBomb (references/derived/statsbomb_goal_actions.json) and
their animation (src/ui/graphics/goal.py), offline: the derived file agrees with the cards, the script
rebuilds it as committed (when the raw events are on this computer), the SVG plays the action."""

from __future__ import annotations

import json
import re

import pytest

from scripts.build_goal_actions import EVENTS_DIR, SHORT_NAMES, goal_actions as derive
from src.corpus.cards import load_cards
from src.ui.graphics import GOAL_ACTIONS, answer_figures, goal_actions, goal_label, goal_svg, pick_goal
from src.ui.view import load_card_index

# The derived file is git-ignored (StatsBomb's licence: no redistribution of raw data); without it
# the app shows no goal action and these tests are skipped.
pytestmark = pytest.mark.skipif(not GOAL_ACTIONS.exists(), reason="python -m scripts.build_goal_actions not run here")
CARDS = load_card_index()
DATA = json.loads(GOAL_ACTIONS.read_text(encoding="utf-8")) if GOAL_ACTIONS.exists() else {"matches": {}, "attribution": ""}
MATCH_CARDS = [c for c in load_cards() if c.metadata["category"] == "match_case"]
WITH_DATA = [c for c in MATCH_CARDS if any("StatsBomb Open Data, match_id" in str(s) for s in c.metadata["sources"])]
EURO, WC22 = "case_2024_euro_final_spain_england", "case_2022_wc_final_argentina_france"


def test_the_finals_with_statsbomb_data_and_the_attribution():
    assert sorted(DATA["matches"]) == sorted(c.document_id for c in WITH_DATA) == [WC22, EURO]
    assert "Data provided by StatsBomb" in DATA["attribution"]


@pytest.mark.parametrize("card_id", [WC22, EURO])
def test_every_goal_agrees_with_the_card_s_timeline(card_id):
    told = [e for e in CARDS[card_id]["timeline"] if e["kind"] in ("goal", "penalty")]
    goals = DATA["matches"][card_id]["goals"]
    assert len(goals) == len(told)
    for goal, event in zip(goals, told):
        assert (goal["team"], goal["score"], goal["scorer"]) == (event["team"], event["score"], event["who"])
        assert goal["penalty"] == (event["kind"] == "penalty")
        steps = goal["steps"]
        assert all(0 <= s[k] <= 120 for s in steps for k in ("x", "x2")) and all(0 <= s[k] <= 80 for s in steps for k in ("y", "y2"))
        assert all(s["t0"] <= s["t1"] for s in steps) and [s["t0"] for s in steps] == sorted(s["t0"] for s in steps)
        assert steps[-1]["kind"] == "shot" and steps[-1]["player"] == goal["scorer"] and steps[-1]["x2"] >= 115
        assert all(s["player"] in SHORT_NAMES.values() for s in steps)
        assert len(steps) == 1 if goal["penalty"] else len(steps) > 1


@pytest.mark.skipif(not EVENTS_DIR.exists(), reason="the raw StatsBomb events are not on this computer")
@pytest.mark.parametrize("card_id", [WC22, EURO])
def test_the_script_rebuilds_the_committed_file(card_id):
    match = DATA["matches"][card_id]
    events = json.loads((EVENTS_DIR / f"{match['match_id']}.json").read_text(encoding="utf-8"))
    assert derive(events, {"id": card_id, "timeline": CARDS[card_id]["timeline"]}) == match["goals"]


def test_the_goal_picked_for_a_real_case_line():
    euro = goal_actions()[EURO]
    assert goal_label(pick_goal(euro, "al 47' Carvajal serve Yamal con l'esterno")) == "47' 1-0 Williams"
    assert goal_label(pick_goal(euro, "all'86' Oyarzabal")) == "86' 2-1 Oyarzabal"
    assert goal_label(pick_goal(euro, "nessun minuto")) == "47' 1-0 Williams"            # the longest action
    assert goal_label(pick_goal(euro, "Southgate inserisce Watkins e Palmer, e Palmer pareggia")) == "73' 1-1 Palmer"
    assert goal_label(pick_goal(euro, "un uno-due Oyarzabal-Cucurella e un cross rasoterra")) == "86' 2-1 Oyarzabal"
    assert goal_label(pick_goal(goal_actions()[WC22], "")) == "2° supplementare 3-2 Messi"  # no minute in the card
    assert goal_label(goal_actions()[WC22][0]) == "23' 1-0 Messi (rig.)"
    assert pick_goal([], "") is None


def test_the_action_is_drawn_and_played():
    goal = pick_goal(goal_actions()[EURO], "al 47'")
    svg = goal_svg(goal, CARDS[EURO])
    assert svg.count("<line class=") == len(goal["steps"])                  # a line per touch
    assert ">Williams</text>" in svg and 'font-weight="700"' in svg           # the scorer, named where he shoots
    assert "L&#39;AZIONE DEL GOL · FINALE EURO 2024" in svg or "L'AZIONE DEL GOL · FINALE EURO 2024" in svg
    assert "47' 1-0 Williams" in svg and "7 passaggi in 21 secondi" in svg
    assert "StatsBomb Open Data" in svg and "Accelerata 1.5 volte" in svg    # 21 s played in 14 s, and said
    assert "-ball {" in svg and "infinite" in svg and "prefers-reduced-motion" in svg and "<script" not in svg
    still = goal_svg(goal, CARDS[EURO], animate=False)
    assert "@keyframes" not in still
    shot = goal["steps"][-1]
    assert f'style="transform: translate({shot["x2"]}px, {shot["y2"]}px)"' in still   # the ball in the net
    assert "THE GOAL" in goal_svg(goal, CARDS[EURO], english=True)


def test_the_goal_goes_under_the_answer_that_cites_a_final_with_data():
    line = ("Caso reale: Colpire appena si apre lo spazio — al 47' Carvajal serve Yamal con l'esterno "
            f"[{EURO}].")
    chat = [{"role": "user", "content": "Come ha vinto la Spagna l'Europeo 2024?"},
            {"role": "assistant", "content": f"Non cambiate piano [situation_rimontare_uno_svantaggio].\n\n{line}",
             "guard": {"input": "football"}}]
    figures = answer_figures(chat, 1, CARDS)
    assert len(figures) == 2 and "ma-timeline" in figures[0] and "ma-goal" in figures[1]
    assert re.search(r"47' 1-0 Williams", figures[1])
    chat[1]["content"] = "Caso reale: [case_2026_wc_final_spain_argentina]."   # no StatsBomb data: no action
    assert ["ma-goal" in f for f in answer_figures(chat, 1, CARDS)] == [False]


def test_the_goals_of_a_real_case_for_the_picker_under_an_answer():
    from src.ui.graphics import answer_goals
    line = "Caso reale: Southgate inserisce Watkins e Palmer, e Palmer pareggia [case_2024_euro_final_spain_england]."
    chat = [{"role": "user", "content": "Come rimontiamo?"},
            {"role": "assistant", "content": "Cambiate presto [situation_rimontare_uno_svantaggio].\n\n" + line,
             "guard": {"input": "football"}}]
    [(case_id, goals, default, english)] = answer_goals(chat, 1, CARDS)
    assert case_id == EURO and [g["scorer"] for g in goals] == ["Williams", "Palmer", "Oyarzabal"]
    assert default == 1 and not english                                       # the goal its line points to
    assert "ma-goal" not in "".join(answer_figures(chat, 1, CARDS, goals=False))   # the app draws it under a picker
    assert "ma-goal" in "".join(answer_figures(chat, 1, CARDS))                    # drawn by default otherwise
    chat[1]["guard"] = {"input": "off_topic"}                                  # a question the guard stopped
    assert answer_goals(chat, 1, CARDS) == []
    chat[1]["guard"] = {"input": "football"}
    chat[1]["content"] = "Caso reale: la finale [case_2026_wc_final_spain_argentina]."   # no StatsBomb data
    assert answer_goals(chat, 1, CARDS) == []

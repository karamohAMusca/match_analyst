"""The shots of a final on the pitch (src/ui/graphics/shot_map.py), offline: the shots derived from
StatsBomb agree with the card's "Numeri" table and its timeline, the SVG, the labels, the answers it is
drawn under. Skipped without the derived file (git-ignored: StatsBomb's licence)."""

from __future__ import annotations

import json
import re

import pytest

from scripts.build_goal_actions import EVENTS_DIR, match_shots as derive
from src.ui.graphics import (GOAL_ACTIONS, answer_figures, final_numbers, match_shots, names_a_shot, numbers_svg,
                             shot_totals, shots_svg, timeline_svg)
from src.ui.graphics.shot_map import _label_places
from src.ui.view import load_card_index

pytestmark = pytest.mark.skipif(not GOAL_ACTIONS.exists(), reason="python -m scripts.build_goal_actions not run here")
CARDS = load_card_index()
EURO, WC22, WC26 = "case_2024_euro_final_spain_england", "case_2022_wc_final_argentina_france", "case_2026_wc_final_spain_argentina"
FINALS = [WC22, EURO]


def _classes(svg: str) -> set[str]:
    return set(re.findall(r'class="(ma-[0-9a-f]{6}-[\w-]+)"', svg))


def _circles(svg: str) -> list[tuple[float, float, float]]:
    """(cx, cy, r) of the circles of the shots, not the pitch's or the symbols'."""
    return [tuple(map(float, m)) for m in re.findall(r'<g class="ma-[0-9a-f]{6}-s\d+"><title>[^<]*</title>'
                                                      r'<circle cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"', svg)]


# ---------------------------------------------------------------- the data
@pytest.mark.parametrize("card_id", FINALS)
def test_the_shots_agree_with_the_numbers_of_the_card(card_id):
    numbers = final_numbers(CARDS[card_id])
    rows = {row["metric"]: row for row in numbers["rows"]}
    totals = shot_totals(match_shots()[card_id])
    for i, team in enumerate(numbers["teams"]):
        shots, on_target = rows["Tiri (in porta)"]["numbers"][i]
        assert (totals[team]["shots"], totals[team]["on_target"]) == (shots, on_target), team
        assert round(totals[team]["xg"], 2) == pytest.approx(rows["xG"]["numbers"][i][0], abs=0.011), team


@pytest.mark.parametrize("card_id", FINALS)
def test_the_goals_of_the_shots_are_the_goals_of_the_timeline(card_id):
    told = [e for e in CARDS[card_id]["timeline"] if e["kind"] in ("goal", "penalty")]
    goals = [s for s in match_shots()[card_id] if s["outcome"] == "Goal"]
    assert [(g["team"], g["player"]) for g in goals] == [(e["team"], e["who"]) for e in told]
    for goal, event in zip(goals, told):
        assert goal["minute"] == (event.get("shown") or (f"{event['minute']}'" if "minute" in event else goal["minute"]))
    assert all(0 <= s["x"] <= 120 and 0 <= s["y"] <= 80 and 0 < s["xg"] < 1 for s in match_shots()[card_id])
    assert {s["period"] for s in match_shots()[card_id]} <= {1, 2, 3, 4}          # no shoot-out
    assert [s["type"] for s in match_shots()[WC22] if s["type"] == "Penalty"].count("Penalty") == 3


@pytest.mark.skipif(not EVENTS_DIR.exists(), reason="the raw StatsBomb events are not on this computer")
@pytest.mark.parametrize("card_id", FINALS)
def test_the_script_rebuilds_the_shots_of_the_committed_file(card_id):
    data = json.loads(GOAL_ACTIONS.read_text(encoding="utf-8"))["matches"][card_id]
    events = json.loads((EVENTS_DIR / f"{data['match_id']}.json").read_text(encoding="utf-8"))
    assert derive(events, {"id": card_id, "timeline": CARDS[card_id]["timeline"]}) == data["shots"]


def test_only_the_finals_with_statsbomb_data_have_shots():
    assert sorted(match_shots()) == sorted(FINALS) and WC26 not in match_shots()


# ---------------------------------------------------------------- the figure
@pytest.mark.parametrize("card_id", FINALS)
def test_a_circle_per_shot_the_goals_filled_and_labelled(card_id):
    shots, card = match_shots()[card_id], CARDS[card_id]
    svg = shots_svg(shots, card)
    assert len(_circles(svg)) == len(shots) and svg.count("<title>") == len(shots) + 2   # a tooltip per shot, the two teams
    goals = [s for s in shots if s["outcome"] == "Goal"]
    assert svg.count('stroke="var(--ma-card,#FBE9EA)" stroke-width="0.5"/>') == len(goals)     # the goals: filled
    for goal in goals:
        assert f">{goal['minute']} {goal['player']}</text>" in svg                          # labelled where scored
    assert "Mappa dei tiri" in svg and "<script" not in svg
    assert f"scheda {card_id}" in svg and "rigori finali esclusi" in svg and "StatsBomb Open Data" in svg


def test_the_header_has_each_team_s_numbers_as_the_card_writes_them():
    svg = shots_svg(match_shots()[WC22], CARDS[WC22])
    assert ">LA MAPPA DEI TIRI · FINALE MONDIALE 2022</text>" in svg
    assert ">20 tiri (10 in porta) · xG 2.76</text>" in svg and ">10 tiri (5 in porta) · xG 2.27</text>" in svg
    assert "<title>Argentina</title>" in svg and "<title>Francia</title>" in svg           # the symbols of the teams
    english = shots_svg(match_shots()[EURO], CARDS[EURO], english=True)
    assert ">16 shots (6 on target) · xG 1.79</text>" in english and "Each team toward the goal it attacks" in english


def test_each_team_is_drawn_toward_the_goal_it_attacks():
    shots = match_shots()[EURO]
    circles = _circles(shots_svg(shots, CARDS[EURO]))
    xs_home = sorted(120 - s["x"] for s in shots if s["team"] == "Spagna")
    xs_away = sorted(s["x"] for s in shots if s["team"] == "Inghilterra")
    assert len(xs_home) == 16 and len(xs_away) == 9
    assert sorted(c[0] for c in circles) == sorted(round(x, 1) for x in xs_home + xs_away)
    assert max(xs_home) < 60 < min(xs_away)                       # the first team on the left, the other on the right


def test_the_circle_is_as_large_as_the_xg_and_the_big_ones_are_drawn_first():
    shots = match_shots()[WC22]
    svg = shots_svg(shots, CARDS[WC22])
    radii = {}
    for m in re.finditer(r'<title>([^<]*)</title><circle cx="[\d.]+" cy="[\d.]+" r="([\d.]+)"', svg):
        radii[m.group(1)] = float(m.group(2))
    penalty = next(r for t, r in radii.items() if "Messi" in t and "xG 0.78" in t)
    smallest = min(radii.values())
    assert penalty > 4 and 0.9 < smallest < 2                      # 0.78 xG a big circle, a tiny one still seen
    order = [r for _, _, r in _circles(svg)]
    goals_at_the_end = order[-6:]                                  # the goals last: drawn on top
    assert len(goals_at_the_end) == 6
    assert order[:-6] == sorted(order[:-6], reverse=True)          # the others from large to small


def test_the_tooltips_say_who_when_how_much_and_what_happened():
    svg = shots_svg(match_shots()[WC22], CARDS[WC22])
    assert "<title>23' · Messi (Argentina) · xG 0.78 · gol · rigore</title>" in svg
    assert re.search(r"<title>\d+' · [^<]+ \(Francia\) · xG 0\.\d\d · (parato|respinto|fuori)</title>", svg)
    english = shots_svg(match_shots()[WC22], CARDS[WC22], english=True)
    assert "<title>23' · Messi (Argentina) · xG 0.78 · goal · penalty</title>" in english


@pytest.mark.parametrize("english", [False, True])
@pytest.mark.parametrize("card_id", FINALS)
def test_the_goal_labels_never_overlap_and_stay_in_the_pitch(card_id, english):
    svg = shots_svg(match_shots()[card_id], CARDS[card_id], english=english)
    labels = [(float(x), float(y), text) for x, y, text in
              re.findall(r'<text class="ma-[0-9a-f]{6}-l\d+" x="([\d.]+)" y="(-?[\d.]+)"[^>]*>([^<]+)</text>', svg)]
    assert len(labels) == len([s for s in match_shots()[card_id] if s["outcome"] == "Goal"])
    boxes = [(x - len(t) * 1.65 / 2, x + len(t) * 1.65 / 2, y - 2.6, y + 0.8) for x, y, t in labels]
    for i, a in enumerate(boxes):
        assert 0 <= a[0] and a[1] <= 120 and -0.5 <= labels[i][1] <= 83, labels[i]
        for b in boxes[i + 1:]:
            assert not (a[0] < b[1] and b[0] < a[1] and a[2] < b[3] and b[2] < a[3]), (labels[i], b)


def test_three_goals_at_the_same_spot_get_three_places():
    places = _label_places([(110.0, 40.0, 4.7, "80' Mbappé"), (110.0, 40.0, 4.7, "117' Mbappé"), (110.0, 40.0, 4.7, "81' Mbappé")])
    assert len(set(places)) == 3 and all(abs(a[1] - b[1]) >= 3.4 for i, a in enumerate(places) for b in places[i + 1:])
    assert _label_places([(1.0, 40.0, 2.0, "108' Messi")])[0][0] >= 8     # near the edge: kept inside


# ---------------------------------------------------------------- motion
def test_the_shots_appear_in_the_order_they_were_taken_and_the_still_one_is_complete():
    shots, card = match_shots()[EURO], CARDS[EURO]
    moving, still = shots_svg(shots, card), shots_svg(shots, card, animate=False)
    assert "@keyframes" in moving and "prefers-reduced-motion: reduce" in moving and "animation: none !important" in moving
    assert "@keyframes" not in still and "<style>" not in still
    delays = {int(n): float(d) for n, d in re.findall(r"\.ma-[0-9a-f]{6}-s(\d+) \{[^}]*ease-out ([\d.]+)s both", moving)}
    assert sorted(delays) == list(range(len(shots)))
    ordered = [delays[n] for n in sorted(delays)]
    assert ordered == sorted(ordered) and ordered[0] < ordered[-1]      # one after the other, in the order of the match
    assert len(_circles(still)) == len(shots)                           # still: all of them
    assert not _classes(moving) & _classes(still) and not _classes(moving) & _classes(shots_svg(shots, card, english=True))


def test_the_shots_share_the_page_with_the_timeline_and_the_numbers_without_sharing_names():
    card = CARDS[EURO]
    shots, timeline, numbers = shots_svg(match_shots()[EURO], card), timeline_svg(card), numbers_svg(card)
    assert not _classes(shots) & _classes(timeline) and not _classes(shots) & _classes(numbers)
    assert not set(re.findall(r"@keyframes (\S+)", shots)) & set(re.findall(r"@keyframes (\S+)", numbers))


def test_the_text_of_the_data_is_escaped_and_nothing_to_draw_is_empty():
    shots = [{"team": "Spagna", "player": 'A<B & "C"', "minute": "10'", "period": 1, "x": 100.0, "y": 40.0, "xg": 0.2,
              "outcome": "Goal", "type": "Open Play"}]
    card = {"id": "case_x", "title": "Finale Coppa 2026: Spagna 1-0 Inghilterra"}
    svg = shots_svg(shots, card)
    assert "A&lt;B &amp; &quot;C&quot;" in svg and "A<B" not in svg
    assert shots_svg([], card) == "" and shots_svg(shots, {"title": "senza squadre"}) == ""


# ---------------------------------------------------------------- when it is drawn
@pytest.mark.parametrize("text, expected", [
    ("Quanti tiri ha fatto la Spagna?", True), ("Qual era l'xG dell'Argentina?", True), ("how many shots did Spain have", True),
    ("Quanto era alto l'expected goals?", True), ("Contro un 4-4-2 basso, i gol attesi contano", True),
    ("Come si batte il tiro in porta?", True), ("Che pressing ha fatto?", False), ("Come tiriamo i calci piazzati?", False),
    ("Il portiere para i tiratori?", False), ("", False),
])
def test_names_a_shot(text, expected):
    assert names_a_shot(text) is expected


def test_the_map_goes_under_an_answer_that_cites_a_final_and_speaks_of_the_shots():
    answer = "Abbassate il blocco [situation_difendere_un_vantaggio].\n\nCaso reale: la finale [case_2022_wc_final_argentina_france]."
    chat = [{"role": "user", "content": "Quanti tiri servono per vincere una finale?"},
            {"role": "assistant", "content": answer, "guard": {"input": "football"}}]
    kinds = [re.search(r'<figure class="ma-figure ?([\w-]*)"', f)[1] for f in answer_figures(chat, 1, CARDS)]
    assert kinds == ["ma-timeline", "ma-numbers", "ma-shots"] + (["ma-goal"] if kinds.count("ma-goal") else [])
    chat[0]["content"] = "Come difendiamo un vantaggio?"                       # no shots named: no map
    assert "ma-shots" not in "".join(answer_figures(chat, 1, CARDS))
    chat[0]["content"] = "Quanti tiri hanno fatto?"
    chat[1]["content"] = answer.replace("2022_wc_final_argentina_france", "2026_wc_final_spain_argentina")   # no StatsBomb data
    assert "ma-shots" not in "".join(answer_figures(chat, 1, CARDS))

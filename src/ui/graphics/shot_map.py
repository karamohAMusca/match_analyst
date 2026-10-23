"""The shots of a final on the pitch, from StatsBomb's events.

Every shot of the match (regular and extra time, not the shoot-out) of a final with StatsBomb event
data (scripts/build_goal_actions.py), drawn where it was taken: its circle as large as its xG, a goal
filled and labelled, a shot on target hollow with a thick line, any other hollow with a thin dashed
one. Each team is drawn toward the goal it attacks: the first team of the title (red) on the left,
the other (ink) on the right, the header above each side with its numbers. Those numbers (shots, shots
on target, xG) are the ones of the "Numeri" table of the card: a test checks that the file agrees.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from functools import lru_cache

from src.guardrails.text import normalize
from src.ui.graphics.badges import badge_width, team_badge
from src.ui.graphics.goal import GOAL_ACTIONS
from src.ui.graphics.svg import (CARD, H, INK, MUTED, RED, TEXT, TITLE_TEAMS_RE, W, esc, figcaption, figure_key,
                                 motion_style, pitch_svg)

ON_TARGET = ("Goal", "Saved", "Saved to Post")   # StatsBomb's outcomes of a shot on target
_OUTCOME_WORDS = {
    "it": {"Goal": "gol", "Saved": "parato", "Saved to Post": "parato, poi il palo", "Blocked": "respinto",
           "Off T": "fuori", "Wayward": "fuori", "Post": "palo"},
    "en": {"Goal": "goal", "Saved": "saved", "Saved to Post": "saved, then the post", "Blocked": "blocked",
           "Off T": "off target", "Wayward": "off target", "Post": "post"},
}
_TYPE_WORDS = {"it": {"Penalty": "rigore", "Free Kick": "punizione"}, "en": {"Penalty": "penalty", "Free Kick": "free kick"}}
# The words that name the shots in a question or an answer ("tiri", "xG"), without case or accents
_SHOT_WORDS = ("tiri", "tiro", "shots", "shot", "xg", "expected goals", "gol attesi", "gol previsti", "conclusioni")
_LABEL_SIZE = 3.0


@lru_cache(maxsize=1)
def match_shots() -> dict[str, list[dict]]:
    """{match card id: its shots}; empty if the derived file is missing (no StatsBomb data here)."""
    if not GOAL_ACTIONS.exists():
        return {}
    data = json.loads(GOAL_ACTIONS.read_text(encoding="utf-8"))
    return {card_id: match["shots"] for card_id, match in data["matches"].items() if match.get("shots")}


def shot_totals(shots: list[dict]) -> dict[str, dict]:
    """{team: {"shots", "on_target", "xg"}}: the numbers of the card's table, from the shots."""
    totals: dict[str, dict] = defaultdict(lambda: {"shots": 0, "on_target": 0, "xg": 0.0})
    for shot in shots:
        total = totals[shot["team"]]
        total["shots"] += 1
        total["on_target"] += shot["outcome"] in ON_TARGET
        total["xg"] += shot["xg"]
    return dict(totals)


def names_a_shot(text: str) -> bool:
    """Whether a text (the coach's question or the answer) speaks of the shots: "tiri", "tiro",
    "shots", "xG", "expected goals", "gol attesi", in whole words, without case or accents."""
    plain = normalize(text or "")
    return any(re.search(rf"(?<!\w){re.escape(word)}(?!\w)", plain) for word in _SHOT_WORDS)


def _radius(xg: float) -> float:
    """The circle of a shot: its area follows the xG, with a floor so a shot of 0.02 is still seen."""
    return 0.9 + 4.2 * math.sqrt(xg)


def _tip(shot: dict, lang: str) -> str:
    kind = _TYPE_WORDS[lang].get(shot["type"], "")
    return " · ".join(filter(None, [shot["minute"], f"{shot['player']} ({shot['team']})", f"xG {shot['xg']:.2f}",
                                   _OUTCOME_WORDS[lang].get(shot["outcome"], shot["outcome"]), kind]))


def _label_places(goals: list[tuple[float, float, float, str]]) -> list[tuple[float, float]]:
    """Where the labels of the goals go: above the circle, else below, else one row further, the first
    spot that overlaps no label already placed; inside the pitch, near the edges too."""
    placed: list[tuple[float, float, float, float]] = []   # left, right, top, bottom
    places = []
    for x, y, r, text in goals:
        width = len(text) * _LABEL_SIZE * 0.55
        centre = min(max(x, width / 2 + 0.5), W - width / 2 - 0.5)
        spots = [y - r - 1.0 - 4.2 * k for k in range(3)] + [y + r + 3.4 + 4.2 * k for k in range(3)]
        for base in spots:
            box = (centre - width / 2, centre + width / 2, base - 2.6, base + 0.8)
            if -0.5 <= base <= H + 3 and not any(box[0] < o[1] and o[0] < box[1] and box[2] < o[3] and o[2] < box[3]
                                                for o in placed):
                break
        placed.append(box)
        places.append((centre, base))
    return places


def shots_svg(shots: list[dict], card: dict, english: bool = False, animate: bool = True) -> str:
    """The shots of a final on the pitch (see the module): in the order they were taken, appearing one
    after the other, the goals labelled; every shot with a tooltip (minute, shooter, xG, outcome).
    Still: all of them. Empty without shots or without the teams of the title."""
    teams = TITLE_TEAMS_RE.search(card.get("title", ""))
    if not shots or not teams:
        return ""
    home, away = teams["home"], teams["away"]
    lang = "en" if english else "it"
    key = figure_key(card.get("id") or card.get("title"), "shots", english, animate)
    totals = shot_totals(shots)
    colour = {home: RED, away: INK}
    css, marks, goals = [], [], []
    count = max(len(shots) - 1, 1)
    # a small circle is drawn after a large one, never hidden under it
    for n, shot in sorted(enumerate(shots), key=lambda item: (item[1]["outcome"] == "Goal", -item[1]["xg"])):
        # each team toward the goal it attacks: the first team of the title on the left
        x, y = (W - shot["x"], H - shot["y"]) if shot["team"] == home else (shot["x"], shot["y"])
        r, ink, name = _radius(shot["xg"]), colour[shot["team"]], f"ma-{key}-s{n}"
        if shot["outcome"] == "Goal":
            style = f'fill="{ink}" stroke="{CARD}" stroke-width="0.5"'
            goals.append((x, y, r, f"{shot['minute']} {shot['player']}", n, ink))
        elif shot["outcome"] in ON_TARGET:
            style = f'fill="{CARD}" fill-opacity="0.6" stroke="{ink}" stroke-width="0.9"'
        else:
            style = f'fill="{CARD}" fill-opacity="0.6" stroke="{ink}" stroke-width="0.45" stroke-dasharray="0.9 0.6"'
        marks.append(f'<g class="{name}"><title>{esc(_tip(shot, lang))}</title>'
                     f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" {style}/></g>')
        if animate:   # in the order they were taken
            delay = 0.2 + 3.2 * n / count
            css.append(f".{name} {{ transform-box: fill-box; transform-origin: center; "
                       f"animation: ma-{key}-pop 0.35s ease-out {delay:.2f}s both; }}")
    labels = []
    for (x, base), (_, _, _, text, n, ink) in zip(_label_places([g[:4] for g in goals]), goals):
        labels.append(f'<text class="ma-{key}-l{n}" x="{x:.1f}" y="{base:.1f}" {TEXT} font-size="{_LABEL_SIZE}" '
                      f'font-weight="700" text-anchor="middle" fill="{INK}" stroke="{CARD}" stroke-width="0.9" '
                      f'paint-order="stroke" stroke-linejoin="round">{esc(text)}</text>')
        if animate:
            css.append(f".ma-{key}-l{n} {{ animation: ma-{key}-fade 0.35s ease-out {0.2 + 3.2 * n / count:.2f}s both; }}")
    if animate:
        css.insert(0, f"@keyframes ma-{key}-pop {{ from {{ opacity: 0; transform: scale(0.4); }} "
                      f"to {{ opacity: 1; transform: scale(1); }} }} "
                      f"@keyframes ma-{key}-fade {{ from {{ opacity: 0; }} to {{ opacity: 1; }} }}")

    def numbers(team: str) -> str:
        total = totals.get(team, {"shots": 0, "on_target": 0, "xg": 0.0})
        return (f"{total['shots']} shots ({total['on_target']} on target) · xG {total['xg']:.2f}" if english else
                f"{total['shots']} tiri ({total['on_target']} in porta) · xG {total['xg']:.2f}")

    competition = card.get("title", "").rpartition(": ")[0]
    kicker = ("THE SHOTS" if english else "LA MAPPA DEI TIRI") + (f" · {competition.upper()}" if competition else "")
    wide = badge_width(away, 4.8)
    header = (f'<text x="0" y="-14.5" {TEXT} font-size="2.8" font-weight="700" letter-spacing="0.4" fill="{MUTED}">'
              f'{esc(kicker)}</text>'
              f'{team_badge(home, 0, -12.2, 4.8)}'
              f'<text x="{badge_width(home, 4.8) + 1.4:.1f}" y="-7.8" {TEXT} font-size="4.2" font-weight="700" '
              f'fill="{RED}">{esc(home)}</text>'
              f'<text x="0" y="-3" {TEXT} font-size="3.2" fill="{INK}">{esc(numbers(home))}</text>'
              f'{team_badge(away, W - wide, -12.2, 4.8)}'
              f'<text x="{W - wide - 1.4:.1f}" y="-7.8" {TEXT} font-size="4.2" font-weight="700" text-anchor="end" '
              f'fill="{INK}">{esc(away)}</text>'
              f'<text x="{W}" y="-3" {TEXT} font-size="3.2" text-anchor="end" fill="{INK}">{esc(numbers(away))}</text>')
    legend = ("● goal · ◎ on target · ○ off target or blocked; each circle is as large as the shot's xG." if english else
              "● gol · ◎ in porta · ○ fuori o respinto; ogni cerchio è grande quanto l'xG del tiro.")
    caption = (f"{legend} Each team toward the goal it attacks. Shots, shots on target and xG as in the Numeri table of the "
               f"card {esc(card.get('id', ''))}; StatsBomb Open Data, extra time included, not the shoot-out." if english else
               f"{legend} Ogni squadra verso la porta che attacca. Tiri, tiri in porta e xG come nella tabella Numeri della "
               f"scheda {esc(card.get('id', ''))}; StatsBomb Open Data, supplementari compresi, rigori finali esclusi.")
    described = "; ".join(f"{team} {numbers(team)}" for team in (home, away))
    return (f'<figure class="ma-figure ma-shots" style="margin:0.5rem 0 0">{motion_style(css, key)}'
            f'<svg viewBox="-2 -17 124 99" role="img" aria-label="{"Shot map" if english else "Mappa dei tiri"}: '
            f'{esc(card.get("title", ""))}. {esc(described)}" style="width:100%;height:auto;display:block">'
            f'{header}{pitch_svg()}{"".join(marks)}{"".join(labels)}</svg>{figcaption(caption)}</figure>')

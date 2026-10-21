"""The action of a goal of a final with StatsBomb event data.

The touches before the goal (scripts/build_goal_actions.py): where the ball went and when, at the real
tempo of the match. The scoring team attacks left to right.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from src.core.config import PROJECT_ROOT
from src.ui.graphics.badges import badge_width, team_badge
from src.ui.graphics.svg import (CARD, INK, MUTED, RED, TEXT, TITLE_TEAMS_RE, esc, figcaption, figure_key,
                                 motion_style, pitch_svg)

GOAL_ACTIONS = PROJECT_ROOT / "references" / "derived" / "statsbomb_goal_actions.json"
_STEP_WORDS = {"it": {"pass": "passaggio", "carry": "conduzione", "shot": "tiro"},
               "en": {"pass": "pass", "carry": "carry", "shot": "shot"}}
_MAX_SECONDS = 14.0   # a longer action is played faster, and the caption says so
_HOLD_SECONDS = 1.8   # the ball rests in the net before the action starts again
_MINUTE_RE = re.compile(r"\b(\d{1,3}')")
_PERIOD_NAMES = {"it": {1: "1° tempo", 2: "2° tempo", 3: "1° supplementare", 4: "2° supplementare"},
                 "en": {1: "1st half", 2: "2nd half", 3: "1st extra half", 4: "2nd extra half"}}


@lru_cache(maxsize=1)
def goal_actions() -> dict[str, list[dict]]:
    """{match card id: its goals of play with their actions}; empty if the derived file is missing."""
    if not GOAL_ACTIONS.exists():
        return {}
    data = json.loads(GOAL_ACTIONS.read_text(encoding="utf-8"))
    return {card_id: match["goals"] for card_id, match in data["matches"].items()}


def pick_goal(goals: list[dict], line: str) -> dict | None:
    """The goal a real-case line speaks of: the one at a minute it writes ("al 47'"), else the one whose
    scorer it names ("Palmer pareggia"; the latest, if he scored twice), else the action with the most
    touches."""
    written = set(_MINUTE_RE.findall(line))
    named = [g for g in goals if re.search(rf"(?<!\w){re.escape(g['scorer'])}(?!\w)", line)]
    return (next((g for g in goals if g["minute"] in written), None) or (named[-1] if named else None)
            or max(goals, key=lambda g: len(g["steps"]), default=None))


def goal_label(goal: dict, english: bool = False) -> str:
    """'36' 2-0 Di María', with '(rig.)' for a penalty; the period when the card gives no minute."""
    when = goal["minute"] or _PERIOD_NAMES["en" if english else "it"].get(goal.get("period"), "")
    penalty = (" (rig.)" if not english else " (pen.)") if goal.get("penalty") else ""
    return f"{when} {goal['score']} {goal['scorer']}{penalty}"


def goal_svg(goal: dict, card: dict, english: bool = False, animate: bool = True) -> str:
    """The action of a goal on the pitch: the passes (solid), the carries (dashed) and the shot (thick)
    drawn as the ball travels, at the real tempo; every player who touches the ball appears when he
    does, named; the ball rests in the net, then the action plays again. Still: the whole action."""
    steps = goal.get("steps") or []
    teams = TITLE_TEAMS_RE.search(card.get("title", ""))
    if not steps or not teams:
        return ""
    lang = "en" if english else "it"
    colour = RED if goal["team"] == teams["home"] else INK
    length = steps[-1]["t1"]
    speed = max(length / _MAX_SECONDS, 1.0)
    total = length / speed + _HOLD_SECONDS
    key = figure_key(card.get("id"), goal_label(goal), english, animate)

    def pct(t: float) -> float:
        return min(100 * (t / speed) / total, 99.9)

    css, lines, dots = [], [], []
    seen: set[str] = set()
    previous = None
    for n, step in enumerate(steps):
        kind, p0, p1 = step["kind"], pct(step["t0"]), max(pct(step["t1"]), pct(step["t0"]) + 0.1)
        style = {"pass": 'stroke-width="0.45"', "carry": 'stroke-width="0.35" stroke-dasharray="1 0.8"',
                 "shot": 'stroke-width="0.9"'}[kind]
        line_class = f"ma-{key}-l{n}"
        tip = esc(f"{step['player']}: {_STEP_WORDS[lang][kind]} ({step['t0']:.1f} s)")
        # a carry keeps its dashes: it is drawn by fading in, a pass or a shot by growing along its line
        path_length = "" if kind == "carry" else ' pathLength="100"'
        lines.append(f'<line class="{line_class}" x1="{step["x"]}" y1="{step["y"]}" x2="{step["x2"]}" y2="{step["y2"]}" '
                     f'stroke="{colour}" {style} stroke-linecap="round"{path_length}><title>{tip}</title></line>')
        if animate:
            if kind == "carry":
                css.append(f"@keyframes {line_class} {{ 0%, {p0:.2f}% {{ opacity: 0; }} {p1:.2f}%, 100% {{ opacity: 1; }} }}")
            else:
                css.append(f"@keyframes {line_class} {{ 0%, {p0:.2f}% {{ stroke-dashoffset: 100; }} "
                           f"{p1:.2f}%, 100% {{ stroke-dashoffset: 0; }} }} .{line_class} {{ stroke-dasharray: 100; }}")
            css.append(f".{line_class} {{ animation: {line_class} {total:.2f}s linear infinite; }}")
        if step["player"] != previous or kind == "shot":   # a new touch: the player, where he got the ball
            dot_class = f"ma-{key}-d{n}"
            label = ""
            if step["player"] not in seen or kind == "shot":   # named once, and again where the goal is scored
                weight = ' font-weight="700"' if step["player"] == goal["scorer"] else ""
                name_y = step["y"] - 2.6 if step["y"] > 5 else step["y"] + 4.4   # under the dot near the top line
                label = (f'<text x="{step["x"]}" y="{name_y:.1f}" {TEXT} font-size="3"{weight} '
                         f'text-anchor="middle" fill="{INK}">{esc(step["player"])}</text>')
                seen.add(step["player"])
            dots.append(f'<g class="{dot_class}"><title>{tip}</title><circle cx="{step["x"]}" cy="{step["y"]}" r="1.5" '
                        f'fill="{colour}" stroke="{CARD}" stroke-width="0.5"/>{label}</g>')
            if animate:
                css.append(f"@keyframes {dot_class} {{ 0%, {p0:.2f}% {{ opacity: 0; }} {min(p0 + 1.5, 99.95):.2f}%, 100% "
                           f"{{ opacity: 1; }} }} .{dot_class} {{ animation: {dot_class} {total:.2f}s linear infinite; }}")
        previous = step["player"]

    end_x, end_y = steps[-1]["x2"], steps[-1]["y2"]
    if animate:   # the ball: at the start and at the end of every touch, at its real second
        frames = []
        for step in steps:
            frames += [(pct(step["t0"]), step["x"], step["y"]), (pct(step["t1"]), step["x2"], step["y2"])]
        frames.append((100.0, end_x, end_y))
        keyframes, last = [], -1.0
        for p, x, y in frames:
            p = max(p, last + 0.01)
            keyframes.append(f"{p:.2f}% {{ transform: translate({x}px, {y}px); }}")
            last = p
        css.append(f"@keyframes ma-{key}-ball {{ {' '.join(keyframes)} }} "
                   f".ma-{key}-ball {{ animation: ma-{key}-ball {total:.2f}s linear infinite; }}")
    ball = (f'<g class="ma-{key}-ball" style="transform: translate({end_x}px, {end_y}px)"><circle cx="0" cy="0" r="1.1" '
            f'fill="{CARD}" stroke="{INK}" stroke-width="0.45"/></g>')

    competition = card.get("title", "").rpartition(": ")[0]
    kicker = ("THE GOAL" if english else "L'AZIONE DEL GOL") + (f" · {competition.upper()}" if competition else "")
    passes = sum(s["kind"] == "pass" for s in steps)
    count = (f"{passes} passes, {length:.0f} seconds" if english else
             f"{passes} passaggi in {length:.0f} secondi") if passes else ""
    header = (f'<text x="0" y="-9" {TEXT} font-size="2.8" font-weight="700" letter-spacing="0.4" '
              f'fill="{MUTED}">{esc(kicker)}</text>'
              f'{team_badge(goal["team"], 0, -7.4, 4.8)}'
              f'<text x="{badge_width(goal["team"], 4.8) + 1.4:.1f}" y="-3.5" {TEXT} font-size="4.2" font-weight="700" '
              f'fill="{colour}">{esc(goal_label(goal, english))}'
              f'<tspan fill="{MUTED}" font-weight="500" font-size="3.2">{"  ·  " + count if count else ""}</tspan>'
              f'</text>')
    faster = (f" Played {speed:.1f} times faster." if english else f" Accelerata {speed:.1f} volte.") if speed > 1 else ""
    caption = ((f"Real positions and tempo of the ball: StatsBomb Open Data.{faster} Solid: pass · dashed: carry · "
                "thick: shot.") if english else
               (f"Posizioni e tempi reali del pallone: StatsBomb Open Data.{faster} Linea piena: passaggio · "
                "tratteggio: conduzione · spessa: tiro."))
    return (f'<figure class="ma-figure ma-goal" style="margin:0.5rem 0 0">{motion_style(css, key)}'
            f'<svg viewBox="-2 -14 124 96" role="img" aria-label="{"The goal" if english else "L&#39;azione del gol"}: '
            f'{esc(goal_label(goal, english))}" style="width:100%;height:auto;display:block">'
            f'{header}{pitch_svg()}{"".join(lines)}{"".join(dots)}{ball}</svg>'
            f"{figcaption(caption)}</figure>")

"""Derive the actions of the goals and the shots of the finals with StatsBomb event data (the raw files
stay out of the repository: references/data/statsbomb/, git-ignored, licence) into a small file the app
draws: references/derived/statsbomb_goal_actions.json.

For every goal of play (not the shoot-out) of a match card whose `sources` cite a StatsBomb match_id:
the touches of the scoring team in the last 25 seconds of the possession that ended in the goal, each
with where the ball started and ended (StatsBomb pitch, 120 x 80, the team attacking left to right),
when (seconds from the first touch kept, the real tempo) and who, by the name the cards and the
press use (`SHORT_NAMES`: "Lionel Andrés Messi Cuccittini" -> "Messi").
The minute and the score come from the card's own timeline (the n-th goal of the match), so the
animation and the timeline never disagree.

Every shot of the match too (regular and extra time, not the shoot-out: the numbers of the card's
"Numeri" table are of the match, and the file must agree with them): who, when, where the shot was
taken (the team attacking left to right), the xG, the outcome and the type. A goal has the minute of
the card; the other shots the minute of StatsBomb's event, the one in progress ("22:24" is the 23').

    python -m scripts.build_goal_actions
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from src.core.config import PROJECT_ROOT
from src.corpus.cards import load_cards

EVENTS_DIR = PROJECT_ROOT / "references" / "data" / "statsbomb" / "events"
OUT = PROJECT_ROOT / "references" / "derived" / "statsbomb_goal_actions.json"
# StatsBomb's team names (English) as the cards write them
TEAMS = {"Argentina": "Argentina", "France": "Francia", "Spain": "Spagna", "England": "Inghilterra"}
WINDOW_S = 25.0   # seconds of the possession kept before the shot
_MATCH_ID_RE = re.compile(r"StatsBomb Open Data, match_id (\d+)")


def seconds(timestamp: str) -> float:
    hours, minutes, rest = timestamp.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


# The players who touch the ball in these actions, by the name StatsBomb gives (full, both surnames)
# and the name the cards and the press use. A table, not a guess: "Daniel Olmo Carvajal" is Olmo, not
# the Carvajal of the same final; "Fabián Ruiz Peña" is Fabián Ruiz. A name missing here stops the script.
SHORT_NAMES = {
    "Adrien Rabiot": "Rabiot", "Alexis Mac Allister": "Mac Allister", "Eduardo Camavinga": "Camavinga",
    "Enzo Fernandez": "Enzo Fernández", "Gonzalo Ariel Montiel": "Montiel", "Julián Álvarez": "Álvarez",
    "Kingsley Coman": "Coman", "Kylian Mbappé Lottin": "Mbappé", "Lautaro Javier Martínez": "Lautaro Martínez",
    "Leandro Daniel Paredes": "Paredes", "Lionel Andrés Messi Cuccittini": "Messi", "Marcus Thuram": "Thuram",
    "Nahuel Molina Lucero": "Molina", "Ángel Fabián Di María Hernández": "Di María",
    "Rodrigo Javier De Paul": "De Paul", "Randal Kolo Muani": "Kolo Muani", "Youssouf Fofana": "Fofana",
    "Robin Aime Robert Le Normand": "Le Normand", "Declan Rice": "Rice", "Álvaro Borja Morata Martín": "Morata",
    "Harry Kane": "Kane", "Phil Foden": "Foden", "Ollie Watkins": "Watkins", "Marc Guehi": "Guéhi",
    "Aymeric Laporte": "Laporte", "Bukayo Saka": "Saka", "Cole Palmer": "Palmer", "Daniel Carvajal Ramos": "Carvajal",
    "Daniel Olmo Carvajal": "Olmo", "Fabián Ruiz Peña": "Fabián Ruiz", "Jordan Pickford": "Pickford",
    "Jude Bellingham": "Bellingham", "Lamine Yamal Nasraoui Ebana": "Yamal", "Marc Cucurella Saseta": "Cucurella",
    "Martín Zubimendi Ibáñez": "Zubimendi", "Mikel Oyarzabal Ugarte": "Oyarzabal", "Nicholas Williams Arthuer": "Williams",
}


def short_name(full: str) -> str:
    if full not in SHORT_NAMES:
        raise SystemExit(f"add the short name of {full!r} to SHORT_NAMES in scripts/build_goal_actions.py")
    return SHORT_NAMES[full]


def goal_actions(events: list[dict], card: dict) -> list[dict]:
    goals = [e for e in events if e["type"]["name"] == "Shot" and e["shot"]["outcome"]["name"] == "Goal"
             and e["period"] < 5]
    card_goals = [e for e in card["timeline"] if e["kind"] in ("goal", "penalty")]
    assert len(goals) == len(card_goals), (card["id"], len(goals), len(card_goals))
    actions = []
    for goal, told in zip(goals, card_goals):
        team = TEAMS[goal["team"]["name"]]
        assert team == told["team"], (card["id"], team, told)
        shot_time = seconds(goal["timestamp"])
        touches = [e for e in events if e["possession"] == goal["possession"] and e["period"] == goal["period"]
                   and e["team"]["name"] == goal["team"]["name"] and e["type"]["name"] in ("Pass", "Carry", "Shot")
                   and e.get("location") and shot_time - seconds(e["timestamp"]) <= WINDOW_S
                   and seconds(e["timestamp"]) <= shot_time]
        start = seconds(touches[0]["timestamp"])
        steps = []
        for e in touches:
            kind = e["type"]["name"].lower()
            end = e[kind]["end_location"]
            t0 = seconds(e["timestamp"]) - start
            steps.append({"kind": kind, "player": short_name(e["player"]["name"]),
                          "x": round(e["location"][0], 1), "y": round(e["location"][1], 1),
                          "x2": round(end[0], 1), "y2": round(end[1], 1),
                          "t0": round(t0, 2), "t1": round(t0 + max(e.get("duration") or 0, 0.2), 2)})
        actions.append({
            "minute": told.get("shown") or (f"{told['minute']}'" if "minute" in told else ""),
            "period": told.get("period"), "score": told["score"], "team": team,
            "scorer": told["who"], "penalty": told["kind"] == "penalty",
            "pattern": goal["play_pattern"]["name"], "steps": steps,
        })
    return actions


def match_shots(events: list[dict], card: dict) -> list[dict]:
    """Every shot of the match, in the order they were taken (the shoot-out left out): the team as the
    card writes it, the shooter's short name, the minute ("23'", the card's for a goal), the period, where
    it was taken, its xG, the outcome and the type of StatsBomb."""
    shots = [e for e in events if e["type"]["name"] == "Shot" and e["period"] < 5]
    told = iter(e for e in card["timeline"] if e["kind"] in ("goal", "penalty"))
    out = []
    for e in shots:
        shot = e["shot"]
        minute = f"{e['minute'] + 1}'"
        if shot["outcome"]["name"] == "Goal":
            goal = next(told)
            minute = goal.get("shown") or (f"{goal['minute']}'" if "minute" in goal else minute)
        out.append({"team": TEAMS[e["team"]["name"]], "player": short_name(e["player"]["name"]), "minute": minute,
                    "period": e["period"], "x": round(e["location"][0], 1), "y": round(e["location"][1], 1),
                    "xg": round(shot["statsbomb_xg"], 3), "outcome": shot["outcome"]["name"],
                    "type": shot["type"]["name"]})
    return out


def main() -> int:
    if not EVENTS_DIR.exists():
        print(f"StatsBomb events not found in {EVENTS_DIR} (see references/SOURCES.md)", file=sys.stderr)
        return 1
    out: dict = {"attribution": "Data: StatsBomb Open Data (https://github.com/hudl/open-data). "
                                "Data provided by StatsBomb. Derived: the touches before each goal and the shots.",
                 "matches": {}}
    for c in load_cards():
        if c.metadata["category"] != "match_case":
            continue
        ids = [m for s in c.metadata["sources"] for m in _MATCH_ID_RE.findall(str(s))]
        if not ids:
            continue
        card = {"id": c.document_id, "timeline": c.metadata.get("timeline") or []}
        events = json.loads((EVENTS_DIR / f"{ids[0]}.json").read_text(encoding="utf-8"))
        out["matches"][c.document_id] = {"match_id": int(ids[0]), "goals": goal_actions(events, card),
                                         "shots": match_shots(events, card)}
        match = out["matches"][c.document_id]
        print(f"{c.document_id}: {len(match['goals'])} goals, {len(match['shots'])} shots")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"written {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

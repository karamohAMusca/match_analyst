"""Build a Markdown data sheet for one match from StatsBomb Open Data (local files only).

    python -m scripts.sb_match_report <match_id> <output.md>

The output is a working document used to write match cards; it is not part of the corpus.
StatsBomb minutes are 0-indexed (the 108th minute is stored as 107): take match minutes from
Wikipedia or FIFA and use this sheet only for statistics.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from src.core.config import REFERENCES_DIR

SB = REFERENCES_DIR / "data" / "statsbomb"
PERIOD_NAMES = {1: "1st half", 2: "2nd half", 3: "ET 1st half", 4: "ET 2nd half"}
DEF_ACTIONS = {"Interception", "Foul Committed"}  # plus Duel/Tackle handled below


def load_match_meta(match_id: int) -> dict:
    for f in (SB / "matches").rglob("*.json"):
        for m in json.loads(f.read_text(encoding="utf-8")):
            if m["match_id"] == match_id:
                return m
    raise SystemExit(f"match {match_id} not found")


def mmss(e: dict) -> str:
    return f"{e['minute']}'"


def main(match_id: int, out: Path) -> None:
    meta = load_match_meta(match_id)
    ev = json.loads((SB / "events" / f"{match_id}.json").read_text(encoding="utf-8"))
    home, away = meta["home_team"]["home_team_name"], meta["away_team"]["away_team_name"]
    teams = [home, away]
    other = {home: away, away: home}

    lines = []
    w = lines.append
    w("---")
    w(f"title: Match data — {home} vs {away} ({meta['competition']['competition_name']} {meta['season']['season_name']})")
    w("source: StatsBomb Open Data")
    w(f"url: https://github.com/statsbomb/open-data (match_id {match_id})")
    w("license: StatsBomb Public Data User Agreement — research/non-commercial use, credit StatsBomb")
    w("source_type: data")
    w("note: Figures computed from StatsBomb event data. Data provided by StatsBomb.")
    w("---\n")
    w(f"# Match data: {home} {meta['home_score']}-{meta['away_score']} {away}\n")
    w(f"- **Competition**: {meta['competition']['competition_name']} {meta['season']['season_name']}, "
      f"{meta.get('competition_stage', {}).get('name', '')}")
    w(f"- **Date**: {meta['match_date']}")
    mgr = lambda side: ", ".join(x["name"] for x in meta[f"{side}_team"].get("managers", [])) or "n/a"
    w(f"- **Managers**: {home} — {mgr('home')}; {away} — {mgr('away')}")
    w("- **Data provided by StatsBomb.**\n")

    # Line-ups and formations
    w("## Starting formations and line-ups\n")
    for e in ev:
        if e["type"]["name"] == "Starting XI":
            f = e["tactics"]["formation"]
            players = ", ".join(f"{p['player']['name']} ({p['position']['name']})" for p in e["tactics"]["lineup"])
            w(f"- **{e['team']['name']}** — formation `{f}`: {players}")
    w("")

    # Timeline: goals, substitutions, tactical shifts, red cards
    w("## Timeline (goals, substitutions, formation changes, red cards)\n")
    w("| Minute | Period | Team | Event |")
    w("|---|---|---|---|")
    for e in ev:
        t, per = e["type"]["name"], e["period"]
        if per == 5:
            continue
        team, text = e["team"]["name"], None
        if t == "Shot" and e["shot"]["outcome"]["name"] == "Goal":
            text = f"GOAL — {e['player']['name']} ({e['shot']['type']['name']}, xG {e['shot'].get('statsbomb_xg', 0):.2f})"
        elif t == "Own Goal For":
            text = "GOAL (own goal)"
        elif t == "Substitution":
            text = f"Substitution — {e['player']['name']} off, {e['substitution']['replacement']['name']} on"
        elif t == "Tactical Shift":
            text = f"Formation change → `{e['tactics']['formation']}`"
        elif t in ("Foul Committed", "Bad Behaviour"):
            card = (e.get("foul_committed") or e.get("bad_behaviour") or {}).get("card", {}).get("name", "")
            if card in ("Red Card", "Second Yellow"):
                text = f"{card} — {e['player']['name']}"
        if text:
            w(f"| {mmss(e)} | {PERIOD_NAMES[per]} | {team} | {text} |")
    w("")

    # Per-period stats
    stats = defaultdict(lambda: defaultdict(float))
    for e in ev:
        per, t = e["period"], e["type"]["name"]
        if per == 5 or "team" not in e:
            continue
        team = e["team"]["name"]
        loc = e.get("location")
        for key in (per, "all"):
            s = stats[(team, key)]
            if t == "Pass":
                s["passes"] += 1
                if "outcome" not in e["pass"]:
                    s["passes_completed"] += 1
                if loc and loc[0] < 72:
                    s["passes_own_60"] += 1
                if loc and loc[0] >= 80:
                    s["passes_final_third"] += 1
            elif t == "Shot":
                s["shots"] += 1
                s["xg"] += e["shot"].get("statsbomb_xg", 0)
                if e["shot"]["outcome"]["name"] in ("Goal", "Saved", "Saved To Post"):
                    s["shots_on_target"] += 1
                if e["shot"]["outcome"]["name"] == "Goal":
                    s["goals"] += 1
            elif t == "Pressure":
                s["pressures"] += 1
                if loc and loc[0] >= 80:
                    s["pressures_att_third"] += 1
            if loc and loc[0] > 48 and (
                t in DEF_ACTIONS or (t == "Duel" and e["duel"]["type"]["name"] == "Tackle")
            ):
                s["def_actions_high"] += 1

    def row(label: str, key) -> None:
        a, b = stats[(home, key)], stats[(away, key)]
        tot_p = a["passes"] + b["passes"] or 1
        tot_f = a["passes_final_third"] + b["passes_final_third"] or 1

        def ppda(team_s, opp_s):
            return f"{opp_s['passes_own_60'] / team_s['def_actions_high']:.1f}" if team_s["def_actions_high"] else "n/a"

        for name, s, o in ((home, a, b), (away, b, a)):
            comp = f"{100 * s['passes_completed'] / s['passes']:.0f}%" if s["passes"] else "n/a"
            w(f"| {label} | {name} | {int(s['goals'])} | {int(s['shots'])} ({int(s['shots_on_target'])}) | "
              f"{s['xg']:.2f} | {int(s['passes'])} ({comp}) | {100 * s['passes'] / tot_p:.0f}% | "
              f"{100 * s['passes_final_third'] / tot_f:.0f}% | {int(s['pressures'])} ({int(s['pressures_att_third'])}) | "
              f"{ppda(s, o)} |")

    w("## Statistics by period\n")
    w("| Period | Team | Goals | Shots (on target) | xG | Passes (completion) | Pass share | Field tilt | Pressures (att. third) | PPDA |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    for per in sorted(p for p in {k[1] for k in stats} if p != "all"):
        row(PERIOD_NAMES[per], per)
    row("**Whole match**", "all")
    w("")

    # Penalty shoot-out
    pens = [e for e in ev if e["period"] == 5 and e["type"]["name"] == "Shot"]
    if pens:
        w("## Penalty shoot-out\n")
        for i, e in enumerate(pens, 1):
            w(f"{i}. {e['team']['name']} — {e['player']['name']}: {e['shot']['outcome']['name']}")
        w("")

    w("## Metric definitions\n")
    w("- **Goals** exclude penalty shoot-outs and own goals (own goals are listed in the timeline).")
    w("- **xG**: StatsBomb expected goals, summed over shots.")
    w("- **Pass share**: share of all passes in the period made by the team (a proxy for possession).")
    w("- **Field tilt**: share of all passes played from the attacking third (x ≥ 80 of 120) made by the team.")
    w("- **PPDA** (passes allowed per defensive action): opponent passes in their own 60% of the pitch divided by the "
      "team's tackles, interceptions and fouls in the opponent's 60%. Lower = more aggressive pressing.")
    w("- **Pressures**: StatsBomb pressure events; in brackets those in the attacking third.")
    w("\n_Data provided by StatsBomb (https://statsbomb.com). Figures computed for this project; "
      "they are not StatsBomb's own analysis._")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written {out}")


if __name__ == "__main__":
    main(int(sys.argv[1]), Path(sys.argv[2]))

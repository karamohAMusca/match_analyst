"""Attack the assistant with a fixed set (eval/red_team.json), and try the same attacks again after a defence.

    python -m scripts.red_team                       # offline, free, no key: the input guard on every attack,
                                                     # the output handling and the page on a hijacked answer
    python -m scripts.red_team --live                # plus the model: every attack through the bare agent and
                                                     # through the guarded one, and three control questions
    python -m scripts.red_team --live --model gpt-4.1-mini
    python -m scripts.red_team --compare <run_a.json> <run_b.json>    # the same attacks in two saved runs

The live part needs Qdrant running, the index built and OPENAI_API_KEY (about 30 calls, a few cents): the user
runs it. It is saved to eval/runs/red_team_<time>.json. "Before" is the bare agent (no guardrails): did the
model comply? "After" is the agent with its guardrails and the page: what reaches the coach, and who stopped
the rest. The controls are normal questions that must still be answered with their sources: a defence that
breaks the task went too far. An attack that no deterministic barrier stops is reported as a residual risk.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from src.core.config import PROJECT_ROOT
from src.evaluation.red_team import live_summary, load_red_team, offline_report, run_live
from src.ui import view

RUNS_DIR = PROJECT_ROOT / "eval" / "runs"


def print_offline(report: dict) -> None:
    print("OFFLINE (no model)\n")
    print(f"{'attack':18} {'input guard':12} {'expected':10}  barrier")
    for row in report["attacks"]:
        mark = "ok " if row["input_ok"] else "NO "
        probe = f" - probed: {row['probe']}" if row.get("probe") else ""
        print(f"{row['id']:18} {row['input']:12} {row['expect_input']:10} {mark} {row.get('barrier') or ''}{probe}")
    print()
    for control in report["controls"]:
        print(f"control {control['id']:16} input guard: {control['input']}")
    print(f"\ninput guard as expected: {report['input_ok']} | deterministic barriers hold: {report['barriers_hold']} | "
          f"controls reach the model: {report['controls_pass']}")
    if report["residual"]:
        print("residual risk (the model must refuse, nothing deterministic stops it): " + ", ".join(report["residual"]))
    present = [name for name, on in report["trifecta"].items() if on]
    print(f"lethal trifecta: {len(present)} of 3 present ({', '.join(present) or 'none'}): "
          + ("all three, an exfiltration is possible" if len(present) == 3 else "no exfiltration path"))


def print_live(live: dict, summary: dict, cost: float) -> None:
    print("\nLIVE (the model)\n")
    print(f"{'attack':18} {'reached':8} {'before: complied':18} {'after: clean':13} stopped by")
    for a in live["attacks"]:
        before = ", ".join(a["before"]["complied"]) or "no"
        print(f"{a['id']:18} {str(a['reached_the_model']):8} {before[:17]:18} {str(a['after']['clean']):13} {a['stopped_by']}")
    for c in live["controls"]:
        print(f"control {c['id']:16} answered: {c['answered']} | with its sources: {c['cited']}")
    print(f"\n{summary['attacks']} attacks, {summary['reached_the_model']} reached the model; the bare agent complied with "
          f"{summary['bare_complied']}; with the guardrails {summary['guarded_leaked']} reached the coach; controls "
          f"{summary['controls_ok']}/{summary['controls']}; errors {summary['errors']}; cost {cost:.4f} $")


def compare(path_a: Path, path_b: Path) -> int:
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (path_a, path_b))
    print(f"A: {path_a.name} ({a.get('model')})   B: {path_b.name} ({b.get('model')})\n")
    rows_a, rows_b = ({x["id"]: x for x in run["live"]["attacks"]} for run in (a, b))
    regressions = 0
    for attack_id in rows_b:
        before, after = rows_a.get(attack_id), rows_b[attack_id]
        if not before:
            continue
        was, now = before["after"]["clean"], after["after"]["clean"]
        note = "same" if was == now else ("FIXED" if now else "REGRESSION")
        regressions += note == "REGRESSION"
        print(f"{attack_id:18} A clean: {str(was):5}  B clean: {str(now):5}  {note}   (stopped by, B: {after['stopped_by']})")
    controls_a, controls_b = a["summary"]["controls_ok"], b["summary"]["controls_ok"]
    print(f"\ncontrols still answered with sources: A {controls_a}, B {controls_b}")
    return 1 if regressions or controls_b < controls_a else 0   # an attack that got through, or a task that broke


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="also run the attacks through the model (needs the key)")
    parser.add_argument("--model", help="OpenAI chat model (default: OPENAI_CHAT_MODEL, else gpt-4o-mini)")
    parser.add_argument("--compare", nargs=2, type=Path, metavar=("RUN_A", "RUN_B"), help="two saved live runs")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    if args.compare:
        return compare(*args.compare)

    data, cards = load_red_team(), view.load_card_index()
    report = offline_report(data, cards)
    print_offline(report)
    ok = report["input_ok"] and report["barriers_hold"] and report["controls_pass"] and not all(report["trifecta"].values())
    if not args.live:
        print("\n(add --live to run the attacks through the model)")
        return 0 if ok else 1

    os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")
    from src.agent.analyst_agent import MatchAnalyst   # after the log level is set
    from src.evaluation.cost import TokenMeter, estimate_cost

    shared: dict = {}

    def make_analyst(guardrails: bool) -> MatchAnalyst:
        analyst = MatchAnalyst(model=args.model, guardrails=guardrails, retriever=shared.get("retriever"))
        shared["retriever"] = analyst.corpus_tools.retriever
        shared["model"], shared["build"] = analyst.model, analyst.build   # the guarded one's, made last
        return analyst

    def meter(analyst: MatchAnalyst):
        counter = TokenMeter(analyst.client)
        return counter.take

    try:
        live = run_live(data, make_analyst, cards, meter)
    except (ValueError, RuntimeError) as e:   # no key, or Qdrant not reachable
        print(e)
        return 1
    summary = live_summary(live)
    cost = sum(estimate_cost(p, c, shared["model"]) for p, c in live["tokens"].values())
    print_live(live, summary, cost)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"red_team_{stamp}.json"
    out.write_text(json.dumps({"run": stamp, "model": shared["model"], "build": shared["build"], "set": data["version"],
                               "offline": report,
                               "live": live, "summary": summary, "cost_usd": round(cost, 5)},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nSaved to {out.relative_to(PROJECT_ROOT)}")
    return 0 if ok and summary["guarded_leaked"] == 0 and summary["controls_ok"] == summary["controls"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

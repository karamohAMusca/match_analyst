"""Ask the agent a set of gold questions and check the answers automatically.

    python -m scripts.eval_agent                  # default set of 8 questions (~$0.02)
    python -m scripts.eval_agent --ids Q13,Q18    # chosen questions
    python -m scripts.eval_agent --all            # whole gold set (~$0.1 with gpt-4o-mini)
    python -m scripts.eval_agent --all --model gpt-4.1-mini   # same questions, another model
    python -m scripts.eval_agent --all --no-guardrails        # bare agent, to measure the guardrails
    python -m scripts.eval_agent --all --no-verifier          # guardrails without the verifier, to measure it
    python -m scripts.eval_agent --no-trace                   # do not send traces to Phoenix
    python -m scripts.eval_agent --follow-up                  # two-turn questions (conversation memory)
    python -m scripts.eval_agent --all --follow-up            # the whole gold set, 45 questions

A question with a previous turn in the gold set (Q37 after Q13) is asked in a fresh conversation
right after that turn: besides the usual checks, the expected card must be consulted and the
previous turn must be used (the formations it named appear in the answer).

Checks per answer (no LLM judge): citations only to consulted cards, no author references used
as citations, names and numbers present in the consulted cards (grounding), correct tool use,
"Non lo so" when required, answer in the language of the question, required facts, forbidden
claims, length of advice.
The checks run on the final answer, after the guardrails; what the guardrails did (input
verdict, problems found, rewrite) is saved with it. With the guardrails on, the verifier
(src/guardrails/verifier.py, gpt-4.1-mini) checks every statement too: two more calls per
answer. Answers, checks, guardrails, model and verifier are saved to eval/runs/agent_<time>.json.
Needs Qdrant running, the index built and OPENAI_API_KEY. With Phoenix running, every question
is also a trace (project from PHOENIX_PROJECT_NAME).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter

from src.core.config import GOLD_SET_PATH, PROJECT_ROOT
from src.evaluation.answer_checks import check_answer, follow_up_problems, problems

# The 5 questions tried by hand, plus a partial abstention, a keyword question and an English one.
DEFAULT_IDS = ["Q24", "Q13", "Q15", "Q19", "Q18", "Q21", "Q31", "Q41"]
RUNS_DIR = PROJECT_ROOT / "eval" / "runs"


def guard_summary(guard: dict) -> str:
    """What the guardrails did for one question, for the progress line ('' if nothing)."""
    parts = []
    if guard.get("input") not in (None, "football"):
        parts.append(f"guard: {guard['input']}")
    if guard.get("rewritten"):
        parts.append("rewritten (" + ", ".join(dict.fromkeys(i.split(":")[0] for i in guard["issues"])) + ")")
    elif guard.get("issues"):
        parts.append("rewrite not kept" + (" (error)" if guard.get("error") else ""))
    return "".join(f"  {p}" for p in parts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", help="comma-separated question ids, e.g. Q13,Q18")
    parser.add_argument("--all", action="store_true", help="every gold question except the follow-up")
    parser.add_argument("--follow-up", action="store_true",
                        help="add the follow-up questions, each after its previous turn (with --all: all 45)")
    parser.add_argument("--model", help="OpenAI chat model (default: OPENAI_CHAT_MODEL, else gpt-4o-mini)")
    parser.add_argument("--no-guardrails", action="store_true", help="run the bare agent, without input/output guards")
    parser.add_argument("--no-verifier", action="store_true", help="keep the guardrails, without the verifier")
    parser.add_argument("--no-trace", action="store_true", help="do not send traces to Phoenix")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels

    from src.agent.analyst_agent import MatchAnalyst   # after the log level is set
    from src.core.config import load_settings
    from src.observability.tracing import flush, setup_tracing

    questions = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))["questions"]
    by_id = {q["question_id"]: q for q in questions}
    if args.all:
        selected = [q for q in questions if q["type"] != "follow_up"]   # needs a previous turn: --follow-up
    elif args.ids or not args.follow_up:
        wanted = args.ids.split(",") if args.ids else DEFAULT_IDS
        selected = [q for q in questions if q["question_id"] in wanted]
    else:
        selected = []
    if args.follow_up:   # added to the rest: --all --follow-up = the whole gold set
        selected += [q for q in questions if q.get("previous_turn") and q not in selected]

    if not args.no_trace:
        settings = load_settings()
        print(setup_tracing(settings.phoenix_endpoint, settings.phoenix_project))
    try:
        analyst = MatchAnalyst(model=args.model, guardrails=not args.no_guardrails, verify=not args.no_verifier)
    except (ValueError, RuntimeError) as e:
        print(e)
        return 1
    guardrails = "on" if analyst.guardrails else "off"
    verifier = analyst.verifier_model or "off"
    print(f"Model: {analyst.model} | guardrails: {guardrails} | verifier: {verifier}\n")

    rows = []
    for q in selected:
        previous = by_id.get(q.get("previous_turn", ""))
        assistant, first_answer = analyst, None
        if previous:   # a fresh conversation: the previous turn first, then the follow-up
            assistant = MatchAnalyst(model=args.model, guardrails=not args.no_guardrails, stateless=False,
                                     retriever=analyst.corpus_tools.retriever, verifier=analyst.verifier,
                                     verify=analyst.verifier is not None)
            first_answer = assistant.analyze(previous["question"])
        answer = assistant.analyze(q["question"])
        consulted = assistant.consulted_cards
        source_text = "\n".join(assistant.corpus_tools.retriever.card_text(c) or "" for c in consulted)
        earlier = previous["question"] if previous else ""
        check = check_answer(answer, q, consulted, len(assistant.corpus_tools.calls), source_text, earlier)
        issues = problems(check) + (follow_up_problems(answer, earlier, check) if previous else [])
        rows.append({"question_id": q["question_id"], "type": q["type"], "question": q["question"],
                     "answer": answer, "consulted": consulted,
                     "tool_calls": [dict(c) for c in assistant.corpus_tools.calls],   # copy: the list is reused
                     "guard": dict(assistant.last_guard), "check": check, "problems": issues})
        if previous:
            rows[-1].update({"previous_turn": previous["question_id"], "previous_question": previous["question"],
                             "previous_answer": first_answer})
        searches = "; ".join(
            f"{c['tool']}({c.get('query') or c.get('document_id')}"
            + (f", {c['categories']}" if c.get("categories") else "") + ")"
            for c in rows[-1]["tool_calls"]
        )
        turn = f" (after {previous['question_id']})" if previous else ""
        print(f"{q['question_id']}{turn} [{q['type']}] {'OK' if not issues else 'CHECK'}  tools: {searches or 'none'}"
              + guard_summary(assistant.last_guard) + "".join(f"\n    - {p}" for p in issues))
        if previous:
            print("    answer: " + " ".join(answer.split())[:400])

    ok = sum(1 for r in rows if not r["problems"])
    print(f"\n{ok}/{len(rows)} answers pass every automatic check ({analyst.model}, guardrails {guardrails}, "
          f"verifier {verifier}).")
    if analyst.guardrails:
        stopped = sum(1 for r in rows if r["guard"].get("input") not in (None, "football", "follow_up"))
        flagged = sum(1 for r in rows if r["guard"].get("issues"))
        rewritten = sum(1 for r in rows if r["guard"].get("rewritten"))
        print(f"Guardrails: {stopped} questions answered without the model, {flagged} answers with "
              f"problems, {rewritten} rewritten.")
    kinds = Counter(p.split(":")[0] for r in rows for p in r["problems"])
    for kind, n in kinds.most_common():
        print(f"  {n:3}  {kind}")
    flush()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"agent_{stamp}.json"
    run = {"run": stamp, "model": analyst.model, "guardrails": analyst.guardrails,
           "verifier": analyst.verifier_model, "questions": rows}
    out.write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Answers saved to {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

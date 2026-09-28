"""Ask the agent a set of gold questions and check the answers automatically.

    python -m scripts.eval_agent                  # default set of 8 questions (~$0.02)
    python -m scripts.eval_agent --ids Q13,Q18    # chosen questions
    python -m scripts.eval_agent --all            # whole gold set (~$0.1 with gpt-4o-mini)
    python -m scripts.eval_agent --all --model gpt-4.1-mini   # same questions, another model

Checks per answer (no LLM judge): citations only to consulted cards, no author references used
as citations, names and numbers present in the consulted cards (grounding), correct tool use,
"Non lo so" when required, answer in the language of the question, required facts, forbidden
claims, length of advice.
Answers, checks and the model name are saved to eval/runs/agent_<time>.json.
Needs Qdrant running, the index built and OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter

from src.core.config import GOLD_SET_PATH, PROJECT_ROOT
from src.evaluation.answer_checks import check_answer, problems

# The 5 questions tried by hand, plus a partial abstention, a keyword question and an English one.
DEFAULT_IDS = ["Q24", "Q13", "Q15", "Q19", "Q18", "Q21", "Q31", "Q41"]
RUNS_DIR = PROJECT_ROOT / "eval" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ids", help="comma-separated question ids, e.g. Q13,Q18")
    parser.add_argument("--all", action="store_true", help="every gold question except the follow-up")
    parser.add_argument("--model", help="OpenAI chat model (default: OPENAI_CHAT_MODEL, else gpt-4o-mini)")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels

    from src.agent.analyst_agent import MatchAnalyst   # after the log level is set

    questions = json.loads(GOLD_SET_PATH.read_text(encoding="utf-8"))["questions"]
    if args.all:
        selected = [q for q in questions if q["type"] != "follow_up"]   # needs a previous turn
    else:
        wanted = args.ids.split(",") if args.ids else DEFAULT_IDS
        selected = [q for q in questions if q["question_id"] in wanted]

    try:
        analyst = MatchAnalyst(model=args.model)
    except (ValueError, RuntimeError) as e:
        print(e)
        return 1
    print(f"Model: {analyst.model}\n")

    rows = []
    for q in selected:
        answer = analyst.analyze(q["question"])
        consulted = analyst.consulted_cards
        source_text = "\n".join(analyst.corpus_tools.retriever.card_text(c) or "" for c in consulted)
        check = check_answer(answer, q, consulted, len(analyst.corpus_tools.calls), source_text)
        issues = problems(check)
        rows.append({"question_id": q["question_id"], "type": q["type"], "question": q["question"],
                     "answer": answer, "consulted": consulted,
                     "tool_calls": [dict(c) for c in analyst.corpus_tools.calls],   # copy: the list is reused
                     "check": check, "problems": issues})
        searches = "; ".join(
            f"{c['tool']}({c.get('query') or c.get('document_id')}"
            + (f", {c['categories']}" if c.get("categories") else "") + ")"
            for c in rows[-1]["tool_calls"]
        )
        print(f"{q['question_id']} [{q['type']}] {'OK' if not issues else 'CHECK'}  tools: {searches or 'none'}"
              + "".join(f"\n    - {p}" for p in issues))

    ok = sum(1 for r in rows if not r["problems"])
    print(f"\n{ok}/{len(rows)} answers pass every automatic check ({analyst.model}).")
    kinds = Counter(p.split(":")[0] for r in rows for p in r["problems"])
    for kind, n in kinds.most_common():
        print(f"  {n:3}  {kind}")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"agent_{stamp}.json"
    out.write_text(json.dumps({"run": stamp, "model": analyst.model, "questions": rows}, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"Answers saved to {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

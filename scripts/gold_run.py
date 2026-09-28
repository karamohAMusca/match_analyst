"""Gold run: the agent on the gold set, judged by an LLM, with retrieval, latency and cost.

    python -m scripts.gold_run                          # gpt-4o-mini, guardrails on (~$0.2)
    python -m scripts.gold_run --tag baseline           # label of the run (in Phoenix and in the file)
    python -m scripts.gold_run --model gpt-4.1-mini     # another model for the agent
    python -m scripts.gold_run --no-guardrails          # the bare agent
    python -m scripts.gold_run --ids Q13,Q17,Q35        # some questions only
    python -m scripts.gold_run --rejudge eval/runs/agent_20260928-175508.json --judge-model gpt-4.1-mini
                                                        # same saved answers, another judge (judge cost only)
    python -m scripts.gold_run --faithfulness holistic  # one faithfulness score per answer, not per statement

Prints the metrics table, the detail per question (`<` = faithfulness or relevancy below 0.7)
and what to try for each low metric; saves everything to eval/runs/gold_<time>.json.
With Phoenix running, the whole run is one trace ("gold_run <tag>") with every question inside.
The judge is a separate client, gpt-4o-mini unless --judge-model says otherwise, and the same for
every run whatever the agent's model: scores are comparable only with the same judge. Its cost is
reported apart from the cost of the answers.
--rejudge replays the answers of a saved run (a gold run or an eval_agent run) instead of asking
the agent: faithfulness is judged on the cards that run consulted, so two judges can be compared
on exactly the same answers. Latency and cost of the answers are not re-measured.
Needs Qdrant running, the index built and OPENAI_API_KEY.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from src.core.config import PROJECT_ROOT

RUNS_DIR = PROJECT_ROOT / "eval" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="gold", help="label of the run, e.g. baseline")
    parser.add_argument("--model", help="agent model (default: OPENAI_CHAT_MODEL, else gpt-4o-mini)")
    parser.add_argument("--judge-model", help="judge model (default: gpt-4o-mini, the same for every run)")
    parser.add_argument("--no-guardrails", action="store_true", help="run the bare agent")
    parser.add_argument("--ids", help="comma-separated question ids, e.g. Q13,Q17")
    parser.add_argument("--rejudge", help="saved run to judge again (eval/runs/gold_*.json or agent_*.json)")
    parser.add_argument("--faithfulness", choices=["claims", "holistic"], default="claims",
                        help="judge faithfulness statement by statement (default) or with one score")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels

    from datapizza.clients.openai import OpenAIClient

    from src.agent.analyst_agent import MatchAnalyst, build_retriever
    from src.core.config import load_settings, require_openai_key
    from src.evaluation.cost import TokenMeter, estimate_cost
    from src.evaluation.gold_run import REMINDER, detail, load_gold, replay, run, score, summary, table, unsupported
    from src.evaluation.judge import DEFAULT_JUDGE_MODEL, JUDGE_MAX_RETRIES, JUDGE_TEMPERATURE, JUDGE_TIMEOUT_S
    from src.observability.tracing import flush, setup_tracing, tag_run
    from src.tools.corpus_tools import card_context

    settings = load_settings()
    print(setup_tracing(settings.phoenix_endpoint, settings.phoenix_project))
    gold = load_gold(ids=args.ids.split(",") if args.ids else None)
    source = json.loads(Path(args.rejudge).read_text(encoding="utf-8")) if args.rejudge else None
    try:
        if source is None:
            analyst = MatchAnalyst(model=args.model, guardrails=not args.no_guardrails)
            retriever, agent_model, guardrails_on = analyst.corpus_tools.retriever, analyst.model, analyst.guardrails
        else:
            retriever = build_retriever()
            agent_model, guardrails_on = source.get("model") or "gpt-4o-mini", source.get("guardrails", True)
        judge_model = args.judge_model or DEFAULT_JUDGE_MODEL   # never the agent's model by accident
        judge = OpenAIClient(api_key=require_openai_key(), model=judge_model, temperature=JUDGE_TEMPERATURE,
                             timeout=JUDGE_TIMEOUT_S, max_retries=JUDGE_MAX_RETRIES)
    except (ValueError, RuntimeError) as e:
        print(e)
        return 1
    judged = TokenMeter(judge)

    def context_of(consulted: list[str]) -> str:
        return card_context({c: retriever.card_text(c) or "" for c in consulted})

    if source is None:
        answers = TokenMeter(analyst.client)

        def answer_fn(question: str, k: int = 5) -> SimpleNamespace:
            text = analyst.analyze(question)
            prompt, completion = answers.take()
            consulted = analyst.consulted_cards
            return SimpleNamespace(text=text, consulted=consulted, context=context_of(consulted) or None,
                                   usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion))
    else:
        answer_fn = replay(source.get("rows") or source["questions"], context_of)
        gold = [g for g in gold if g["q"] in answer_fn.questions]
        if not any((r.get("consulted") is not None) for r in source.get("rows") or source["questions"]):
            print("Note: this run did not save the consulted cards: faithfulness is judged on the retrieved chunks.")

    def retrieve_fn(question: str, k: int = 5) -> list:
        return retriever.retrieve(question, k=k)

    guardrails = "on" if guardrails_on else "off"
    origin = f" | answers replayed from {Path(args.rejudge).name}" if source else ""
    print(f"Gold run '{args.tag}': {len(gold)} questions {summary(gold)} | model {agent_model} | "
          f"judge {judge_model} ({args.faithfulness}) | guardrails {guardrails}{origin}\n")
    with tag_run(args.tag):
        metrics, rows = run(answer_fn, retrieve_fn, gold, judge, model=agent_model, faithfulness=args.faithfulness,
                            progress=lambda f: print(f"\r  {f * 100:5.1f}%", end=""))
    flush()
    if source is not None:
        metrics["replayed"] = True
    judge_cost = estimate_cost(*judged.take(), judge_model)

    print("\n\n" + table(metrics))
    print(f"{'judge cost':24s} : ${judge_cost:.4f}\n")
    print(detail(rows) + "\n")
    print(unsupported(rows) + "\n")
    print(REMINDER)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"gold_{stamp}.json"
    record = {"run": stamp, "tag": args.tag, "model": agent_model, "judge_model": judge_model,
              "faithfulness_method": args.faithfulness,
              "guardrails": guardrails_on, "rejudged_from": args.rejudge, "metrics": metrics,
              "score": score(metrics), "judge_cost_usd": judge_cost, "rows": rows}
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRun saved to {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

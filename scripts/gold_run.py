"""Gold run: the agent on the gold set, judged by an LLM, with retrieval, latency and cost.

    python -m scripts.gold_run                          # gpt-4o-mini, guardrails on (~$0.2)
    python -m scripts.gold_run --tag baseline           # label of the run (in Phoenix and in the file)
    python -m scripts.gold_run --model gpt-4.1-mini     # another model for the agent
    python -m scripts.gold_run --no-guardrails          # the bare agent
    python -m scripts.gold_run --verifier               # with the verifier (off by default)
    python -m scripts.gold_run --ids Q13,Q17,Q35        # some questions only
    python -m scripts.gold_run --rejudge eval/runs/agent_20260928-175508.json --judge-model gpt-4.1-mini
                                                        # same saved answers, another judge (judge cost only)
    python -m scripts.gold_run --faithfulness holistic  # one faithfulness score per answer, not per statement
    python -m scripts.gold_run --rejudge <run> --no-judge-cache   # ask the judge again, even for saved verdicts

Prints the metrics table, the detail per question (`<` = faithfulness or relevancy below 0.7)
and what to try for each low metric; saves everything to eval/runs/gold_<time>.json.
With Phoenix running, the whole run is one trace ("gold_run <tag>") with every question inside.
The judge is a separate client, gpt-4.1-mini unless --judge-model says otherwise, and the same for
every run whatever the agent's model: scores are comparable only with the same judge. Its cost is
reported apart from the cost of the answers. Both clients are built by datapizza's ClientFactory:
--judge-provider picks another provider for the judge (its datapizza client package installed and
its key in .env as <PROVIDER>_API_KEY; the timeout and retries are the OpenAI client's options).
The judge's verdicts are saved in .cache/ (src/core/disk_cache.py): a re-judge stopped halfway
starts again without paying the verdicts it already has, and the same answers get the same
verdicts; --no-judge-cache asks the judge again (e.g. to see how much its verdicts vary).
--rejudge replays the answers of a saved run (a gold run or an eval_agent run) instead of asking
the agent: faithfulness is judged on the cards that run consulted, so two judges can be compared
on exactly the same answers. Latency and cost of the answers are not re-measured.
With --verifier, the verifier (src/guardrails/verifier.py) checks every statement of every
answer: its calls are in the cost of the answers, priced with its own model. Its method and model are
the judge's, so a run judged by gpt-4.1-mini favours it: re-judge the same run with --judge-model
gpt-4.1 to compare.
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

from src.core.config import CACHE_DIR, PROJECT_ROOT

RUNS_DIR = PROJECT_ROOT / "eval" / "runs"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tag", default="gold", help="label of the run, e.g. baseline")
    parser.add_argument("--model", help="agent model (default: OPENAI_CHAT_MODEL, else gpt-4o-mini)")
    parser.add_argument("--judge-model", help="judge model (default: gpt-4.1-mini, the same for every run)")
    parser.add_argument("--no-guardrails", action="store_true", help="run the bare agent")
    parser.add_argument("--verifier", action="store_true", help="add the verifier (off by default)")
    parser.add_argument("--ids", help="comma-separated question ids, e.g. Q13,Q17")
    parser.add_argument("--rejudge", help="saved run to judge again (eval/runs/gold_*.json or agent_*.json)")
    parser.add_argument("--faithfulness", choices=["claims", "holistic"], default="claims",
                        help="judge faithfulness statement by statement (default) or with one score")
    parser.add_argument("--judge-provider", default="openai",
                        help="provider of the judge for datapizza's ClientFactory (default: openai)")
    parser.add_argument("--no-judge-cache", action="store_true",
                        help="ask the judge again even for the verdicts saved in .cache/")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")
    os.environ.setdefault("DATAPIZZA_AGENT_LOG_LEVEL", "WARNING")   # no agent log panels

    from datapizza.clients import ClientFactory

    from src.agent.analyst_agent import MatchAnalyst, build_retriever
    from src.core.config import load_settings, require_api_key
    from src.core.disk_cache import DiskCache
    from src.evaluation.cost import PRICES, TokenMeter, estimate_cost
    from src.evaluation.gold_run import REMINDER, detail, load_gold, replay, run, score, summary, table, unsupported
    from src.evaluation.judge import (DEFAULT_JUDGE_MODEL, JUDGE_MAX_RETRIES, JUDGE_OUTPUTS, JUDGE_TEMPERATURE,
                                      JUDGE_TIMEOUT_S)
    from src.observability.tracing import flush, setup_tracing, tag_run
    from src.tools.corpus_tools import card_context

    settings = load_settings()
    print(setup_tracing(settings.phoenix_endpoint, settings.phoenix_project))
    gold = load_gold(ids=args.ids.split(",") if args.ids else None)
    source = json.loads(Path(args.rejudge).read_text(encoding="utf-8")) if args.rejudge else None
    try:
        if source is None:
            analyst = MatchAnalyst(model=args.model, guardrails=not args.no_guardrails, verify=args.verifier)
            retriever, agent_model, guardrails_on = analyst.corpus_tools.retriever, analyst.model, analyst.guardrails
            verifier_model, build = analyst.verifier_model, analyst.build
        else:
            retriever = build_retriever()
            agent_model, guardrails_on = source.get("model") or "gpt-4o-mini", source.get("guardrails", True)
            verifier_model, build = source.get("verifier"), source.get("build")   # the answers' own version
        judge_model = args.judge_model or DEFAULT_JUDGE_MODEL   # never the agent's model by accident
        cache = None if args.no_judge_cache else DiskCache(CACHE_DIR / f"judge_{judge_model}.json", JUDGE_OUTPUTS)
        judge = ClientFactory.create(provider=args.judge_provider, api_key=require_api_key(args.judge_provider),
                                     model=judge_model, temperature=JUDGE_TEMPERATURE, cache=cache,
                                     timeout=JUDGE_TIMEOUT_S, max_retries=JUDGE_MAX_RETRIES)
    except (ValueError, RuntimeError, ImportError) as e:   # ImportError: provider package not installed
        print(e)
        return 1
    judged = TokenMeter(judge)

    def context_of(consulted: list[str]) -> str:
        return card_context({c: retriever.card_text(c) or "" for c in consulted})

    if source is None:
        answers = TokenMeter(analyst.client)
        checks = TokenMeter(analyst.verifier) if analyst.verifier is not None else None

        def answer_fn(question: str, k: int = 5) -> SimpleNamespace:
            text = analyst.analyze(question)
            prompt, completion = answers.take()
            checked = checks.take() if checks else (0, 0)
            cost = estimate_cost(prompt, completion, agent_model) + estimate_cost(*checked, verifier_model or "")
            consulted = analyst.consulted_cards
            return SimpleNamespace(text=text, consulted=consulted, context=context_of(consulted) or None,
                                   usage=SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion),
                                   cost_usd=cost)
    else:
        answer_fn = replay(source.get("rows") or source["questions"], context_of)
        gold = [g for g in gold if g["q"] in answer_fn.questions]
        if not any((r.get("consulted") is not None) for r in source.get("rows") or source["questions"]):
            print("Note: this run did not save the consulted cards: faithfulness is judged on the retrieved chunks.")

    def retrieve_fn(question: str, k: int = 5) -> list:
        return retriever.retrieve(question, k=k)

    guardrails = "on" if guardrails_on else "off"
    origin = f" | answers replayed from {Path(args.rejudge).name}" if source else ""
    judge_name = judge_model if args.judge_provider == "openai" else f"{args.judge_provider}/{judge_model}"
    print(f"Gold run '{args.tag}': {len(gold)} questions {summary(gold)} | model {agent_model} | "
          f"judge {judge_name} ({args.faithfulness}) | guardrails {guardrails} | verifier {verifier_model or 'off'}"
          f"{origin}\n")
    with tag_run(args.tag):
        metrics, rows = run(answer_fn, retrieve_fn, gold, judge, model=agent_model, faithfulness=args.faithfulness,
                            progress=lambda f: print(f"\r  {f * 100:5.1f}%", end=""))
    flush()
    if source is not None:
        metrics["replayed"] = True
    judge_cost = estimate_cost(*judged.take(), judge_model)
    cached = cache.hits if cache else 0
    notes = ([f"{cached} judge calls answered by the cache, not paid"] if cached else []) + (
        [] if judge_model in PRICES else ["model not in the price list of src/evaluation/cost.py"])

    print("\n\n" + table(metrics))
    print(f"{'judge cost':24s} : ${judge_cost:.4f}" + (f" ({'; '.join(notes)})" if notes else "") + "\n")
    print(detail(rows) + "\n")
    print(unsupported(rows) + "\n")
    print(REMINDER)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"gold_{stamp}.json"
    record = {"run": stamp, "tag": args.tag, "model": agent_model, "judge_provider": args.judge_provider,
              "judge_model": judge_model, "faithfulness_method": args.faithfulness,
              "guardrails": guardrails_on, "verifier": verifier_model, "build": build, "rejudged_from": args.rejudge,
              "metrics": metrics,
              "score": score(metrics), "judge_cost_usd": judge_cost, "judge_cache_hits": cached, "rows": rows}
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRun saved to {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

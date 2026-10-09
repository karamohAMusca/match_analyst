"""Gold run: the whole system measured on the fixed gold set, with one set of metrics.

    recall@1 · recall@5 · MRR · faithfulness · relevancy · abstention_out_of_corpus
    latency_p50_s · latency_p95_s · cost_per_query_usd · cost_run_usd

Contract of the functions passed to `run()` (no global state):
    answer_fn(question, k) -> object with .text and .usage (.prompt_tokens, .completion_tokens);
                              optional .context: the text of the cards the agent consulted,
                              and .consulted: their ids (saved, so the run can be re-judged)
    retrieve_fn(question, k) -> chunks with .metadata["document_id"]
    judge_llm                -> client for the judges (src/evaluation/judge.py)

Retrieval metrics use one call with a wide pool (k=10) for recall@1, recall@5 and MRR, on the
first expected card of each question (the entry point, for multi-card questions).
Faithfulness (default: claim by claim, see judge.py) is judged on the context the agent actually retrieved (`.context`: the cards it
consulted through its tools, possibly with several searches); if answer_fn gives none, on the
top-k chunks of retrieve_fn.
Gold set format: `load_gold()` turns eval/gold_set.json into {q, source, ref} (source=None for
out-of-corpus questions, measured by abstention) plus id, type, sources, language.
Off-topic, chitchat and follow-up questions test the guardrails and the conversation: they are
measured by scripts/eval_agent.py, not here.
"""

from __future__ import annotations

import json
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.core.config import GOLD_SET_PATH
from src.evaluation.cost import estimate_cost
from src.evaluation.judge import judge_faithfulness, judge_faithfulness_claims, judge_relevancy
from src.guardrails.output_guard import ABSTENTION

NO_SOURCE_TYPES = {"out_of_corpus"}
SKIPPED_TYPES = {"off_topic", "chitchat", "follow_up"}
THRESHOLD = 0.7   # rows below it are marked in the detail


# ============================ GOLD SET ======================================
def load_gold(path: Path | str = GOLD_SET_PATH, ids: list[str] | None = None) -> list[dict]:
    """The gold questions in the form used by `run()`; `ids` keeps only those questions."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for q in raw["questions"]:
        if q["type"] in SKIPPED_TYPES or (ids and q["question_id"] not in ids):
            continue
        sources = q.get("relevant_sources") or []
        out.append({
            "q": q["question"],
            "source": sources[0] if sources and q["type"] not in NO_SOURCE_TYPES else None,
            "ref": q.get("expected_answer", ""),
            "id": q["question_id"],
            "type": q["type"],
            "sources": sources,
            "language": q.get("language", "it"),
        })
    return out


def summary(gold: list[dict]) -> dict[str, int]:
    """Questions per type."""
    counts: dict[str, int] = {}
    for g in gold:
        counts[g["type"]] = counts.get(g["type"], 0) + 1
    return counts


# ============================ GOLD RUN ======================================
def _abstained(answer: str) -> bool:
    text = answer.lower()
    return any(a in text for a in ABSTENTION)


def run(
    answer_fn: Callable[..., Any],
    retrieve_fn: Callable[..., list] | None,
    gold: list[dict],
    judge_llm: Any,
    k: int = 5,
    model: str = "gpt-4o-mini",
    progress: Callable[[float], None] | None = None,
    faithfulness: str = "claims",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the gold set through the system; returns (metrics, one detail row per question).

    `faithfulness`: "claims" (statement by statement) or "holistic" (one score per answer).
    """
    in_corpus = [g for g in gold if g["source"]]
    r1 = r5 = 0
    mrr_sum = 0.0
    faith: list[float] = []
    rel: list[float] = []
    times: list[float] = []
    costs: list[float] = []
    n_out = abstained = judge_errors = 0
    rows = []

    for i, g in enumerate(gold):
        if progress:
            progress(i / max(1, len(gold)))
        t0 = time.perf_counter()
        resp = answer_fn(g["q"], k=k)
        times.append(time.perf_counter() - t0)
        answer = getattr(resp, "text", "") or ""
        usage = getattr(resp, "usage", None)
        cost = getattr(resp, "cost_usd", None)   # given when the answer used more than one model (verifier)
        costs.append(cost if cost is not None else estimate_cost(getattr(usage, "prompt_tokens", 0) or 0,
                                                                 getattr(usage, "completion_tokens", 0) or 0, model))
        hits = retrieve_fn(g["q"], k=10) if retrieve_fn else []   # wide pool: r@1, r@5 and MRR
        found = [h.metadata.get("document_id") for h in hits]
        row: dict[str, Any] = {"id": g["id"], "type": g["type"], "question": g["q"],
                               "latency_s": round(times[-1], 2), "cost_usd": round(costs[-1], 6),
                               "answer": answer, "ref": g["ref"], "consulted": getattr(resp, "consulted", None)}
        if g["source"]:
            rank = found.index(g["source"]) + 1 if g["source"] in found else None
            r1 += g["source"] in found[:1]
            r5 += g["source"] in found[:5]
            mrr_sum += (1.0 / rank) if rank else 0.0
            context = getattr(resp, "context", None) or "\n\n".join(
                f"[{h.metadata.get('document_id', '?')}]\n{h.text}" for h in hits[:k]) or "(no context retrieved)"
            f = (judge_faithfulness_claims(judge_llm, context, answer, g["q"]) if faithfulness == "claims"
                 else judge_faithfulness(judge_llm, context, answer))
            r = judge_relevancy(judge_llm, g["q"], answer)
            for verdict, scores in ((f, faith), (r, rel)):       # a judge error is left out, and counted
                if verdict.get("error"):
                    judge_errors += 1
                else:
                    scores.append(verdict["score"])
            row.update({"expected_source": g["source"], "found": bool(rank), "rank": rank,
                        "faithfulness": None if f.get("error") else round(f["score"], 2),
                        "relevancy": None if r.get("error") else round(r["score"], 2),
                        "faithfulness_reason": f["reason"], "relevancy_reason": r["reason"]})
            if "claims" in f:
                row["faithfulness_claims"] = f["claims"]
        else:
            n_out += 1
            did_abstain = _abstained(answer)
            abstained += did_abstain
            row.update({"expected_source": None, "abstained": did_abstain})
        rows.append(row)

    if progress:
        progress(1.0)
    ordered = sorted(times)
    p95 = ordered[min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))] if ordered else 0.0
    metrics = {
        "recall@1": r1 / len(in_corpus) if in_corpus else 0.0,
        "recall@5": r5 / len(in_corpus) if in_corpus else 0.0,
        "MRR": mrr_sum / len(in_corpus) if in_corpus else 0.0,
        "faithfulness": sum(faith) / len(faith) if faith else 0.0,
        "relevancy": sum(rel) / len(rel) if rel else 0.0,
        "judge_errors": judge_errors,
        "abstention_out_of_corpus": abstained / n_out if n_out else None,
        "latency_p50_s": statistics.median(times) if times else 0.0,
        "latency_p95_s": p95,
        "cost_per_query_usd": sum(costs) / len(costs) if costs else 0.0,
        "cost_run_usd": sum(costs),
    }
    return metrics, rows


def score(metrics: dict[str, Any]) -> float:
    """One number to compare runs: the mean of faithfulness and relevancy. Only quality: latency
    and cost stay out, or a shorter, emptier answer could look like an improvement."""
    return (metrics["faithfulness"] + metrics["relevancy"]) / 2


def replay(saved_rows: list[dict[str, Any]], context_of: Callable[[list[str]], str]) -> Callable[..., Any]:
    """An answer_fn that returns the answers of a saved run instead of asking the agent: to judge
    the same answers with another judge. Works with gold runs and with eval_agent runs (both save
    the answer and the consulted cards). No latency and no cost: they belong to the original run."""
    by_question = {r["question"]: r for r in saved_rows}

    def answer_fn(question: str, k: int = 5) -> Any:
        saved = by_question[question]
        consulted = saved.get("consulted") or []
        return SimpleNamespace(text=saved["answer"], consulted=consulted, context=context_of(consulted) or None,
                               usage=SimpleNamespace(prompt_tokens=0, completion_tokens=0))

    answer_fn.questions = set(by_question)   # type: ignore[attr-defined]
    return answer_fn


def table(metrics: dict[str, Any]) -> str:
    """The metrics as aligned text (latency and cost "n/a" for a re-judged run)."""
    abstention = metrics["abstention_out_of_corpus"]
    replayed = metrics.get("replayed", False)
    lines = [
        ("recall@1", f"{metrics['recall@1']:.2f}"),
        ("recall@5", f"{metrics['recall@5']:.2f}"),
        ("MRR", f"{metrics['MRR']:.3f}"),
        ("faithfulness", f"{metrics['faithfulness']:.2f}"),
        ("relevancy", f"{metrics['relevancy']:.2f}"),
        ("abstention out of corpus", "—" if abstention is None else f"{abstention:.0%}"),
        ("latency p50 / p95", "n/a (re-judged)" if replayed
         else f"{metrics['latency_p50_s']:.2f}s / {metrics['latency_p95_s']:.2f}s"),
        ("cost per query", "n/a (re-judged)" if replayed else f"${metrics['cost_per_query_usd']:.5f}"),
        ("cost of the run", "n/a (re-judged)" if replayed else f"${metrics['cost_run_usd']:.4f}"),
        ("SCORE (faith+rel)/2", f"{score(metrics):.3f}"),
    ]
    if metrics.get("judge_errors"):
        lines.append(("judge errors (left out)", str(metrics["judge_errors"])))
    width = max(len(a) for a, _ in lines)
    return "\n".join(f"{a:{width}s} : {b}" for a, b in lines)


def detail(rows: list[dict[str, Any]], threshold: float = THRESHOLD) -> str:
    """One line per question; `<` marks faithfulness or relevancy below `threshold`."""
    out = [f"{'id':4s} {'type':14s} {'src':4s} {'rank':>4s} {'faith':>6s} {'rel':>6s} {'lat':>6s}  question",
           "-" * 108]
    for d in rows:
        f, r = d.get("faithfulness"), d.get("relevancy")
        below = any(isinstance(v, (int, float)) and v < threshold for v in (f, r))
        if d.get("expected_source"):
            src, rank = ("OK" if d["found"] else "NO"), str(d["rank"] or "—")
            scores = " ".join(f"{v:>6.2f}" if v is not None else f"{'err':>6s}" for v in (f, r))
        else:
            src, rank = "—", "—"
            scores = f"{'—':>6s} {('abst.' if d['abstained'] else 'NO ABS'):>6s}"
        out.append(f"{d['id']:4s} {d['type']:14s} {src:4s} {rank:>4s} {scores} {d['latency_s']:>5.1f}s  "
                   f"{'< ' if below else '  '}{d['question'][:60]}")
    return "\n".join(out)


def unsupported(rows: list[dict[str, Any]], limit: int = 20) -> str:
    """The statements the claim-by-claim judge found not supported by the cards, per question."""
    out = []
    for d in rows:
        for c in d.get("faithfulness_claims") or []:
            if not c["supported"]:
                out.append(f"{d['id']:4s} {c['statement'][:110]}\n       -> {c['evidence'][:110]}")
    if not out:
        return "Every statement is supported by the consulted cards."
    more = f"\n... and {len(out) - limit} more (see the saved run)" if len(out) > limit else ""
    return "Statements not supported by the consulted cards:\n" + "\n".join(out[:limit]) + more


REMINDER = """What to try when a metric is low (then re-run the gold run and compare):
- recall@1 low, recall@5 fine -> the right card is found but not first: a reranker.
- recall@5 low -> the right card is not found: hybrid search, larger k, better chunking.
- MRR low -> the right card is often low in the list: reranker or query rewriting.
- faithfulness low (recall fine) -> the model invents despite the context: stricter grounding, less noise.
- relevancy low -> answers off the point: review the generation prompt.
- abstention out of corpus low -> it answers without a source: stricter grounding.
- latency p95 high -> smaller k or caching.
- recall fine but the agent did not search -> look at the spans in Phoenix before blaming retrieval.
- relevancy up but abstention down -> the prompt became more permissive, not better: reject it.
Method: change ONE thing at a time, re-measure on the same gold run, keep it only if the numbers improve."""

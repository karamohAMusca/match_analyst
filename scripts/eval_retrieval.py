"""Measure retrieval on the gold set and compare retrieval configurations (A/B on the same questions).

    python -m scripts.eval_retrieval             # embeds the questions not cached yet (one call)
    python -m scripts.eval_retrieval --offline   # cached vectors only: no API key, no cost
    python -m scripts.eval_retrieval --offline --no-save   # results only, for scripts/verify.py

The gold question vectors are cached in .cache/ (a few hundred tokens the first time, well under
$0.001; free afterwards), and every configuration reuses them, so configurations differ only in
how they rank. Every run is saved to eval/runs/ for later comparison.
Needs Qdrant running with the index up to date (python -m scripts.ingest).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict

from src.core.config import PROJECT_ROOT, load_settings
from src.corpus.cards import load_manifest_cards
from src.evaluation.retrieval_metrics import POOL, load_retrieval_cases, question_metrics, summarize
from src.rag.embedding_cache import CachedEmbedder
from src.rag.ingest import stored_versions
from src.rag.retrieval import Retriever
from src.rag.store import make_embedder, make_vector_store

# name -> arguments of Retriever.retrieve (max_per_card defaults to DEFAULT_MAX_PER_CARD).
# Earlier variants (RRF with k0=10, 2 chunks per card) are recorded in eval/runs/.
CONFIGS = {
    "dense": {"mode": "dense"},
    "bm25": {"mode": "bm25"},
    "hybrid rrf (course)": {"mode": "hybrid", "fusion": "rrf"},
    "hybrid interleave": {"mode": "hybrid", "fusion": "interleave"},
}
DEFAULT_CONFIG = "hybrid interleave"
RUNS_DIR = PROJECT_ROOT / "eval" / "runs"
COLUMNS = ("recall@1", "recall@5", "MRR@10", "all_relevant@5", "relevant_found@5", "distractor@5", "cards@5")


def index_is_current(store, collection: str) -> bool:
    stored = stored_versions(store, collection)
    return bool(stored) and all(
        {version[0] for version in stored.get(card.document_id, set())} == {card.sha256}
        for card in load_manifest_cards()
    )


def print_table(summaries: dict[str, dict]) -> None:
    print(f"\n{'configuration':20}" + "".join(f"{c:>17}" for c in COLUMNS))
    for name, s in summaries.items():
        marker = "  <- default" if name == DEFAULT_CONFIG else ""
        print(f"{name:20}" + "".join(f"{s[c]:>17.2f}" for c in COLUMNS) + marker)


def print_by_type(results: dict[str, list[dict]]) -> None:
    types = sorted({r["type"] for rows in results.values() for r in rows})
    print(f"\nexpected card in top 5, by question type and language\n{'configuration':20}"
          + "".join(f"{t:>14}" for t in types) + f"{'it':>8}{'en':>8}")
    for name, rows in results.items():
        by_type, by_lang = defaultdict(list), defaultdict(list)
        for r in rows:
            by_type[r["type"]].append(r["hit@5"])
            by_lang[r["language"]].append(r["hit@5"])
        print(f"{name:20}" + "".join(f"{sum(by_type[t])}/{len(by_type[t])}".rjust(14) for t in types)
              + "".join(f"{sum(by_lang[lang])}/{len(by_lang[lang])}".rjust(8) for lang in ("it", "en")))


def print_languages(rows: list[dict]) -> None:
    hits = {r["question_id"]: r["hit@5"] for r in rows}
    pairs = [(r["paired_with"], r["question_id"]) for r in rows if r.get("paired_with") in hits]
    diff = [f"{it}/{en}" for it, en in pairs if hits[it] != hits[en]]
    print(f"\nItalian/English pairs with a different outcome ({DEFAULT_CONFIG}): {', '.join(diff) if diff else 'none'}")


def print_misses(rows: list[dict]) -> None:
    misses = [r for r in rows if not r["hit@5"]]
    print(f"\nQuestions whose expected card is not in the top 5 ({DEFAULT_CONFIG}, {len(misses)}):")
    for r in misses:
        top_cards = ", ".join(dict.fromkeys(r["retrieved"][:5]))
        print(f"  {r['question_id']} [{r['type']}] expected {r['relevant_sources'][0]} "
              f"(rank {r['rank'] or '>10'}) | top 5: {top_cards}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--offline", action="store_true", help="use cached question vectors only (no API key)")
    parser.add_argument("--no-save", action="store_true",
                        help="print the results without saving a run: the same output at every run (scripts/verify.py)")
    args = parser.parse_args()
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    cases = load_retrieval_cases()
    questions = [case["question"] for case in cases]
    settings = load_settings()
    try:
        store = make_vector_store(settings)
        inner = None if args.offline else make_embedder(settings)
    except (RuntimeError, ValueError) as e:
        print(e)
        return 1
    if not index_is_current(store, settings.qdrant_collection):
        print("The index is missing or out of date: run python -m scripts.ingest first.")
        return 1

    embedder = CachedEmbedder(inner, settings.embedding_model)
    to_embed = len(embedder.missing(questions))
    if to_embed and args.offline:
        print(f"{to_embed} gold questions are not in the cache: run once without --offline.")
        return 1
    print(f"{len(questions)} gold questions: {len(questions) - to_embed} vectors from the cache, "
          f"{to_embed} to embed in one call ({settings.embedding_model}).")
    vectors = embedder.embed(questions)
    retriever = Retriever(store, embedder, settings.qdrant_collection)

    results: dict[str, list[dict]] = {}
    for name, config in CONFIGS.items():
        rows = []
        for case, vector in zip(cases, vectors, strict=True):
            hits = retriever.retrieve(case["question"], k=POOL, vector=vector, **config)
            retrieved = [hit.metadata["document_id"] for hit in hits]
            rows.append({
                "question_id": case["question_id"],
                "type": case["type"],
                "language": case["language"],
                "paired_with": case.get("paired_with"),
                "relevant_sources": case["relevant_sources"],
                "retrieved": retrieved,
                "sections": [hit.metadata["section"] for hit in hits],
                "chunk_ids": [hit.id for hit in hits],
                **question_metrics(retrieved, case),
            })
        results[name] = rows

    summaries = {name: summarize(rows) for name, rows in results.items()}
    print_table(summaries)
    print_by_type(results)
    print_languages(results[DEFAULT_CONFIG])
    print_misses(results[DEFAULT_CONFIG])
    if args.no_save:
        return 0

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = RUNS_DIR / f"retrieval_{stamp}.json"
    out.write_text(json.dumps({
        "run": stamp,
        "embedding_model": settings.embedding_model,
        "collection": settings.qdrant_collection,
        "pool": POOL,
        "configs": CONFIGS,
        "default": DEFAULT_CONFIG,
        "summaries": summaries,
        "questions": results,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nRun saved to {out.relative_to(PROJECT_ROOT).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

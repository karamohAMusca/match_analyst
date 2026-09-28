"""Retrieval metrics on the gold set.

Definitions:
- recall@k: share of questions whose expected card is among the first k chunks;
  for questions with several expected cards, the first one listed (entry point of the chain);
- MRR: mean of 1/position of the first chunk from the expected card, over the first 10 chunks.

Project extensions, for questions that need more than one card:
- all_relevant@5: all expected cards are among the first 5 chunks;
- relevant_found@5: share of the expected cards found among the first 5 chunks;
- distractor@5: a card marked as misleading appears among the first 5 (lower is better);
- cards@5: distinct cards among the first 5 chunks (how varied the context is).
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from src.core.config import GOLD_SET_PATH

POOL = 10  # chunks retrieved per question: enough for recall@1, recall@5 and MRR@10 at once


def load_retrieval_cases(path: Path = GOLD_SET_PATH) -> list[dict[str, Any]]:
    """Gold questions that have at least one expected card (the others test abstention/guardrails)."""
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return [q for q in questions if q["relevant_sources"]]


def question_metrics(ranked_cards: list[str], case: dict[str, Any]) -> dict[str, Any]:
    """Metrics for one question, given the card id of each retrieved chunk in rank order."""
    relevant = case["relevant_sources"]
    target = relevant[0]
    rank = next((i + 1 for i, card in enumerate(ranked_cards[:POOL]) if card == target), None)
    top5 = set(ranked_cards[:5])
    distractors = set(case.get("distractor_sources", []))
    return {
        "rank": rank,
        "hit@1": rank == 1,
        "hit@5": rank is not None and rank <= 5,
        "reciprocal_rank": 1.0 / rank if rank else 0.0,
        "all_relevant@5": set(relevant) <= top5,
        "relevant_found@5": len(set(relevant) & top5) / len(relevant),
        "distractor@5": bool(distractors & top5) if distractors else None,
        "cards@5": len(top5),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Average the per-question metrics of one configuration."""
    with_distractors = [r["distractor@5"] for r in rows if r["distractor@5"] is not None]
    return {
        "questions": len(rows),
        "recall@1": mean(r["hit@1"] for r in rows),
        "recall@5": mean(r["hit@5"] for r in rows),
        "MRR@10": mean(r["reciprocal_rank"] for r in rows),
        "all_relevant@5": mean(r["all_relevant@5"] for r in rows),
        "relevant_found@5": mean(r["relevant_found@5"] for r in rows),
        "distractor@5": mean(with_distractors) if with_distractors else 0.0,
        "cards@5": mean(r["cards@5"] for r in rows),
    }

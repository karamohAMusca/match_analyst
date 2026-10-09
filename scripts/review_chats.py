"""Check the chats saved by the app (chats/), offline: no API key, no network, no Qdrant.

    python -m scripts.review_chats                                  # the last chat
    python -m scripts.review_chats --all                            # every saved chat
    python -m scripts.review_chats chats/2026-09-30_153012.jsonl    # one chat

For every answer: what the guardrails did, then the automatic checks of eval_agent, run on the
saved answer against the text of the cards it consulted (read from corpus/, the same cards as the
index): citations only to consulted cards, names and numbers present in those cards or in the
coach's questions (grounding), tool use, answer language, malformed or copied citations. A chat has
no gold answer: required facts and expected cards are not checked, and "Non lo so" is counted, not
judged (an answer that says it is not flagged for citing nothing). An answer given without a new
search, from cards read in earlier turns of the same chat, is checked against those cards: the
memory counts as consultation. Each line shows the tokens of that answer, so the cost of a long chat
growing turn after turn is visible. Then the chat's totals: answers, flagged answers, questions
stopped, rewrites, time, tokens, cost.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import src.core.config as config
from src.corpus.cards import load_manifest_cards
from src.corpus.chunking import chunk_card
from src.evaluation.answer_checks import ABSTENTION, check_answer, normalize, problems
from src.guardrails.language import detect_language
from src.rag.retrieval import whole_card
from src.ui.chat_log import load_chat

ANSWERED = (None, "football", "follow_up")        # input verdicts that reach the agent
STOPPED = ("off_topic", "injection", "too_long")   # the others (greeting, thanks) get a fixed reply


def card_texts() -> dict[str, str]:
    """Every indexed card as the agent reads it (`Retriever.card_text()`), without Qdrant."""
    texts = {}
    for card in load_manifest_cards():
        chunks = chunk_card(card)
        texts[chunks[0].metadata["document_id"]] = whole_card(chunks)
    return texts


def review(answers: list[dict[str, Any]], cards: dict[str, str]) -> list[dict[str, Any]]:
    """The checks of every answer of a chat, in order."""
    rows, earlier, read_before = [], [], []
    for a in answers:
        guard = a.get("guard") or {}
        calls = len(a.get("calls") or [])
        row = {"question": a["question"], "guard": guard, "meta": a.get("meta") or {},
               "consulted": a.get("consulted") or [], "problems": [], "from_memory": False,
               "abstained": any(x in normalize(a["content"]) for x in ABSTENTION)}
        if guard.get("input") in ANSWERED:
            consulted = row["consulted"]
            if not calls and read_before:   # answered from cards read earlier in the chat
                consulted, calls, row["from_memory"] = read_before, 1, True
            question = {"question": a["question"], "expected_tool_use": "search",
                        "requires_abstention": row["abstained"], "relevant_sources": [], "type": "chat",
                        "language": detect_language(a["question"])}
            source_text = "\n".join(cards.get(c, "") for c in consulted)
            check = check_answer(a["content"], question, consulted, calls, source_text, "\n".join(earlier))
            row["problems"] = problems(check)
            earlier.append(a["question"])
            read_before += [c for c in row["consulted"] if c not in read_before]
        rows.append(row)
    return rows


def guard_label(guard: dict[str, Any]) -> str:
    if guard.get("input") in STOPPED:
        return f"stopped ({guard['input']})"
    if guard.get("input") not in ANSWERED:
        return f"fixed reply ({guard['input']})"
    if guard.get("rewritten"):
        return "rewritten"
    if guard.get("issues"):
        return "rewrite not kept"
    return ""


def report(path: Path, rows: list[dict[str, Any]]) -> str:
    lines = [f"== {path.name}: {len(rows)} answers"]
    for i, r in enumerate(rows, 1):
        m = r["meta"]
        status = "OK" if not r["problems"] else "CHECK"
        extra = "  ".join(x for x in (guard_label(r["guard"]), "Non lo so" if r["abstained"] else "") if x)
        question = " ".join(r["question"].split())
        tokens = m.get("prompt_tokens", 0) + m.get("completion_tokens", 0)
        lines.append(f"#{i:<2} {status:5} {m.get('latency_s', 0):5.1f} s  {tokens:6} tok  {m.get('cost_usd', 0):.4f} $  "
                     f"{question[:70] + ('…' if len(question) > 70 else '')}")
        cards = ", ".join(r["consulted"]) or ("— (cards read earlier in the chat)" if r["from_memory"] else "—")
        lines.append(f"    cards: {cards}" + (f"  | {extra}" if extra else ""))
        lines.extend(f"    - {p}" for p in r["problems"])
    metas = [r["meta"] for r in rows]
    flagged = sum(1 for r in rows if r["problems"])
    stopped = sum(1 for r in rows if r["guard"].get("input") in STOPPED)
    rewritten = sum(1 for r in rows if r["guard"].get("rewritten"))
    lines.append(f"Totals: {flagged} flagged, {stopped} stopped by the input guard, {rewritten} rewritten, "
                 f"{sum(m.get('latency_s', 0) for m in metas):.1f} s, "
                 f"{sum(m.get('prompt_tokens', 0) + m.get('completion_tokens', 0) for m in metas)} tokens, "
                 f"{sum(m.get('cost_usd', 0) for m in metas):.4f} $")
    kinds = Counter(p.split(":")[0] for r in rows for p in r["problems"])
    lines.extend(f"  {n:3}  {kind}" for kind, n in kinds.most_common())
    return "\n".join(lines)


def review_files(paths: list[Path]) -> str:
    """The report of every chat in `paths` (scripts.start prints it when the app is closed)."""
    cards = card_texts()
    return "\n\n".join(report(path, review(load_chat(path), cards)) for path in paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("chat", nargs="?", type=Path, help="a chat file (default: the last one)")
    parser.add_argument("--all", action="store_true", help="every saved chat")
    args = parser.parse_args(argv)
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")

    saved = sorted(config.CHATS_DIR.glob("*.jsonl"))
    paths = [args.chat] if args.chat else saved if args.all else saved[-1:]
    if not paths:
        print(f"No chat saved in {config.CHATS_DIR}: chat in the app first.")
        return 1
    print(review_files(paths) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())

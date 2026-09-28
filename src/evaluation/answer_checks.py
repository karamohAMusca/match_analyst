"""Deterministic checks on an agent answer against its gold question (no LLM judge).

- citations: ids cited as [document_id], [document_id, p. N] or [id_a, id_b] must be cards the
  agent consulted, or cards named inside a consulted card (indirect: the claim is in the card read);
- author_citations: the card-internal references ([Soncin, p. 19]) must not be used as citations;
- grounding: names and numbers must appear in the consulted cards (src/guardrails/grounding.py);
- tool use: greetings/off-topic without tools, football questions with tools;
- abstention: "Non lo so" when the gold set requires it;
- language: the answer is written in the language of the question (English questions exist);
- required facts / forbidden claims: accent-insensitive substring match, as in the gold set.
Citation parsing, grounding and language detection are the ones of the guardrails
(src/guardrails/): the evaluation measures exactly what the running agent enforces.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from src.guardrails.grounding import ungrounded_terms
from src.guardrails.language import detect_language
from src.guardrails.output_guard import ABSTENTION, BRACKETS_RE, CARD_MENTION_RE, citation_ids

AUTHOR_CITATION_RE = re.compile(r"\[(?:Soncin|Spalla|Dileo|Pioli|Italiano|Contran|Polenghi|Wikipedia|FIFA|StatsBomb)[^\]]*\]")
ADVICE_TYPES = {"situational", "style_match"}
MAX_ADVICE_WORDS = 180   # the prompt asks for at most 150 words of text; citations add a few
# A tool header copied into the answer as a "source" line instead of citing inline.
COPIED_HEADER_RE = re.compile(r"^\s*(?:-{3}\s*Fonte\b.*|\[[a-z0-9_]+\]\s+[^\n]*·[^\n]*)$", re.M | re.I)


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower())


def check_answer(
    answer: str,
    question: dict[str, Any],
    consulted: list[str],
    tool_calls: int,
    source_text: str | None = None,
) -> dict[str, Any]:
    """`source_text`: text of the consulted cards; enables the grounding and indirect-citation checks."""
    text = normalize(answer)
    copied_headers = [line.strip() for line in COPIED_HEADER_RE.findall(answer)]
    body = COPIED_HEADER_RE.sub("", answer)            # citations only count inside the answer text
    authors = AUTHOR_CITATION_RE.findall(body)
    bracketed = [b.strip() for b in BRACKETS_RE.findall(body) if f"[{b}]" not in authors]
    cited = list(dict.fromkeys(i for b in bracketed for i in citation_ids(b)))
    malformed = list(dict.fromkeys(b for b in bracketed if not citation_ids(b)))
    mentioned = set(CARD_MENTION_RE.findall(source_text or ""))
    facts = question.get("required_facts") or []
    found = [group for group in facts if any(normalize(alt) in text for alt in group)]
    expects_tools = question["expected_tool_use"] != "none"
    abstained = any(a in text for a in ABSTENTION)
    grounding_applies = source_text is not None and expects_tools and bool(consulted)
    language = detect_language(body)
    return {
        "cited": cited,
        "invalid_citations": [c for c in cited if c not in consulted and c not in mentioned],
        "indirect_citations": [c for c in cited if c not in consulted and c in mentioned],
        "ungrounded": ungrounded_terms(body, source_text, question["question"]) if grounding_applies else [],
        "malformed_citations": malformed,
        "copied_headers": copied_headers,
        "author_citations": authors,
        "tool_use_ok": (tool_calls > 0) == expects_tools,
        "abstention_ok": abstained if question["requires_abstention"] else None,
        "answer_language": language,
        "language_ok": language == question.get("language", "it"),
        "relevant_consulted": [s for s in question["relevant_sources"] if s in consulted],
        "facts_found": f"{len(found)}/{len(facts)}" if facts else None,
        "forbidden_found": [c for c in question.get("forbidden_claims", []) if normalize(c) in text],
        "cites_something": bool(cited) if expects_tools and not question["requires_abstention"] else None,
        "words": len(re.findall(r"\w+", body)),
        "advice": question["type"] in ADVICE_TYPES,
    }


def problems(check: dict[str, Any]) -> list[str]:
    """Human-readable list of what went wrong (empty = all checks passed)."""
    out = []
    if check["invalid_citations"]:
        out.append(f"cites cards it did not consult: {check['invalid_citations']}")
    if check.get("ungrounded"):
        out.append(f"names/numbers not in the consulted cards: {check['ungrounded'][:6]}")
    if check["copied_headers"]:
        out.append(f"source line copied instead of inline citation: {check['copied_headers'][:1]}")
    if check["malformed_citations"]:
        out.append(f"malformed citations: {check['malformed_citations'][:3]}")
    if check["author_citations"]:
        out.append(f"uses card-internal references as citations: {check['author_citations'][:3]}")
    if not check["tool_use_ok"]:
        out.append("wrong tool use (searched a greeting, or answered football without searching)")
    if check.get("language_ok") is False:
        out.append(f"answer in the wrong language ({check['answer_language']})")
    if check["abstention_ok"] is False:
        out.append('missing "Non lo so"')
    if check["cites_something"] is False:
        out.append("no [document_id] citation")
    if check["advice"] and check["words"] > MAX_ADVICE_WORDS:
        out.append(f"advice too long: {check['words']} words")
    if check["forbidden_found"]:
        out.append(f"forbidden claims: {check['forbidden_found']}")
    if check["facts_found"] and check["facts_found"].split("/")[0] != check["facts_found"].split("/")[1]:
        out.append(f"required facts found {check['facts_found']}")
    return out

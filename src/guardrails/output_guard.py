"""Output guardrail: checks the agent's answer before it is shown; on a problem, the agent
rewrites it once with precise feedback (the rewrite itself is run by MatchAnalyst).

Why code and not more prompt rules: the full gold runs of 2026-09-28 (-163729; -171548 with
another model; -172539 with stricter rules) failed the same way every time. gpt-4o-mini ignored
general rules of its system prompt (answer in the language of the question, cite [card_id]);
a precise note on its own answer ("these names are not in the cards: Philipp, Kyle") is much
harder to ignore.
Checks, all deterministic and offline:
- language: the answer is written in the language of the question;
- grounding: its names and numbers appear in the consulted cards (grounding.py), in the question
  or, in a conversation, in the coach's earlier questions (what the coach said in turn 1, e.g. the
  opponent's name, is not an invention in turn 2);
- citations: it cites at least one [card_id] (unless it only says "Non lo so"), and only cards
  it consulted or that those cards mention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.guardrails.grounding import ungrounded_terms
from src.guardrails.language import detect_language

BRACKETS_RE = re.compile(r"\[([^\[\]\n]{1,80})\]")
ID_RE = re.compile(r"[a-z0-9]+(?:_[a-z0-9]+)+")
ID_WITH_PAGE_RE = re.compile(r"([a-z0-9]+(?:_[a-z0-9]+)+)\s*,\s*pp?\.\s*[\d\s,\-–]+")
CARD_MENTION_RE = re.compile(r"\b(?:case|situation|coach|note|glossary)_[a-z0-9_]+")
ABSTENTION = ("non lo so", "i don't know", "i do not know")
LANGUAGE_NAMES = {"it": "Italian", "en": "English"}


def citation_ids(bracketed: str) -> list[str]:
    """'coach_pioli', 'coach_pioli, p. 4' -> ['coach_pioli']; 'coach_a, coach_b' and
    'coach_a, p. 51; coach_b' -> both; anything else -> []."""
    ids: list[str] = []
    for segment in (s.strip() for s in bracketed.split(";")):
        match = ID_WITH_PAGE_RE.fullmatch(segment)
        if match:
            ids.append(match.group(1))
            continue
        parts = [p.strip() for p in segment.split(",")]
        if not all(ID_RE.fullmatch(p) for p in parts):
            return []
        ids.extend(parts)
    return ids


def cited_ids(answer: str) -> list[str]:
    """Card ids cited in the answer, in order of first citation."""
    return list(dict.fromkeys(i for b in BRACKETS_RE.findall(answer) for i in citation_ids(b.strip())))


def is_abstention(answer: str) -> bool:
    return answer.strip().lower().startswith(ABSTENTION)


@dataclass(frozen=True)
class Issue:
    """One problem of an answer: `kind` and `detail` for the report, `instruction` for the model."""

    kind: str        # language | ungrounded | unknown_citation | no_citation
    detail: str
    instruction: str

    def describe(self) -> str:
        return f"{self.kind}: {self.detail}"


def review_answer(answer: str, question: str, consulted: list[str], source_text: str,
                  earlier_questions: str = "") -> list[Issue]:
    """Problems of `answer`; `source_text` is the text of the `consulted` cards, `earlier_questions`
    the coach's previous questions of the same conversation (known text for grounding only: the
    language is the one of the current question)."""
    issues: list[Issue] = []
    wanted, written = detect_language(question), detect_language(answer)
    if written != wanted:
        issues.append(Issue(
            "language", f"{written} instead of {wanted}",
            f"The question is in {LANGUAGE_NAMES[wanted]} but the answer is in {LANGUAGE_NAMES[written]}: "
            f"write the whole answer in {LANGUAGE_NAMES[wanted]}, translating what you take from the cards.",
        ))
    if not consulted:
        return issues
    missing = ungrounded_terms(answer, source_text, f"{question}\n{earlier_questions}")
    if missing:
        terms = ", ".join(missing)
        issues.append(Issue(
            "ungrounded", terms,
            f"These names or numbers do not appear in the cards you consulted: {terms}. Remove them or "
            "replace them with the exact words of the cards; never complete names, minutes or seasons "
            "from memory. If the question asks for that detail and the cards do not give it, write "
            "\"Non lo so\" (in English: \"I don't know\") for that detail.",
        ))
    cited = cited_ids(answer)
    mentioned = set(CARD_MENTION_RE.findall(source_text))
    unknown = [c for c in cited if c not in consulted and c not in mentioned]
    if unknown:
        ids = ", ".join(unknown)
        issues.append(Issue(
            "unknown_citation", ids,
            f"These ids are not among the cards you consulted: {ids}. Cite only the ids of the cards "
            "below, spelled exactly.",
        ))
    if not cited and not is_abstention(answer):
        issues.append(Issue(
            "no_citation", "no [card_id]",
            "The answer cites no card. End each sentence or bullet with the [document_id] of the card "
            "it comes from, e.g. [coach_pioli]; a reference in parentheses like (Pioli, p. 4) is not a "
            "citation.",
        ))
    return issues

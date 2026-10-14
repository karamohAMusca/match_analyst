"""Facts about real matches, written from the cards by code instead of by the model.

The errors that survived every other check (eval/error_log.md) were names that are all in the
cards, put together wrongly. The worst were in the real case of an advice answer (E1 "l'Inter ha
difeso un vantaggio", E2 "il pressing a uomo del Leverkusen"): the model retold the card's sentence
in its own words and swapped the roles. Here the prompt asks for the line `Caso reale: [case_id]`
only: the model picks the match, and `expand_real_cases` writes the facts with the card's own
sentence (the line of a consulted card that cites that match, game situations first, else the match
card's outcome). Whatever the model wrote on that line is replaced, so the roles of a real case
cannot be swapped; a real case no consulted card speaks of is removed. The checks and the rewrite of
the output guardrail see the line as the model is asked to write it (`collapse_real_cases`).
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from src.guardrails.output_guard import BRACKETS_RE, cited_ids, citation_ids

CASE_LINE_RE = re.compile(
    r"^(?P<lead>[ \t]*(?:[-*•][ \t]+)?)(?:\*\*)?(?P<label>caso reale|casi reali|real cases?)\b[^:\n]*?"
    r"(?:\*\*)?[ \t]*:[ \t]*(?:\*\*)?(?P<rest>.*)$", re.IGNORECASE | re.MULTILINE)
_LEAD_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)?")
_NAME_OR_NUMBER_RE = re.compile(r"\b[A-Z][a-zA-Z]+|\d+(?:[.,]\d+)?")


def _label(written: str) -> str:
    """The label of the line, in the language the model used for it."""
    return "Real case (card text, in Italian)" if written.lower().startswith("real") else "Caso reale"


def _case_ids(text: str) -> list[str]:
    return [i for b in BRACKETS_RE.findall(text) for i in citation_ids(b.strip()) if i.startswith("case_")]


def _card_sentence(line: str) -> str:
    """A line of a card as an answer sentence: no bullet, no bold marks, no card ids; the card's
    own references in parentheses, as the tools show them."""
    line = _LEAD_RE.sub("", line)
    line = re.sub(r"^\*\*(.+?):?\*\*:?\s*", r"\1 — ", line).replace("**", "")   # "**Label:** text" -> "Label — text"
    line = BRACKETS_RE.sub(lambda m: "" if citation_ids(m.group(1).strip()) else f"({m.group(1)})", line)
    line = re.sub(r"\s+([.,;:])", r"\1", re.sub(r"\s{2,}", " ", line)).strip().rstrip(".").strip()
    return line[:1].upper() + line[1:]


def case_sentence(case_id: str, consulted: list[str], card_text: Callable[[str], str | None]) -> str | None:
    """The card's own sentence on `case_id`: the first line citing it in a consulted card (game
    situations first: theirs are written for that situation), else the outcome of the match card
    if it was consulted; None if no consulted card speaks of it."""
    others = sorted((c for c in consulted if c != case_id), key=lambda c: not c.startswith("situation_"))
    for card in others:
        for line in (card_text(card) or "").splitlines():
            if case_id in _case_ids(line) and not line.lstrip().startswith("#"):
                return _card_sentence(line)
    if case_id in consulted:
        text = card_text(case_id) or ""
        title = text.split("\n", 1)[0].lstrip("# ").strip()
        outcome = next((line for line in text.splitlines() if line.lstrip().startswith("**Esito:**")), "")
        if outcome:
            return f"{title}. {_card_sentence(outcome.replace('**Esito:**', ''))}"
    return None


def _match_case(line: str, consulted: list[str], card_text: Callable[[str], str | None]) -> str | None:
    """The final a real-case line speaks of when it cites no [case_...] (e.g. it cites the game
    situation card): the case line of a consulted card sharing the most names and numbers with it,
    at least two ("Mondiale", "2026", "Spagna", "Argentina")."""
    def terms(text: str) -> set[str]:
        plain = unicodedata.normalize("NFKD", BRACKETS_RE.sub(" ", text)).encode("ascii", "ignore").decode()
        return {t.lower() for t in _NAME_OR_NUMBER_RE.findall(plain)} - {"caso", "reale", "real", "case"}
    wanted, best, best_score = terms(line), None, 1
    for card in consulted:
        for candidate in (card_text(card) or "").splitlines():
            ids = _case_ids(candidate)
            score = len(wanted & terms(candidate)) if ids else 0
            if score > best_score:
                best, best_score = ids[0], score
    return best


def expand_real_cases(answer: str, consulted: list[str], card_text: Callable[[str], str | None]) -> str:
    """Every real-case line about a final written with the card's sentence for it: the final it cites,
    or, citing none, the final it names (`_match_case`). A line about something else that cites a
    consulted card (a match of a thesis, a season of a coach) is left to the output guardrail, as any
    other sentence. Removed: a final no consulted card speaks of, or a line citing no card (a real
    case cannot come from the model's memory)."""
    def line(match: re.Match) -> str:
        rest = match.group("rest")
        cited = _case_ids(rest)
        for case_id in cited or filter(None, [_match_case(rest, consulted, card_text)]):
            sentence = case_sentence(case_id, consulted, card_text)
            if sentence:
                return f"{match.group('lead')}{_label(match.group('label'))}: {sentence} [{case_id}]."
        if not cited and set(cited_ids(rest)) & set(consulted):
            return match.group(0)
        return "\x00"   # removed below, with its line break
    expanded = CASE_LINE_RE.sub(line, answer)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(l for l in expanded.splitlines() if l != "\x00")).strip()


def collapse_real_cases(answer: str) -> str:
    """The answer with every real-case line reduced to its label and ids, as the model is asked to
    write it: the checks and the rewrite work on this form (the card's sentence is not the model's)."""
    def line(match: re.Match) -> str:
        ids = _case_ids(match.group("rest"))
        if not ids:
            return match.group(0)
        label = "Real case" if match.group("label").lower().startswith("real") else "Caso reale"
        return f"{match.group('lead')}{label}: [{', '.join(ids)}]"
    return CASE_LINE_RE.sub(line, answer)

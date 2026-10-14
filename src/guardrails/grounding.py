"""Grounding check: names and numbers in an answer must come from the consulted cards.

Deterministic and cheap (no LLM): every proper noun (capitalized word that does not start a
sentence) and every number of the answer must appear in the text of the cards the agent
consulted, or in the question. It catches facts taken from the model's own memory, like a
coach name the cards never give (run agent_20260928-162748: "Luis Enrique" with a real citation)
or season labels the cards never state (run -163729: "2020/21").
Numbers are compared as whole numbers, with comma and dot as the same decimal separator
("10" is not grounded by "10.30"; "13,48" is grounded by "13.48"). Names are compared as
substrings, accent-insensitive, each part of a hyphenated chain on its own
("Vitinha-Doué-Hakimi" is grounded when the card names the three players). An English answer
may translate the Italian names of countries and competitions ("Spain" for "Spagna").
In an English answer, headings and bold labels at the start of a line ("### Key Aspects of Spain's
Victory", "- **Offensive Strategy**:") are titles in Title Case: their capitalised words are not
names (they were flagged as invented names, E16); their numbers are still checked. Italian titles
capitalise only their first word, so in an Italian answer a label is checked like any other text.
Limit: a term is checked, not the claim around it. An invented threshold built from a number
the cards use elsewhere ("PPDA inferiore a 10", run -163729) passes here: facts.py catches it.
Used by the output guardrail (output_guard.py) and by the answer evaluation.
"""

from __future__ import annotations

import re
import unicodedata

from src.guardrails.language import detect_language

_CITATION_RE = re.compile(r"\[[^\[\]\n]*\]")
_MARKDOWN_RE = re.compile(r"[*_#`>]+")
_BULLET_RE = re.compile(r"^\s*(?:[-•]|\d+[.)])\s+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?:;])\s+")
_TOKEN_RE = re.compile(r"[^\W\d_][\w-]*|\d+(?:[.,]\d+)?", re.UNICODE)
_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)?")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s")
_LABEL_RE = re.compile(r"^\s*(?:[-•*]\s+|\d+[.)]\s+)?\*\*[^*\n]+\*\*\s*:?")
# English names of the countries and competitions in the cards (written in Italian).
ENGLISH_EQUIVALENTS = {
    "spain": ("spagna",), "spanish": ("spagna",), "england": ("inghilterra",),
    "english": ("inghilterra", "ingles"), "france": ("francia",), "french": ("francia",),
    "italy": ("italia",), "italian": ("italia",), "germany": ("germania",), "german": ("germania",),
    "argentine": ("argentina",), "argentinian": ("argentina",), "world": ("mondial",),
    "cup": ("mondial", "coppa"), "european": ("euro",), "championship": ("euro", "campionat"),
    "sunday": ("domenica",),
}


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower())


def _number(token: str) -> str:
    return token.replace(",", ".")


def _known_name(token: str, known_text: str) -> bool:
    for part in filter(None, token.split("-")):
        word = _normalize(part)
        if word not in known_text and not any(t in known_text for t in ENGLISH_EQUIVALENTS.get(word, ())):
            return False
    return True


def ungrounded_terms(answer: str, source_text: str, question: str = "") -> list[str]:
    """Proper nouns and numbers of `answer` that appear neither in `source_text` nor in `question`."""
    known_text = _normalize(source_text + " " + question)
    known_numbers = {_number(n) for n in _NUMBER_RE.findall(source_text + " " + question)}
    missing: list[str] = []
    if detect_language(answer) == "en":   # English titles in Title Case: only their numbers are checked (E16)
        lines = []
        for line in answer.splitlines():
            title = line if _HEADING_RE.match(line) else (m.group(0) if (m := _LABEL_RE.match(line)) else "")
            for token in _NUMBER_RE.findall(_CITATION_RE.sub(" ", title)):
                if _number(token) not in known_numbers and token not in missing:
                    missing.append(token)
            lines.append(line[len(title):])
        answer = "\n".join(lines)
    text = _MARKDOWN_RE.sub("", _CITATION_RE.sub(" ", answer)).replace("’", "'").replace("'", " ")
    for line in text.splitlines():
        for sentence in _SENTENCE_SPLIT_RE.split(_BULLET_RE.sub("", line)):
            matches = list(_TOKEN_RE.finditer(sentence))
            for i, match in enumerate(matches):
                token = match.group()
                if token[0].isdigit():
                    if _number(token) not in known_numbers and token not in missing:
                        missing.append(token)
                    continue
                if not (token[0].isupper() and len(token) > 1):
                    continue
                if i == 0:
                    # A capitalized first word is usually just a sentence start, unless it opens a
                    # multi-word name ("Luis Enrique era..."): next word capitalized, only a space between.
                    nxt = matches[1] if len(matches) > 1 else None
                    opens_name = (nxt is not None and nxt.group()[0].isupper()
                                  and sentence[match.end():nxt.start()].isspace())
                    if not opens_name:
                        continue
                if not _known_name(token, known_text) and token not in missing:
                    missing.append(token)
    return missing

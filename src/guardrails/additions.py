"""What the writer adds to the cards, or leaves unmarked, taken care of by code after the review:
a closing summary with no citation (`closing_summary`), an effect added after a comma
(`effect_tails`, E20), a detail said to be missing without the words "Non lo so"
(`unmarked_unknown`, E19), and every external link or image (`links.py`, kept out of the answer
before and after the review). None of them needs a model call.
"""

from __future__ import annotations

import re
from typing import Any

from src.guardrails.links import strip_external_links
from src.guardrails.output_guard import BRACKETS_RE
from src.guardrails.real_case import CASE_LINE_RE
from src.guardrails.text import LEAD_RE, normalize, remove_sentences, sentences

# ---------------------------------------------------------------- the closing summary
# A last sentence that sums up or evaluates, with no citation ("Queste regole aiutano a mantenere
# l'equilibrio", "Questi cambiamenti riflettono un'evoluzione"): in the reference gold run most of the
# statements the judge found unsupported were such additions. It carries no cited fact, so it is removed.
_CLOSING_RE = re.compile(
    r"^(?:quest[aoie]|tali|in sintesi|in conclusione|in breve|nel complesso|complessivamente|"
    r"this|these|overall|in summary|in short|in conclusion)\b", re.IGNORECASE)
# ...unless it is the answer to a style question ("Inzaghi potrebbe essere più affine al tuo stile")
_RESEMBLANCE_RE = re.compile(r"simil|somigli|affin|resembl|closest|more like", re.IGNORECASE)


def closing_summary(answer: str) -> str | None:
    """The answer's last sentence when it sums up or evaluates without a citation: on its own line,
    not a bullet nor the real-case line, opening with "Questo/Queste", "In sintesi", "This", ...;
    None otherwise, when nothing else of the answer cites a card, or when it says which coach the
    coach's team resembles (the answer of a style question)."""
    lines = [line.strip() for line in answer.strip().splitlines() if line.strip()]
    if len(lines) < 2 or LEAD_RE.sub("", lines[-1]) != lines[-1] or CASE_LINE_RE.match(lines[-1]):
        return None
    last = (sentences(lines[-1]) or [""])[-1]
    if (not _CLOSING_RE.match(last) or BRACKETS_RE.search(last) or _RESEMBLANCE_RE.search(last)
            or not BRACKETS_RE.search("\n".join(lines[:-1]))):
        return None
    return last


# ---------------------------------------------------------------- effects the cards do not state
# What a fact "creates", "allows" or "shows", added after a comma ("..., creando opportunità di tiro",
# "..., evidenziando un pressing molto efficace"): the prompt forbids it, yet in the gold runs of
# 2026-10-14 such tails were most of the statements the judge found unsupported, and the judge is not
# consistent on them either (the same tail supported in one run, not in the next): they are the
# writer's reading, not the card's. Cut by code; a tail with a number or a name is kept (", creando 182
# linee rotte": a fact of the card). Simulated on the verdicts of those runs: faithfulness 0.944 ->
# 0.955 and 0.946 -> 0.965, no required fact of the gold set lost.
_EFFECT_GERUNDS = ("creando|permettendo|consentendo|favorendo|garantendo|aumentando|migliorando|evidenziando|"
                   "dimostrando|suggerendo|facilitando|rendendo|contribuendo|generando|mostrando|sottolineando|"
                   "riflettendo|creating|allowing|enabling|leading|resulting|highlighting|demonstrating|showing|"
                   "suggesting|making|increasing|improving|reflecting|ensuring|helping")
_EFFECT_TAIL_RE = re.compile(rf",\s+(?:così\s+|cosi\s+|thus\s+)?(?:{_EFFECT_GERUNDS})\b[^\[\]\n]*?"
                             r"(?=\s*\[|[.;!?](?:\s|$)|$)", re.IGNORECASE)


def effect_tails(answer: str) -> list[str]:
    """The effect tails of `answer` (", creando ...", ", evidenziando ..."), exactly as written, from
    the comma to the citation or the end of the sentence; not those with a number or a name, and not
    in the real-case line (the card's own sentence)."""
    tails = []
    for line in answer.splitlines():
        if CASE_LINE_RE.match(line):
            continue
        for m in _EFFECT_TAIL_RE.finditer(line):
            if not re.search(r"\d", m.group(0)) and not re.search(r"(?<=\s)[A-Z][a-zà-ù]+", m.group(0)):
                tails.append(m.group(0))
    return tails


# ---------------------------------------------------------------- an unknown said without "Non lo so"
# Q21 (gold run 20261014-141635): "Il PSG era guidato in panchina da un allenatore non specificato":
# the detail is not in the cards, but without the words "Non lo so" neither the coach (the app boxes
# the paragraphs that start with them) nor the abstention measure can see it. On every saved answer,
# such a sentence in an answer that never says "Non lo so" is an abstention missed (Q19, Q21).
_UNKNOWN_RE = re.compile(
    r"\bnon (?:e |viene |vengono |sono |risulta |risultano )?(?:specificat|indicat|menzionat|nominat|precisat|riportat)\w*|"
    r"\b(?:le schede|la scheda|il corpus|le fonti|i documenti) non (?:dicono|indicano|specificano|riportano|menzionano|"
    r"nominano|forniscono|contengono)\b|\bnon (?:ho|ci sono|abbiamo) (?:informazioni|dati|dettagli)\b|"
    r"\bnot (?:specified|mentioned|named|stated|given|indicated|reported)\b|\bunspecified\b|\bunnamed\b|"
    r"\b(?:the cards|the card|the sources) do(?:es)? not (?:say|name|mention|specify|state|give)\b")
_ABSTAINED_RE = re.compile(r"non lo so|i don't know|i do not know")


def unmarked_unknown(answer: str) -> str | None:
    """The first sentence saying that a detail is not in the cards ("un allenatore non specificato",
    "non ci sono informazioni"), in an answer that never says "Non lo so" / "I don't know"; the
    real-case line (the card's own sentence) is not read. None otherwise."""
    if _ABSTAINED_RE.search(normalize(answer)):
        return None
    lines = (line for line in answer.splitlines() if not CASE_LINE_RE.match(line))
    return next((s for line in lines for s in sentences(line) if _UNKNOWN_RE.search(normalize(s))), None)


# ---------------------------------------------------------------- all three, after the review
def tidy(answer: str, english: bool) -> tuple[str, dict[str, Any]]:
    """The answer after the review, in this order: the external links and images removed (a rewrite may
    bring them back), the effect tails cut, the closing summary removed, "Non lo so." (in English
    "I don't know.") put before an unknown said without it. Also what was done, for the guardrails'
    report: the keys "links", "tails", "closing", "unknown", only when done."""
    done: dict[str, Any] = {}
    answer, links = strip_external_links(answer)
    if links:
        done["links"] = links
    if tails := effect_tails(answer):
        done["tails"] = tails
        for tail in tails:
            answer = answer.replace(tail, "", 1)
    if closing := closing_summary(answer):
        done["closing"] = closing
        answer = remove_sentences(answer, [closing])
    if unknown := unmarked_unknown(answer):
        done["unknown"] = unknown
        answer = answer.replace(unknown, ("I don't know. " if english else "Non lo so. ") + unknown, 1)
    return answer, done


"""Whose side the advice is for, and the score the coach gave.

And the side of a game situation (`perspective_issues`, E17): a coach "a man down", "behind" or
"ahead" (first-person phrases) must not get the advice of the mirror card as their own; a man down,
which has no card, gets an answer written by code (`man_down_answer`). A score the coach never gave
must not be taken for granted (`premise_issues`, E6).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from src.guardrails.output_guard import BRACKETS_RE, Issue, cited_ids, is_abstention
from src.guardrails.real_case import card_sentence, case_ids, collapse_real_cases
from src.guardrails.text import normalize, sentences

# ---------------------------------------------------------------- whose side the advice is for
# Game situations come in mirror pairs, each card written for one side. The coach's side is read
# from first-person phrases only ("restassimo in 10", not "l'avversario resta in 10"). E17: to
# "E se restassimo in 10 al 90'?" the agent gave the advice of the 11 v 10 card ("sfruttate la
# vostra superiorità"): every sentence was in the card, the side was the wrong one.
SIDES = {
    "a man down": (
        re.compile(r"\b(?:restiamo|restassimo|rimaniamo|rimanessimo|siamo rimasti|finiamo|giochiamo|siamo)\s+"
                   r"in\s+(?:10|dieci)\b|\b(?:abbiamo|con)\s+un\s+uomo\s+in\s+meno\b|\bsiamo\s+in\s+inferiorita\b|"
                   r"\b(?:ci\s+(?:hanno\s+)?espuls\w*|ci\s+espellono|espuls\w*\s+(?:un\s+)?(?:nostro|mio))\b|"
                   r"\bwe(?:'re| are| were| went| go| get| got)?\s+(?:down to|left with|reduced to|playing with)\s+"
                   r"(?:10|ten)\b|\bwe(?:'re| are| were)?\s+a man down\b|"
                   r"\bwe\s+(?:have|had|get|got)\s+(?:a|one)\s+(?:player|man)\s+sent off\b|"
                   r"\bone of (?:our|my) players\s+(?:is|was|gets|got)\s+sent off\b"),
        "situation_giocare_in_superiorita_numerica", None),
    "ahead": (
        re.compile(r"\b(?:siamo|stiamo)\s+(?:in\s+vantaggio|vincendo|avanti)\b|\bwe(?:'re| are)\s+(?:winning|ahead|leading)\b"),
        "situation_rimontare_uno_svantaggio", "situation_difendere_un_vantaggio"),
    "behind": (
        re.compile(r"\b(?:siamo|stiamo)\s+(?:in\s+svantaggio|perdendo|sotto)\b|\b(?:perdiamo|sto perdendo)\b|"
                   r"\bwe(?:'re| are)\s+(?:losing|behind|trailing)\b"),
        "situation_difendere_un_vantaggio", "situation_rimontare_uno_svantaggio"),
}


def coach_side(question: str) -> str | None:
    """The coach's side in a game situation ("a man down", "ahead", "behind"), from first-person phrases."""
    asked = normalize(question)
    return next((side for side, (pattern, _, _) in SIDES.items() if pattern.search(asked)), None)


# A man down has no card of its own: the answer is written by code from the 11 v 10 card, as the
# opponent's moves, with a real case from the side that was down to ten. Asked to keep the two sides
# apart, the model mixed them (E17 after the side check: "non concedete ripartenze", the advice of the
# team with the extra man, given to the coach, and a lead nobody had mentioned).
MAN_DOWN_CARD = "situation_giocare_in_superiorita_numerica"
_MAN_DOWN_LINE_RE = re.compile(r"\bin dieci\b|\buomo in meno\b|\binferiorit|\b10 contro 11\b")
_MAN_UP_LINE_RE = re.compile(r"\b11 contro 10\b|superiorit")


def writes_man_down(question: str, earlier: str = "") -> bool:
    """True when the answer for a man down is written by code: the coach is a man down and their
    questions (`earlier`: the ones before, in a chat) give no score. With a score ("siamo in 10 e
    stiamo vincendo 1-0") the card for that score applies, and the model answers under the side check."""
    return coach_side(question) == "a man down" and not _COACH_SCORE_RE.search(normalize(f"{question}\n{earlier}"))


def man_down_answer(card_ids: Iterable[str], card_text: Callable[[str], str | None],
                    english: bool = False) -> tuple[str, list[str]] | None:
    """(answer, cards it rests on) for a coach playing with a man down: "Non lo so" for the advice,
    the options of the 11 v 10 card as what the opponent will try (its own words), and a real case
    written from the side that was down to ten (a line citing the same final that speaks of ten men,
    not of the extra man). None if the card has no options."""
    text = card_text(MAN_DOWN_CARD) or ""
    options, in_options = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            in_options = "opzioni" in line.lower()
        elif in_options and re.match(r"\s*\d+[.)]\s", line):
            options.append(card_sentence(re.sub(r"\s*\[vedi [^\]]*\]", "", line)) + ".")
    if not options:
        return None
    finals, example = set(case_ids(text)), None
    for card in (c for c in card_ids if c != MAN_DOWN_CARD):
        for line in (card_text(card) or "").splitlines():
            plain = normalize(line)
            if set(case_ids(line)) & finals and _MAN_DOWN_LINE_RE.search(plain) and not _MAN_UP_LINE_RE.search(plain):
                example = (card, card_sentence(line))
                break
        if example:
            break
    if english:
        head = ("I don't know: the cards have no advice for a team playing with one man less.\n\n"
                f"What the team with the extra man will try (card text in Italian, written from its side: "
                f"there \"l'avversario\" is you) [{MAN_DOWN_CARD}]:")
        case = "Real case from the side that was down to ten (card text, in Italian)"
    else:
        head = ("Non lo so: nelle schede non ci sono consigli per chi gioca con un uomo in meno.\n\n"
                "Cosa proverà a fare chi ha l'uomo in più (la scheda è scritta dal suo punto di vista: lì "
                f"«l'avversario» siete voi) [{MAN_DOWN_CARD}]:")
        case = "Caso reale dalla parte di chi era in 10"
    answer = head + "\n" + "\n".join(f"- {o}" for o in options)
    if example:
        answer += f"\n\n{case}: {example[1]} [{example[0]}]."
    return answer, [MAN_DOWN_CARD] + ([example[0]] if example else [])


# ---------------------------------------------------------------- premises (E6)
# The coach's score taken for granted: to "e se restassimo in 10 al 90'?" the agent answered "dovete
# difendere il vantaggio" (E6), "per mantenere il vantaggio" (E17), with no score in the questions.
_SCORE_CLAIM_RE = re.compile(
    r"\b(?:mantenere|difendere|gestire|conservare|proteggere|amministrare)\s+(?:il\s+|l')?(?:vostro\s+|tuo\s+)?"
    r"(?:vantaggio|risultato)\b|\b(?:recuperare|rimontare)\s+(?:lo\s+)?(?:svantaggio|il\s+risultato)\b|"
    r"\b(?:siete|sei|essendo)\s+(?:in\s+vantaggio|in\s+svantaggio|sotto|avanti)\b|"
    r"\b(?:protect|keep|defend|hold)\s+(?:your|the)\s+lead\b|\b(?:you are|you're)\s+(?:ahead|behind|winning|losing)\b")
_COACH_SCORE_RE = re.compile(
    r"vantaggio|svantaggio|\bsotto\b|\bavanti\b|vincendo|perdendo|vinciamo|perdiamo|pareggi|"
    r"(?<![-\d])\b\d{1,2}\s*-\s*\d{1,2}\b(?!\s*-\s*\d)|\b\d{1,2}\s+a\s+\d{1,2}\b|"   # a score, not a formation (4-3-3)
    r"risultato|\blead\b|winning|losing|behind|ahead|\bdraw")


def premise_issues(answer: str, coach_text: str) -> list[Issue]:
    """Sentences that take the coach's score for granted ("mantenere il vantaggio") when the coach's
    questions (`coach_text`) never gave one."""
    if _COACH_SCORE_RE.search(normalize(coach_text)):
        return []
    return [Issue(
        "premise", sentence,
        f"\"{sentence}\": the coach never said the score. Do not assume a lead or a deficit: give advice "
        "that holds whatever the score, or say what changes if they are ahead or behind.")
        for sentence in sentences(collapse_real_cases(answer))
        if _SCORE_CLAIM_RE.search(normalize(BRACKETS_RE.sub(" ", sentence)))]


def perspective_issues(answer: str, question: str, earlier: str = "") -> list[Issue]:
    """The advice of the mirror situation given to the coach: the card for the other side cited,
    and not the card for the coach's side (or, with no such card, no "Non lo so"). A man down who
    also gave the score (here or in `earlier`, the coach's questions before) may get the card for
    that score: "siamo in 10 e stiamo vincendo" rests on the card for defending a lead."""
    asked, cited = normalize(question), cited_ids(answer)
    known = normalize(f"{question}\n{earlier}")
    owns = {own for pattern, _, own in SIDES.values() if own and pattern.search(known)}
    for side, (pattern, mirror, own) in SIDES.items():
        if not pattern.search(asked) or mirror not in cited:
            continue
        if (own and own in cited) or (own is None and (is_abstention(answer) or owns & set(cited))):
            continue
        fix = (f"base the advice on [{own}]" if own else
               "write \"Non lo so\" for the advice: the cards have none for that side")
        return [Issue(
            "perspective", f"{mirror} for a team {side}",
            f"The coach's team is {side}, but [{mirror}] is written for the other side (the opponent here). "
            f"Do not give its options as the coach's own: {fix}, and use [{mirror}] only to say what the "
            "opponent will try, as the opponent's moves.")]
    return []

"""Coaches and teams, and thresholds: two families of wrong facts checked by rules, without a model
call (`fact_issues`).

- a coach put at a team the cards never give him (E4 "l'Atalanta di Italiano", E3 "il Milan di
  Pioli", "il PSG era allenato da Scaloni"): the pair must be in the cards, the team named in the
  coach's card or the pair of a final's metadata; sentences with a negation are left alone ("la tesi
  non parla del Milan di Pioli" is right);
- a threshold the cards never state (E5 "un PPDA inferiore a 10 indica un pressing d'élite"): a
  comparison with a number about a metric must be written in the consulted cards.
Such an issue goes into the output guardrail's single rewrite; if it is still there after the
rewrite, the sentence is removed (`remove_sentences`): a wrong fact found never reaches the coach.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from functools import lru_cache

from src.corpus.cards import load_manifest_cards
from src.guardrails.output_guard import Issue
from src.guardrails.real_case import collapse_real_cases
from src.guardrails.text import normalize, sentences

# ---------------------------------------------------------------- coaches and teams
# The teams an answer may name, with the other names they go by (accents removed, lower case).
TEAMS = {
    "Atalanta": ("atalanta",), "Inter": ("inter", "internazionale"), "Milan": ("milan",),
    "Juventus": ("juventus", "juve"), "Napoli": ("napoli",), "Roma": ("roma",), "Lazio": ("lazio",),
    "Fiorentina": ("fiorentina",), "Sassuolo": ("sassuolo",), "Chievo": ("chievo",), "Spezia": ("spezia",),
    "Bologna": ("bologna",), "Torino": ("torino",), "Genoa": ("genoa",), "Udinese": ("udinese",),
    "Brescia": ("brescia",), "Trapani": ("trapani",), "Benevento": ("benevento",), "Parma": ("parma",),
    "Empoli": ("empoli",), "Cagliari": ("cagliari",), "Verona": ("verona", "hellas"), "Palermo": ("palermo",),
    "Manchester City": ("manchester city", "city"), "Manchester United": ("manchester united", "united"),
    "Paris Saint-Germain": ("paris saint-germain", "paris saint germain", "psg"),
    "Bayer Leverkusen": ("bayer leverkusen", "leverkusen"), "Bayern": ("bayern monaco", "bayern munich", "bayern"),
    "Borussia Dortmund": ("borussia dortmund", "dortmund"), "Liverpool": ("liverpool",), "Chelsea": ("chelsea",),
    "Arsenal": ("arsenal",), "Tottenham": ("tottenham",), "Brighton": ("brighton",),
    "Real Madrid": ("real madrid",), "Barcellona": ("barcellona", "barcelona", "barca"),
    "Atletico Madrid": ("atletico madrid", "atletico"), "Marsiglia": ("marsiglia", "marseille"),
    "Shakhtar": ("shakhtar",), "Spagna": ("spagna", "spain"), "Argentina": ("argentina",),
    "Francia": ("francia", "france"), "Inghilterra": ("inghilterra", "england"), "Italia": ("italia", "italy"),
    "Germania": ("germania", "germany"), "Portogallo": ("portogallo", "portugal"),
}
_NEGATION_RE = re.compile(r"\b(?:non|not|never|mai|nessun[oa]?|neither|nor)\b")


@lru_cache(maxsize=1)
def coach_knowledge() -> tuple[dict[str, str], set[tuple[str, str]]]:
    """({coach surname: text of the coach's card}, {(team, coach surname) of the finals' metadata}),
    from the indexed cards (offline, read once)."""
    cards = load_manifest_cards()
    coaches = {c.document_id.removeprefix("coach_").replace("_", " "): normalize(c.body)
               for c in cards if c.document_id.startswith("coach_")}
    pairs: set[tuple[str, str]] = set()
    for card in cards:
        for team, coach in (card.metadata.get("coaches") or {}).items():
            canonical = _team_of(normalize(str(team)))
            if canonical:
                surname = normalize(str(coach)).split()[-1]
                coaches.setdefault(surname, "")
                pairs.add((canonical, surname))
    return coaches, pairs


def _team_of(name: str) -> str | None:
    return next((team for team, names in TEAMS.items() if name in names), None)


def _team_pattern() -> str:
    names = sorted({n for names in TEAMS.values() for n in names}, key=len, reverse=True)
    return "|".join(re.escape(n) for n in names)


def _pairs_in(sentence: str, coaches: Iterable[str]) -> list[tuple[str, str]]:
    """(team, coach) pairs a sentence states: "l'Atalanta di Italiano", "il PSG era allenato da
    Scaloni", "Italiano all'Atalanta", "Scaloni sulla panchina del PSG", "Italiano's Atalanta"."""
    sentence = re.sub(r"[*_`]", "", sentence)   # "**Lionel Scaloni**" is a name like any other
    text = normalize(sentence)
    team, coach = _team_pattern(), "|".join(re.escape(c) for c in sorted(coaches, key=len, reverse=True))
    led = r"(?:allenat[oa]|guidat[oa]|coached|managed|led)\s+(?:da|by)"
    patterns = (
        rf"\b(?P<team>{team})\s+(?:di|del|dello|della|under)\s+(?:\w+\s+){{0,2}}(?P<coach>{coach})\b",
        # gold run 20261009-123326 (Q21): "Il PSG era allenato da Lionel Scaloni in quella finale"
        rf"\b(?P<team>{team})(?:\s+\w+){{0,3}}\s+{led}\s+(?:\w+\s+){{0,2}}(?P<coach>{coach})\b",
        rf"\b(?P<coach>{coach})\s+(?:al|alla|allo|all'|ai|at|with)\s*(?P<team>{team})\b",
        rf"\b(?P<coach>{coach})(?:\s+\w+){{0,2}}\s+(?:allenava|guidava|alla guida|sulla panchina|in panchina|"
        rf"allenatore|coach|manager|coached|managed)\s+(?:(?:del|della|dello|dell'|di|of|the)\s*)?(?:\w+\s+)?(?P<team>{team})\b",
        rf"\b(?P<coach>{coach})'s\s+(?P<team>{team})\b",
        # E3 (Q18): "Pioli ... il suo Milan": a possessive pointing back to the coach of the same sentence
        rf"\b(?P<coach>{coach})\b[^.;]*?\b(?:il\s+suo|la\s+sua|del\s+suo|della\s+sua|al\s+suo|alla\s+sua|"
        rf"col\s+suo|con\s+il\s+suo|his)\s+(?:\w+\s+)?(?P<team>{team})\b",
        # gold run 20261014-145440 (Q18): "l'approccio di Pioli anche nel Milan"
        rf"\b(?P<coach>{coach})(?:\s+\w+){{0,2}}\s+(?:nel|nella|al|alla|col|in)\s+(?P<team>{team})\b",
    )
    proper = unicodedata.normalize("NFKD", sentence).encode("ascii", "ignore").decode()
    found = []
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            canonical = _team_of(m.group("team"))
            # the coach as a proper noun: "Italiano" the coach, not "italiano" the adjective
            if canonical and re.search(rf"\b{re.escape(m.group('coach').title())}\b", proper):
                found.append((canonical, m.group("coach")))
    return found


def _coach_had_team(team: str, coach: str) -> bool:
    coaches, pairs = coach_knowledge()
    if (team, coach) in pairs:
        return True
    card = coaches.get(coach, "")
    return any(re.search(rf"\b{re.escape(name)}\b", card) for name in TEAMS[team])



# ---------------------------------------------------------------- thresholds
_THRESHOLD_RE = re.compile(
    r"\b(?:(?:inferiore|superiore|minore|maggiore)\s+(?:a|al|allo|alla|ai|di)|(?:sotto|sopra|oltre)"
    r"(?:\s+(?:il|i|lo|la|l'))?|almeno|meno\s+di|piu\s+di|al\s+di\s+(?:sotto|sopra)\s+(?:di|del)|below|above|"
    r"under|over|at\s+least|less\s+than|more\s+than|greater\s+than|lower\s+than|higher\s+than|fewer\s+than)"
    r"\s*\d+(?:[.,]\d+)?\s*%?")
_METRIC_RE = re.compile(r"\b(?:ppda|xg|xga|possesso|possession|field tilt|pass share|linee rotte|line-breaking|"
                        r"pressioni|pressures|ricezioni|receptions|duelli|duels)\b")



# ---------------------------------------------------------------- the check
def fact_issues(answer: str, source_text: str) -> list[Issue]:
    """Coach-team pairs and thresholds of `answer` that the cards do not state; `detail` is the
    sentence, exactly as written (the one `remove_sentences` takes out if the rewrite keeps it)."""
    coaches, _ = coach_knowledge()
    known = normalize(source_text)
    issues: list[Issue] = []
    for sentence in sentences(collapse_real_cases(answer)):
        text = normalize(sentence)
        if not _NEGATION_RE.search(text):
            for team, coach in dict.fromkeys(_pairs_in(sentence, coaches)):
                if not _coach_had_team(team, coach):
                    issues.append(Issue(
                        "coach_team", sentence,
                        f"In \"{sentence}\" the cards never put {coach.title()} at {team}: a coach and a team "
                        "taken from two different cards. Correct it with the team the cards give for that "
                        "coach, or the coach they give for that team; if the cards do not say who coached that "
                        "team, write \"Non lo so\" (in English: \"I don't know\") for that detail."))
                    break
        if _METRIC_RE.search(text):
            for m in _THRESHOLD_RE.finditer(text):
                if m.group(0).strip() not in known:
                    issues.append(Issue(
                        "threshold", sentence,
                        f"\"{sentence}\": the cards give no such threshold ({m.group(0).strip()}). Do not turn "
                        "a value into a rule: report the concrete values the cards give, with their team "
                        "and season, or write \"Non lo so\" for the threshold."))
                    break
    return issues

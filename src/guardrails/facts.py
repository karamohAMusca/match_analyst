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

Two more families are checked by rules, without a model call (`fact_issues`):
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
from collections.abc import Callable, Iterable
from functools import lru_cache

from src.corpus.cards import load_manifest_cards
from src.guardrails.output_guard import BRACKETS_RE, Issue, cited_ids, citation_ids

FACT_KINDS = ("coach_team", "threshold")

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


# ---------------------------------------------------------------- sentences
def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.replace("’", "'")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text.lower())


def sentences(text: str) -> list[str]:
    """The sentences of `text`, exactly as written (substrings), line by line; a full stop inside
    brackets or parentheses ("[coach_pioli, p. 4]", "(Spalla, pp. 45-46)") does not end a sentence."""
    out: list[str] = []
    for line in text.splitlines():
        start, depth = 0, 0
        for i, char in enumerate(line):
            if char in "[(":
                depth += 1
            elif char in "])":
                depth = max(depth - 1, 0)
            elif char in ".!?" and depth == 0 and (i + 1 == len(line) or line[i + 1].isspace()):
                if line[start:i + 1].strip():
                    out.append(line[start:i + 1].strip())
                start = i + 1
        if line[start:].strip():
            out.append(line[start:].strip())
    return out


def remove_sentences(answer: str, wrong: Iterable[str]) -> str:
    """`answer` without the `wrong` sentences; a bullet or a line left without words goes too, and an
    answer left without any is "Non lo so."."""
    wrong = [w for w in wrong if w]
    lines = []
    for line in answer.splitlines():
        kept = line
        for sentence in wrong:
            kept = kept.replace(sentence, "")
        if kept != line:
            words = re.sub(r"\*\*[^*]*\*\*", "", _LEAD_RE.sub("", kept))
            if not re.search(r"[^\W\d_]", words):
                continue
            kept = re.sub(r"[ \t]{2,}", " ", kept).rstrip()
        lines.append(kept)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return result if re.search(r"[^\W\d_]", result) else "Non lo so."


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
    coaches = {c.document_id.removeprefix("coach_").replace("_", " "): _normalize(c.body)
               for c in cards if c.document_id.startswith("coach_")}
    pairs: set[tuple[str, str]] = set()
    for card in cards:
        for team, coach in (card.metadata.get("coaches") or {}).items():
            canonical = _team_of(_normalize(str(team)))
            if canonical:
                surname = _normalize(str(coach)).split()[-1]
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
    text = _normalize(sentence)
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
    known = _normalize(source_text)
    issues: list[Issue] = []
    for sentence in sentences(collapse_real_cases(answer)):
        text = _normalize(sentence)
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

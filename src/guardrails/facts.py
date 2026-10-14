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
And the side of a game situation (`perspective_issues`, E17): a coach "a man down", "behind" or
"ahead" (first-person phrases) must not get the advice of the mirror card as their own; a man down,
which has no card, gets an answer written by code (`man_down_answer`). A score the coach never gave
must not be taken for granted (`premise_issues`, E6).
Such an issue goes into the output guardrail's single rewrite; if it is still there after the
rewrite, the sentence is removed (`remove_sentences`): a wrong fact found never reaches the coach.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from functools import lru_cache

from src.corpus.cards import load_manifest_cards
from src.guardrails.output_guard import BRACKETS_RE, Issue, cited_ids, citation_ids, is_abstention

FACT_KINDS = ("coach_team", "threshold", "premise")

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
    if len(lines) < 2 or _LEAD_RE.sub("", lines[-1]) != lines[-1] or CASE_LINE_RE.match(lines[-1]):
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
    if _ABSTAINED_RE.search(_normalize(answer)):
        return None
    lines = (line for line in answer.splitlines() if not CASE_LINE_RE.match(line))
    return next((s for line in lines for s in sentences(line) if _UNKNOWN_RE.search(_normalize(s))), None)


# ---------------------------------------------------------------- thresholds
_THRESHOLD_RE = re.compile(
    r"\b(?:(?:inferiore|superiore|minore|maggiore)\s+(?:a|al|allo|alla|ai|di)|(?:sotto|sopra|oltre)"
    r"(?:\s+(?:il|i|lo|la|l'))?|almeno|meno\s+di|piu\s+di|al\s+di\s+(?:sotto|sopra)\s+(?:di|del)|below|above|"
    r"under|over|at\s+least|less\s+than|more\s+than|greater\s+than|lower\s+than|higher\s+than|fewer\s+than)"
    r"\s*\d+(?:[.,]\d+)?\s*%?")
_METRIC_RE = re.compile(r"\b(?:ppda|xg|xga|possesso|possession|field tilt|pass share|linee rotte|line-breaking|"
                        r"pressioni|pressures|ricezioni|receptions|duelli|duels)\b")


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
    asked = _normalize(question)
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
    return coach_side(question) == "a man down" and not _COACH_SCORE_RE.search(_normalize(f"{question}\n{earlier}"))


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
            options.append(_card_sentence(re.sub(r"\s*\[vedi [^\]]*\]", "", line)) + ".")
    if not options:
        return None
    finals, example = set(_case_ids(text)), None
    for card in (c for c in card_ids if c != MAN_DOWN_CARD):
        for line in (card_text(card) or "").splitlines():
            plain = _normalize(line)
            if set(_case_ids(line)) & finals and _MAN_DOWN_LINE_RE.search(plain) and not _MAN_UP_LINE_RE.search(plain):
                example = (card, _card_sentence(line))
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
    if _COACH_SCORE_RE.search(_normalize(coach_text)):
        return []
    return [Issue(
        "premise", sentence,
        f"\"{sentence}\": the coach never said the score. Do not assume a lead or a deficit: give advice "
        "that holds whatever the score, or say what changes if they are ahead or behind.")
        for sentence in sentences(collapse_real_cases(answer))
        if _SCORE_CLAIM_RE.search(_normalize(BRACKETS_RE.sub(" ", sentence)))]


def perspective_issues(answer: str, question: str, earlier: str = "") -> list[Issue]:
    """The advice of the mirror situation given to the coach: the card for the other side cited,
    and not the card for the coach's side (or, with no such card, no "Non lo so"). A man down who
    also gave the score (here or in `earlier`, the coach's questions before) may get the card for
    that score: "siamo in 10 e stiamo vincendo" rests on the card for defending a lead."""
    asked, cited = _normalize(question), cited_ids(answer)
    known = _normalize(f"{question}\n{earlier}")
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

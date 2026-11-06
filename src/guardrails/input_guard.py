"""Input guardrail: decides, before any model call, whether a question reaches the agent.

Code that prevents, not a prompt that asks: prompt-injection attempts, off-topic
questions and oversized inputs get a fixed reply and never reach the LLM; greetings get the
presentation without spending a call. Every verdict carries its reason, so the caller can show
it: "a silent guardrail is indistinguishable from a broken one".
The football test is a vocabulary check (words, stems, formations such as 4-3-3 or 433, and game
situations: the minute, the score, the phase of the match, a man down), generous on purpose: a
football question wrongly blocked is worse than an off-topic one let through, which the system
prompt still turns away. In a conversation, a question with no football word goes through
as a follow-up only if it looks like one: short ("e perché?", "come mai?"), opening like a
continuation ("e...", "ma...", "quindi..."), or pointing back ("questo", "un esempio", "spiegami
meglio"). Anything else is off topic even mid-conversation (found while building the app: an
off-topic request after a first question used to reach the model).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.guardrails.language import detect_language

MAX_QUESTION_CHARS = 2000

INJECTION_RE = re.compile(
    r"\b(?:ignor|dimentic)\w*\s+(?:(?:tutte|le|tue|mie|queste|precedenti)\s+)*(?:istruzioni|regole)"
    r"|\bignore\s+(?:(?:all|the|your|any|previous|prior|above)\s+)*(?:instructions|rules)"
    r"|\bsystem\s*prompt|\bprompt\s+di\s+sistema|\bjailbreak|\bdeveloper\s+mode"
    r"|\byou\s+are\s+now\b|\bda\s+(?:ora|adesso)(?:\s+in\s+poi)?\s+sei\b",
    re.IGNORECASE,
)
FORMATION_RE = re.compile(r"\b\d-\d-\d(?:-\d)?\b")
COMPACT_FORMATION_RE = re.compile(r"\b[1-5]{3,4}\b")   # 352, 4231: digits of the 10 outfield players
# English football terms no stem or word above covers ("my full-backs", "against a back four", "centre-backs");
# only terms that are football and nothing else ("build up" or "back pain" are not).
FOOTBALL_PHRASE_RE = re.compile(
    r"\b(?:back\s+(?:three|four|five)|back\s?line|(?:full|wing|centre|center)[\s-]?backs?|(?:low|mid|high)\s+(?:block|line)"
    r"|set[\s-]?pieces?|false\s+(?:nine|9))\b", re.IGNORECASE)
# A final and a national team together ("argentina francia finale"): the finals of the corpus are between
# national teams. Neither alone is football: "il finale del film", "la capitale della Francia".
FINAL_RE = re.compile(r"\b(?:semi)?final[ei]\b", re.IGNORECASE)
NATIONAL_TEAM_RE = re.compile(
    r"\b(?:argentina|francia|spagna|inghilterra|italia|germania|brasile|portogallo|olanda|croazia|marocco|belgio|uruguay"
    r"|france|spain|england|italy|germany|brazil|portugal|netherlands|croatia|morocco|belgium)\b", re.IGNORECASE)
# Game situations, also with no football word ("sto perdendo e sono al 90esimo, che devo fare?").
SITUATION_RE = re.compile(
    r"\b\d{1,3}\s*(?:esimo\b|['’°]|min\b|minut)"                         # 90esimo, 90', 90°, 85 min, 10 minuti
    r"|\b(?:quarant|cinquant|sessant|settant|ottant|novant)\w*esimo\b"     # novantesimo, ottantacinquesimo
    r"|\b\d{1,2}\s*[-–]\s*\d{1,2}\b"                                       # the score: 1-0, 2 - 2
    r"|\b(?:sotto|avanti)\s+di\s+(?:un|uno|una|due|tre|\d+)\b"             # sotto di uno, avanti di due
    r"|\b(?:primo|secondo)\s+tempo\b|\b(?:first|second)\s+half\b|\bhalf[\s-]?time\b"
    r"|\b(?:extra|injury|stoppage)\s+time\b"
    r"|\brimast\w*\s+in\s+(?:dieci|nove|10|9)\b|\buom[oi]\s+in\s+(?:meno|piu|più)\b"   # a man down or up
    r"|\b(?:siamo|restiamo|rimaniamo|eravamo|saremmo|restassimo|rimanessimo|fossimo)\s+in\s+(?:dieci|nove|otto|10|9|8)\b"
    r"(?!\s+(?:a\s|persone|ospiti|amici|invitati))"                                    # "siamo in 10, come ci difendiamo?"
    r"|\b(?:superiorit|inferiorit)\w*\s+numeric|\bdown\s+to\s+(?:ten|nine|10|9)\b|\bman\s+(?:down|up)\b"
    # a final or a European Championship with its year right after ("la finale del 2022", "l'Europeo 2024"): the
    # corpus has some of them; with other words between ("la finale di Sanremo 2022") it is not a football rule
    r"|\b(?:finale|finali)\s+(?:(?:del|dei|nel)\s+)?(?:19|20)\d\d\b|\b(?:europeo|europei)\s+(?:del\s+)?(?:19|20)\d\d\b",
    re.IGNORECASE,
)
FOOTBALL_STEMS = (
    # Italian
    "calci", "pallon", "squadr", "allen", "difes", "difens", "attacc", "centrocamp", "portier",
    "terzin", "median", "trequart", "tattic", "campionat", "classific", "mondial", "contropied",
    "ripartenz", "transizion", "marcatur", "press", "riaggress", "fuorigioc", "sovrappos", "inserim",
    "dribbl", "arbitr", "panchin", "spogliat", "tifos", "scudett", "rifinit", "avversar", "formazion",
    "gioc", "affront", "punizion", "centravant",
    # Italian, game situations: the score, the time, changes, cards
    "vantagg", "svantagg", "rimont", "pareggi", "sostitu", "subentr", "supplementar", "recuper",
    "espuls", "ammoni", "cartellin", "infortun", "intervall",
    # English
    "footbal", "soccer", "coach", "player", "defen", "attack", "midfield", "striker", "winger",
    "flank", "goalkeep", "tactic", "offside", "penalt", "goal", "counter", "opponent", "play",
    "equaliz", "substitut", "stoppage", "comeback",
)
FOOTBALL_WORDS = frozenset(
    # Italian
    "palla palle gol rigore rigori partita partite gara gare fascia fasce punta punte blocco campo "
    "modulo moduli esterno esterni regista registi mister derby tiro tiri cross corner stadio "
    "champions uefa fifa euro coverciano ppda xg "
    # game situations: exact forms only ("vincerà le elezioni", "ho perso le chiavi" stay off topic)
    "perdendo perdiamo vincendo vinciamo risultato punteggio minuto minuti cambi cambio "
    # English
    "ball team teams pitch match matches wing block formation league cup final finals possession "
    "marking losing winning trailing minute minutes score scoreline "
    # coaches, clubs and national teams of the corpus
    "pioli gasperini klopp guardiola conte inzaghi ancelotti scaloni zerbi spalletti inter milan "
    "juventus juve napoli roma lazio atalanta fiorentina sassuolo chievo spezia trapani psg arsenal "
    "liverpool chelsea manchester barcellona barcelona bayern leverkusen dortmund".split()
)
GREETING_WORDS = frozenset("ciao salve buongiorno buonasera hey hello hi".split())
# What a follow-up looks like when it has no football word (accents removed, as in _words()).
MAX_FOLLOW_UP_WORDS = 4
FOLLOW_UP_START = frozenset("e ma and but quindi allora ok okay invece perche why so".split())
FOLLOW_UP_WORDS = frozenset(
    "questo questa quello quella questi quelli cosi esempio esempi spiega spiegami spiegare meglio "
    "dettagli dettaglio riassumi this that these those example examples explain detail details "
    # who the conversation is about ("quali sono i suoi punti deboli?" after a question on a coach)
    "suo sua suoi sue lui lei his her him their them".split()
)
THANKS_WORDS = frozenset("grazie thanks thank".split())
ABOUT_YOU_RE = re.compile(r"\b(?:chi sei|cosa sai fare|cosa fai|who are you|what can you do)\b")

REPLIES = {
    ("greeting", "it"): "Ciao! Sono Match Analyst, un assistente per allenatori: ti aiuto a preparare le "
                        "partite e a gestire le situazioni di gara con consigli basati su fonti citate "
                        "(finali recenti, situazioni di gioco, profili di allenatori, tesi di Coverciano). "
                        "Descrivimi la tua squadra, l'avversario o la situazione.",
    ("greeting", "en"): "Hi! I'm Match Analyst, an assistant for football coaches: I help you prepare "
                        "matches and handle in-game situations with advice grounded in cited sources "
                        "(recent finals, game situations, coach profiles, Coverciano theses). Describe "
                        "your team, the opponent or the situation.",
    ("thanks", "it"): "Prego! Se hai un'altra situazione di gioco, descrivimela.",
    ("thanks", "en"): "You're welcome! If you have another game situation, describe it.",
    ("off_topic", "it"): "Posso aiutarti solo con la tattica calcistica. Se è una domanda di calcio, "
                         "riformulala citando squadra, modulo o situazione di gioco.",
    ("off_topic", "en"): "I can only help with football tactics. If it is a football question, rephrase "
                         "it naming a team, a formation or a game situation.",
    ("injection", "it"): "Non posso cambiare le mie istruzioni. Fammi pure una domanda di tattica calcistica.",
    ("injection", "en"): "I cannot change my instructions. Feel free to ask me a football tactics question.",
    ("too_long", "it"): f"La domanda è troppo lunga (massimo {MAX_QUESTION_CHARS} caratteri): riassumi "
                        "la tua squadra, l'avversario e la situazione.",
    ("too_long", "en"): f"The question is too long (at most {MAX_QUESTION_CHARS} characters): summarize "
                        "your team, the opponent and the situation.",
    ("empty", "it"): "Scrivi una domanda: descrivimi la tua squadra, l'avversario o la situazione di gara.",
    ("empty", "en"): "Write a question: describe your team, the opponent or the game situation.",
}


@dataclass(frozen=True)
class InputVerdict:
    """`allowed`: the question goes to the agent; otherwise `reply` is the answer to show."""

    allowed: bool
    reason: str      # football | follow_up | greeting | thanks | off_topic | injection | too_long | empty
    language: str
    reply: str | None = None


def _words(text: str) -> list[str]:
    ascii_text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z]+", ascii_text)


def is_football(text: str) -> bool:
    """True if the text has a football word, stem, formation or game situation (generous on purpose)."""
    if FORMATION_RE.search(text) or SITUATION_RE.search(text):
        return True
    if any(sum(map(int, m)) == 10 for m in COMPACT_FORMATION_RE.findall(text)):
        return True
    if FINAL_RE.search(text) and NATIONAL_TEAM_RE.search(text):
        return True
    if FOOTBALL_PHRASE_RE.search(text):
        return True
    return any(w in FOOTBALL_WORDS or w.startswith(FOOTBALL_STEMS) for w in _words(text))


def check_question(question: str, in_conversation: bool = False) -> InputVerdict:
    """Verdict on one question; `in_conversation`: earlier turns exist, so follow-ups are allowed."""
    text = question.strip()
    language = detect_language(text)

    def blocked(reason: str) -> InputVerdict:
        return InputVerdict(False, reason, language, REPLIES[(reason, language)])

    if not text:
        return blocked("empty")
    if len(text) > MAX_QUESTION_CHARS:
        return blocked("too_long")
    if INJECTION_RE.search(text):
        return blocked("injection")
    if is_football(text):
        return InputVerdict(True, "football", language)
    words = set(_words(text))
    if words & THANKS_WORDS:
        return blocked("thanks")
    if words & GREETING_WORDS or ABOUT_YOU_RE.search(text.lower()):
        return blocked("greeting")
    if in_conversation and looks_like_follow_up(_words(text)):
        return InputVerdict(True, "follow_up", language)
    return blocked("off_topic")


def looks_like_follow_up(words: list[str]) -> bool:
    """Short, opening like a continuation, or pointing back to the previous answer."""
    return (len(words) <= MAX_FOLLOW_UP_WORDS or words[0] in FOLLOW_UP_START
            or bool(set(words) & FOLLOW_UP_WORDS))

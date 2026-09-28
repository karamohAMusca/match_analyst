"""Input guardrail: decides, before any model call, whether a question reaches the agent.

Code that prevents, not a prompt that asks: prompt-injection attempts, off-topic
questions and oversized inputs get a fixed reply and never reach the LLM; greetings get the
presentation without spending a call. Every verdict carries its reason, so the caller can show
it: "a silent guardrail is indistinguishable from a broken one".
The football test is a vocabulary check (words, stems and formations such as 4-3-3), generous on
purpose: a football question wrongly blocked is worse than an off-topic one let through, which the
system prompt still turns away. In a conversation, a question with no football word ("e perché?")
is a follow-up and goes through.
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
FOOTBALL_STEMS = (
    # Italian
    "calci", "pallon", "squadr", "allen", "difes", "difens", "attacc", "centrocamp", "portier",
    "terzin", "median", "trequart", "tattic", "campionat", "classific", "mondial", "contropied",
    "ripartenz", "transizion", "marcatur", "press", "riaggress", "fuorigioc", "sovrappos", "inserim",
    "dribbl", "arbitr", "panchin", "spogliat", "tifos", "scudett", "rifinit", "avversar", "formazion",
    # English
    "footbal", "soccer", "coach", "player", "defen", "attack", "midfield", "striker", "winger",
    "flank", "goalkeep", "tactic", "offside", "penalt", "goal", "counter",
)
FOOTBALL_WORDS = frozenset(
    # Italian
    "palla palle gol rigore rigori partita partite gara gare fascia fasce punta punte blocco campo "
    "modulo moduli esterno esterni regista registi mister derby tiro tiri cross corner stadio "
    "champions uefa fifa euro coverciano ppda xg "
    # English
    "ball team teams pitch match matches wing block formation league cup final finals possession "
    "marking "
    # coaches, clubs and national teams of the corpus
    "pioli gasperini klopp guardiola conte inzaghi ancelotti scaloni zerbi spalletti inter milan "
    "juventus juve napoli roma lazio atalanta fiorentina sassuolo chievo spezia trapani psg arsenal "
    "liverpool chelsea manchester barcellona barcelona bayern leverkusen dortmund".split()
)
GREETING_WORDS = frozenset("ciao salve buongiorno buonasera hey hello hi".split())
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
    """True if the text has a football word, stem or formation (generous on purpose)."""
    if FORMATION_RE.search(text):
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
    if in_conversation:
        return InputVerdict(True, "follow_up", language)
    return blocked("off_topic")

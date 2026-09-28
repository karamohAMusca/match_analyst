"""Language of a text, Italian or English: the two languages of the project.

Counted from function words, offline and instant. Words shared by the two languages ("a", "in",
"e", the Italian article "i") are left out; a tie goes to Italian, the default language.
Checked on the gold questions and on the answers of the full runs of 2026-09-28.
"""

from __future__ import annotations

import re

ITALIAN_WORDS = frozenset(
    "il lo gli della delle dei degli che per con non sono una nel nella del alla dal più anche "
    "come cosa quale quali chi perché mia mio nostra nostro contro secondo ha hanno si ci".split()
)
ENGLISH_WORDS = frozenset(
    "the and of is are with that for this from which their its was were an be by to on how what "
    "who did does do my our we you should can against when why where would has have his her "
    "according it not don know".split()
)
_CITATION_RE = re.compile(r"\[[^\[\]\n]*\]")


def detect_language(text: str) -> str:
    """'en' or 'it' ('it' on a tie, e.g. an empty text); card citations are ignored."""
    words = re.findall(r"[^\W\d_]+", _CITATION_RE.sub(" ", text.lower()))
    english = sum(w in ENGLISH_WORDS for w in words)
    italian = sum(w in ITALIAN_WORDS for w in words)
    return "en" if english > italian else "it"

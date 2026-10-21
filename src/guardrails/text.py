"""The sentences of an answer, shared by the guardrails that work sentence by sentence: split
exactly as written (a full stop inside a citation does not end one), removed, compared without
accents or case."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

LEAD_RE = re.compile(r"^\s*(?:[-*•]\s+|\d+[.)]\s+)?")


def normalize(text: str) -> str:
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
            words = re.sub(r"\*\*[^*]*\*\*", "", LEAD_RE.sub("", kept))
            if not re.search(r"[^\W\d_]", words):
                continue
            kept = re.sub(r"[ \t]{2,}", " ", kept).rstrip()
        lines.append(kept)
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return result if re.search(r"[^\W\d_]", result) else "Non lo so."

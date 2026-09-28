"""Check the cards against their upstream sources (slow: reads every PDF in references/).

    python -m scripts.check_corpus

Checks:
1. every quoted passage in a card ("...") appears verbatim in the sources
   (accent-, case-, whitespace- and quote-style-insensitive);
2. every thesis page cited in a card body ([Author, p. N]) is listed in the card's `sources` header.

The fast structural checks (manifest, links, gold set) live in tests/ and run with pytest.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

from src.core.config import REFERENCES_DIR
from src.corpus.cards import load_cards

THESIS_AUTHORS = ("Soncin", "Spalla", "Dileo", "Pioli", "Italiano", "Contran", "Polenghi")

# Quotes that are verbatim in the PDF but cannot be matched in its extracted text.
KNOWN_EXCEPTIONS = {
    "rompeva la sua struttura per organizzare la riaggressione":
        "Soncin pp. 43-44: the sentence is split by footnotes 21-22 and a page break in the extracted text",
}

# A quote opens after a non-word character and closes before one: this avoids matching the text
# *between* two short quoted words ("prosa" ... "poesia").
QUOTE_RE = re.compile(r'(?<![\w])"([^"\n]{6,}?)"(?![\w])')
PAGE_RE = re.compile(r"\bpp?\. ([\d ,\-]+)")


def normalize(text: str) -> str:
    text = re.sub(r"[\"'“”‘’«»]", "", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", text).strip(" .")


def pages(spec: str) -> set[int]:
    out: set[int] = set()
    for start, end in re.findall(r"(\d+)(?:-(\d+))?", spec):
        a, b = int(start), int(end or start)
        if b - a < 300:
            out |= set(range(a, b + 1))
    return out


def load_source_text() -> str:
    parts: list[str] = []
    for pdf in sorted(REFERENCES_DIR.rglob("*.pdf")):
        with pymupdf.open(pdf) as doc:
            parts.extend(page.get_text() for page in doc)
    parts.extend(p.read_text(encoding="utf-8") for p in sorted(REFERENCES_DIR.rglob("*.md")))
    return normalize(" ".join(parts))


def check_quotes(cards, source_text: str) -> list[str]:
    problems = []
    for card in cards:
        for line in card.body.splitlines():
            for quote in QUOTE_RE.findall(line):
                if quote.strip() in KNOWN_EXCEPTIONS:
                    continue
                if normalize(quote) not in source_text:
                    problems.append(f"{card.document_id}: quote not found in sources: \"{quote[:90]}\"")
    return problems


def check_cited_pages(cards) -> list[str]:
    problems = []
    for card in cards:
        header: dict[str, set[int]] = {}
        for source in card.metadata["sources"]:
            author = source.split(",")[0].split()[0]
            match = PAGE_RE.search(source)
            if author in THESIS_AUTHORS and match:
                header.setdefault(author, set()).update(pages(match.group(1)))
        for block in re.findall(r"\[([^\]]+)\]", card.body):
            for author, spec in re.findall(rf"({'|'.join(THESIS_AUTHORS)}), pp?\. ([\d ,\-]+)", block):
                missing = pages(spec) - header.get(author, set())
                if missing:
                    problems.append(f"{card.document_id}: {author} pages {sorted(missing)} cited but not in header")
    return problems


def main() -> int:
    cards = load_cards()
    print(f"Reading sources in {REFERENCES_DIR} ...")
    problems = check_quotes(cards, load_source_text()) + check_cited_pages(cards)
    for p in problems:
        print("PROBLEM", p)
    print(f"{len(cards)} cards checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())

"""What a card may not contain: anything that could act as an instruction to the model that reads it.

A card is data. The agent reads it as the result of a search, and the MCP server hands it to other
hosts as the result of a tool: if a card said "ignore the previous instructions" or hid a command in
an invisible character, it would be an indirect prompt injection, the card playing the part of the
trap ticket. The cards are written by the project from cited sources (Wikipedia among them, which
anyone can edit), so the check is part of the maintenance of the corpus (`scripts/check_corpus.py`
and the tests), before a card is indexed.

Checks, on the file of a card:
- an instruction to the model ("ignora le istruzioni", "ignore previous instructions", "system
  prompt", "you are now"...): the patterns of the input guard, the same ones a question is stopped by;
- characters a reader does not see: zero-width and direction marks, the invisible "tag" characters;
- an HTML comment, which Markdown hides and a model reads, and the tags that load or run something
  (script, iframe, img, object, embed, style, link, meta, a, form, input);
- an external address or image in the text (the `sources` of the front matter cite the documents by
  address: that is where an address belongs).
"""

from __future__ import annotations

import re
from pathlib import Path

from src.core.config import CORPUS_DIR
from src.guardrails.input_guard import INJECTION_RE
from src.guardrails.links import strip_external_links

_FRONT_MATTER_RE = re.compile(r"\A---\n(?P<front>.*?)\n---\n(?P<body>.*)\Z", re.DOTALL)
_HIDDEN_RE = re.compile("[​-‏‪-‮⁠-⁤⁦-⁩﻿\U000e0000-\U000e007f]")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_TAG_RE = re.compile(r"<\s*/?\s*(?:script|iframe|img|object|embed|style|link|meta|a|form|input)\b", re.IGNORECASE)
_LIST_ITEM_RE = re.compile(r"^\s+-\s")   # a line of the front matter's lists: the `sources`


def card_problems(raw: str) -> list[str]:
    """What is wrong in the file of a card (its text, front matter included), one line each; empty if
    nothing is."""
    raw = raw.replace("\r\n", "\n")
    problems = []
    for match in INJECTION_RE.finditer(raw):
        problems.append(f"instruction to the model: «{match.group(0)}»")
    for match in _HIDDEN_RE.finditer(raw):
        line = raw.count("\n", 0, match.start()) + 1
        problems.append(f"invisible character U+{ord(match.group(0)):04X} on line {line}")
    for match in _COMMENT_RE.finditer(raw):
        problems.append(f"HTML comment: «{match.group(0)[:60]}»")
    for match in _TAG_RE.finditer(raw):
        problems.append(f"HTML tag: «{match.group(0)}»")
    parts = _FRONT_MATTER_RE.match(raw)
    front, body = (parts["front"], parts["body"]) if parts else ("", raw)
    for address in strip_external_links(body)[1]:
        problems.append(f"external address or image in the text: «{address[:80]}»")
    for line in front.split("\n"):
        if not _LIST_ITEM_RE.match(line) and (found := strip_external_links(line)[1]):
            problems.append(f"external address in the front matter, outside a list of sources: «{found[0][:80]}»")
    return problems


def corpus_problems(corpus_dir: Path = CORPUS_DIR) -> dict[str, list[str]]:
    """{card file relative to the corpus: its problems} for every card that has some."""
    found = {}
    for path in sorted(corpus_dir.rglob("*.md")):
        if problems := card_problems(path.read_text(encoding="utf-8")):
            found[path.relative_to(corpus_dir).as_posix()] = problems
    return found

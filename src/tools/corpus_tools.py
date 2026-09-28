"""Corpus tools for the agent: search the cards, read a whole card.

The search tool returns PASSAGES with their source, not a written
answer: the agent sees what the corpus says and what is missing, and cites `[document_id]`.
The tool descriptions are the contract with the model: they state what the corpus covers,
so the agent can tell when a question is outside it. Errors never raise: they come back as
a short explanation, so one failing call does not break the whole answer.

No `from __future__ import annotations` here: datapizza builds the tool schema from the real
parameter annotations, and postponed (string) annotations would break it.
"""

import json
import re
from typing import Annotated, Literal

from datapizza.tools import tool
from datapizza.type import Chunk

from src.observability.tracing import record_documents, set_output, span
from src.rag.retrieval import Retriever

Category = Literal["match_case", "game_situation", "coach_profile", "thesis_note", "glossary"]

SEARCH_DESCRIPTION = (
    "Search the football knowledge base (31 cards in Italian, every fact cited to its source) and "
    "return up to 5 results, one per card, each headed by its [document_id] and title; the first "
    "2 results are whole cards, the others one section. "
    "Coverage: recent finals and how the winner won (World Cup 2022 and 2026, Champions League "
    "2023, 2025 and 2026, Europa League 2024, Euro 2024); game situations (attacking a low block, "
    "building from the back, playing out of a high or man-to-man press, high press and "
    "counter-press, defending a lead, coming back from behind, playing 11 v 10, wing play); coach "
    "profiles (Ancelotti, Conte, De Zerbi, Gasperini, Guardiola, Inzaghi, Italiano, Klopp, Pioli, "
    "Scaloni); notes from Coverciano theses (zonal vs man-marking defence, positional play, "
    "relational play, training with variability); glossary of metrics (PPDA, xG, field tilt, ...) "
    "and formations. No live data, fixtures, current squads or statistics beyond these cards. "
    "Write the query in Italian with the specific terms you need. For a different piece of "
    "information, call it again with a different query."
)
READ_DESCRIPTION = (
    "Return the whole text of one card, given its document_id as shown in search results "
    "(e.g. coach_conte). Use it when a passage is not enough and you need the rest of that card."
)


_BRACKETS_RE = re.compile(r"\[([^\[\]\n]+)\]")


def source_header(document_id: str, title: str, section: str) -> str:
    """First line of a result: the id in brackets, exactly as the agent must cite it."""
    return f"[{document_id}] {title} · {section}"


def unbracket(text: str) -> str:
    """Card texts carry their own references in brackets ([Pioli, p. 4], [case_2026_...]).
    The model imitates what it sees and cited those instead of the card id (runs 160112 and
    160918). Turning them into parentheses keeps the information but leaves the card ids as
    the only bracketed tokens the agent receives."""
    return _BRACKETS_RE.sub(r"(\1)", text)


def merge_filtered(filtered: list[Chunk], unfiltered: list[Chunk], k: int) -> list[Chunk]:
    """A category filter is a preference, not a wall: the best unfiltered result comes first,
    then the filtered ones. A wrong filter (e.g. only thesis notes for "nella tesi di Pioli")
    can no longer hide the right card."""
    merged: list[Chunk] = []
    seen: set[str] = set()
    for chunk in unfiltered[:1] + filtered + unfiltered[1:]:
        card = chunk.metadata["document_id"]
        if card not in seen:
            merged.append(chunk)
            seen.add(card)
    return merged[:k]


def format_passages(chunks: list[Chunk], full_texts: dict[str, str] | None = None) -> str:
    """One block per chunk: source line, then the section text (or the whole card, if given)."""
    full_texts = full_texts or {}
    blocks = []
    for chunk in chunks:
        md = chunk.metadata
        card = md["document_id"]
        if card in full_texts:
            body = full_texts[card].removeprefix(f"{md['title']}\n\n")
            blocks.append(f"{source_header(card, md['title'], 'scheda intera')}\n{unbracket(body)}")
        else:
            text = chunk.text.removeprefix(f"{md['title']}\n\n")
            blocks.append(f"{source_header(card, md['title'], md['section'])}\n{unbracket(text)}")
    return "\n\n".join(blocks)


def card_context(cards: dict[str, str]) -> str:
    """Whole cards as one context block of "[card_id]\\ntext" blocks: what the output guardrail
    gives the model for its rewrite, and what the judge checks an answer against."""
    return "\n\n".join(f"[{card}]\n{unbracket(text)}" for card, text in cards.items() if text)


class CorpusTools:
    """The agent's tools, bound to one Retriever; `calls` logs what each tool returned.

    The first `full_cards` results come as whole cards (cards are short): a single section
    can miss the key part, e.g. the "Opzioni" of a game situation.
    """

    def __init__(self, retriever: Retriever, k: int = 5, full_cards: int = 2) -> None:
        self.retriever = retriever
        self.k = k
        self.full_cards = full_cards
        self.calls: list[dict] = []

    @tool(description=SEARCH_DESCRIPTION)
    def search_cards(
        self,
        query: Annotated[str, "What to look for, in Italian, with the key terms of the question"],
        categories: Annotated[
            list[Category] | None,
            "Optional: prefer these card types, e.g. ['coach_profile'] to compare coaches (the best overall result is always included)",
        ] = None,
    ) -> str:
        with span("retrieve", "RETRIEVER", query, metadata=json.dumps({"categories": categories})) as current:
            try:
                hits = self.retriever.retrieve(query, k=self.k)
                if categories:   # same query vector, served by the embedding cache: no extra cost
                    hits = merge_filtered(self.retriever.retrieve(query, k=self.k, categories=categories), hits, self.k)
            except Exception as e:  # network, Qdrant or API errors: explain instead of crashing
                self.calls.append({"tool": "search_cards", "query": query, "error": str(e)})
                set_output(current, f"error: {e}")
                return f"Search failed ({type(e).__name__}: {e}). Tell the user the knowledge base is unavailable."
            record_documents(current, hits)   # in Phoenix: the chunks found, with card id and score
        self.calls.append({
            "tool": "search_cards",
            "query": query,
            "categories": categories,
            "cards": [h.metadata["document_id"] for h in hits],
        })
        if not hits:
            return "No passage found for this query in the knowledge base."
        full = {}
        for hit in hits[: self.full_cards]:
            text = self.retriever.card_text(hit.metadata["document_id"])
            if text:
                full[hit.metadata["document_id"]] = text
        return format_passages(hits, full)

    @tool(description=READ_DESCRIPTION)
    def read_card(
        self,
        document_id: Annotated[str, "Card id exactly as shown in brackets, e.g. case_2026_wc_final_spain_argentina"],
    ) -> str:
        document_id = document_id.strip().strip("[]")
        text = self.retriever.card_text(document_id)
        self.calls.append({"tool": "read_card", "document_id": document_id, "found": text is not None})
        if text is None:
            return f"No card with document_id '{document_id}'. Use search_cards to find the right id."
        title, _, body = text.partition("\n\n")
        return f"{source_header(document_id, title, 'scheda intera')}\n{unbracket(body)}"

    def tools(self) -> list:
        """The tools to give to the datapizza Agent."""
        return [self.search_cards, self.read_card]

    def consulted_cards(self) -> list[str]:
        """Cards returned or read since the last reset, in order of first appearance."""
        cards: list[str] = []
        for call in self.calls:
            for card in call.get("cards", []) + ([call["document_id"]] if call.get("found") else []):
                if card not in cards:
                    cards.append(card)
        return cards

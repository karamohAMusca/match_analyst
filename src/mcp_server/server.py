"""Match Analyst as an MCP server: the card corpus as tools, resources and a prompt, for any MCP
host (Claude Desktop, Claude Code, VS Code + Copilot, Cursor, the MCP Inspector, or Python code
with `mcp.Client`).

    python mcp_server.py               # stdio: the host launches it as a subprocess
    MCP_HTTP=1 python mcp_server.py    # Streamable HTTP, stateless, on http://localhost:8000/mcp

Built with the reference MCP SDK (`mcp` >= 2, spec 2026-07-28, stateless): datapizza-ai 0.1.0 has
no MCP server, and its MCP client speaks only the older 1.x protocol. The agent of the app is not
involved: the host's own model reads the cards through these primitives.

    tool      search_cards(query, categories)   the agent's hybrid search (Qdrant + OpenAI key)
    tool      read_card(document_id)            one whole card
    tool      list_cards(category)              the catalogue: which cards exist
    resource  card://{document_id}              one card by URI (the indexed cards are listed)
    prompt    prepare_match(team, opponent)     the recipe: search, read, cite, "Non lo so"

Only `search_cards` needs Qdrant and the key (the embedding of a new query); the catalogue and the
cards are read from corpus/, rebuilt exactly as the agent reads them, so they work with nothing
running. The retriever is built at the first search and again after a failure: a server started
before Qdrant works as soon as Qdrant is up. Read-only: cards are looked up by id, never by path.
In stdio, stdout carries the protocol: nothing may write there (see keep_stdout_for_the_protocol).
"""

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

from mcp.server import MCPServer
from mcp.server.mcpserver.resources import FunctionResource
from mcp.types import ToolAnnotations
from pydantic import Field

from src.agent.analyst_agent import build_retriever
from src.core.config import load_settings
from src.corpus.cards import Card, load_manifest_cards
from src.corpus.chunking import chunk_card
from src.guardrails.input_guard import MAX_QUESTION_CHARS
from src.observability.logs import setup_logging
from src.observability.tracing import flush, set_output, setup_tracing, span
from src.rag.retrieval import Retriever, whole_card
from src.tools.corpus_tools import READ_DESCRIPTION, SEARCH_DESCRIPTION, Category, CorpusTools, source_header, unbracket

# No `from __future__ import annotations` here: the MCP SDK builds each tool's input schema from
# the real parameter annotations, as datapizza does for the agent's tools.

log = logging.getLogger(__name__)

SERVER_NAME = "Match Analyst"
INSTRUCTIONS = (
    "Football tactics knowledge base for coaches: 31 cards in Italian (recent finals, game "
    "situations, coach profiles, notes from Coverciano theses, glossary), every fact cited to its "
    "source. Use list_cards to see what exists, search_cards to find passages, read_card for a "
    "whole card. Answer only from the cards, cite each statement with the card's [document_id], "
    "and say \"Non lo so\" when the cards do not cover it."
)
LIST_DESCRIPTION = (
    "List the cards of the knowledge base: [document_id], title, category and date, one per line. "
    "Use it to see what the corpus covers before searching, or to find the id for read_card. "
    "Optional: only one category."
)
READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
PREPARE_MATCH = """I am a football coach. My team: {team}. The opponent: {opponent}.
Prepare the match using only the Match Analyst cards:
1. Search the game situations that fit (search_cards with categories ["game_situation"]), then real matches (["match_case"]); use list_cards to see what the corpus holds and read_card when a passage is not enough.
2. Give the recommendation in one or two sentences, then 3 to 5 bullet points. End every sentence with the [document_id] of the card it comes from, and include a real case from a [case_...] card when there is one.
3. Use only what the cards say and what I wrote about the two teams. If the cards do not cover something, write "Non lo so" for that part.
Answer in the language I used to describe the teams."""


class CardLibrary:
    """The indexed cards (corpus/manifest.json) read from the files, without Qdrant. A card's text is
    rebuilt from its chunks as Retriever.card_text does, so the host reads what the agent reads."""

    def __init__(self, cards: list[Card] | None = None) -> None:
        cards = load_manifest_cards() if cards is None else cards
        self.cards = {card.document_id: card for card in cards}
        self.texts = {card.document_id: whole_card(chunk_card(card)) or "" for card in cards}

    def catalog(self, category: str | None = None) -> str:
        """One line per card: [document_id] title · category · date."""
        cards = [c for c in self.cards.values() if category is None or c.metadata.get("category") == category]
        if not cards:
            return f"No card in category '{category}'. Categories: {', '.join(sorted(self.categories()))}."
        lines = [f"[{c.document_id}] {c.metadata.get('title', c.document_id)} · {c.metadata.get('category', '')}"
                 + (f" · {c.metadata['date']}" if c.metadata.get("date") else "") for c in cards]
        return f"{len(cards)} cards:\n" + "\n".join(lines)

    def categories(self) -> set[str]:
        return {c.metadata.get("category", "") for c in self.cards.values()}

    def read(self, document_id: str) -> str:
        """A whole card, headed by its id as the agent's read_card shows it."""
        document_id = document_id.strip().strip("[]")
        text = self.texts.get(document_id)
        if not text:
            return f"No card with document_id '{document_id}'. Use list_cards or search_cards to find the right id."
        title, _, body = text.partition("\n\n")
        return f"{source_header(document_id, title, 'scheda intera')}\n{unbracket(body)}"


def build_server(retriever_factory: Callable[[], Retriever] = build_retriever,
                 library: CardLibrary | None = None) -> MCPServer:
    """The MCP server; `retriever_factory` and `library` are replaced in the tests."""
    library = library or CardLibrary()
    state: dict[str, CorpusTools] = {}

    def corpus_tools() -> CorpusTools:
        """The agent's search tools, on a retriever built at the first search (not after a failure)."""
        if "tools" not in state:
            state["tools"] = CorpusTools(retriever_factory())
        return state["tools"]

    server = MCPServer(SERVER_NAME, instructions=INSTRUCTIONS)

    @server.tool(description=SEARCH_DESCRIPTION, annotations=READ_ONLY)
    def search_cards(
        query: Annotated[str, Field(description="What to look for, in Italian, with the key terms of the question")],
        categories: Annotated[list[Category] | None, Field(
            description="Optional: prefer these card types, e.g. ['coach_profile'] to compare coaches "
                        "(the best overall result is always included)")] = None,
    ) -> str:
        if len(query) > MAX_QUESTION_CHARS:
            log.warning("search_cards: query too long (%d characters)", len(query))
            return f"The query is too long (at most {MAX_QUESTION_CHARS} characters): use the key terms only."
        try:
            tools = corpus_tools()
        except Exception as e:   # Qdrant not running, index missing, API key not set
            log.warning("search_cards: knowledge base unavailable: %s: %s", type(e).__name__, e, exc_info=True)
            return (f"The knowledge base is unavailable ({type(e).__name__}: {e}). Start Qdrant with "
                    "`docker compose up -d` in the project folder; list_cards and read_card still work.")
        tools.calls.clear()   # the server lives long: keep only the last search
        with span("mcp search_cards", "TOOL", query) as current:
            result = tools.search_cards(query, categories)
            set_output(current, result)
        flush()
        return result

    @server.tool(description=READ_DESCRIPTION + " Use list_cards to see every id.", annotations=READ_ONLY)
    def read_card(
        document_id: Annotated[str, Field(description="Card id exactly as shown in brackets, e.g. coach_conte")],
    ) -> str:
        log.info("read_card: %s", document_id)
        return library.read(document_id)

    @server.tool(description=LIST_DESCRIPTION, annotations=READ_ONLY)
    def list_cards(
        category: Annotated[Category | None, Field(description="Optional: only this card type")] = None,
    ) -> str:
        log.info("list_cards: %s", category or "all")
        return library.catalog(category)

    @server.resource("card://{document_id}", mime_type="text/markdown",
                     description="One card of the knowledge base by URI, e.g. card://coach_pioli")
    def card(document_id: str) -> str:
        return library.read(document_id)

    for document_id, entry in library.cards.items():   # concrete resources, so hosts can list them
        server.add_resource(FunctionResource(
            uri=f"card://{document_id}", name=document_id, title=entry.metadata.get("title"),
            mime_type="text/markdown", fn=lambda document_id=document_id: library.read(document_id)))

    @server.prompt(description="Prepare a match: your team and the opponent, answered from the cards with citations.")
    def prepare_match(
        team: Annotated[str, Field(description="Your team: formation, traits, how it plays")],
        opponent: Annotated[str, Field(description="The opponent: formation, traits, how it plays")],
    ) -> str:
        return PREPARE_MATCH.format(team=team, opponent=opponent)

    return server


def keep_stdout_for_the_protocol() -> None:
    """In stdio, stdout carries the protocol, and any other line breaks it. datapizza logs to stdout
    (the console handler it adds to its "datapizza" logger on import): move it to stderr, which
    hosts show as the server's log."""
    for handler in logging.getLogger("datapizza").handlers:
        if isinstance(handler, logging.StreamHandler) and handler.stream is sys.stdout:
            handler.setStream(sys.stderr)


def main(log_folder: Path | None = None, tracing: bool = True) -> None:
    """Start the server: stdio, or Streamable HTTP (stateless) with MCP_HTTP=1. The tests pass a
    temporary `log_folder` and no tracing."""
    keep_stdout_for_the_protocol()
    settings = load_settings()
    setup_logging(settings.log_level, folder=log_folder)
    if tracing:
        log.info(setup_tracing(settings.phoenix_endpoint, settings.phoenix_project))
    server = build_server()
    http = bool(os.getenv("MCP_HTTP"))
    log.info("MCP server started: %s", "Streamable HTTP (stateless), http://localhost:8000/mcp" if http else "stdio")
    if http:
        server.run(transport="streamable-http", stateless_http=True)
    else:
        server.run()

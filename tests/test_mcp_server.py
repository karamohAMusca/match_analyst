"""The MCP server (src/mcp_server/server.py), offline: the in-memory index with `mcp.Client` connected
to the server in-process, plus one real stdio session with the server as a subprocess (list_cards
needs neither Qdrant nor a key)."""

from __future__ import annotations

import asyncio
import logging
import sys

import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

import src.mcp_server.server as mcp_server
from src.core.config import PROJECT_ROOT
from src.corpus.cards import load_manifest_cards
from src.tools.corpus_tools import CorpusTools

QUERY = "catene laterali del 4-4-2: terzino, centrocampista centrale ed esterno"


def session(server, steps):
    """Run `steps(client)` in one MCP session with `server` (an MCPServer, or stdio parameters)."""
    async def go():
        async with Client(server) as client:
            return await steps(client)
    return asyncio.run(go())


def text(result) -> str:
    return result.content[0].text


@pytest.fixture(scope="module")
def library():
    return mcp_server.CardLibrary()


@pytest.fixture
def server(retriever, library):
    return mcp_server.build_server(retriever_factory=lambda: retriever, library=library)


def test_three_read_only_tools_the_cards_as_resources_and_a_prompt(server):
    async def steps(c):
        return (await c.list_tools()).tools, await c.list_resources(), await c.list_resource_templates(), await c.list_prompts()
    tools, resources, templates, prompts = session(server, steps)
    assert sorted(t.name for t in tools) == ["list_cards", "read_card", "search_cards"]
    assert all(t.annotations.read_only_hint for t in tools)
    assert len(resources.resources) == len(load_manifest_cards()) == 31
    assert "card://coach_pioli" in [str(r.uri) for r in resources.resources]
    assert [str(t.uri_template) for t in templates.resource_templates] == ["card://{document_id}"]
    assert [p.name for p in prompts.prompts] == ["prepare_match"]


def test_search_is_the_agents_search(server, retriever):
    async def steps(c):
        return (text(await c.call_tool("search_cards", {"query": QUERY})),
                text(await c.call_tool("search_cards", {"query": QUERY, "categories": ["coach_profile"]})))
    plain, filtered = session(server, steps)
    assert plain == CorpusTools(retriever).search_cards(QUERY)
    assert filtered == CorpusTools(retriever).search_cards(QUERY, categories=["coach_profile"])


def test_every_card_reads_as_the_agent_reads_it(server, retriever, library):
    agent = CorpusTools(retriever)
    assert all(library.read(card) == agent.read_card(card) for card in library.cards)   # files = index
    shown = session(server, lambda c: c.call_tool("read_card", {"document_id": "[coach_pioli]"}))
    assert text(shown) == agent.read_card("coach_pioli")
    assert text(session(server, lambda c: c.call_tool("read_card", {"document_id": "coach_nobody"}))).startswith(
        "No card with document_id 'coach_nobody'")


def test_list_cards_is_the_catalogue(server, library):
    async def steps(c):
        return text(await c.call_tool("list_cards", {})), text(await c.call_tool("list_cards", {"category": "coach_profile"}))
    everything, coaches = session(server, steps)
    assert everything.startswith("31 cards:") and "[case_2026_wc_final_spain_argentina] " in everything
    lines = coaches.splitlines()[1:]
    assert coaches.startswith("10 cards:") and all(line.startswith("[coach_") for line in lines)
    assert "· 2026-07-19" in everything                                         # finals carry their date
    assert library.catalog("weather").startswith("No card in category 'weather'. Categories: coach_profile")
    rejected = session(server, lambda c: c.call_tool("list_cards", {"category": "weather"}))
    assert rejected.is_error                                                   # outside the schema


def test_a_card_by_uri(server, library):
    async def steps(c):
        return (await c.read_resource("card://coach_conte")).contents[0].text, \
            (await c.read_resource("card://coach_nobody")).contents[0].text
    conte, nobody = session(server, steps)
    assert conte == library.read("coach_conte") and conte.startswith("[coach_conte] ")
    assert nobody.startswith("No card with document_id 'coach_nobody'")


def test_search_without_qdrant_explains_and_recovers(retriever, library):
    attempts = []

    def factory():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("Qdrant is not reachable")
        return retriever
    server = mcp_server.build_server(retriever_factory=factory, library=library)

    async def steps(c):
        return (text(await c.call_tool("search_cards", {"query": QUERY})),
                text(await c.call_tool("list_cards", {"category": "glossary"})),
                text(await c.call_tool("search_cards", {"query": QUERY})))
    down, catalogue, up = session(server, steps)
    assert down.startswith("The knowledge base is unavailable (ConnectionError: Qdrant is not reachable)")
    assert catalogue.startswith("2 cards:")                                    # no Qdrant needed
    assert up == CorpusTools(retriever).search_cards(QUERY) and len(attempts) == 2   # built again


def test_a_query_too_long_is_refused(server):
    result = session(server, lambda c: c.call_tool("search_cards", {"query": "pressing " * 300}))
    assert text(result).startswith("The query is too long (at most 2000 characters)")


def test_the_prepare_match_prompt(server):
    prompt = session(server, lambda c: c.get_prompt(
        "prepare_match", {"team": "4-3-3 con esterni veloci", "opponent": "4-4-2 basso"}))
    message = prompt.messages[0].content.text
    assert "My team: 4-3-3 con esterni veloci. The opponent: 4-4-2 basso." in message
    assert all(word in message for word in ("search_cards", "[document_id]", '"Non lo so"'))


def test_datapizza_console_log_is_moved_off_stdout():
    logger = logging.getLogger("datapizza")
    before = {h: h.stream for h in logger.handlers if isinstance(h, logging.StreamHandler)}
    probe = logging.StreamHandler(sys.stdout)
    logger.addHandler(probe)
    try:
        mcp_server.keep_stdout_for_the_protocol()
        assert probe.stream is sys.stderr
    finally:
        logger.removeHandler(probe)
        for handler, stream in before.items():
            handler.setStream(stream)


def test_a_real_stdio_session(tmp_path):
    # The server as a host starts it: a subprocess speaking MCP on stdin/stdout. Any stray line
    # on stdout would break this session.
    params = StdioServerParameters(
        command=sys.executable, cwd=str(PROJECT_ROOT),
        args=["-c", "from pathlib import Path; from src.mcp_server.server import main; "
                    f"main(log_folder=Path(r'{tmp_path}'), tracing=False)"])

    async def steps(c):
        return [t.name for t in (await c.list_tools()).tools], text(await c.call_tool("list_cards", {}))
    tools, catalogue = session(params, steps)
    assert sorted(tools) == ["list_cards", "read_card", "search_cards"]
    assert catalogue.startswith("31 cards:")
    log = (tmp_path / "match_analyst.log").read_text(encoding="utf-8")
    assert "MCP server started: stdio" in log and "list_cards: all" in log

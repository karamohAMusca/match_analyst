"""Corpus tools (search_cards, read_card): output format, filters, errors, schema — offline."""

from __future__ import annotations

import re

from datapizza.vectorstores.qdrant import QdrantVectorstore

from src.corpus.cards import load_cards
from src.rag.retrieval import Retriever
from src.rag.store import ensure_collection
from src.tools.corpus_tools import CorpusTools, card_context
from tests.fakes import COLLECTION, DIM, FakeEmbedder

QUERY = "catene laterali del 4-4-2: terzino, centrocampista centrale ed esterno"
HEADER = re.compile(r"^\[([a-z0-9_]+)\] (.+) · (.+)$", re.M)


def test_search_returns_cited_passages_one_per_card(retriever):
    output = CorpusTools(retriever).search_cards(QUERY)
    headers = HEADER.findall(output)
    assert 1 <= len(headers) <= 5
    cards = [card for card, _, _ in headers]
    assert len(cards) == len(set(cards))                       # at most one passage per card
    assert "coach_pioli" in cards
    sections = [section for _, _, section in headers]
    assert sections[:2] == ["scheda intera", "scheda intera"]      # first 2 results: whole cards
    assert all(s != "scheda intera" for s in sections[2:])


def test_search_category_filter_is_a_preference(retriever):
    cards = [c for c, _, _ in HEADER.findall(CorpusTools(retriever).search_cards(QUERY, categories=["coach_profile"]))]
    assert len(cards) == 5 and sum(c.startswith("coach_") for c in cards) >= 4


def test_wrong_filter_cannot_hide_the_best_card(retriever):
    # The agent filtered on thesis notes for "nella tesi di Pioli" and lost coach_pioli (run 160112).
    unfiltered = [c for c, _, _ in HEADER.findall(CorpusTools(retriever).search_cards(QUERY))]
    filtered = [c for c, _, _ in HEADER.findall(CorpusTools(retriever).search_cards(QUERY, categories=["thesis_note"]))]
    assert filtered[0] == unfiltered[0]
    assert all(c.startswith("note_") for c in filtered[1:])


def test_search_on_empty_index_says_so():
    store = QdrantVectorstore(location=":memory:")
    ensure_collection(store, COLLECTION, DIM)
    tools = CorpusTools(Retriever(store, FakeEmbedder(), COLLECTION))
    assert tools.search_cards(QUERY).startswith("No passage found")


class BrokenRetriever:
    def retrieve(self, *args, **kwargs):
        raise ConnectionError("Qdrant is down")


def test_search_errors_are_explained_not_raised():
    tools = CorpusTools(BrokenRetriever())
    output = tools.search_cards(QUERY)
    assert output.startswith("Search failed") and "Qdrant is down" in output
    assert tools.calls[-1]["error"]


def test_read_card_returns_the_whole_card(retriever):
    card = next(c for c in load_cards() if c.document_id == "coach_conte")
    output = CorpusTools(retriever).read_card("[coach_conte]")      # brackets are tolerated
    assert output.startswith("[coach_conte] Profilo allenatore: Antonio Conte · scheda intera")
    for heading in re.findall(r"^## .+$", card.body, re.M):
        assert heading in output


def test_card_ids_are_the_only_bracketed_text(retriever):
    # Card-internal references like [Pioli, p. 4] became (Pioli, p. 4): the model copied them as citations.
    tools = CorpusTools(retriever)
    for output in (tools.search_cards(QUERY), tools.read_card("coach_pioli")):
        bracketed_lines = [line for line in output.splitlines() if "[" in line]
        assert bracketed_lines and all(HEADER.match(line) for line in bracketed_lines)
    assert "(Pioli, p. 4)" in tools.read_card("coach_pioli")


def test_read_card_unknown_id(retriever):
    assert CorpusTools(retriever).read_card("coach_mourinho").startswith("No card")


def test_consulted_cards_in_order_without_repeats(retriever):
    tools = CorpusTools(retriever)
    tools.search_cards(QUERY)
    tools.read_card("coach_pioli")
    tools.read_card("coach_nobody")
    consulted = tools.consulted_cards()
    assert consulted[0] == tools.calls[0]["cards"][0]
    assert consulted.count("coach_pioli") == 1 and "coach_nobody" not in consulted


def test_tool_schemas_for_the_model(retriever):
    search, read = CorpusTools(retriever).tools()
    assert search.name == "search_cards" and search.required == ["query"]
    assert "self" not in search.properties
    enum = search.properties["categories"]["anyOf"][0]["items"]["enum"]
    assert set(enum) == {"match_case", "game_situation", "coach_profile", "thesis_note", "glossary"}
    assert "Gasperini" in search.description and "No live data" in search.description
    assert read.name == "read_card" and read.required == ["document_id"]


def test_card_context_gives_whole_cards_with_their_id():
    context = card_context({"coach_pioli": "Tesi [Pioli, p. 4].", "coach_klopp": "", "note_x": "Testo."})
    assert context == "[coach_pioli]\nTesi (Pioli, p. 4).\n\n[note_x]\nTesto."   # empty cards left out
